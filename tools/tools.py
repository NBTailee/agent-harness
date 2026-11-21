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
    context: ToolContext = None,
) -> dict:
    """Push the current project to Kaggle."""
    try:
        result = context.kaggle_manager.kernel_executor.push(
            accelerator=accelerator,
            timeout=timeout,
            no_run=no_run,
        )
        return _kaggle_result(result)
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
            # Training ETA plus a margin for evaluation, saving and
            # Kaggle finishing the session; capped so the agent rechecks.
            wait = remaining + 60
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
        result = executor.download_output_files(
            force=force,
            quiet=quiet,
            regex=regex,
            page_size=page_size,
        )
        output = _kaggle_result(result)
        output["output_path"] = str(executor.output_path)

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


def kaggle_get_output_log(context):
    """
    Retrieve the beautified Kaggle kernel output log.

    Requires kaggle_download_output_files to have been
    executed first.
    """
    try:
        log_content = context.kaggle_manager.kernel_executor.get_output_log()

        return {
            "success": True,
            "log": log_content,
        }

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
    context: ToolContext = None
) -> str:
    """Create, overwrite, append to, or partially edit a project file."""

    if operation not in {"write", "replace", "append"}:
        return (
            "Error: operation must be 'write', "
            "'replace', or 'append'."
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
