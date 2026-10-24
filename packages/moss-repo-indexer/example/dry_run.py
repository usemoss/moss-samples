"""Dry-run a local path into Moss document chunks (no upload).

Usage:
  cd packages/moss-repo-indexer
  PYTHONPATH=src python example/dry_run.py [path]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running without install when SDK is missing: prefer installed moss.
try:
    from moss_repo_indexer import MossCreds, SyncOptions, sync
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from moss_repo_indexer import MossCreds, SyncOptions, sync


async def main() -> None:
    source = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[1])
    creds = MossCreds(
        project_id="unused-in-dry-run",
        project_key="unused-in-dry-run",
        index_name="repo-dry-run",
    )
    result = await sync(SyncOptions(source=source, creds=creds, dry_run=True))
    print(f"repo={result.repo_name} chunks={len(result.documents)} dry_run={result.dry_run}")
    for doc in result.documents[:5]:
        meta = doc.metadata or {}
        print(f"- {doc.id} [{meta.get('type')}] {meta.get('navigation')}")
    if len(result.documents) > 5:
        print(f"... and {len(result.documents) - 5} more")


if __name__ == "__main__":
    asyncio.run(main())
