"""Snowflake connector.

Reads rows from a Snowflake warehouse via ``snowflake-connector-python`` and
yields one ``DocumentInfo`` per row. Uses ``DictCursor`` so every row is a
plain dict keyed by column name.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import snowflake.connector
from moss import DocumentInfo
from snowflake.connector import DictCursor


def _load_private_key_bytes(path: str) -> bytes:
    """Load an unencrypted PKCS8 PEM private key and return DER bytes."""
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        load_pem_private_key,
    )

    with open(path, "rb") as fh:
        key = load_pem_private_key(fh.read(), password=None)
    return key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())


class SnowflakeConnector:
    """Run a SELECT against Snowflake and yield one ``DocumentInfo`` per row.

    ``mapper`` turns a row dict into a ``DocumentInfo``; the caller decides
    which columns become id, text, metadata, or embedding.
    """

    def __init__(
        self,
        account: str,
        user: str,
        warehouse: str,
        database: str,
        schema: str,
        query: str,
        mapper: Callable[[dict[str, Any]], DocumentInfo],
        password: str | None = None,
        private_key_path: str | None = None,
        role: str | None = None,
    ) -> None:
        if not password and not private_key_path:
            raise ValueError("Either 'password' or 'private_key_path' must be provided.")
        self.account = account
        self.user = user
        self.password = password
        self.private_key_path = private_key_path
        self.warehouse = warehouse
        self.database = database
        self.schema = schema
        self.query = query
        self.mapper = mapper
        self.role = role

    def __iter__(self) -> Iterator[DocumentInfo]:
        connect_kwargs: dict[str, Any] = {
            "account": self.account,
            "user": self.user,
            "warehouse": self.warehouse,
            "database": self.database,
            "schema": self.schema,
        }
        if self.private_key_path:
            connect_kwargs["private_key"] = _load_private_key_bytes(self.private_key_path)
        else:
            connect_kwargs["password"] = self.password
        if self.role is not None:
            connect_kwargs["role"] = self.role

        conn = snowflake.connector.connect(**connect_kwargs)
        try:
            cursor = conn.cursor(DictCursor)
            try:
                cursor.execute(self.query)
                for row in cursor:
                    yield self.mapper(row)
            finally:
                cursor.close()
        finally:
            conn.close()
