"""Seed the pre-loaded travel catalog (the long-term cloud index).

The live session (what the traveler says on the call) is built at runtime by the
agent — it is NOT seeded here. Run once before starting the agent:

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
CATALOG_INDEX = os.getenv("TRAVEL_CATALOG_INDEX", "demo-travel-catalog")

CATALOG_PATH = Path(__file__).parent / "data" / "catalog.json"


async def main() -> None:
    if not MOSS_PROJECT_ID or not MOSS_PROJECT_KEY:
        raise SystemExit(
            "Missing MOSS_PROJECT_ID / MOSS_PROJECT_KEY. Copy .env.example to .env and fill them in."
        )

    trips = json.loads(CATALOG_PATH.read_text())
    docs = [DocumentInfo(id=t["id"], text=t["text"]) for t in trips]
    client = MossClient(project_id=MOSS_PROJECT_ID, project_key=MOSS_PROJECT_KEY)
    logger.info(f"Creating catalog index '{CATALOG_INDEX}' with {len(docs)} destinations...")
    try:
        await client.create_index(CATALOG_INDEX, docs)
        logger.info("Catalog ready.")
    except Exception as e:
        logger.error(f"Failed to create index: {e}")
        logger.error("If it already exists, delete it in the Moss portal (or change TRAVEL_CATALOG_INDEX) and retry.")
        raise


if __name__ == "__main__":
    asyncio.run(main())
