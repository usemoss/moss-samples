from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CALL_LOG_READER = ROOT / "app" / "calls" / "callLog.ts"
CALLS_CLIENT = ROOT / "app" / "calls" / "CallsListClient.tsx"
CALLS_PAGE = ROOT / "app" / "calls" / "page.tsx"
CALLS_ROUTE = ROOT / "app" / "api" / "calls" / "route.ts"


class T6CallsPageStaticContractTest(unittest.TestCase):
    def test_calls_route_and_page_files_exist(self) -> None:
        self.assertTrue(CALL_LOG_READER.exists())
        self.assertTrue(CALLS_CLIENT.exists())
        self.assertTrue(CALLS_ROUTE.exists())
        self.assertTrue(CALLS_PAGE.exists())

    def test_web_reader_uses_read_only_sqlite_and_newest_first_order(self) -> None:
        source = CALL_LOG_READER.read_text(encoding="utf-8")

        self.assertIn('from "node:sqlite"', source)
        self.assertIn("DatabaseSync", source)
        self.assertIn("readOnly: true", source)
        self.assertIn("CALL_LOG_DB_PATH", source)
        self.assertIn('"data/calls.db"', source)
        self.assertIn("FROM CALL_LOG", source)
        self.assertIn("ORDER BY started_at DESC, call_id DESC", source)
        self.assertIn("JSON.parse", source)
        self.assertNotIn("INSERT", source)
        self.assertNotIn("UPDATE", source)
        self.assertNotIn("DELETE", source)

    def test_calls_api_returns_calls_from_reader(self) -> None:
        source = CALLS_ROUTE.read_text(encoding="utf-8")

        self.assertIn('export const runtime = "nodejs"', source)
        self.assertIn('export const dynamic = "force-dynamic"', source)
        self.assertIn("listCallLogRows", source)
        self.assertIn("export async function GET", source)
        self.assertIn("Response.json({ calls })", source)
        self.assertNotIn("export async function POST", source)

    def test_calls_page_mounts_client_list_component(self) -> None:
        source = CALLS_PAGE.read_text(encoding="utf-8")

        self.assertIn("CallsListClient", source)
        self.assertIn("export default function CallsPage", source)

    def test_calls_client_fetches_api_and_renders_required_row_fields(self) -> None:
        source = CALLS_CLIENT.read_text(encoding="utf-8")

        self.assertIn('"use client"', source)
        self.assertIn('fetch("/api/calls"', source)
        self.assertIn("formatVehicle", source)
        self.assertIn("formatParts", source)
        self.assertIn("formatOutcome", source)
        self.assertIn("call.started_at", source)
        self.assertIn("call.set_aside?.first_name", source)
        self.assertIn("calls.map", source)
        self.assertIn("No calls yet.", source)
