# moss-connector-snowflake

Snowflake source connector for Moss. It runs a SQL query against a Snowflake
warehouse and turns each returned row into a Moss `DocumentInfo`.

## Install

```bash
pip install moss-connector-snowflake
```

This package uses the official `snowflake-connector-python` driver.

## Usage

```python
import asyncio
from moss import DocumentInfo
from moss_connector_snowflake import SnowflakeConnector, ingest

async def main():
    source = SnowflakeConnector(
        account="xy12345.us-east-1",
        user="your_user",
        password="your_password",
        warehouse="COMPUTE_WH",
        database="MY_DB",
        schema="PUBLIC",
        query="SELECT id, title, body FROM articles",
        mapper=lambda row: DocumentInfo(
            id=str(row["ID"]),
            text=row["BODY"],
            metadata={"title": row["TITLE"]},
        ),
    )

    result = await ingest(
        source,
        project_id="your_project_id",
        project_key="your_project_key",
        index_name="articles",
    )
    print(f"copied {result.doc_count} rows")

asyncio.run(main())
```

Snowflake uppercases unquoted column names in result rows, so
`SELECT id, title, body ...` is typically mapped as `row["ID"]`,
`row["TITLE"]`, and `row["BODY"]`.

Use `auto_id=True` when your mapper does not have a stable primary key and you
want Moss to generate UUID document IDs.

## Layout

```text
src/
|-- __init__.py      # re-exports SnowflakeConnector and ingest
|-- connector.py     # SnowflakeConnector class
`-- ingest.py        # ingest() - keep in sync with the other connector packages
```

## Tests

```bash
pip install -e ".[dev]"
pytest tests/test_snowflake.py -v
pytest tests/test_integration_snowflake_moss.py -v -s
```

The integration test requires Snowflake and Moss credentials:

```bash
SNOWFLAKE_ACCOUNT=...
SNOWFLAKE_USER=...
SNOWFLAKE_PASSWORD=...
SNOWFLAKE_WAREHOUSE=...
SNOWFLAKE_DATABASE=...
SNOWFLAKE_SCHEMA=...
MOSS_PROJECT_ID=...
MOSS_PROJECT_KEY=...
```
