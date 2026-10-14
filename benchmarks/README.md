# Moss standard vector-search benchmark

Compares Moss with nine local in-process engine setups on standard public datasets, using the methodology of VectorDBBench, qdrant's vector-db-benchmark and ann-benchmarks. Every engine runs **off the shelf**: its library's default index and search settings, so the comparison is what a user gets without tuning. Every run writes an interactive Plotly report and Markdown tables.

## Benchmarks

The suite is modular: each benchmark has its own runner, result files and report page, and a page reads only the results it names, so a change to one benchmark cannot break another. Shared code is small: `bench_data.py` (datasets), `engines.py` (engine adapters), `metrics.py` (quality and latency statistics), `harness.py` (load, build, timing, memory, result files) and `report_common.py` (page shell, chart and table helpers).

| Benchmark | Runner (`./run_suite.sh <suite> ...`) | Measures (one process per dataset x engine x metric) | Page |
|---|---|---|---|
| Default settings | `defaults` (`suite_defaults.py`) | build (time, docs/s, memory, disk); at the library-default search setting, one pass per k: latency and quality; search-stage memory peak; text datasets: example results | `defaults.html` |
| Tuning | `tuning` (`suite_tuning.py`) | every setting of an engine's primary search knob (`engine.sweep`, e.g. HNSW ef) and secondary knob (`engine.extra`, e.g. LanceDB-HNSW refine_factor), each at every k: latency and quality. Exact engines (one setting) are not run; their page uses their defaults runs | `tuning.html` |
| Filtered search | `filter` (`suite_filter.py`) | at default settings, k = 100: an unfiltered pass (the reference), then each VectorDBBench filter case cold and warm, against the case's own exact ground truth | `filter.html` |
| Scaling | `defaults` with `--docs N` | the default-settings measurements on the first N docs | `scaling.html` |

`report.py` builds each page in its own process (`BENCH_RESULTS=<dir>` builds them from another results directory, e.g. a copy kept for comparison) (`report_defaults.py`, `report_tuning.py`, `report_filter.py`, `report_scaling.py`) and writes `results/index.html`, which links the pages and shows any page that failed to build with its error.

## What it measures

