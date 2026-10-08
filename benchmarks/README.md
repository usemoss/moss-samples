# Moss standard vector-search benchmark

Compares Moss with eight local in-process engines on standard public datasets, using the methodology of VectorDBBench, qdrant's vector-db-benchmark and ann-benchmarks. Every run writes an interactive Plotly report and Markdown tables.

## What it measures

Four stages per (dataset, engine), run by `run.py`:

| Stage | What | Metrics |
|---|---|---|
| `load` | build the index | build seconds, docs/s, RSS before/after, peak RSS |
| `serial` | one client, every sweep setting x every k | recall@k, nDCG@k, p50/p95/p99/p99.9/mean latency (ms), QPS |
| `concurrent` | ladder of N in-flight clients on one index, `--duration` s per level, random start offsets | QPS and latency per level |
| `filter` | VectorDBBench filter cases at k=100, each scored against its own ground truth | recall@100, latency, QPS |

- **Recall@k** = `|got[:k] ∩ gt[:k]| / k` against exact brute-force ground truth. **nDCG@k** weights each hit by its ground-truth rank. Text datasets use nDCG@10 and Recall@100 against BEIR qrels.
- **Latency** is per query in milliseconds. Percentiles are `numpy.percentile` (linear interpolation). Serial QPS = queries / summed latency.
- **Operating point** (qdrant-style "best speed at a precision threshold"): the lowest-p50 sweep setting with recall@max(k) >= `--target-recall` (default 0.95); if none qualifies, the most accurate setting. The concurrent and filter stages run there. Text datasets use the most accurate setting.
- **Hardware and library versions** are recorded in every result file.

Metric sources:

