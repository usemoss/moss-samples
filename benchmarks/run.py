"""Benchmark one engine on one prepared dataset; writes results/<dataset>/<engine>[-docs<N>]-<timestamp>.json.

usage: uv run python run.py <dataset> <engine> [options]      (engines: see engines.ENGINES; one per process)

Stages (VectorDBBench / qdrant / ann-benchmarks methodology, see README.md):
  load        build the index: build seconds, docs/s, RSS before/after build
  serial      one client, every sweep setting x every --k: recall@k, nDCG@k, p50/p95/p99/p99.9/mean latency, QPS
              (text datasets: nDCG@10 and Recall@100 against qrels, k = 100)
  concurrent  ladder of N in-flight clients sharing one index, --duration s per level: QPS + latency per level
  filter      VectorDBBench filter cases (k = 100), scored against each case's own ground truth
The concurrent and filter stages run at the operating point: the fastest (lowest p50) sweep setting whose
recall@max(k) >= --target-recall, else the most accurate setting (qdrant's "best speed at a precision threshold").
"""

import argparse
import asyncio
import inspect
import json
import os
import platform
import random
import resource
import subprocess
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version
from pathlib import Path

import numpy as np

from bench_data import DATA, exact_topk, load
from engines import ENGINES, MossTextEngine, make_engine
from metrics import latency_summary, ndcg_gt, ndcg_qrels, recall, recall_qrels

HERE = Path(__file__).parent
RESULTS = HERE / "results"
PACKAGES = [
    "moss",
    "inferedge-moss-core",
    "chromadb",
    "lancedb",
    "qdrant-client",
    "faiss-cpu",
    "zvec",
    "sqlite-vec",
    "duckdb",
    "fastembed",
    "numpy",
]


def ensure_latest_moss() -> None:
    """Exit unless the installed moss is the newest release on PyPI (the suite always benchmarks the latest Moss)."""
    installed = version("moss")
    latest = json.load(
        urllib.request.urlopen("https://pypi.org/pypi/moss/json", timeout=10)
    )["info"]["version"]
    if installed != latest:
        raise SystemExit(
            f"moss {installed} is installed but {latest} is the latest release; run: "
            "uv lock --upgrade-package moss && uv sync"
        )


async def search(
    eng: object, q: object, k: int, flt: dict | None = None, threaded: bool = False
) -> list[int]:
    """Call eng.search natively: coroutines are awaited; sync engines run inline, or in a worker thread if threaded."""
    if inspect.iscoroutinefunction(eng.search):
        return await eng.search(q, k, flt)
    if threaded:
        return await asyncio.to_thread(eng.search, q, k, flt)
    return eng.search(q, k, flt)


async def timed(
    eng: object, qs: list, k: int, flt: dict | None = None
) -> tuple[list[list[int]], list[float]]:
    """Serial pass: results and per-query latency (seconds, perf_counter) for every query."""
    got, lat = [], []
    for q in qs:
        t0 = time.perf_counter()
        got.append(await search(eng, q, k, flt))
        lat.append(time.perf_counter() - t0)
    return got, lat


async def ladder_level(
    eng: object, qs: list, k: int, level: int, duration: float
) -> dict:
    """One VectorDBBench-style level: `level` concurrent clients, random start offsets, cycling queries for
    `duration` seconds. The loop's default executor (used by asyncio.to_thread, including Moss's own query path)
    holds min(32, cpu+4) threads, so each level installs an executor with exactly `level` threads."""
    loop = asyncio.get_running_loop()
    ex = ThreadPoolExecutor(max_workers=level)
    loop.set_default_executor(ex)
    lat: list[float] = []
    stop = time.perf_counter() + duration

    async def client(i: int) -> None:
        """Issue queries back to back until the level's deadline."""
        while (t0 := time.perf_counter()) < stop:
            await search(eng, qs[i % len(qs)], k, None, threaded=True)
            lat.append(time.perf_counter() - t0)
            i += 1

    t0 = time.perf_counter()
    await asyncio.gather(*(client(random.randrange(len(qs))) for _ in range(level)))
    wall = time.perf_counter() - t0
    loop.set_default_executor(
        ThreadPoolExecutor()
    )  # later to_thread calls (e.g. Moss close) need a live pool
    ex.shutdown()
    return {"level": level, "qps": len(lat) / wall, "latency_ms": latency_summary(lat)}