- **Recall@k** = `|got[:k] ∩ gt[:k]| / k` against the exact brute-force top-k. Both lists have k items, so it also equals precision@k, and an exact engine scores 1.0 by definition: it measures how closely an index matches exact search, not whether a person would find the results relevant. **nDCG@k** weights each hit by its ground-truth rank. Text datasets are scored against BEIR's human relevance labels: nDCG@10, recall@k and **R-precision** (relevant docs in the top R over R, R = that query's relevant-doc count; on hotpotqa every query has 2, so it is precision@2).
- **Latency** is per query in milliseconds. Percentiles are `numpy.percentile` (linear interpolation). Throughput is not reported: local Moss serves one user, and serial throughput is just 1 / mean latency.
- **Memory** is the physical footprint (Activity Monitor's "Memory"; it excludes clean file-backed pages such as the memory-mapped dataset), read with macOS `proc_pid_rusage`. Each stage's peak comes from `proc_reset_footprint_interval` (a private macOS API; no sampling thread, so latencies are untouched). The report shows values over the footprint after the dataset loads: index (after build), build peak, search peak. Disk-backed engines (chroma, lancedb, zvec, sqlite-vec) keep part of their index in files that the OS caches outside the process, so their index size on disk is shown too, plus the RSS increase over the build.
- **Default settings** means no `set_search()` call after the build: the engine searches exactly as the library ships it (`defaults` and `filter` suites). The `tuning` suite applies each setting with `set_search()`; `{}` restores the library default, so its first row is the default again.
- **Warm-up** (100 queries before the measured passes of each run, and before each tuning setting) never uses a measured query: it takes the queries after the measured ones when at least 100 exist (`--queries` below the total), else, on text datasets, 100 train-split queries (`warmup.jsonl`, written at prepare; they never overlap the measured test queries), else 100 indexed doc vectors. With corpus texts as the warm-up instead, Chroma's and LanceDB's first measured pass on scifact was 1.3-1.6x slower in mean latency than their next pass. Warming up on measured queries made those queries 5-9% faster for zvec and about 6% for chroma (cohere-100k). Each result records its warm-up source.
- **Build time** covers ingest and index build only. Each engine's library is imported before the timer (imports took 0.02-0.39 s), and Moss's session is opened before it: `session()` authenticates, looks up a same-named cloud index and, for built-in models, loads the model (0.71 s with custom vectors, 0.99 s with moss-minilm, median on the M5 Max). That time is recorded as `open_s`.
- **Metric.** Vectors are L2-normalized, so l2, inner product and cosine rank documents identically; the distance setting still changes speed (faiss-flat's inner-product scan took 1.26 ms against 2.44 ms with l2 at k = 100 on cohere-100k, 2026-10-13). `--metric ip` sets inner product (cosine for sqlite-vec, which has none): this is the **dataset metric** (the datasets are cosine), which is how public benchmarks configure engines (ann-benchmarks' FAISS wrapper and VectorDBBench's Milvus GPU, Doris and Aliyun clients normalize, then use inner product or l2), and it is the report's default view. `--metric default` keeps each library's default distance (the off-the-shelf view, the report's other metric view). Engines whose default is already inner product (moss, qdrant-local, zvec) have no separate ip run; the report shows their default run in both views.
- **Hardware, library versions, the git commit and whether the code had uncommitted changes** are recorded in every result file; pages print them.

Metric sources:

- VectorDBBench [`metric.py`](https://github.com/zilliztech/VectorDBBench/blob/1760db1/vectordb_bench/metric.py) (recall, nDCG)
- qdrant [`engine/base_client/search.py`](https://github.com/qdrant/vector-db-benchmark/blob/871a0b2/engine/base_client/search.py) (recall, percentiles)
- ann-benchmarks [`plotting/metrics.py`](https://github.com/erikbern/ann-benchmarks/blob/2e081ad/ann_benchmarks/plotting/metrics.py) (recall, percentiles)

## Engines

Defaults read from the installed libraries (DuckDB's from its VSS docs). The ef sweep is 16, 32, 64, 100, 128, 160, 200, 256, 320, 400, 512, 768, 1024 (settings with ef < k are skipped at that k).

| Engine | Version | Index (library defaults) | Default search | Default metric / `ip` mode | Sweep | Filter mechanism |
|---|---|---|---|---|---|---|
| `moss` | 1.16.0 (`inferedge-moss-core` 0.30.0) | exact search via public `SessionIndex` | exact | inner product | none (text: `alpha` default 0.8, then 1.0) | metadata filter (`$gte`, `$eq`) |
| `chroma` | 1.5.9 | HNSW M 16, ef_construction 100, persistent client | ef 100 | l2 / ip | ef | `where` |
| `lancedb` | 0.40.0 | `create_index()`: IVF_PQ | no refine | l2 / dot | refine_factor 2, 5, 10, 20, 50 | `where` (prefilter, the default) |
| `lancedb-hnsw` | 0.40.0 | `IvfHnswSq()` (docs: best recall/latency for unfiltered search) | ef 1.5 x k | l2 / dot | ef, then refine_factor 2, 5, 10 (re-rank with full vectors; ef alone levels off near 0.96 recall) | `where` (prefilter) |
| `qdrant-local` | qdrant-client 1.19.1 | local `:memory:` mode, always exact | exact | DOT (Qdrant requires a choice) | none | payload filter |
| `faiss-flat` | faiss-cpu 1.15.1 | `IndexFlat`, exact | exact | l2 / ip | none | `IDSelectorBitmap`, built inside each query from a numpy predicate (FAISS has no metadata filter) |
| `faiss-hnsw` | faiss-cpu 1.15.1 | `IndexHNSWFlat` M 32 (C++ default; Python requires M), efConstruction 40 | efSearch 16 | l2 / ip | efSearch | `IDSelectorBitmap`, as faiss-flat |
| `zvec` | 0.7.0 | HNSW M 50, ef_construction 500 | ef 300 | inner product | ef | filter expression |
| `sqlite-vec` | 0.1.9 | `vec0` brute force, exact | exact | l2 / cosine | none | metadata columns |
| `duckdb-vss` | duckdb 1.5.6 + vss | HNSW M 16, ef_construction 128 | ef 64 | l2sq / ip | ef | `WHERE` |

Each search returns what the library returns by default (Chroma: metadata, documents and distances; Qdrant: payload; LanceDB: every column, the vector included; zvec: all scalar fields; FAISS: ids and distances; Moss: documents and metadata). The SQL engines select id and labels (sqlite-vec also the distance).

LanceDB setups: its docs say an exact scan "works fine below ~100K vectors, but past that you should build a dedicated vector index", call IVF_PQ the "General-purpose default; what Enterprise builds automatically", and IVF_HNSW_SQ "Best recall/latency for unfiltered search; higher latency variance under selective filters" ([performance](https://docs.lancedb.com/performance)); VectorDBBench's default LanceDB config is IVF_PQ. At the defaults on cohere-100k (200 queries) IVF_PQ reaches recall@10 0.55 (`refine_factor` 50: 0.99) and IVF_HNSW_SQ 0.87.

Versions come from `uv.lock`. Known behaviors:

- **Chroma:** a modified `ef_search` is stored but only applied after the client reopens, so the sweep closes and reopens the persistent client. `close()` frees the old client's loaded index; reopening without it kept one more copy of the index per setting (about 340 MB each at cohere-100k), which inflated Chroma's search memory before 2026-10-13.
- **Index builds of Chroma, DuckDB-VSS, LanceDB and zvec are not reproducible:** identical runs gave different recall (scifact nDCG@10 for Chroma: 0.6524, 0.6545, 0.6541 in three runs on 2026-10-13; zvec differed by at most 0.0001 recall, at k = 50 and 100 on cohere-100k and dbpedia-openai-1m, 2026-10-14), so the defaults, tuning and filter pages, which each build their own index, can differ slightly for these engines. FAISS, Moss, Qdrant and sqlite-vec reproduced exactly.
- **DuckDB HNSW** applies `WHERE` after the index scan (post-filtering), so selective filters lose recall.
- **FAISS HNSW** with 1%-selectivity filters has low recall.
- **LanceDB HNSW** defaults to ef = 1.5 x k, so recall at k = 1 is low.
- **qdrant-local** keeps everything in memory and searches exhaustively: peak RSS 2.3 GB at cohere-100k and 27.6 GB at dbpedia-openai-1m, where one run took 77 minutes (2026-10-09).
- **DuckDB** downloads the `vss` extension into `~/.duckdb/extensions` on first use.

## Datasets

| Name | Source | Docs / queries | Dim / metric | License | Download |
|---|---|---|---|---|---|
| `cohere-100k` (smoke) | VectorDBBench Cohere | 100K / 1,000 | 768 / cosine | no data license stated; Cohere Wikipedia embeddings are Apache-2.0 (secondary source) | 313 MB |
| `cohere-1m` | VectorDBBench Cohere | 1M / 1,000 | 768 / cosine | same | 3.13 GB |
| `dbpedia-openai-1m` | HF `KShivendu/dbpedia-entities-openai-1M`, ann-benchmarks split | 990K / 10,000 | 1536 / angular | MIT | 9.52 GB |
| `arxiv-titles-2m` | Qdrant `arxiv_no_filters.tar.gz` (all-MiniLM-L6-v2) | 2,138,591 / ~15K | 384 / cosine | arXiv metadata CC0; tarball none stated | 3.10 GB |
| `hotpotqa-1m` | BEIR HotpotQA, VectorDBBench subset rule (qrel docs + corpus-order fill to 1M) | 1M / 7,405 | text (nDCG@10, Recall@100, R-precision) | CC BY-SA 4.0 | 654 MB + about 1.5 GB of vectors |
| `scifact` | BEIR SciFact, test split, all docs | 5,183 / 300 (about 1.1 relevant docs per query) | text (nDCG@10, Recall@k, R-precision) | claims CC BY 4.0, abstracts ODC-By 1.0 ([allenai/scifact](https://github.com/allenai/scifact/blob/master/LICENSE.md)) | 2.7 MB |

Ground truth is exact brute force (cohere sets ship VectorDBBench's; our float32 brute force matches it as a set at k ≤ 10 and on 99.997% of the top-100 ids at cohere-100k, the rest being near-ties at rank 100, so exact engines can score just under 1.0 recall@100). `--docs N` runs use the exact ground truth over the first N docs, `data/<name>/gt_docs<N>.npy`, which `run_suite.sh` creates with `bench_data.py subset-gt <name> <N>` in its own process (log `results/logs/subset-gt-<name>-<N>-<stamp>.log`); computing it inside the benchmark process inflated its memory baseline by up to 440 MB. The defaults runner refuses a missing cache or one older than the dataset's `base.npy`. The published dbpedia-openai-1m runs use its first 1,000 queries (`--queries 1000`) and k = 10 and 100 (`--k 10,100`, big-ann's and VectorDBBench's k) to fit one night; the other datasets use every query and k = 1, 10, 50, 100. MS MARCO is excluded (non-commercial terms). Moss indexes the text datasets with its built-in embedder; other engines use fastembed MiniLM at 512 tokens.

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
for s in defaults tuning filter; do
  ./run_suite.sh $s cohere-100k all --queries 200 --metric ip
done
open results/index.html
```

- The watchdog prints `pid=... log=...` and a final `watchdog: rc=0 peak_rss_mb=... elapsed=...s` line. `cat` the log to see the command's output. It kills the job on memory pressure, RSS > 85% of RAM, or `WATCHDOG_MAX_S`.
- Every run gets its own log, never overwritten: `results/logs/<suite>-<dataset>-<engine>[-ip][-docs<N>]-<stamp>.log`, and its result has the same name and stamp, `results/<suite>/<dataset>/<engine>[-ip][-docs<N>]-<stamp>.json`. The newest stamp per run is the attempt the report checks. Fetch, prepare and subset ground-truth logs use a prefix (`fetch-`, `prepare-`, `subset-gt-`) plus a stamp, so the report ignores them.
- `run_suite.sh` first upgrades `moss` to the latest release, then runs one watchdogged process per (dataset, engine), skipping pairs that do not apply with the reason (`harness.applies`: no ip mode, an exact engine in `tuning`, no filter cases, `--docs` outside `defaults`), then rebuilds the pages. A failed or killed run prints `DNF <suite> <dataset> <engine>` and appears under DNF on its page.
- Launch python as `$PWD/.venv/bin/python` from `benchmarks/` under the watchdog, never `uv run`: the watchdog then measures the benchmark's RSS, and the stop pattern below matches it.
- Runaway job: `pkill -9 -f run_suite.sh; pkill -9 -f 'benchmarks/\.venv/bin/python'` (the loop first, or it logs a DNF and starts the next pair). The second pattern kills every benchmark python, so check `pgrep -fl 'benchmarks/\.venv/bin/python'` first. The watchdog is killed too, so the log ends without a `watchdog: rc=` line.

Results: `results/<suite>/<dataset>/<engine>[-ip][-docs<N>]-<stamp>.json`; pages `results/index.html` and `results/<page>.html` / `.md` (work offline).

## Options

`./run_suite.sh <suite> "<datasets>" "<engines>|all" [options]`. Datasets and engines are space-separated lists; run a single pair the same way, so its log and result share a stamp. Write `--docs N` and `--metric ip`, not `--flag=value` (the log name needs them).

| Flag | Suites | Example | Effect |
|---|---|---|---|
| `--queries N` | all | `--queries 200` | first N queries |
| `--k` | defaults, tuning | `--k 10,100` | k values (default `1,10,50,100`; text datasets use those >= 10); the filter suite uses k = 100 |
| `--metric` | all | `--metric ip` | `default` (each library's default distance) or `ip` (inner product, cosine for sqlite-vec) |
| `--docs N` | defaults | `--docs 25000` | index the first N docs (1 to n_base - 1) of a vector dataset, exact ground truth over them; feeds the scaling page |
| `--filters` | filter | `--filters int_1p,label_50p` | filter cases (default `int_1p,int_99p,label_1p,label_50p`) |

Examples:

```bash
./run_suite.sh tuning cohere-100k "faiss-hnsw zvec" --metric ip --k 10
./run_suite.sh defaults cohere-100k "faiss-flat sqlite-vec" --docs 25000 --metric ip
./run_suite.sh filter cohere-100k "moss chroma"
```

## Reading the report

`results/index.html` links one page per benchmark. Every page has a dataset picker and a **metric switch**:
- **inner product†** (opens first): every engine in its inner-product mode (cosine for sqlite-vec), i.e. the datasets' cosine on unit vectors: `--metric ip` runs, plus the default runs of engines whose default is already inner product;
- **library default**: each library's default distance.

An "About these results" section at the top has one subsection each for the metric (†, shown only in the inner-product view), the quality measures and how latency is measured. Every chart sits in a numbered card titled `Chart N · <dataset> · <measure>` with a subtitle (metric, k and other specifics) and a description; every measure axis says whether higher or lower is better; a latency axis is log (titled "(log scale)") only when its values span more than 20x. Dropdown views of one unit share one fixed axis range.

- **Default settings** (`defaults.html`): latency (dropdown: mean, p50, p95, p99) and quality at one k for every engine (the largest k all runs share; k = 10 on text datasets, the depth nDCG@10 scores); index build time (text datasets stack the corpus-embedding time, measured once at prepare, on the non-Moss engines, which index vectors embedded by fastembed; Moss embeds inside its build); memory (index, build peak, search peak, RSS increase, on disk). Tables: every k, build and memory, example results (text: each engine's top 5 for 10 queries, ✓ = labelled relevant), DNFs.
- **Tuning** (`tuning.html`): latency at equal recall (vector datasets: the mean latency of each engine's fastest setting reaching recall@k ≥ 0.95 / 0.99, any knob, bar label = the setting; exact engines at their one setting; public benchmarks compare speed this way: Qdrant, VIBE, big-ann); quality vs latency showing only each engine's best settings of its primary knob (the Pareto frontier at mean latency, as in ann-benchmarks' `create_pointset`: a setting slower without being better is left out), exact engines as a dotted horizontal line at their latency, ending at their point (another engine's settings below the line are faster), k from a dropdown (text: k = 10); one chart per engine with a secondary knob (LanceDB-HNSW refine_factor) against that engine's default. Tables: every measured setting, equal recall.
- **Filtered search** (`filter.html`): one card per engine with recall@100 and mean latency (warm solid, cold dotted) per filter case, from most to fewest docs kept, after the engine's own unfiltered pass from the same run. Table: every case, cold and warm.
- **Scaling** (`scaling.html`): each engine over corpus size (its `--docs` runs plus the full run), dropdown: recall, latency statistic, index or build peak memory, build time.
- **Tables:** click a header to sort; each categorical column (engine, metric, knob, setting, k, filter, target) has a value list (tick values to show only those rows; nothing ticked = all rows; "clear filters" unticks everything; plain CSS, no script); the best value per column among the shown rows is bold.
- Hover for exact values and parameters; click a legend entry to hide an engine; double-click to isolate it.
- **DNF** = a run's newest log has no `wrote` line and no result exists for that run. **STALE:** if a run's newest attempt failed but an older result exists, that page's builder exits without writing (the index shows the error), so an old number never stands in for a failed rerun.
- **Limits:** each configuration is measured in one run (no repeats or confidence intervals); latency is single-client wall time, and CPU time per query is not measured (engines differ in how many cores one query uses); each engine returns its library's default result payload (see Engines), which costs more as k grows for engines that return more; the k passes of a run reuse the same queries, so later passes can find them cached.

## Moss notes

- **Exact search.** Recall is 1.0 against brute force; there are no ANN knobs, so each vector dataset gives one recall point per (dataset, k). On text datasets `alpha` (the SDK default 0.8 hybrid, then 1.0 vector only) is the sweep. Vector queries pass `alpha=1.0`, since there is no query text.
- **Normalization.** Moss scores by inner product without normalizing, so all vectors are L2-normalized for every engine (raw Cohere vectors: recall@100 0.41 against cosine).
- **Concurrency is not benchmarked** (local Moss serves one user). Calls serialize per session: an earlier cohere-100k run (Apple M5 Max, moss 1.15.1) measured 586 / 611 / 613 QPS at 1 / 4 / 16 clients while p99 grew 2.14 / 7.79 / 28.76 ms. One query already used about 12 cores from 5k docs up (CPU time over wall time, `moss_core` 0.28.1, 2026-10-07); this benchmark does not measure CPU time.
- **Every run rebuilds the index** (the build is what is measured) and consumes metered session minutes (about 2.5x query time, 0.8x build time, measured 2026-09-24).
- **Session setup is not build time.** `client.session()` authenticates, looks up a same-named cloud index and, for built-in models, loads the model, so a local session is not free of a cloud round trip on the public API. It runs in the adapter's `open()`, before the build timer, and is recorded as `open_s` (0.71 s custom, 0.99 s moss-minilm, median of 5 on the M5 Max).
- **Latest Moss is enforced.** `moss` is unpinned; `run_suite.sh` runs `uv lock --upgrade-package moss`, and every runner exits unless the installed version equals the newest PyPI release. Commit `uv.lock` when it changes.
- Credentials: `MOSS_ENV_FILE` (a dotenv file) or `MOSS_PROJECT_ID` / `MOSS_PROJECT_KEY`.

## Hardware

Apple M5 Max, 18 cores, 128 GB, recorded in every result file together with OS, Python and package versions.

## Phase 2

Served databases (Milvus, Qdrant server, ...) plug into the same engine contract in `engines.py`.
