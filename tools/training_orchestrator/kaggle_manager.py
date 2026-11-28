from tools.training_orchestrator.kaggle_executor import KernelExecutor, DatasetExecutor, ModelExecutor
from tools.training_orchestrator.wandb_monitor import WandbMonitor
from dataclasses import dataclass


@dataclass
class KaggleManager:
    kernel_executor: KernelExecutor
    dataset_executor: DatasetExecutor
    model_executor: ModelExecutor
    wandb_monitor: WandbMonitor | None = None  # None when W&B is off
