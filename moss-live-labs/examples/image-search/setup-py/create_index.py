"""Creates a Moss index from a tiered COCO dataset JSON file.

Set MOSS_INDEX_TIER in .env to choose the tier (1k, 10k, 50k, 100k).
The index name will be "${MOSS_INDEX_NAME}-${tier}".
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from moss import DocumentInfo, MossClient

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

VALID_TIERS = ("1k", "10k", "50k", "100k")
DEFAULT_MODEL_ID = "moss-minilm"
ROOT_DIR = Path(__file__).resolve().parent.parent


def _get_data_file_path(tier: str) -> Path:
    """Return the path to the tiered COCO data file."""
    return ROOT_DIR / f"coco-data-{tier}.json"


def _get_index_name(base_name: str, tier: str) -> str:
    """Return the tier-qualified index name."""
    return f"{base_name}-{tier}"


def _load_documents(tier: str) -> list[DocumentInfo]:
    """Load documents from the tiered COCO JSON file."""
    data_path = _get_data_file_path(tier)
    if not data_path.exists():
        raise FileNotFoundError(
            f"Data file not found: {data_path}. Run download_coco.py first."
        )

    with data_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Data file must contain a JSON array.")

    documents: list[DocumentInfo] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        doc_id = entry.get("id")
        text = entry.get("text")
        if not doc_id or not text:
            continue
        metadata = entry.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            metadata = None
        documents.append(
            DocumentInfo(id=str(doc_id), text=str(text), metadata=metadata or {})
        )

    if not documents:
        raise ValueError("No valid documents loaded from the data file.")

    return documents


async def create_index_for_tier(tier: str) -> None:
    """Create a Moss index for the given tier."""
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")
    base_index_name = os.getenv("MOSS_INDEX_NAME")
    model_id = os.getenv("MOSS_MODEL_ID", DEFAULT_MODEL_ID)

    missing = [
        name
        for name, value in {
            "MOSS_PROJECT_ID": project_id,
            "MOSS_PROJECT_KEY": project_key,
            "MOSS_INDEX_NAME": base_index_name,
        }.items()
        if not value
    ]
    if missing:
        raise OSError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    documents = _load_documents(tier)
    index_name = _get_index_name(base_index_name, tier)

    client = MossClient(project_id, project_key)

    # Check if index already exists
    try:
        existing = await client.get_index(index_name)
        print(
            f"Index '{index_name}' already exists with {existing.doc_count} documents. "
            "Skipping creation."
        )
        return
    except RuntimeError:
        pass  # Index doesn't exist, proceed with creation

    print(f"Creating index '{index_name}' with {len(documents)} documents using {model_id}...")
    await client.create_index(index_name, documents, model_id)
    print(f"Index '{index_name}' created successfully.")


if __name__ == "__main__":
    tier = os.getenv("MOSS_INDEX_TIER", "1k")
    if tier not in VALID_TIERS:
        raise ValueError(f"Invalid tier: {tier}. Valid tiers: {', '.join(VALID_TIERS)}")
    asyncio.run(create_index_for_tier(tier))
