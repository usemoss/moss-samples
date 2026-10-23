from __future__ import annotations

import asyncio
import inspect
import os
import time
from collections.abc import Awaitable, Callable

ShutdownCallback = Callable[[], None | Awaitable[None]]

DEFAULT_IDLE_TIMEOUT_SECONDS: float = 120.0
DEFAULT_MAX_DURATION_SECONDS: float = 900.0

IDLE_TIMEOUT_ENV = "SESSION_IDLE_TIMEOUT_SECONDS"
MAX_DURATION_ENV = "SESSION_MAX_DURATION_SECONDS"

CLOSING_LINE = "Seems like you've stepped away, so I'm closing out. Call back anytime."


def _positive_seconds_from_env(env_name: str, default: float) -> float:
    """Read a positive float from the environment.

    Any missing, empty, unparsable, zero, or negative value returns the
    default. Zero does NOT mean unlimited; there is no unlimited.
    """
    raw = os.environ.get(env_name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if value <= 0:
        return default
    return value


def configured_idle_timeout() -> float:
    """Idle timeout in seconds, from env or default. Always positive."""
    return _positive_seconds_from_env(IDLE_TIMEOUT_ENV, DEFAULT_IDLE_TIMEOUT_SECONDS)


def configured_max_duration() -> float:
    """Hard session cap in seconds, from env or default. Always positive."""
    return _positive_seconds_from_env(MAX_DURATION_ENV, DEFAULT_MAX_DURATION_SECONDS)


class SessionLimits:
    """Two watchdogs that end a session: idle timeout and hard max duration.

    Usage:
        limits = SessionLimits(
            on_idle_timeout=shutdown_cb,
            on_max_duration=shutdown_cb,
        )
        limits.start()
        # from the user-turn-completed hook ONLY:
        limits.record_user_activity()
        ...
        await limits.stop()  # on normal session end

    At most one callback fires, exactly once, across both watchdogs.
    There is intentionally no record_agent_activity(): agent speech must
    not keep a session alive.
    """

    def __init__(
        self,
        *,
        on_idle_timeout: ShutdownCallback,
        on_max_duration: ShutdownCallback,
        idle_timeout: float | None = None,
        max_duration: float | None = None,
    ) -> None:
        self._on_idle_timeout = on_idle_timeout
        self._on_max_duration = on_max_duration
        # Explicit positive constructor values win; anything else falls
        # back to env-or-default. No path yields a non-positive limit.
        self._idle_timeout = (
            idle_timeout
            if idle_timeout is not None and idle_timeout > 0
            else configured_idle_timeout()
        )
        self._max_duration = (
            max_duration
            if max_duration is not None and max_duration > 0
            else configured_max_duration()
        )
        self._idle_deadline: float = 0.0
        self._idle_task: asyncio.Task[None] | None = None
        self._max_task: asyncio.Task[None] | None = None
        self._fired: str | None = None
        self._started = False

    @property
    def idle_timeout(self) -> float:
        return self._idle_timeout

    @property
    def max_duration(self) -> float:
        return self._max_duration

    @property
    def fired(self) -> str | None:
        """None until a watchdog fires; then "idle" or "max"."""
        return self._fired

    def start(self) -> None:
        """Arm both watchdogs. Idempotent."""
        if self._started:
            return
        self._started = True
        self._idle_deadline = time.monotonic() + self._idle_timeout
        self._idle_task = asyncio.create_task(
            self._watch_idle(), name="session-idle-watchdog"
        )
        self._max_task = asyncio.create_task(
            self._watch_max(), name="session-max-watchdog"
        )

    def record_user_activity(self) -> None:
        """Reset the idle deadline.

        Call this ONLY from the user-turn-completed event. Never call it
        for agent speech: the agent's own output must not keep the
        session alive (feedback loops make agent speech self-sustaining).
        """
        self._idle_deadline = time.monotonic() + self._idle_timeout

    async def stop(self) -> None:
        """Cancel both watchdogs (normal session teardown)."""
        for task in (self._idle_task, self._max_task):
            if task is not None and not task.done():
                task.cancel()
        for task in (self._idle_task, self._max_task):
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._idle_task = None
        self._max_task = None

    async def _watch_idle(self) -> None:
        # Sleeps until the current deadline; if user activity moved the
        # deadline while sleeping, recomputes and sleeps again. No polling.
        while self._fired is None:
            remaining = self._idle_deadline - time.monotonic()
            if remaining <= 0:
                await self._fire("idle", self._on_idle_timeout)
                return
            await asyncio.sleep(remaining)

    async def _watch_max(self) -> None:
        await asyncio.sleep(self._max_duration)
        await self._fire("max", self._on_max_duration)

    async def _fire(self, which: str, callback: ShutdownCallback) -> None:
        if self._fired is not None:
            return
        self._fired = which
        # Stop the sibling watchdog so only one shutdown path runs.
        current = asyncio.current_task()
        for task in (self._idle_task, self._max_task):
            if task is not None and task is not current and not task.done():
                task.cancel()
        result = callback()
        if inspect.isawaitable(result):
            await result
