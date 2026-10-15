# Embedded vector search: detailed results

Summary: [RESULTS.md](RESULTS.md). Methods, options and known behaviors: [README.md](README.md).

## Setup

- **Machine:** Apple M5 Max, 18 cores, 128 GiB RAM, macOS 26.6.2. Runs in October 2026, commit `3d169e8`.

- **Engines:**
  - Moss 1.16.1 (core 0.30.1)
  - Chroma 1.5.9
  - LanceDB 0.40.0 (IVF-PQ and IVF-HNSW-SQ)
  - Qdrant client 1.19.1 (local mode)
  - FAISS 1.15.1 (flat and HNSW)
  - zvec 0.7.0, sqlite-vec 0.1.9
  - DuckDB 1.5.6 + vss
  
  All in-process, with each library's default index build settings (see the README's engine table).

- **Datasets:**
  - dbpedia-openai-1m: 990k docs, 1536-d OpenAI embeddings, 1,000 queries.
  - cohere-100k: 100k docs, 768-d, 1,000 queries. Also used for filters and corpus scaling.
  - SciFact: 5,183 abstracts, 300 test queries, human relevance labels.

- **Method:**
  - Queries run one at a time from one client, after 100 unmeasured warm-up queries. Latency is wall-clock time per call.
  - Recall@k (R in tables) is measured against exact search; text quality is nDCG@10 against the human labels.
  - One run per configuration, no repeats.

- **Metric:** vectors are normalized, so inner product (the dataset metric) and each library's default distance give the same exact results. Approximate indexes can differ in speed and recall between the two. Numbers below use inner product unless noted.

- **Bold** marks the best value in each comparison (column, unless a table says otherwise), including values within 0.002 of it for recall and nDCG, or within 5% for time and size. Memory and disk sizes are in MiB and GiB (2^20 and 2^30 bytes).

## What recall means for an application

Recall@10 is the share of a query's 10 best matches (by embedding similarity, as exact search finds them) that an engine returns, averaged over queries. Each miss is silently replaced by a weaker match:

| recall@10   | Best matches missed per query | Engines at default settings (1M docs)              |
| :---------: | :---------------------------: | -------------------------------------------------- |
|     1.0     |               0               | Moss, FAISS-flat, Qdrant local, sqlite-vec (exact) |
|    0.998    |              0.02             | zvec                                               |
| 0.951-0.964 |           0.36-0.49           | Chroma, DuckDB-VSS                                 |
|     0.85    |              1.5              | FAISS-HNSW, LanceDB-HNSW                           |
|     0.53    |              4.7              | LanceDB IVF-PQ                                     |

In retrieval-augmented generation (RAG), a missed document is context the model never sees. If it held the answer, the response rests on weaker evidence, and nothing reports it.

Recall is an average: at 0.95, most queries may miss nothing while a few miss several. It is also measured against exact vector search, so it adds to the embedding model's own relevance limit. On SciFact, exact vector search over all-MiniLM-L6-v2 embeddings reached nDCG@10 0.654; at default settings the HNSW-based engines scored up to 0.010 lower, and LanceDB IVF-PQ 0.115 lower.

## Results at 1M docs

dbpedia-openai-1m, k = 10, inner product. Compare engines down each column.

