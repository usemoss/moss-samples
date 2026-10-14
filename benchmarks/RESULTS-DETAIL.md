# Embedded vector search: detailed results

Summary: [RESULTS.md](RESULTS.md). Methods, options and known behaviors: [README.md](README.md).

## Setup

- **Machine:** Apple M5 Max, 18 cores, 128 GB RAM, macOS 26.6.2. Runs in October 2026, commit `3d169e8`.

- **Engines:**
  - Moss 1.16.1 (core 0.30.1)
  - Chroma 1.5.9
  - LanceDB 0.40.0 (IVF-PQ and IVF-HNSW-SQ)
  - Qdrant client 1.19.1 (local mode)
  - FAISS 1.15.1 (flat and HNSW)
  - zvec 0.7.0, sqlite-vec 0.1.9
  - DuckDB 1.5.6 + vss
  
  All in-process; index settings are each library's defaults (see the README's engine table).

- **Datasets:**
  - dbpedia-openai-1m: 990k docs, 1536-d OpenAI embeddings, 1,000 queries.
  - cohere-100k: 100k docs, 768-d, 1,000 queries. Also used for filters and corpus scaling.
  - SciFact: 5,183 abstracts, 300 test queries, human relevance labels.

- **Method:**
  - Queries run one at a time from one client, after 100 unmeasured warm-up queries. Latency is the wall-clock time per call.
  - Recall@k is measured against exact search; text quality is nDCG@10 against the human labels.
  - Each configuration was measured in one run, without repeats.

- **Metric:** vectors are normalized, so inner product (the dataset metric) and each library's default distance rank documents the same; only speed differs. Numbers below use inner product unless noted.

## What recall means for an application

Recall@10 is how many of a query's 10 best matches (by embedding similarity, as an exact search finds them) an engine returns, averaged over queries. A skipped match is silently replaced by a weaker one:

| recall@10 | True top-10 documents missing per query, on average | Engines at default settings (1M docs) |
|---|---|---|
| 1.0 | 0 | Moss, FAISS-flat, Qdrant local, sqlite-vec (exact) |
| 0.998 | 0.02 | zvec |
| 0.951-0.964 | 0.36-0.49 | Chroma, DuckDB-VSS |
| 0.85 | 1.5 | FAISS-HNSW, LanceDB-HNSW |
| 0.53 | 4.7 | LanceDB IVF-PQ |

For retrieval-augmented generation (RAG), a missed document is context the model never sees. If it was the one holding the answer, the response is built from weaker evidence, and nothing in the pipeline reports it.

Recall is a mean, so a 0.95 average can include queries that lose more than half a result. It is also measured against exact vector search, so it stacks on top of the embedding model's own relevance limit. On SciFact, exact vector search over the all-MiniLM-L6-v2 embeddings generated ahead of time reached nDCG@10 0.654, and at default settings the HNSW-based engines scored up to 0.010 lower and LanceDB IVF-PQ 0.115 lower.

## Results at 1M docs

dbpedia-openai-1m, k = 10, inner product:

