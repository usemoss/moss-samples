"""Seed the Moss index the voice agent queries.

Loads data/faqs.json into a Moss index so the agent has a knowledge base to
retrieve from. Run this once before starting the agent:

    python seed_index.py
"""

import asyncio
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from moss import MossClient, DocumentInfo

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("moss-seed")

MOSS_PROJECT_ID = os.getenv("MOSS_PROJECT_ID")
MOSS_PROJECT_KEY = os.getenv("MOSS_PROJECT_KEY")
INDEX_NAME = os.getenv("MOSS_INDEX_NAME", "demo-customer_faqs")

FAQS_PATH = Path(__file__).parent / "data" / "faqs.json"


async def main() -> None:
    if not MOSS_PROJECT_ID or not MOSS_PROJECT_KEY:
        raise SystemExit(
            "Missing MOSS_PROJECT_ID / MOSS_PROJECT_KEY. Copy .env.example to .env and fill them in."
        )

    faqs = json.loads(FAQS_PATH.read_text())
    docs = [
        DocumentInfo(
            id=f["id"],
            text=f["text"],
            metadata={"category": f.get("category", ""), "region": f.get("region", "all")},
        )
        for f in faqs
    ]

    client = MossClient(project_id=MOSS_PROJECT_ID, project_key=MOSS_PROJECT_KEY)

    logger.info(f"Creating index '{INDEX_NAME}' with {len(docs)} documents...")
    try:
        await client.create_index(INDEX_NAME, docs)
        logger.info("Index created. The agent can now answer from this knowledge base.")
    except Exception as e:
        logger.error(f"Failed to create index: {e}")
        logger.error(
            "If the index already exists, delete it in the Moss portal (or use a new "
            "MOSS_INDEX_NAME) and run this again."
        )
        raise


if __name__ == "__main__":
    asyncio.run(main())
