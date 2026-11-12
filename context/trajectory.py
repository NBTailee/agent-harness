
MAX_LIMIT = 10000


def truncate(text: str, limit: int = MAX_LIMIT) -> str:
    text = str(text)

    if len(text) <= limit:
        return text

    return text[:limit - 3] + "..."


def _construct_trajectory(output: list[dict], include_all: bool = True) -> str:
    trajectory = ""

    # System prompt and user task
    if include_all and len(output) >= 2:
        trajectory += (
            f"[SYSTEM]\n{truncate(output[0].get('content', ''))}"
            f"\n[TASK]\n{truncate(output[1].get('content', ''))}"
        )

    for msg in output:

        if msg["role"] == "assistant":

            # Tool calls
            for call in msg.get("tool_calls", []):
                content = (
                    f"\n[ACTION]"
                    f"\ntool_call_id: {call['id']}"
                    f"\ntool_name: {call['function']['name']}"
                    f"\narguments: {truncate(call['function']['arguments'])}"
                )
                trajectory += content

            # Reasoning
            if msg.get("reasoning"):
                trajectory += (
                    f"\n[THINKING] {truncate(msg['reasoning'])}"
                )

            # Assistant response
            if msg.get("content"):
                trajectory += (
                    f"\n[ASSISTANT] {truncate(msg['content'])}"
                )

        elif msg["role"] == "tool":
            content = (
                f"\n[OBSERVATION]"
                f"\ntool_call_id: {msg['tool_call_id']}"
                f"\ncontent: {truncate(msg['content'])}"
            )
            trajectory += content

    return trajectory