| Engine | recall@10 at defaults | Mean latency at defaults | Fastest setting with recall ≥ 0.95 | Fastest setting with recall ≥ 0.99 (or max recall) | Build | Index in RAM | Index on disk |
|---|---|---|---|---|---|---|---|
| Moss | 1.000 | 25.2 ms | 25.2 ms | 25.2 ms | 55 s | 6.0 GB | none |
| FAISS-flat | 1.000 | 25.2 ms | 25.2 ms | 25.2 ms | 1.3 s | 9.7 GB | none |
| FAISS-HNSW | 0.855 | 0.14 ms | 0.45 ms (ef 100) | 2.58 ms (ef 768) | 51 s | 6.2 GB | none |
| zvec | 0.998 | 3.63 ms | 0.66 ms (ef 32) | 1.51 ms (ef 100) | 836 s | 0.12 GB | 6.1 GB |
| Chroma | 0.964 | 2.38 ms | 2.33 ms (ef 100) | 10.5 ms (ef 768) | 418 s | 6.3 GB | 6.0 GB |
| LanceDB-HNSW | 0.849 | 1.69 ms | 3.15 ms (refine 5) | max 0.988 (refine 10, 4.47 ms) | 114 s | 2.3 GB | 7.3 GB |
| DuckDB-VSS | 0.951 | 6.03 ms | 6.06 ms (ef 100) | 8.09 ms (ef 512) | 117 s | 15.7 GB | none |
| LanceDB IVF-PQ | 0.531 | 5.79 ms | 7.12 ms (refine 20) | max 0.974 (refine 50, 8.93 ms) | 28 s | 3.2 GB | 5.8 GB |
| Qdrant local | 1.000 | 952 ms | 952 ms | 952 ms | 477 s | 9.7 GB (21.1 GB peak while searching) | none |
| sqlite-vec | 1.000 | 1,374 ms | 1,374 ms | 1,374 ms | 163 s | 0.01 GB | 5.7 GB |

The "Index in RAM" column is the process footprint added by the index. For the disk-backed engines it leaves out the OS file cache that holds their index files.

With each library's default distance instead of inner product, a few engines change speed:

| Engine | Default distance | Inner product |
|---|---|---|
| Chroma | 0.89 ms | 2.38 ms |
| FAISS-flat | 45.3 ms | 25.2 ms |
| sqlite-vec | 678 ms | 1,374 ms (cosine) |

On this dataset FAISS-HNSW's first passes after its build ran slow (see Limits), which overstates its default-distance latency.

## The cost of tuning

Approximate indexes expose a speed/recall knob (HNSW `ef`, LanceDB `refine_factor`), and the defaults leave recall behind. Tuning that knob is not a one-time step:

- **Measuring recall needs ground truth that real data does not have.** Benchmarks ship the exact nearest neighbours of every query. For your own data, you must:
  - sample representative queries;
  - run an exact search over the whole corpus for each one;
  - compare the results.
  
  Measuring answer quality, rather than neighbour recall, needs human relevance labels, as SciFact has.
- **The right setting drifts as the corpus grows.** At unchanged defaults, recall@100 fell as cohere-100k grew from 25k to 100k docs:

  | Engine | 25k | 50k | 75k | 100k |
  |---|---|---|---|---|
  | FAISS-HNSW | 0.727 | 0.709 | 0.705 | 0.699 |
  | Chroma | 0.934 | 0.922 | 0.914 | 0.909 |
  | DuckDB-VSS | 0.937 | 0.924 | 0.917 | 0.913 |
  | LanceDB IVF-PQ | 0.542 | 0.517 | 0.500 | 0.489 |
  | LanceDB-HNSW | 0.961 | 0.956 | 0.953 | 0.950 |
  | zvec | 0.999 | 0.998 | 0.998 | 0.997 |
  | Moss and the other exact engines | 1.000 | 1.000 | 1.000 | 1.000 |

  The FAISS-HNSW setting that reached recall@10 ≥ 0.99 was ef 160 on cohere-100k and ef 768 on dbpedia-openai-1m. These are different datasets, but the direction is the same: larger corpora need higher settings, and higher settings are slower.
- **Filters change recall too.** A setting tuned on unfiltered queries says little about filtered ones (next section).
- **The cost recurs.** Corpus growth, shifts in what users ask, and a new embedding model each invalidate the last tuning. You have to measure again or accept unknown recall.

Exact engines (Moss, FAISS-flat, Qdrant local, sqlite-vec) have nothing to tune: recall is 1.0 by construction. The cost moves to latency, which grows with corpus size. Mean latency at k = 100 on cohere-100k:

