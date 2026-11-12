import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
from tools.sandbox.model import ToolContext


PROJECT_ROOT = Path.cwd().resolve()


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


def read_file(path: Path) -> str:
    """
    Read and return the contents of a file.

    Args:
        path: Path to the file to read.
    """
    path = Path(path)

    if not path.is_file():
        return f"{path} is not a file"

    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return f"Error reading file '{path}': {exc}"


def write_file(
    path: str,
    operation: str,
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

    # Resolve the path and prevent edits outside the project.
    target = (PROJECT_ROOT / path).resolve()

    # Control the agent to only can write inside the allow places
    target = context.host_filesystem._resolve(target, "write")

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
