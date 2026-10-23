"""Pluggable text chunking for Moss.

Splitters are swappable; the shape of what they emit is not. Every strategy in
here yields chunks that carry a stable ID, declared position metadata, and the
SDK's own `DocumentInfo` — see `chunk.py` for why that contract is the point of
the package.

    from moss_chunking import SentenceSplitter, chunk_document, ingest

    docs = chunk_document(text, source="notes.md", strategy=SentenceSplitter())
    await ingest(docs, project_id, project_key, "my-index")
"""

from .chunk import (
    LOCATOR_TYPES,
    MAX_CHUNK_INDEX,
    RESERVED_KEYS,
    Chunk,
    LocatorType,
    chunk_id,
)
from .enrich import prepend_context, prepend_source_context
from .ingest import ingest, refresh_source
from .strategies import (
    CharSplitter,
    ChunkingStrategy,
    ParagraphSplitter,
    RecursiveSplitter,
    SentenceSplitter,
    chunk_document,
)

__all__ = [
    "LOCATOR_TYPES",
    "MAX_CHUNK_INDEX",
    "RESERVED_KEYS",
    "CharSplitter",
    "Chunk",
    "ChunkingStrategy",
    "LocatorType",
    "ParagraphSplitter",
    "RecursiveSplitter",
    "SentenceSplitter",
    "chunk_document",
    "chunk_id",
    "ingest",
    "prepend_context",
    "prepend_source_context",
    "refresh_source",
]
