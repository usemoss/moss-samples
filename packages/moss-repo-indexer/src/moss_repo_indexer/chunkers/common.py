"""Shared helpers for building DocumentInfo chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from moss import DocumentInfo

from ..types import (
    METADATA_END_LINE,
    METADATA_LANGUAGE,
    METADATA_NAVIGATION,
    METADATA_PATH,
    METADATA_REF,
    METADATA_REPO,
    METADATA_START_LINE,
    METADATA_SYMBOL,
    METADATA_TITLE,
    METADATA_TYPE,
)


@dataclass
class FileChunkRequest:
    path: Path
    root: Path
    content: str
    language: str
    repo_name: str | None = None
    ref: str | None = None


@dataclass
class ChunkSlice:
    start_line: int
    end_line: int
    body: str
    chunk_type: str
    symbol: str
    title: str


def relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "section"


def make_document(request: FileChunkRequest, slice_: ChunkSlice) -> DocumentInfo:
    rel = relative_path(request.path, request.root)
    symbol = slice_.symbol
    chunk_id = _chunk_id(rel, symbol, slice_.start_line, slice_.end_line)
    prefix = f"{rel} :: {symbol}" if symbol else rel
    text = f"{prefix}\n\n{slice_.body}".strip()
    return DocumentInfo(id=chunk_id, text=text, metadata=_metadata(request, slice_, rel))


def _chunk_id(rel: str, symbol: str, start_line: int, end_line: int) -> str:
    if symbol:
        return f"{rel}#{slugify(symbol)}:{start_line}-{end_line}"
    return f"{rel}:{start_line}-{end_line}"


def _metadata(request: FileChunkRequest, slice_: ChunkSlice, rel: str) -> dict[str, str]:
    meta = {
        METADATA_PATH: rel,
        METADATA_LANGUAGE: request.language,
        METADATA_TYPE: slice_.chunk_type,
        METADATA_START_LINE: str(slice_.start_line),
        METADATA_END_LINE: str(slice_.end_line),
        METADATA_TITLE: slice_.title,
        METADATA_NAVIGATION: f"{rel}:{slice_.start_line}",
        METADATA_SYMBOL: slice_.symbol,
    }
    if request.repo_name:
        meta[METADATA_REPO] = request.repo_name
    if request.ref:
        meta[METADATA_REF] = request.ref
    return meta


def split_lines(content: str) -> list[str]:
    return content.splitlines()
