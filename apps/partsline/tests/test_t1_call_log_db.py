from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.db import list_calls, save_call
from agent.outcome import CallOutcome


class T1CallLogDbTest(unittest.TestCase):
    def test_save_call_appends_rows_and_lists_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "calls.db"
            first = CallOutcome(
                call_id="call-older",
                started_at="2026-07-07T04:00:00+00:00",
            )
            first.record_vehicle(
                year="2015",
                make="Toyota",
                model="Camry",
                engine="2.5",
            )
            first.record_quoted_part(
                part_number="A-100B",
                name="Engine Air Filter",
                price="8.49",
                stock=11,
                resolution="quoted",
            )
            first.record_set_aside(first_name="Mike", part_number="A-100B")

            save_call(first, db_path=db_path)
            persisted_first = list_calls(db_path=db_path)[0]

            first.record_transfer(
                reason="fleet pricing",
                context_summary="mutated after first save",
            )

            second = CallOutcome(
                call_id="call-newer",
                started_at="2026-07-07T04:15:00+00:00",
            )
            second.record_vehicle(year="2014", make="Subaru", model="Outback")
            second.set_final_outcome("no_match")

            save_call(second, db_path=db_path)

            self.assertEqual(
                list_calls(db_path=db_path),
                [
                    second.to_record(),
                    persisted_first,
                ],
            )
            self.assertIsNone(persisted_first["transfer"])
            self.assertEqual(persisted_first["outcome"], "set_aside")
