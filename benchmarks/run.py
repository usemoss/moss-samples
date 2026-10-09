"""Benchmark one engine on one prepared dataset; writes results/<dataset>/<engine>[-docs<N>]-<timestamp>.json.

usage: ./watchdog.sh results/logs/<dataset>-<engine>.log $PWD/.venv/bin/python run.py <dataset> <engine> [options]
       (engines: see engines.ENGINES; one per process; the first output line is "args: {...}")

Stages (VectorDBBench / qdrant / ann-benchmarks methodology, see README.md):
  load        build the index: build seconds, docs/s, RSS before/after build, index size on disk
  serial      one client, every sweep setting x every --k: recall@k and nDCG@k vs exact top-k (vector), nDCG@10,
              recall@100 and R-precision vs human labels (text), p50/p95/p99/p99.9/mean latency, QPS
  concurrent  ladder of N in-flight clients sharing one index, --duration s per level: QPS + latency per level
  filter      VectorDBBench filter cases (k = 100), scored against each case's own ground truth; per case a cold
              pass (first use of that filter) then a warm pass, both measured
The concurrent and filter stages run at the operating point: the fastest (lowest p50) sweep setting whose
recall@max(k) >= --target-recall, else the most accurate setting (qdrant's "best speed at a precision threshold"; qdrant's precision is this recall).
After the operating point is applied, 100 unmeasured warm-up queries run. Text datasets keep the top 5 of the first 10
warm-up queries as example results. Memory: physical footprint (macOS
proc_pid_rusage) after the dataset loads and after build, plus the peak of every stage, in the result's "memory" block.
"""

import argparse
import asyncio
import ctypes
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
from metrics import (
    latency_summary,
    ndcg_gt,
    ndcg_qrels,
    r_precision,
    recall,
    recall_qrels,
)

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


class RusageInfoV4(ctypes.Structure):
    """struct rusage_info_v4 from macOS <sys/resource.h>; only the footprint fields are read."""

    _fields_ = [("ri_uuid", ctypes.c_uint8 * 16)] + [
        (f, ctypes.c_uint64)
        for f in (
            "ri_user_time ri_system_time ri_pkg_idle_wkups ri_interrupt_wkups ri_pageins ri_wired_size "
            "ri_resident_size ri_phys_footprint ri_proc_start_abstime ri_proc_exit_abstime ri_child_user_time "
            "ri_child_system_time ri_child_pkg_idle_wkups ri_child_interrupt_wkups ri_child_pageins "
            "ri_child_elapsed_abstime ri_diskio_bytesread ri_diskio_byteswritten ri_cpu_time_qos_default "
            "ri_cpu_time_qos_maintenance ri_cpu_time_qos_background ri_cpu_time_qos_utility "
            "ri_cpu_time_qos_legacy ri_cpu_time_qos_user_initiated ri_cpu_time_qos_user_interactive "
            "ri_billed_system_time ri_serviced_system_time ri_logical_writes ri_lifetime_max_phys_footprint "
            "ri_instructions ri_cycles ri_billed_energy ri_serviced_energy ri_interval_max_phys_footprint "
            "ri_runnable_time"
        ).split()
    ]


LIBSYSTEM = ctypes.CDLL("/usr/lib/libSystem.B.dylib")


def footprint_mb() -> tuple[float, float]:
    """(current, peak since reset_peak()) physical footprint of this process in MB: Activity Monitor's "Memory",
    which excludes clean file-backed pages such as the memory-mapped base vectors."""
    r = RusageInfoV4()
    if (
        LIBSYSTEM.proc_pid_rusage(os.getpid(), 4, ctypes.byref(r)) != 0
    ):  # 4 = RUSAGE_INFO_V4
        raise OSError("proc_pid_rusage failed")
    return r.ri_phys_footprint / 2**20, r.ri_interval_max_phys_footprint / 2**20


def reset_peak() -> None:
    """Start a new footprint peak interval (libproc's private proc_reset_footprint_interval; verified on macOS 26.6).
    Reading the interval peak needs no sampling thread, so measured latencies are unaffected."""
    if LIBSYSTEM.proc_reset_footprint_interval(os.getpid()) != 0:
        raise OSError("proc_reset_footprint_interval failed")


