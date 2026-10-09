# Moss standard vector-search benchmark

Compares Moss with eight local in-process engines on standard public datasets, using the methodology of VectorDBBench, qdrant's vector-db-benchmark and ann-benchmarks. Every run writes an interactive Plotly report and Markdown tables.

## What it measures

Four stages per (dataset, engine), run by `run.py`:

| Stage | What | Metrics |
|---|---|---|
| `load` | build the index | build seconds, docs/s, RSS before/after, memory footprint (baseline, after build, build peak), index size on disk |
| `serial` | one client, every sweep setting x every k | vector: recall@k and nDCG@k vs the exact top-k; text: nDCG@10, Recall@100, R-precision vs human labels; p50/p95/p99/p99.9/mean latency (ms), QPS |
| `concurrent` | ladder of N in-flight clients on one index, `--duration` s per level, random start offsets | QPS and latency per level |
| `filter` | VectorDBBench filter cases at k=100, each scored against its own ground truth: a cold pass (first use of the filter) then a warm pass | recall@100, latency, QPS and first-query latency, per pass |

- **Recall@k** = `|got[:k] ∩ gt[:k]| / k` against the exact brute-force top-k. Both lists have k items, so it also equals precision@k, and an exact engine scores 1.0 by definition: it measures how closely an index matches exact search, not whether a person would find the results relevant. **nDCG@k** weights each hit by its ground-truth rank. Text datasets are scored against BEIR's human relevance labels: nDCG@10, Recall@100 and **R-precision** (relevant docs in the top R over R, R = that query's relevant-doc count; on hotpotqa every query has 2, so it is precision@2).
- **Latency** is per query in milliseconds. Percentiles are `numpy.percentile` (linear interpolation). Serial QPS = queries / summed latency.
- **Memory** is the physical footprint (Activity Monitor's "Memory"; it excludes clean file-backed pages such as the memory-mapped dataset), read with macOS `proc_pid_rusage`. Each stage's peak comes from `proc_reset_footprint_interval` (a private macOS API; no sampling thread, so latencies are untouched). The report shows values over the footprint after the dataset loads: index (after build), build peak, search peak. Disk-backed engines (chroma, lancedb, zvec, sqlite-vec) keep part of their index in files that the OS caches outside the process, so their index size on disk is shown too, plus the RSS increase over the build.
- **Operating point** (qdrant-style "best speed at a precision threshold"; qdrant's precision is the recall above): the lowest-p50 sweep setting with recall@max(k) >= `--target-recall` (default 0.95); if none qualifies, the most accurate setting. The concurrent and filter stages run there. Text datasets use the most accurate setting. After it is applied, 100 unmeasured warm-up queries run.
- **Hardware and library versions** are recorded in every result file.

Metric sources:

- VectorDBBench [`metric.py`](https://github.com/zilliztech/VectorDBBench/blob/1760db1/vectordb_bench/metric.py) (recall, nDCG, QPS ladder)
- qdrant [`engine/base_client/search.py`](https://github.com/qdrant/vector-db-benchmark/blob/871a0b2/engine/base_client/search.py) (recall, percentiles)
- ann-benchmarks [`plotting/metrics.py`](https://github.com/erikbern/ann-benchmarks/blob/2e081ad/ann_benchmarks/plotting/metrics.py) (recall, QPS, percentiles)

## Engines

All engines index the same L2-normalized vectors with inner product (cosine for sqlite-vec; same ranking on unit vectors). HNSW engines are built once with M=16, ef_construction=200, then swept over ef = 16, 32, 64, 100, 128, 160, 200, 256, 320, 400, 512, 768, 1024 (settings with ef < k are skipped at that k).

| Engine | Version | Index | Sweep | Filter mechanism |
|---|---|---|---|---|
| `moss` | 1.15.1 (`inferedge-moss-core` 0.28.1) | exact search via public `SessionIndex` | none (`alpha` 1.0 / 0.8 on text datasets) | metadata filter (`$gte`, `$eq`) |
| `chroma` | 1.5.9 | HNSW, ip space, persistent client | ef | `where` |
| `lancedb` | 0.40.0 | HNSW-SQ, dot, one partition | ef | prefiltered `where` |
| `qdrant-local` | qdrant-client 1.19.1 | local `:memory:` mode, DOT, always exact | none | payload filter |
| `faiss-flat` | faiss-cpu 1.15.1 | `IndexFlatIP`, exact | none | `IDSelectorBatch` |
| `faiss-hnsw` | faiss-cpu 1.15.1 | `IndexHNSWFlat` | efSearch | `IDSelectorBatch` |
| `zvec` | 0.7.0 | HNSW, IP | ef | filter expression (exact) |
| `sqlite-vec` | 0.1.9 | `vec0` brute force, exact | none | metadata columns |
| `duckdb-vss` | duckdb 1.5.6 + vss | HNSW, `ip` | ef | `WHERE` |

Versions come from `uv.lock`. Known behaviors:

- **Chroma:** a modified `ef_search` is stored but only applied after the client reopens, so the sweep reopens the persistent client.
- **DuckDB HNSW** applies `WHERE` after the index scan (post-filtering), so selective filters lose recall (cohere-100k smoke: 0.01 at `label_1p`).
- **FAISS HNSW** with 1%-selectivity filters has low recall (cohere-100k smoke: 0.27 at `label_1p`).
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

Ground truth is exact brute force (cohere sets ship VectorDBBench's; ours agrees 100% on cohere-100k). MS MARCO is excluded (non-commercial terms). Moss indexes `hotpotqa-1m` text with its built-in embedder; other engines use fastembed MiniLM at 512 tokens.

```bash
mkdir -p results/logs
./watchdog.sh results/logs/fetch-<name>.log $PWD/.venv/bin/python bench_data.py fetch <name>
./watchdog.sh results/logs/prepare-<name>.log $PWD/.venv/bin/python bench_data.py prepare <name>
```

Measured on a cohere-100k smoke run (Apple M5 Max): fetch 5 s (sha256-checked against `checksums.json`), prepare 1 s at 2078 MiB peak RSS. hotpotqa-1m: fetch 84 s, prepare 7442 s (embedding 7418 s) at 25903 MiB peak RSS. Other 1M prepare costs will be added once measured. Prepare for the 1M sets is heavy (GB of RAM, large ground-truth matmuls): raise `WATCHDOG_MAX_S` (default 1200 s) as needed.

## Quick start

`MOSS_ENV_FILE` points at a dotenv file defining `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY` (or export those two instead).

Needs macOS (the watchdog uses `sysctl`), [uv](https://docs.astral.sh/uv/), and Moss credentials for the `moss` engine.

```bash
cd benchmarks
uv sync
export MOSS_ENV_FILE=/path/to/.env

mkdir -p results/logs
./watchdog.sh results/logs/fetch-cohere-100k.log $PWD/.venv/bin/python bench_data.py fetch cohere-100k
./watchdog.sh results/logs/prepare-cohere-100k.log $PWD/.venv/bin/python bench_data.py prepare cohere-100k
./run_suite.sh cohere-100k all --queries 200 --levels 1,4,16 --duration 3
open results/report.html
```

- The watchdog prints `pid=... log=...` and a final `watchdog: rc=0 peak_rss_mb=... elapsed=...s` line. `cat` the log to see the command's output. It kills the job on memory pressure, RSS > 85% of RAM, or `WATCHDOG_MAX_S`.
- Engine logs are `results/logs/<dataset>-<engine>.log` and hold that engine's newest attempt; other logs use a prefix (`fetch-`, `prepare-`) so the report ignores them.
- `run_suite.sh` first upgrades `moss` to the latest release, then runs one watchdogged process per (dataset, engine), then rebuilds the report. A failed or killed run prints `DNF <dataset> <engine>` and appears under DNF in the report.
- Launch python as `$PWD/.venv/bin/python` from `benchmarks/` under the watchdog, never `uv run`: the watchdog then measures the benchmark's RSS, and the stop pattern below matches it.
- Runaway job: `pkill -9 -f run_suite.sh; pkill -9 -f 'benchmarks/\.venv/bin/python'` (the loop first, or it logs a DNF and starts the next pair). The second pattern kills every benchmark python, so check `pgrep -fl 'benchmarks/\.venv/bin/python'` first. The watchdog is killed too, so the log ends without a `watchdog: rc=` line.

Results: `results/<dataset>/<engine>-<timestamp>.json`, `results/summary.md`, `results/report.html` (works offline).

## Subsets

`run_suite.sh "<datasets>" "<engines>|all" [run.py options]`. Datasets and engines are space-separated lists. Run a single pair with `./watchdog.sh results/logs/<dataset>-<engine>.log $PWD/.venv/bin/python run.py <dataset> <engine> [options]`, then `$PWD/.venv/bin/python report.py`.

| Flag | Example | Effect |
|---|---|---|
| `--queries N` | `--queries 200` | first N queries |
| `--docs N` | `--docs 20000` | index first N docs, ground truth recomputed (vector datasets; not with the filter stage) |
| `--stages` | `--stages serial` | `load` and `serial` always run (serial picks the operating point); this selects `filter` / `concurrent` |
| `--k` | `--k 10` | k values (vector datasets; text always 100) |
| `--levels` | `--levels 1,4,16` | concurrency ladder (default `1,5,10,20,30,40,60,80`) |
| `--duration` | `--duration 3` | seconds per level (default 30) |
| `--filters` | `--filters int_1p,label_50p` | filter cases (default `int_1p,int_99p,label_1p,label_50p`) |
| `--target-recall` | `--target-recall 0.9` | operating-point recall (default 0.95) |

Examples:

```bash
./run_suite.sh cohere-100k "moss faiss-hnsw zvec" --stages serial --k 10
./run_suite.sh cohere-100k "faiss-flat sqlite-vec" --docs 20000 --stages serial,concurrent --duration 5
for n in 100000 250000 500000; do ./run_suite.sh cohere-1m all --docs $n --stages serial --queries 1000; done
```

`--docs` runs get their own `<dataset>-subsets` section, which opens with the scaling chart.

## Reading the report

`results/report.html` has one section per dataset:

- **Recall (vector) or nDCG@10 (text) vs speed:** Pareto frontier per engine and k (ann-benchmarks style); exact engines are dotted horizontal lines ending at their point. Dropdowns pick the speed metric (QPS, p50, p95, p99, p99.9, mean) and k.
- **Concurrency ladder:** QPS and latency (percentile dropdown) against clients.
- **Operating-point latency, build cost** (time, docs/s), **memory** (index, build peak, search peak, RSS increase over the build, on disk) **and filtered search** (dropdown: warm recall, cold / warm latency percentiles and QPS, cold first-query latency).
- **Example results** (text datasets): for 10 queries, each engine's top 5 at its operating point, with ✓ on documents the dataset labels relevant, so a person can judge the results directly.
- **Scaling** (`<dataset>-subsets` section, from `--docs` runs): one line per engine over corpus size, including the full run when it exists; the dropdown picks latency, QPS, recall (or nDCG@10), memory or build time.
- Hover for exact values and parameters; click a legend entry to hide an engine; double-click to isolate it.
- **DNF** = an engine's newest log has no `wrote` line and no result exists for that run (killed by the watchdog, out of memory, or crashed). The table shows the log's last line.
- **STALE:** if an engine's newest attempt failed but an older result for the same run exists, `report.py` prints `STALE <log>: <last line>`, exits 1 and writes nothing, so an old number never stands in for a failed rerun. Read the log, fix the cause and rerun (or move the old result out of `results/` on purpose). Running `report.py` while a run is in progress stops here too.

## Moss notes

- **Exact search.** Recall is 1.0 against brute force; there are no ANN knobs, so each vector dataset gives one recall point per (dataset, k). On text datasets `alpha` (1.0 vector only, 0.8 default hybrid) is the sweep.
- **Normalization.** Moss scores by inner product without normalizing, so all vectors are L2-normalized for every engine (raw Cohere vectors: recall@100 0.41 against cosine).
- **Calls serialize per session.** More clients add latency, not throughput. cohere-100k smoke run (Apple M5 Max, moss 1.15.1), QPS / p99 ms:

  | Clients | 1 | 4 | 16 |
  |---|---|---|---|
  | moss | 586 / 2.14 | 611 / 7.79 | 613 / 28.76 |
  | moss (repeat run) | 507 / 3.26 | 568 / 8.90 | 561 / 35.55 |

  One query already uses about 12 cores from 5k docs up.
- **Every run rebuilds the index** (no public save/load in Python) and consumes metered session minutes (about 2.5x query time, 0.8x build time).
- **Latest Moss is enforced.** `moss` is unpinned; `run_suite.sh` runs `uv lock --upgrade-package moss`, and `run.py` exits unless the installed version equals the newest PyPI release. Commit `uv.lock` when it changes.
- Credentials: `MOSS_ENV_FILE` (a dotenv file) or `MOSS_PROJECT_ID` / `MOSS_PROJECT_KEY`.

## Hardware

Apple M5 Max, 18 cores, 128 GB, recorded in every result file together with OS, Python and package versions.

## Phase 2

Served databases (Milvus, Qdrant server, ...) plug into the same engine contract in `engines.py`.
