"""Benchmark: ChromaDB — external embedding + local in-memory vector search.

This measures end-to-end latency: embed the query via an external API,
then search a local in-memory ChromaDB collection.
"""


from dotenv import load_dotenv

from corpus import get_documents, get_queries
from embedding import EmbeddingClient
from stats import Timer, BenchmarkResult

load_dotenv()

DOC_COUNT = 100_000
TOP_K = 5
WARMUP_ROUNDS = 3
QUERY_ROUNDS = 50


def run():
    import chromadb

    embed = EmbeddingClient()
    docs = get_documents(DOC_COUNT)
    queries = get_queries()

    print(f"  docs in index  : {DOC_COUNT}")
    print(f"  warmup rounds  : {WARMUP_ROUNDS}")
    print(f"  query rounds   : {QUERY_ROUNDS}")
    print(f"  queries/round  : {len(queries)}")
    print(f"  embedding      : {embed.provider} (dim={embed.dimension})")

    # --- Setup ChromaDB (in-memory) ---
    client = chromadb.Client()
    collection = client.create_collection(name="benchmark")

    # --- Embed and add documents ---
    print("  Embedding and adding documents...")
    BATCH = 100
    for i in range(0, len(docs), BATCH):
        batch = docs[i : i + BATCH]
        texts = [d["text"] for d in batch]
        embeddings = embed.embed_batch(texts)
        ids = [d["id"] for d in batch]
        metadatas = [d.get("metadata") or None for d in batch]
        # ChromaDB rejects empty dicts — omit metadatas if all are None
        if any(m for m in metadatas):
            metadatas = [m if m else {"_": ""} for m in metadatas]
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
        else:
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
            )

    print(f"  Loaded {collection.count()} docs")

    # --- Cold query ---
    with Timer() as t:
        emb = embed.embed(queries[0])
        collection.query(query_embeddings=[emb], n_results=TOP_K)
    print(f"\n  Cold query: {t.elapsed_ms:.3f} ms")

    # --- Warmup ---
    print(f"\n  Warming up ({WARMUP_ROUNDS} rounds)...")
    for _ in range(WARMUP_ROUNDS):
        for q in queries:
            emb = embed.embed(q)
            collection.query(query_embeddings=[emb], n_results=TOP_K)

    # --- Measure ---
    print(f"  Measuring ({QUERY_ROUNDS} rounds x {len(queries)} queries)...\n")
    latencies = []
    for _ in range(QUERY_ROUNDS):
        for q in queries:
            with Timer() as t:
                emb = embed.embed(q)
                collection.query(query_embeddings=[emb], n_results=TOP_K)
            latencies.append(t.elapsed_ms)

    result = BenchmarkResult(
        f"ChromaDB (external embed + in-memory search, top_k={TOP_K}, {DOC_COUNT} docs)",
        latencies,
    )
    print(result.summary())
    return result


if __name__ == "__main__":
    run()
