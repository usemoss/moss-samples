"""
Metadata filtering sample for the Moss Python SDK.

This example demonstrates querying with metadata filters on a locally loaded index.
"""

import asyncio
import os
from datetime import datetime
from typing import List

from dotenv import load_dotenv
from moss import DocumentInfo, MossClient, QueryOptions

# Load environment variables
load_dotenv()


async def metadata_filtering_sample() -> None:
    """Run metadata-filtered queries using eq, and, in, and near operators."""
    print("⭐ Moss Metadata Filtering Sample (Python) ⭐")

    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")

    if not project_id or not project_key:
        print("❌ Please set MOSS_PROJECT_ID and MOSS_PROJECT_KEY in .env file")
        print("Copy .env.template to .env and fill in your credentials")
        return

    client = MossClient(project_id, project_key)

    documents: List[DocumentInfo] = [
        DocumentInfo(
            id="doc1",
            text="Running shoes with breathable mesh for daily training.",
            metadata={
                "category": "shoes",
                "brand": "swiftfit",
                "price": "79",
                "city": "new-york",
                "location": "40.7580,-73.9855",
            },
        ),
        DocumentInfo(
            id="doc2",
            text="Trail running shoes built for rocky mountain terrain.",
            metadata={
                "category": "shoes",
                "brand": "peakstride",
                "price": "149",
                "city": "seattle",
                "location": "47.6062,-122.3321",
            },
        ),
        DocumentInfo(
            id="doc3",
            text="Lightweight city backpack with laptop compartment.",
            metadata={
                "category": "bags",
                "brand": "urbanpack",
                "price": "95",
                "city": "new-york",
                "location": "40.7505,-73.9934",
            },
        ),
    ]

    index_name = f"metadata-filter-sample-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    try:
        print("\n1. Creating index...")
        await client.create_index(index_name, documents)

        print("2. Loading index locally (required for filtering)...")
        await client.load_index(index_name)

        print("\n3. $eq filter: category == shoes")
        eq_filter = {"field": "category", "condition": {"$eq": "shoes"}}
        eq_results = await client.query(
            index_name,
            "running gear",
            QueryOptions(top_k=5, alpha=0.5, filter=eq_filter),
        )
        for item in eq_results.docs:
            print(f"- {item.id} | score={item.score:.3f} | metadata={item.metadata}")

        print("\n4. $and filter: shoes and price < 100")
        and_filter = {
            "$and": [
                {"field": "category", "condition": {"$eq": "shoes"}},
                {"field": "price", "condition": {"$lt": "100"}},
            ]
        }
        and_results = await client.query(
            index_name,
            "running shoes",
            QueryOptions(top_k=5, alpha=0.6, filter=and_filter),
        )
        for item in and_results.docs:
            print(f"- {item.id} | score={item.score:.3f} | metadata={item.metadata}")

        print("\n5. $in filter: city in [new-york]")
        in_filter = {"field": "city", "condition": {"$in": ["new-york"]}}
        in_results = await client.query(
            index_name,
            "city essentials",
            QueryOptions(top_k=5, filter=in_filter),
        )
        for item in in_results.docs:
            print(f"- {item.id} | score={item.score:.3f} | metadata={item.metadata}")

        print("\n6. $near filter: within 5km of Times Square")
        near_filter = {
            "field": "location",
            "condition": {"$near": "40.7580,-73.9855,5000"},
        }
        near_results = await client.query(
            index_name,
            "city products",
            QueryOptions(top_k=5, filter=near_filter),
        )
        for item in near_results.docs:
            print(f"- {item.id} | score={item.score:.3f} | metadata={item.metadata}")

        print("\n✅ Metadata filtering sample completed")
    finally:
        print("\n7. Cleaning up index...")
        await client.delete_index(index_name)


__all__ = ["metadata_filtering_sample"]


if __name__ == "__main__":
    asyncio.run(metadata_filtering_sample())
