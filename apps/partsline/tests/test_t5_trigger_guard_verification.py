from __future__ import annotations

import unittest

from agent.outcome import CallOutcome
from agent.prompts import PARTSLINE_SYSTEM_PROMPT
from agent.tools.set_aside import set_aside
from agent.tools.transfer import transfer_to_human


def quoted_outcome(*, stock: int = 3) -> CallOutcome:
    outcome = CallOutcome(
        call_id="call-trigger-guard",
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
        stock=stock,
        resolution="quoted",
    )
    return outcome


class T5TriggerGuardVerificationTest(unittest.TestCase):
    def test_prompt_pins_each_transfer_trigger_to_transfer_tool(self) -> None:
        prompt = PARTSLINE_SYSTEM_PROMPT.lower()

        for trigger_phrase in [
            "vehicle modifications",
            "interchange / cross-reference",
            "returns/warranty",
            "fleet pricing",
        ]:
            self.assertIn(trigger_phrase, prompt)

        self.assertIn("never answer these trigger questions directly", prompt)
        self.assertIn("call transfer_to_human", prompt)
        self.assertIn(
            "let me grab someone who can help with that, one moment",
            prompt,
        )

    def test_transfer_trigger_paths_end_as_transferred(self) -> None:
        for reason in [
            "vehicle modifications",
            "interchange / cross-reference",
            "returns/warranty",
            "fleet pricing",
        ]:
            outcome = quoted_outcome()

            result = transfer_to_human(outcome, reason=reason)

            self.assertEqual(result["status"], "transferred")
            self.assertEqual(result["event"]["name"], "transfer")
            self.assertEqual(outcome.to_record()["outcome"], "transferred")
            transfer = outcome.to_record()["transfer"]
            self.assertIsNotNone(transfer)
            assert transfer is not None
            self.assertEqual(transfer["reason"], reason)

    def test_set_aside_guards_preserve_refused_outcomes(self) -> None:
        no_match = CallOutcome(
            call_id="call-no-match",
            started_at="2026-07-07T04:15:00+00:00",
        )
        no_match.set_final_outcome("no_match")

        no_match_result = set_aside(
            no_match,
            first_name="Mike",
            part_number="A-100B",
        )

        self.assertEqual(no_match_result["status"], "rejected")
        self.assertEqual(no_match.to_record()["outcome"], "no_match")
        self.assertIsNone(no_match.to_record()["set_aside"])

        zero_stock = quoted_outcome(stock=0)

        zero_stock_result = set_aside(
            zero_stock,
            first_name="Mike",
            part_number="B-250",
        )

        self.assertEqual(zero_stock_result["status"], "rejected")
        self.assertEqual(zero_stock.to_record()["outcome"], "quoted")
        self.assertIsNone(zero_stock.to_record()["set_aside"])