| Engine | 25k docs | 100k docs |
|---|---|---|
| Moss | 0.70 ms | 1.90 ms |
| FAISS-flat | 0.38 ms | 1.27 ms |
| Qdrant local | 4.71 ms | 17.35 ms |
| sqlite-vec | 18.6 ms | 73.6 ms |

## In-memory vs on-disk

| Engine | Storage as tested | Persistence | Rebuild after restart without a save (1M docs) |
|---|---|---|---|
| Moss | in-memory session (not saved) | `save_to_disk()` / `load_from_disk()`, or a Moss cloud index loaded locally with a cache; standard in production, not used here | 55 s |
| FAISS (flat, HNSW) | in memory | `write_index()` / `read_index()` (save and load cost not measured) | 1.3 s (flat), 51 s (HNSW) |
| DuckDB-VSS | in-memory database | HNSW in a database file needs `hnsw_enable_experimental_persistence` | 117 s |
| Qdrant local | `:memory:` | local mode can write to a `path` instead | 477 s |
| Chroma | persistent client | automatic | none (reopen) |
| LanceDB (both) | on disk | automatic | none (reopen) |
| zvec | on disk | automatic | none (reopen) |
| sqlite-vec | database file | automatic | none (reopen) |

In-memory engines have three costs:
- **RAM:** the whole index must fit in memory, 6-16 GB at 1M docs here, with Qdrant local peaking at 21 GB.
- **Restarts:** after a restart or crash the index is rebuilt unless it was saved.
- **Unsaved changes:** with an explicit save (Moss to disk, FAISS), changes since the last save are lost on a crash.

Disk-backed engines reopen without rebuilding, though reopen time was not measured. They lean on the OS file cache, so their search speed depends on how much of the index stays cached.

## Filtered search

Filtering splits the approximate engines in two: those that stay fast lose most of their recall (FAISS-HNSW, DuckDB-VSS), and those that keep recall slow down by 10-100x in some cases (Chroma, zvec). Moss and FAISS-flat stay exact at a few ms.

cohere-100k, k = 100, inner product. Each cell is recall@100 / mean latency (warm cache), with recall measured against exact search within the filtered set.

| Engine | No filter | id filter keeping 99% | id filter keeping 1% | label keeping 1% | label keeping 50% |
|---|---|---|---|---|---|
| Moss | 1.000 / 1.89 ms | 1.000 / 4.61 ms | 1.000 / 4.49 ms | 1.000 / 3.34 ms | 1.000 / 4.28 ms |
| FAISS-flat | 1.000 / 1.26 ms | 1.000 / 4.04 ms | 1.000 / 0.14 ms | 1.000 / 0.43 ms | 1.000 / 4.48 ms |
| FAISS-HNSW | 0.699 / 0.10 ms | 0.697 / 0.11 ms | 0.056 / 0.10 ms | 0.048 / 0.37 ms | 0.566 / 0.67 ms |
| zvec | 0.997 / 1.63 ms | 0.997 / 177 ms | 1.000 / 2.03 ms | 1.000 / 0.25 ms | 0.999 / 2.57 ms |
| Chroma | 0.909 / 1.86 ms | 0.909 / 101 ms | 0.989 / 38.4 ms | 0.991 / 40.5 ms | 0.931 / 55.9 ms |
| LanceDB-HNSW | 0.950 / 2.85 ms | 0.950 / 4.33 ms | 0.980 / 2.42 ms | 0.979 / 3.12 ms | 0.958 / 5.90 ms |
| DuckDB-VSS | 0.913 / 2.69 ms | 0.912 / 2.78 ms | 0.012 / 2.73 ms | 0.010 / 2.73 ms | 0.492 / 2.77 ms |
| LanceDB IVF-PQ | 0.489 / 2.99 ms | 0.490 / 4.78 ms | 0.675 / 2.56 ms | 0.672 / 3.45 ms | 0.508 / 4.84 ms |
| Qdrant local | 1.000 / 17.1 ms | 1.000 / 274 ms | 1.000 / 271 ms | 1.000 / 278 ms | 1.000 / 278 ms |
| sqlite-vec | 1.000 / 73.3 ms | 1.000 / 73.3 ms | 1.000 / 30.9 ms | 1.000 / 32.0 ms | 1.000 / 59.2 ms |

