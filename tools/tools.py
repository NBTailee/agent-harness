import json
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
from tools.sandbox.model import ToolContext
from typing import Any

PROJECT_ROOT = Path.cwd().resolve()


SANDBOX_MOUNT_HINT = (
    "Use a sandbox path under /deliverables or /kaggle_sandbox, a path "
    "relative to /deliverables, or a host path inside an allowed folder."
)


def _sandbox_mounts(context: ToolContext) -> dict[str, Path]:
    """Sandbox mount point -> host folder."""
    return {
        "/kaggle_sandbox": Path(
            context.kaggle_manager.kernel_executor.kernel_path
        ).resolve(),
        "/deliverables": Path(context.deliverables_dir).resolve(),
    }


def _to_host_path(
    path: str | Path,
    context: ToolContext,
    mode: str,
    relative_base: Path,
) -> Path:
    """
    Translate a path the agent wrote into an absolute, allowed host path.

    - /kaggle_sandbox/x or /deliverables/x -> matching host folder
    - relative x                           -> relative_base / x
    - absolute host path                   -> unchanged
    Then enforce the host filesystem read/write roots.
    """
    raw = str(path).strip().replace("\\", "/")
    target = None

    for prefix, host_root in _sandbox_mounts(context).items():
        if raw == prefix or raw.startswith(prefix + "/"):
            target = host_root / raw[len(prefix):].lstrip("/")
            break

    if target is None:
        target = Path(path)
        # "/x" on Windows has no drive, so it is not a real host path.
        if not target.is_absolute() and not raw.startswith("/"):
            target = Path(relative_base) / target

    try:
        return context.host_filesystem._resolve(target.resolve(), mode)
    except PermissionError as exc:
        raise PermissionError(f"{exc}. {SANDBOX_MOUNT_HINT}") from exc
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"File not found: {path} (host: {target})"
        ) from exc


def _resolve_output_path(
    output_path: str | Path | None,
    default: Path,
    context: ToolContext,
) -> Path:
    """Resolve a Kaggle download directory; relative -> /kaggle_sandbox."""
    if output_path is None:
        return context.host_filesystem._resolve(
            Path(default).resolve(), "write"
        )

    return _to_host_path(
        output_path,
        context,
        "write",
        relative_base=_sandbox_mounts(context)["/kaggle_sandbox"],
    )


# KAGGLE MODEL TOOLS
def _kaggle_model_result(result: Any) -> dict:
    """Convert subprocess.CompletedProcess into an LLM-friendly result."""
    return {
        "success": result.returncode == 0,
        "exit_code": result.returncode,
        "stdout": result.stdout or "",
        "stderr": result.stderr or "",
    }


