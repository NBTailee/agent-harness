import os
import json
from openai import OpenAI, APIError
from prompt.registry import PromptRegistry
from prompt.render import render_prompt
from dotenv import load_dotenv
from tools.executor import dispatch_tool
from tools.registry import TOOL_SCHEMAS, list_tools
from tools.skills import skills_prompt
from context.context import reminder
from pathlib import Path
from context.compact import estimate_tokens, process_tool_result, _get_prune_idx, prune_messages, compact
from tools.sandbox.model import ToolContext

CONTEXT_LIMIT = 1048576
COMPACTION_THRESHOLD = 1
TOOL_CONTEXT_LIMIT = 4000

load_dotenv()

client = OpenAI(
    base_url=os.environ.get("BASE_URL"),
    api_key=os.environ.get("OPENROUTER_API_KEY"),
)

MODEL = "deepseek/deepseek-v4.1-flash-1017"

prompt_registry = PromptRegistry(
    template_dir=r"C:\Users\leduc\OneDrive\Desktop\NLP\agent-harness\prompt\templates")
instruction = prompt_registry.get("agent")
instruction = render_prompt(
    instruction, {"tools": list_tools(), "skills": skills_prompt()})


# print(instruction)


# print("ASK AI Agent: ")
# user_input = input()


def print_section(title: str, content: str = "") -> None:
    """Print a formatted terminal section."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)
    if content:
        print(content)


MAX_TURNS = 50


MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", 32000))
MAX_REPEATS = 5  # identical failing calls before the harness stops executing them
NO_COMPACT_TOOLS = {"read_file", "delegate_task"}
STUCK_NOTE = (
    "You keep sending the same failing tool call. Stop and change approach. "
    "If a write_file call arrives without content, the text is too long for "
    "one call: write the file in sections of at most ~3000 characters, the "
    "first with operation='write' and every later one with operation='append'."
)
CUT_OFF_NOTE = (
    "Your last reply hit the output limit and was cut off, so tool arguments "
    "may be missing or incomplete. Use shorter replies: write long files in "
    "parts (operation='write' for the first part, then 'append')."
)


def _create(request_messages, tool_schemas):
    """Model call with a raised output limit; retry without it if refused."""
    try:
        return client.chat.completions.create(
            model=MODEL, messages=request_messages, tools=tool_schemas,
            max_tokens=MAX_OUTPUT_TOKENS)
    except APIError as exc:
        if "max_tokens" not in str(exc) and "max tokens" not in str(exc).lower():
            raise RuntimeError(f"Model API error: {exc}") from exc
    try:
        return client.chat.completions.create(
            model=MODEL, messages=request_messages, tools=tool_schemas)
    except APIError as exc:
        raise RuntimeError(f"Model API error: {exc}") from exc


def _pretty_args(args: str) -> str:
    try:
        return json.dumps(json.loads(args), indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return f"(invalid JSON) {args}"  # e.g. cut off at the output limit


def _looks_failed(result) -> bool:
    text = str(result)[:300]
    return (text.startswith(("Error", "Tool execution error", "Not executed"))
            or "'success': False" in text or '"success": false' in text)


def _run_one(MAX_TURNS: int = 50, system_prompt: str = None, task: str = None, resume: Path = None, context: ToolContext = None, tool_schemas: list = None, transcript: list = None):

    # Sub-agents pass a reduced tool list; only those tools may run.
    tool_schemas = tool_schemas or TOOL_SCHEMAS
    allowed = {t["function"]["name"] for t in tool_schemas}

    if not resume:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task}
        ]
    else:
        with open(resume, "r", encoding="utf-8") as f:
            messages = json.load(f)

    # `messages` gets compacted; `transcript` keeps every message for review.
    if transcript is not None:
        transcript.extend(messages)

    def record(msg):
        messages.append(msg)
        if transcript is not None:
            transcript.append(msg)

    last_failed, repeats = None, 0

    for turn in range(MAX_TURNS):
        print_section(f"TURN {turn + 1}/{MAX_TURNS}")

        if estimate_tokens(messages)*10 >= CONTEXT_LIMIT * COMPACTION_THRESHOLD:
            print("CONTEXT LENGTH EXIST NEED COMPACTION")
            start, end = _get_prune_idx(messages, 5)
            summary = compact(messages[start: end])
            messages = prune_messages(messages, start, end, summary)

        request_messages = [
            *messages,
            reminder(),
        ]

        response = _create(request_messages, tool_schemas)
        message = response.choices[0].message
        cut_off = response.choices[0].finish_reason == "length"

        record(message.model_dump(exclude_none=True))

        if message.content:
            print_section("ASSISTANT SUMMARY", message.content)

        if not message.tool_calls:
            if cut_off:
                # A truncated final answer is not an answer; ask for the rest.
                record({"role": "user", "content": CUT_OFF_NOTE +
                       " Continue where you stopped."})
                continue
            print_section("FINAL ANSWER",
                          message.content or "(No answer returned)")
            break

        stuck = False
        for tool_call in message.tool_calls:
            name = tool_call.function.name
            args = tool_call.function.arguments

            print_section(f"TOOL CALL: {name}", _pretty_args(args))

            signature = (name, args)
            repeats = repeats + 1 if signature == last_failed else 0
            if repeats >= MAX_REPEATS:
                stuck = True
                result = (
                    f"Not executed: this exact {name} call already failed "
                    f"{repeats} times in a row. Change the arguments or the "
                    "approach (for long text, send it in smaller parts)."
                )
            elif name in allowed:
                result = dispatch_tool(name, args, context)
            else:
                result = f"Tool '{name}' is not available to this agent."

            if _looks_failed(result):
                last_failed = signature
                if repeats >= 2:
                    result = (f"{result}\n\n[Warning: same failing call {repeats + 1} "
                              "times in a row. Do not repeat it unchanged.]")
            else:
                last_failed, repeats = None, 0
            if cut_off:
                result = f"{result}\n\n[{CUT_OFF_NOTE}]"

            # read_file must return the real text; delegate answers are already summaries.
            if name not in NO_COMPACT_TOOLS and estimate_tokens(result) > TOOL_CONTEXT_LIMIT:
                print(f"[TOOL RESULT LIMIT EXCEED] Compact Tool Result....")

                result = process_tool_result(
                    current_task=task or "",
                    tool_name=name,
                    tool_arguments=_pretty_args(args),
                    tool_result=str(result),
                )

                result = "<compact_tool_result>\n" + \
                    str(result) + "\n</compact_tool_result>"

            print_section(f"TOOL RESULT: {name}", str(result))

            record({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(result),
            })

        if stuck:
            # Tool results alone did not break the loop; say it as the user.
            record({"role": "user", "content": STUCK_NOTE})

    else:
        print_section(
            "TURN LIMIT REACHED",
            f"The agent stopped after {MAX_TURNS} turns without a final response.",
        )
        return messages

    return messages


# messages = _run_one(MAX_TURNS, instruction, user_input)
# with open(rf"C:\Users\leduc\OneDrive\Desktop\NLP\agent-harness\test.json", "w", encoding="utf-8") as file:
#     json.dump(messages, file, indent=4, ensure_ascii=False)

# completion_details = response.usage.completion_tokens_details
# prompt_details = response.usage.prompt_tokens_details

# usage = {
#     "prompt_tokens": prompt_details,
#     "completion_tokens": completion_details,
#     "reasoning_tokens": getattr(completion_details, "reasoning_tokens", None),
#     "cached_tokens": getattr(prompt_details, "cached_tokens", None),
# }

# print("AGENT OUTPUT: ")
# print(response.choices[0].message)

# create a login page within only a html file called "test.html". decompose into smaller tasks first then implement
