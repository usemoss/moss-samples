import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from moss import DocumentInfo, MossClient, MutationOptions, QueryOptions
from unstructured.chunking.title import chunk_by_title
from unstructured.partition.auto import partition

DEFAULT_MAX_CHARACTERS = 1_500
DEFAULT_NEW_AFTER_N_CHARS = 1_200
DEFAULT_COMBINE_UNDER_N_CHARS = 300
DEFAULT_JOB_POLL_INTERVAL = 2.0
DEFAULT_JOB_TIMEOUT = 300.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse files with Unstructured and index chunks into Moss."
    )
    parser.add_argument(
        "--input-dir",
        default="sample_docs",
        help="Directory containing PDFs, Word docs, HTML, images, or other files.",
    )
    parser.add_argument(
        "--index-name",
        default=os.getenv("MOSS_INDEX_NAME", "unstructured-docs"),
        help="Moss index name.",
    )
    parser.add_argument(
        "--query",
        help="Optional query to run after ingestion.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of Moss search results to return for --query.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of chunks to upsert per Moss request.",
    )
    return parser.parse_args()


def _stringify_metadata_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, sort_keys=True, default=str)


def _element_metadata(element: Any) -> dict[str, str]:
    metadata = getattr(element, "metadata", None)
    if hasattr(metadata, "to_dict"):
        raw = dict(metadata.to_dict())
    elif isinstance(metadata, dict):
        raw = dict(metadata)
    else:
        raw = {}

    raw.pop("orig_elements", None)
    return {
        str(key): _stringify_metadata_value(value)
        for key, value in raw.items()
        if value is not None
    }


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _stable_doc_id(relative_path: str, chunk_index: int) -> str:
    return f"{relative_path}::chunk-{chunk_index:04d}"


def _iter_files(input_dir: Path) -> list[Path]:
    return sorted(path for path in input_dir.rglob("*") if path.is_file())


def file_to_documents(path: Path, input_dir: Path) -> list[DocumentInfo]:
    relative_path = path.relative_to(input_dir).as_posix()
    elements = partition(filename=str(path))
    chunks = chunk_by_title(
        elements,
        max_characters=DEFAULT_MAX_CHARACTERS,
        new_after_n_chars=DEFAULT_NEW_AFTER_N_CHARS,
        combine_text_under_n_chars=DEFAULT_COMBINE_UNDER_N_CHARS,
    )

    docs: list[DocumentInfo] = []
    for chunk_index, chunk in enumerate(chunks):
        text = str(chunk).strip()
        if not text:
            continue

        metadata = _element_metadata(chunk)
        metadata.update(
            {
                "source_path": relative_path,
                "filename": path.name,
                "filetype": path.suffix.lower(),
                "chunk_index": str(chunk_index),
                "category": str(getattr(chunk, "category", chunk.__class__.__name__)),
                "text_hash": _text_hash(text),
            }
        )

        element_id = getattr(chunk, "id", None)
        if element_id:
            metadata["element_id"] = str(element_id)

        docs.append(
            DocumentInfo(
                id=_stable_doc_id(relative_path, chunk_index),
                text=text,
                metadata=metadata,
            )
        )

    return docs


def parse_documents(input_dir: Path) -> list[DocumentInfo]:
    docs: list[DocumentInfo] = []
    for path in _iter_files(input_dir):
        file_docs = file_to_documents(path, input_dir)
        docs.extend(file_docs)
        print(f"Parsed {path.relative_to(input_dir)} -> {len(file_docs)} chunks")
    return docs


def _batches(docs: list[DocumentInfo], batch_size: int) -> list[list[DocumentInfo]]:
    return [docs[i : i + batch_size] for i in range(0, len(docs), batch_size)]


async def _index_exists(client: MossClient, index_name: str) -> bool:
    try:
        await client.get_index(index_name)
        return True
    except RuntimeError:
        # The SDK currently uses RuntimeError for both a missing index and request
        # failures. Listing indexes gives us an unambiguous existence check without
        # depending on error-message text.
        indexes = await client.list_indexes()
        return any(index.name == index_name for index in indexes)


def _job_status_value(status: Any) -> str:
    value = getattr(status.status, "value", status.status)
    return str(value).upper()


async def _wait_for_job(
    client: MossClient,
    job_id: str,
    poll_interval: float = DEFAULT_JOB_POLL_INTERVAL,
    timeout: float = DEFAULT_JOB_TIMEOUT,
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    while True:
        status = await client.get_job_status(job_id)
        status_value = _job_status_value(status)
        if status_value == "COMPLETED":
            print(f"Job {job_id} completed")
            return
        if status_value == "FAILED":
            detail = getattr(status, "error", None) or "unknown error"
            raise RuntimeError(f"Moss job {job_id} failed: {detail}")
        if loop.time() >= deadline:
            raise TimeoutError(f"Moss job {job_id} did not finish within {timeout:g}s")
        await asyncio.sleep(poll_interval)


async def upsert_documents(
    client: MossClient,
    index_name: str,
    docs: list[DocumentInfo],
    batch_size: int,
) -> None:
    if not docs:
        print("No document chunks to index.")
        return

    batches = _batches(docs, batch_size)
    upsert_options = MutationOptions(upsert=True)

    if await _index_exists(client, index_name):
        print(f"Index '{index_name}' already exists; upserting chunks")
        start = 0
    else:
        result = await client.create_index(index_name, batches[0])
        print(f"Created index '{index_name}' with {len(batches[0])} chunks")
        await _wait_for_job(client, result.job_id)
        start = 1

    for batch_number, batch in enumerate(batches[start:], start=start + 1):
        result = await client.add_docs(index_name, batch, upsert_options)
        print(f"Upserted batch {batch_number}/{len(batches)} ({len(batch)} chunks)")
        await _wait_for_job(client, result.job_id)


async def main() -> None:
    load_dotenv()
    args = parse_args()
    if args.batch_size < 1:
        raise RuntimeError("--batch-size must be at least 1.")

    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")
    if not project_id or not project_key:
        raise RuntimeError("Set MOSS_PROJECT_ID and MOSS_PROJECT_KEY.")

    input_dir = Path(args.input_dir).expanduser().resolve()
    if not input_dir.is_dir():
        raise RuntimeError(f"Input directory not found: {input_dir}")

    docs = parse_documents(input_dir)
    print(f"\nPrepared {len(docs)} chunks from {input_dir}")

    client = MossClient(project_id, project_key)
    await upsert_documents(client, args.index_name, docs, args.batch_size)

    if args.query:
        await client.load_index(args.index_name)
        results = await client.query(
            args.index_name,
            args.query,
            QueryOptions(top_k=args.top_k, alpha=0.7),
        )

        print(f"\nQuery: {args.query}")
        if not results.docs:
            print("No results found.")
        for i, doc in enumerate(results.docs, 1):
            metadata = doc.metadata or {}
            source = metadata.get("source_path", "?")
            page = metadata.get("page_number")
            location = f"{source} page {page}" if page else source
            print(f"\n{i}. {location} (score={doc.score:.3f})")
            print(doc.text[:500])


if __name__ == "__main__":
    asyncio.run(main())
