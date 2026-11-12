from tools.todos import todos_prompt


def reminder():
    plan = todos_prompt()

    if not plan:
        return {
            "role": "user",
            "content": "<env>\nNo active todo list.\n</env>",
        }

    return {
        "role": "user",
        "content": f"<env>\n<todos>\n{plan}\n</todos>\n</env>",
    }