import hashlib
from pathlib import Path

from .docker_executor import DockerExecutor


class SandboxManager:
    def __init__(
        self,
        image="agent-harness-sandbox:latest",
    ):
        self.docker = DockerExecutor(image=image)

    def _container_name(self, run_id):
        # Generate a predictable, Docker-safe container name.
        digest = hashlib.sha256(
            run_id.encode("utf-8")
        ).hexdigest()[:12]

        return f"agent-sandbox-{digest}"

    def ensure(self, run_id, workspace):
        """
        Ensure that this run has a running container.
        Reuse it if it already exists and is running.
        """
        workspace = Path(workspace).resolve()
        workspace.mkdir(parents=True, exist_ok=True)

        container = self._container_name(run_id)

        if self.docker.is_running(container):
            return container

        # Remove an existing stopped container before recreating it.
        self.docker.remove(container)

        result = self.docker.create(
            container_name=container,
            workspace=workspace,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to create sandbox: {result.stderr}"
            )

        print(f"[DOCKER SANDBOX] Starting container {container}")
        return container

    def _require_running(self, run_id):
        container = self._container_name(run_id)

        if not self.docker.is_running(container):
            raise RuntimeError(
                f"Sandbox for run '{run_id}' is not running. "
                "Call ensure() first."
            )

        return container

    def _result(self, result):
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def execute_python(self, run_id, code, timeout=30):
        container = self._require_running(run_id)

        result = self.docker.execute(
            container_name=container,
            command=[
                "timeout",
                "--signal=TERM",
                "--kill-after=2s",
                f"{timeout}s",
                "python",
                "-",
            ],
            timeout=timeout,
            input_text=code,
        )

        return self._result(result)

    def execute_bash(self, run_id, command, timeout=30):
        container = self._require_running(run_id)

        result = self.docker.execute(
            container_name=container,
            command=[
                "timeout",
                "--signal=TERM",
                "--kill-after=2s",
                f"{timeout}s",
                "bash",
                "-lc",
                command,
            ],
            timeout=timeout,
        )

        return self._result(result)

    def is_running(self, run_id):
        container = self._container_name(run_id)
        return self.docker.is_running(container)

    def destroy(self, run_id):
        container = self._container_name(run_id)
        return self.docker.remove(container)
