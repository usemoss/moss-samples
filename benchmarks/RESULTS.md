# Embedded vector search: results summary

Ten vector search engines that run inside your application (no separate server), measured October 2026 on one Apple M5 Max (128 GB). Queries ran one at a time, first at each library's default settings, then tuned. Datasets: 1M Wikipedia (DBpedia) articles embedded with an OpenAI model, and SciFact, a real text-retrieval dataset. Full numbers and methods: [RESULTS-DETAIL.md](RESULTS-DETAIL.md).

## Recall in plain terms

An engine's `recall@10` is how many of a query's 10 best matches (by embedding similarity) it returns. At 0.95, on average 1 result in 20 is a weaker match that took the place of a better one; at 0.85, 3 in 20. Nothing flags the miss at runtime: if a skipped document held the answer, your application never sees it.

<details><summary>What is HNSW?</summary>

HNSW (Hierarchical Navigable Small World) is a widely used approximate index. It links each document to a few of its most similar documents, forming a graph, and a search walks that graph toward the query instead of checking every document. A setting usually called `ef` controls how many candidates the walk keeps: higher `ef` finds more of the best matches but is slower. Adding a document means searching the graph for its neighbours, so additions cost more as the graph grows. FAISS-HNSW, zvec, Chroma, DuckDB-VSS and LanceDB-HNSW use it.

</details>

## Key findings

- **Default settings often skip the best matches.** Approximate indexes search only part of the data to save time, and several ship with defaults that skip a large share of the best matches. Exact engines always return the best matches, with no tuning.

- **Tuning is a recurring cost.** Benchmarks come with an answer key; your data does not, so checking recall means running exact searches for a sample of your own queries. The right setting drifts as the corpus grows or changes, so tuning has to be repeated.

- **Fast filtered search usually costs recall.** With a filter that keeps few documents (e.g. 1%), some approximate indexes stay fast but return almost none of the best matches. Others keep their recall, but some filtered queries run 10x slower or more.

- **Hybrid search finds more relevant text.** SciFact has real queries and human relevance judgments, so it is the closest test here to a production search or RAG workload. Moss's default hybrid search (keyword + vector, with its own built-in embedding model) ranked relevant documents higher than every vector-only engine (each searching the same off-the-shelf model embeddings).

- **In-memory indexes need a save step.** An index held only in RAM must fit in memory and is lost on restart unless saved. Moss saves to disk or to Moss cloud¹, and FAISS to disk, with an explicit call; disk-based engines persist automatically.

- **Growing an index gets more expensive with some engines.** Moss's build cost per document stays flat as the corpus grows. Graph-based (HNSW) engines get slower per document as they grow (zvec most), and adding documents to an indexed DuckDB-VSS table is slower than rebuilding it.

- **Exact search can still be fast.** Moss searches exactly, with no recall loss, as fast as FAISS's exact index. Its latency grows with corpus size, but less than proportionally.

## Choosing an engine

| Engine | Benefits | Tradeoffs | Use it when |
|---|---|---|---|
| **Moss** | Exact results, no tuning; fast exact filtered search; hybrid text search; steady build cost as the corpus grows; index on disk or in Moss cloud | Latency grows with corpus size, 4x the docs: ~2.7x the latency | The index fits in RAM and you want exact results and filters with steady latency (2 ms at 100K docs, 25 ms at 1M) and no tuning as the corpus grows |
| FAISS-flat | Exact; near-instant build; can save to disk | Bare index: you store ids and metadata yourself; no metadata filters | The index fits in RAM, you already manage storage and metadata, and you need exact results |
| FAISS-HNSW | Fastest at 0.95 recall once tuned; can save to disk | Low recall at defaults; recall plummets when filters applied; requires significant tuning | Unfiltered speed matters most, the index fits in RAM, and someone can re-tune as data changes |
| zvec | Fastest at 0.99 recall once tuned; low RAM; on disk | Slowest build, and slower per doc as the index grows; slow filtered search, up to ~180 ms; requires continuous tuning | RAM is tight, data changes rarely (slow builds and inserts), and you need very high recall |
| Chroma | Good recall at defaults; simple API; on disk | Slow filtered search, up to ~100 ms; requires tuning | Prototypes or small to medium collections where filters are rare and build time matters little |
| LanceDB-HNSW | Low RAM; good filtered recall; on disk | Low recall at defaults; best recall@10 at 1M docs: 0.988; requires tuning | RAM is tight, filters are common, and recall up to ~0.99 is enough |
| DuckDB-VSS | Vector search inside SQL | Largest in-memory index; recall plummets when filters applied; adding docs is slower than rebuilding; on-disk index is experimental; requires tuning | You already use DuckDB, RAM is plentiful, filters are rare, and data loads in bulk |
| LanceDB IVF-PQ | Fast build; compressed vectors; on disk | Recall 0.53 at defaults; best recall@10 at 1M docs: 0.974; requires tuning | The corpus is very large, RAM and build time matter most, and lower recall is acceptable |
| Qdrant (local mode) | Exact; same API as Qdrant server | Slow exact search in local mode: ~1 s per query at 1M | Prototyping a small collection before moving to a Qdrant server |
| sqlite-vec | Exact; tiny RAM; plain SQLite file | Slow exact search: 0.7-1.4 s per query at 1M | Collections are small (tens of thousands of docs), RAM is minimal, and an SQLite file is convenient |

One run per configuration on one machine; CPU use per query was not measured.

¹ The benchmark searched Moss's index without saving it. A saved index loads back into memory and is searched the same way; load time was not measured.
