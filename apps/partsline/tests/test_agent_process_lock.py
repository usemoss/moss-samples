from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.process_lock import AgentProcessLock, AgentProcessLockError


class AgentProcessLockTest(unittest.TestCase):
    def test_no_lockfile_starts_cleanly_and_removes_lock_on_shutdown(self) -> None:
        with TemporaryDirectory() as temp_dir:
            lockfile = Path(temp_dir) / ".agent.lock"

            with AgentProcessLock(
                lockfile_path=lockfile,
                current_pid=lambda: 1234,
                pid_is_running=lambda _: False,
            ):
                self.assertEqual(lockfile.read_text(encoding="utf-8"), "1234\n")

            self.assertFalse(lockfile.exists())

    def test_live_pid_lockfile_refuses_to_start_with_clear_message(self) -> None:
        with TemporaryDirectory() as temp_dir:
            lockfile = Path(temp_dir) / ".agent.lock"
            lockfile.write_text("9876\n", encoding="utf-8")

            lock = AgentProcessLock(
                lockfile_path=lockfile,
                current_pid=lambda: 1234,
                pid_is_running=lambda pid: pid == 9876,
            )

            with self.assertRaisesRegex(
                AgentProcessLockError,
                r"already running with PID 9876.*kill that PID first.*delete "
                r"the stale lockfile",
            ):
                lock.acquire()

            self.assertEqual(lockfile.read_text(encoding="utf-8"), "9876\n")

    def test_dead_pid_lockfile_starts_cleanly_and_overwrites_stale_lock(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            lockfile = Path(temp_dir) / ".agent.lock"
            lockfile.write_text("9876\n", encoding="utf-8")

            with AgentProcessLock(
                lockfile_path=lockfile,
                current_pid=lambda: 1234,
                pid_is_running=lambda _: False,
            ):
                self.assertEqual(lockfile.read_text(encoding="utf-8"), "1234\n")

            self.assertFalse(lockfile.exists())


if __name__ == "__main__":
    unittest.main()
