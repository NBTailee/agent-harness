import json
import re
import time
from pathlib import Path

from tools.agents.agent_registry import get_agent

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "prompt" / "templates"


def _child_tools(config) -> list:
    # Imported here: tools.registry imports this module.
    from tools.registry import TOOL_SCHEMAS

    tools = [t for t in TOOL_SCHEMAS
             if t["function"]["name"] != "delegate_task"]  # no nested agents
    if config.allowed_tools is not None:
        tools = [t for t in tools
                 if t["function"]["name"] in config.allowed_tools]
    return tools


def _system_prompt(config, tools: list, context) -> str:
    """Agent role (prompt/templates/<name>.md) on top of the main agent prompt."""
    from prompt.registry import PromptRegistry
    from prompt.render import render_prompt
    from tools.skills import skills_prompt

    registry = PromptRegistry(template_dir=str(TEMPLATE_DIR))
    role = config.system_prompt or registry.get(config.name) or (
        f"# Sub-agent: {config.name}\n\n{config.description}\n")

    monitor = getattr(context.kaggle_manager, "wandb_monitor", None)
    values = {
        "tools": "\n".join(f"- {t['function']['name']}" for t in tools),
        "skills": skills_prompt(),
        "deliverables_dir": str(context.deliverables_dir),
        "kaggle_sandbox_dir": str(context.kaggle_manager.kernel_executor.kernel_path),
        "wandb_status": "enabled" if monitor else "disabled",
        "wandb_project": monitor.project if monitor else "",
    }
    # Drop the main agent's "delegate every experiment" block.
    base = re.sub(r"<!-- main-agent-only -->.*?<!-- /main-agent-only -->\n?",
                  "", registry.get("agent"), flags=re.S)
    base = render_prompt(base, values)
    role = render_prompt(role, values)
    return (
        f"{role}\n\nYou are a sub-agent. Finish the task you were given and "
        "end with a clear final answer: it is the only thing returned to the "
        f"main agent.\n\n---\n\n{base}"
    )


def _save_transcript(name: str, messages: list, context) -> str | None:
    try:
        folder = Path(context.deliverables_dir).parent / "history"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"subagent-{name}-{time.strftime('%Y%m%d-%H%M%S')}.json"
        path.write_text(json.dumps(messages, indent=2, ensure_ascii=False,
                                   default=str), encoding="utf-8")
        return str(path)
    except OSError:
        return None


def run_subagent(agent_name: str, task: str, context=None) -> str:
    from harness import _run_one
    from tools.todos import TODOS

    config = get_agent(agent_name)
    tools = _child_tools(config)

    print(f"\n[SUBAGENT STARTED] {config.name}")
    print(f"[TASK] {task}")

    # The todo list is global; keep the parent's plan intact.
    parent_todos = [t.copy() for t in TODOS]
    TODOS.clear()
    full = []  # every message, even after context compaction
    try:
        messages = _run_one(
            MAX_TURNS=config.max_turns,
            system_prompt=_system_prompt(config, tools, context),
            task=task,
            context=context,
            tool_schemas=tools,
            transcript=full,
        )
    finally:
        TODOS[:] = parent_todos

    transcript = _save_transcript(config.name, full or messages, context)
    print(f"[SUBAGENT FINISHED] {config.name}")

    for message in reversed(messages):
        if (message.get("role") == "assistant" and message.get("content")
                and not message.get("tool_calls")):
            answer = message["content"]
            break
    else:
        answer = (f"Sub-agent stopped after {config.max_turns} turns without "
                  "a final answer.")

    if transcript:
        answer += f"\n\n[full sub-agent transcript: {transcript}]"
    return answer
