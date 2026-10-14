# Embedded vector search: results summary

Ten in-process vector search engines, measured in 2026-10 on one Apple M5 Max (128 GB). Queries ran one at a time, first at each library's default settings, then tuned. Datasets: 1M OpenAI embeddings (dbpedia-openai-1m) and SciFact, a real text-retrieval dataset. Full numbers and methods: [RESULTS-DETAIL.md](RESULTS-DETAIL.md).

## Recall in plain terms

Recall@10 is how many of the 10 truly closest documents a search returns. At 0.95, one result in 20 is not one of them; at 0.85, three in 20. Missed documents are silently replaced by less relevant ones: if a missed document held the answer, your application never sees it.

## Key findings

- **Default settings often return the wrong documents.** Approximate indexes trade recall for speed, and several ship with defaults that miss a large share of the true results. Exact engines return the true results with no tuning.
- **Tuning is a recurring cost.** Measuring recall needs exact results for a sample of your own queries, which benchmarks provide and real data does not. The right setting drifts as the corpus grows or changes, so tuning has to be repeated.
- **Fast filtered search usually costs recall.** Some approximate indexes stay fast under a selective filter but return almost none of the right documents. Others keep recall but slow down by an order of magnitude or more.
- **Hybrid search finds more relevant text.** SciFact has real queries and human relevance judgments, so it is the closest test here to a production search or RAG workload. Moss's default hybrid search (keyword + vector) ranked relevant documents higher than every vector-only engine.
- **In-memory indexes need a save step.** An index held only in RAM must fit in memory and is lost on restart unless saved. Moss saves to disk or to Moss cloud, and FAISS to disk, with an explicit call; disk-based engines persist automatically. The benchmark used in-memory sessions for Moss.
- **Growing an index gets more expensive with some engines.** Moss's build cost per document stays flat as the corpus grows. HNSW-based engines cost more per document as they grow (zvec most), and adding documents to an indexed DuckDB-VSS table is slower than rebuilding it.
- **Exact search can still be fast.** Moss searches exactly, with no recall loss, as fast as FAISS's exact index. Its latency grows with corpus size, but less than proportionally in these runs.

## Choosing an engine

| Engine | Benefits | Tradeoffs |
|---|---|---|
| **Moss** | Exact results, no tuning; fast exact filtered search; hybrid text search; steady build cost as the corpus grows; index on disk or in Moss cloud | Latency grows with corpus size (4x the docs: 2.7x the latency) |
| FAISS-flat | Exact; near-instant build; saves to disk (`write_index()`) | Library only: no storage layer or metadata filters |
| FAISS-HNSW | Fastest at 0.95 recall once tuned; saves to disk (`write_index()`) | Low recall at defaults; recall plummets when filters applied |
| zvec | Fastest at 0.99 recall once tuned; low RAM; on disk | Slowest build, and slower per doc as the index grows; slow filtered search, up to ~180 ms |
| Chroma | Good recall at defaults; simple API; on disk | Slow filtered search, up to ~100 ms |
| LanceDB-HNSW | Low RAM; good filtered recall; on disk | Low recall at defaults; max recall@10 0.988 at 1M |
| DuckDB-VSS | Vector search inside SQL | Largest in-memory index; recall plummets when filters applied; adding docs is slower than rebuilding; on-disk index is experimental |
| LanceDB IVF-PQ | Fast build; compressed index; on disk | Recall 0.53 at defaults; max recall@10 0.974 at 1M |
| Qdrant (local mode) | Exact; same API as Qdrant server | Brute force in local mode: ~1 s per query at 1M |
| sqlite-vec | Tiny RAM; plain SQLite file | Brute force: 0.7-1.4 s per query at 1M |

One run per configuration on one machine; CPU use per query was not measured.
