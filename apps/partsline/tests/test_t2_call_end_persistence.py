from __future__ import annotations

import asyncio
import json
import importlib.util
import unittest
from collections.abc import Awaitable, Callable, Generator
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_MAIN = ROOT / "agent" / "main.py"


def load_agent_module():
    spec = importlib.util.spec_from_file_location("partsline_agent_main", AGENT_MAIN)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeSpeechHandle:
    def __await__(self) -> Generator[None, None, "FakeSpeechHandle"]:
        async def wait_for_playout() -> FakeSpeechHandle:
            return self

        return wait_for_playout().__await__()


class FakeLocalParticipant:
    def __init__(self, events: list[object]) -> None:
        self._events = events

    def publish_data(
        self,
        payload: bytes | str,
        *,
        reliable: bool = True,
        destination_identities: list[str] | None = None,
        topic: str = "",
    ) -> None:
        self._events.append(
            (
                "publish_data",
                topic,
                reliable,
                destination_identities or [],
                json.loads(payload),
            )
        )


class FakeRoom:
    def __init__(self, events: list[object]) -> None:
        self.local_participant = FakeLocalParticipant(events)


class FakeAgentSession:
    def __init__(self, userdata: object) -> None:
        self.userdata = userdata

    async def start(self, **kwargs: object) -> None:
        pass

    def say(self, text: str, **kwargs: object) -> FakeSpeechHandle:
        return FakeSpeechHandle()


class FakeContext:
    def __init__(self, events: list[object]) -> None:
        self.room = FakeRoom(events)
        self.shutdown_callbacks: list[Callable[[str], Awaitable[None]]] = []

    def add_shutdown_callback(self, callback: Callable[[str], Awaitable[None]]) -> None:
        self.shutdown_callbacks.append(callback)


class T2CallEndPersistenceTest(unittest.TestCase):
    def test_shutdown_saves_outcome_then_emits_call_ended(self) -> None:
        async def run_scenario() -> list[object]:
            agent = load_agent_module()
            events: list[object] = []
            state = agent.PartsLineSessionState()
            session = FakeAgentSession(state)
            context = FakeContext(events)

            def fake_save_call(outcome) -> None:
                events.append(
                    (
                        "save_call",
                        outcome.call_id,
                        outcome.outcome,
                    )
                )

            agent.build_session = lambda: session
            agent.build_agent = agent.PartsLineAgent
            agent.save_call = fake_save_call

            async def skip_warmup() -> None:
                pass

            agent.warm_moss_client_cache = skip_warmup

            await agent.run_retrieval_session(context)
            state.call_outcome.call_id = "call-t2"
            state.call_outcome.set_final_outcome("no_match")
            await context.shutdown_callbacks[0]("normal room shutdown")
            return events

        self.assertEqual(
            asyncio.run(run_scenario()),
            [
                ("save_call", "call-t2", "no_match"),
                (
                    "publish_data",
                    "call_ended",
                    True,
                    [],
                    {"call_id": "call-t2", "outcome": "no_match"},
                ),
            ],
        )
