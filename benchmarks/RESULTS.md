# Embedded vector search: results summary

Ten in-process engines, measured 2026-10-13/14 on one Apple M5 Max (18 cores, 128 GB, macOS 26.6), one query at a time, each library at its own defaults and then tuned. Main dataset: dbpedia-openai-1m (990K docs, 1536-d OpenAI embeddings, 1,000 queries). Full numbers, methods and caveats: [RESULTS-DETAIL.md](RESULTS-DETAIL.md).

## What recall means for an application

Recall@10 is the share of the true 10 nearest documents that the engine returns. At 0.95, one result in twenty is not one of the true top 10: on average half a document per query is silently swapped for a less similar one. At 0.85 it is 1.5 documents per query; at 0.53, almost 5. Nothing signals the miss. If the dropped document held the answer, a RAG pipeline never sees it. Recall is an average, so some queries can lose more.

## Key findings

- **Approximate engines trade recall for speed, and their defaults often give up a lot.** At default settings on 1M docs, FAISS-HNSW returns 0.855 recall@10, LanceDB-HNSW 0.849 and LanceDB IVF-PQ 0.531. Moss, FAISS-flat, Qdrant (local mode) and sqlite-vec are exact: 1.0, nothing to tune.
- **Tuning is a recurring cost, not a one-time step.** To tune, you must measure recall, which needs exact results for a sample of your real queries. Benchmarks ship that ground truth; your data does not. The right setting also drifts: at fixed defaults, recall fell as the same dataset grew from 25K to 100K docs (FAISS-HNSW 0.727 → 0.699, Chroma 0.934 → 0.909). Every corpus growth, data shift or embedding-model change means measuring and tuning again.
- **Filters break some approximate indexes.** With a filter keeping 1% of documents, DuckDB-VSS returned 0.01 recall and FAISS-HNSW 0.05 (100K docs, k = 100). Moss stayed exact at 3-5 ms.
- **In-memory engines cost RAM and restart time.** Moss, FAISS, DuckDB-VSS and Qdrant's local `:memory:` mode keep the whole index in RAM (6-16 GB at 1M docs here). After a restart, an index that was not saved is rebuilt (51 s for FAISS-HNSW, 55 s for Moss, 8 min for Qdrant local). Saving is an explicit call: Moss `save_to_disk()`, FAISS `write_index()`; DuckDB-VSS persistence is experimental; Qdrant's local mode can write to a path instead. Chroma, LanceDB, zvec and sqlite-vec persist to disk automatically.
- **Exact search can be fast.** With inner product, Moss matches FAISS-flat (25 ms at 1M docs) and is 38x faster than Qdrant local mode and 27-54x faster than sqlite-vec, the other exact options. Exact latency grows with corpus size (Moss: 0.70 ms at 25K docs, 1.90 ms at 100K, same dataset).
- **Hybrid search lifts text relevance.** On SciFact, Moss's default hybrid (keyword + vector) search scored nDCG@10 0.685. The other engines search by vector only: their corpus embeddings were generated ahead of time with all-MiniLM-L6-v2, each query was embedded with the same model at search time, and the best of them scored 0.654.

## Choosing an engine

| Engine | Benefits | Tradeoffs |
|---|---|---|
| **Moss** | Exact results with no tuning; exact filtered search at a few ms; hybrid text search | In-memory (save is a manual call); latency grows with corpus size |
| FAISS-flat | Exact; builds in about 1 s | Library only (no storage, no metadata); in-memory |
| FAISS-HNSW | Fastest at 0.95 recall (0.45 ms) once tuned | 0.855 recall at defaults; collapses under selective filters; in-memory |
| zvec | Fastest at 0.99 recall (1.5 ms); low RAM; persistent | Slowest build (14 min at 1M); 177 ms with a filter keeping 99% of docs |
| Chroma | Good default recall (0.964); persistent | Slow filtered search (38-101 ms) |
| LanceDB-HNSW | Low RAM; good filtered recall; persistent | 0.849 recall at defaults; never reached 0.99 at 1M |
| DuckDB-VSS | SQL alongside vectors | Largest in-memory index (15.7 GB at 1M); collapses under selective filters |
| LanceDB IVF-PQ | Fast build; compressed index; persistent | 0.53 recall at defaults; did not reach 0.99 at 1M |
| Qdrant (local mode) | Exact; same API as Qdrant server | Brute force in local mode: 952 ms per query at 1M; in-memory as tested (`:memory:`) |
| sqlite-vec | Tiny RAM; plain SQLite; persistent | Brute force: 0.7-1.4 s per query at 1M |

Each configuration was measured once, on one machine; CPU cores used per query were not measured. Memory for disk-backed engines excludes the OS file cache holding their index files.