DuckDB-VSS applies the filter after the index search, so a filter keeping 1% leaves almost nothing of the top 100. FAISS-HNSW's recall also collapses when a filter keeps 1% of docs, at its default setting.

## Growing an index

Corpora grow, so the cost of adding documents matters as much as the first build. Setup:
- Data: the first 250k docs of dbpedia-openai-1m, inner product, no metadata.
- Incremental: build 10k, then add 90k and then 150k to the same index with each library's own API (LanceDB: `add()` then `optimize()`; zvec: `insert()` then `optimize()`).
- Full builds from scratch at 100k and 250k for comparison; 1M times come from the main runs.
- One run each. After each step, 20 of the added docs searched by their own vector came back first (19 of 20 for LanceDB-HNSW at 250k). Search quality after incremental adds was not measured.

| Engine | Build time per doc at 10k | 100k | 250k | 1M | Add 150k docs to a 100k index | Full build of 250k |
|---|---|---|---|---|---|---|
| Moss | 58 µs | 54 µs | 53 µs | 55 µs | 8.5 s | 13.3 s |
| FAISS-flat | 2 µs | <1 µs | <1 µs | 1 µs | 0.4 s | 0.1 s |
| FAISS-HNSW | 24 µs | 39 µs | 45 µs | 51 µs | 7.2 s | 11.3 s |
| zvec | 179 µs | 455 µs | 632 µs | 844 µs | 92.4 s | 158.0 s |
| Chroma | 181 µs | 252 µs | 276 µs | 422 µs | 44.7 s | 69.1 s |
| LanceDB-HNSW | 43 µs | 86 µs | 98 µs | 115 µs | 12.7 s | 24.6 s |
| DuckDB-VSS | 97 µs | 94 µs | 107 µs | 118 µs | 114.4 s | 26.8 s |
| LanceDB IVF-PQ | 277 µs | 223 µs | 96 µs | 29 µs | 1.9 s | 24.1 s |
| Qdrant local | 357 µs | 376 µs | 405 µs | 482 µs | 63.4 s | 101.2 s |
| sqlite-vec | 180 µs | 167 µs | 167 µs | 165 µs | 29.7 s | 41.7 s |

- **Steady cost per doc:** Moss and sqlite-vec (flat from 10k to 1M), DuckDB-VSS (+22%). Build time grows in proportion to the corpus.
- **Rising cost per doc:** zvec (4.7x from 10k to 1M), Chroma (2.3x), LanceDB-HNSW (2.7x), FAISS-HNSW (2.1x) and Qdrant local (1.35x). Each new document costs more as the index grows.
- **Adding vs rebuilding:** for most engines, adding 150k docs to a 100k index took 52-71% of a full 250k build, about the cost of indexing the new docs alone.
- **DuckDB-VSS:** inserting into a table that already has an HNSW index took 4.3x longer than a full build of all 250k docs, so for bulk loads a rebuild was faster here.
- **LanceDB IVF-PQ:** `optimize()` added the new rows to the existing index in 1.9 s, against 24 s for a full build. Its full-build cost per doc falls as the corpus grows. Whether recall holds after many such additions was not measured.

## Text search (SciFact)

SciFact is the most realistic test here: real scientific claims as queries, real abstracts as documents, and human relevance judgments. Its score, nDCG@10, measures whether the relevant documents come back near the top, not only whether the nearest vectors do.

nDCG@10 with each engine's default settings, k = 10:

