
TODO_STATUS = {
    "done": "[V]",
    "pending": "[]",
    "in_progress": "[~]",
}

TODOS = []


def write_todos(todos: list[dict[str, str]]) -> str:
    """Replace the whole todo list. At most one task may be in_progress."""

    if not isinstance(todos, list):
        return "Error: todos must be a list."

    valid_statuses = set(TODO_STATUS)

    for i, task in enumerate(todos):
        if not isinstance(task, dict):
            return f"Error: task {i} must be an object."

        if not isinstance(task.get("content"), str) or not task["content"].strip():
            return f"Error: task {i} must have non-empty string content."

        if task.get("status") not in valid_statuses:
            return (
                f"Error: task {i} has invalid status. "
                f"Allowed statuses: {', '.join(valid_statuses)}."
            )

    active = [t for t in todos if t["status"] == "in_progress"]

    if len(active) > 1:
        return (
            f"Error: {len(active)} tasks are in_progress. "
            "At most one task may be in_progress."
        )

    # Replace the list only after validation succeeds.
    TODOS[:] = [task.copy() for task in todos]

    return todos_prompt() or "Todo list CLEARED"


def todos_prompt() -> str:
    return "\n".join(
        f"{TODO_STATUS[task['status']]} {task['content']}"
        for task in TODOS
    )
