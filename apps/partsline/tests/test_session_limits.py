from __future__ import annotations

import asyncio
import os
import unittest

from agent.session_limits import (
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    DEFAULT_MAX_DURATION_SECONDS,
    IDLE_TIMEOUT_ENV,
    MAX_DURATION_ENV,
    SessionLimits,
    configured_idle_timeout,
    configured_max_duration,
)


class RecordingCallbacks:
    """Counts watchdog firings."""

    def __init__(self) -> None:
        self.idle_fired = 0
        self.max_fired = 0

    def on_idle(self) -> None:
        self.idle_fired += 1

    def on_max(self) -> None:
        self.max_fired += 1


class SessionLimitsWatchdogTest(unittest.IsolatedAsyncioTestCase):
    def _make(
        self, *, idle: float, max_duration: float
    ) -> tuple[SessionLimits, RecordingCallbacks]:
        cb = RecordingCallbacks()
        limits = SessionLimits(
            on_idle_timeout=cb.on_idle,
            on_max_duration=cb.on_max,
            idle_timeout=idle,
            max_duration=max_duration,
        )
        return limits, cb

    async def test_a_idle_timeout_fires_and_triggers_shutdown(self) -> None:
        limits, cb = self._make(idle=0.1, max_duration=5.0)
        limits.start()
        await asyncio.sleep(0.3)
        self.assertEqual(cb.idle_fired, 1)
        self.assertEqual(cb.max_fired, 0)
        self.assertEqual(limits.fired, "idle")
        await limits.stop()

    async def test_b_completed_user_turn_resets_idle_timer(self) -> None:
        limits, cb = self._make(idle=0.3, max_duration=5.0)
        limits.start()
        await asyncio.sleep(0.15)
        limits.record_user_activity()  # deadline moves to t ~= 0.45
        await asyncio.sleep(0.2)  # t ~= 0.35, before new deadline
        self.assertEqual(cb.idle_fired, 0, "activity should have reset the timer")
        await asyncio.sleep(0.4)  # t ~= 0.75, past new deadline
        self.assertEqual(cb.idle_fired, 1)
        self.assertEqual(limits.fired, "idle")
        await limits.stop()

    async def test_c_agent_speech_does_not_reset_idle_timer(self) -> None:
        # The contract: the ONLY reset hook is record_user_activity(),
        # to be called from the user-turn-completed event. Agent speech
        # has no hook at all, so we simulate the agent "speaking"
        # repeatedly during the idle window and assert the timeout still
        # fires. We also pin the API surface so no one adds an
        # agent-activity hook later without breaking this test.
        limits, cb = self._make(idle=0.2, max_duration=5.0)
        self.assertFalse(
            hasattr(limits, "record_agent_activity"),
            "agent speech must never be able to keep a session alive",
        )
        limits.start()

        async def agent_speaks() -> None:
            # Simulated TTS playout: consumes time, touches no reset hook.
            await asyncio.sleep(0.05)

        for _ in range(6):  # agent "talks" throughout the idle window
            await agent_speaks()
        self.assertEqual(cb.idle_fired, 1)
        self.assertEqual(limits.fired, "idle")
        await limits.stop()

    async def test_d_hard_cap_fires_even_with_continuous_user_activity(self) -> None:
        limits, cb = self._make(idle=0.2, max_duration=0.4)
        limits.start()
        for _ in range(10):  # keep the caller "active" past the cap
            await asyncio.sleep(0.06)
            limits.record_user_activity()
        self.assertEqual(cb.max_fired, 1)
        self.assertEqual(cb.idle_fired, 0)
        self.assertEqual(limits.fired, "max")
        await limits.stop()

    async def test_only_one_watchdog_ever_fires(self) -> None:
        limits, cb = self._make(idle=0.1, max_duration=0.12)
        limits.start()
        await asyncio.sleep(0.4)
        self.assertEqual(cb.idle_fired + cb.max_fired, 1)
        await limits.stop()

    async def test_stop_cancels_both_watchdogs(self) -> None:
        limits, cb = self._make(idle=0.1, max_duration=0.15)
        limits.start()
        await limits.stop()
        await asyncio.sleep(0.3)  # well past both deadlines
        self.assertEqual(cb.idle_fired, 0)
        self.assertEqual(cb.max_fired, 0)
        self.assertIsNone(limits.fired)


class SessionLimitsEnvConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            name: os.environ.get(name) for name in (IDLE_TIMEOUT_ENV, MAX_DURATION_ENV)
        }

    def tearDown(self) -> None:
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_e_env_vars_override_defaults(self) -> None:
        os.environ[IDLE_TIMEOUT_ENV] = "45"
        os.environ[MAX_DURATION_ENV] = "600"
        self.assertEqual(configured_idle_timeout(), 45.0)
        self.assertEqual(configured_max_duration(), 600.0)

    def test_e_missing_env_uses_defaults(self) -> None:
        os.environ.pop(IDLE_TIMEOUT_ENV, None)
        os.environ.pop(MAX_DURATION_ENV, None)
        self.assertEqual(configured_idle_timeout(), DEFAULT_IDLE_TIMEOUT_SECONDS)
        self.assertEqual(configured_max_duration(), DEFAULT_MAX_DURATION_SECONDS)

    def test_e_zero_negative_or_garbage_cannot_disable_limits(self) -> None:
        for bad in ("0", "-5", "abc", "", "  "):
            os.environ[IDLE_TIMEOUT_ENV] = bad
            os.environ[MAX_DURATION_ENV] = bad
            self.assertEqual(
                configured_idle_timeout(),
                DEFAULT_IDLE_TIMEOUT_SECONDS,
                f"idle timeout must fall back to default for {bad!r}",
            )
            self.assertEqual(
                configured_max_duration(),
                DEFAULT_MAX_DURATION_SECONDS,
                f"max duration must fall back to default for {bad!r}",
            )

    def test_e_constructor_ignores_non_positive_overrides(self) -> None:
        os.environ.pop(IDLE_TIMEOUT_ENV, None)
        os.environ.pop(MAX_DURATION_ENV, None)
        cb = RecordingCallbacks()
        limits = SessionLimits(
            on_idle_timeout=cb.on_idle,
            on_max_duration=cb.on_max,
            idle_timeout=0,
            max_duration=-1,
        )
        self.assertEqual(limits.idle_timeout, DEFAULT_IDLE_TIMEOUT_SECONDS)
        self.assertEqual(limits.max_duration, DEFAULT_MAX_DURATION_SECONDS)


if __name__ == "__main__":
    unittest.main()
