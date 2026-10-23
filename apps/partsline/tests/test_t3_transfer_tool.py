from __future__ import annotations

import unittest

from agent.outcome import CallOutcome
from agent.tools.transfer import HANDOFF_LINE, transfer_to_human


def outcome_with_context() -> CallOutcome:
    outcome = CallOutcome(
        call_id="call-123",
        started_at="2026-07-07T04:00:00+00:00",
    )
    outcome.record_vehicle(
        year="2014",
        make="Subaru",
        model="Outback",
        engine="2.5",
    )
    outcome.record_quoted_part(
        part_number="B-250",
        name="Serpentine Belt",
        price="22.50",
        stock=3,
        resolution="quoted",
    )
    return outcome


class T3TransferToolTest(unittest.TestCase):
    def test_transfer_records_context_emits_event_and_returns_handoff_signal(
        self,
    ) -> None:
        outcome = outcome_with_context()

        result = transfer_to_human(outcome, reason=" fleet pricing ")

        self.assertEqual(
            result,
            {
                "status": "transferred",
                "speak": HANDOFF_LINE,
                "transfer": {
                    "reason": "fleet pricing",
                    "context_summary": (
                        "2014 Subaru Outback 2.5; B-250 Serpentine Belt"
                    ),
                },
                "event": {
                    "name": "transfer",
                    "payload": {
                        "reason": "fleet pricing",
                        "context_summary": (
                            "2014 Subaru Outback 2.5; B-250 Serpentine Belt"
                        ),
                    },
                },
            },
        )
        self.assertEqual(outcome.to_record()["transfer"], result["transfer"])
        self.assertEqual(outcome.to_record()["outcome"], "transferred")

    def test_transfer_without_captured_context_still_emits_renderable_payload(
        self,
    ) -> None:
        outcome = CallOutcome(
            call_id="call-456",
            started_at="2026-07-07T04:15:00+00:00",
        )

        result = transfer_to_human(outcome, reason="returns or warranty")

        self.assertEqual(
            result["event"],
            {
                "name": "transfer",
                "payload": {
                    "reason": "returns or warranty",
                    "context_summary": "No vehicle or part captured",
                },
            },
        )
        self.assertEqual(outcome.to_record()["transfer"], result["transfer"])
        self.assertEqual(outcome.to_record()["outcome"], "transferred")

    def test_blank_reason_is_rejected_without_updating_outcome(self) -> None:
        outcome = outcome_with_context()

        with self.assertRaises(ValueError):
            transfer_to_human(outcome, reason=" ")

        self.assertIsNone(outcome.to_record()["transfer"])
        self.assertEqual(outcome.to_record()["outcome"], "quoted")
