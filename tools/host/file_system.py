
from pathlib import Path
from typing import Literal


class HostFilesystem:
    def __init__(
        self,
        allowed_roots_read,
        allowed_roots_write,
        max_read_bytes=2_000_000,
    ):
        self.allowed_roots_read = [
            Path(p).expanduser().resolve()
            for p in allowed_roots_read
        ]

        self.allowed_roots_write = [
            Path(p).expanduser().resolve()
            for p in allowed_roots_write
        ]

        self.max_read_bytes = max_read_bytes

    def _resolve(
        self,
        path,
        mode: Literal["write", "read"],
    ):
        if mode not in {"write", "read"}:
            raise ValueError(f"Invalid filesystem mode: {mode}")

        target = Path(path).expanduser().resolve(
            strict=(mode == "read")
        )

        roots = (
            self.allowed_roots_read
            if mode == "read"
            else self.allowed_roots_write
        )

        allowed = any(
            target == root or root in target.parents
            for root in roots
        )

        if not allowed:
            raise PermissionError(
                f"Access denied: {target}. "
                f"Allowed roots: {roots}"
            )

        return target

    def read_file(self, path):
        target = self._resolve(path, "read")

        if not target.is_file():
            raise ValueError("Not a file")

        if target.stat().st_size > self.max_read_bytes:
            raise ValueError("File exceeds maximum size")

        return target.read_text(
            encoding="utf-8",
            errors="replace",
        )
