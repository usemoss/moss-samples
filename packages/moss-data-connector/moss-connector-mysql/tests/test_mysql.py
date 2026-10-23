"""Unit tests for the MySQL connector. No live MySQL needed — we mock
``pymysql.connect`` so the test runs anywhere pymysql is importable, and
we patch ``moss.MossClient`` inside ingest so no Moss network call is made.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("pymysql")

from moss import DocumentInfo  # noqa: E402
from moss_connector_mysql import MySQLConnector, ingest  # noqa: E402


@dataclass
class FakeMutationResult:
    doc_count: int
    job_id: str = "fake-job-id"
    index_name: str = ""


@dataclass
class FakeMossClient:
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def create_index(self, name, docs, model_id=None):
        docs = list(docs)
        self.calls.append({"name": name, "docs": docs, "model_id": model_id})
        return FakeMutationResult(doc_count=len(docs), index_name=name)


def _pymysql_mock_returning(rows: list[dict[str, Any]]) -> MagicMock:
    """Build a mock ``pymysql.connect(...)`` that returns *rows* from its cursor.

    The cursor is configured as an iterator (matching ``DictCursor`` behaviour),
    so ``for row in cursor:`` works naturally.
    """
    cursor = MagicMock()
    cursor.__iter__ = MagicMock(return_value=iter(rows))
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


async def test_mysql_ingest_end_to_end():
    rows_from_mysql = [
        {"id": 1, "title": "Refund policy", "body": "Refunds take 3–5 days."},
        {"id": 2, "title": "Shipping", "body": "We ship within 24 hours."},
        {"id": 3, "title": "Returns", "body": "Returns accepted within 30 days."},
    ]
    fake_conn = _pymysql_mock_returning(rows_from_mysql)
    fake_moss = FakeMossClient()

    with patch("moss_connector_mysql.connector.pymysql.connect", return_value=fake_conn), patch(
        "moss_connector_mysql.ingest.MossClient", return_value=fake_moss
    ):
        source = MySQLConnector(
            host="localhost",
            user="root",
            password="secret",
            database="shop",
            query="SELECT id, title, body FROM articles",
            mapper=lambda r: DocumentInfo(
                id=str(r["id"]),
                text=r["body"],
                metadata={"title": r["title"]},
            ),
        )
        result = await ingest(source, "fake_id", "fake_key", index_name="articles")

    assert result is not None
    assert result.doc_count == 3
    assert len(fake_moss.calls) == 1

    moss_docs = fake_moss.calls[0]["docs"]
    assert moss_docs[0].id == "1"
    assert moss_docs[0].text == "Refunds take 3–5 days."
    assert moss_docs[0].metadata == {"title": "Refund policy"}
    assert moss_docs[2].id == "3"


async def test_empty_result_skips_network_call():
    fake_conn = _pymysql_mock_returning([])
    fake_moss = FakeMossClient()

    with patch("moss_connector_mysql.connector.pymysql.connect", return_value=fake_conn), patch(
        "moss_connector_mysql.ingest.MossClient", return_value=fake_moss
    ):
        source = MySQLConnector(
            host="localhost",
            user="root",
            password="",
            database="empty_db",
            query="SELECT id, body FROM articles",
            mapper=lambda r: DocumentInfo(id=str(r["id"]), text=r["body"]),
        )
        result = await ingest(source, "fake_id", "fake_key", "empty")

    assert result is None
    assert fake_moss.calls == []


async def test_auto_id_defaults_to_false():
    rows_from_mysql = [
        {"id": 1, "title": "Refund policy", "body": "Refunds take 3 to 5 days."},
        {"id": 2, "title": "Shipping", "body": "We ship within 24 hours."},
    ]
    fake_conn = _pymysql_mock_returning(rows_from_mysql)
    fake_moss = FakeMossClient()

    with patch("moss_connector_mysql.connector.pymysql.connect", return_value=fake_conn), patch(
        "moss_connector_mysql.ingest.MossClient", return_value=fake_moss
    ):
        source = MySQLConnector(
            host="localhost",
            user="root",
            password="secret",
            database="shop",
            query="SELECT id, title, body FROM articles",
            mapper=lambda r: DocumentInfo(
                id=str(r["id"]),
                text=r["body"],
                metadata={"title": r["title"]},
            ),
        )
        await ingest(source, "fake_id", "fake_key", index_name="articles")

    docs = fake_moss.calls[0]["docs"]
    assert docs[0].id == "1"
    assert docs[1].id == "2"


async def test_auto_id_replaces_mapper_id():
    rows_from_mysql = [
        {"id": 1, "title": "Refund policy", "body": "Refunds take 3 to 5 days."},
        {"id": 2, "title": "Shipping", "body": "We ship within 24 hours."},
    ]
    fake_conn = _pymysql_mock_returning(rows_from_mysql)
    fake_moss = FakeMossClient()

    with patch("moss_connector_mysql.connector.pymysql.connect", return_value=fake_conn), patch(
        "moss_connector_mysql.ingest.MossClient", return_value=fake_moss
    ):
        source = MySQLConnector(
            host="localhost",
            user="root",
            password="secret",
            database="shop",
            query="SELECT id, title, body FROM articles",
            mapper=lambda r: DocumentInfo(
                id=str(r["id"]),
                text=r["body"],
                metadata={"title": r["title"]},
            ),
        )
        result = await ingest(
            source, "fake_id", "fake_key", index_name="articles", auto_id=True
        )

    assert result is not None
    docs = fake_moss.calls[0]["docs"]
    original_ids = {"1", "2"}
    for doc in docs:
        assert doc.id
        assert uuid.UUID(doc.id)
        assert doc.id not in original_ids
    assert [doc.text for doc in docs] == [
        "Refunds take 3 to 5 days.",
        "We ship within 24 hours.",
    ]
    assert [doc.metadata for doc in docs] == [
        {"title": "Refund policy"},
        {"title": "Shipping"},
    ]


async def test_port_and_charset_forwarded():
    """Verify that custom port and charset values are forwarded to pymysql.connect."""
    fake_conn = _pymysql_mock_returning([])
    patch_target = "moss_connector_mysql.connector.pymysql.connect"

    with patch(patch_target, return_value=fake_conn) as mock_connect:
        source = MySQLConnector(
            host="db.example.com",
            user="app",
            password="p@ss",
            database="prod",
            query="SELECT 1",
            mapper=lambda r: DocumentInfo(id="x", text="y"),
            port=3307,
            charset="latin1",
        )
        list(source)  # exhaust the iterator to trigger connect()

    mock_connect.assert_called_once()
    call_kwargs = mock_connect.call_args
    # pymysql.connect is called with keyword args
    assert call_kwargs.kwargs["port"] == 3307 or call_kwargs[1].get("port") == 3307
    assert call_kwargs.kwargs["charset"] == "latin1" or call_kwargs[1].get("charset") == "latin1"
