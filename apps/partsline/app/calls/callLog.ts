import { existsSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";

export type CallLogVehicle = {
  year?: string;
  make?: string;
  model?: string;
  engine?: string;
  trim?: string;
};

export type CallLogPart = {
  part_number: string;
  name: string;
  price?: string;
  stock?: number;
  resolution?: string;
};

export type CallLogSetAside = {
  first_name: string;
  part_number: string;
  quantity?: number;
};

export type CallLogTransfer = {
  reason: string;
  context_summary: string;
};

export type CallLogRow = {
  call_id: string;
  started_at: string;
  vehicle: CallLogVehicle;
  parts: CallLogPart[];
  set_aside: CallLogSetAside | null;
  transfer: CallLogTransfer | null;
  outcome: string;
};

type SqliteCallLogRow = {
  call_id: string;
  started_at: string;
  vehicle: string;
  parts: string;
  set_aside: string | null;
  transfer: string | null;
  outcome: string;
};

const DEFAULT_DB_PATH = "data/calls.db";

function callLogDbPath() {
  return process.env.CALL_LOG_DB_PATH || DEFAULT_DB_PATH;
}

function parseJsonField<T>(value: string): T {
  return JSON.parse(value) as T;
}

function optionalJsonField<T>(value: string | null): T | null {
  return value ? parseJsonField<T>(value) : null;
}

function rowToCall(row: SqliteCallLogRow): CallLogRow {
  return {
    call_id: row.call_id,
    started_at: row.started_at,
    vehicle: parseJsonField<CallLogVehicle>(row.vehicle),
    parts: parseJsonField<CallLogPart[]>(row.parts),
    set_aside: optionalJsonField<CallLogSetAside>(row.set_aside),
    transfer: optionalJsonField<CallLogTransfer>(row.transfer),
    outcome: row.outcome,
  };
}

export function listCallLogRows(): CallLogRow[] {
  const dbPath = callLogDbPath();
  if (!existsSync(dbPath)) {
    return [];
  }

  const db = new DatabaseSync(dbPath, { readOnly: true });
  try {
    const rows = db
      .prepare(
        `
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
        `,
      )
      .all() as SqliteCallLogRow[];

    return rows.map(rowToCall);
  } finally {
    db.close();
  }
}
