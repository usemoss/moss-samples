"""
Multi-index search sample for the Moss Python SDK.

Demonstrates the v1.1.0 additions:

- `load_indexes` / `unload_indexes` for bulk lifecycle management
- `query_multi_index` for searching across multiple loaded indexes in one
  call, returning the global top-K with each result tagged by its source
  `index_name`

Notes:
    - All indexes participating in `query_multi_index` must be loaded
      locally and share the same embedding model.
    - `QueryOptions.alpha` works as in `query` (default 0.8): 1.0 is
      embedding-only, 0.0 is keyword-only, anything between is hybrid via
      Reciprocal Rank Fusion. Keyword scoring runs each index's own BM25 and
      merges the hits by score before fusion.
"""

import asyncio
import os
from datetime import datetime
from typing import List

from dotenv import load_dotenv

load_dotenv()

from moss import (
    DocumentInfo,
    LoadIndexesResult,
    MossClient,
    QueryOptions,
)


PRODUCT_DOCS: List[DocumentInfo] = [
    DocumentInfo(
        id="p1",
        text="Sony WH-1000XM5 wireless noise-cancelling headphones with 30-hour battery life.",
        metadata={"category": "electronics", "price": "399"},
    ),
    DocumentInfo(
        id="p2",
        text="Bose QuietComfort Ultra over-ear headphones, immersive audio and ANC.",
        metadata={"category": "electronics", "price": "429"},
    ),
    DocumentInfo(
        id="p3",
        text="Apple AirPods Max with H1 chip, spatial audio, premium leather ear cushions.",
        metadata={"category": "electronics", "price": "549"},
    ),
]

REVIEW_DOCS: List[DocumentInfo] = [
    DocumentInfo(
        id="r1",
        text="Battery on these wireless headphones easily lasts a 30-hour transatlantic week.",
        metadata={"product_id": "p1", "stars": "5"},
    ),
    DocumentInfo(
        id="r2",
        text="Comfortable for long flights but the noise cancelling could be stronger.",
        metadata={"product_id": "p2", "stars": "4"},
    ),
    DocumentInfo(
        id="r3",
        text="Sound quality is incredible but the battery degrades after a year of heavy use.",
        metadata={"product_id": "p3", "stars": "3"},
    ),
]

FAQ_DOCS: List[DocumentInfo] = [
    DocumentInfo(
        id="f1",
        text="How long does the battery last on wireless noise-cancelling headphones?",
        metadata={"topic": "battery"},
    ),
    DocumentInfo(
        id="f2",
        text="Do over-ear headphones support spatial audio for movies and games?",
        metadata={"topic": "audio"},
    ),
    DocumentInfo(
        id="f3",
        text="What is the warranty period for premium wireless headphones?",
        metadata={"topic": "warranty"},
    ),
]


async def main() -> None:
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")

    if not project_id or not project_key:
        print("Set MOSS_PROJECT_ID and MOSS_PROJECT_KEY in your environment.")
        return

    client = MossClient(project_id, project_key)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    products_index = f"sample-multi-products-{timestamp}"
    reviews_index = f"sample-multi-reviews-{timestamp}"
    faqs_index = f"sample-multi-faqs-{timestamp}"

    all_indexes = [products_index, reviews_index, faqs_index]

    try:
        print("1. Creating three indexes with related but distinct content...")
        await asyncio.gather(
            client.create_index(products_index, PRODUCT_DOCS),
            client.create_index(reviews_index, REVIEW_DOCS),
            client.create_index(faqs_index, FAQ_DOCS),
        )
        print(f"   created: {all_indexes}")

        print("\n2. Bulk-loading all three with load_indexes...")
        load_result: LoadIndexesResult = await client.load_indexes(all_indexes)
        print(f"   loaded: {load_result.loaded}")
        print(f"   failed: {load_result.failed}")

        print("\n3. Querying across all three indexes in one call.")
        print("   Each result is tagged with its source index_name.")
        results = await client.query_multi_index(
            all_indexes,
            "wireless headphones battery life",
            QueryOptions(top_k=6),
        )
        print(f'\n   Query: "{results.query}"')
        print(f"   Returned {len(results.docs)} docs (global top-K across indexes):\n")
        for i, doc in enumerate(results.docs, 1):
            preview = doc.text[:70] + "..." if len(doc.text) > 70 else doc.text
            print(f"   {i}. [{doc.index_name}] [{doc.id}] score={doc.score:.3f}")
            print(f"      {preview}")

        print("\n4. options.alpha picks the signal mix, as in single-index query.")
        print("   alpha=0.0 is keyword-only (BM25 per index, merged), 1.0 is")
        print("   embedding-only, and the default 0.8 blends both with RRF:")
        keyword_only = await client.query_multi_index(
            all_indexes,
            "wireless headphones battery life",
            QueryOptions(top_k=6, alpha=0.0),
        )
        embedding_only = await client.query_multi_index(
            all_indexes,
            "wireless headphones battery life",
            QueryOptions(top_k=6, alpha=1.0),
        )
        print(f"   hybrid (0.8):   {[f'{d.index_name}/{d.id}' for d in results.docs]}")
        print(f"   keyword (0.0):  {[f'{d.index_name}/{d.id}' for d in keyword_only.docs]}")
        print(f"   embedding (1.0): {[f'{d.index_name}/{d.id}' for d in embedding_only.docs]}")

        print("\n5. load_indexes is best-effort — a typo on one name does not")
        print("   roll back the others. (Reusing already-loaded names here is fine;")
        print("   load_index is idempotent and will reload them.)")
        partial = await client.load_indexes([products_index, "does-not-exist-xyz"])
        print(f"   loaded: {partial.loaded}")
        print(f"   failed: {partial.failed}")

        print("\n6. Bulk-unloading all three with unload_indexes...")
        await client.unload_indexes(all_indexes)
        print("   unloaded.")

        print("\n7. Cleaning up cloud indexes...")
        await asyncio.gather(*(client.delete_index(name) for name in all_indexes))
        print("   deleted.")

        print("\nDone.")

    except Exception as error:
        print(f"Error: {error}")
        # Best-effort cleanup so the sample doesn't leave orphan indexes around.
        try:
            await client.unload_indexes(all_indexes)
        except Exception:
            pass
        for name in all_indexes:
            try:
                await client.delete_index(name)
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