| Engine         | recall@10 at defaults | p95 at defaults (ms) | Fastest p95 at R ≥ 0.95 (ms) | Fastest p95 at R ≥ 0.99 (ms) | Build (s) | Index in RAM (GiB) | Search max memory (GiB) | Index on disk (GiB) |
| -------------- | :-------------------: | :------------------: | :--------------------------: | :--------------------------: | :-------: | :----------------: | :---------------------: | :-----------------: |
| Moss           |       **1.000**       |         27.8         |             27.8             |             27.8             |     55    |        6.0         |           6.1           |         N/A         |
| FAISS-flat     |       **1.000**       |         25.0         |             25.0             |             25.0             |  **0.6**  |        5.7         |           5.7           |         N/A         |
| FAISS-HNSW     |         0.855         |       **0.21**       |          **0.67\***          |            3.82\*            |     51    |        6.2         |           6.2           |         N/A         |
| zvec           |       **0.998**       |         5.48         |            0.93\*            |          **2.22\***          |    836    |        0.12        |           0.12          |         6.12        |
| Chroma         |         0.964         |         3.17         |             3.17             |            15.7\*            |    418    |        6.3         |           6.3           |         6.01        |
| LanceDB-HNSW   |         0.849         |         1.90         |            3.61\*            |      5.35\* <br>R=0.988      |    114    |        2.3         |           4.6           |         7.31        |
| DuckDB-VSS     |         0.951         |         6.44         |             6.44             |            9.40\*            |    117    |        15.7        |           15.7          |         N/A         |
| LanceDB IVF-PQ |         0.531         |         6.28         |            7.98\*            |      9.81\* <br>R=0.974      |     28    |        3.2         |           3.2           |       **5.76**      |
| Qdrant local   |       **1.000**       |         961          |             961              |             961              |    477    |        9.7         |           21.1          |         N/A         |
| sqlite-vec     |       **1.000**       |        1,384         |            1,384             |            1,384             |    163    |      **0.01**      |         **0.02**        |       **5.72**      |

\* Needs a non-default setting (tuning). Unmarked values use the library defaults.

