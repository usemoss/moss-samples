from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Generator
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent.session_limits import CLOSING_LINE


ROOT = Path(__file__).resolve().parents[1]
AGENT_MAIN = ROOT / "agent" / "main.py"
ENV_EXAMPLE = ROOT / ".env.example"


def load_agent_module():
    spec = importlib.util.spec_from_file_location("partsline_agent_main", AGENT_MAIN)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeSpeechHandle:
    def __init__(self, events: list[object], text: str) -> None:
        self._events = events
        self._text = text

    def __await__(self) -> Generator[None, None, "FakeSpeechHandle"]:
        async def wait_for_playout() -> FakeSpeechHandle:
            self._events.append(("playout", self._text))
            return self

        return wait_for_playout().__await__()


class HangingSpeechHandle(FakeSpeechHandle):
    def __init__(self) -> None:
        pass

    def __await__(self) -> Generator[None, None, "HangingSpeechHandle"]:
        async def never_finish() -> HangingSpeechHandle:
            await asyncio.Future()
            return self

        return never_finish().__await__()


class FakeAgentSession:
    def __init__(self, events: list[object]) -> None:
        self._events = events
        self.started = False
        self.start_kwargs: dict[str, object] = {}

    async def start(self, **kwargs: object) -> None:
        self.started = True
        self.start_kwargs = kwargs
        self._events.append("session.start")

    def say(self, text: str, **kwargs: object) -> FakeSpeechHandle:
        self._events.append(("session.say", text, kwargs))
        return FakeSpeechHandle(self._events, text)

    async def aclose(self) -> None:
        self._events.append("session.aclose")


class HangingClosingLineSession(FakeAgentSession):
    def say(self, text: str, **kwargs: object) -> HangingSpeechHandle:
        self._events.append(("session.say", text, kwargs))
        return HangingSpeechHandle()


class FakeRoom:
    def __init__(self, events: list[object]) -> None:
        self._events = events

    async def disconnect(self) -> None:
        self._events.append("room.disconnect")


class FakeContext:
    def __init__(self, events: list[object]) -> None:
        self.room = FakeRoom(events)
        self.shutdown_callbacks: list[Callable[[str], Awaitable[None]]] = []
        self._events = events

    def add_shutdown_callback(self, callback: Callable[[str], Awaitable[None]]) -> None:
        self.shutdown_callbacks.append(callback)
        self._events.append("ctx.add_shutdown_callback")

    def shutdown(self, reason: str = "") -> None:
        self._events.append(("ctx.shutdown", reason))


class FakeSessionLimits:
    instances: list["FakeSessionLimits"] = []

    def __init__(
        self,
        *,
        on_idle_timeout,
        on_max_duration,
    ) -> None:
        self.on_idle_timeout = on_idle_timeout
        self.on_max_duration = on_max_duration
        self.started = False
        self.stopped = False
        self.user_activity_records = 0
        self.events: list[object] | None = None
        self.instances.append(self)

    def start(self) -> None:
        self.started = True
        assert self.events is not None
        self.events.append("limits.start")

    def record_user_activity(self) -> None:
        self.user_activity_records += 1

    async def stop(self) -> None:
        self.stopped = True
        assert self.events is not None
        self.events.append("limits.stop")


