"""Sliding-window code chunker with path/symbol context prefixes."""

from __future__ import annotations

import re

from moss import DocumentInfo

from ..types import CHUNK_TYPE_CODE
from .common import ChunkSlice, FileChunkRequest, make_document, split_lines

WINDOW_LINES = 60
OVERLAP_LINES = 15

_SYMBOL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_][\w]*)"),
    re.compile(r"^\s*class\s+([A-Za-z_][\w]*)"),
    re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][\w]*)"),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_][\w]*)\s*="),
    re.compile(r"^\s*func\s+([A-Za-z_][\w]*)"),
    re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_][\w]*)"),
]


def chunk_code(request: FileChunkRequest) -> list[DocumentInfo]:
    lines = split_lines(request.content)
    if not lines:
        return []
    docs: list[DocumentInfo] = []
    start = 1
    total = len(lines)
    while start <= total:
        end = min(start + WINDOW_LINES - 1, total)
        body = "\n".join(lines[start - 1 : end])
        symbol = _detect_symbol(lines[start - 1 : end])
        title = symbol or request.path.name
        docs.append(
            make_document(
                request,
                ChunkSlice(
                    start_line=start,
                    end_line=end,
                    body=body,
                    chunk_type=CHUNK_TYPE_CODE,
                    symbol=symbol or "",
                    title=title,
                ),
            )
        )
        if end >= total:
            break
        start = max(end - OVERLAP_LINES + 1, start + 1)
    return docs


def _detect_symbol(window_lines: list[str]) -> str | None:
    for line in window_lines:
        for pattern in _SYMBOL_PATTERNS:
            match = pattern.match(line)
            if match:
                return match.group(1)
    return None
