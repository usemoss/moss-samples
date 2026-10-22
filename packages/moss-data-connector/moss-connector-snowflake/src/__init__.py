"""Snowflake source connector for Moss.

    from moss_connector_snowflake import SnowflakeConnector, ingest
"""

from .connector import SnowflakeConnector
from .ingest import ingest

__all__ = ["SnowflakeConnector", "ingest"]
