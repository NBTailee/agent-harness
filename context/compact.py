import tiktoken
import json
import os
from typing import Any
from openai import OpenAI
from dotenv import load_dotenv
from context.trajectory import _construct_trajectory
from prompt.registry import PromptRegistry
from prompt.render import render_prompt

load_dotenv()

prompt_registry = PromptRegistry(
    template_dir=r"C:\Users\leduc\OneDrive\Desktop\NLP\agent-harness\prompt\templates")


client = OpenAI(
    base_url=os.environ.get("BASE_URL"),
    api_key=os.environ.get("OPENROUTER_API_KEY"),
)

MODEL = "deepseek/deepseek-v4.1-flash-1017"

encoder = tiktoken.get_encoding("cl100k_base")


def estimate_tokens(content: Any) -> int:
    text = (
        content
        if isinstance(content, str)
        else json.dumps(content, ensure_ascii=False, default=str)
    )
    return len(encoder.encode(text))


def serialize_tool_result(result: Any) -> str:
    if isinstance(result, str):
        return result

    return json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
        default=str
    )


def compact_tool(
    current_task: str,
    tool_name: str,
    tool_arguments: Any,
    tool_result: str,
):
    instruction = prompt_registry.get("compact_tool")

    instruction = render_prompt(instruction, {
        "current_task": current_task,
        "tool_name": tool_name,
        "tool_arguments": json.dumps(
            tool_arguments,
            ensure_ascii=False,
            default=str
        ),
        "tool_result": tool_result,
        "max_output_tokens": 1500
    })

    response = client.responses.create(
        model=MODEL,
        input=instruction
    )

    return response.output_text


def process_tool_result(
    current_task: str,
    tool_name: str,
    tool_arguments: Any,
    tool_result: Any,
    max_tool_tokens: int = 2000,
    compacted_tokens: int = 1000,
) -> str:

    raw_result = serialize_tool_result(tool_result)
    token_count = estimate_tokens(raw_result)

    print(f"[Tool Middleware] {tool_name}: {token_count} tokens")

    # Keep original result.
    if token_count <= max_tool_tokens:
        print("[Tool Middleware] KEEP original result")
        return raw_result

    # Compact oversized result.
    print("[Tool Middleware] COMPACT result")

    try:
        compacted_result = compact_tool(
            current_task=current_task,
            tool_name=tool_name,
            tool_arguments=tool_arguments,
            tool_result=raw_result
        )

        compacted_count = estimate_tokens(compacted_result)

        print(
            f"[Tool Middleware] Compacted: "
            f"{compacted_count} tokens"
        )

        if compacted_count > compacted_tokens:
            raise ValueError(
                f"Compacted output exceeds limit: "
                f"{compacted_count} > {compacted_tokens}"
            )

        return compacted_result

    except Exception as e:
        print(f"[Tool Middleware] Compaction failed: {e}")

        return (
            "[WARNING: Tool result exceeded the token limit. "
            "Compaction failed. Original result follows.]\n\n"
            + raw_result
        )


def compact(messages: list[dict]) -> str:
    text = _construct_trajectory(messages)

    instruction = prompt_registry.get("compact")

    summary = client.responses.create(
        model=MODEL,
        instructions=instruction,
        input=text
    )

    return summary.output_text


def prune_messages(
    full_context: list[dict],
    start_idx: int,
    end_idx: int,
    summary: str,
) -> list[dict]:

    summary_message = {
        "role": "assistant",
        "content": (
            f"<compacted_context>\n"
            f"{summary}\n"
            f"</compacted_context>"
        ),
    }

    return (
        full_context[:start_idx]
        + [summary_message]
        + full_context[end_idx:]
    )


def _get_prune_idx(
    full_context: list[dict],
    n_messages: int = 5,
    protected_messages: int = 2,
) -> tuple[int, int]:
    """
    Find a safe message range to compact.

    Returns:
        (start_idx, end_idx)

    The end index is exclusive, following Python slicing conventions.

    Guarantees:
        - Preserves the initial protected messages.
        - Never splits assistant tool calls from their tool results.
        - Preserves at least n_messages recent messages.
        - Preserves incomplete tool-call groups at the end.
        - Raises ValueError if no safe range can be pruned.
    """

    if not isinstance(full_context, list):
        raise TypeError("full_context must be a list.")

    if n_messages < 1:
        raise ValueError("n_messages must be at least 1.")

    if protected_messages < 0:
        raise ValueError("protected_messages cannot be negative.")

    context_len = len(full_context)

    if context_len <= protected_messages + n_messages:
        raise ValueError("Not enough messages to compact.")

    # Each group represents an atomic conversation unit:
    # (start_idx, end_idx), where end_idx is exclusive.
    groups = []

    i = protected_messages

    while i < context_len:
        message = full_context[i]

        if not isinstance(message, dict):
            raise TypeError(f"Invalid message at index {i}.")

        role = message.get("role")

        # Assistant message containing tool calls.
        if role == "assistant" and message.get("tool_calls"):
            tool_calls = message["tool_calls"]

            expected_ids = set()

            for call in tool_calls:
                call_id = call.get("id")

                if not call_id:
                    raise ValueError(
                        f"Missing tool call ID at message index {i}."
                    )

                if call_id in expected_ids:
                    raise ValueError(
                        f"Duplicate tool call ID: {call_id}"
                    )

                expected_ids.add(call_id)

            group_start = i
            received_ids = set()

            i += 1

            # Consume all corresponding tool results.
            while i < context_len:
                next_message = full_context[i]

                if next_message.get("role") != "tool":
                    break

                tool_call_id = next_message.get("tool_call_id")

                if tool_call_id not in expected_ids:
                    raise ValueError(
                        f"Unexpected tool_call_id at index {i}: "
                        f"{tool_call_id}"
                    )

                if tool_call_id in received_ids:
                    raise ValueError(
                        f"Duplicate tool result: {tool_call_id}"
                    )

                received_ids.add(tool_call_id)
                i += 1

            # A missing tool result is allowed only at the end
            # of the conversation. Keep this incomplete group.
            if received_ids != expected_ids:
                if i != context_len:
                    missing = expected_ids - received_ids

                    raise ValueError(
                        "Incomplete tool interaction before the end "
                        f"of history. Missing results: {missing}"
                    )

            groups.append((group_start, i))
            continue

        # A tool result without its preceding assistant tool call
        # indicates malformed conversation history.
        if role == "tool":
            raise ValueError(
                f"Orphan tool result at message index {i}."
            )

        # Ordinary user or assistant message.
        groups.append((i, i + 1))
        i += 1

    # Keep at least n_messages recent messages.
    target_cutoff = context_len - n_messages

    # Move cutoff backward if it falls inside an atomic group.
    safe_cutoff = target_cutoff

    for group_start, group_end in groups:
        if group_start < target_cutoff < group_end:
            safe_cutoff = group_start
            break

    # Ensure we have something meaningful to compact.
    if safe_cutoff <= protected_messages:
        raise ValueError(
            "No complete conversation groups available for pruning."
        )

    start_idx = protected_messages
    end_idx = safe_cutoff

    i = 0
    for msg in full_context:
        if (
            msg.get("role") == "assistant"
            and "<compacted_context>" in (msg.get("content") or "")
        ):
            return i+1, end_idx
        i += 1

    return start_idx, end_idx
