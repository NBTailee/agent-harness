from dataclasses import dataclass
from typing import Optional


@dataclass
class AgentConfig:
    name: str
    description: str
    max_turns: int = 20
    system_prompt: str = None
    allowed_tools: Optional[list[str]] = None


AGENTS = {}


def register_agent(config: AgentConfig):
    AGENTS[config.name] = config


def get_agent(name: str) -> AgentConfig:
    if name not in AGENTS:
        raise ValueError(f"Unknown agent: {name}")

    return AGENTS[name]


def list_agents():
    return list(AGENTS.keys())

# REGISTER AGENTS


register_agent(
    AgentConfig(
        name="experiment-scientist",
        max_turns=150,
        description=(
            "Runs, monitors and analyses ML experiments on Kaggle with W&B: "
            "writes train.py with AgentRun, pushes, watches fit verdicts, "
            "stops and fixes bad runs, compares runs and reports the best."
        )
    )
)
