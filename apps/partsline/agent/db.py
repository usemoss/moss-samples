"""SQLite persistence for the append-only CALL_LOG table."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final, cast

from agent.outcome import (
    CallOutcome,
    CallOutcomeRecord,
    FinalOutcome,
    PartOutcomeRecord,
    SetAsideRecord,
    TransferRecord,
    VehicleRecord,
    validate_outcome,
)


DEFAULT_DB_PATH: Final = "data/calls.db"


def _resolve_db_path(db_path: str | os.PathLike[str] | None) -> Path:
    return Path(db_path or os.environ.get("CALL_LOG_DB_PATH") or DEFAULT_DB_PATH)


def _connect(db_path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    resolved = _resolve_db_path(db_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(resolved)
    connection.row_factory = sqlite3.Row
    _create_schema(connection)
    connection.commit()
    return connection


@contextmanager
def _managed_connection(
    db_path: str | os.PathLike[str] | None = None,
) -> Iterator[sqlite3.Connection]:
    connection = _connect(db_path)
    try:
        yield connection
    finally:
        connection.close()


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS CALL_LOG (
            call_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            vehicle TEXT NOT NULL,
            parts TEXT NOT NULL,
            set_aside TEXT,
            transfer TEXT,
            outcome TEXT NOT NULL
        )
        """
    )


def init_db(*, db_path: str | os.PathLike[str] | None = None) -> None:
    """Create the CALL_LOG table if it does not already exist."""
    with _managed_connection(db_path):
        pass


def _to_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _optional_json(value: Any | None) -> str | None:
    if value is None:
        return None
    return _to_json(value)


def save_call(
    outcome: CallOutcome, *, db_path: str | os.PathLike[str] | None = None
) -> None:
    """Append one completed call outcome to CALL_LOG."""
    record = outcome.to_record()
    with _managed_connection(db_path) as connection:
        with connection:
            connection.execute(
                """
                INSERT INTO CALL_LOG (
                    call_id,
                    started_at,
                    vehicle,
                    parts,
                    set_aside,
                    transfer,
                    outcome
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["call_id"],
                    record["started_at"],
                    _to_json(record["vehicle"]),
                    _to_json(record["parts"]),
                    _optional_json(record["set_aside"]),
                    _optional_json(record["transfer"]),
                    record["outcome"],
                ),
            )


def _load_json(value: str) -> Any:
    return json.loads(value)


def _row_to_record(row: sqlite3.Row) -> CallOutcomeRecord:
    set_aside = cast(str | None, row["set_aside"])
    transfer = cast(str | None, row["transfer"])
    outcome = cast(FinalOutcome, validate_outcome(cast(str, row["outcome"])))
    return {
        "call_id": cast(str, row["call_id"]),
        "started_at": cast(str, row["started_at"]),
        "vehicle": cast(VehicleRecord, _load_json(cast(str, row["vehicle"]))),
        "parts": cast(list[PartOutcomeRecord], _load_json(cast(str, row["parts"]))),
        "set_aside": (
            cast(SetAsideRecord, _load_json(set_aside)) if set_aside else None
        ),
        "transfer": cast(TransferRecord, _load_json(transfer)) if transfer else None,
        "outcome": outcome,
    }


def list_calls(
    *, db_path: str | os.PathLike[str] | None = None
) -> list[CallOutcomeRecord]:
    """Return persisted call outcomes newest-first."""
    with _managed_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                call_id,
                started_at,
                vehicle,
                parts,
                set_aside,
                transfer,
                outcome
            FROM CALL_LOG
            ORDER BY started_at DESC, call_id DESC
            """
        ).fetchall()
    return [_row_to_record(row) for row in rows]


__all__ = ["init_db", "list_calls", "save_call"]
