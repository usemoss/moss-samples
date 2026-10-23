from __future__ import annotations

import unittest

from agent.outcome import CallOutcome
from agent.tools.set_aside import set_aside


def outcome_with_quoted_part(*, stock: int = 11) -> CallOutcome:
    outcome = CallOutcome(
        call_id="call-123",
        started_at="2026-07-07T04:00:00+00:00",
    )
    outcome.record_quoted_part(
        part_number="A-100B",
        name="Engine Air Filter",
        price="8.49",
        stock=stock,
        resolution="quoted",
    )
    return outcome


class T2SetAsideToolTest(unittest.TestCase):
    def test_quoted_in_stock_part_records_hold_and_returns_confirmation(self) -> None:
        outcome = outcome_with_quoted_part()

        result = set_aside(
            outcome,
            first_name=" Mike ",
            part_number=" a-100b ",
            quantity=2,
        )

        self.assertEqual(
            result,
            {
                "status": "set_aside",
                "confirmation": (
                    "Done, I've set aside 2 of the A-100B under Mike. "
                    "They'll be at the counter."
                ),
                "set_aside": {
                    "first_name": "Mike",
                    "part_number": "A-100B",
                    "quantity": 2,
                },
            },
        )
        assert result["status"] == "set_aside"
        self.assertEqual(outcome.to_record()["set_aside"], result["set_aside"])
        self.assertEqual(outcome.to_record()["outcome"], "set_aside")

    def test_default_quantity_is_one(self) -> None:
        outcome = outcome_with_quoted_part()

        result = set_aside(outcome, first_name="Ada", part_number="A-100B")

        assert result["status"] == "set_aside"
        self.assertEqual(
            result["confirmation"],
            "Done, I've set aside 1 of the A-100B under Ada. They'll be at the counter.",
        )
        hold = outcome.to_record()["set_aside"]
        self.assertIsNotNone(hold)
        assert hold is not None
        self.assertEqual(hold["quantity"], 1)

    def test_zero_stock_part_is_rejected_without_updating_outcome(self) -> None:
        outcome = outcome_with_quoted_part(stock=0)

        result = set_aside(outcome, first_name="Mike", part_number="A-100B")

        self.assertEqual(
            result,
            {
                "status": "rejected",
                "reason": "A-100B is out of stock.",
            },
        )
        self.assertIsNone(outcome.to_record()["set_aside"])
        self.assertEqual(outcome.to_record()["outcome"], "quoted")

    def test_part_not_quoted_this_call_is_rejected(self) -> None:
        outcome = CallOutcome(
            call_id="call-456",
            started_at="2026-07-07T04:15:00+00:00",
        )
        outcome.set_final_outcome("no_match")

        result = set_aside(outcome, first_name="Mike", part_number="A-100B")

        self.assertEqual(
            result,
            {
                "status": "rejected",
                "reason": "A-100B was not quoted this call.",
            },
        )
        self.assertIsNone(outcome.to_record()["set_aside"])
        self.assertEqual(outcome.to_record()["outcome"], "no_match")

    def test_invalid_quantity_is_rejected_without_updating_outcome(self) -> None:
        outcome = outcome_with_quoted_part()

        result = set_aside(
            outcome,
            first_name="Mike",
            part_number="A-100B",
            quantity=0,
        )

        self.assertEqual(
            result,
            {
                "status": "rejected",
                "reason": "quantity must be at least 1.",
            },
        )
        self.assertIsNone(outcome.to_record()["set_aside"])
        self.assertEqual(outcome.to_record()["outcome"], "quoted")