def kaggle_model_init(
    context: ToolContext,
) -> dict:
    """Initialize Kaggle model metadata in the project directory."""
    try:
        result = context.kaggle_manager.model_executor.init()
        return _kaggle_model_result(result)

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def write_kaggle_model_metadata(
    title: str = None,
    description: str = None,
    owner_slug: str = None,
    slug: str = None,
    is_private: bool = None,
    context: ToolContext = None,
) -> dict:
    """
    Write or update Kaggle model metadata.

    The model directory is managed by ModelExecutor.
    Only supplied fields are updated.
    """
    try:
        metadata = {}

        if title is not None:
            metadata["title"] = title

        if description is not None:
            metadata["description"] = description

        if owner_slug is not None:
            metadata["ownerSlug"] = owner_slug

        if slug is not None:
            metadata["slug"] = slug

        if is_private is not None:
            metadata["isPrivate"] = is_private

        path = context.kaggle_manager.model_executor.write_metadata(metadata)

        return {
            "success": True,
            "metadata_path": str(path),
            "metadata": context.kaggle_manager.model_executor.read_metadata(),
        }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def kaggle_model_read_metadata(
    context: ToolContext,
) -> dict:
    """Read the current local Kaggle model metadata."""
    try:
        metadata = context.kaggle_manager.model_executor.read_metadata()

        return {
            "success": True,
            "metadata": metadata,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def kaggle_model_create(
    context: ToolContext = None,
) -> dict:
    """Create a new Kaggle model."""
    try:
        result = context.kaggle_manager.model_executor.create()
        return _kaggle_model_result(result)

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def kaggle_model_update(
    context: ToolContext = None,
) -> dict:
    """Update the existing Kaggle model metadata."""
    try:
        result = context.kaggle_manager.model_executor.update()
        return _kaggle_model_result(result)

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def kaggle_model_get(
    output_path: str = None,
    context: ToolContext = None,
) -> dict:
    """Get model details from Kaggle."""
    try:
        target = _resolve_output_path(
            output_path,
            context.kaggle_manager.kernel_executor.output_path / "models",
            context,
        )

        result = context.kaggle_manager.model_executor.get(
            output_path=target,
        )

        return {**_kaggle_model_result(result), "output_path": str(target)}

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def kaggle_model_list(
    search: str = None,
    page_size: int = 20,
    sort_by: str = None,
    context: ToolContext = None,
) -> dict:
    """List or search the Kaggle models owned by nbtailee22."""
    try:
        result = context.kaggle_manager.model_executor.list(
            search=search,
            page_size=page_size,
            sort_by=sort_by,
        )
        output = _kaggle_model_result(result)

        if output["success"] and not output["stdout"].strip():
            output["success"] = False
            output["error"] = (
                "Kaggle returned an empty response (no rows and no "
                "'No models found' message). This is not a real empty "
                "result. Retry without search or with a different "
                "page_size."
            )

        return output

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def kaggle_model_delete(
    confirm: bool = False,
    context: ToolContext = None,
) -> dict:
    """Delete the current Kaggle model. Requires confirmation."""
    try:
        if not confirm:
            return {
                "success": False,
                "error": "Model deletion requires confirm=True.",
            }

        result = context.kaggle_manager.model_executor.delete(
            confirm=confirm,
        )

        return _kaggle_model_result(result)

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


# KAGGLE DATASET TOOLS
def _kaggle_dataset_result(result: Any) -> dict:
    """Convert subprocess.CompletedProcess into an LLM-friendly result."""
    return {
        "success": result.returncode == 0,
        "exit_code": result.returncode,
        "stdout": result.stdout or "",
        "stderr": result.stderr or "",
    }


def kaggle_dataset_init(context: ToolContext) -> dict:
    """Initialize Kaggle dataset metadata in the project directory."""
    try:
        result = context.kaggle_manager.dataset_executor.init()
        return _kaggle_dataset_result(result)

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def write_kaggle_dataset_metadata(
    title: str = None,
    subtitle: str = None,
    description: str = None,
    licenses: list = None,
    keywords: list = None,
    resources: list = None,
    is_private: bool = None,
    id: str = None,
    context: ToolContext = None,
) -> dict:
    """
    Write or update Kaggle dataset metadata.

    The dataset ID is managed by DatasetExecutor.
    """

    try:
        metadata = {}

        if title is not None:
            metadata["title"] = title

        if subtitle is not None:
            metadata["subtitle"] = subtitle

        if description is not None:
            metadata["description"] = description

        if licenses is not None:
            metadata["licenses"] = licenses

        if keywords is not None:
            metadata["keywords"] = keywords

        if resources is not None:
            metadata["resources"] = resources

        if is_private is not None:
            metadata["is_private"] = bool(is_private)

        if id is not None:
            from tools.training_orchestrator.kaggle_executor import validate_ref
            metadata["id"] = validate_ref(id, "Dataset")

        path = context.kaggle_manager.dataset_executor.write_metadata(metadata)

        return {
            "success": True,
            "metadata_path": str(path),
            "metadata": context.kaggle_manager.dataset_executor.read_metadata(),
        }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def kaggle_dataset_read_metadata(
    context: ToolContext,
) -> dict:
    """Read the current local Kaggle dataset metadata."""
    try:
        metadata = context.kaggle_manager.dataset_executor.read_metadata()

        return {
            "success": True,
            "metadata": metadata,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def kaggle_dataset_create(
    public: bool = False,
    quiet: bool = False,
    context: ToolContext = None,
) -> dict:
    """Create and upload a new Kaggle dataset."""
    try:
        result = context.kaggle_manager.dataset_executor.create(
            public=public,
            quiet=quiet,
        )

        return _kaggle_dataset_result(result)

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def kaggle_dataset_version(
    message: str,
    convert_to_csv: bool = False,
    quiet: bool = False,
    context: ToolContext = None,
) -> dict:
    """Upload a new version of the current Kaggle dataset."""
    try:
        result = context.kaggle_manager.dataset_executor.version(
            message=message,
            convert_to_csv=convert_to_csv,
            quiet=quiet,
        )

        return _kaggle_dataset_result(result)

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def kaggle_dataset_status(
    context: ToolContext,
) -> dict:
    """Get the remote Kaggle dataset status."""
    try:
        result = context.kaggle_manager.dataset_executor.status()

        return _kaggle_dataset_result(result)

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def kaggle_dataset_list_files(
    context: ToolContext,
) -> dict:
    """List files belonging to the current Kaggle dataset."""
    try:
        result = context.kaggle_manager.dataset_executor.list_files()

        return _kaggle_dataset_result(result)

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def kaggle_dataset_download(
    output_path: str = None,
    force: bool = False,
    unzip: bool = True,
    quiet: bool = False,
    context: ToolContext = None,
) -> dict:
    """Download the current Kaggle dataset."""
    try:
        target = _resolve_output_path(
            output_path,
            context.kaggle_manager.kernel_executor.output_path / "datasets",
            context,
        )

        result = context.kaggle_manager.dataset_executor.download(
            output_path=target,
            force=force,
            unzip=unzip,
            quiet=quiet,
        )

        return {**_kaggle_dataset_result(result), "output_path": str(target)}

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def kaggle_dataset_delete(
    confirm: bool = False,
    context: ToolContext = None,
) -> dict:
    """Delete the current Kaggle dataset. Requires confirmation."""
    try:
        if not confirm:
            return {
                "success": False,
                "error": "Dataset deletion requires confirm=True.",
            }

        result = context.kaggle_manager.dataset_executor.delete()

        return _kaggle_dataset_result(result)

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def kaggle_list_available_dataset(context: ToolContext = None):
    try:
        result = context.kaggle_manager.dataset_executor.list_available_datasets()
        return _kaggle_dataset_result(result)
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc)
        }