- **Fastest p95 at R ≥ X:** the lowest p95 latency among the measured settings that reach that recall; the default's value is shown when it reaches X within 5% of the fastest. Where no setting reached it, the cell shows the best R over the settings tried and that setting's p95 (LanceDB's `nprobes` was not part of the sweep).
- **Build:** ingest and index build. Moss's session setup (a round trip to Moss cloud, about 1 s) is not timed; the other engines' local client setup is.
- **Index in RAM:** process memory added by the index after the build. **Search max memory:** its peak during search. Both leave out the OS file cache that holds disk-backed indexes.
- **Index on disk:** N/A for in-memory engines, which can save to disk but weren't saved here (see [In-memory vs on-disk](#in-memory-vs-on-disk)).

With each library's default distance instead of inner product, three engines change speed by 1.5x or more (p95 at k = 10; bold: faster per row):

| Engine     | Default distance (ms) | Inner product (ms) |
| ---------- | :-------------------: | :----------------: |
| Chroma     |     **1.14** (l2)     |        3.17        |
| FAISS-flat |       47.9 (l2)       |      **25.0**      |
| sqlite-vec |      **681** (l2)     |   1,384 (cosine)   |

The distance can also change recall: LanceDB IVF-PQ reached R=0.662 with l2 and R=0.531 with inner product. FAISS-HNSW's default-distance run was slowed by a post-build effect (see Limits).

## The cost of tuning

Approximate indexes expose a speed/recall knob (HNSW `ef`, LanceDB `refine_factor`), and the defaults leave recall behind. Tuning is not a one-time step:

- **Measuring recall needs ground truth your data doesn't have.** Benchmarks ship the exact nearest neighbours of every query. For your own data you must sample representative queries, run an exact search over the whole corpus for each, and compare. Measuring answer quality instead needs human relevance labels, as SciFact has.
- **The right setting drifts as the corpus grows.** At unchanged defaults, recall@100 fell as cohere-100k grew:

  | Engine                           | 25k docs  | 50k docs  | 75k docs  | 100k docs |
  | -------------------------------- | :-------: | :-------: | :-------: | :-------: |
  | FAISS-HNSW                       |   0.727   |   0.709   |   0.705   |   0.699   |
  | Chroma                           |   0.934   |   0.922   |   0.914   |   0.909   |
  | DuckDB-VSS                       |   0.937   |   0.924   |   0.917   |   0.913   |
  | LanceDB IVF-PQ                   |   0.542   |   0.517   |   0.500   |   0.489   |
  | LanceDB-HNSW                     |   0.961   |   0.956   |   0.953   |   0.950   |
  | zvec                             | **0.999** | **0.998** |   0.998   |   0.997   |
  | Moss and the other exact engines | **1.000** | **1.000** | **1.000** | **1.000** |

  FAISS-HNSW needed ef 160 for recall@10 ≥ 0.99 on cohere-100k and ef 768 on dbpedia-openai-1m. The datasets differ, but the direction holds: larger corpora need higher settings, which are slower.
- **Filters change recall too.** A setting tuned on unfiltered queries says little about filtered ones (see [Filtered search](#filtered-search)).
- **The cost recurs.** Corpus growth, shifts in what users ask, and a new embedding model each invalidate the last tuning. Measure again or accept unknown recall.

Exact engines (Moss, FAISS-flat, Qdrant local, sqlite-vec) have nothing to tune: recall is 1.0 by construction. Their cost is latency, which grows with corpus size. cohere-100k, k = 100:

| Engine       | Mean latency at 25k docs (ms) | Mean latency at 100k docs (ms) |
| ------------ | :---------------------------: | :----------------------------: |
| Moss         |              0.70             |              1.90              |
| FAISS-flat   |            **0.38**           |            **1.27**            |
| Qdrant local |              4.71             |             17.35              |
| sqlite-vec   |              18.6             |              73.6              |

## In-memory vs on-disk

| Engine             | Storage as tested     | Persistence                                                                                                        | Rebuild after restart without a save, 1M docs |
| ------------------ | --------------------- | ------------------------------------------------------------------------------------------------------------------ | :-------------------------------------------: |
| Moss               | in memory (not saved) | `save_to_disk()` / `load_from_disk()`, or a Moss cloud index cached locally; standard in production, not used here |                      55 s                     |
| FAISS (flat, HNSW) | in memory             | `write_index()` / `read_index()`                                                                                   |           0.6 s (flat), 51 s (HNSW)           |
| DuckDB-VSS         | in-memory database    | HNSW in a database file needs `hnsw_enable_experimental_persistence`                                               |                     117 s                     |
| Qdrant local       | `:memory:`            | can write to a `path` instead                                                                                      |                     477 s                     |
| Chroma             | persistent client     | automatic                                                                                                          |                 none (reopen)                 |
| LanceDB (both)     | on disk               | automatic                                                                                                          |                 none (reopen)                 |
| zvec               | on disk               | automatic                                                                                                          |                 none (reopen)                 |
| sqlite-vec         | database file         | automatic                                                                                                          |                 none (reopen)                 |

Save, load and reopen times were not measured.

In-memory engines have three costs:
- **RAM:** the whole index must fit in memory: 6-16 GiB at 1M docs here, with Qdrant local peaking at 21 GiB.
- **Restarts:** after a restart or crash, the index is rebuilt unless it was saved.
- **Unsaved changes:** with an explicit save (Moss, FAISS), changes since the last save are lost on a crash.

Disk-backed engines reopen without a rebuild, but rely on the OS file cache: search speed depends on how much of the index stays cached.

## Filtered search

Filtering splits the approximate engines in two: those that stay fast lose most of their recall (FAISS-HNSW, DuckDB-VSS), and those that keep recall slow down 20-110x on some filters (Chroma, zvec). Moss and FAISS-flat stay exact at a few ms.

cohere-100k, k = 100, inner product, warm cache. R is recall@100, measured against exact search within the filtered set; ms is mean latency. id filters keep docs above an id cutoff; label filters keep docs with one label (VectorDBBench filter cases). Compare engines down each column.

| Engine         | No filter (R) | No filter (ms) | id, 99% kept (R) | id, 99% kept (ms) | id, 1% kept (R) | id, 1% kept (ms) | label, 1% kept (R) | label, 1% kept (ms) | label, 50% kept (R) | label, 50% kept (ms) |
| -------------- | :-----------: | :------------: | :--------------: | :---------------: | :-------------: | :--------------: | :----------------: | :-----------------: | :-----------------: | :------------------: |
| Moss           |   **1.000**   |      1.89      |    **1.000**     |        4.61       |    **1.000**    |       4.49       |     **1.000**      |         3.34        |      **1.000**      |         4.28         |
| FAISS-flat     |   **1.000**   |      1.26      |    **1.000**     |        4.04       |    **1.000**    |       0.14       |     **1.000**      |         0.43        |      **1.000**      |         4.48         |
| FAISS-HNSW     |     0.699     |    **0.10**    |      0.697       |      **0.11**     |      0.056      |     **0.10**     |       0.048        |         0.37        |        0.566        |       **0.67**       |
| zvec           |     0.997     |      1.63      |      0.997       |        177        |    **1.000**    |       2.03       |     **1.000**      |       **0.25**      |      **0.999**      |         2.57         |
| Chroma         |     0.909     |      1.86      |      0.909       |        101        |      0.989      |       38.4       |       0.991        |         40.5        |        0.931        |         55.9         |
| LanceDB-HNSW   |     0.950     |      2.85      |      0.950       |        4.33       |      0.980      |       2.42       |       0.979        |         3.12        |        0.958        |         5.90         |
| DuckDB-VSS     |     0.913     |      2.69      |      0.912       |        2.78       |      0.012      |       2.73       |       0.010        |         2.73        |        0.492        |         2.77         |
| LanceDB IVF-PQ |     0.489     |      2.99      |      0.490       |        4.78       |      0.675      |       2.56       |       0.672        |         3.45        |        0.508        |         4.84         |
| Qdrant local   |   **1.000**   |      17.1      |    **1.000**     |        274        |    **1.000**    |       271        |     **1.000**      |         278         |      **1.000**      |         278          |
| sqlite-vec     |   **1.000**   |      73.3      |    **1.000**     |        73.3       |    **1.000**    |       30.9       |     **1.000**      |         32.0        |      **1.000**      |         59.2         |

DuckDB-VSS filters after the index search (post-filtering), so a filter keeping 1% leaves almost none of the top 100. FAISS-HNSW's recall also collapses with a 1% filter at its default setting.

## Growing an index

Corpora grow, so the cost of adding documents matters as much as the first build. Setup:
- Data: the first 250k docs of dbpedia-openai-1m, inner product, no metadata.
- Incremental: build 10k, then add 90k, then 150k to the same index with each library's own API (LanceDB: `add()` then `optimize()`; zvec: `insert()` then `optimize()`).
- Full builds from scratch at 100k and 250k for comparison; 1M times come from the main runs.
- One run each. After each step, 20 of the added docs searched by their own vector came back first (19 of 20 for LanceDB-HNSW at 250k). Search quality after adds was not measured.

| Engine         | Build per doc at 10k (µs) | at 100k (µs) | at 250k (µs) | at 1M (µs) | +150k docs to 100k index (s) | Full build of 250k (s) |
| -------------- | :-----------------------: | :----------: | :----------: | :--------: | :--------------------------: | :--------------------: |
| Moss           |             58            |      54      |      53      |     55     |             8.5              |          13.3          |
| FAISS-flat     |           **2**           |    **<1**    |    **<1**    |   **<1**   |           **0.4**            |        **0.1**         |
| FAISS-HNSW     |             24            |      39      |      45      |     51     |             7.2              |          11.3          |
| zvec           |            179            |     455      |     632      |    844     |             92.4             |         158.0          |
| Chroma         |            181            |     252      |     276      |    422     |             44.7             |          69.1          |
| LanceDB-HNSW   |             43            |      86      |      98      |    115     |             12.7             |          24.6          |
| DuckDB-VSS     |             97            |      94      |     107      |    118     |            114.4             |          26.8          |
| LanceDB IVF-PQ |            277            |     223      |      96      |     29     |             1.9              |          24.1          |
| Qdrant local   |            357            |     376      |     405      |    482     |             63.4             |         101.2          |
| sqlite-vec     |            180            |     167      |     167      |    165     |             29.7             |          41.7          |

- **Steady cost per doc:** Moss and sqlite-vec (flat from 10k to 1M), DuckDB-VSS (+22%). Build time grows in proportion to the corpus.
- **Rising cost per doc:** zvec (4.7x from 10k to 1M), LanceDB-HNSW (2.7x), Chroma (2.3x), FAISS-HNSW (2.1x), Qdrant local (1.35x). Each new doc costs more as the index grows.
- **Adding vs rebuilding:** for most engines, adding 150k docs to a 100k index took 52-71% of a full 250k build, about the cost of indexing the new docs alone.
- **DuckDB-VSS:** inserting into a table with an HNSW index took 4.3x longer than a full build of all 250k docs; for bulk loads, rebuilding was faster.
- **LanceDB IVF-PQ:** `optimize()` added the new rows to the existing index in 1.9 s, against 24 s for a full build, and its full-build cost per doc falls as the corpus grows. Whether recall holds after many such adds was not measured.

## Text search (SciFact)

SciFact is the most realistic test here: real scientific claims as queries, real abstracts as documents, and human relevance judgments. Its score, nDCG@10, measures whether relevant documents rank near the top, not only whether the nearest vectors come back.

Default settings, k = 10. Moss uses its default hybrid search (keyword + vector) and built-in embedding model. The other engines search by vector only, over all-MiniLM-L6-v2 embeddings generated ahead of time; each query is embedded with the same model inside the measured latency. Compare engines down each column.

| Engine         | nDCG@10   | recall@10 (labels) | R-precision | Mean latency (ms) | p95 latency (ms) | Embed + build (s) | Index in RAM (MiB) | Search max memory (MiB) | Index on disk (MiB) |
| -------------- | :-------: | :----------------: | :---------: | :---------------: | :--------------: | :---------------: | :----------------: | :---------------------: | :-----------------: |
| Moss           | **0.685** |     **0.813**      |  **0.538**  |        2.13       |       3.35       |        152        |       1,760        |          1,766          |         N/A         |
| FAISS-flat     |   0.654   |       0.808        |    0.496    |        1.25       |       1.88       |   **68 + <0.01**  |         8          |            14           |         N/A         |
| FAISS-HNSW     |   0.645   |       0.791        |    0.492    |      **1.15**     |     **1.79**     |   **68 + 0.04**   |         9          |            15           |         N/A         |
| zvec           |   0.654   |       0.808        |    0.496    |        1.57       |       2.19       |   **68 + 0.40**   |         27         |            33           |         13.4        |
| Chroma         |   0.651   |       0.805        |    0.492    |        1.79       |       2.42       |   **68 + 0.42**   |         7          |          **12**         |         19.4        |
| LanceDB-HNSW   |   0.644   |       0.790        |    0.493    |        2.57       |       3.22       |   **68 + 0.11**   |         52         |            62           |         10.5        |
| DuckDB-VSS     |   0.652   |       0.805        |    0.496    |        3.16       |       3.80       |   **68 + 0.21**   |         41         |            62           |         N/A         |
| LanceDB IVF-PQ |   0.539   |       0.717        |    0.371    |        2.53       |       3.20       |   **68 + 0.48**   |         51         |            59           |       **8.1**       |
| Qdrant local   |   0.654   |       0.808        |    0.496    |        1.80       |       2.40       |   **68 + 0.48**   |         53         |            72           |         N/A         |
| sqlite-vec     |   0.654   |       0.808        |    0.496    |        3.26       |       3.81       |   **68 + 0.04**   |       **4**        |            14           |         9.3         |

- **recall@10 (labels):** share of a query's human-labeled relevant docs in the top 10 (not R, which is measured against exact search). **R-precision:** precision at rank r, where r is the query's number of relevant docs.
- **Embed + build:** Moss embeds the corpus inside its build. The other engines share one 68 s MiniLM embedding pass, plus their own index build.
- **Memory:** Moss's figures cover everything its build added, its embedding work included. The other engines' figures leave out the MiniLM query embedder, which was loaded before the memory baseline.

## Engines: benefits and tradeoffs

| Engine | Benefits | Tradeoffs | Use it when... |
|---|---|---|---|
| **Moss** | Exact results, no tuning; within 7% of FAISS-flat at 1M docs (25.2 vs 23.6 ms mean); exact filtered search in a few ms; hybrid keyword + vector search; index on disk or in Moss cloud | Latency grows with corpus size, sub-linearly from 25k to 100k docs (4x the docs, 2.7x the latency); slower text build | you want exact results, hybrid search, fast filtered queries and low latency (2 ms @100k docs, 25 ms @1M) with no tuning, and have RAM for the whole index |
| FAISS-flat | Exact; builds in under 1 s; exact filters; saves to disk (`write_index()`) | A library, not a database: no storage layer or metadata (filters need your own id mapping) | you want exact results, low latency and fast builds, have RAM for the whole index, and don't need hybrid search or built-in metadata storage |
| FAISS-HNSW | Lowest p95 at R ≥ 0.95 (0.67 ms at 1M); saves to disk (`write_index()`) | R=0.855 at defaults; recall plummets with selective filters; needs tuning and re-tuning | you want the lowest unfiltered latency, have RAM for the whole index, don't need filters, and don't mind regular re-tuning |
| zvec | Lowest p95 at R ≥ 0.99 (2.22 ms at 1M); R=0.998 at defaults; low RAM; on disk | Slowest build (14 min at 1M), and cost per doc rises with index size (4.7x from 10k to 1M); 177 ms with a filter keeping 99% | you want minimal RAM usage, don't need frequent updates (slow builds and inserts), and don't mind tuning that trades recall for latency |
| Chroma | R=0.964 at defaults; simple API; on disk | Slow filtered search, up to ~100 ms; 2.8x slower with inner product than with its default l2 | you want to prototype or search a small to medium collection, and don't mind tuning or slow filtered searches and builds |
| LanceDB-HNSW | Low RAM; R=0.95-0.98 with filters; on disk | R=0.849 at defaults; best recall@10 at 1M over the settings tried: 0.988 | you want low RAM usage and frequent filtered search, don't need recall above ~0.99, and don't mind re-tuning |
| DuckDB-VSS | Vector search inside SQL | Largest in-memory index (15.7 GiB at 1M); recall plummets with selective filters (post-filtering); adding docs to an indexed table 4.3x slower than rebuilding; on-disk index experimental | you want vector search in an existing DuckDB database, and don't need filters, incremental inserts or low RAM usage |
| LanceDB IVF-PQ | Fast build (28 s at 1M); compressed index; on disk | R=0.53 at defaults; best recall@10 at 1M over the settings tried: 0.974 | you want low RAM usage and fast builds for a very large corpus, don't need recall above ~0.97, and don't mind re-tuning |
| Qdrant local | Exact; same API as the Qdrant server | Brute force in local mode: 961 ms p95 at 1M, 21 GiB peak; filtered queries ~275 ms at 100k | you want to prototype for a Qdrant server and aren't building for edge retrieval |
| sqlite-vec | Tiny RAM; plain SQLite file | Brute force: 0.68-1.38 s p95 at 1M | you want minimal RAM usage for a small corpus (<100k docs), and don't need low latency |

## Limits

- One run per configuration, on one machine; no confidence intervals.
- FAISS-flat's dbpedia-openai-1m runs were repeated on 2026-10-15 after its adapter switched to one add call (adding 100k rows at a time had left about 4 GiB of freed buffers in its memory figure); the other runs are from 2026-10-13/14.
- CPU time per query was not measured; engines use different numbers of cores per query.
- Chroma, DuckDB-VSS, LanceDB and zvec index builds are not reproducible, so their recall varies slightly between runs.
- FAISS-HNSW's first passes after its dbpedia-openai-1m build ran 1.2-2.4x slower than the same setting measured later (k = 10, default distance, mean: 0.320 ms in the defaults run against 0.138 ms in the tuning run), so its default-distance latency there is overstated.
- DuckDB-VSS was slower at k = 50 than at k = 100 in every run (cohere-100k: 3.37 vs 2.70 ms).
- Each engine returns its library's default payload (e.g. LanceDB returns every column, the vector included), which costs more as k grows.
