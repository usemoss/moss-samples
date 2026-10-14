# Embedded vector search: results summary

Ten vector search engines that run inside your application (no separate server), measured in 2026-10 on one Apple M5 Max (128 GB). Queries ran one at a time, first at each library's default settings, then tuned. Datasets: 1M Wikipedia (DBpedia) articles embedded with an OpenAI model, and SciFact, a real text-retrieval dataset. Full numbers and methods: [RESULTS-DETAIL.md](RESULTS-DETAIL.md).

## Recall in plain terms

Recall@10 is how many of a query's 10 best matches (by embedding similarity) an engine returns. At 0.95, on average 1 result in 20 is a weaker match that took the place of a better one; at 0.85, 3 in 20. Nothing indicates the miss at runtime: if a skipped document held the answer, your application never sees it.

<details>
<summary>What is HNSW?</summary>

HNSW (Hierarchical Navigable Small World) is a widely used approximate index. It links each document to a few of its most similar documents, forming a graph, and a search walks that graph toward the query instead of checking every document. A setting usually called `ef` controls how many candidates the walk keeps: higher finds more of the best matches but is slower. Adding a document means searching the graph for its neighbours, so additions cost more as the graph grows. FAISS-HNSW, zvec, Chroma, DuckDB-VSS and LanceDB-HNSW use it.

</details>

## Key findings

- **Default settings often skip the best matches.** Approximate indexes search only part of the data to save time, and several ship with defaults that skip a large share of the best matches. Exact engines always return the best matches, with no tuning.

- **Tuning is a recurring cost.** Benchmarks come with an answer key; your data does not, so checking recall means running exact searches for a sample of your own queries. The right setting drifts as the corpus grows or changes, so tuning has to be repeated.

- **Fast filtered search usually costs recall.** With a filter that keeps few documents (e.g. 1%), some approximate indexes stay fast but return almost none of the best matches. Others keep recall but slow down by an order of magnitude or more.

- **Hybrid search finds more relevant text.** SciFact has real queries and human relevance judgments, so it is the closest test here to a production search or RAG workload. Moss's default hybrid search (keyword + vector, with its built-in embedding model) ranked relevant documents higher than every vector-only engine (each searching the same model embeddings).

- **In-memory indexes need a save step.** An index held only in RAM must fit in memory and is lost on restart unless saved. Moss saves to disk or to Moss cloud, and FAISS to disk, with an explicit call; disk-based engines persist automatically. Moss was benchmarked without saving to disk.

- **Growing an index gets more expensive with some engines.** Moss's build cost per document stays flat as the corpus grows. Graph-based (HNSW) engines get slower per document as they grow (zvec most), and adding documents to an indexed DuckDB-VSS table is slower than rebuilding it.

- **Exact search can still be fast.** Moss searches exactly, with no recall loss, as fast as FAISS's exact index. Its latency grows with corpus size, but less than proportionally in these runs.

## Choosing an engine

| Engine | Benefits | Tradeoffs | Use it when |
|---|---|---|---|
| **Moss** | Exact results, no tuning; fast exact filtered search; hybrid text search; steady build cost as the corpus grows; index on disk or in Moss cloud | Latency grows with corpus size (4x the docs: 2.7x the latency) | You want correct results and filters without tuning, or text search |
| FAISS-flat | Exact; near-instant build; saves to disk (`write_index()`) | Library only: no storage layer or metadata filters | You want an exact in-memory index inside your own data layer |
| FAISS-HNSW | Fastest at 0.95 recall once tuned; saves to disk (`write_index()`) | Low recall at defaults; recall plummets when filters applied; requires significant tuning | Unfiltered search must be as fast as possible and someone can maintain the tuning |
| zvec | Fastest at 0.99 recall once tuned; low RAM; on disk | Slowest build, and slower per doc as the index grows; slow filtered search, up to ~180 ms; requires continuous tuning | Data changes rarely and you need very high recall |
| Chroma | Good recall at defaults; simple API; on disk | Slow filtered search, up to ~100 ms; requires tuning | Prototypes and small to medium collections |
| LanceDB-HNSW | Low RAM; good filtered recall; on disk | Low recall at defaults; best recall@10 at 1M docs: 0.988; requires tuning | Data lives on disk and moderate recall is enough |
| DuckDB-VSS | Vector search inside SQL | Largest in-memory index; recall plummets when filters applied; adding docs is slower than rebuilding; on-disk index is experimental; requires tuning | You already use DuckDB and rarely filter |
| LanceDB IVF-PQ | Fast build; compressed vectors; on disk | Recall 0.53 at defaults; best recall@10 at 1M docs: 0.974; requires tuning | Data is very large and memory matters more than recall |
| Qdrant (local mode) | Exact; same API as Qdrant server | Slow exact search in local mode: ~1 s per query at 1M | Developing before moving to a Qdrant server |
| sqlite-vec | Exact; tiny RAM; plain SQLite file | Slow exact search: 0.7-1.4 s per query at 1M | Collections are small, or the app is embedded or on the edge |

One run per configuration on one machine; CPU use per query was not measured.
