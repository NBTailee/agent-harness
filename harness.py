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
TOOL_CONTEXT_LIMIT = 2000

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


def _run_one(MAX_TURNS: int = 50, system_prompt: str = None, task: str = None, resume: Path = None, context: ToolContext = None):

    if not resume:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task}
        ]
    else:
        with open(resume, "r", encoding="utf-8") as f:
            messages = json.load(f)

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

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=request_messages,
                tools=TOOL_SCHEMAS,
            )
        except APIError as exc:
            raise RuntimeError(f"Model API error: {exc}") from exc

        message = response.choices[0].message

        messages.append(message.model_dump(exclude_none=True))

        if message.content:
            print_section("ASSISTANT SUMMARY", message.content)

        if not message.tool_calls:
            print_section("FINAL ANSWER",
                          message.content or "(No answer returned)")
            break

        for tool_call in message.tool_calls:
            name = tool_call.function.name
            args = tool_call.function.arguments

            print_section(
                f"TOOL CALL: {name}",
                json.dumps(
                    json.loads(args),
                    indent=2,
                    ensure_ascii=False,
                ),
            )

            result = dispatch_tool(name, args, context)

            if estimate_tokens(result) > TOOL_CONTEXT_LIMIT:
                print(f"[TOOL RESULT LIMIT EXCEED] Compact Tool Result....")

                result = process_tool_result(
                    current_task=task or "",
                    tool_name=name,
                    tool_arguments=json.loads(args),
                    tool_result=str(result),
                )

                result = "<compact_tool_result>\n" + \
                    str(result) + "\n</compact_tool_result>"

            print_section(f"TOOL RESULT: {name}", str(result))

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(result),
            })

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
