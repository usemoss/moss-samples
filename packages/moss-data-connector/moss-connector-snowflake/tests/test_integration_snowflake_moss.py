"""End-to-end integration test against real Snowflake and Moss projects.

This test creates a throwaway Snowflake table, ingests from it into a real Moss
index, queries the index, and cleans up afterwards. It is skipped unless
Snowflake and Moss credentials are set in the environment or a loaded .env file.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import pytest

# Load .env from the package dir, then the repo root, if present.
try:
    from dotenv import load_dotenv

    _here = Path(__file__).resolve()
    for candidate in (
        _here.parents[1] / ".env",
        _here.parents[2] / ".env",
        _here.parents[4] / ".env",
    ):
        if candidate.exists():
            load_dotenv(candidate, override=False)
except ImportError:
    pass

pytest.importorskip("snowflake.connector")

import snowflake.connector  # noqa: E402
from moss import DocumentInfo, MossClient, QueryOptions  # noqa: E402
from moss_connector_snowflake import SnowflakeConnector, ingest  # noqa: E402

SNOWFLAKE_ACCOUNT = os.getenv("SNOWFLAKE_ACCOUNT")
SNOWFLAKE_USER = os.getenv("SNOWFLAKE_USER")
SNOWFLAKE_PASSWORD = os.getenv("SNOWFLAKE_PASSWORD")
SNOWFLAKE_PRIVATE_KEY_PATH = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
SNOWFLAKE_WAREHOUSE = os.getenv("SNOWFLAKE_WAREHOUSE")
SNOWFLAKE_DATABASE = os.getenv("SNOWFLAKE_DATABASE")
SNOWFLAKE_SCHEMA = os.getenv("SNOWFLAKE_SCHEMA")
SNOWFLAKE_ROLE = os.getenv("SNOWFLAKE_ROLE")
PROJECT_ID = os.getenv("MOSS_PROJECT_ID")
PROJECT_KEY = os.getenv("MOSS_PROJECT_KEY")

_has_auth = bool(SNOWFLAKE_PASSWORD or SNOWFLAKE_PRIVATE_KEY_PATH)

pytestmark = pytest.mark.skipif(
    not (
        SNOWFLAKE_ACCOUNT
        and SNOWFLAKE_USER
        and _has_auth
        and SNOWFLAKE_WAREHOUSE
        and SNOWFLAKE_DATABASE
        and SNOWFLAKE_SCHEMA
        and PROJECT_ID
        and PROJECT_KEY
    ),
    reason=(
        "Set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD (or "
        "SNOWFLAKE_PRIVATE_KEY_PATH), SNOWFLAKE_WAREHOUSE, SNOWFLAKE_DATABASE, "
        "SNOWFLAKE_SCHEMA, MOSS_PROJECT_ID, and MOSS_PROJECT_KEY to run the real "
        "integration test."
    ),
)


def _load_private_key(path: str) -> bytes:
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        load_pem_private_key,
    )

    with open(path, "rb") as f:
        key = load_pem_private_key(f.read(), password=None)
    return key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())


def _snowflake_params() -> dict[str, Any]:
    params: dict[str, Any] = {
        "account": SNOWFLAKE_ACCOUNT,
        "user": SNOWFLAKE_USER,
        "warehouse": SNOWFLAKE_WAREHOUSE,
        "database": SNOWFLAKE_DATABASE,
        "schema": SNOWFLAKE_SCHEMA,
    }
    if SNOWFLAKE_PRIVATE_KEY_PATH:
        params["private_key"] = _load_private_key(SNOWFLAKE_PRIVATE_KEY_PATH)
    elif SNOWFLAKE_PASSWORD:
        params["password"] = SNOWFLAKE_PASSWORD
    if SNOWFLAKE_ROLE:
        params["role"] = SNOWFLAKE_ROLE
    return params


@pytest.fixture()
def snowflake_table():
    """Create a throwaway table with 5 recognisable rows, then drop it."""
    table_name = f"MOSS_TEST_{uuid.uuid4().hex[:8].upper()}"
    conn = snowflake.connector.connect(**_snowflake_params())
    try:
        cursor = conn.cursor()
        try:
            # Explicitly set session context — service users may have no defaults.
            if SNOWFLAKE_ROLE:
                cursor.execute(f"USE ROLE {SNOWFLAKE_ROLE}")
            cursor.execute(f"USE WAREHOUSE {SNOWFLAKE_WAREHOUSE}")
            cursor.execute(f"USE DATABASE {SNOWFLAKE_DATABASE}")
            cursor.execute(f"USE SCHEMA {SNOWFLAKE_SCHEMA}")
            cursor.execute(f"CREATE TABLE {table_name} (id INT, title STRING, body STRING)")

            cursor.executemany(
                f"INSERT INTO {table_name} (id, title, body) VALUES (%s, %s, %s)",
                [
                    (1, "Refund policy", "Refunds take 3 to 5 business days."),
                    (2, "Shipping time", "Orders ship within 24 hours."),
                    (3, "Contact support", "Reach support 24/7 via live chat."),
                    (4, "Password reset", "Click the link on the login page."),
                    (5, "Order tracking", "Tracking number sent by email."),
                ],
            )
        finally:
            cursor.close()
        yield table_name
    finally:
        cursor = conn.cursor()
        try:
            cursor.execute(f"USE DATABASE {SNOWFLAKE_DATABASE}")
            cursor.execute(f"USE SCHEMA {SNOWFLAKE_SCHEMA}")
            cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
        finally:
            cursor.close()
            conn.close()


async def test_snowflake_ingest_end_to_end(snowflake_table):
    """Full round trip: Snowflake -> Moss index -> query -> delete."""
    client = MossClient(PROJECT_ID, PROJECT_KEY)
    index_name = f"moss-snowflake-e2e-{uuid.uuid4().hex[:8]}"

    try:
        connector = SnowflakeConnector(
            account=SNOWFLAKE_ACCOUNT,
            user=SNOWFLAKE_USER,
            password=SNOWFLAKE_PASSWORD if not SNOWFLAKE_PRIVATE_KEY_PATH else None,
            private_key_path=SNOWFLAKE_PRIVATE_KEY_PATH,
            warehouse=SNOWFLAKE_WAREHOUSE,
            database=SNOWFLAKE_DATABASE,
            schema=SNOWFLAKE_SCHEMA,
            role=SNOWFLAKE_ROLE,
            query=f"SELECT id, title, body FROM {snowflake_table}",
            mapper=lambda row: DocumentInfo(
                id=str(row["ID"]),
                text=row["BODY"],
                metadata={"title": row["TITLE"]},
            ),
        )

        result = await ingest(connector, PROJECT_ID, PROJECT_KEY, index_name=index_name)
        assert result is not None
        assert result.doc_count == 5

        await client.load_index(index_name)
        result = await client.query(index_name, "how long do refunds take", QueryOptions(top_k=3))

        assert result.docs, "expected at least one document in the search result"
        top_ids = [doc.id for doc in result.docs]
        assert "1" in top_ids, f"refund-policy doc not in top 3: {top_ids}"

        refund_doc = next(doc for doc in result.docs if doc.id == "1")
        assert refund_doc.metadata is not None
        assert refund_doc.metadata.get("title") == "Refund policy"

    finally:
        try:
            await client.delete_index(index_name)
        except Exception as exc:  # pragma: no cover, best-effort cleanup
            print(f"warning: failed to delete test index {index_name}: {exc}")
