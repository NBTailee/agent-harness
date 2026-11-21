from tools.training_orchestrator.kaggle_executor import KernelExecutor, DatasetExecutor, ModelExecutor
from dataclasses import dataclass


@dataclass
class KaggleManager:
    kernel_executor: KernelExecutor
    dataset_executor: DatasetExecutor
    model_executor: ModelExecutor
