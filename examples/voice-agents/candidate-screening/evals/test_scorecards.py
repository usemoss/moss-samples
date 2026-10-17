"""Unit tests for the scorecard logic.

These tests don't need an LLM or a live Moss index - they verify the
deterministic parts of the agent: rubric capture, recommendation rules,
and scorecard JSON shape. Treat this as the "we don't ship vibes"
floor; expand with LLM-driven scenario tests separately.

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
    RubricEntry,
    ScreeningSessionData,
    _build_scorecard,
    _recommendation_from_rubric,
)


@pytest.fixture
def session() -> ScreeningSessionData:
    return ScreeningSessionData(
        candidate_id="c-test",
        role_id="senior-backend-payments",
        consent_to_record=True,
    )


def _entry(score: int, skill: str = "python", evidence: str = "ok") -> RubricEntry:
    return RubricEntry(score=score, skill=skill, evidence=evidence)


# -- recommendation rule -----------------------------------------------------


def test_advance_when_all_scores_strong():
    rubric = {f"skill_{i}": _entry(4 if i % 2 else 5) for i in range(5)}
    assert _recommendation_from_rubric(rubric) == "advance_to_technical"


def test_borderline_when_one_low_score():
    rubric = {
        "python":           _entry(4),
        "postgres":         _entry(4),
        "payments_domain":  _entry(2),
        "distributed":      _entry(3),
    }
    assert _recommendation_from_rubric(rubric) == "borderline_review"


def test_do_not_advance_when_multiple_lows():
    rubric = {
        "python":           _entry(2),
        "postgres":         _entry(2),
        "payments_domain":  _entry(1),
    }
    assert _recommendation_from_rubric(rubric) == "do_not_advance"


def test_no_signal_when_empty():
    assert _recommendation_from_rubric({}) == "no_signal"


# -- scorecard shape ---------------------------------------------------------


def test_scorecard_has_required_top_level_keys(session):
    session.rubric["python"] = _entry(4, "python", "Used asyncio in production for 3 years")
    card = _build_scorecard(session)
    for key in (
        "candidate_id",
        "role_id",
        "duration_sec",
        "rubric",
        "candidate_questions",
        "notes",
        "recommendation",
        "schema_version",
    ):
        assert key in card, f"scorecard missing key: {key}"


def test_scorecard_rubric_carries_evidence(session):
    session.rubric["postgres"] = _entry(
        5, "postgres", "Walked through serializable isolation tradeoffs unprompted"
    )
    card = _build_scorecard(session)
    assert card["rubric"]["postgres"]["score"] == 5
    assert "serializable" in card["rubric"]["postgres"]["evidence"]


def test_scorecard_recommendation_matches_rubric(session):
    session.rubric = {
        "python":          _entry(5),
        "postgres":        _entry(4),
        "payments_domain": _entry(5),
        "distributed":     _entry(4),
    }
    card = _build_scorecard(session)
    assert card["recommendation"] == "advance_to_technical"


def test_scorecard_duration_is_non_negative(session):
    card = _build_scorecard(session)
    assert card["duration_sec"] >= 0
