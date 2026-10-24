"""Heading-aware Markdown chunker."""

from __future__ import annotations

import re

from moss import DocumentInfo

from ..types import CHUNK_TYPE_HEADER, CHUNK_TYPE_PAGE, CHUNK_TYPE_TEXT
from .common import ChunkSlice, FileChunkRequest, make_document, relative_path, split_lines

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def chunk_markdown(request: FileChunkRequest) -> list[DocumentInfo]:
    lines = split_lines(request.content)
    docs = [_page_document(request)]
    sections = _parse_sections(lines, relative_path(request.path, request.root))
    for section in sections:
        docs.extend(_documents_for_section(request, section))
    return docs


def _page_document(request: FileChunkRequest) -> DocumentInfo:
    rel = relative_path(request.path, request.root)
    title = request.path.stem
    end_line = max(1, len(split_lines(request.content)))
    generated = make_document(
        request,
        ChunkSlice(
            start_line=1,
            end_line=end_line,
            body=title,
            chunk_type=CHUNK_TYPE_PAGE,
            symbol="",
            title=title,
        ),
    )
    return DocumentInfo(id=rel, text=generated.text, metadata=generated.metadata)


def _parse_sections(
    lines: list[str],
    fallback_title: str,
) -> list[tuple[str, int, int, str]]:
    """Return (heading, start_line, end_line, body) tuples."""
    sections: list[tuple[str, int, list[str]]] = []
    heading = fallback_title
    start = 1
    body: list[str] = []

    for index, line in enumerate(lines, start=1):
        match = _HEADING_RE.match(line)
        if match:
            _flush_section(sections, heading, start, body)
            heading = match.group(2).strip()
            start = index
            body = [line]
            continue
        body.append(line)

    _flush_section(sections, heading, start, body)
    return [(h, s, s + len(b) - 1, "\n".join(b).strip()) for h, s, b in sections if b]


def _flush_section(
    sections: list[tuple[str, int, list[str]]],
    heading: str,
    start: int,
    body: list[str],
) -> None:
    if body:
        sections.append((heading, start, list(body)))


def _documents_for_section(
    request: FileChunkRequest,
    section: tuple[str, int, int, str],
) -> list[DocumentInfo]:
    heading, start_line, end_line, body = section
    docs = [
        make_document(
            request,
            ChunkSlice(
                start_line=start_line,
                end_line=start_line,
                body=heading,
                chunk_type=CHUNK_TYPE_HEADER,
                symbol=heading,
                title=heading,
            ),
        )
    ]
    body_without_heading = _strip_leading_heading(body)
    if body_without_heading:
        docs.append(
            make_document(
                request,
                ChunkSlice(
                    start_line=start_line,
                    end_line=end_line,
                    body=body_without_heading,
                    chunk_type=CHUNK_TYPE_TEXT,
                    symbol=heading,
                    title=heading,
                ),
            )
        )
    return docs


def _strip_leading_heading(body: str) -> str:
    lines = body.splitlines()
    if lines and _HEADING_RE.match(lines[0]):
        return "\n".join(lines[1:]).strip()
    return body.strip()
