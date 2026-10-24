"""Moss repo indexer — chunk a codebase and upload it to Moss.

Public API (implementation filled in subsequent steps):

    from moss_repo_indexer import build_documents, sync, MossCreds, SyncOptions
"""

from __future__ import annotations

from moss import DocumentInfo

from .chunkers import FileChunkRequest, chunk_code, chunk_markdown
from .clone import ResolvedSource, resolve_source
from .discover import discover_files
from .documents import build_documents
from .sync import SyncResult, sync
from .types import (
    CHUNK_TYPE_CODE,
    CHUNK_TYPE_HEADER,
    CHUNK_TYPE_MARKDOWN,
    CHUNK_TYPE_PAGE,
    CHUNK_TYPE_TEXT,
    DEFAULT_EXCLUDE_DIRS,
    DEFAULT_INCLUDE_GLOBS,
    DEFAULT_MODEL_NAME,
    IndexOptions,
    MossCreds,
    SyncOptions,
    metadata_contract,
)
from .uploader import UploadOptions, upload_documents

__all__ = [
    "CHUNK_TYPE_CODE",
    "CHUNK_TYPE_HEADER",
    "CHUNK_TYPE_MARKDOWN",
    "CHUNK_TYPE_PAGE",
    "CHUNK_TYPE_TEXT",
    "DEFAULT_EXCLUDE_DIRS",
    "DEFAULT_INCLUDE_GLOBS",
    "DEFAULT_MODEL_NAME",
    "DocumentInfo",
    "FileChunkRequest",
    "IndexOptions",
    "MossCreds",
    "ResolvedSource",
    "SyncOptions",
    "SyncResult",
    "UploadOptions",
    "build_documents",
    "chunk_code",
    "chunk_markdown",
    "discover_files",
    "metadata_contract",
    "resolve_source",
    "sync",
    "upload_documents",
]