- VectorDBBench [`metric.py`](https://github.com/zilliztech/VectorDBBench/blob/1760db1/vectordb_bench/metric.py) (recall, nDCG, QPS ladder)
- qdrant [`engine/base_client/search.py`](https://github.com/qdrant/vector-db-benchmark/blob/871a0b2/engine/base_client/search.py) (precision, percentiles)
- ann-benchmarks [`plotting/metrics.py`](https://github.com/erikbern/ann-benchmarks/blob/2e081ad/ann_benchmarks/plotting/metrics.py) (recall, Pareto frontier)

## Engines

All engines index the same L2-normalized vectors with inner product. HNSW engines are built once with M=16, ef_construction=200, then swept over ef = 16, 32, 64, 128, 256, 512.

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
- **qdrant-local** keeps everything in memory: 10.6 GB peak RSS at 100k x 768, so it is expected to DNF at 1M+.
- **DuckDB** downloads the `vss` extension into `~/.duckdb/extensions` on first use.

## Datasets

| Name | Source | Docs / queries | Dim / metric | License | Download |
|---|---|---|---|---|---|
| `cohere-100k` (smoke) | VectorDBBench Cohere | 100K / 1,000 | 768 / cosine | no data license stated; Cohere Wikipedia embeddings are Apache-2.0 (secondary source) | 313 MB |
| `cohere-1m` | VectorDBBench Cohere | 1M / 1,000 | 768 / cosine | same | 3.13 GB |
| `dbpedia-openai-1m` | HF `KShivendu/dbpedia-entities-openai-1M`, ann-benchmarks split | 990K / 10,000 | 1536 / angular | MIT | 9.52 GB |
| `arxiv-titles-2m` | Qdrant `arxiv_no_filters.tar.gz` (all-MiniLM-L6-v2) | 2,138,591 / ~15K | 384 / cosine | arXiv metadata CC0; tarball none stated | 3.10 GB |
| `hotpotqa-1m` | BEIR HotpotQA, VectorDBBench subset rule (qrel docs + corpus-order fill to 1M) | 1M / 7,405 | text (nDCG@10, Recall@100) | CC BY-SA 4.0 | 654 MB + about 1.5 GB of vectors |

Ground truth is exact brute force (cohere sets ship VectorDBBench's; ours agrees 100% on cohere-100k). MS MARCO is excluded (non-commercial terms). Moss indexes `hotpotqa-1m` text with its built-in embedder; other engines use fastembed MiniLM at 512 tokens.

```bash
mkdir -p results/logs
./watchdog.sh results/logs/fetch-<name>.log .venv/bin/python bench_data.py fetch <name>
./watchdog.sh results/logs/prepare-<name>.log .venv/bin/python bench_data.py prepare <name>
```

Measured on a cohere-100k smoke run (Apple M5 Max): fetch 5 s (298 MB, sha256-checked against `checksums.json`), prepare 1 s at 2.1 GB peak RSS, 621 MB on disk under `data/cohere-100k`. 1M prepare costs will be added once measured. Prepare for the 1M sets is heavy (GB of RAM, large ground-truth matmuls): raise `WATCHDOG_MAX_S` (default 1200 s) as needed.

## Quick start

Needs macOS (the watchdog uses `sysctl`), [uv](https://docs.astral.sh/uv/), and Moss credentials for the `moss` engine.

```bash
cd benchmarks
uv sync
export MOSS_ENV_FILE=/path/to/.env      # defines MOSS_PROJECT_ID and MOSS_PROJECT_KEY (or export those two)

mkdir -p results/logs
./watchdog.sh results/logs/fetch-cohere-100k.log .venv/bin/python bench_data.py fetch cohere-100k
./watchdog.sh results/logs/prepare-cohere-100k.log .venv/bin/python bench_data.py prepare cohere-100k
./run_suite.sh cohere-100k all --queries 200 --levels 1,4,16 --duration 3
open results/report.html
```

- The watchdog prints `pid=... log=...` and a final `watchdog: rc=0 peak_rss_mb=... elapsed=...s` line. `cat` the log to see the command's output. It kills the job on memory pressure, RSS > 85% of RAM, or `WATCHDOG_MAX_S`.
- Log names are prefixed (`fetch-`, `prepare-`) because `report.py` flags any `results/logs/<dataset>-*.log` without a result file as DNF.
- `run_suite.sh` first upgrades `moss` to the latest release, then runs one watchdogged process per (dataset, engine), then rebuilds the report. A failed or killed run prints `DNF <dataset> <engine>` and appears under DNF in the report.
- Use `.venv/bin/python` under the watchdog, never `uv run`, so the RSS cap measures the benchmark.
- Runaway job: `pkill -9 -f '\.venv/bin/python (run|bench_data|report)\.py'`

Results: `results/<dataset>/<engine>-<timestamp>.json`, `results/summary.md`, `results/report.html` (works offline).

## Subsets

`run_suite.sh "<datasets>" "<engines>|all" [run.py options]`. Datasets and engines are space-separated lists. Run a single pair with `.venv/bin/python run.py <dataset> <engine> [options]`.

| Flag | Example | Effect |
|---|---|---|
| `--queries N` | `--queries 200` | first N queries |
| `--docs N` | `--docs 20000` | index first N docs, ground truth recomputed (vector datasets; not with the filter stage) |
| `--stages` | `--stages serial` | any of `serial,concurrent,filter` (`load` always runs) |
| `--k` | `--k 10` | k values (vector datasets; text always 100) |
| `--levels` | `--levels 1,4,16` | concurrency ladder (default `1,5,10,20,30,40,60,80`) |
| `--duration` | `--duration 3` | seconds per level (default 30) |
| `--filters` | `--filters int_1p,label_50p` | filter cases (default `int_1p,int_99p,label_1p,label_50p`) |
| `--target-recall` | `--target-recall 0.9` | operating-point recall (default 0.95) |

Examples:

```bash
./run_suite.sh "cohere-100k cohere-1m" "moss faiss-hnsw zvec" --stages serial --k 10
./run_suite.sh cohere-100k "faiss-flat sqlite-vec" --docs 20000 --stages serial,concurrent --duration 5
```

## Reading the report

`results/report.html` has one section per dataset:

- **Precision vs speed:** Pareto frontier per engine and k (ann-benchmarks style). Dropdowns pick the speed metric (QPS, p50, p95, p99, p99.9, mean) and k.
- **Concurrency ladder:** QPS and latency (percentile dropdown) against clients.
- **Operating-point latency, build cost** (time, docs/s, peak RSS) **and filtered search** (recall, latency, QPS dropdown).
- Hover for exact values and parameters; click a legend entry to hide an engine; double-click to isolate it.
- **DNF** = a log exists in `results/logs/` with no result file (killed by the watchdog, out of memory, or crashed). The table shows the log's last line.

## Moss notes

- **Exact search.** Recall is 1.0 against brute force; there are no ANN knobs, so each vector dataset gives one precision point per (dataset, k). On text datasets `alpha` (1.0 vector only, 0.8 default hybrid) is the sweep.
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