class SessionLimitsWiringTest(unittest.TestCase):
    def setUp(self) -> None:
        FakeSessionLimits.instances.clear()

    def test_run_session_starts_limits_after_session_start_and_registers_normal_stop(
        self,
    ) -> None:
        async def run_scenario() -> tuple[list[object], FakeContext]:
            agent = load_agent_module()
            events: list[object] = []
            session = FakeAgentSession(events)
            retrieval_agent = agent.PartsLineAgent()
            context = FakeContext(events)

            def build_limits(**kwargs):
                limits = FakeSessionLimits(**kwargs)
                limits.events = events
                return limits

            async def skip_warmup() -> None:
                pass

            agent.build_session = lambda: session
            agent.build_agent = lambda: retrieval_agent
            agent.SessionLimits = build_limits
            agent.warm_moss_client_cache = skip_warmup

            await agent.run_retrieval_session(context)
            await context.shutdown_callbacks[0]("normal room shutdown")
            return events, context

        events, context = asyncio.run(run_scenario())

        self.assertTrue(context.shutdown_callbacks)
        self.assertEqual(
            events[:4],
            [
                "session.start",
                "limits.start",
                "ctx.add_shutdown_callback",
                (
                    "session.say",
                    "Parts counter, go ahead.",
                    {"allow_interruptions": True},
                ),
            ],
        )
        self.assertIn(("playout", "Parts counter, go ahead."), events)
        self.assertIn("limits.stop", events)

    def test_limit_callbacks_share_shutdown_that_closes_session_room_and_job(
        self,
    ) -> None:
        async def run_scenario() -> tuple[list[object], FakeSessionLimits]:
            agent = load_agent_module()
            events: list[object] = []
            session = FakeAgentSession(events)
            retrieval_agent = agent.PartsLineAgent()
            context = FakeContext(events)

            def build_limits(**kwargs):
                limits = FakeSessionLimits(**kwargs)
                limits.events = events
                return limits

            async def skip_warmup() -> None:
                pass

            agent.build_session = lambda: session
            agent.build_agent = lambda: retrieval_agent
            agent.SessionLimits = build_limits
            agent.warm_moss_client_cache = skip_warmup

            await agent.run_retrieval_session(context)
            limits = FakeSessionLimits.instances[0]
            self.assertIs(limits.on_idle_timeout, limits.on_max_duration)
            await limits.on_idle_timeout()
            return events, limits

        events, _ = asyncio.run(run_scenario())

        closing_sequence = [
            (
                "session.say",
                CLOSING_LINE,
                {"allow_interruptions": False},
            ),
            ("playout", CLOSING_LINE),
            "session.aclose",
            "room.disconnect",
        ]
        closing_start = events.index(closing_sequence[0])
        self.assertEqual(
            events[closing_start : closing_start + len(closing_sequence)],
            closing_sequence,
        )
        self.assertEqual(events[-1], ("ctx.shutdown", "session limits reached"))

    def test_limit_shutdown_closes_session_when_closing_line_playout_hangs(
        self,
    ) -> None:
        async def run_scenario() -> list[object]:
            agent = load_agent_module()
            agent.CLOSING_LINE_TIMEOUT_SECONDS = 0.01
            events: list[object] = []
            session = HangingClosingLineSession(events)
            context = FakeContext(events)

            await asyncio.wait_for(
                agent._shutdown_for_session_limits(session, context), timeout=0.2
            )
            return events

        events = asyncio.run(run_scenario())

        self.assertEqual(
            events,
            [
                (
                    "session.say",
                    CLOSING_LINE,
                    {"allow_interruptions": False},
                ),
                "session.aclose",
                "room.disconnect",
                ("ctx.shutdown", "session limits reached"),
            ],
        )

    def test_user_turn_completed_is_the_only_activity_reset_path(self) -> None:
        agent = load_agent_module()
        source = AGENT_MAIN.read_text(encoding="utf-8")
        retrieval_agent = agent.PartsLineAgent()
        limits = SimpleNamespace(record_user_activity=lambda: None)
        count = 0

        def record() -> None:
            nonlocal count
            count += 1

        limits.record_user_activity = record
        retrieval_agent.session_limits = limits

        asyncio.run(retrieval_agent.on_user_turn_completed(None, None))

        self.assertEqual(count, 1)
        self.assertEqual(source.count("record_user_activity()"), 1)

    def test_env_example_lists_session_limit_defaults(self) -> None:
        env_template = ENV_EXAMPLE.read_text(encoding="utf-8")

        self.assertIn("SESSION_IDLE_TIMEOUT_SECONDS=120", env_template)
        self.assertIn("SESSION_MAX_DURATION_SECONDS=900", env_template)
