from __future__ import annotations

import unittest

import agent.outcome as outcome_module
from agent.outcome import CallOutcome


class T1CallOutcomeTest(unittest.TestCase):
    def test_quote_then_set_aside_exports_step5_record_shape(self) -> None:
        outcome = CallOutcome(
            call_id="call-123",
            started_at="2026-07-07T04:00:00+00:00",
        )

        outcome.record_vehicle(
            year="2015",
            make="Toyota",
            model="Camry",
            engine="2.5",
        )
        outcome.record_quoted_part(
            part_number="A-100B",
            name="Engine Air Filter",
            price="8.49",
            stock=11,
            resolution="superseded_quoted",
        )
        outcome.record_set_aside(
            first_name="Mike",
            part_number="A-100B",
            quantity=2,
        )

        self.assertEqual(
            outcome.to_record(),
            {
                "call_id": "call-123",
                "started_at": "2026-07-07T04:00:00+00:00",
                "vehicle": {
                    "year": "2015",
                    "make": "Toyota",
                    "model": "Camry",
                    "engine": "2.5",
                },
                "parts": [
                    {
                        "part_number": "A-100B",
                        "name": "Engine Air Filter",
                        "price": "8.49",
                        "stock": 11,
                        "resolution": "superseded_quoted",
                    }
                ],
                "set_aside": {
                    "first_name": "Mike",
                    "part_number": "A-100B",
                    "quantity": 2,
                },
                "transfer": None,
                "outcome": "set_aside",
            },
        )

    def test_transfer_and_final_outcome_helpers_update_contract_fields(self) -> None:
        outcome = CallOutcome(
            call_id="call-456",
            started_at="2026-07-07T04:15:00+00:00",
        )

        outcome.record_vehicle(year="2014", make="Subaru", model="Outback")
        outcome.record_quoted_part(
            part_number="B-250",
            name="Serpentine Belt",
            price="22.50",
            stock=3,
            resolution="quoted",
        )
        transfer = outcome.record_transfer(reason="fleet pricing")

        self.assertEqual(
            transfer,
            {
                "reason": "fleet pricing",
                "context_summary": "2014 Subaru Outback; B-250 Serpentine Belt",
            },
        )
        self.assertEqual(outcome.to_record()["transfer"], transfer)
        self.assertEqual(outcome.to_record()["outcome"], "transferred")

        no_match = CallOutcome(
            call_id="call-789",
            started_at="2026-07-07T04:30:00+00:00",
        )
        no_match.set_final_outcome("no_match")

        self.assertEqual(no_match.to_record()["outcome"], "no_match")

    def test_schema_is_documented_for_step5_consumers(self) -> None:
        self.assertIn("CALL_LOG", outcome_module.__doc__ or "")