def disk_mb(eng: object) -> float:
    """Allocated size in MB of the engine's index directory (chroma, lancedb, zvec, sqlite-vec keep their index in a
    temp dir; text mode wraps the engine as .engine), counted like du; 0 for in-memory engines."""
    d = getattr(getattr(eng, "engine", eng), "dir", None)
    return (
        sum(f.stat().st_blocks * 512 for f in Path(d).rglob("*") if f.is_file()) / 2**20
        if d
        else 0.0
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

    mem: dict = {"baseline_footprint_mb": footprint_mb()[0], "peak_footprint_mb": {}}
    peaks = mem["peak_footprint_mb"]
    rss0, t0 = rss_mb(), time.perf_counter()
    reset_peak()
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
    peaks["build"] = footprint_mb()[1]
    n = len(d["ids"])
    out["load"] = {
        "docs": n,
        "build_s": build_s,
        "docs_per_s": n / build_s,
        "rss_before_build_mb": rss0,
        "rss_after_build_mb": rss_mb(),
    }
    mem |= {
        "footprint_after_build_mb": footprint_mb()[0],
        "rss_after_build_mb": out["load"]["rss_after_build_mb"],
        "disk_mb": disk_mb(eng),
    }
    print(json.dumps(out["load"] | mem), flush=True)

    qs = [q["text"] for q in d["queries_text"]] if text else list(d["queries"])
    reset_peak()
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
                    "r_precision": r_precision(by_q, qrels),
                }
            else:
                row |= {
                    f"recall@{k}": recall(got, d["gt"], k),
                    f"ndcg@{k}": ndcg_gt(got, d["gt"], k),
                }
            row["headline"] = (
                row["ndcg@10"] if text else row[f"recall@{k}"]
            )  # nDCG@10 (text) or recall@k vs exact top-k
            out["serial"].append(row)
            print(json.dumps(row), flush=True)

    peaks["serial"] = footprint_mb()[1]
    rows = [r for r in out["serial"] if r["k"] == max(ks)]
    out["operating_point"] = operating_point(
        rows, "headline", None if text else a.target_recall
    )
    if out["operating_point"]:
        eng.set_search(out["operating_point"])
    warm, _ = await timed(
        eng, qs[:100], max(ks)
    )  # unmeasured warm-up at the operating point (Chroma reopens its client)
    if text:  # top 5 of the first 10 queries for the report's example results; corpus position = id
        out["examples"] = [
            {
                "query": q["text"],
                "results": [
                    {
                        "text": d["corpus"][i]["text"][:240],
                        "relevant": str(i) in d["qrels"][q["id"]],
                    }
                    for i in g[:5]
                ],
            }
            for q, g in zip(d["queries_text"][:10], warm)
        ]
    if "filter" in stages and d.get("gt_filters"):
        reset_peak()
        for tag in a.filters.split(","):
            row: dict = {"filter": tag, "k": 100}
            for p in (
                "cold",
                "warm",
            ):  # cold: first use of this filter in the process; warm: the same pass again
                got, lat = await timed(eng, qs, 100, d["meta"]["filters"][tag])
                row[p] = {
                    "recall@100": recall(got, d["gt_filters"][tag], 100),
                    "qps": len(lat) / sum(lat),
                    "latency_ms": latency_summary(lat),
                    "first_ms": lat[0] * 1000,
                }
            out["filter"].append(row)
            print(json.dumps(row), flush=True)
        peaks["filter"] = footprint_mb()[1]
    if "concurrent" in stages:
        reset_peak()
        for level in [int(x) for x in a.levels.split(",")]:
            out["concurrent"].append(
                await ladder_level(eng, qs, max(ks), level, a.duration)
            )
            print(json.dumps(out["concurrent"][-1]), flush=True)
        peaks["concurrent"] = footprint_mb()[1]
    r = eng.close()
    if inspect.isawaitable(r):
        await r
    out["load"]["peak_rss_mb"] = (
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20
    )  # bytes on macOS
    out["memory"] = mem
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
    print(
        "args: " + json.dumps(vars(args)), flush=True
    )  # first log line: report.py reads the run key (--docs) from it
    if args.engine == "moss":
        ensure_latest_moss()
    res = asyncio.run(main(args))
    out_dir = RESULTS / args.dataset
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"-docs{args.docs}" if args.docs else ""
    path = out_dir / f"{args.engine}{tag}-{time.strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(res, indent=1) + "\n")
    print(f"wrote {path}")
