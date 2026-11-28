from tools import tools, skills, todos
from tools.agents.agent_registry import AGENTS
from tools.agents.subagent import run_subagent

available_agents_name = []
available_agents = ""

for k, v in AGENTS.items():
    available_agents_name.append(f"{k}")
    available_agents += f"\n\n - {k}: {v.description}"


TOOL_REGISTRY = {
    "delegate_task": {
        "schema": {
            "type": "function",
            "function": {
                "name": "delegate_task",
                "description": (
                    "Delegate a task to a specialized sub-agent. It runs its "
                    "own agent loop with the same sandbox, Kaggle kernel and "
                    "W&B project, and returns only its final answer. It does "
                    "not see this conversation: put every needed detail "
                    "(goal, files, ids, constraints, expected output) in "
                    f"task.\n\nAvailable agents:{available_agents}"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_name": {
                            "type": "string",
                            "enum": available_agents_name
                        },
                        "task": {
                            "type": "string",
                            "description": "Detailed task for the sub-agent."
                        }
                    },
                    "required": [
                        "agent_name",
                        "task"
                    ],
                    "additionalProperties": False
                }
            },
        },

        "function": run_subagent
    },

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
                                "File to read. Sandbox paths work: "
                                "'/deliverables/report.md', "
                                "'/kaggle_sandbox/train.py'. A relative "
                                "path is looked up in /deliverables, "
                                "then in the project root."
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
                "description": (
                    "Create, overwrite, append to, or partially edit a project file. "
                    "Always pass `operation`. 'write' and 'append' need `content`; "
                    "'replace' needs `old_text` and `new_text`."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "File to write. Sandbox paths work: "
                                "'/deliverables/report.md', "
                                "'/kaggle_sandbox/train.py'. A relative "
                                "path is relative to /deliverables. "
                                "Only /deliverables and /kaggle_sandbox "
                                "are writable."
                            ),
                        },

                        "operation": {
                            "type": "string",
                            "enum": ["write", "replace", "append"],
                            "description": (
                                "write: create/overwrite with content. "
                                "append: add content to the end. "
                                "replace: swap old_text for new_text."
                            ),
                        },

                        "content": {
                            "type": "string",
                            "description": "The text for 'write' or 'append' (required for them).",
                        },
                        "old_text": {
                            "type": "string"
                        },
                        "new_text": {
                            "type": "string"
                        },
                        "replace_many": {
                            "type": "boolean"
                        },
                        "allow_empty": {
                            "type": "boolean",
                            "description": "Only to create an empty file on purpose; otherwise empty content is refused."
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

    "kaggle_init": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_init",
                "description": (
                    "Initialize Kaggle kernel metadata in the current "
                    "project directory. Call this before configuring "
                    "or pushing a new Kaggle kernel."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_init,
    },

    "kaggle_push": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_push",
                "description": (
                    "Push the current project to Kaggle and optionally "
                    "execute the kernel. Supports GPU accelerators, "
                    "execution timeout, and no-run mode."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "accelerator": {
                            "type": ["string", "null"],
                            "description": (
                                "Kaggle accelerator, such as "
                                "NvidiaTeslaT4 or NvidiaTeslaP100."
                            ),
                        },
                        "timeout": {
                            "type": ["integer", "null"],
                            "description": "Kernel execution timeout in seconds.",
                        },
                        "no_run": {
                            "type": "boolean",
                            "description": "Push without executing the kernel.",
                        },
                        "force": {
                            "type": "boolean",
                            "description": "Push even if train.py is unchanged since the last push (a deliberate re-run).",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_push,
    },

    "kaggle_status": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_status",
                "description": (
                    "Check the execution status of the current Kaggle kernel."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_status,
    },

    "kaggle_training_progress": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_training_progress",
                "description": (
                    "Check a pushed kernel: status, and while RUNNING the "
                    "live training progress read from the streaming log "
                    "(step, total steps, percent, elapsed and remaining "
                    "seconds, latest log lines). Returns "
                    "suggested_wait_seconds: sleep that long with "
                    "execute_bash before checking again. Use it instead "
                    "of kaggle_status while waiting for a run."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "watch_seconds": {
                            "type": "integer",
                            "description": (
                                "How long to read the live log (5-60). "
                                "Default 20."
                            ),
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_training_progress,
    },

    "kaggle_delete": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_delete",
                "description": (
                    "Permanently delete the current Kaggle kernel. "
                    "Use only when deletion is explicitly requested."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_delete,
    },

    "kaggle_list_output_files": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_list_output_files",
                "description": (
                    "List files generated by the current Kaggle kernel."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "page_size": {
                            "type": ["integer", "null"],
                            "description": "Number of output files per page.",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_list_output_files,
    },

    "kaggle_download_output_files": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_download_output_files",
                "description": (
                    "Download output files from the current Kaggle kernel "
                    "into the configured output directory."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "force": {
                            "type": "boolean",
                            "description": "Overwrite existing output files.",
                        },
                        "quiet": {
                            "type": "boolean",
                            "description": "Suppress Kaggle CLI output.",
                        },
                        "regex": {
                            "type": ["string", "null"],
                            "description": (
                                "Optional regular expression matched "
                                "against output filenames, e.g. "
                                "'.*\\.csv$'. A glob such as '*.csv' "
                                "is also accepted and converted."
                            ),
                        },
                        "page_size": {
                            "type": ["integer", "null"],
                            "description": "Number of files per page.",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_download_output_files,
    },


    "write_kaggle_metadata": {
        "schema": {
            "type": "function",
            "function": {
                "name": "write_kaggle_metadata",
                "description": (
                    "Partially update kernel-metadata.json. Only the "
                    "arguments you pass are changed; omitted fields, "
                    "including every *_sources list, keep their current "
                    "values. Pass an empty list to clear a source list. "
                    "enable_gpu=false also removes machine_shape. "
                    "Also sets the identity fields (id, title, "
                    "code_file, language, kernel_type) that "
                    "kaggle_init leaves as placeholders."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": (
                                "Kernel id 'nbtailee22/<slug>'; slug is "
                                "lowercase letters, digits, single hyphens."
                            ),
                        },
                        "title": {
                            "type": "string",
                            "description": "Kernel title; its words should match the slug.",
                        },
                        "code_file": {
                            "type": "string",
                            "description": "Entry script in the kernel dir, e.g. 'train.py'.",
                        },
                        "language": {
                            "type": "string",
                            "enum": ["python", "r", "rmarkdown"],
                            "description": "Kernel language. Use 'python'.",
                        },
                        "kernel_type": {
                            "type": "string",
                            "enum": ["script", "notebook"],
                            "description": "Use 'script' for train.py.",
                        },
                        "enable_gpu": {
                            "type": "boolean",
                            "description": (
                                "Enable GPU. true also sets machine_shape "
                                "to NvidiaTeslaT4; false removes it."
                            ),
                        },
                        "enable_internet": {
                            "type": "boolean",
                            "description": "Enable internet access for the Kaggle kernel.",
                        },
                        "machine_shape": {
                            "type": "boolean",
                            "description": (
                                "true: use the NvidiaTeslaT4 machine shape "
                                "(implies enable_gpu=true). false: remove "
                                "machine_shape from the metadata."
                            ),
                        },
                        "dataset_sources": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Replace dataset sources (owner/slug).",
                        },
                        "model_sources": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Replace model sources.",
                        },
                        "competition_sources": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Replace competition sources.",
                        },
                        "kernel_sources": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Replace kernel sources (owner/slug).",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.write_kaggle_metadata,
    },

    "kaggle_get_output_log": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_get_output_log",
                "description": (
                    "Retrieve the beautified execution log of the current "
                    "Kaggle kernel. The output files must first be downloaded "
                    "using kaggle_download_output_files."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_get_output_log,
    },

    "wandb_training_metrics": {
        "schema": {
            "type": "function",
            "function": {
                "name": "wandb_training_metrics",
                "description": (
                    "Live W&B metrics of the current kernel's latest run "
                    "(any framework that uses AgentRun): loss and metric "
                    "curves, best point, and a fit verdict (healthy, "
                    "warming_up, overfit, underfit, diverged) with an "
                    "action (continue, stop_and_edit, let_finish, "
                    "final_only), suggested_edits and "
                    "suggested_wait_seconds. Use while the kernel is "
                    "RUNNING, next to kaggle_training_progress."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "last_n": {
                            "type": "integer",
                            "description": "Points per curve (1-50). Default 10.",
                        },
                        "chance_level": {
                            "type": ["number", "null"],
                            "description": (
                                "Metric value of a random guess, e.g. 0.5 "
                                "for balanced binary accuracy."
                            ),
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.wandb_training_metrics,
    },

    "wandb_stop_training": {
        "schema": {
            "type": "function",
            "function": {
                "name": "wandb_stop_training",
                "description": (
                    "Stop the running Kaggle training early to save GPU "
                    "time. Use only when wandb_training_metrics returns "
                    "action 'stop_and_edit'. train.py stops within about "
                    "30 seconds and keeps the best checkpoint."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": (
                                "Verdict and evidence, e.g. 'overfit: eval "
                                "loss up for 3 evals'."
                            ),
                        },
                    },
                    "required": ["reason"],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.wandb_stop_training,
    },

    "wandb_compare_runs": {
        "schema": {
            "type": "function",
            "function": {
                "name": "wandb_compare_runs",
                "description": (
                    "Rank W&B training runs by a metric (default: the "
                    "run's primary_metric) and return the best run with "
                    "its hyperparameters, framework and URL."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": ["string", "null"],
                            "description": (
                                "e.g. eval/accuracy, eval/rmse. Null uses "
                                "the primary_metric."
                            ),
                        },
                        "goal": {
                            "type": ["string", "null"],
                            "enum": ["max", "min", None],
                            "description": "Null uses the run's goal.",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Rows to return (1-20). Default 5.",
                        },
                        "scope": {
                            "type": "string",
                            "enum": ["kernel", "project"],
                            "description": (
                                "project: every run in the active project, "
                                "incl. host-recorded baselines (default). "
                                "kernel: runs of the current kernel only."
                            ),
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.wandb_compare_runs,
    },

    "wandb_sync_kaggle_run": {
        "schema": {
            "type": "function",
            "function": {
                "name": "wandb_sync_kaggle_run",
                "description": (
                    "Upload offline W&B runs (train.py printed "
                    "WANDB_OFFLINE) from the downloaded kernel output. "
                    "Call after kaggle_download_output_files."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.wandb_sync_kaggle_run,
    },

    "wandb_list_projects": {
        "schema": {
            "type": "function",
            "function": {
                "name": "wandb_list_projects",
                "description": (
                    "List the W&B projects of entity leductai2201 (fixed) "
                    "and show which one is active. The other wandb_* tools "
                    "use the active project."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.wandb_list_projects,
    },

    "wandb_create_project": {
        "schema": {
            "type": "function",
            "function": {
                "name": "wandb_create_project",
                "description": (
                    "Create a new W&B project under leductai2201 and make "
                    "it the active project. Then set WANDB_PROJECT in "
                    "train.py to the same name."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": (
                                "Project name: letters, digits, '-', '_' or "
                                "'.', e.g. sst2-distilbert."
                            ),
                        },
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.wandb_create_project,
    },

    "wandb_use_project": {
        "schema": {
            "type": "function",
            "function": {
                "name": "wandb_use_project",
                "description": (
                    "Switch the active W&B project to an existing one. "
                    "Then set WANDB_PROJECT in train.py to the same name."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Existing project name.",
                        },
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.wandb_use_project,
    },

    "wandb_list_runs": {
        "schema": {
            "type": "function",
            "function": {
                "name": "wandb_list_runs",
                "description": (
                    "List runs of a W&B project, newest first: id, name, "
                    "state, group, framework, primary metric value, tags, URL."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": ["string", "null"],
                            "description": "Project name. Null = active project.",
                        },
                        "group": {
                            "type": ["string", "null"],
                            "description": "Only runs of this group (a kernel slug).",
                        },
                        "state": {
                            "type": ["string", "null"],
                            "enum": ["running", "finished", "crashed",
                                     "failed", "killed", None],
                            "description": "Only runs in this state.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max runs (1-100). Default 20.",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.wandb_list_runs,
    },

    "wandb_create_run": {
        "schema": {
            "type": "function",
            "function": {
                "name": "wandb_create_run",
                "description": (
                    "Create a finished W&B run from the host to record "
                    "results that did not come from an AgentRun kernel, "
                    "e.g. a baseline, a local evaluation or an experiment "
                    "note. Training runs on Kaggle create their own runs."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Run name."},
                        "project": {
                            "type": ["string", "null"],
                            "description": "Project name. Null = active project.",
                        },
                        "config": {
                            "type": ["object", "null"],
                            "description": "Hyperparameters / settings.",
                        },
                        "metrics": {
                            "type": ["object", "null"],
                            "description": (
                                "Final metrics written to the run summary, "
                                "e.g. {\"eval/accuracy\": 0.91}."
                            ),
                        },
                        "group": {"type": ["string", "null"]},
                        "tags": {
                            "type": ["array", "null"],
                            "items": {"type": "string"},
                        },
                        "notes": {"type": ["string", "null"]},
                    },
                    "required": ["name", "metrics"],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.wandb_create_run,
    },






    "kaggle_model_init": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_model_init",
                "description": (
                    "Initialize Kaggle model metadata in the current "
                    "project directory. Call this before configuring "
                    "or creating a new Kaggle model."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_model_init,
    },


    "write_kaggle_model_metadata": {
        "schema": {
            "type": "function",
            "function": {
                "name": "write_kaggle_model_metadata",
                "description": (
                    "Write or update Kaggle model metadata, including "
                    "model title, description, owner slug, model slug, "
                    "and privacy settings. Only supplied fields are updated."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": ["string", "null"],
                            "description": "Title of the Kaggle model.",
                        },
                        "description": {
                            "type": ["string", "null"],
                            "description": "Description of the Kaggle model.",
                        },
                        "owner_slug": {
                            "type": ["string", "null"],
                            "description": "Kaggle username or owner slug.",
                        },
                        "slug": {
                            "type": ["string", "null"],
                            "description": "Unique model slug.",
                        },
                        "is_private": {
                            "type": ["boolean", "null"],
                            "description": (
                                "Whether the model should be private. "
                                "Omit or use null to leave the current "
                                "privacy setting unchanged."
                            ),
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.write_kaggle_model_metadata,
    },


    "kaggle_model_read_metadata": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_model_read_metadata",
                "description": (
                    "Read the current local Kaggle model metadata "
                    "from model-metadata.json."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_model_read_metadata,
    },


    "kaggle_model_create": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_model_create",
                "description": (
                    "Create and register a new Kaggle model using "
                    "the configured local model metadata. Initialize "
                    "and configure model metadata before calling."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_model_create,
    },


    "kaggle_model_update": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_model_update",
                "description": (
                    "Update the existing Kaggle model using the "
                    "local model-metadata.json file."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_model_update,
    },


    "kaggle_model_get": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_model_get",
                "description": (
                    "Retrieve details and metadata for the configured "
                    "Kaggle model into a local output directory."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "output_path": {
                            "type": ["string", "null"],
                            "description": (
                                "Relative paths resolve against "
                                "/kaggle_sandbox; /kaggle_sandbox/... and "
                                "/deliverables/... map to those mounts. "
                                "Local directory for downloaded model "
                                "information. Defaults to the configured "
                                "models output directory."
                            ),
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_model_get,
    },


    "kaggle_model_list": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_model_list",
                "description": (
                    "List or search the Kaggle models owned by "
                    "nbtailee22. The owner is fixed; supports search "
                    "terms, page size, and sorting."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "search": {
                            "type": ["string", "null"],
                            "description": (
                                "Search term for model discovery."
                            ),
                        },
                        "page_size": {
                            "type": "integer",
                            "description": (
                                "Number of models per page."
                            ),
                            "default": 20,
                        },
                        "sort_by": {
                            "type": ["string", "null"],
                            "description": (
                                "Optional model sorting field."
                            ),
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_model_list,
    },


    "kaggle_model_delete": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_model_delete",
                "description": (
                    "Permanently delete the configured Kaggle model. "
                    "Use only when deletion is explicitly requested. "
                    "Requires explicit confirmation."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "confirm": {
                            "type": "boolean",
                            "description": (
                                "Explicit confirmation to permanently "
                                "delete the Kaggle model."
                            ),
                            "default": False,
                        },
                    },
                    "required": ["confirm"],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_model_delete,
    },


    # dataset

    "kaggle_dataset_init": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_dataset_init",
                "description": (
                    "Initialize Kaggle dataset metadata in the current "
                    "project directory. Call this before configuring "
                    "or creating a new Kaggle dataset."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_dataset_init,
    },


    "write_kaggle_dataset_metadata": {
        "schema": {
            "type": "function",
            "function": {
                "name": "write_kaggle_dataset_metadata",
                "description": (
                    "Write or update local Kaggle dataset metadata, "
                    "including title, subtitle, description, licenses, "
                    "keywords, resources, and privacy settings. "
                    "Only supplied metadata fields are updated. Also "
                    "sets the dataset id that kaggle_dataset_init leaves "
                    "as a placeholder."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": (
                                "Dataset id 'nbtailee22/<slug>'; slug is "
                                "lowercase letters, digits, single hyphens."
                            ),
                        },
                        "title": {
                            "type": ["string", "null"],
                            "description": "Dataset title.",
                        },
                        "subtitle": {
                            "type": ["string", "null"],
                            "description": "Short dataset subtitle.",
                        },
                        "description": {
                            "type": ["string", "null"],
                            "description": "Dataset description.",
                        },
                        "licenses": {
                            "type": ["array", "null"],
                            "items": {
                                "type": "object",
                            },
                            "description": (
                                "Dataset license information."
                            ),
                        },
                        "keywords": {
                            "type": ["array", "null"],
                            "items": {
                                "type": "string",
                            },
                            "description": (
                                "Keywords associated with the dataset."
                            ),
                        },
                        "resources": {
                            "type": ["array", "null"],
                            "items": {
                                "type": "object",
                            },
                            "description": (
                                "Dataset resource definitions."
                            ),
                        },
                        "is_private": {
                            "type": ["boolean", "null"],
                            "description": (
                                "Whether the dataset should be private. "
                                "Omit to leave the current setting "
                                "(new datasets are private)."
                            ),
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.write_kaggle_dataset_metadata,
    },


    "kaggle_dataset_read_metadata": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_dataset_read_metadata",
                "description": (
                    "Read the current local Kaggle dataset metadata "
                    "from dataset-metadata.json."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_dataset_read_metadata,
    },


    "kaggle_dataset_create": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_dataset_create",
                "description": (
                    "Create and upload a new Kaggle dataset using "
                    "the configured local dataset metadata and files. "
                    "Can optionally publish the dataset publicly."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "public": {
                            "type": "boolean",
                            "description": (
                                "Whether to create the dataset publicly."
                            ),
                            "default": False,
                        },
                        "quiet": {
                            "type": "boolean",
                            "description": (
                                "Suppress non-error command output."
                            ),
                            "default": False,
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_dataset_create,
    },


    "kaggle_dataset_version": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_dataset_version",
                "description": (
                    "Upload a new version of the current Kaggle dataset. "
                    "Requires a version message describing the changes."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": (
                                "Description of changes in this dataset version."
                            ),
                        },
                        "convert_to_csv": {
                            "type": "boolean",
                            "description": (
                                "Convert supported files to CSV during upload."
                            ),
                            "default": False,
                        },
                        "quiet": {
                            "type": "boolean",
                            "description": (
                                "Suppress non-error command output."
                            ),
                            "default": False,
                        },
                    },
                    "required": ["message"],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_dataset_version,
    },


    "kaggle_dataset_status": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_dataset_status",
                "description": (
                    "Get the remote status of the current Kaggle dataset."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_dataset_status,
    },


    "kaggle_dataset_list_files": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_dataset_list_files",
                "description": (
                    "List files belonging to the current remote "
                    "Kaggle dataset."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_dataset_list_files,
    },

    "kaggle_dataset_download": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_dataset_download",
                "description": (
                    "Download the current Kaggle dataset into a local "
                    "directory. By default, files are downloaded to "
                    "the configured datasets output directory and unzipped."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "output_path": {
                            "type": ["string", "null"],
                            "description": (
                                "Relative paths resolve against "
                                "/kaggle_sandbox; /kaggle_sandbox/... and "
                                "/deliverables/... map to those mounts. "
                                "Local directory where dataset files "
                                "should be downloaded. Defaults to "
                                "the configured datasets output directory."
                            ),
                        },
                        "force": {
                            "type": "boolean",
                            "description": (
                                "Force download even if files already exist."
                            ),
                            "default": False,
                        },
                        "unzip": {
                            "type": "boolean",
                            "description": (
                                "Extract downloaded archive files."
                            ),
                            "default": True,
                        },
                        "quiet": {
                            "type": "boolean",
                            "description": (
                                "Suppress non-error command output."
                            ),
                            "default": False,
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_dataset_download,
    },


    "kaggle_dataset_delete": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_dataset_delete",
                "description": (
                    "Permanently delete the current Kaggle dataset. "
                    "Only use when deletion is explicitly requested. "
                    "Requires explicit confirmation."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "confirm": {
                            "type": "boolean",
                            "description": (
                                "Explicit confirmation to permanently "
                                "delete the Kaggle dataset."
                            ),
                            "default": False,
                        },
                    },
                    "required": ["confirm"],
                    "additionalProperties": False,
                },
            },
        },
        "function": tools.kaggle_dataset_delete,
    },


    "kaggle_list_available_dataset": {
        "schema": {
            "type": "function",
            "function": {
                "name": "kaggle_list_available_dataset",
                "description": (
                    "List the Kaggle datasets owned by nbtailee22. "
                    "The owner is fixed. Use it to check which "
                    "datasets already exist."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },

        "function": tools.kaggle_list_available_dataset,
    },



}

# Runs arbitrary Python on the host with its keys; not given to agents.
HOST_ONLY_TOOLS = {"write_and_run_temp_file"}

TOOL_SCHEMAS = [
    item["schema"] for name, item in TOOL_REGISTRY.items()
    if name not in HOST_ONLY_TOOLS
]

# Running and monitoring kernels belongs to the experiment-scientist sub-agent.
EXPERIMENT_TOOLS = {
    "kaggle_init", "write_kaggle_metadata", "kaggle_push", "kaggle_delete",
    "kaggle_training_progress", "wandb_training_metrics",
    "wandb_stop_training", "wandb_sync_kaggle_run",
}
MAIN_TOOL_SCHEMAS = [
    t for t in TOOL_SCHEMAS if t["function"]["name"] not in EXPERIMENT_TOOLS
]


def list_tools():
    return "\n".join(f"- {tool}" for tool in TOOL_REGISTRY)
