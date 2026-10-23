from __future__ import annotations

import asyncio
import json
import importlib.util
import unittest
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
                topic,
                reliable,
                destination_identities or [],
                json.loads(payload),
            )
        )


class FakeRoom:
    def __init__(self, events: list[object]) -> None:
        self.local_participant = FakeLocalParticipant(events)


class FakeRoomIO:
    def __init__(self, room: FakeRoom) -> None:
        self.room = room


class FakeSession:
    def __init__(self, room: FakeRoom) -> None:
        self.room_io = FakeRoomIO(room)


class FakeContext:
    def __init__(self, userdata: object, room: FakeRoom) -> None:
        self.userdata = userdata
        self.session = FakeSession(room)


class T3LookupChipEventsTest(unittest.TestCase):
    def test_ambiguous_lookup_emits_chip_with_candidate_engines(self) -> None:
        async def run_scenario() -> tuple[object, list[object]]:
            agent = load_agent_module()
            events: list[object] = []
            state = agent.PartsLineSessionState()
            ctx = FakeContext(state, FakeRoom(events))

            async def fake_lookup_part(**kwargs: object) -> dict[str, object]:
                self.assertEqual(
                    kwargs,
                    {
                        "part": "serpentine belt",
                        "year": "2014",
                        "make": "Subaru",
                        "model": "Outback",
                        "engine": None,
                        "trim": None,
                    },
                )
                return {
                    "status": "ambiguous",
                    "attribute": "engine",
                    "candidates": ["2.5", "3.6"],
                }

            agent.lookup_part = fake_lookup_part

            result = await agent.lookup_part_for_session(
                ctx,
                part="serpentine belt",
                year="2014",
                make="Subaru",
                model="Outback",
            )
            return result, events

        result, events = asyncio.run(run_scenario())

        self.assertEqual(
            result,
            {
                "status": "ambiguous",
                "attribute": "engine",
                "candidates": ["2.5", "3.6"],
            },
        )
        self.assertEqual(
            events,
            [
                (
                    "lookup_chip",
                    True,
                    [],
                    {
                        "filter": {
                            "year": "2014",
                            "make": "Subaru",
                            "model": "Outback",
                        },
                        "result": "ambiguous",
                        "parts": [],
                        "candidates": {
                            "attribute": "engine",
                            "values": ["2.5", "3.6"],
                        },
                    },
                )
            ],
        )
