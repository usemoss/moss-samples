"""Benchmark: Pinecone Serverless — external embedding + cloud vector search.

This measures the real-world experience: embed the query via an external
API, then search Pinecone's cloud index. Both network round-trips are
included in the measured latency.
"""

import os
import time

from dotenv import load_dotenv

from corpus import get_documents, get_queries
from embedding import EmbeddingClient
from stats import Timer, BenchmarkResult

load_dotenv()

DOC_COUNT = 100_000
TOP_K = 5
WARMUP_ROUNDS = 3
QUERY_ROUNDS = 50
INDEX_NAME = "benchmark-public"


def run():
    from pinecone import Pinecone, ServerlessSpec

    embed = EmbeddingClient()
    docs = get_documents(DOC_COUNT)
    queries = get_queries()

    print(f"  docs in index  : {DOC_COUNT}")
    print(f"  warmup rounds  : {WARMUP_ROUNDS}")
    print(f"  query rounds   : {QUERY_ROUNDS}")
    print(f"  queries/round  : {len(queries)}")
    print(f"  embedding      : {embed.provider} (dim={embed.dimension})")

    # --- Setup Pinecone ---
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

    # Delete if exists
    existing = [idx.name for idx in pc.list_indexes()]
    if INDEX_NAME in existing:
        pc.delete_index(INDEX_NAME)

    pc.create_index(
        name=INDEX_NAME,
        dimension=embed.dimension,
        metric="cosine",
        spec=ServerlessSpec(
            cloud=os.getenv("PINECONE_CLOUD", "aws"),
            region=os.getenv("PINECONE_REGION", "us-east-1"),
        ),
    )

    # Wait for index to be ready
    print("  Waiting for Pinecone index to be ready...")
    while not pc.describe_index(INDEX_NAME).status["ready"]:
        time.sleep(1)

    index = pc.Index(INDEX_NAME)

    # --- Embed and upsert documents ---
    print("  Embedding and upserting documents...")
    BATCH = 100
    for i in range(0, len(docs), BATCH):
        batch = docs[i : i + BATCH]
        texts = [d["text"] for d in batch]
        embeddings = embed.embed_batch(texts)
        vectors = [
            {
                "id": d["id"],
                "values": emb,
                "metadata": d.get("metadata", {}),
            }
            for d, emb in zip(batch, embeddings)
        ]
        index.upsert(vectors=vectors)

    # Wait for vectors to be indexed
    print("  Waiting for vectors to be indexed...")
    while True:
        stats = index.describe_index_stats()
        if stats.total_vector_count >= DOC_COUNT:
            break
        print(f"    indexed {stats.total_vector_count}/{DOC_COUNT} vectors...")
        time.sleep(5)
    print(f"  Index stats: {stats}")

    # --- Cold query ---
    with Timer() as t:
        emb = embed.embed(queries[0])
        index.query(vector=emb, top_k=TOP_K)
    print(f"\n  Cold query: {t.elapsed_ms:.3f} ms")

    # --- Warmup ---
    print(f"\n  Warming up ({WARMUP_ROUNDS} rounds)...")
    for _ in range(WARMUP_ROUNDS):
        for q in queries:
            emb = embed.embed(q)
            index.query(vector=emb, top_k=TOP_K)

    # --- Measure ---
    print(f"  Measuring ({QUERY_ROUNDS} rounds x {len(queries)} queries)...\n")
    latencies = []
    for _ in range(QUERY_ROUNDS):
        for q in queries:
            with Timer() as t:
                emb = embed.embed(q)
                index.query(vector=emb, top_k=TOP_K)
            latencies.append(t.elapsed_ms)

    result = BenchmarkResult(
        f"Pinecone Serverless (external embed + cloud search, top_k={TOP_K}, {DOC_COUNT} docs)",
        latencies,
    )
    print(result.summary())

    # --- Cleanup ---
    print("\n  Cleaning up Pinecone index...")
    pc.delete_index(INDEX_NAME)

    return result


if __name__ == "__main__":
    run()