def subset(d: dict, docs: int | None, queries: int | None, stages: list[str]) -> dict:
    """Limit a vector dataset to the first `docs` docs / `queries` queries; a doc subset gets exact GT recomputed."""
    d = dict(d, meta=dict(d["meta"]))
    if queries:
        d["queries"], d["gt"] = d["queries"][:queries], d["gt"][:queries]
        d["gt_filters"] = {t: g[:queries] for t, g in d.get("gt_filters", {}).items()}
    if docs:
        if "filter" in stages:
            raise SystemExit(
                "--docs cannot be combined with the filter stage (filter ground truth covers the full set)"
            )
        d["base"], d["ids"] = np.asarray(d["base"][:docs]), d["ids"][:docs]
        d["gt"] = d["ids"][exact_topk(d["base"], d["queries"], min(100, docs))]
        if "labels" in d:
            d["labels"] = d["labels"][:docs]
        d["meta"]["n_base"] = docs
    return d


def operating_point(rows: list[dict], metric: str, target: float | None) -> dict:
    """Sweep setting for the concurrent/filter stages: fastest row meeting target, else the most accurate row."""
    ok = [r for r in rows if target is not None and r[metric] >= target]
    best = (
        min(ok, key=lambda r: r["latency_ms"]["p50"])
        if ok
        else max(rows, key=lambda r: r[metric])
    )
    return best["params"]


def env() -> dict:
    """Hardware and software versions recorded in every result file."""

    def sh(*cmd: str) -> str:
        """stdout of a command, stripped."""
        return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()

    return {
        "cpu": sh("sysctl", "-n", "machdep.cpu.brand_string"),
        "cores": os.cpu_count(),
        "ram_gb": round(int(sh("sysctl", "-n", "hw.memsize")) / 2**30),
        "os": platform.platform(),
        "python": platform.python_version(),
        "git": sh("git", "rev-parse", "--short", "HEAD"),
        "versions": {p: version(p) for p in PACKAGES},
    }


def rss_mb() -> float:
    """Current resident set size of this process in MB."""
    return (
        int(
            subprocess.run(
                ["ps", "-o", "rss=", "-p", str(os.getpid())],
                capture_output=True,
                text=True,
            ).stdout
        )
        / 1024
    )


