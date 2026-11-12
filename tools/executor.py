from tools.registry import TOOL_REGISTRY
import json
import inspect


def dispatch_tool(
    name: str,
    arguments: str,
    context=None,
):
    tool = TOOL_REGISTRY.get(name)

    if tool is None:
        return f"Unknown tool: {name}"

    try:
        args = json.loads(arguments)

        if not isinstance(args, dict):
            raise ValueError("Tool arguments must be a JSON object")

        # Inject runtime context when required.
        if "context" in list(inspect.signature(tool["function"]).parameters.keys()):
            if context is None:
                raise ValueError(
                    f"Tool '{name}' requires runtime context"
                )

            result = tool["function"](
                **args,
                context=context,
            )
        else:
            result = tool["function"](**args)

        return str(result)

    except (
        json.JSONDecodeError,
        TypeError,
        ValueError,
        PermissionError,
        RuntimeError,
        OSError,
    ) as exc:
        return f"Tool execution error: {exc}"
