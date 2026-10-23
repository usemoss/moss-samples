from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_MAIN = ROOT / "agent" / "main.py"
DEMO_CLIENT = ROOT / "app" / "PartsLineDemoClient.tsx"
CALLS_ROUTE = ROOT / "app" / "api" / "calls" / "route.ts"
CALLS_CLIENT = ROOT / "app" / "calls" / "CallsListClient.tsx"


class T7ProofLayerPathStaticContractTest(unittest.TestCase):
    def test_agent_persists_call_before_emitting_call_ended(self) -> None:
        source = AGENT_MAIN.read_text(encoding="utf-8")

        self.assertIn('"lookup_chip"', source)
        self.assertIn('"call_ended"', source)
        self.assertLess(
            source.index("save_call(outcome)"),
            source.index("await emit_call_ended(ctx.room, outcome)"),
        )

    def test_demo_transcript_renders_lookup_chips_and_call_end_handoff(self) -> None:
        source = DEMO_CLIENT.read_text(encoding="utf-8")

        self.assertIn("LOOKUP_CHIP_TOPIC", source)
        self.assertIn("CALL_ENDED_TOPIC", source)
        self.assertIn("parseLookupChipPayload", source)
        self.assertIn("parseCallEndedPayload", source)
        self.assertIn('kind: "lookup_chip"', source)
        self.assertIn('kind: "call_ended"', source)
        self.assertIn("RoomEvent.DataReceived", source)
        self.assertIn('item.kind === "call_ended"', source)
        self.assertIn("item.event.call_id", source)
        self.assertIn('href="/calls"', source)
        self.assertIn("View call log", source)

    def test_calls_page_reads_rows_through_api(self) -> None:
        route_source = CALLS_ROUTE.read_text(encoding="utf-8")
        client_source = CALLS_CLIENT.read_text(encoding="utf-8")

        self.assertIn("listCallLogRows", route_source)
        self.assertIn("Response.json({ calls })", route_source)
        self.assertIn('fetch("/api/calls"', client_source)
        self.assertIn("calls.map", client_source)
        self.assertIn("call.outcome", client_source)
        self.assertIn("call.set_aside?.first_name", client_source)
