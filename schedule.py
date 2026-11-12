import re
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
import os
from harness import _run_one
import json
from prompt.registry import PromptRegistry
from prompt.render import render_prompt
from context.trajectory import _construct_trajectory
from tools.sandbox.model import ToolContext
from tools.sandbox.manager import SandboxManager
from tools.host.file_system import HostFilesystem


def get_current_time():
    current_datetime = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    return current_datetime.replace(" ", "_").replace("/", "-").replace(":", "-")


def validate_tag(tag: str) -> None:
    """Check a tag's shape: it becomes a path segment and must not spell a seed segment."""
    if not tag:
        return
    if not re.fullmatch(r"[A-Za-z0-9_.][A-Za-z0-9_.\-]*", tag):
        raise ValueError(
            f"tag {tag!r} must be [A-Za-z0-9_.-] with no leading '-' and "
            f"no '/': it becomes a path segment and a run-id segment"
        )
    if re.match(r"s\d+(-|$)", tag):
        raise ValueError(
            f"tag {tag!r} spells a seed segment; pass --seed instead so "
            f"seeded and tagged namespaces can never collide"
        )


def ns(
    task_id: str, *, seed: int | None = None, tag: str = ""
) -> str:

    validate_tag(tag)
    out = f"{task_id}"
    if seed is not None:
        out += f"-s{int(seed)}"
    if tag:
        out += f"-{tag}"
    return out


@dataclass
class NameSpace:

    task_id: str
    seed: int
    tag: str

    def __str__(self) -> str:
        return ns(self.task_id, seed=self.seed, tag=self.tag)

    def task_dir(self, root: Path):
        return Path(root) / "runs" / self.run_id() / self.task_id

    def run_id(self):
        current = get_current_time()
        return f"{self.task_id}-{current}"


def _write_file(path: Path, content: str):
    path = Path(path)
    path.write_text(content, encoding="utf-8")


def run_task(
    MAX_TURNS: int,
    prompt_registry: PromptRegistry,
    prompt_name: str,
    render_dict: dict,
    task: str,
    root: Path,
    name_space: NameSpace,
    resume: Path = None
):
    if not (Path(root) / "runs").is_dir():
        os.mkdir(Path(root) / "runs")
        print(f"[CREATE] {Path(root) / "runs"} folder")

    task_dir = name_space.task_dir(root)
    task_dir.mkdir(parents=True, exist_ok=True)
    print(f"[CREATE] {task_dir} folder")

    # write task.md file that contain the information of task
    _write_file(
        task_dir / "task.md",
        task
    )

    deliverables_dir = task_dir / "deliverables"
    deliverables_dir.mkdir(parents=True, exist_ok=True)

    # render prompt
    render_dict["deliverables_dir"] = str(deliverables_dir)

    host_system = HostFilesystem(
        allowed_roots_read=[root], allowed_roots_write=[deliverables_dir])
    sandbox_manager = SandboxManager()

    tool_context = ToolContext(
        run_id=str(name_space),
        deliverables_dir=deliverables_dir,
        sandbox=sandbox_manager,
        host_filesystem=host_system

    )

    # start Docker container
    tool_context.sandbox.ensure(
        run_id=tool_context.run_id,
        workspace=deliverables_dir
    )

    system_prompt = prompt_registry.get(prompt_name)
    system_prompt = render_prompt(system_prompt, render_dict)

    output = _run_one(MAX_TURNS, system_prompt, task,
                      resume, context=tool_context)

    # Destroy Docker container
    tool_context.sandbox.destroy(run_id=tool_context.run_id)

    history_dir = task_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    with open(history_dir / "history.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4, ensure_ascii=False)

    trajectory = _construct_trajectory(output)

    # write trajectory
    rollout_dir = task_dir / "rollouts"
    rollout_dir.mkdir(parents=True, exist_ok=True)

    _write_file(
        rollout_dir / f"{name_space.task_id}.md",
        trajectory
    )
