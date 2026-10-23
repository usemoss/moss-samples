from __future__ import annotations

import errno
import os
from collections.abc import Callable
from pathlib import Path
from types import TracebackType

LOCKFILE_PATH = Path(__file__).resolve().parents[1] / ".agent.lock"


class AgentProcessLockError(RuntimeError):
    pass


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError as exc:
        return exc.errno == errno.EPERM
    return True


class AgentProcessLock:
    def __init__(
        self,
        *,
        lockfile_path: Path = LOCKFILE_PATH,
        current_pid: Callable[[], int] = os.getpid,
        pid_is_running: Callable[[int], bool] = pid_is_running,
    ) -> None:
        self.lockfile_path = lockfile_path
        self._current_pid = current_pid
        self._pid_is_running = pid_is_running
        self._pid: int | None = None

    def __enter__(self) -> AgentProcessLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()

    def acquire(self) -> None:
        self.lockfile_path.parent.mkdir(parents=True, exist_ok=True)
        pid = self._current_pid()
        while True:
            existing_pid = self._read_existing_pid()
            if existing_pid is not None and self._pid_is_running(existing_pid):
                raise AgentProcessLockError(
                    "PartsLine agent is already running with PID "
                    f"{existing_pid}. Please kill that PID first or delete "
                    f"the stale lockfile at {self.lockfile_path}."
                )
            if self.lockfile_path.exists():
                self.lockfile_path.unlink()
            try:
                with self.lockfile_path.open("x", encoding="utf-8") as lockfile:
                    lockfile.write(f"{pid}\n")
            except FileExistsError:
                continue
            self._pid = pid
            return

    def release(self) -> None:
        if self._pid is None or not self.lockfile_path.exists():
            return
        if self._read_existing_pid() == self._pid:
            self.lockfile_path.unlink()
        self._pid = None

    def _read_existing_pid(self) -> int | None:
        try:
            raw_pid = self.lockfile_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        try:
            return int(raw_pid)
        except ValueError:
            return None