async def main(a: argparse.Namespace) -> dict:
    """Run the selected stages for one engine and return the result document."""
    stages, ks = a.stages.split(","), [int(x) for x in a.k.split(",")]
    d = load(a.dataset)
    text = d["meta"]["kind"] == "text"
    if text and a.docs:
        raise SystemExit(
            "--docs is not supported for text datasets (it would drop qrel documents)"
        )
    if text:
        ks, d["queries_text"] = (
            [100],
            d["queries_text"][: a.queries] if a.queries else d["queries_text"],
        )
    else:
        d = subset(d, a.docs, a.queries, stages)
    eng = make_engine(a.engine, text, str(DATA / ".fastembed"))
    out: dict = {
        "dataset": d["meta"],
        "engine": a.engine,
        "env": env(),
        "args": vars(a),
        "serial": [],
        "concurrent": [],
        "filter": [],
    }

    rss0, t0 = rss_mb(), time.perf_counter()
    if isinstance(eng, MossTextEngine):
        await eng.build(d["ids"], [c["text"] for c in d["corpus"]])
    else:
        labels = d.get("labels")
        meta = (
            [{"id": int(i), "labels": str(x)} for i, x in zip(d["ids"], labels)]
            if labels is not None
            else None
        )
        r = eng.build(d["ids"], d["base"], meta)
        if inspect.isawaitable(r):
            await r
    build_s = time.perf_counter() - t0
    n = len(d["ids"])
    out["load"] = {
        "docs": n,
        "build_s": build_s,
        "docs_per_s": n / build_s,
        "rss_before_build_mb": rss0,
        "rss_after_build_mb": rss_mb(),
    }
    print(json.dumps(out["load"]), flush=True)

    qs = [q["text"] for q in d["queries_text"]] if text else list(d["queries"])
    for params in eng.sweep or [{}]:
        if params:
            eng.set_search(params)
        await timed(eng, qs[:100], min(ks))  # warm-up for this setting, unmeasured
        for k in ks:
            if params.get("ef", k) < k:  # HNSW needs ef >= k to return k results
                continue
            got, lat = await timed(eng, qs, k)
            row = {
                "params": params,
                "k": k,
                "qps": len(lat) / sum(lat),
                "latency_ms": latency_summary(lat),
            }
            if text:
                by_q = {
                    q["id"]: [str(x) for x in g] for q, g in zip(d["queries_text"], got)
                }
                qrels = {q["id"]: d["qrels"][q["id"]] for q in d["queries_text"]}
                row |= {
                    "ndcg@10": ndcg_qrels(by_q, qrels, 10),
                    "recall@100": recall_qrels(by_q, qrels, 100),
                }
            else:
                row |= {
                    f"recall@{k}": recall(got, d["gt"], k),
                    f"ndcg@{k}": ndcg_gt(got, d["gt"], k),
                }
            row["precision"] = row["ndcg@10"] if text else row[f"recall@{k}"]  # the headline precision value
            out["serial"].append(row)
            print(json.dumps(row), flush=True)

    rows = [r for r in out["serial"] if r["k"] == max(ks)]
    out["operating_point"] = operating_point(
        rows, "precision", None if text else a.target_recall
    )
    if out["operating_point"]:
        eng.set_search(out["operating_point"])
    if "filter" in stages and d.get("gt_filters"):
        for tag in a.filters.split(","):
            got, lat = await timed(eng, qs, 100, d["meta"]["filters"][tag])
            out["filter"].append(
                {
                    "filter": tag,
                    "k": 100,
                    "recall@100": recall(got, d["gt_filters"][tag], 100),
                    "qps": len(lat) / sum(lat),
                    "latency_ms": latency_summary(lat),
                }
            )
            print(json.dumps(out["filter"][-1]), flush=True)
    if "concurrent" in stages:
        for level in [int(x) for x in a.levels.split(",")]:
            out["concurrent"].append(
                await ladder_level(eng, qs, max(ks), level, a.duration)
            )
            print(json.dumps(out["concurrent"][-1]), flush=True)
    r = eng.close()
    if inspect.isawaitable(r):
        await r
    out["load"]["peak_rss_mb"] = (
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20
    )  # bytes on macOS
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("dataset")
    p.add_argument("engine", choices=list(ENGINES))
    p.add_argument(
        "--stages", default="serial,concurrent,filter", help="load always runs"
    )
    p.add_argument(
        "--k", default="10,100", help="vector datasets; text datasets always use k=100"
    )
    p.add_argument("--queries", type=int, help="use only the first N queries")
    p.add_argument(
        "--docs",
        type=int,
        help="vector datasets: index only the first N docs (GT recomputed)",
    )
    p.add_argument("--levels", default="1,5,10,20,30,40,60,80")
    p.add_argument(
        "--duration", type=float, default=30.0, help="seconds per concurrency level"
    )
    p.add_argument("--filters", default="int_1p,int_99p,label_1p,label_50p")
    p.add_argument("--target-recall", type=float, default=0.95)
    args = p.parse_args()
    if args.engine == "moss":
        ensure_latest_moss()
    res = asyncio.run(main(args))
    out_dir = RESULTS / args.dataset
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"-docs{args.docs}" if args.docs else ""
    path = out_dir / f"{args.engine}{tag}-{time.strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(res, indent=1) + "\n")
    print(f"wrote {path}")
