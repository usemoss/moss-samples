"""Shared test corpus for reproducible benchmarks.

Documents are fetched from the Moss index specified by MOSS_INDEX_NAME so
that every system (Moss, Chroma, Pinecone, Qdrant) benchmarks against the
same real data.
"""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

QUERIES = [
    "neural network training data",
    "anomaly detection patterns",
    "computer vision image processing",
    "natural language processing",
    "reinforcement learning rewards",
    "transfer learning pretrained models",
    "distributed computing systems",
    "cryptographic data encryption",
    "database indexing performance",
    "knowledge graph entities",
    "generative adversarial networks",
    "attention mechanism transformers",
    "dimensionality reduction compression",
    "federated learning privacy",
    "stream processing pipelines",
]


def get_documents(count=100_000):
    """Fetch *count* documents from the Moss index."""
    docs = fetch_docs_from_moss()
    return docs[:count] if count < len(docs) else docs


def get_queries():
    """Return the fixed set of 15 test queries."""
    return list(QUERIES)


# ---------------------------------------------------------------------------
# Fetch real documents from a Moss index
# ---------------------------------------------------------------------------

def fetch_docs_from_moss():
    """Fetch all documents from the Moss index specified by MOSS_INDEX_NAME."""
    index_name = os.getenv("MOSS_INDEX_NAME")
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")

    if not all([index_name, project_id, project_key]):
        raise ValueError(
            "MOSS_INDEX_NAME, MOSS_PROJECT_ID, and MOSS_PROJECT_KEY must be set "
            "in .env to fetch docs from Moss"
        )

    return asyncio.run(
        _fetch_moss_docs(index_name, project_id, project_key)
    )


async def _fetch_moss_docs(index_name, project_id, project_key):
    from moss import MossClient

    client = MossClient(project_id, project_key)
    print(f"  Fetching docs from Moss index '{index_name}'...")
    moss_docs = await client.get_docs(index_name)
    print(f"  Fetched {len(moss_docs)} docs")
    return [
        {
            "id": d.id,
            "text": d.text,
            "metadata": dict(d.metadata) if d.metadata else {},
        }
        for d in moss_docs
    ]
