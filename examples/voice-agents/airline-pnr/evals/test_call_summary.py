"""Unit tests for the call summary logic.

These cover the deterministic spine of the agent: state capture,
verification gating, summary shape. They do not exercise the LLM or
hit a live Moss index - that's what scenario tests are for.

Run from the example folder:

    uv run pytest evals/
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the agent module importable without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import (
    CallSessionData,
    ChangeRequest,
    _build_summary,
    _first_name_matches,
    _index_name_for,
)


@pytest.fixture
def call() -> CallSessionData:
    return CallSessionData(
        active_pnr="WJ7BNH",
        active_index="booking-wj7bnh",
        bookings_loaded=["WJ7BNH"],
        caller_verified=True,
    )


# -- index naming ------------------------------------------------------------


def test_index_name_lowercases_pnr():
    assert _index_name_for("WJ7BNH") == "booking-wj7bnh"


def test_index_name_handles_already_lowercased():
    assert _index_name_for("xkq4p2") == "booking-xkq4p2"


# -- first-name verification (security-critical, privacy gate) -------------


def test_first_name_matches_exact():
    assert _first_name_matches("Max", "Passenger of record: Max P Lee.") is True


def test_first_name_matches_case_insensitive():
    assert _first_name_matches("MAYA", "Passenger of record: Maya R Singh.") is True


def test_first_name_matches_rejects_single_letter():
    # Substring matching would have let "a" or "e" through against almost any record.
    assert _first_name_matches("a", "Passenger of record: Max P Lee.") is False
    assert _first_name_matches("e", "Passenger of record: Max P Lee.") is False


def test_first_name_matches_rejects_empty():
    assert _first_name_matches("", "Passenger of record: Max P Lee.") is False
    assert _first_name_matches("   ", "Passenger of record: Max P Lee.") is False


def test_first_name_matches_rejects_unrelated():
    assert _first_name_matches("Alice", "Passenger of record: Max P Lee.") is False


def test_first_name_matches_handles_record_punctuation():
    # The record text often has commas, periods, etc. The matcher must
    # still find the name as a clean token.
    assert _first_name_matches("Sam", "Passengers on this PNR: Sam J Park, adult.") is True


# -- summary shape -----------------------------------------------------------


def test_summary_has_required_top_level_keys(call):
    summary = _build_summary(call)
    for key in (
        "active_pnr",
        "bookings_loaded",
        "duration_sec",
        "caller_verified",
        "verification_attempts",
        "questions_asked",
        "change_requests",
        "notes",
        "schema_version",
    ):
        assert key in summary, f"summary missing key: {key}"


def test_summary_carries_change_requests(call):
    call.change_requests = [
        ChangeRequest(kind="seat", detail="prefers aisle row 12 or further back"),
        ChangeRequest(kind="meal", detail="switch to vegetarian"),
    ]
    summary = _build_summary(call)
    assert len(summary["change_requests"]) == 2
    assert summary["change_requests"][0]["kind"] == "seat"
    assert "aisle" in summary["change_requests"][0]["detail"]


def test_summary_records_multiple_bookings_touched(call):
    call.bookings_loaded = ["WJ7BNH", "MR5XBP"]
    summary = _build_summary(call)
    assert summary["bookings_loaded"] == ["WJ7BNH", "MR5XBP"]


def test_summary_duration_is_non_negative(call):
    summary = _build_summary(call)
    assert summary["duration_sec"] >= 0


def test_summary_records_verification_outcome():
    not_verified = CallSessionData(
        active_pnr="XKQ4P2",
        active_index="booking-xkq4p2",
        caller_verified=False,
        verification_attempts=3,
    )
    summary = _build_summary(not_verified)
    assert summary["caller_verified"] is False
    assert summary["verification_attempts"] == 3


def test_summary_with_no_pnr_loaded_still_emits():
    empty = CallSessionData()
    summary = _build_summary(empty)
    assert summary["active_pnr"] is None
    assert summary["bookings_loaded"] == []
    assert summary["change_requests"] == []
