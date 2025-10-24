"""Utility script to create or refresh the Moss FAQ index.

Reads FAQ documents from ``faqs.json`` in this directory and uploads them to the Moss service
using credentials defined in ``.env``.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from inferedge_moss import DocumentInfo, MossClient

from settings import get_settings

# Load environment variables from the project .env file
load_dotenv(".env")

# Get configuration settings
settings = get_settings()

FAQ_PATH = Path(__file__).resolve().parent / settings.moss.data_path


def _load_faq_documents() -> List[DocumentInfo]:
    if not FAQ_PATH.exists():
        raise FileNotFoundError(
            f"FAQ data file not found at {FAQ_PATH}. Ensure the moss-sdk samples are present."
        )

    with FAQ_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, list):
        raise ValueError("FAQ data must be a list of document entries.")

    documents: List[DocumentInfo] = []
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
            DocumentInfo(
                id=str(doc_id),
                text=str(text),
                metadata=metadata or {},
            )
        )

    if not documents:
        raise ValueError("No valid FAQ documents were loaded from the JSON file.")

    return documents


async def create_faq_index() -> None:
    moss_config = settings.moss
    documents = _load_faq_documents()

    client = MossClient(
        os.environ["MOSS_PROJECT_ID"],
        os.environ["MOSS_PROJECT_KEY"]
    )

    print(
        f"Creating Moss index '{moss_config.index_name}' with {len(documents)} "
        f"FAQ entries using {moss_config.model_id}..."
    )
    created = await client.create_index(
        moss_config.index_name,
        documents,
        moss_config.model_id
    )
    print("Index creation response:", created)
    print("FAQ index ready for use!")


if __name__ == "__main__":
    asyncio.run(create_faq_index())
