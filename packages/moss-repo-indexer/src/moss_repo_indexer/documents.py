"""Build DocumentInfo lists from a resolved repository root."""

from __future__ import annotations

from pathlib import Path

from moss import DocumentInfo

from .chunkers import FileChunkRequest, chunk_code, chunk_markdown
from .discover import discover_files
from .language import is_markdown_path, language_for_path
from .types import IndexOptions


def build_documents(
    root: Path | str,
    options: IndexOptions | None = None,
) -> list[DocumentInfo]:
    """Discover files under `root`, chunk them, and return DocumentInfo rows."""
    resolved_root = Path(root).expanduser().resolve()
    opts = options or IndexOptions()
    documents: list[DocumentInfo] = []
    for path in discover_files(resolved_root, opts):
        documents.extend(_chunk_file(path, resolved_root, opts))
    return documents


def _chunk_file(path: Path, root: Path, options: IndexOptions) -> list[DocumentInfo]:
    content = _read_text(path)
    if content is None:
        return []
    request = FileChunkRequest(
        path=path,
        root=root,
        content=content,
        language=language_for_path(path),
        repo_name=options.repo_name,
        ref=options.ref,
    )
    if is_markdown_path(path):
        return chunk_markdown(request)
    return chunk_code(request)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
