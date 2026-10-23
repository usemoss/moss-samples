"""
seed.py - builds the demo parts catalog and pushes it to Moss.
Run once:  python seed.py
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, TypedDict, cast

from dotenv import load_dotenv
from moss import DocumentInfo, MossClient


load_dotenv()

INDEX_NAME = "parts-catalog-test"
EMBEDDING_MODEL = "moss-minilm"
CATALOG_PATH = Path(__file__).resolve().parent / "catalog" / "demo_catalog.json"


class CatalogDocument(TypedDict):
    id: str
    text: str
    metadata: dict[str, str]


def _string_field(document: dict[str, Any], field: str, position: int) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"catalog document {position} must have a non-empty {field}")
    return value


def _metadata_field(document: dict[str, Any], position: int) -> dict[str, str]:
    metadata = document.get("metadata")
    if not isinstance(metadata, dict) or not metadata:
        raise ValueError(f"catalog document {position} must have metadata")

    normalized: dict[str, str] = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or not key:
            raise ValueError(
                f"catalog document {position} has a non-string metadata key"
            )
        if not isinstance(value, str):
            raise ValueError(
                f"catalog document {position} metadata {key!r} must be a string"
            )
        normalized[key] = value

    return normalized


def load_catalog_entries(path: Path = CATALOG_PATH) -> list[CatalogDocument]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("catalog must be a JSON object")

    documents = payload.get("documents")
    if not isinstance(documents, list):
        raise ValueError("catalog must contain a documents list")

    entries: list[CatalogDocument] = []
    seen_ids: set[str] = set()
    for position, raw_document in enumerate(documents, start=1):
        if not isinstance(raw_document, dict):
            raise ValueError(f"catalog document {position} must be a JSON object")

        document = cast(dict[str, Any], raw_document)
        document_id = _string_field(document, "id", position)
        if document_id in seen_ids:
            raise ValueError(f"duplicate catalog document id: {document_id}")
        seen_ids.add(document_id)

        entries.append(
            {
                "id": document_id,
                "text": _string_field(document, "text", position),
                "metadata": _metadata_field(document, position),
            }
        )

    return entries


def build_documents(path: Path = CATALOG_PATH) -> list[DocumentInfo]:
    return [
        DocumentInfo(id=entry["id"], text=entry["text"], metadata=entry["metadata"])
        for entry in load_catalog_entries(path)
    ]


def moss_credentials() -> tuple[str, str]:
    project_id = os.environ.get("MOSS_PROJECT") or os.environ.get("MOSS_PROJECT_ID")
    project_key = os.environ.get("MOSS_API_KEY") or os.environ.get("MOSS_PROJECT_KEY")
    if not project_id or not project_key:
        raise RuntimeError("Moss environment is not configured")
    return project_id, project_key


async def main() -> None:
    client = MossClient(*moss_credentials())
    docs = build_documents()
    print(f"Creating index '{INDEX_NAME}' with {len(docs)} docs...")
    await client.create_index(INDEX_NAME, docs, EMBEDDING_MODEL)
    print("Done. Index created.")


if __name__ == "__main__":
    asyncio.run(main())
