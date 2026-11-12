from tools import tools, skills, todos


TOOL_REGISTRY = {
    # "bash": {
    #     "schema": {
    #         "type": "function",
    #         "function": {
    #             "name": "bash",
    #             "description": "run a shell command and return its output",
    #             "parameters": {
    #                 "type": "object",
    #                 "properties": {
    #                     "command": {
    #                         "type": "string",
    #                         "description": "a shell command to be run"
    #                     }
    #                 },
    #                 "required": ["command"]
    #             }
    #         }
    #     },

    #     "function": tools.bash
    # },

    "read_file": {
        "schema": {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read and return the contents of a file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Path to the file to read, "
                                "for example 'README.md' or "
                                "'src/agent.py'."
                            ),
                        },
                    },
                    "required": ["path"]
                }
            }
        },

        "function": tools.read_file
    },

    "read_skill": {
        "schema": {
            "type": "function",
            "function": {
                "name": "read_skill",
                "description": "Read and return the contents of a skill file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": (
                                "Path to the skill file to read, "
                                "for example 'SKILL.md'"
                            ),
                        },
                    },
                    "required": ["skill_name"]
                }
            }
        },
        "function": skills.read_skill
    },

    "write_file": {
        "schema": {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Create, overwrite, append to, or partially edit a project file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Path to the file to write."
                            ),
                        },

                        "operation": {
                            "type": "string",
                            "enum": ["write", "replace", "append"],
                            "description": "The file operation to perform."
                        },

                        "content": {
                            "type": "string"
                        },
                        "old_text": {
                            "type": "string"
                        },
                        "new_text": {
                            "type": "string"
                        },
                        "replace_many": {
                            "type": "boolean"
                        }
                    },
                    "required": ["path", "operation"]
                }
            }
        },

        "function": tools.write_file
    },

    "write_todos": {
        "schema": {
            "type": "function",
            "function": {
                "name": "write_todos",
                "description": (
                    "Replace the entire todo list. Each task must have a "
                    "description and a status. At most one task may be "
                    "in_progress."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "todos": {
                            "type": "array",
                            "description": "The complete updated todo list.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "content": {
                                        "type": "string",
                                        "description": "Description of the task."
                                    },
                                    "status": {
                                        "type": "string",
                                        "enum": [
                                            "done",
                                            "pending",
                                            "in_progress"
                                        ],
                                        "description": "Current task status."
                                    }
                                },
                                "required": ["content", "status"],
                                "additionalProperties": False
                            }
                        }
                    },
                    "required": ["todos"]
                }
            }
        },

        "function": todos.write_todos
    },

    "write_and_run_temp_file": {
        "schema": {
            "type": "function",
            "function": {
                "name": "write_and_run_temp_file",
                "description": (
                    "Write Python code to a temporary file, execute it, "
                    "and return its output. The temporary directory is "
                    "automatically deleted afterward."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string"
                        },
                        "content": {
                            "type": "string"
                        }
                    },
                    "required": ["filename", "content"],
                    "additionalProperties": False
                }
            }
        },
        "function": tools.write_and_run_temp_file
    },

    "execute_python": {
        "schema": {
            "type": "function",
            "function": {
                "name": "execute_python",
                "description": (
                    "Execute Python code inside the current "
                    "run's persistent Docker sandbox."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python source code.",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Execution timeout in seconds.",
                        },
                    },
                    "required": ["code", "timeout"],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.execute_python,
    },

    "execute_bash": {
        "schema": {
            "type": "function",
            "function": {
                "name": "execute_bash",
                "description": (
                    "Execute a Bash command inside the current "
                    "run's persistent Docker sandbox."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Bash command to execute.",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Execution timeout in seconds.",
                        },
                    },
                    "required": ["command", "timeout"],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.execute_bash,
    },

}

TOOL_SCHEMAS = [
    item["schema"] for item in TOOL_REGISTRY.values()
]


def list_tools():
    return "\n".join(f"- {tool}" for tool in TOOL_REGISTRY)