# KAGGLE TOOLS
def _kaggle_result(result: Any) -> dict:
    """Convert subprocess.CompletedProcess into an LLM-friendly result."""
    return {
        "success": result.returncode == 0,
        "exit_code": result.returncode,
        "stdout": result.stdout or "",
        "stderr": result.stderr or "",
    }


def kaggle_init(context: ToolContext) -> dict:
    """Initialize Kaggle kernel metadata in the project directory."""
    try:
        result = context.kaggle_manager.kernel_executor.init()
        return _kaggle_result(result)
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def kaggle_push(
    accelerator: str = None,
    timeout: int = None,
    no_run: bool = False,
    force: bool = False,
    context: ToolContext = None,
) -> dict:
    """Push the current project to Kaggle."""
    import hashlib
    try:
        executor = context.kaggle_manager.kernel_executor
        code = _agent_run_code(context)
        pushed_text = code
        if pushed_text is None and executor.metadata_path.is_file():
            code_file = executor.kernel_path / executor.read_metadata().get("code_file", "")
            pushed_text = code_file.read_text(encoding="utf-8") if code_file.is_file() else ""
        digest = hashlib.sha256((pushed_text or "").encode("utf-8")).hexdigest()
        if not force and digest == getattr(executor, "last_push_digest", None):
            return {
                "success": False,
                "error": (
                    "train.py is unchanged since the last push, so this would "
                    "re-run the same code. Check that your edit was saved to "
                    "/kaggle_sandbox/train.py (use write_file). Pass force=true "
                    "only for a deliberate re-run."
                ),
            }
        result = executor.push(
            accelerator=accelerator,
            timeout=timeout,
            no_run=no_run,
            code_override=code,
        )
        output = _kaggle_result(result)
        if output["success"]:
            executor.last_push_digest = digest
        if code is not None:
            output["note"] = (
                "AgentRun inlined into the pushed train.py (slug and W&B "
                "project filled in); your /kaggle_sandbox/train.py is unchanged."
            )
        return output
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def kaggle_status(context: ToolContext) -> dict:
    """Get the execution status of the current Kaggle kernel."""
    try:
        executor = context.kaggle_manager.kernel_executor
        result = executor.status()
        output = _kaggle_result(result)

        if executor.last_push_no_run:
            output["note"] = (
                "The latest version was pushed with no_run=True and was "
                "never executed. Kaggle may still report RUNNING or ERROR "
                "for it; that status does not reflect a real run. Push "
                "with no_run=False to execute the kernel."
            )

        return output
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def kaggle_training_progress(
    watch_seconds: int = 20,
    context: ToolContext = None,
) -> dict:
    """
    Status plus live training progress of the current kernel, and how
    long to wait before checking again.
    """
    import time as _time
    from tools.training_orchestrator.kaggle_executor import (
        TERMINAL_STATUSES, parse_progress, parse_status,
    )

    try:
        executor = context.kaggle_manager.kernel_executor
        watch_seconds = max(5, min(int(watch_seconds or 20), 60))

        status = parse_status(executor.status().stdout)
        output: dict = {"success": True, "status": status}

        if executor.last_push_time:
            output["seconds_since_push"] = round(
                _time.time() - executor.last_push_time)

        if status in TERMINAL_STATUSES:
            output["suggested_wait_seconds"] = 0
            output["next_step"] = (
                "Run finished. Download outputs and read the log."
            )
            return output

        if status != "RUNNING":
            output["suggested_wait_seconds"] = 30
            output["next_step"] = "Kernel is queued or starting."
            return output

        progress = parse_progress(executor.logs(follow_seconds=watch_seconds))
        output["progress"] = progress
        remaining = progress.get("remaining_seconds")

        if progress.get("found") and remaining is not None:
            # Long runs: check again halfway, early ETAs include startup time.
            # Short runs: ETA plus a margin for eval, saving and session end.
            wait = remaining // 2 if remaining > 120 else remaining + 30
            output["next_step"] = (
                f"Training {progress['percent']}% done "
                f"({progress['step']}/{progress['total_steps']} steps), "
                f"about {remaining}s left."
            )
        else:
            wait = 60
            output["next_step"] = (
                "No training progress bar yet (installing packages, "
                "downloading data or model, or the script does not use "
                "tqdm). See progress.tail for the latest log lines."
            )

        output["suggested_wait_seconds"] = max(30, min(wait, 900))
        return output

    except Exception as exc:
        return {
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def kaggle_delete(context: ToolContext) -> dict:
    """Delete the current Kaggle kernel."""
    try:
        result = context.kaggle_manager.kernel_executor.delete()
        return _kaggle_result(result)
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def kaggle_list_output_files(
    page_size: int = None,
    context: ToolContext = None,
) -> dict:
    """List files generated by the current Kaggle kernel."""
    try:
        result = context.kaggle_manager.kernel_executor.list_output_files(
            page_size=page_size,
        )
        output = _kaggle_result(result)

        if output["success"] and not output["stdout"].strip():
            output["note"] = (
                "No output files found. The kernel may still be running "
                "or produced no outputs yet; check kaggle_status."
            )

        return output
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def _archive_outputs(out_dir: Path) -> str | None:
    """Move the previous version's outputs to output/archive/<time> before a new download."""
    import shutil
    import time as _time
    items = [p for p in out_dir.iterdir() if p.name != "archive"] if out_dir.is_dir() else []
    if not items:
        return None
    target = out_dir / "archive" / _time.strftime("%Y%m%d-%H%M%S")
    target.mkdir(parents=True, exist_ok=True)
    for item in items:
        shutil.move(str(item), str(target / item.name))
    return str(target)


def kaggle_download_output_files(
    force: bool = False,
    quiet: bool = False,
    regex: str = None,
    page_size: int = None,
    context: ToolContext = None,
) -> dict:
    """Download Kaggle kernel output files into the project output directory."""
    try:
        executor = context.kaggle_manager.kernel_executor
        # Full downloads replace the previous version; keep it in output/archive.
        archived = None if regex else _archive_outputs(Path(executor.output_path))
        result = executor.download_output_files(
            force=force,
            quiet=quiet,
            regex=regex,
            page_size=page_size,
        )
        output = _kaggle_result(result)
        output["output_path"] = str(executor.output_path)

        # Never keep key files a kernel may have written to its output.
        removed = [f for f in Path(executor.output_path).rglob("*.env")
                   if f.is_file()]  # pathlib's * also matches ".env"
        for f in removed:
            f.unlink()
        if removed:
            output["note"] = f"Removed {len(removed)} .env file(s) from the output."
        if archived:
            output["previous_outputs"] = archived

        # The pretty log is a convenience; its failure does not
        # make the download fail.
        if output["success"]:
            try:
                output["pretty_log"] = str(executor.beautify_log())
            except Exception as exc:
                output["log_warning"] = (
                    f"Download succeeded, but the log could not be "
                    f"beautified: {type(exc).__name__}: {exc}"
                )

        return output
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


GPU_MACHINE_SHAPE = "NvidiaTeslaT4"


def write_kaggle_metadata(
    id: str = None,
    title: str = None,
    code_file: str = None,
    language: str = None,
    kernel_type: str = None,
    enable_gpu: bool = None,
    enable_internet: bool = None,
    machine_shape: bool = None,
    dataset_sources: list = None,
    model_sources: list = None,
    competition_sources: list = None,
    kernel_sources: list = None,
    context: ToolContext = None,
) -> dict:
    """
    Partially update kernel-metadata.json.

    Only supplied fields change; omitted fields (including every
    *_sources list) keep their current values.
    """
    try:
        from tools.training_orchestrator.kaggle_executor import validate_ref

        meta = {}
        remove_keys = []

        if id is not None:
            meta["id"] = validate_ref(id, "Kernel")
        for key, value in (
            ("title", title),
            ("code_file", code_file),
            ("language", language),
            ("kernel_type", kernel_type),
        ):
            if value is not None:
                meta[key] = value

        if enable_internet is not None:
            meta["enable_internet"] = bool(enable_internet)

        # machine_shape=True requests the T4 shape and implies a GPU.
        if machine_shape is True:
            if enable_gpu is False:
                return {
                    "success": False,
                    "error": "machine_shape=True requires enable_gpu=True.",
                }
            enable_gpu = True

        if enable_gpu is not None:
            meta["enable_gpu"] = bool(enable_gpu)
            if enable_gpu and machine_shape is not False:
                meta["machine_shape"] = GPU_MACHINE_SHAPE
            else:
                # No stale GPU machine shape on a CPU kernel.
                remove_keys.append("machine_shape")
        elif machine_shape is False:
            remove_keys.append("machine_shape")

        for key, value in (
            ("dataset_sources", dataset_sources),
            ("model_sources", model_sources),
            ("competition_sources", competition_sources),
            ("kernel_sources", kernel_sources),
        ):
            if value is not None:
                meta[key] = list(value)

        executor = context.kaggle_manager.kernel_executor
        path = executor.write_metadata(
            meta_dict=meta,
            remove_keys=remove_keys,
        )

        return {
            "success": True,
            "metadata_path": str(path),
            "metadata": executor.read_metadata(),
        }

    except Exception as exc:
        return {
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


LOG_CHAR_LIMIT = 6000  # stays under the 2000-token tool-result compaction
LOG_KEY_RE = re.compile(
    r"error|exception|traceback|warning|WANDB_OFFLINE|STOPPED_BY_AGENT|"
    r"final|best|accuracy|eval",
    re.I,
)


def kaggle_get_output_log(context):
    """
    Retrieve the beautified Kaggle kernel output log.

    Requires kaggle_download_output_files to have been
    executed first.
    """
    try:
        executor = context.kaggle_manager.kernel_executor
        log_content = executor.get_output_log()
        output = {"success": True}

        if len(log_content) <= LOG_CHAR_LIMIT:
            output["log"] = log_content
            return output

        # Long logs: head, important lines, tail. Long lines are mostly tqdm frames.
        lines = [l if len(l) <= 300 else l[:150] + " ... " + l[-100:]
                 for l in log_content.splitlines()]
        head, tail = lines[:20], lines[-50:]
        middle = lines[20:-50]
        important = [l for l in middle if LOG_KEY_RE.search(l)][-30:]
        output["log"] = "\n".join(
            head
            + [f"... [{len(middle)} lines skipped; {len(important)} key lines kept] ..."]
            + important
            + ["... [end of key lines] ..."]
            + tail
        )
        output["note"] = (
            f"Log shortened ({len(log_content)} chars). Full log: "
            f"{executor.pretty_log_path()}. Use execute_bash with grep on "
            "/kaggle_sandbox/output for anything missing."
        )
        return output

    except FileNotFoundError as e:
        return {
            "success": False,
            "error": str(e),
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to retrieve Kaggle output log: {str(e)}",
        }


# W&B TOOLS
def _monitor(context: ToolContext):
    monitor = getattr(context.kaggle_manager, "wandb_monitor", None)
    if monitor is None:
        raise ValueError(
            "W&B is off. Set WANDB_API_KEY in .env (and not WANDB_ENABLED=0), then restart. "
            "Use kaggle_training_progress instead."
        )
    return monitor


def _wandb(context: ToolContext):
    """Monitor plus the kernel slug, which is the W&B group of its runs."""
    return (_monitor(context),
            context.kaggle_manager.kernel_executor.kernel_slug())


AGENT_RUN_SNIPPET = Path(__file__).resolve().parents[1] / "prompt" / "snippets" / "agent_run.py"
AGENT_RUN_IMPORT_RE = re.compile(r"^from agent_run import AgentRun[^\n]*\n?", re.M)
NO_AGENT_RUN_MARK = "# no-agent-run"


def _agent_run_code(context: ToolContext) -> str | None:
    """
    train.py with `from agent_run import AgentRun` replaced by the harness
    AgentRun (slug and project filled in). None when nothing to inline.
    Refuses hand-written W&B code while W&B is enabled.
    """
    km = context.kaggle_manager
    monitor = getattr(km, "wandb_monitor", None)
    executor = km.kernel_executor
    if not executor.metadata_path.is_file():
        return None
    code_file = executor.kernel_path / executor.read_metadata().get("code_file", "")
    if not code_file.is_file():
        return None  # validate_for_push reports it
    text = code_file.read_text(encoding="utf-8")

    if re.search(r"^\s*class AgentRun\b", text, re.M):
        raise ValueError(
            "train.py defines its own AgentRun. Delete it and use "
            "`from agent_run import AgentRun`; the harness inlines the real "
            "one at push.")
    if not AGENT_RUN_IMPORT_RE.search(text):
        if monitor is not None and NO_AGENT_RUN_MARK not in text:
            raise ValueError(
                "W&B is enabled: train.py must contain "
                "`from agent_run import AgentRun` and log through it. Do not "
                "write your own W&B code. For a kernel that does not train, "
                f"add the comment `{NO_AGENT_RUN_MARK}`.")
        return None

    snippet = AGENT_RUN_SNIPPET.read_text(encoding="utf-8")
    project = monitor.project if monitor else "agent-harness-kaggle"
    snippet = snippet.replace('"INSERT_KERNEL_SLUG_HERE"', json.dumps(executor.kernel_slug()))
    snippet = snippet.replace('"INSERT_WANDB_PROJECT_HERE"', json.dumps(project))
    return AGENT_RUN_IMPORT_RE.sub(lambda _: snippet + "\n", text, count=1)


def _tail(series: list, n: int) -> list:
    return [{"step": s, "value": round(v, 4)} for s, v in series[-n:]]


def _suggest_wait(run, evals: list, step: int) -> int:
    """Seconds until about the next eval point."""
    if run.state != "running":
        return 0
    if len(evals) < 2:
        return 60
    interval = evals[-1][0] - evals[-2][0]
    rate = step / max(run.summary.get("_runtime") or 1, 1)  # steps/second
    to_next = interval - (step - evals[-1][0])
    return int(min(max(to_next / max(rate, 1e-6) + 15, 30), 900))


def _best_point(run, mkey: str, goal: str, metric: list) -> dict:
    """Best point from the live curve; the run summary syncs less often."""
    name = mkey or "metric"
    if metric:
        pick = max if goal == "max" else min
        step, value = pick(metric, key=lambda p: p[1])
        return {name: value, "step": step}
    return {name: run.summary.get(f"best/{mkey}"),
            "step": run.summary.get("best/step")}


def wandb_training_metrics(
    last_n: int = 10,
    chance_level: float = None,
    context: ToolContext = None,
) -> dict:
    """Live metrics and fit verdict of the current kernel's latest W&B run."""
    from tools.training_orchestrator.wandb_monitor import (
        FitThresholds, diagnose_fit, diagnose_single,
    )

    try:
        monitor, slug = _wandb(context)
        run = monitor.latest_run(slug)
        if run is None:
            return {
                "success": False,
                "error": (
                    f"No W&B run for kernel '{slug}' in project "
                    f"'{monitor.project}' yet. Most likely: (1) W&B is "
                    "offline in the kernel - look for WANDB_OFFLINE in the "
                    "kaggle_training_progress tail; (2) the kernel is still "
                    "starting (no PROGRESS lines yet). Check again after "
                    "the next PROGRESS line."
                ),
            }

        last_n = max(1, min(int(last_n or 10), 50))
        th = FitThresholds(chance_level=chance_level)
        mkey, goal = monitor.primary(run)
        name = mkey or "metric"
        output = {
            "success": True,
            "run": run.name,
            "url": run.url,
            "state": run.state,
            "framework": run.config.get("framework"),
            "primary_metric": mkey,
            "goal": goal,
            "stop_requested": "agent-stop" in run.tags,
            "stop_reason": run.summary.get("stop_reason"),
        }
        if not run.config.get("framework"):
            if (run.summary.get("_runtime") or 0) > 60:
                output["note"] = (
                    "This run has no AgentRun config after a minute: train.py "
                    "is not logging through `from agent_run import AgentRun`, "
                    "so verdicts, progress and stop will not work."
                )
            else:
                output["note"] = (
                    "Run config not synced to W&B yet (a few seconds after "
                    "start); primary_metric and total_steps may be missing."
                )

        if run.config.get("fit_mode") == "single":
            short = mkey.split("/", 1)[-1] if mkey else None
            output["fit"] = diagnose_single(
                run.summary.get(f"train/{short}"),
                run.summary.get(f"eval/{short}"),
                goal, th,
            )
            output["suggested_wait_seconds"] = (
                30 if run.state == "running" else 0)
            return output

        train = monitor.series(run, "train/loss")
        evals = monitor.series(run, "eval/loss")
        metric = (monitor.series(run, mkey)
                  if mkey and mkey != "eval/loss" else [])
        step = max([s for s, _ in train + evals + metric] or [0])
        total = run.config.get("total_steps")
        progress = round(step / total, 3) if total else None

        output.update({
            "step": step,
            "total_steps": total,
            "progress": progress,
            "best": _best_point(run, mkey, goal, metric),
            "latest": {"train_loss": train[-1][1] if train else None,
                       "eval_loss": evals[-1][1] if evals else None,
                       name: metric[-1][1] if metric else None},
            "curves": {"train_loss": _tail(train, last_n),
                       "eval_loss": _tail(evals, last_n),
                       name: _tail(metric, last_n)},
            "fit": diagnose_fit(train, evals, metric, progress, th),
            "suggested_wait_seconds": _suggest_wait(run, evals, step),
        })
        return output

    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


def wandb_stop_training(reason: str, context: ToolContext = None) -> dict:
    """Tag the running W&B run so AgentRun in train.py stops training."""
    try:
        monitor, slug = _wandb(context)
        run = monitor.latest_run(slug)
        if run is None or run.state != "running":
            return {
                "success": False,
                "error": (
                    f"No running W&B run in group '{slug}' "
                    f"(state: {getattr(run, 'state', None)})."
                ),
            }
        if run.config.get("fit_mode") == "single":
            return {
                "success": False,
                "error": "A single-fit run cannot be stopped mid-fit.",
            }

        monitor.request_stop(run, reason)
        return {
            "success": True,
            "run": run.name,
            "url": run.url,
            "next_step": (
                "Training stops within about 30s and keeps the best "
                "checkpoint. Sleep 60, then call kaggle_training_progress: "
                "the log should show STOPPED_BY_AGENT (or STOP_POLL failed). "
                "If neither appears within 3 minutes, report that the stop "
                "did not reach the kernel. After COMPLETE, apply "
                "fit.suggested_edits to train.py and kaggle_push."
            ),
        }
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


def wandb_compare_runs(
    metric: str = None,
    goal: str = None,
    top_k: int = 5,
    scope: str = "project",
    context: ToolContext = None,
) -> dict:
    """Rank W&B runs by a metric and return the best with its hyperparameters."""
    try:
        monitor = _monitor(context)
        top_k = max(1, min(int(top_k or 5), 20))
        # Project scope needs no kernel, so it works before any push.
        group = _wandb(context)[1] if scope == "kernel" else None
        metric, goal, rows = monitor.leaderboard(metric, goal, top_k, group)
        if not rows:
            return {
                "success": False,
                "error": f"No runs with summary '{metric}' in scope '{scope}'.",
            }
        return {
            "success": True,
            "metric": metric,
            "goal": goal,
            "best": rows[0],
            "leaderboard": rows,
        }
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


def wandb_sync_kaggle_run(context: ToolContext = None) -> dict:
    """Upload offline W&B runs found in the downloaded kernel output."""
    try:
        monitor, _ = _wandb(context)
        out_dir = Path(context.kaggle_manager.kernel_executor.output_path)
        run_dirs = sorted(p for p in out_dir.rglob("offline-run-*")
                          if p.is_dir())
        if not run_dirs:
            return {
                "success": False,
                "error": (
                    "No offline-run-* folder in the kernel output. Call "
                    "kaggle_download_output_files first."
                ),
            }

        command = [sys.executable, "-m", "wandb", "sync",
                   "--entity", monitor.entity, "--project", monitor.project]
        proc = subprocess.run(
            command + [str(d) for d in run_dirs],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300,
        )
        return {
            "success": proc.returncode == 0,
            "synced": [d.name for d in run_dirs],
            "output": proc.stdout[-1500:],
            "error": proc.stderr[-1500:] if proc.returncode else None,
        }
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


def wandb_list_projects(context: ToolContext = None) -> dict:
    """List the projects of the fixed W&B entity."""
    try:
        monitor = _monitor(context)
        return {
            "success": True,
            "entity": monitor.entity,
            "active_project": monitor.project,
            "projects": monitor.list_projects(),
        }
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


def wandb_create_project(name: str, context: ToolContext = None) -> dict:
    """Create a W&B project and make it the active one."""
    try:
        monitor = _monitor(context)
        if name == monitor.project:
            # Empty projects are not listed yet, so agents may think it is missing.
            return {"success": True, "active_project": name,
                    "note": "This is already the active project; nothing to create."}
        if monitor.project_exists(name):
            return {
                "success": False,
                "error": (
                    f"Project '{name}' already exists. Use "
                    "wandb_use_project to switch to it."
                ),
            }
        monitor.create_project(name)
        monitor.project = name
        return {
            "success": True,
            "active_project": name,
            "next_step": f'Set WANDB_PROJECT = "{name}" in train.py.',
        }
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


def wandb_use_project(name: str, context: ToolContext = None) -> dict:
    """Switch the active W&B project used by the other wandb_* tools."""
    try:
        monitor = _monitor(context)
        if not monitor.project_exists(name):
            return {
                "success": False,
                "error": (
                    f"Project '{name}' not found for entity "
                    f"'{monitor.entity}'. See wandb_list_projects or use "
                    "wandb_create_project."
                ),
            }
        monitor.project = name
        return {
            "success": True,
            "active_project": name,
            "next_step": f'Set WANDB_PROJECT = "{name}" in train.py.',
        }
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


def wandb_list_runs(
    project: str = None,
    group: str = None,
    state: str = None,
    limit: int = 20,
    context: ToolContext = None,
) -> dict:
    """List runs of a project (default: active), newest first."""
    try:
        monitor = _monitor(context)
        limit = max(1, min(int(limit or 20), 100))
        runs = monitor.list_runs(project, group, state, limit)
        return {
            "success": True,
            "project": project or monitor.project,
            "count": len(runs),
            "runs": runs,
        }
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


def wandb_create_run(
    name: str,
    project: str = None,
    config: dict = None,
    metrics: dict = None,
    group: str = None,
    tags: list = None,
    notes: str = None,
    context: ToolContext = None,
) -> dict:
    """Create a finished run from the host to record results or notes."""
    if not metrics:
        return {
            "success": False,
            "error": "metrics is required, e.g. {\"eval/accuracy\": 0.1}.",
        }
    try:
        monitor = _monitor(context)
        run = monitor.create_run(name, project, config, metrics,
                                 group, tags, notes)
        return {"success": True, **run}
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


# DOCKER TOOLS

def execute_python(code: str, timeout: int, context: ToolContext):
    return context.sandbox.execute_python(
        run_id=context.run_id,
        code=code,
        timeout=timeout,
    )


def execute_bash(command: str, timeout: int, context: ToolContext):
    return context.sandbox.execute_bash(
        run_id=context.run_id,
        command=command,
        timeout=timeout,
    )


def bash(command: str) -> str:
    """Execute a shell command and return its output."""
    try:
        result = subprocess.run(command, shell=True,
                                capture_output=True, text=True, timeout=100)
    except Exception as err:
        return str(err)
    return result.stdout + result.stderr


def read_file(path: str, context: ToolContext = None) -> str:
    """
    Read and return the contents of a file.

    Accepts sandbox paths (/deliverables/..., /kaggle_sandbox/...),
    host paths, or relative paths. A relative path is looked up in
    /deliverables first, then in the project root.
    """
    if context is None:
        target = Path(path)
    else:
        deliverables = Path(context.deliverables_dir).resolve()
        candidate = deliverables / path
        base = (
            deliverables
            if not Path(path).is_absolute() and candidate.exists()
            else PROJECT_ROOT
        )
        target = _to_host_path(path, context, "read", relative_base=base)

    if target.name == ".env" or target.name.startswith(".env."):
        return "Error: reading .env files is not allowed."

    if not target.is_file():
        return f"{path} is not a file (host: {target})"

    try:
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return f"Error reading file '{path}': {exc}"


def write_file(
    path: str,
    operation: str = "write",
    content: str = "",
    old_text: str = "",
    new_text: str = "",
    replace_many: bool = False,
    allow_empty: bool = False,
    context: ToolContext = None
) -> str:
    """Create, overwrite, append to, or partially edit a project file."""

    if operation not in {"write", "replace", "append"}:
        return (
            "Error: operation must be 'write', "
            "'replace', or 'append'."
        )

    # Guard against a whole-file overwrite when an edit was meant.
    if operation != "replace" and (old_text or new_text):
        return (
            "Error: old_text/new_text are only used with operation='replace'. "
            "Nothing was written."
        )
    if operation in {"write", "append"} and not content and not allow_empty:
        return (
            "Error: content is missing or empty, so nothing was written. Send "
            "the text in `content`. For a long file, write the first part with "
            "operation='write' and add the rest with operation='append'. To "
            "create an empty file on purpose, pass allow_empty=true."
        )
    if operation == "replace" and content and not new_text:
        return (
            "Error: for operation='replace' put the new text in new_text, "
            "not content. Nothing was written."
        )

    # Translate sandbox/relative paths and enforce the write roots.
    # A relative path is relative to /deliverables (sandbox working dir).
    target = _to_host_path(
        path,
        context,
        "write",
        relative_base=Path(context.deliverables_dir).resolve(),
    )

    if not target.is_relative_to(PROJECT_ROOT):
        return "Error: path is outside the project directory."

    if operation == "replace" and not old_text:
        return "Error: old_text cannot be empty."

    if operation == "write":
        # Create parent directories if necessary.
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} characters to {path}."

    if not target.is_file():
        return f"Error: file does not exist: {path}"

    # Read the existing file for append and replace operations.
    existing = target.read_text(encoding="utf-8")

    if operation == "append":
        with target.open("a", encoding="utf-8", newline="") as file:
            file.write(content)
        return f"Successfully appended {len(content)} characters to {path}."

    # operation == "replace"
    matches = existing.count(old_text)

    if matches == 0:
        return "Error: old_text was not found. File unchanged."

    if matches > 1 and not replace_many:
        return (
            f"Error: old_text matched {matches} times. "
            "Provide a more specific section. File unchanged."
        )

    # Replace one occurrence by default, or all if requested.
    count = -1 if replace_many else 1
    updated = existing.replace(old_text, new_text, count)

    target.write_text(updated, encoding="utf-8", newline="")

    replaced = matches if replace_many else 1
    return f"Successfully replaced {replaced} occurrence(s) in {path}."


def write_and_run_temp_file(
    filename: str,
    content: str,
):
    relative_path = Path(filename)

    if relative_path.is_absolute():
        return "Error: Absolute is NOT allowed"

    try:
        with TemporaryDirectory(prefix="agent_") as temp_dir:
            workspace = Path(temp_dir).resolve()
            target_path = (workspace / relative_path).resolve()

            if not target_path.is_relative_to(workspace):
                return "Error: Invalid file path."

            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(target_path)],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=200,
            )

            return (
                f"Exit code: {result.returncode}\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}"
            )

    except subprocess.TimeoutExpired:
        return "Error: Execution Time out after 200s"
