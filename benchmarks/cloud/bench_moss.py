"""Benchmark: Moss — built-in embedding, single-call semantic search.

Moss embeds and searches in a single call. No external embedding
service is needed. This measures true end-to-end latency.
"""

import asyncio
import os

from dotenv import load_dotenv

from corpus import get_documents, get_queries
from stats import Timer, BenchmarkResult

load_dotenv()

DOC_COUNT = 100_000
TOP_K = 5
WARMUP_ROUNDS = 3
QUERY_ROUNDS = 50


async def run_async():
    from moss import MossClient, DocumentInfo, QueryOptions

    queries = get_queries()

    print(f"  docs in index  : {DOC_COUNT}")
    print(f"  warmup rounds  : {WARMUP_ROUNDS}")
    print(f"  query rounds   : {QUERY_ROUNDS}")
    print(f"  queries/round  : {len(queries)}")
    print("  embedding      : built-in (moss-minilm)")

    # --- Setup ---
    client = MossClient(
        os.getenv("MOSS_PROJECT_ID"),
        os.getenv("MOSS_PROJECT_KEY"),
    )

    index_name = os.getenv("MOSS_INDEX_NAME", "benchmark-public")

    # Create index if it doesn't exist, otherwise reuse
    try:
        await client.get_index(index_name)
        print(f"  Reusing existing index '{index_name}'")
    except Exception:
        docs = get_documents(DOC_COUNT)
        moss_docs = [
            DocumentInfo(id=d["id"], text=d["text"], metadata=d.get("metadata"))
            for d in docs
        ]
        result = await client.create_index(index_name, moss_docs, "moss-minilm")
        print(f"  Created index with {result.doc_count} docs")

    # --- Load index locally for in-memory search ---
    print("  Loading index into memory...")
    await client.load_index(index_name)

    # --- Cold query ---
    with Timer() as t:
        await client.query(index_name, queries[0], QueryOptions(top_k=TOP_K, alpha=1))
    print(f"\n  Cold query: {t.elapsed_ms:.3f} ms")

    # --- Warmup ---
    print(f"\n  Warming up ({WARMUP_ROUNDS} rounds)...")
    for _ in range(WARMUP_ROUNDS):
        for q in queries:
            await client.query(index_name, q, QueryOptions(top_k=TOP_K, alpha=1))

    # --- Measure ---
    print(f"  Measuring ({QUERY_ROUNDS} rounds x {len(queries)} queries)...\n")
    latencies = []
    for _ in range(QUERY_ROUNDS):
        for q in queries:
            with Timer() as t:
                await client.query(index_name, q, QueryOptions(top_k=TOP_K, alpha=1))
            latencies.append(t.elapsed_ms)

    result = BenchmarkResult(
        f"Moss (built-in embedding, top_k={TOP_K}, {DOC_COUNT} docs)", latencies
    )
    print(result.summary())
    return result


def run():
    return asyncio.run(run_async())


if __name__ == "__main__":
    run()
