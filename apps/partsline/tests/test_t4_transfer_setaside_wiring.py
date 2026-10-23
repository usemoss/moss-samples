from __future__ import annotations

import asyncio
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent.outcome import CallOutcome


ROOT = Path(__file__).resolve().parents[1]
AGENT_MAIN = ROOT / "agent" / "main.py"
AGENT_PROMPTS = ROOT / "agent" / "prompts.py"


def load_agent_module():
    spec = importlib.util.spec_from_file_location("partsline_agent_main", AGENT_MAIN)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class T4TransferSetAsideWiringTest(unittest.TestCase):
    def test_prompt_adds_transfer_triggers_and_set_aside_flow(self) -> None:
        prompt_source = AGENT_PROMPTS.read_text(encoding="utf-8")

        for required_text in [
            "transfer_to_human",
            "modifications",
            "interchange",
            "returns or warranty",
            "fleet or commercial pricing",
            "Let me grab someone who can help with that, one moment",
            "set_aside",
            "first name",
            "offer to hold",
            "Done, I've set aside",
        ]:
            self.assertIn(required_text, prompt_source)

    def test_session_state_carries_call_outcome_for_tools(self) -> None:
        agent = load_agent_module()

        state = agent.PartsLineSessionState()

        self.assertIsInstance(state.call_outcome, CallOutcome)

    def test_registered_tools_include_lookup_set_aside_and_transfer(self) -> None:
        agent = load_agent_module()
        tool_names = [
            agent.LOOKUP_PART_TOOL.info.name,
            agent.SET_ASIDE_TOOL.info.name,
            agent.TRANSFER_TO_HUMAN_TOOL.info.name,
        ]

        self.assertEqual(tool_names, ["lookup_part", "set_aside", "transfer_to_human"])
        self.assertIn(
            "tools=[LOOKUP_PART_TOOL, SET_ASIDE_TOOL, TRANSFER_TO_HUMAN_TOOL]",
            AGENT_MAIN.read_text(encoding="utf-8"),
        )

    def test_set_aside_wrapper_updates_session_call_outcome(self) -> None:
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

        result = asyncio.run(
            agent.set_aside_for_session(
                ctx,
                first_name="Mike",
                part_number="A-100B",
                quantity=2,
            )
        )

        self.assertEqual(result["status"], "set_aside")
        self.assertEqual(
            state.call_outcome.to_record()["set_aside"],
            {"first_name": "Mike", "part_number": "A-100B", "quantity": 2},
        )

    def test_transfer_wrapper_updates_session_call_outcome(self) -> None:
        agent = load_agent_module()
        state = agent.PartsLineSessionState()
        state.call_outcome.record_vehicle(
            year="2014",
            make="Subaru",
            model="Outback",
            engine="2.5",
        )
        state.call_outcome.record_quoted_part(
            part_number="B-250",
            name="Serpentine Belt",
            price="22.50",
            stock=3,
            resolution="quoted",
        )
        ctx = SimpleNamespace(userdata=state)

        result = asyncio.run(
            agent.transfer_to_human_for_session(ctx, reason="fleet pricing")
        )

        self.assertEqual(result["status"], "transferred")
        self.assertEqual(result["event"]["name"], "transfer")
        self.assertEqual(
            state.call_outcome.to_record()["transfer"],
            {
                "reason": "fleet pricing",
                "context_summary": "2014 Subaru Outback 2.5; B-250 Serpentine Belt",
            },
        )
