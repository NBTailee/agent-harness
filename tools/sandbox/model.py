from dataclasses import dataclass
from pathlib import Path

from tools.sandbox.manager import SandboxManager
from tools.host.file_system import HostFilesystem


@dataclass
class ToolContext:
    run_id: str
    deliverables_dir: Path

    sandbox: SandboxManager
    host_filesystem: HostFilesystem


@dataclass
class SandboxConfig:
    memory: str = "2g"
    memory_swap: str = "2g"
    cpus: float = 1.0
    pids_limit: int = 128
    timeout: int = 60
    tmpfs_size: str = "256m"
