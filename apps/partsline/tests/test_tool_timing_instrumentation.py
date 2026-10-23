from __future__ import annotations

import asyncio
import json
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AGENT_MAIN = ROOT / "agent" / "main.py"


def load_agent_module():
    spec = importlib.util.spec_from_file_location("partsline_agent_main", AGENT_MAIN)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_tool_timing(record: Any) -> dict[str, Any]:
    message = record.getMessage()
    assert message.startswith("partsline_tool_timing ")
    return json.loads(message.removeprefix("partsline_tool_timing "))


class ToolTimingInstrumentationTest(unittest.TestCase):
    def test_tool_wrappers_log_structured_timing_breakdowns(self) -> None:
        async def run_scenario() -> list[dict[str, Any]]:
            agent = load_agent_module()
            state = agent.PartsLineSessionState()
            state.call_outcome.record_quoted_part(
                part_number="A-100B",
                name="Engine Air Filter",
                price="8.49",
                stock=11,
                resolution="quoted",
            )
            ctx = SimpleNamespace(userdata=state)

            async def fake_lookup_part(**kwargs: object) -> dict[str, object]:
                return {"status": "no_match"}

            async def fake_emit_lookup_chip(*args: object, **kwargs: object) -> None:
                return None

            def fake_set_aside(*args: object, **kwargs: object) -> dict[str, object]:
                return {"status": "set_aside"}

            def fake_transfer_to_human(
                *args: object, **kwargs: object
            ) -> dict[str, object]:
                return {"status": "transferred"}

            agent.lookup_part = fake_lookup_part
            agent.emit_lookup_chip = fake_emit_lookup_chip
            agent.set_aside = fake_set_aside
            agent.transfer_to_human = fake_transfer_to_human

            with self.assertLogs(agent.LOGGER, level="INFO") as captured:
                await agent.lookup_part_for_session(
                    ctx,
                    part="air filter",
                    year="2014",
                    make="Subaru",
                    model="Outback",
                )
                await agent.set_aside_for_session(
                    ctx,
                    first_name="Mike",
                    part_number="A-100B",
                    quantity=2,
                )
                await agent.transfer_to_human_for_session(
                    ctx,
                    reason="fleet pricing",
                )

            return [parse_tool_timing(record) for record in captured.records]

        payloads = asyncio.run(run_scenario())

        self.assertEqual(
            [payload["tool_name"] for payload in payloads],
            ["lookup_part", "set_aside", "transfer_to_human"],
        )
        self.assertEqual(payloads[0]["result_status"], "no_match")
        self.assertEqual(
            set(payloads[0]["stages"]),
            {
                "lookup_part_seconds",
                "outcome_recording_seconds",
                "lookup_chip_emit_seconds",
            },
        )
        self.assertEqual(
            set(payloads[1]["stages"]),
            {
                "quote_lookup_seconds",
                "quantity_parse_seconds",
                "set_aside_seconds",
            },
        )
        self.assertEqual(
            set(payloads[2]["stages"]),
            {
                "outcome_access_seconds",
                "transfer_seconds",
            },
        )
        for payload in payloads:
            self.assertEqual(payload["event"], "partsline_tool_timing")
            self.assertIsInstance(payload["total_seconds"], float)
            self.assertGreaterEqual(payload["total_seconds"], 0.0)
            for seconds in payload["stages"].values():
                self.assertIsInstance(seconds, float)
                self.assertGreaterEqual(seconds, 0.0)
