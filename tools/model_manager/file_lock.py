from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path


class LockTimeoutError(TimeoutError):
    pass


@dataclass
class FileLock:
    path: Path
    timeout_sec: int = 15
    poll_sec: float = 0.25
    _fd: int | None = None

    def acquire(self) -> None:
        deadline = time.time() + self.timeout_sec
        while True:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self._fd, str(os.getpid()).encode("utf-8"))
                return
            except FileExistsError:
                if time.time() >= deadline:
                    raise LockTimeoutError(f"Could not acquire lock: {self.path}")
                time.sleep(self.poll_sec)

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            self.path.unlink(missing_ok=True)
        except Exception:
            pass

    def __enter__(self) -> "FileLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