- **Moss:** 0.685. Moss's default hybrid search (keyword + vector) uses its built-in embedding model inside the index build and each query.
- **Other engines:** 0.654 for the exact engines and zvec, and 0.644-0.652 for the other approximate ones; LanceDB IVF-PQ scored 0.539. These engines search by vector only. Their corpus embeddings were generated ahead of time with all-MiniLM-L6-v2 (68 s for the corpus), and each query was embedded with the same model at search time, inside the measured latency.
- **Latency** with query embedding was 1.1-3.3 ms for every engine (Moss 2.13 ms).
- **Build:** Moss took 152 s, including its embedding. The other engines took 68 s for the embedding plus under 0.5 s to index.

## Engines: benefits and tradeoffs

| Engine | Benefits | Tradeoffs | Fits |
|---|---|---|---|
| **Moss** | Exact results with no tuning; as fast as FAISS-flat at 1M docs (25 ms, inner product); exact filtered search at a few ms; hybrid keyword + vector text search; index on disk or in Moss cloud | Latency grows with corpus size, less than proportionally from 25k to 100k docs (4x the docs: 2.7x the latency; 25 ms at 1M); slower text build | Correct results and filters without tuning effort; growing corpora (steady build cost per doc); text retrieval |
| FAISS-flat | Exact; builds in about 1 s; exact filters; saves to disk (`write_index()`) | A library, not a database: no storage layer or metadata (filters need your own id mapping) | An exact baseline inside your own data layer |
| FAISS-HNSW | Lowest latency at 0.95 recall (0.45 ms at 1M); saves to disk (`write_index()`) | 0.855 recall at defaults; recall plummets when filters applied; must be tuned and re-tuned | Unfiltered, latency-critical search with a team to maintain tuning |
| zvec | Lowest latency at 0.99 recall (1.51 ms at 1M); 0.998 recall at defaults; low RAM; on disk | Slowest build (14 min at 1M), and cost per doc rises with index size (4.7x from 10k to 1M); 177 ms with a filter keeping 99% | Read-heavy data that is rebuilt rarely |
| Chroma | 0.964 recall at defaults; simple API; on disk | Slow filtered search, up to ~100 ms; 2.7x slower with inner product than with its default l2 | Prototypes and small to medium collections |
| LanceDB-HNSW | Low RAM; 0.95-0.98 filtered recall; on disk | 0.849 recall at defaults; best recall@10 at 1M: 0.988 | Disk-resident data with moderate recall needs |
| DuckDB-VSS | Vector search inside SQL | Largest in-memory index (15.7 GB at 1M); recall plummets when filters applied (post-filtering); adding docs to an indexed table 4.3x slower than rebuilding; on-disk index experimental | Analytics in DuckDB without selective filters |
| LanceDB IVF-PQ | Fast build (28 s at 1M); compressed index; on disk | 0.53 recall at defaults; best recall@10 at 1M: 0.974 | Very large data where memory matters more than recall |
| Qdrant local | Exact; same API as the Qdrant server | Brute force in local mode: 952 ms at 1M, 21 GB peak; filtered queries ~275 ms at 100k | Development before moving to a Qdrant server |
| sqlite-vec | Tiny RAM; plain SQLite file | Brute force: 0.68-1.37 s at 1M | Small collections, edge and embedded apps |

## Limits

- Each configuration was measured once, on one machine. No confidence intervals.
- CPU time per query was not measured; engines use different numbers of cores per query.
- Index builds of Chroma, DuckDB-VSS, LanceDB and zvec are not reproducible, so their recall varies slightly between runs.
- FAISS-HNSW's first measured passes after its dbpedia-openai-1m build ran 1.2-2.4x slower than the same setting measured later in the run (k = 10, default distance: 0.320 ms against 0.138 ms). Its default-settings latency there is overstated.
- DuckDB-VSS was slower at k = 50 than at k = 100 in every run (cohere-100k: 3.33 vs 2.69 ms).
- Each engine returns its library's default payload (e.g. LanceDB returns every column, the vector included), which costs more as k grows.
