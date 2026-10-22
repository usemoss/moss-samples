# moss-data-connector

Folder holding the database-connector packages. Each subfolder is its own pip-installable package

## Layout

```
moss-data-connector/
├── _template/                  # copy-me starting point for a new connector
├── moss-connector-sqlite/      # SQLite source (stdlib, no driver)
├── moss-connector-mongodb/     # MongoDB source (requires pymongo)
├── moss-connector-mysql/       # MySQL / MariaDB source (requires pymysql)
├── moss-connector-supabase/    # Supabase source (requires supabase)
├── moss-connector-dynamodb/    # Amazon DynamoDB source (requires boto3)
├── moss-connector-huggingface/ # Hugging Face datasets source (requires datasets)
├── moss-connector-s3/          # Amazon S3 source + watch/re-index (requires boto3)
└── moss-connector-zeroentropy/ # ZeroEntropy source (requires zeroentropy)
```


## Caller shape

```python
from moss import DocumentInfo
from moss_connector_sqlite import SQLiteConnector, ingest

source = SQLiteConnector(
    database="my.db",
    query="SELECT id, title, body FROM articles",
    mapper=lambda r: DocumentInfo(id=str(r["id"]), text=r["body"], metadata={"title": r["title"]}),
)

await ingest(source, project_id="...", project_key="...", index_name="articles")
```

Use `auto_id=True` when your mapper does not have a stable primary key and you want Moss to generate UUID document IDs.


## Available connectors

| Package                                                    | Source        | Extra driver |
| ---------------------------------------------------------- | ------------- | ------------ |
| [`moss-connector-sqlite`](moss-connector-sqlite)           | SQLite        | —            |
| [`moss-connector-mongodb`](moss-connector-mongodb)         | MongoDB       | `pymongo`    |
| [`moss-connector-mysql`](moss-connector-mysql)             | MySQL         | `pymysql`    |
| [`moss-connector-supabase`](moss-connector-supabase)       | Supabase      | `supabase`   |
| [`moss-connector-dynamodb`](moss-connector-dynamodb)       | Amazon DynamoDB | `boto3`    |
| [`moss-connector-snowflake`](moss-connector-snowflake)     | Snowflake     | `snowflake-connector-python` |
| [`moss-connector-huggingface`](moss-connector-huggingface) | Hugging Face datasets | `datasets` |
| [`moss-connector-s3`](moss-connector-s3)                   | Amazon S3     | `boto3`      |
| [`moss-connector-zeroentropy`](moss-connector-zeroentropy) | ZeroEntropy   | `zeroentropy` |

## Adding a new connector

See [`_template/README.md`](_template/README.md).

