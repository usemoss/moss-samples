"""Standalone transfer helper for simulated human handoff."""

from __future__ import annotations

from typing import Literal, TypedDict

from agent.outcome import CallOutcome, TransferRecord


HANDOFF_LINE = "Let me grab someone who can help with that, one moment."


class TransferEvent(TypedDict):
    name: Literal["transfer"]
    payload: TransferRecord


class TransferResult(TypedDict):
    status: Literal["transferred"]
    speak: str
    transfer: TransferRecord
    event: TransferEvent


def normalize_reason(reason: str) -> str:
    normalized = " ".join(reason.strip().split())
    if not normalized:
        raise ValueError("reason is required")
    return normalized


def transfer_event_payload(transfer: TransferRecord) -> TransferEvent:
    return {
        "name": "transfer",
        "payload": {
            "reason": transfer["reason"],
            "context_summary": transfer["context_summary"],
        },
    }


def transfer_to_human(outcome: CallOutcome, reason: str) -> TransferResult:
    transfer = outcome.record_transfer(reason=normalize_reason(reason))
    return {
        "status": "transferred",
        "speak": HANDOFF_LINE,
        "transfer": transfer,
        "event": transfer_event_payload(transfer),
    }


__all__ = [
    "HANDOFF_LINE",
    "TransferEvent",
    "TransferResult",
    "transfer_event_payload",
    "transfer_to_human",
]
