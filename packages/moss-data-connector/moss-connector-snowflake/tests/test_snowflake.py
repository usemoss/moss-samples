"""Unit tests for the Snowflake connector.

No live Snowflake needed. ``snowflake.connector.connect`` is mocked, and
``MossClient`` is patched inside ingest so no Moss network call is made.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("snowflake.connector")

from moss import DocumentInfo  # noqa: E402
from moss_connector_snowflake import SnowflakeConnector, ingest  # noqa: E402
from snowflake.connector import DictCursor  # noqa: E402

CONNECT_TARGET = "moss_connector_snowflake.connector.snowflake.connector.connect"


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


def _snowflake_mock_returning(rows: list[dict[str, Any]]) -> tuple[MagicMock, MagicMock]:
    cursor = MagicMock()
    cursor.__iter__ = MagicMock(return_value=iter(rows))

    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


def _source(**kwargs: Any) -> SnowflakeConnector:
    defaults = {
        "account": "xy12345.us-east-1",
        "user": "app",
        "password": "secret",
        "warehouse": "COMPUTE_WH",
        "database": "MY_DB",
        "schema": "PUBLIC",
        "query": "SELECT id, title, body FROM articles",
        "mapper": lambda row: DocumentInfo(
            id=str(row["ID"]),
            text=row["BODY"],
            metadata={"title": row["TITLE"]},
        ),
    }
    defaults.update(kwargs)
    return SnowflakeConnector(**defaults)


async def test_snowflake_ingest_end_to_end():
    rows_from_snowflake = [
        {"ID": 1, "TITLE": "Refund policy", "BODY": "Refunds take 3-5 days."},
        {"ID": 2, "TITLE": "Shipping", "BODY": "We ship within 24 hours."},
        {"ID": 3, "TITLE": "Returns", "BODY": "Returns accepted within 30 days."},
    ]
    fake_conn, _ = _snowflake_mock_returning(rows_from_snowflake)
    fake_moss = FakeMossClient()

    with (
        patch(CONNECT_TARGET, return_value=fake_conn),
        patch("moss_connector_snowflake.ingest.MossClient", return_value=fake_moss),
    ):
        result = await ingest(_source(), "fake_id", "fake_key", index_name="articles")

    assert result is not None
    assert result.doc_count == 3
    assert len(fake_moss.calls) == 1

    moss_docs = fake_moss.calls[0]["docs"]
    assert moss_docs[0].id == "1"
    assert moss_docs[0].text == "Refunds take 3-5 days."
    assert moss_docs[0].metadata == {"title": "Refund policy"}
    assert moss_docs[2].id == "3"


async def test_empty_result_skips_network_call():
    fake_conn, _ = _snowflake_mock_returning([])
    fake_moss = FakeMossClient()

    with (
        patch(CONNECT_TARGET, return_value=fake_conn),
        patch("moss_connector_snowflake.ingest.MossClient", return_value=fake_moss),
    ):
        result = await ingest(_source(), "fake_id", "fake_key", "empty")

    assert result is None
    assert fake_moss.calls == []


async def test_connection_args_and_dict_cursor_forwarded():
    fake_conn, fake_cursor = _snowflake_mock_returning([])

    with patch(CONNECT_TARGET, return_value=fake_conn) as mock_connect:
        source = _source(role="ANALYST")
        list(source)

    mock_connect.assert_called_once_with(
        account="xy12345.us-east-1",
        user="app",
        password="secret",
        warehouse="COMPUTE_WH",
        database="MY_DB",
        schema="PUBLIC",
        role="ANALYST",
    )
    fake_conn.cursor.assert_called_once_with(DictCursor)
    fake_cursor.execute.assert_called_once_with("SELECT id, title, body FROM articles")


async def test_connection_role_omitted_when_none():
    fake_conn, _ = _snowflake_mock_returning([])

    with patch(CONNECT_TARGET, return_value=fake_conn) as mock_connect:
        list(_source())

    assert "role" not in mock_connect.call_args.kwargs


async def test_cursor_and_connection_close_on_mapper_failure():
    fake_conn, fake_cursor = _snowflake_mock_returning(
        [{"ID": 1, "TITLE": "Refund policy", "BODY": "Refunds take 3-5 days."}]
    )

    def broken_mapper(row: dict[str, Any]) -> DocumentInfo:
        raise RuntimeError(f"bad row: {row['ID']}")

    with patch(CONNECT_TARGET, return_value=fake_conn):
        source = _source(mapper=broken_mapper)
        with pytest.raises(RuntimeError, match="bad row: 1"):
            list(source)

    fake_cursor.close.assert_called_once()
    fake_conn.close.assert_called_once()


async def test_auto_id_replaces_mapper_id():
    rows_from_snowflake = [
        {"ID": 1, "TITLE": "T1", "BODY": "B1"},
        {"ID": 2, "TITLE": "T2", "BODY": "B2"},
    ]
    fake_conn, _ = _snowflake_mock_returning(rows_from_snowflake)
    fake_moss = FakeMossClient()

    with (
        patch(CONNECT_TARGET, return_value=fake_conn),
        patch("moss_connector_snowflake.ingest.MossClient", return_value=fake_moss),
    ):
        await ingest(_source(), "fake_id", "fake_key", index_name="articles", auto_id=True)

    docs = fake_moss.calls[0]["docs"]
    assert len(docs) == 2
    original_ids = {"1", "2"}
    for doc in docs:
        assert doc.id
        assert uuid.UUID(doc.id)
        assert doc.id not in original_ids
    assert [doc.text for doc in docs] == ["B1", "B2"]
    assert [doc.metadata for doc in docs] == [{"title": "T1"}, {"title": "T2"}]
