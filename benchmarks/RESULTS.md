# Embedded vector search: results summary

Ten vector search engines that run inside your application (no separate server), measured October 2026 on one Apple M5 Max (128 GB). Queries ran one at a time, first at each library's default settings, then tuned. Datasets: 1M Wikipedia (DBpedia) articles embedded with an OpenAI model, and SciFact, a real text-retrieval dataset. Full numbers and methods: [RESULTS-DETAIL.md](RESULTS-DETAIL.md).

## Recall in plain terms

An engine's `recall@10` is how many of a query's 10 best matches (by embedding similarity) it returns. Below 1.0, weaker matches take the place of better ones. Nothing flags the miss at runtime: if a skipped document held the answer, your application never sees it.

### Missed matches

| recall@10 | Weaker matches returned (on avg) |
| :-------: | -------------------------------- |
| 1.0       | none (exact search)              |
| 0.99      | ~1 in 100 results                |
| 0.97      | ~3 in 100                        |
| 0.95      | 1 in 20                          |
| 0.85      | 3 in 20                          |

---

<details><summary>What is HNSW?</summary>

HNSW (Hierarchical Navigable Small World) is a widely used approximate index. It links each document to a few of its most similar documents, forming a graph, and a search walks that graph toward the query instead of checking every document. A setting usually called `ef` controls how many candidates the walk keeps: higher `ef` finds more of the best matches but is slower. Adding a document means searching the graph for its neighbours, so additions cost more as the graph grows. FAISS-HNSW, zvec, Chroma, DuckDB-VSS and LanceDB-HNSW use it.

</details>

## Key findings

- **Default settings often skip the best matches.** Approximate indexes search only part of the data to save time, and several ship with defaults that skip a large share of the best matches. Exact engines always return the best matches, with no tuning.

- **Tuning is a recurring cost.** Benchmarks come with an answer key; your data does not, so checking recall means running exact searches for a sample of your own queries. The right setting drifts as the corpus grows or changes, so tuning has to be repeated.

- **Fast filtered search usually costs recall.** With a filter that keeps few documents (e.g. 1%), some approximate indexes stay fast but return almost none of the best matches. Others keep their recall, but some filtered queries run 10x slower or more.

- **Hybrid search finds more relevant text.** SciFact has real queries and human relevance judgments, so it is the closest test here to a production search or RAG workload. Moss's default hybrid search (keyword + vector, built-in embedding model) ranked relevant documents higher than every vector-only engine (all searching the same off-the-shelf embeddings).

- **In-memory indexes need a save step.** An index held only in RAM must fit in memory and is lost on restart unless saved. Moss saves to disk or to Moss cloud¹, and FAISS to disk, with an explicit call; disk-based engines persist automatically.

- **Growing an index gets more expensive with some engines.** Moss's build cost per document stays flat as the corpus grows. Graph-based (HNSW) engines get slower per document as they grow (zvec most), and adding documents to an indexed DuckDB-VSS table is slower than rebuilding it.

- **Exact search can still be fast.** Moss's exact search matches FAISS's exact index at 1M docs (25 ms). Its latency grew sub-linearly from 25k to 100k docs.

## Choosing an engine

| Engine | Benefits | Tradeoffs | Use it when... |
|---|---|---|---|
| **Moss** | Exact results, no tuning; fast exact filtered search; hybrid text search; steady build cost as the corpus grows; index on disk or in Moss cloud | Query latency increases with a larger corpus | you want exact results, hybrid search, fast filtered queries and low latency (2 ms @100k docs, 25 ms @1M) with no tuning, and have RAM for the whole index |
| FAISS-flat | Exact; near-instant build; can save to disk | Bare index: you store ids and metadata yourself; no metadata filters | you want exact results, low latency and fast builds, have RAM for the whole index, and don't need hybrid search or built-in metadata storage |
| FAISS-HNSW | Fastest at 0.95 recall once tuned; can save to disk | Low recall at defaults; recall plummets with filters; requires significant tuning | you want the lowest unfiltered latency, have RAM for the whole index, don't need filters, and don't mind regular re-tuning |
| zvec | Fastest at 0.99 recall once tuned; low RAM; on disk | Slowest build, and per-doc build cost grows with the index; slow filtered search, up to ~180 ms; requires tuning | you want minimal RAM usage, don't need frequent updates (slow builds and inserts), and don't mind tuning that trades recall for latency |
| Chroma | Good recall at defaults; simple API; on disk | Slow filtered search, up to ~100 ms; requires tuning | you want to prototype or search a small to medium collection, and don't mind tuning or slow filtered searches and builds |
| LanceDB-HNSW | Low RAM; good filtered recall; on disk | Low recall at defaults; best recall@10 at 1M docs: 0.988; requires tuning | you want low RAM usage and frequent filtered search, don't need recall above [~0.99](#missed-matches), and don't mind re-tuning |
| DuckDB-VSS | Vector search inside SQL | Largest in-memory index; recall plummets with filters; adding docs is slower than rebuilding; on-disk index is experimental; requires tuning | you want vector search in an existing DuckDB database, and don't need filters, incremental inserts or low RAM usage |
| LanceDB IVF-PQ | Fast build; compressed vectors; on disk | Recall 0.53 at defaults; best recall@10 at 1M docs: 0.974; requires tuning | you want low RAM usage and fast builds for a very large corpus, don't need recall above [~0.97](#missed-matches), and don't mind re-tuning |
| Qdrant (local mode) | Exact; same API as Qdrant server | Brute-force search: ~1 s per query at 1M | you want to prototype for a Qdrant server and aren't building for edge retrieval |
| sqlite-vec | Exact; tiny RAM; plain SQLite file | Brute-force search: 0.7-1.4 s per query at 1M | you want minimal RAM usage for a small corpus (<100k docs), and don't need low latency |

One run per configuration on one machine; CPU use per query was not measured.

¹ The benchmark searched Moss's index without saving it. A saved index loads back into memory and is searched the same way; load time from disk was not measured.
