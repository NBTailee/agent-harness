import os
import re
import shutil
import fnmatch
import subprocess
import time
from pathlib import Path
from typing import Any
import json


# Kaggle account every listing is scoped to.
KAGGLE_OWNER = "nbtailee22"

# Keys Kaggle expects as JSON booleans. `kaggle * init` templates write
# them as the strings "true"/"false", which are truthy in Python.
# Private dataset (uploaded by the user) holding keys/.env; kernels attach it.
KEYS_DATASET = f"{KAGGLE_OWNER}/secret-keys"
BOOL_KEYS = {
    "is_private", "isPrivate",
    "enable_gpu", "enable_tpu", "enable_internet",
}

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

PLACEHOLDER_MARK = "INSERT_"


def normalize_bools(metadata: dict) -> dict:
    """Convert "true"/"false" strings to real booleans for BOOL_KEYS."""
    for key in BOOL_KEYS & metadata.keys():
        value = metadata[key]
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            metadata[key] = value.strip().lower() == "true"
    return metadata


def find_placeholders(metadata: dict, keys) -> list[str]:
    """Return the keys whose value still holds an INSERT_..._HERE placeholder."""
    found = []
    for key in keys:
        value = metadata.get(key)
        values = value if isinstance(value, list) else [value]
        if any(isinstance(v, str) and PLACEHOLDER_MARK in v for v in values):
            found.append(key)
    return found


def validate_ref(ref: str, kind: str) -> str:
    """Validate an 'owner/slug' reference."""
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError(f"{kind} metadata must contain a valid 'id'.")
    ref = ref.strip()
    if PLACEHOLDER_MARK in ref:
        raise ValueError(
            f"{kind} id is still the init placeholder ({ref}). "
            f"Set it to 'nbtailee22/<slug>' first."
        )
    parts = ref.split("/")
    if len(parts) != 2 or not parts[0] or not SLUG_RE.match(parts[1]):
        raise ValueError(
            f"Invalid {kind} id: {ref}. Expected 'owner/slug' where slug is "
            f"lowercase letters, digits and single hyphens."
        )
    return ref


def _add_keys_source(metadata: dict) -> None:
    """Every kernel gets the keys dataset, next to its other sources."""
    sources = list(metadata.get("dataset_sources") or [])
    if KEYS_DATASET not in sources:
        sources.append(KEYS_DATASET)
    metadata["dataset_sources"] = sources


def write_json(path: Path, data: dict, indent: int = 4) -> Path:
    with Path(path).open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=indent, ensure_ascii=False)
    return Path(path)


def normalize_file(path: Path, indent: int = 4) -> None:
    """Rewrite an init-generated metadata file with real booleans."""
    path = Path(path)
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        write_json(path, normalize_bools(data), indent)


# Kaggle answers 403 both for private items and for items that do not
# exist, so an access error usually means a wrong slug.
ACCESS_DENIED_RE = re.compile(
    r"\b403\b|forbidden|permission '[^']+' was denied|"
    r"don't have access|do not have access",
    re.IGNORECASE,
)
REF_RE = re.compile(r"^[^/\s-][^/\s]*/[^/\s]+$")


def _target_ref(command) -> str | None:
    """The owner/slug argument of a CLI command, if any."""
    for arg in command[3:]:
        if REF_RE.match(str(arg)) and not Path(str(arg)).exists():
            return str(arg)
    return None


# tqdm bar, e.g. " 45%|####5     | 141/313 [00:12<00:15,  6.55it/s]"
TQDM_RE = re.compile(
    r"(?P<pct>\d{1,3})%\|[^|]*\|\s*(?P<n>\d+)/(?P<total>\d+)\s*"
    r"\[(?P<elapsed>[\d:]+)<(?P<remaining>[\d:]+|\?)"
)
# Printed by AgentRun: "PROGRESS step=12/150 elapsed=24.3s"
AGENT_PROGRESS_RE = re.compile(
    r"PROGRESS step=(?P<n>\d+)(?:/(?P<total>\d+))? elapsed=(?P<elapsed>[\d.]+)s")
