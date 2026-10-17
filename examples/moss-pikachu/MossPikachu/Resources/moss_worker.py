#!/usr/bin/env python3
"""Picklight worker — line-delimited JSON protocol over stdin/stdout."""

from __future__ import annotations

import asyncio
import json
import os
import re
import resource
import shutil
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTENT_EXTENSIONS = {".md", ".txt", ".html", ".rtf", ".pdf", ".docx"}

# Avoid hanging the indexer on huge/corrupt documents.
MAX_CONTENT_BYTES = 8 * 1024 * 1024
MAX_PDF_PAGES = 40

CHUNK_CHARS = 1800
CHUNK_OVERLAP = 300
QUERY_CANDIDATE_TOP_K = 40
DEFAULT_ALPHA = 0.75

session = None
client = None
index_name = "local-files"
session_cache_path: str | None = None
session_loaded_from_disk = False
shutdown_requested = False


def log_stderr(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def log_memory(label: str) -> None:
    """Log peak resident memory (MB) for the worker process."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # macOS reports ru_maxrss in bytes; Linux reports kilobytes.
    if sys.platform == "darwin":
        mb = usage.ru_maxrss / (1024 * 1024)
    else:
        mb = usage.ru_maxrss / 1024
    log_stderr(f"[memory] {label}: {mb:.1f} MB peak RSS")


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, path: str) -> list[tuple[str, str, int]]:
    """Return list of (chunk_id, chunk_text, chunk_index)."""
    text = normalize_whitespace(text)
    if not text:
        return []
    if len(text) <= CHUNK_CHARS:
        return [(f"{path}#chunk-0000", text, 0)]

    chunks: list[tuple[str, str, int]] = []
    start = 0
    idx = 0
    while start < len(text):
        end = min(start + CHUNK_CHARS, len(text))
        piece = text[start:end].strip()
        if piece:
            chunks.append((f"{path}#chunk-{idx:04d}", piece, idx))
            idx += 1
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def enrich_chunk_body(filename: str, path: str, chunk_body: str) -> str:
    """Prepend filename/path so hybrid BM25 can match on names and folders."""
    return f"Filename: {filename}\nPath: {path}\n\n{chunk_body}"


def read_plain(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log_stderr(f"Failed to read {path}: {exc}")
        return None


def read_html(path: Path) -> str | None:
    raw = read_plain(path)
    if not raw:
        return None
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return soup.get_text(separator="\n")
    except Exception as exc:
        log_stderr(f"HTML parse failed {path}: {exc}")
        return raw


def read_pdf(path: Path) -> str | None:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts = []
        for index, page in enumerate(reader.pages):
            if index >= MAX_PDF_PAGES:
                log_stderr(f"PDF truncated to {MAX_PDF_PAGES} pages: {path}")
                break
            parts.append(page.extract_text() or "")
        return "\n".join(parts)
    except Exception as exc:
        log_stderr(f"PDF extract failed {path}: {exc}")
        return None


def read_docx(path: Path) -> str | None:
    try:
        from docx import Document

        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as exc:
        log_stderr(f"DOCX extract failed {path}: {exc}")
        return None


def read_file_text(path: str) -> str | None:
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in CONTENT_EXTENSIONS:
        return None

    try:
        size = p.stat().st_size
    except OSError as exc:
        log_stderr(f"Stat failed {path}: {exc}")
        return None

    if size > MAX_CONTENT_BYTES:
        log_stderr(f"Using metadata only for large file ({size} bytes): {path}")
        return None

    if ext in {".md", ".txt", ".rtf"}:
        return read_plain(p)
    if ext == ".html":
        return read_html(p)
    if ext == ".pdf":
        return read_pdf(p)
    if ext == ".docx":
        return read_docx(p)
    return None


def fallback_metadata_text(path: str) -> str:
    p = Path(path)
    ext = p.suffix.lower().lstrip(".") or "no extension"
    parent = str(p.parent)
    try:
        size = p.stat().st_size
    except OSError:
        size = 0
    return "\n".join(
        [
            f"Filename: {p.name}",
            f"Path: {path}",
            f"Folder: {parent}",
            f"File extension: {ext}",
            f"File size bytes: {size}",
        ]
    )


def file_mtime_iso(path: str) -> str:
    try:
        ts = Path(path).stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except OSError:
        return ""


async def ensure_client() -> None:
    global client
    if client is not None:
        return
    from moss import MossClient

    project_id = os.environ.get("MOSS_PROJECT_ID")
    project_key = os.environ.get("MOSS_PROJECT_KEY")
    if not project_id or not project_key:
        raise RuntimeError("MOSS_PROJECT_ID and MOSS_PROJECT_KEY must be set")

    client = MossClient(project_id, project_key)


def default_session_cache_path() -> str:
    return str(Path.home() / "Library" / "Application Support" / "Picklight" / "moss-session-cache")


async def ensure_session(
    name: str | None = None,
    *,
    cache_path: str | None = None,
) -> None:
    global session, index_name, session_cache_path, session_loaded_from_disk
    await ensure_client()
    if name:
        index_name = name
    if cache_path is not None:
        session_cache_path = cache_path or default_session_cache_path()
    if session is not None:
        return

    if session_cache_path is None:
        session_cache_path = default_session_cache_path()

    from moss.client.session_index import SessionIndex

    project_id = os.environ.get("MOSS_PROJECT_ID")
    project_key = os.environ.get("MOSS_PROJECT_KEY")
    if not project_id or not project_key:
        raise RuntimeError("MOSS_PROJECT_ID and MOSS_PROJECT_KEY must be set")

    log_memory("before session open")
    session = SessionIndex._create(
        name=index_name,
        model_id="moss-minilm",
        project_id=project_id,
        project_key=project_key,
    )

    loaded_count = 0
    session_loaded_from_disk = False
    try:
        log_stderr(f"Loading local session cache: {session_cache_path}/{index_name}")
        loaded_count = await asyncio.to_thread(session._inner.load_from_disk, session_cache_path)
        session_loaded_from_disk = loaded_count > 0
        if loaded_count > 0:
            session._model_id = session._inner.model_id
    except Exception as exc:
        log_stderr(f"No usable local session cache; starting empty: {exc}")

    if session._model_id != "custom":
        await session._get_embedding_service()

    log_memory("after session open")
    log_stderr(
        f"Session opened: {index_name} ({session.doc_count} docs, "
        f"disk_loaded={session_loaded_from_disk}, loaded_count={loaded_count})"
    )


async def handle_init_session(payload: dict[str, Any]) -> dict[str, Any]:
    name = payload.get("index_name", index_name)
    cache_path = payload.get("cache_path")
    await ensure_session(name, cache_path=cache_path)
    return {
        "status": "ok",
        "index": index_name,
        "doc_count": session.doc_count,
        "loaded_from_disk": session_loaded_from_disk,
        "cache_path": session_cache_path,
    }


async def handle_save_session(payload: dict[str, Any]) -> dict[str, Any]:
    global session_cache_path
    cache_path = payload.get("cache_path")
    if cache_path is not None:
        session_cache_path = cache_path or default_session_cache_path()
    await ensure_session(cache_path=session_cache_path)
    Path(session_cache_path or default_session_cache_path()).mkdir(parents=True, exist_ok=True)
    if session.doc_count == 0:
        cache_dir = Path(session_cache_path or default_session_cache_path()) / index_name
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        return {
            "status": "ok",
            "doc_count": 0,
            "cache_path": session_cache_path,
        }
    await asyncio.to_thread(session._inner.save_to_disk, session_cache_path)
    log_stderr(f"Saved local session cache: {session_cache_path}/{index_name} ({session.doc_count} docs)")
    return {
        "status": "ok",
        "doc_count": session.doc_count,
        "cache_path": session_cache_path,
    }


async def handle_add_docs(payload: dict[str, Any]) -> dict[str, Any]:
    from moss import DocumentInfo

    await ensure_session()
    files: list[str] = payload.get("files", [])
    log_memory(f"before add_docs ({len(files)} files)")
    docs = []
    files_indexed = 0
    files_skipped = 0
    file_chunk_counts: dict[str, int] = {}
    errors: list[str] = []

    for path in files:
        text = read_file_text(path)
        if not text:
            text = fallback_metadata_text(path)
        chunks = chunk_text(text, path)
        if not chunks:
            files_skipped += 1
            continue
        file_chunk_counts[path] = len(chunks)
        filename = Path(path).name
        ext = Path(path).suffix.lower().lstrip(".")
        mtime = file_mtime_iso(path)
        for chunk_id, chunk_body, chunk_idx in chunks:
            enriched = enrich_chunk_body(filename, path, chunk_body)
            docs.append(
                DocumentInfo(
                    id=chunk_id,
                    text=enriched,
                    metadata={
                        "path": path,
                        "filename": filename,
                        "chunk": str(chunk_idx),
                        "extension": ext,
                        "modified_at": mtime,
                    },
                )
            )
        files_indexed += 1

    if not docs:
        return {
            "status": "ok",
            "added": 0,
            "updated": 0,
            "chunks_indexed": 0,
            "files_indexed": files_indexed,
            "files_skipped": files_skipped + (len(files) - files_indexed - files_skipped),
            "file_chunk_counts": file_chunk_counts,
            "errors": errors,
        }

    try:
        added, updated = await session.add_docs(docs)
    except Exception as exc:
        errors.append(str(exc))
        raise

    log_memory(f"after add_docs ({len(docs)} chunks)")
    return {
        "status": "ok",
        "added": added,
        "updated": updated,
        "chunks_indexed": len(docs),
        "files_indexed": files_indexed,
        "files_skipped": len(files) - files_indexed,
        "file_chunk_counts": file_chunk_counts,
        "doc_count": session.doc_count,
        "errors": errors,
    }


async def handle_query(payload: dict[str, Any]) -> dict[str, Any]:
    from moss import ParentGrouping, QueryOptions

    await ensure_session()
    query_text = payload.get("query", "")
    top_k = int(payload.get("top_k", 12))
    alpha = float(payload.get("alpha", DEFAULT_ALPHA))
    candidate_top_k = max(top_k * 4, QUERY_CANDIDATE_TOP_K)
    group_by = ParentGrouping(parent_field="path", order_field="chunk")

    log_stderr(
        f"[query] q={query_text!r} top_k={top_k} candidates={candidate_top_k} "
        f"alpha={alpha:.2f} group_by=path"
    )
    log_memory("before query")
    start = time.perf_counter()
    grouped = True
    try:
        result = await session.query(
            query_text,
            QueryOptions(
                top_k=candidate_top_k,
                alpha=alpha,
                group_by=group_by,
            ),
        )
    except Exception as exc:
        # Older sessions may contain docs without the path/chunk metadata needed for grouping.
        grouped = False
        log_stderr(f"[query] grouped query failed, retrying without group_by: {exc}")
        result = await session.query(
            query_text,
            QueryOptions(
                top_k=candidate_top_k,
                alpha=alpha,
            ),
        )
    timing_ms = (time.perf_counter() - start) * 1000
    log_memory("after query")

    results = []
    for doc in result.docs[:top_k]:
        meta = doc.metadata or {}
        results.append(
            {
                "id": doc.id,
                "text": doc.text,
                "score": float(doc.score),
                "path": meta.get("path", doc.id.split("#chunk-")[0]),
                "filename": meta.get("filename", Path(meta.get("path", doc.id)).name),
            }
        )
    log_stderr(f"[query] returned {len(results)} results grouped={grouped}")
    return {
        "results": results,
        "timing_ms": timing_ms,
        "raw_count": len(result.docs),
        "grouped": grouped,
    }


async def handle_delete_docs(payload: dict[str, Any]) -> dict[str, Any]:
    await ensure_session()
    ids: list[str] = payload.get("ids", [])
    if not ids:
        return {"status": "ok", "deleted": 0}
    try:
        await session.delete_docs(ids)
    except Exception as exc:
        log_stderr(f"delete_docs partial failure: {exc}")
    return {"status": "ok", "deleted": len(ids), "doc_count": session.doc_count}


async def handle_clear_index(_: dict[str, Any]) -> dict[str, Any]:
    global session, session_loaded_from_disk
    await ensure_session()
    docs = await session.get_docs()
    if docs:
        await session.delete_docs([d.id for d in docs])
    if session_cache_path:
        cache_dir = Path(session_cache_path) / index_name
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
            log_stderr(f"Removed local session cache: {cache_dir}")
    session = None
    session_loaded_from_disk = False
    await ensure_session(index_name, cache_path=session_cache_path)
    return {"status": "ok", "doc_count": 0}


async def handle_ping(_: dict[str, Any]) -> dict[str, Any]:
    return {"status": "ok"}


async def handle_shutdown(_: dict[str, Any]) -> dict[str, Any]:
    global shutdown_requested
    shutdown_requested = True
    return {"status": "ok"}


HANDLERS = {
    "ping": handle_ping,
    "init_session": handle_init_session,
    "add_docs": handle_add_docs,
    "query": handle_query,
    "save_session": handle_save_session,
    "clear_index": handle_clear_index,
    "delete_docs": handle_delete_docs,
    "shutdown": handle_shutdown,
}


async def dispatch(line: str) -> dict[str, Any]:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid JSON: {exc}"}

    action = payload.get("action")
    if not action:
        return {"error": "Missing action"}

    handler = HANDLERS.get(action)
    if not handler:
        return {"error": f"Unknown action: {action}"}

    try:
        return await handler(payload)
    except Exception as exc:
        log_stderr(f"Handler error ({action}): {exc}")
        return {"error": str(exc)}


async def main_loop() -> None:
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while not shutdown_requested:
        try:
            line = await reader.readline()
        except Exception:
            break
        if not line:
            break
        decoded = line.decode("utf-8").strip()
        if not decoded:
            continue
        response = await dispatch(decoded)
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()
        if shutdown_requested:
            break


def handle_sigterm(*_: Any) -> None:
    global shutdown_requested
    shutdown_requested = True


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_sigterm)
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        pass
