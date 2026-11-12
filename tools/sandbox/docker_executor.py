import subprocess
from pathlib import Path


class DockerExecutor:
    def __init__(self, image="agent-harness-sandbox:latest"):
        self.image = image

    def _run(self, args, timeout=200, input_text=None):
        return subprocess.run(
            ["docker", *args],
            timeout=timeout,
            input=input_text,
            capture_output=True,
            text=True,
            check=False
        )

    def is_running(self, container_name):
        result = self._run([
            "inspect",
            "--format",
            "{{.State.Running}}",
            container_name
        ])

        return (
            result.returncode == 0 and result.stdout.strip() == "true"
        )

    def create(self, container_name, workspace):
        workspace = Path(workspace).resolve()

        if not workspace.is_dir():
            raise NotADirectoryError(str(workspace))

        return self._run([
            "run",
            "-d",
            "--name", container_name,

            # network isolation
            "--network", "none",

            # resource limits
            "--memory", "2g",
            "--memory-swap", "2g",
            "--cpus", "1",
            "--pids-limit", "128",

            # filesystem restrictions
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m",

            # security
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "--user", "10001:10001",

            # bind mount folder so we can read and write the mount folder even in the sandbox
            "--mount",
            f"type=bind,source={workspace},target=/deliverables",

            "--workdir", "/deliverables",
            self.image,
        ])

    def execute(self, container_name, command, timeout=200, input_text=None):
        return self._run([
            "exec",
            "-i",
            container_name,
            *command
        ], timeout=timeout, input_text=input_text)

    def remove(self, container_name):
        return self._run([
            "rm",
            "-f",
            container_name
        ])