# Generic script output, e.g. "EPOCH 12/150" or "step: 40/500"
STEP_LINE_RE = re.compile(
    r"\b(?:epoch|step|iter(?:ation)?)\s*[:=]?\s*(?P<n>\d+)\s*/\s*(?P<total>\d+)",
    re.I)
# Labeled bars that count data, not training steps.
DATA_BAR_RE = re.compile(
    r"map|generating|download|filter|token|load|extract|eval|predict", re.I)
WORKER_STATUS_RE = re.compile(r"KernelWorkerStatus\.(\w+)")
PLAIN_STATUS_RE = re.compile(r'has status "?(\w+)"?')
TERMINAL_STATUSES = {"COMPLETE", "ERROR", "CANCELLED", "CANCEL_ACKNOWLEDGED"}


def _clock_to_seconds(clock: str) -> int | None:
    """'1:02:03' / '02:03' -> seconds; '?' -> None."""
    if not clock or "?" in clock:
        return None
    seconds = 0
    for part in clock.split(":"):
        seconds = seconds * 60 + int(part)
    return seconds


def log_text(raw: str) -> str:
    """Turn a Kaggle log (JSON events, or plain text) into plain text."""
    chunks = []
    for line in raw.splitlines():
        line = line.strip().lstrip(",").strip()
        if not line:
            continue
        try:
            event = json.loads(line.rstrip(","))
        except ValueError:
            # Whole log may be one JSON array spread over lines; fall back
            # to the raw line if it is not a JSON object.
            chunks.append(line)
            continue
        events = event if isinstance(event, list) else [event]
        for item in events:
            if isinstance(item, dict):
                chunks.append(str(item.get("data", "")))
            else:
                chunks.append(str(item))
    return "".join(c if c.endswith("\n") else c + "\n" for c in chunks)


def _progress_from_lines(lines: list[str]) -> dict[str, Any]:
    """Fallback when no tqdm bar reached the log yet."""
    for line in reversed(lines):
        match = AGENT_PROGRESS_RE.search(line)
        if match:
            n, elapsed = int(match["n"]), float(match["elapsed"])
            total = int(match["total"]) if match["total"] else None
            out = {"found": True, "source": "agent_run", "step": n,
                   "total_steps": total, "elapsed_seconds": round(elapsed)}
            if total and n:
                out["percent"] = min(100, round(100 * n / total))
                out["remaining_seconds"] = round(elapsed * (total - n) / n)
            return out
    for line in reversed(lines):
        match = STEP_LINE_RE.search(line)
        if match and int(match["total"]) > 0:
            n, total = int(match["n"]), int(match["total"])
            return {"found": True, "source": "log_line", "step": n,
                    "total_steps": total,
                    "percent": min(100, round(100 * n / total)),
                    "remaining_seconds": None}
    return {}


def parse_progress(raw: str) -> dict[str, Any]:
    """
    Extract training progress from a kernel log.

    The Trainer's bars have no label and count iterations (it/s or s/it),
    unlike labeled data bars ("Map:", "Generating train split:") that
    count examples. The training bar is the first such bar to appear;
    eval bars that interleave with it have a different total.
    """
    text = log_text(raw)
    segments = [seg for seg in re.split(r"[\r\n]+", text) if seg.strip()]

    bars, labeled = [], []
    for seg in segments:
        match = TQDM_RE.search(seg)
        if not match:
            continue
        # Drop ANSI cursor codes (nested eval bars print "\x1b[A").
        label = re.sub(r"\x1b\[[0-9;]*[A-Za-z]|\[A", "", seg[:match.start()])
        unit_ok = re.search(r"(it/s|s/it)", seg[match.end():])
        # The first frame of a bar has no rate yet ("<?").
        unit_ok = unit_ok or "<?" in seg
        if not unit_ok:
            continue
        if not label.strip():
            bars.append(match.groupdict())
        elif not DATA_BAR_RE.search(label):
            labeled.append(match.groupdict())
    bars = bars or labeled

    lines = [seg for seg in segments if not TQDM_RE.search(seg)]
    progress: dict[str, Any] = {"found": False, "tail": lines[-8:]}

    if bars:
        train_total = int(bars[0]["total"])
        bar = [b for b in bars if int(b["total"]) == train_total][-1]
        progress.update({
            "found": True,
            "step": int(bar["n"]),
            "total_steps": train_total,
            "percent": int(bar["pct"]),
            "elapsed_seconds": _clock_to_seconds(bar["elapsed"]),
            "remaining_seconds": _clock_to_seconds(bar["remaining"]),
        })
    else:
        progress.update(_progress_from_lines(lines))

    epochs = re.findall(r"'epoch':\s*'?([\d.]+)", text)
    if epochs:
        progress["epoch"] = float(epochs[-1])

    return progress


