"""CallOutcome schema for Step 4b and the Step 5 CALL_LOG contract.

CallOutcome.to_record() returns the JSON-ready shape that Step 5 persists:
call_id, started_at, vehicle, parts, set_aside, transfer, and outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Final, Literal, TypedDict, cast
from uuid import uuid4


PartResolution = Literal["quoted", "superseded_quoted"]
FinalOutcome = Literal["quoted", "set_aside", "transferred", "no_match", "abandoned"]

PART_RESOLUTIONS: Final = ("quoted", "superseded_quoted")
FINAL_OUTCOMES: Final = (
    "quoted",
    "set_aside",
    "transferred",
    "no_match",
    "abandoned",
)


class VehicleRecord(TypedDict, total=False):
    year: str
    make: str
    model: str
    engine: str
    trim: str


class PartOutcomeRecord(TypedDict):
    part_number: str
    name: str
    price: str
    stock: int
    resolution: PartResolution


class SetAsideRecord(TypedDict):
    first_name: str
    part_number: str
    quantity: int


class TransferRecord(TypedDict):
    reason: str
    context_summary: str


class CallOutcomeRecord(TypedDict):
    call_id: str
    started_at: str
    vehicle: VehicleRecord
    parts: list[PartOutcomeRecord]
    set_aside: SetAsideRecord | None
    transfer: TransferRecord | None
    outcome: FinalOutcome


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def empty_vehicle() -> VehicleRecord:
    return {}


def copy_vehicle(record: VehicleRecord) -> VehicleRecord:
    copied: VehicleRecord = {}
    if "year" in record:
        copied["year"] = record["year"]
    if "make" in record:
        copied["make"] = record["make"]
    if "model" in record:
        copied["model"] = record["model"]
    if "engine" in record:
        copied["engine"] = record["engine"]
    if "trim" in record:
        copied["trim"] = record["trim"]
    return copied


def copy_part(record: PartOutcomeRecord) -> PartOutcomeRecord:
    return {
        "part_number": record["part_number"],
        "name": record["name"],
        "price": record["price"],
        "stock": record["stock"],
        "resolution": record["resolution"],
    }


def copy_set_aside(record: SetAsideRecord) -> SetAsideRecord:
    return {
        "first_name": record["first_name"],
        "part_number": record["part_number"],
        "quantity": record["quantity"],
    }


def copy_transfer(record: TransferRecord) -> TransferRecord:
    return {
        "reason": record["reason"],
        "context_summary": record["context_summary"],
    }


def validate_resolution(resolution: str) -> PartResolution:
    if resolution not in PART_RESOLUTIONS:
        raise ValueError(f"unsupported part resolution: {resolution}")
    return cast(PartResolution, resolution)


def validate_outcome(outcome: str) -> FinalOutcome:
    if outcome not in FINAL_OUTCOMES:
        raise ValueError(f"unsupported final outcome: {outcome}")
    return cast(FinalOutcome, outcome)


@dataclass(slots=True)
class CallOutcome:
    call_id: str = field(default_factory=lambda: str(uuid4()))
    started_at: str = field(default_factory=utc_now_iso)
    vehicle: VehicleRecord = field(default_factory=empty_vehicle)
    parts: list[PartOutcomeRecord] = field(default_factory=list)
    set_aside: SetAsideRecord | None = None
    transfer: TransferRecord | None = None
    outcome: FinalOutcome = "abandoned"

    def record_vehicle(
        self,
        *,
        year: str,
        make: str,
        model: str,
        engine: str | None = None,
        trim: str | None = None,
    ) -> VehicleRecord:
        vehicle: VehicleRecord = {
            "year": year,
            "make": make,
            "model": model,
        }
        if engine:
            vehicle["engine"] = engine
        if trim:
            vehicle["trim"] = trim

        self.vehicle = vehicle
        return copy_vehicle(vehicle)

    def record_quoted_part(
        self,
        *,
        part_number: str,
        name: str,
        price: str,
        stock: int,
        resolution: PartResolution,
    ) -> PartOutcomeRecord:
        part: PartOutcomeRecord = {
            "part_number": part_number,
            "name": name,
            "price": price,
            "stock": stock,
            "resolution": validate_resolution(resolution),
        }
        self.parts.append(part)
        self.outcome = "quoted"
        return copy_part(part)

    def record_set_aside(
        self,
        *,
        first_name: str,
        part_number: str,
        quantity: int = 1,
    ) -> SetAsideRecord:
        if quantity < 1:
            raise ValueError("quantity must be at least 1")

        set_aside: SetAsideRecord = {
            "first_name": first_name,
            "part_number": part_number,
            "quantity": quantity,
        }
        self.set_aside = set_aside
        self.outcome = "set_aside"
        return copy_set_aside(set_aside)

    def record_transfer(
        self, *, reason: str, context_summary: str | None = None
    ) -> TransferRecord:
        transfer: TransferRecord = {
            "reason": reason,
            "context_summary": context_summary or self.context_summary(),
        }
        self.transfer = transfer
        self.outcome = "transferred"
        return copy_transfer(transfer)

    def set_final_outcome(self, outcome: FinalOutcome) -> None:
        self.outcome = validate_outcome(outcome)

    def context_summary(self) -> str:
        context = []
        vehicle = self.vehicle_summary()
        if vehicle:
            context.append(vehicle)
        if self.parts:
            part = self.parts[-1]
            context.append(f"{part['part_number']} {part['name']}")

        return "; ".join(context) or "No vehicle or part captured"

    def vehicle_summary(self) -> str:
        vehicle_parts = [
            self.vehicle.get("year"),
            self.vehicle.get("make"),
            self.vehicle.get("model"),
            self.vehicle.get("engine"),
            self.vehicle.get("trim"),
        ]
        return " ".join(part for part in vehicle_parts if part)

    def to_record(self) -> CallOutcomeRecord:
        return {
            "call_id": self.call_id,
            "started_at": self.started_at,
            "vehicle": copy_vehicle(self.vehicle),
            "parts": [copy_part(part) for part in self.parts],
            "set_aside": copy_set_aside(self.set_aside) if self.set_aside else None,
            "transfer": copy_transfer(self.transfer) if self.transfer else None,
            "outcome": self.outcome,
        }


__all__ = [
    "CallOutcome",
    "CallOutcomeRecord",
    "FinalOutcome",
    "PartOutcomeRecord",
    "PartResolution",
    "SetAsideRecord",
    "TransferRecord",
    "VehicleRecord",
]
