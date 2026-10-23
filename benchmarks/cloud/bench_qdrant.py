"""Benchmark: Qdrant Cloud — external embedding + cloud vector search.

This measures end-to-end latency: embed the query via an external API,
then search a Qdrant Cloud index.

Requires QDRANT_URL and QDRANT_API_KEY environment variables.
"""

import os

from dotenv import load_dotenv

from corpus import get_documents, get_queries
from embedding import EmbeddingClient
from stats import Timer, BenchmarkResult

load_dotenv()

DOC_COUNT = 100_000
TOP_K = 5
WARMUP_ROUNDS = 3
QUERY_ROUNDS = 50
COLLECTION = "benchmark"


def run():
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    embed = EmbeddingClient()
    docs = get_documents(DOC_COUNT)
    queries = get_queries()

    print(f"  docs in index  : {DOC_COUNT}")
    print(f"  warmup rounds  : {WARMUP_ROUNDS}")
    print(f"  query rounds   : {QUERY_ROUNDS}")
    print(f"  queries/round  : {len(queries)}")
    print(f"  embedding      : {embed.provider} (dim={embed.dimension})")

    # --- Setup Qdrant Cloud ---
    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")
    if not qdrant_url or not qdrant_api_key:
        raise ValueError("QDRANT_URL and QDRANT_API_KEY must be set in .env")
    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(
            size=embed.dimension, distance=Distance.COSINE
        ),
    )

    # --- Embed and upsert documents ---
    print("  Embedding and upserting documents...")
    texts = [d["text"] for d in docs]
    embeddings = embed.embed_batch(texts)
    points = [
        PointStruct(
            id=i,
            vector=emb,
            payload={"text": d["text"], **(d.get("metadata") or {})},
        )
        for i, (d, emb) in enumerate(zip(docs, embeddings))
    ]
    client.upload_points(collection_name=COLLECTION, points=points)

    print(f"  Loaded {client.count(COLLECTION).count} docs")

    def qdrant_search(query_vector):
        return client.query_points(
            collection_name=COLLECTION,
            query=query_vector,
            limit=TOP_K,
        )

    # --- Cold query ---
    with Timer() as t:
        emb = embed.embed(queries[0])
        qdrant_search(emb)
    print(f"\n  Cold query: {t.elapsed_ms:.3f} ms")

    # --- Warmup ---
    print(f"\n  Warming up ({WARMUP_ROUNDS} rounds)...")
    for _ in range(WARMUP_ROUNDS):
        for q in queries:
            emb = embed.embed(q)
            qdrant_search(emb)

    # --- Measure ---
    print(f"  Measuring ({QUERY_ROUNDS} rounds x {len(queries)} queries)...\n")
    latencies = []
    for _ in range(QUERY_ROUNDS):
        for q in queries:
            with Timer() as t:
                emb = embed.embed(q)
                qdrant_search(emb)
            latencies.append(t.elapsed_ms)

    result = BenchmarkResult(
        f"Qdrant Cloud (external embed + cloud search, top_k={TOP_K}, {DOC_COUNT} docs)",
        latencies,
    )
    print(result.summary())
    return result


if __name__ == "__main__":
    run()
