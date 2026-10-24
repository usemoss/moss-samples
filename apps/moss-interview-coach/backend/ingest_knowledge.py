#!/usr/bin/env python3
"""Ingest interview rubrics into per-track Moss indexes.

By default ingests all tracks defined in tracks.py. Pass --track or --source
to ingest a single index. Creates/loads each index and runs a sample query.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from moss import DocumentInfo, MossClient, QueryOptions

from tracks import DEFAULT_TRACK_ID, INTERVIEW_TRACKS, normalize_track_id

DEFAULT_MODEL = "moss-minilm"


def _require_credentials() -> tuple[str, str]:
    project_id = os.getenv("MOSS_PROJECT_ID", "").strip()
    project_key = os.getenv("MOSS_PROJECT_KEY", "").strip()
    if not project_id or not project_key:
        print(
            "Missing MOSS_PROJECT_ID or MOSS_PROJECT_KEY. "
            "Copy backend/.env.example to backend/.env and fill in Moss credentials.",
            file=sys.stderr,
        )
        sys.exit(1)
    return project_id, project_key


def _documents_from_json(path: Path) -> list[DocumentInfo]:
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"JSON source must be a list of documents: {path}")
    if not raw:
        raise ValueError(f"JSON source has no documents: {path}")

    documents: list[DocumentInfo] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"Document at index {i} must be an object")
        raw_id = item.get("id")
        doc_id = raw_id if isinstance(raw_id, str) and raw_id.strip() else f"doc-{i}"
        if "text" not in item:
            raise ValueError(f"Document {doc_id} is missing required field 'text'")
        if not isinstance(item["text"], str):
            raise ValueError(
                f"Document {doc_id} field 'text' must be a string, "
                f"got {type(item['text']).__name__}"
            )
        title = item.get("title")
        if title is not None and not isinstance(title, str):
            raise ValueError(
                f"Document {doc_id} field 'title' must be a string, "
                f"got {type(title).__name__}"
            )
        title = (title or "").strip()
        text = item["text"].strip()
        if not text:
            raise ValueError(f"Document {doc_id} has empty text")
        body = f"{title}\n\n{text}".strip() if title else text
        metadata_raw = item.get("metadata")
        if metadata_raw is None:
            metadata: dict[str, str] = {}
        elif not isinstance(metadata_raw, dict):
            raise ValueError(f"Document {doc_id} metadata must be an object")
        else:
            metadata = {}
            for key, value in metadata_raw.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    raise ValueError(
                        f"Document {doc_id} metadata must be Dict[str, str]; "
                        f"invalid entry {key!r}: {type(value).__name__}"
                    )
                metadata[key] = value
        if title and "topic" not in metadata:
            metadata = {**metadata, "topic": title}
        documents.append(DocumentInfo(id=doc_id, text=body, metadata=metadata))
    return documents


def _documents_from_markdown_dir(path: Path) -> list[DocumentInfo]:
    md_files = sorted(path.glob("*.md"))
    if not md_files:
        raise ValueError(f"No .md files found in {path}")

    documents: list[DocumentInfo] = []
    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        documents.append(
            DocumentInfo(
                id=md_path.stem,
                text=text,
                metadata={"topic": md_path.stem, "source": md_path.name},
            )
        )
    if not documents:
        raise ValueError(f"All markdown files in {path} were empty")
    return documents


def load_documents(source: Path) -> list[DocumentInfo]:
    if not source.exists():
        raise FileNotFoundError(f"Source not found: {source}")
    if source.is_dir():
        return _documents_from_markdown_dir(source)
    if source.suffix.lower() == ".json":
        return _documents_from_json(source)
    raise ValueError(f"Unsupported source (use .json or a directory of .md): {source}")


def _is_index_conflict_error(exc: BaseException) -> bool:
    """True only for Moss duplicate-index conflicts; not auth/transport failures."""
    for attr in ("status_code", "status", "code"):
        val = getattr(exc, attr, None)
        if val == 409:
            return True
    msg = str(exc).lower()
    if "already exists" in msg and "index" in msg:
        return True
    return False


async def _delete_index_if_exists(client: MossClient, index_name: str) -> None:
    delete = getattr(client, "delete_index", None)
    if callable(delete):
        try:
            await delete(index_name)
            print(f"Deleted existing index '{index_name}'.")
        except Exception as exc:  # noqa: BLE001 — best-effort recreate
            print(f"Note: could not delete existing index ({exc}); create may fail if it exists.")


async def ingest_index(
    client: MossClient,
    *,
    index_name: str,
    source: Path,
    sample_query: str | None,
    recreate: bool,
) -> None:
    documents = load_documents(source)
    print(f"\n=== {index_name} ===")
    print(f"Loaded {len(documents)} document(s) from {source}")

    if recreate:
        await _delete_index_if_exists(client, index_name)

    try:
        await client.create_index(index_name, documents, DEFAULT_MODEL)
        print(f"Created index '{index_name}' with model '{DEFAULT_MODEL}'.")
    except Exception as exc:  # noqa: BLE001
        if _is_index_conflict_error(exc):
            print(
                f"Index '{index_name}' already exists. "
                "Re-run with --recreate to delete and rebuild, or load as-is.",
                file=sys.stderr,
            )
            if recreate:
                raise
        else:
            raise

    await client.load_index(index_name)
    print(f"Loaded index '{index_name}' into the local Moss runtime.")

    if not sample_query:
        print("Skipping sample query (pass --sample-query to run one).")
        return

    results = await client.query(
        index_name,
        sample_query,
        QueryOptions(top_k=1, alpha=0.6),
    )
    elapsed = getattr(results, "time_taken_ms", None)
    elapsed_str = f"{elapsed:.2f} ms" if isinstance(elapsed, (int, float)) else "n/a"
    print(f"Sample query: {sample_query}")
    print(f"Retrieval latency: {elapsed_str}")
    if results.docs:
        top = results.docs[0]
        preview = (top.text[:160] + "…") if len(top.text) > 160 else top.text
        print(f"Top hit [{top.id}] score={top.score:.3f}: {preview}")
    else:
        print("No documents returned.")


async def ingest_tracks(track_ids: list[str], *, recreate: bool) -> None:
    project_id, project_key = _require_credentials()
    client = MossClient(project_id, project_key)

    for track_id in track_ids:
        meta = INTERVIEW_TRACKS[track_id]
        await ingest_index(
            client,
            index_name=meta["index_name"],
            source=Path(meta["knowledge_file"]),
            sample_query=meta["sample_query"],
            recreate=recreate,
        )


async def ingest_source(
    source: Path,
    *,
    index_name: str,
    sample_query: str | None,
    recreate: bool,
) -> None:
    project_id, project_key = _require_credentials()
    client = MossClient(project_id, project_key)
    await ingest_index(
        client,
        index_name=index_name,
        source=source,
        sample_query=sample_query,
        recreate=recreate,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest interview rubrics into per-track Moss indexes.",
    )
    parser.add_argument(
        "--track",
        action="append",
        dest="tracks",
        choices=sorted(INTERVIEW_TRACKS.keys()),
        help="Ingest only this track (repeatable). Default: all tracks.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help=(
            "JSON file or markdown directory to ingest instead of the built-in "
            "rubrics. Destination index comes from --index-name, else from the "
            "single --track given, else the default track."
        ),
    )
    parser.add_argument(
        "--index-name",
        default=None,
        help="Index name when using --source (default: track index or system-design-rubric).",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete the index if it exists, then create it fresh.",
    )
    parser.add_argument(
        "--sample-query",
        default=None,
        help=(
            "Query to run after load. Built-in tracks use each track's default; "
            "with --source, omit to skip the sample query."
        ),
    )
    args = parser.parse_args(argv)
    # --track is repeatable, but --source writes to exactly one index. Silently
    # taking the first would make argument order decide the destination.
    if args.source is not None and args.tracks and len(args.tracks) > 1:
        parser.error(
            "--source ingests into a single index, so pass at most one --track "
            "(or use --index-name to name the destination explicitly)."
        )
    return args


def main() -> None:
    load_dotenv()
    args = parse_args()
    try:
        if args.source is not None:
            # --index-name still wins; otherwise fall back to the requested
            # track's index rather than always the default one, which would
            # write e.g. ML documents into the system-design index.
            track_id = normalize_track_id(args.tracks[0]) if args.tracks else DEFAULT_TRACK_ID
            track = INTERVIEW_TRACKS[track_id]
            index_name = args.index_name or track["index_name"]
            sample_query = args.sample_query
            asyncio.run(
                ingest_source(
                    args.source.resolve(),
                    index_name=index_name,
                    sample_query=sample_query,
                    recreate=args.recreate,
                )
            )
        else:
            track_ids = (
                [normalize_track_id(t) for t in args.tracks]
                if args.tracks
                else list(INTERVIEW_TRACKS.keys())
            )
            # Preserve declaration order from INTERVIEW_TRACKS.
            ordered = [tid for tid in INTERVIEW_TRACKS if tid in set(track_ids)]
            asyncio.run(ingest_tracks(ordered, recreate=args.recreate))
    except Exception as exc:  # noqa: BLE001
        print(f"Ingest failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
