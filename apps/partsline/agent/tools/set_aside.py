"""Standalone set-aside helper for quoted, in-stock call outcomes."""

from __future__ import annotations

from typing import Literal, TypedDict

from agent.outcome import CallOutcome, PartOutcomeRecord, SetAsideRecord


class SetAsideSuccess(TypedDict):
    status: Literal["set_aside"]
    confirmation: str
    set_aside: SetAsideRecord


class SetAsideRejected(TypedDict):
    status: Literal["rejected"]
    reason: str


SetAsideResult = SetAsideSuccess | SetAsideRejected


def normalize_first_name(first_name: str) -> str:
    normalized = " ".join(first_name.strip().split())
    if not normalized:
        raise ValueError("first_name is required")
    return normalized.title()


def normalize_part_number(part_number: str) -> str:
    normalized = " ".join(part_number.strip().split()).upper()
    if not normalized:
        raise ValueError("part_number is required")
    return normalized


def find_quoted_part(
    outcome: CallOutcome, part_number: str
) -> PartOutcomeRecord | None:
    for part in outcome.parts:
        if part["part_number"].upper() == part_number:
            return part
    return None


def reject(reason: str) -> SetAsideRejected:
    return {
        "status": "rejected",
        "reason": reason,
    }


def set_aside(
    outcome: CallOutcome,
    first_name: str,
    part_number: str,
    quantity: int = 1,
) -> SetAsideResult:
    if quantity < 1:
        return reject("quantity must be at least 1.")

    normalized_name = normalize_first_name(first_name)
    normalized_part_number = normalize_part_number(part_number)
    quoted_part = find_quoted_part(outcome, normalized_part_number)

    if quoted_part is None:
        return reject(f"{normalized_part_number} was not quoted this call.")

    if quoted_part["stock"] <= 0:
        return reject(f"{normalized_part_number} is out of stock.")

    hold = outcome.record_set_aside(
        first_name=normalized_name,
        part_number=quoted_part["part_number"],
        quantity=quantity,
    )
    return {
        "status": "set_aside",
        "confirmation": (
            f"Done, I've set aside {quantity} of the "
            f"{quoted_part['part_number']} under {normalized_name}. "
            "They'll be at the counter."
        ),
        "set_aside": hold,
    }


__all__ = ["SetAsideResult", "SetAsideSuccess", "SetAsideRejected", "set_aside"]
