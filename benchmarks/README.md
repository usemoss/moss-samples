# Moss standard vector-search benchmark

Compares Moss with nine local in-process engine setups on standard public datasets, using the methodology of VectorDBBench, qdrant's vector-db-benchmark and ann-benchmarks. Every engine runs **off the shelf**: its library's default index and search settings, so the comparison is what a user gets without tuning. Every run writes an interactive Plotly report and Markdown tables.

## What it measures

Three stages per (dataset, engine), run by `run.py`:

| Stage | What | Metrics |
|---|---|---|
| `load` | build the index | build seconds (ingest + index only), session setup seconds (`open_s`), docs/s, RSS before/after, memory footprint (baseline, after build, build peak), index size on disk |
| `serial` | one client, every sweep setting x every k (default 1, 10, 50, 100) | vector: recall@k and nDCG@k vs the exact top-k; text (k >= 10): nDCG@10, recall@k and R-precision vs human labels; mean/p50/p95/p99/p99.9 latency (ms) |
| `filter` | VectorDBBench filter cases at k=100 at the operating point, each scored against its own ground truth: a cold pass (first use of the filter) then a warm pass | recall@100, latency and first-query latency, per pass |

- **Recall@k** = `|got[:k] ∩ gt[:k]| / k` against the exact brute-force top-k. Both lists have k items, so it also equals precision@k, and an exact engine scores 1.0 by definition: it measures how closely an index matches exact search, not whether a person would find the results relevant. **nDCG@k** weights each hit by its ground-truth rank. Text datasets are scored against BEIR's human relevance labels: nDCG@10, recall@k and **R-precision** (relevant docs in the top R over R, R = that query's relevant-doc count; on hotpotqa every query has 2, so it is precision@2).
- **Latency** is per query in milliseconds. Percentiles are `numpy.percentile` (linear interpolation). Throughput is not reported: local Moss serves one user, and serial throughput is just 1 / mean latency.
- **Memory** is the physical footprint (Activity Monitor's "Memory"; it excludes clean file-backed pages such as the memory-mapped dataset), read with macOS `proc_pid_rusage`. Each stage's peak comes from `proc_reset_footprint_interval` (a private macOS API; no sampling thread, so latencies are untouched). The report shows values over the footprint after the dataset loads: index (after build), build peak, search peak. Disk-backed engines (chroma, lancedb, zvec, sqlite-vec) keep part of their index in files that the OS caches outside the process, so their index size on disk is shown too, plus the RSS increase over the build.
- **Sweep and operating point.** Every sweep starts with the library-default search setting (`{}`, shown as "default"), followed by the tuning knob's values, so the tradeoff chart shows both what you get out of the box and what tuning buys. The **operating point is the library default**; the latency and filter results use it. After it is restored, 100 unmeasured warm-up queries run.
- **Warm-up** (100 queries before each sweep setting and before the operating point) never uses a measured query: it takes the queries after the measured ones when at least 100 exist (`--queries` below the total), else 100 indexed docs (doc vectors, or corpus texts on text datasets). Warming up on measured queries made those queries 5-9% faster for zvec and about 6% for chroma (cohere-100k). Each result records its warm-up source.
- **Build time** covers ingest and index build only. Each engine's library is imported before the timer (imports took 0.02-0.39 s), and Moss's session is opened before it: `session()` authenticates, looks up a same-named cloud index and, for built-in models, loads the model (0.71 s with custom vectors, 0.99 s with moss-minilm, median on the M5 Max). That time is recorded as `open_s`.
- **Metric.** Vectors are L2-normalized, so l2, inner product and cosine rank documents identically; the distance setting still changes speed (faiss-flat 1.29 ms with inner product vs 2.42 ms with l2, chroma 1.43 vs 0.64 ms on cohere-100k). `--metric ip` sets inner product (cosine for sqlite-vec, which has none): this is the **dataset metric** (the datasets are cosine), which is how public benchmarks configure engines (ann-benchmarks' FAISS wrapper and VectorDBBench's Milvus GPU, Doris and Aliyun clients normalize, then use inner product or l2), and it is the report's primary section. `--metric default` keeps each library's default distance (the off-the-shelf view, secondary section). Engines whose default is already inner product (moss, qdrant-local, zvec) have no separate ip run; the report reuses their default run in the dataset-metric section.
- **Hardware and library versions** are recorded in every result file.

Metric sources:

- VectorDBBench [`metric.py`](https://github.com/zilliztech/VectorDBBench/blob/1760db1/vectordb_bench/metric.py) (recall, nDCG)
- qdrant [`engine/base_client/search.py`](https://github.com/qdrant/vector-db-benchmark/blob/871a0b2/engine/base_client/search.py) (recall, percentiles)
- ann-benchmarks [`plotting/metrics.py`](https://github.com/erikbern/ann-benchmarks/blob/2e081ad/ann_benchmarks/plotting/metrics.py) (recall, percentiles)

## Engines

Defaults read from the installed libraries (DuckDB's from its VSS docs). The ef sweep is 16, 32, 64, 100, 128, 160, 200, 256, 320, 400, 512, 768, 1024 (settings with ef < k are skipped at that k).

| Engine | Version | Index (library defaults) | Default search | Default metric / `ip` mode | Sweep | Filter mechanism |
|---|---|---|---|---|---|---|
| `moss` | 1.15.1 (`inferedge-moss-core` 0.28.1) | exact search via public `SessionIndex` | exact | inner product | none (text: `alpha` default 0.8, then 1.0) | metadata filter (`$gte`, `$eq`) |
| `chroma` | 1.5.9 | HNSW M 16, ef_construction 100, persistent client | ef 100 | l2 / ip | ef | `where` |
| `lancedb` | 0.40.0 | `create_index()`: IVF_PQ | no refine | l2 / dot | refine_factor 2, 5, 10, 20, 50 | `where` (prefilter, the default) |
| `lancedb-hnsw` | 0.40.0 | `IvfHnswSq()` (docs: best recall/latency for unfiltered search) | ef 1.5 x k | l2 / dot | ef | `where` (prefilter) |
| `qdrant-local` | qdrant-client 1.19.1 | local `:memory:` mode, always exact | exact | DOT (Qdrant requires a choice) | none | payload filter |
| `faiss-flat` | faiss-cpu 1.15.1 | `IndexFlat`, exact | exact | l2 / ip | none | `IDSelectorBatch` |
| `faiss-hnsw` | faiss-cpu 1.15.1 | `IndexHNSWFlat` M 32 (C++ default; Python requires M), efConstruction 40 | efSearch 16 | l2 / ip | efSearch | `IDSelectorBatch` |
| `zvec` | 0.7.0 | HNSW M 50, ef_construction 500 | ef 300 | inner product | ef | filter expression |
| `sqlite-vec` | 0.1.9 | `vec0` brute force, exact | exact | l2 / cosine | none | metadata columns |
| `duckdb-vss` | duckdb 1.5.6 + vss | HNSW M 16, ef_construction 128 | ef 64 | l2sq / ip | ef | `WHERE` |

Each search returns what the library returns by default (Chroma: metadata, documents and distances; Qdrant: payload; LanceDB: every column, the vector included; zvec: all scalar fields; FAISS: ids and distances; Moss: documents and metadata). The SQL engines select id and labels (sqlite-vec also the distance).

LanceDB setups: its docs say an exact scan "works fine below ~100K vectors, but past that you should build a dedicated vector index", call IVF_PQ the "General-purpose default; what Enterprise builds automatically", and IVF_HNSW_SQ "Best recall/latency for unfiltered search; higher latency variance under selective filters" ([performance](https://docs.lancedb.com/performance)); VectorDBBench's default LanceDB config is IVF_PQ. At the defaults on cohere-100k (200 queries) IVF_PQ reaches recall@10 0.55 (`refine_factor` 50: 0.99) and IVF_HNSW_SQ 0.87.

Versions come from `uv.lock`. Known behaviors:

- **Chroma:** a modified `ef_search` is stored but only applied after the client reopens, so the sweep reopens the persistent client. Those reopens inflate its serial-stage memory peak, which the memory chart's "search peak" includes.
- **DuckDB HNSW** applies `WHERE` after the index scan (post-filtering), so selective filters lose recall.
- **FAISS HNSW** with 1%-selectivity filters has low recall.
- **LanceDB HNSW** defaults to ef = 1.5 x k, so recall at k = 1 is low.
- **qdrant-local** keeps everything in memory: about 10.3 GB peak RSS at 100k x 768, so it is expected to DNF at 1M+.
- **DuckDB** downloads the `vss` extension into `~/.duckdb/extensions` on first use.

## Datasets

| Name | Source | Docs / queries | Dim / metric | License | Download |
|---|---|---|---|---|---|
| `cohere-100k` (smoke) | VectorDBBench Cohere | 100K / 1,000 | 768 / cosine | no data license stated; Cohere Wikipedia embeddings are Apache-2.0 (secondary source) | 313 MB |
| `cohere-1m` | VectorDBBench Cohere | 1M / 1,000 | 768 / cosine | same | 3.13 GB |
| `dbpedia-openai-1m` | HF `KShivendu/dbpedia-entities-openai-1M`, ann-benchmarks split | 990K / 10,000 | 1536 / angular | MIT | 9.52 GB |
| `arxiv-titles-2m` | Qdrant `arxiv_no_filters.tar.gz` (all-MiniLM-L6-v2) | 2,138,591 / ~15K | 384 / cosine | arXiv metadata CC0; tarball none stated | 3.10 GB |
| `hotpotqa-1m` | BEIR HotpotQA, VectorDBBench subset rule (qrel docs + corpus-order fill to 1M) | 1M / 7,405 | text (nDCG@10, Recall@100, R-precision) | CC BY-SA 4.0 | 654 MB + about 1.5 GB of vectors |

Ground truth is exact brute force (cohere sets ship VectorDBBench's; ours agrees 100% on cohere-100k). `--docs N` runs use the exact ground truth over the first N docs, `data/<name>/gt_docs<N>.npy`, which `run_suite.sh` creates with `bench_data.py subset-gt <name> <N>` in its own process (log `results/logs/subset-gt-<name>-<N>-<stamp>.log`); computing it inside the benchmark process inflated its memory baseline by up to 440 MB. `run.py` refuses a missing cache or one older than the dataset's `base.npy`. MS MARCO is excluded (non-commercial terms). Moss indexes `hotpotqa-1m` text with its built-in embedder; other engines use fastembed MiniLM at 512 tokens.

```bash
mkdir -p results/logs
./watchdog.sh results/logs/fetch-<name>-$(date +%Y%m%dT%H%M%S).log $PWD/.venv/bin/python bench_data.py fetch <name>
./watchdog.sh results/logs/prepare-<name>-$(date +%Y%m%dT%H%M%S).log $PWD/.venv/bin/python bench_data.py prepare <name>
```

Measured on a cohere-100k smoke run (Apple M5 Max): fetch 5 s (sha256-checked against `checksums.json`), prepare 1 s at 2078 MiB peak RSS. hotpotqa-1m: fetch 84 s, prepare 7442 s (embedding 7418 s) at 25903 MiB peak RSS. dbpedia-openai-1m: fetch 271 s (9.0 GB, 26 shards), prepare 79 s at 25710 MiB peak RSS. cohere-1m and arxiv-titles-2m are not measured yet. Prepare for the 1M sets is heavy (GB of RAM, large ground-truth matmuls): raise `WATCHDOG_MAX_S` (default 1200 s) as needed.

## Quick start

`MOSS_ENV_FILE` points at a dotenv file defining `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY` (or export those two instead).

Needs macOS (the watchdog uses `sysctl`), [uv](https://docs.astral.sh/uv/), and Moss credentials for the `moss` engine.

```bash
cd benchmarks
uv sync
export MOSS_ENV_FILE=/path/to/.env

mkdir -p results/logs
./watchdog.sh results/logs/fetch-cohere-100k-$(date +%Y%m%dT%H%M%S).log $PWD/.venv/bin/python bench_data.py fetch cohere-100k
./watchdog.sh results/logs/prepare-cohere-100k-$(date +%Y%m%dT%H%M%S).log $PWD/.venv/bin/python bench_data.py prepare cohere-100k
./run_suite.sh cohere-100k all --queries 200
./run_suite.sh cohere-100k all --queries 200 --metric ip
open results/report.html
```

- The watchdog prints `pid=... log=...` and a final `watchdog: rc=0 peak_rss_mb=... elapsed=...s` line. `cat` the log to see the command's output. It kills the job on memory pressure, RSS > 85% of RAM, or `WATCHDOG_MAX_S`.
- Every run gets its own log, never overwritten: `results/logs/<dataset>-<engine>[-ip][-docs<N>]-<stamp>.log`, and its result has the same name and stamp, `results/<dataset>/<engine>[-ip][-docs<N>]-<stamp>.json`. The newest stamp per run is the attempt the report checks. Fetch, prepare and subset ground-truth logs use a prefix (`fetch-`, `prepare-`, `subset-gt-`) plus a stamp, so the report ignores them.
- `run_suite.sh` first upgrades `moss` to the latest release, then runs one watchdogged process per (dataset, engine), then rebuilds the report. A failed or killed run prints `DNF <dataset> <engine>` and appears under DNF in the report.
- Launch python as `$PWD/.venv/bin/python` from `benchmarks/` under the watchdog, never `uv run`: the watchdog then measures the benchmark's RSS, and the stop pattern below matches it.
- Runaway job: `pkill -9 -f run_suite.sh; pkill -9 -f 'benchmarks/\.venv/bin/python'` (the loop first, or it logs a DNF and starts the next pair). The second pattern kills every benchmark python, so check `pgrep -fl 'benchmarks/\.venv/bin/python'` first. The watchdog is killed too, so the log ends without a `watchdog: rc=` line.

Results: `results/<dataset>/<engine>[-ip][-docs<N>]-<stamp>.json`, `results/summary.md`, `results/report.html` (works offline).

## Subsets

`run_suite.sh "<datasets>" "<engines>|all" [run.py options]`. Datasets and engines are space-separated lists. Run a single pair the same way, `./run_suite.sh <dataset> <engine> [options]`, so its log and result share a stamp. Write `--docs N` and `--metric ip`, not `--flag=value` (the log name needs them).

| Flag | Example | Effect |
|---|---|---|
| `--queries N` | `--queries 200` | first N queries |
| `--docs N` | `--docs 20000` | index the first N docs (1 to n_base - 1), exact ground truth over them (vector datasets; not with the filter stage on datasets that have filters) |
| `--stages` | `--stages serial` | `load` and `serial` always run; this selects `filter` |
| `--k` | `--k 10` | k values (default `1,10,50,100`; text datasets use those >= 10) |
| `--metric` | `--metric ip` | `default` (each library's default distance) or `ip` (inner product, cosine for sqlite-vec); `run_suite.sh` skips engines that have no ip mode |
| `--filters` | `--filters int_1p,label_50p` | filter cases (default `int_1p,int_99p,label_1p,label_50p`) |

Examples:

```bash
./run_suite.sh cohere-100k "moss faiss-hnsw zvec" --stages serial --k 10
./run_suite.sh cohere-100k "faiss-flat sqlite-vec" --docs 20000 --stages serial
for n in 100000 250000 500000; do ./run_suite.sh cohere-1m all --docs $n --stages serial --queries 1000 || break; done
```

`--docs` runs get their own `<dataset>-subsets` section, which opens with the scaling chart.

## Reading the report

`results/report.html` has a **Charts** tab and a **Tables** tab, and a dataset picker. Each dataset has up to three sections:
- `· dataset metric (cosine ≡ inner product on unit vectors)` (primary): `--metric ip` runs, plus the default runs of engines whose default is already inner product;
- `· library default metric`: each library's default distance;
- `-subsets`: `--docs` runs.

Every chart sits in a numbered card with its description, and cards are separated by a horizontal rule.

- **Chart 1, headline (vector datasets): latency at equal recall.** The mean latency of each engine's cheapest setting that reaches recall@k >= 0.95 or 0.99 (dropdown: k and target; opens at the largest k and 0.95). Public benchmarks compare speed at a recall threshold (Qdrant, VIBE: QPS at recall@100 >= 0.95, big-ann: recall@10 >= 0.9) rather than at library defaults. The bar label names the setting; a missing bar means the sweep never reached the target.
- **Chart 2: recall (vector) or nDCG@10 (text) vs latency.** The Pareto frontier per engine and k. As in ann-benchmarks' `create_pointset`, settings are scanned fastest first and a point is kept only when its quality is higher than every faster one, so at equal quality only the fastest stays. Exact engines are dotted horizontal lines ending at their point. A ring marks each swept engine's library-default setting, which may sit off the frontier. Dropdowns pick the latency statistic (mean, p50, p95, p99, p99.9) and k. Text sections lead with this chart (end-to-end latency, query embedding included).
- **Operating-point latency:** one bar per engine at the library default, at the largest k that every run measured (title states it; if the runs share no k, each bar's label names its k). Dropdown: mean, p50, p95, p99, p99.9.
- **Build cost** (time, docs/s). On text datasets, Moss embeds the corpus inside its build with its built-in model, while the other engines index vectors embedded once at prepare (fastembed all-MiniLM-L6-v2 at 512 tokens). That embedding time (`corpus_embed_s` in the dataset meta, measured at batch 256, not per run) is stacked on their bars, so every bar covers embedding plus indexing. The text operating-point table has a `corpus embed s` column.
- **Memory** (dropdown: index, build peak, search peak, RSS increase over the build, on disk): one bar per engine.
- **Filtered search:** one line per engine across the filter cases, from most to fewest docs kept, starting at an **unfiltered** point: the same engine's serial result at k = 100 and the same setting (not re-measured), so the drop from it is what the filter costs. Dropdown: warm recall, warm then cold latency, cold first-query latency. The filter table shows the same reference as `unfiltered recall@100` and `unfiltered mean ms`.
- **Axes:** linear from 0, except the trade-off chart's latency axis, which is log (latencies span 0.1 ms HNSW to 40+ ms exact scans). Dropdown views with the same unit share one fixed range, so switching mean / p50 / p95 / p99 / p99.9 never moves the axis, and the trade-off chart keeps one recall range across k.
- **Tables:** operating point, equal recall, full serial sweep, filter cases, memory, DNF.
  - Click a header to sort.
  - Each categorical column (engine, metric, setting, k, filter, target) has a value list above the table. Tick values to show only those rows: nothing ticked shows every row; values in one column are OR-ed and columns are AND-ed. "clear filters" unticks everything. The filtering is plain CSS, with no script.
  - The best value of each column among the shown rows is bold.
- **Example results** (text datasets, Tables tab): for 10 queries, each engine's top 5 at its operating point (from an unmeasured pass), with ✓ on documents the dataset labels relevant, so a person can judge the results directly.
- **Scaling** (`-subsets` section, from `--docs` runs): one line per run over corpus size, including the full run when it exists; the dropdown picks recall (or nDCG@10), latency, memory or build time.
- Hover for exact values and parameters; click a legend entry to hide an engine; double-click to isolate it.
- **DNF** = a run's newest log has no `wrote` line and no result exists for that run (killed by the watchdog, out of memory, or crashed). The table shows the log's last line.
- **STALE:** if an engine's newest attempt failed but an older result for the same run exists, `report.py` prints `STALE <log>: <last line>`, exits 1 and writes nothing, so an old number never stands in for a failed rerun. Read the log, fix the cause and rerun (or move the old result out of `results/` on purpose). Running `report.py` while a run is in progress stops here too.

## Moss notes

- **Exact search.** Recall is 1.0 against brute force; there are no ANN knobs, so each vector dataset gives one recall point per (dataset, k). On text datasets `alpha` (the SDK default 0.8 hybrid, then 1.0 vector only) is the sweep. Vector queries pass `alpha=1.0`, since there is no query text.
- **Normalization.** Moss scores by inner product without normalizing, so all vectors are L2-normalized for every engine (raw Cohere vectors: recall@100 0.41 against cosine).
- **Concurrency is not benchmarked** (local Moss serves one user). Calls serialize per session: an earlier cohere-100k run (Apple M5 Max, moss 1.15.1) measured 586 / 611 / 613 QPS at 1 / 4 / 16 clients while p99 grew 2.14 / 7.79 / 28.76 ms. One query already uses about 12 cores from 5k docs up.
- **Every run rebuilds the index** (no public save/load in Python) and consumes metered session minutes (about 2.5x query time, 0.8x build time).
- **Session setup is not build time.** `client.session()` authenticates, looks up a same-named cloud index and, for built-in models, loads the model, so a local session is not free of a cloud round trip on the public API. It runs in the adapter's `open()`, before the build timer, and is recorded as `open_s` (0.71 s custom, 0.99 s moss-minilm, median of 5 on the M5 Max).
- **Latest Moss is enforced.** `moss` is unpinned; `run_suite.sh` runs `uv lock --upgrade-package moss`, and `run.py` exits unless the installed version equals the newest PyPI release. Commit `uv.lock` when it changes.
- Credentials: `MOSS_ENV_FILE` (a dotenv file) or `MOSS_PROJECT_ID` / `MOSS_PROJECT_KEY`.

## Hardware

Apple M5 Max, 18 cores, 128 GB, recorded in every result file together with OS, Python and package versions.

## Phase 2

Served databases (Milvus, Qdrant server, ...) plug into the same engine contract in `engines.py`.
