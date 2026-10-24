# moss-repo-indexer

Clone or walk a repository, chunk **code** and **Markdown**, and build a searchable Moss index.

Python library (no CLI). TypeScript twin: [`@moss-tools/repo-indexer`](../moss-repo-indexer-js) — same document metadata contract.

## Install (editable)

```bash
cd packages/moss-repo-indexer
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```python
from pathlib import Path
from moss_repo_indexer import (
    MossCreds,
    SyncOptions,
    IndexOptions,
    build_documents,
    sync,
)

creds = MossCreds(
    project_id="...",
    project_key="...",
    index_name="my-codebase",
)

# Build DocumentInfo rows without uploading
docs = build_documents(Path("./my-repo"), IndexOptions())

# Dry-run (no Moss upload)
result = await sync(
    SyncOptions(
        source="./my-repo",  # or https://github.com/org/repo.git
        creds=creds,
        dry_run=True,
    )
)
print(len(result.documents), "chunks")

# Create index (fails if it already exists)
result = await sync(SyncOptions(source="./my-repo", creds=creds))

# Incremental upsert
result = await sync(SyncOptions(source="./my-repo", creds=creds, upsert=True))

# Destructive recreate (opt-in)
result = await sync(SyncOptions(source="./my-repo", creds=creds, replace=True))
```

## Example

```bash
PYTHONPATH=src python example/dry_run.py ./my-repo
```

## Document metadata contract

Shared with `@moss-tools/repo-indexer`. Every chunk is a Moss `DocumentInfo` with:

| Field | Meaning |
| --- | --- |
| `id` | Stable id, e.g. `path#symbol:start-end` |
| `text` | Search text (path/symbol prefix + chunk body) |
| `metadata.path` | Repo-relative path |
| `metadata.language` | e.g. `python`, `typescript`, `markdown` |
| `metadata.type` | `code` \| `markdown` \| `header` \| `text` \| `page` |
| `metadata.start_line` / `end_line` | 1-based line range (strings) |
| `metadata.symbol` | Optional symbol or heading |
| `metadata.navigation` | UI target, e.g. `src/foo.py:12` |
| `metadata.repo` / `ref` | Optional repo name and git ref |
| `metadata.title` | Display title |

Inspect keys via `metadata_contract()`.

## Environment

```bash
MOSS_PROJECT_ID=...
MOSS_PROJECT_KEY=...
```

## Layout

```text
src/moss_repo_indexer/
  types.py          # creds, options, metadata contract
  clone.py          # path / git URL resolution
  discover.py       # file walk + filters
  chunkers/         # markdown + code
  documents.py      # build_documents()
  uploader.py       # create_index / upsert
  sync.py           # end-to-end sync()
tests/
example/dry_run.py
```

## Tests

```bash
PYTHONPATH=src python -m pytest tests/ -q
```