def parse_status(stdout: str) -> str:
    match = (WORKER_STATUS_RE.search(stdout or "")
             or PLAIN_STATUS_RE.search(stdout or ""))
    return match.group(1).upper() if match else "UNKNOWN"


class KaggleCLIError(RuntimeError):
    def __init__(self, command, returncode, stdout, stderr):
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.ref = _target_ref(command)
        self.access_denied = bool(
            ACCESS_DENIED_RE.search(f"{stderr}\n{stdout}")
        )

        details = (stderr or "").strip() or (stdout or "").strip()
        message = (
            f"Kaggle CLI failed ({returncode}): "
            f"{' '.join(map(str, command))}\n{details}"
        )

        if self.access_denied:
            target = f"'{self.ref}'" if self.ref else "the target"
            message += (
                f"\nHint: {target} was not found or is private. Kaggle "
                f"returns 403 for both. Check the slug in the metadata "
                f"file against the list tools before looking for a "
                f"permissions problem."
            )

        super().__init__(message)


class KaggleExecutor:

    def __init__(self, timeout: int = 200):
        self.timeout = timeout

    def _run(
        self,
        *args: str | Path,
        timeout: int | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess:

        command = [
            "kaggle",
            *map(str, args),
        ]

        # The Kaggle CLI is Python: force UTF-8 on its pipes so non-ASCII
        # text (e.g. em dashes in hints) is not garbled by the Windows
        # code page, and decode it as UTF-8 on our side.
        env = {
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }

        result = subprocess.run(
            command,
            timeout=timeout or self.timeout,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=False,
        )

        if check and result.returncode != 0:
            raise KaggleCLIError(
                command=command,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )

        return result


class KernelExecutor(KaggleExecutor):

    def __init__(
        self,
        kernel_path: Path,
        output_path: Path,
        kernel_id: str,
        timeout: int = 200,
    ):
        super().__init__(timeout)

        self.kernel_path = Path(kernel_path)
        self.output_path = Path(output_path)
        # Fallback only: the real kernel id always comes from
        # kernel-metadata.json (see read_kernel_id).
        self.kernel_id = kernel_id.replace("_", "-")
        # time.time() of the most recent push in this session.
        self.last_push_time: float | None = None
        # Whether the most recent push used --no-run. Kaggle reports a
        # misleading RUNNING -> ERROR lifecycle for never-executed versions.
        self.last_push_no_run: bool | None = None

    def read_metadata(self) -> dict[str, Any]:
        metadata_path = self.kernel_path / "kernel-metadata.json"

        if not metadata_path.is_file():
            raise FileNotFoundError(
                f"{metadata_path} does not exist. Initialize the kernel first."
            )

        with metadata_path.open("r", encoding="utf-8") as file:
            metadata = json.load(file)

        if not isinstance(metadata, dict):
            raise ValueError("Kernel metadata must be a JSON object.")

        return metadata

    @property
    def metadata_path(self) -> Path:
        return self.kernel_path / "kernel-metadata.json"

    def read_kernel_id(self) -> str:
        return validate_ref(self.read_metadata().get("id"), "Kernel")

    def validate_for_push(self) -> dict[str, Any]:
        """Local pre-flight check so placeholder or broken metadata never
        reaches the Kaggle CLI."""
        metadata = self.read_metadata()
        validate_ref(metadata.get("id"), "Kernel")

        required = ("id", "title", "code_file", "language", "kernel_type")
        missing = [k for k in required if not metadata.get(k)]
        if missing:
            raise ValueError(f"Kernel metadata is missing: {missing}")

        placeholders = find_placeholders(
            metadata,
            required + ("dataset_sources", "model_sources",
                        "competition_sources", "kernel_sources"),
        )
        if placeholders:
            raise ValueError(
                f"Kernel metadata still has init placeholders in: "
                f"{placeholders}. Set them with write_kaggle_metadata."
            )

        code_file = (self.kernel_path / metadata["code_file"]).resolve()
        if not code_file.is_file():
            raise FileNotFoundError(
                f"code_file '{metadata['code_file']}' not found in the "
                f"kernel directory ({code_file})."
            )

        # AgentRun groups W&B runs by KERNEL_SLUG; the W&B tools look up the metadata slug.
        slug = metadata["id"].split("/")[-1]
        match = re.search(r"^KERNEL_SLUG\s*=\s*[\"']([^\"']*)[\"']",
                          code_file.read_text(encoding="utf-8"), re.M)
        if match and match.group(1) != slug:
            raise ValueError(
                f"KERNEL_SLUG in {metadata['code_file']} is "
                f"'{match.group(1)}' but the metadata slug is '{slug}'. "
                f"Set KERNEL_SLUG = \"{slug}\"."
            )

        return metadata

    def init(self):
        kernel_path = Path(self.kernel_path).resolve()

        if not self.kernel_path.is_dir():
            raise NotADirectoryError(str(self.kernel_path))

        result = self._run(
            "kernels",
            "init",
            "-p",
            kernel_path
        )
        normalize_file(self.metadata_path)
        return result

    def push(
        self,
        accelerator: str = None,
        timeout: int = None,
        no_run: bool = None,
        code_override: str | None = None,
    ):
        kernel_path = Path(self.kernel_path).resolve()

        if not kernel_path.is_dir():
            raise NotADirectoryError(str(kernel_path))

        self.write_metadata({})  # adds the keys dataset if missing
        metadata = self.validate_for_push()

        push_path = kernel_path
        if code_override is not None:
            # Push a build copy so the agent's own train.py stays as written.
            push_path = kernel_path / ".push_build"
            shutil.rmtree(push_path, ignore_errors=True)
            code_path = push_path / metadata["code_file"]
            code_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(self.metadata_path, push_path / self.metadata_path.name)
            code_path.write_text(code_override, encoding="utf-8")

        command = ["kernels", "push", "-p", push_path]

        if accelerator is not None:
            command.extend(["--accelerator", accelerator])

        if no_run:
            command.append("--no-run")

        if timeout is not None:
            command.extend(["-t", str(timeout)])

        result = self._run(*command)
        self.last_push_no_run = bool(no_run)
        self.last_push_time = time.time()
        return result

    def logs(self, follow_seconds: int | None = None) -> str:
        """
        Kernel execution log. With follow_seconds, stream the live log of
        a running kernel (`kaggle kernels logs -f`) for that many seconds
        and return what arrived.
        """
        kernel_id = self.read_kernel_id()

        if not follow_seconds:
            return self._run("kernels", "logs", kernel_id).stdout

        try:
            return self._run(
                "kernels", "logs", kernel_id, "-f",
                timeout=follow_seconds, check=False,
            ).stdout
        except subprocess.TimeoutExpired as exc:
            # Expected: -f streams until the run ends. Keep what arrived.
            out = exc.stdout or b""
            return out.decode("utf-8", errors="replace") \
                if isinstance(out, bytes) else out

    def status(self):
        return self._run("kernels", "status", self.read_kernel_id())

    def kernel_slug(self) -> str:
        """Slug part of the kernel id from kernel-metadata.json."""
        return self.read_kernel_id().split("/")[-1]

    def log_path(self) -> Path:
        """
        Locate the raw log written by `kaggle kernels output`.

        The CLI names it after the kernel slug from the metadata id.
        Fall back to the newest non-pretty *.log in the output dir.
        """
        output_path = Path(self.output_path)
        expected = output_path / f"{self.kernel_slug()}.log"

        if expected.is_file():
            return expected

        candidates = sorted(
            (
                p for p in output_path.glob("*.log")
                if not p.name.endswith(".pretty.log")
            ),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if candidates:
            return candidates[0]

        raise FileNotFoundError(
            f"Kernel log not found: expected {expected} (named after the "
            f"kernel id in kernel-metadata.json) and no other *.log file "
            f"exists in {output_path}. The kernel may not have finished, "
            f"or the download used a file pattern that excluded the log."
        )

    def pretty_log_path(self) -> Path:
        return Path(self.output_path) / f"{self.kernel_slug()}.pretty.log"

    @staticmethod
    def normalize_file_pattern(pattern: str) -> str:
        """Accept a regex; if it is not valid regex, treat it as a glob."""
        try:
            re.compile(pattern)
            return pattern
        except re.error:
            return fnmatch.translate(pattern)

    def delete(self):
        return self._run(
            "kernels", "delete", self.read_kernel_id(), "-y"
        )

    def list_output_files(self, page_size: int = None):
        command = ["kernels", "files", self.read_kernel_id()]

        if page_size is not None:
            command.extend(["--page-size", str(page_size)])

        return self._run(*command)

    def download_output_files(
        self,
        force: bool = False,
        quiet: bool = False,
        regex: str = None,
        page_size: int = None,
    ):
        output_path = Path(self.output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        command = [
            "kernels",
            "output",
            self.read_kernel_id(),
            "-p",
            str(output_path),
        ]

        if force:
            command.append("-o")

        if quiet:
            command.append("-q")

        if regex is not None:
            command.extend(
                ["--file-pattern", self.normalize_file_pattern(regex)]
            )

        if page_size is not None:
            command.extend(["--page-size", str(page_size)])

        # Beautifying the log is a separate step: its failure must not
        # turn a successful download into a failure.
        return self._run(*command)

    def beautify_log(self) -> Path:
        path = self.log_path()
        output_path = self.pretty_log_path()

        events = json.loads(path.read_text(encoding="utf-8"))
        output = []

        for event in events:
            stream = event.get("stream_name", "stdout").upper()
            timestamp = event.get("time", 0)
            data = event.get("data", "")

            buffer = ""

            for char in data:
                if char == "\r":
                    buffer = ""
                elif char == "\n":
                    if buffer:
                        output.append(
                            f"[{timestamp:09.3f}s] [{stream}] {buffer}"
                        )
                    buffer = ""
                else:
                    buffer += char

            if buffer:
                output.append(
                    f"[{timestamp:09.3f}s] [{stream}] {buffer}"
                )

        output_path.write_text(
            "\n".join(output) + "\n",
            encoding="utf-8",
        )

        return output_path

    def get_output_log(self):
        path = self.pretty_log_path()

        if not path.is_file():
            # The raw log may exist from an earlier download; build the
            # pretty log from it instead of blaming the caller.
            try:
                path = self.beautify_log()
            except FileNotFoundError as err:
                raise FileNotFoundError(
                    f"{err} Download the output with "
                    f"kaggle_download_output_files first."
                ) from err

        return path.read_text(encoding="utf-8")

    def write_metadata(
        self,
        meta_dict: dict[str, Any],
        remove_keys: list[str] | None = None,
    ):
        if not isinstance(meta_dict, dict):
            raise TypeError("meta_dict must be a dictionary")

        metadata = self.read_metadata()

        # Partial update: only supplied fields change.
        metadata.update(meta_dict)

        for key in remove_keys or []:
            metadata.pop(key, None)

        _add_keys_source(metadata)

        normalize_bools(metadata)
        metadata_path = self.metadata_path

        try:
            return write_json(metadata_path, metadata, 4)

        except (OSError, TypeError, ValueError) as err:
            raise RuntimeError(
                f"Error writing kernel metadata at {metadata_path}: {err}"
            ) from err


class DatasetExecutor(KaggleExecutor):

    def __init__(
        self,
        dataset_path: Path,
        dataset_id: str,
        timeout: int = 200,
    ):
        super().__init__(timeout)

        self.dataset_path = Path(dataset_path).resolve()
        self.dataset_id = dataset_id.replace("_", "-")

    def _validate_path(self):
        if not self.dataset_path.is_dir():
            raise NotADirectoryError(
                str(self.dataset_path)
            )

    def read_dataset_id(self) -> str:
        ref = validate_ref(self.read_metadata().get("id"), "Dataset")
        if ref == KEYS_DATASET:
            raise ValueError(
                f"{KEYS_DATASET} holds API keys and is off-limits to the "
                "dataset tools. Only attach it via dataset_sources."
            )
        return ref

    def _validate_for_upload(self):
        metadata = self._validate_metadata()
        self.read_dataset_id()
        placeholders = find_placeholders(metadata, ("id", "title"))
        if placeholders:
            raise ValueError(
                f"Dataset metadata still has init placeholders in: "
                f"{placeholders}. Set them with write_kaggle_dataset_metadata."
            )
        if not metadata.get("title"):
            raise ValueError("Dataset metadata is missing 'title'.")

    @property
    def metadata_path(self) -> Path:
        return self.dataset_path / "dataset-metadata.json"

    def _validate_metadata(self):
        if not self.metadata_path.is_file():
            raise FileNotFoundError(
                f"{self.metadata_path} does not exist. "
                "Initialize the dataset first."
            )

        with self.metadata_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            metadata = json.load(file)

        return metadata

    def init(self):
        self.dataset_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        result = self._run(
            "datasets",
            "init",
            "-p",
            self.dataset_path,
        )
        normalize_file(self.metadata_path)
        return result

    def write_metadata(self, meta_dict: dict[str, Any]):
        if not isinstance(meta_dict, dict):
            raise TypeError("meta_dict must be a dictionary")

        metadata = self._validate_metadata()
        metadata.update(meta_dict)
        normalize_bools(metadata)

        return write_json(self.metadata_path, metadata, 4)

    def read_metadata(self):
        return self._validate_metadata()

    def create(
        self,
        public: bool = False,
        quiet: bool = False,
    ):
        self._validate_path()
        self._validate_for_upload()

        command = [
            "datasets",
            "create",
            "-p",
            self.dataset_path,
        ]

        if public:
            command.append("--public")

        if quiet:
            command.append("-q")

        return self._run(*command)

    def version(
        self,
        message: str,
        convert_to_csv: bool = False,
        quiet: bool = False,
    ):
        self._validate_path()
        self._validate_for_upload()

        if not message.strip():
            raise ValueError(
                "Version message cannot be empty."
            )

        command = [
            "datasets",
            "version",
            "-p",
            self.dataset_path,
            "-m",
            message,
        ]

        if convert_to_csv:
            command.append("--convert-to-csv")

        if quiet:
            command.append("-q")

        return self._run(*command)

    def status(self):
        return self._run(
            "datasets", "status", self.read_dataset_id()
        )

    def list_files(self):
        return self._run(
            "datasets", "files", self.read_dataset_id()
        )

    def delete(self):
        return self._run(
            "datasets", "delete", self.read_dataset_id(), "-y"
        )

    def download(
        self,
        output_path: Path,
        force: bool = False,
        unzip: bool = False,
        quiet: bool = False,
    ):
        output_path = Path(output_path).resolve()

        output_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        command = [
            "datasets",
            "download",
            self.read_dataset_id(),
            "-p",
            output_path,
        ]

        if force:
            command.append("-o")

        if unzip:
            command.append("--unzip")

        if quiet:
            command.append("-q")

        return self._run(*command)

    def list_available_datasets(self):
        return self._run(
            "datasets",
            "list",
            "--user",
            KAGGLE_OWNER,
        )


class ModelExecutor(KaggleExecutor):
    MODEL_METADATA = "model-metadata.json"

    def __init__(
        self,
        model_path: Path | str,
        model_ref: str | None = None,
        timeout: int = 600,
    ):
        super().__init__(timeout=timeout)

        self.model_path = Path(model_path).expanduser().resolve()
        self.model_ref = model_ref

    def read_model_ref(self) -> str:
        metadata = self.read_metadata()

        owner = metadata.get("ownerSlug")
        slug = metadata.get("slug")

        if not isinstance(owner, str) or not owner.strip():
            raise ValueError(
                "Model metadata must contain a valid 'ownerSlug'."
            )

        if not isinstance(slug, str) or not slug.strip():
            raise ValueError(
                "Model metadata must contain a valid 'slug'."
            )

        return validate_ref(f"{owner.strip()}/{slug.strip()}", "Model")

    @property
    def metadata_path(self) -> Path:
        return self.model_path / self.MODEL_METADATA

    def validate_path(self) -> Path:
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Model directory does not exist: {self.model_path}"
            )

        if not self.model_path.is_dir():
            raise NotADirectoryError(
                f"Not a directory: {self.model_path}"
            )

        return self.model_path

    def _require_model_ref(self) -> str:
        return self.read_model_ref()

    # Metadata

    def init(self):
        """Initialize model-metadata.json."""
        self.model_path.mkdir(parents=True, exist_ok=True)

        result = self._run(
            "models",
            "init",
            "-p",
            self.model_path,
        )
        normalize_file(self.metadata_path, indent=2)

        # Same convention as kernel/dataset templates, whose ids already
        # carry the owner: pre-fill ownerSlug so only `slug` is left.
        if self.metadata_path.is_file():
            metadata = self.read_metadata()
            if PLACEHOLDER_MARK in str(metadata.get("ownerSlug", "")):
                metadata["ownerSlug"] = KAGGLE_OWNER
                write_json(self.metadata_path, metadata, 2)

        return result

    def read_metadata(self) -> dict[str, Any]:
        """Read model metadata."""
        self.validate_path()

        if not self.metadata_path.exists():
            raise FileNotFoundError(
                f"Metadata not found: {self.metadata_path}"
            )

        with self.metadata_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    def write_metadata(
        self,
        metadata: dict[str, Any],
    ) -> Path:
        """Create or update model metadata."""
        self.model_path.mkdir(parents=True, exist_ok=True)

        if not isinstance(metadata, dict):
            raise TypeError("metadata must be a dictionary")

        current = {}

        if self.metadata_path.exists():
            current = self.read_metadata()

        current.update(metadata)
        normalize_bools(current)

        return write_json(self.metadata_path, current, 2)

    # Model operations

    def create(self):
        """Create a Kaggle Model."""
        self.validate_path()

        if not self.metadata_path.exists():
            raise FileNotFoundError(
                "Run init() and configure model-metadata.json first."
            )

        metadata = self.read_metadata()

        required = ("ownerSlug", "title", "slug")
        missing = [
            key for key in required
            if not metadata.get(key)
        ]

        if missing:
            raise ValueError(
                f"Missing required metadata fields: {missing}"
            )

        placeholders = find_placeholders(metadata, required)
        if placeholders:
            raise ValueError(
                f"Model metadata still has init placeholders in: "
                f"{placeholders}. Set them with write_kaggle_model_metadata."
            )

        self.read_model_ref()

        return self._run(
            "models",
            "create",
            "-p",
            self.model_path,
        )

    def update(self):
        self.validate_path()
        self.read_model_ref()

        return self._run(
            "models",
            "update",
            "-p",
            self.model_path,
        )

    def get(
        self,
        output_path: Path | str | None = None,
    ):
        """Get model details from Kaggle."""
        model_ref = self._require_model_ref()

        target = Path(
            output_path or self.model_path
        ).expanduser()

        target.mkdir(parents=True, exist_ok=True)

        return self._run(
            "models",
            "get",
            model_ref,
            "-p",
            target,
        )

    def list(
        self,
        search: str | None = None,
        page_size: int = 20,
        sort_by: str | None = None,
    ):
        """List Kaggle Models owned by KAGGLE_OWNER."""
        if page_size < 1:
            raise ValueError("page_size must be >= 1")

        command = [
            "models",
            "list",
            "--page-size",
            str(page_size),
            "--owner",
            KAGGLE_OWNER,
        ]

        if search:
            command.extend(["--search", search])

        if sort_by:
            command.extend(["--sort-by", sort_by])

        return self._run(*command)

    def delete(self, confirm: bool = False):
        """Delete a Kaggle Model."""
        if not confirm:
            raise ValueError("Deletion requires confirm=True.")

        return self._run(
            "models",
            "delete",
            self._require_model_ref(),
            "-y",
        )
