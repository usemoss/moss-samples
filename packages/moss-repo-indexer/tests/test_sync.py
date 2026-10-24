"""Unit tests for sync and upload paths."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from moss_repo_indexer import MossCreds, SyncOptions, sync
from moss_repo_indexer.uploader import UploadOptions, upload_documents


def test_sync_dry_run(tmp_path: Path):
    (tmp_path / "a.py").write_text("def hello():\n    return 1\n")
    creds = MossCreds("pid", "pkey", "idx")

    async def run():
        with patch("moss_repo_indexer.uploader.MossClient") as client_cls:
            result = await sync(SyncOptions(source=str(tmp_path), creds=creds, dry_run=True))
            client_cls.assert_not_called()
            return result

    result = asyncio.run(run())
    assert result.dry_run is True
    assert result.mutation is None
    assert len(result.documents) >= 1
    assert result.repo_name == tmp_path.name


def test_upload_default_does_not_delete():
    from moss import DocumentInfo

    creds = MossCreds("pid", "pkey", "idx", model_name="moss-minilm")
    docs = [DocumentInfo(id="1", text="hello", metadata={"path": "a.py"})]
    client = AsyncMock()
    client.delete_index = AsyncMock()
    client.create_index = AsyncMock(return_value=type("R", (), {"doc_count": 1})())

    async def run():
        with patch("moss_repo_indexer.uploader.MossClient", return_value=client):
            return await upload_documents(docs, creds)

    result = asyncio.run(run())
    client.delete_index.assert_not_awaited()
    client.create_index.assert_awaited_once()
    assert result.doc_count == 1


def test_upload_replace():
    from moss import DocumentInfo

    creds = MossCreds("pid", "pkey", "idx", model_name="moss-minilm")
    docs = [DocumentInfo(id="1", text="hello", metadata={"path": "a.py"})]
    client = AsyncMock()
    client.delete_index = AsyncMock(side_effect=Exception("not found"))
    client.create_index = AsyncMock(return_value=type("R", (), {"doc_count": 1})())

    async def run():
        with patch("moss_repo_indexer.uploader.MossClient", return_value=client):
            return await upload_documents(docs, creds, UploadOptions(replace=True))

    result = asyncio.run(run())
    client.delete_index.assert_awaited_once()
    client.create_index.assert_awaited_once()
    assert result.doc_count == 1


def test_upload_upsert():
    from moss import DocumentInfo

    creds = MossCreds("pid", "pkey", "idx")
    docs = [DocumentInfo(id="1", text="hello")]
    client = AsyncMock()
    client.add_docs = AsyncMock(return_value=type("R", (), {"doc_count": 1})())

    async def run():
        with patch("moss_repo_indexer.uploader.MossClient", return_value=client):
            await upload_documents(docs, creds, UploadOptions(upsert=True))

    asyncio.run(run())
    options = client.add_docs.await_args.args[2]
    assert options.upsert is True
