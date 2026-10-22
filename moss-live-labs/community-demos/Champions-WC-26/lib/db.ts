import Database from "better-sqlite3";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import type { TournamentResult } from "./types";

const dataDir = join(process.cwd(), ".local-data");
mkdirSync(dataDir, { recursive: true });

const db = new Database(join(dataDir, "champions-wc26.sqlite"));
db.pragma("journal_mode = WAL");
db.exec(`
  CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    replaced_team TEXT NOT NULL,
    formation TEXT NOT NULL,
    champion INTEGER NOT NULL,
    perfect INTEGER NOT NULL,
    result_json TEXT NOT NULL
  )
`);

export function saveRun(result: TournamentResult) {
  const id = crypto.randomUUID().slice(0, 8);
  const stored = { ...result, id };
  db.prepare(`
    INSERT INTO runs (id, created_at, replaced_team, formation, champion, perfect, result_json)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).run(id, result.createdAt, result.replacedTeam, result.formation, result.champion ? 1 : 0, result.perfect ? 1 : 0, JSON.stringify(stored));
  return stored;
}

export function getRun(id: string): TournamentResult | null {
  const row = db.prepare("SELECT result_json FROM runs WHERE id = ?").get(id) as { result_json: string } | undefined;
  return row ? JSON.parse(row.result_json) : null;
}

export function getStats() {
  const row = db.prepare(`
    SELECT COUNT(*) AS runs,
      SUM(CASE WHEN champion = 1 THEN 1 ELSE 0 END) AS champions,
      SUM(CASE WHEN perfect = 1 THEN 1 ELSE 0 END) AS perfectRuns
    FROM runs
  `).get() as { runs: number; champions: number | null; perfectRuns: number | null };
  return { runs: row.runs, champions: row.champions ?? 0, perfectRuns: row.perfectRuns ?? 0 };
}
