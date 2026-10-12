"""Benchmark one engine on one prepared dataset and write the result as JSON.

The result goes to results/<dataset>/<engine>[-ip][-docs<N>]-<stamp>.json.

usage: ./run_suite.sh <dataset> <engine> [options]   (one watchdogged run.py per pair; its log is
       results/logs/<dataset>-<engine>[-ip][-docs<N>]-<stamp>.log with the same --stamp as the
       result; engines: see engines.ENGINES; the first output line is "args: {...}")

Every engine runs off the shelf: library-default index and search settings (see engines.py).
--metric picks the library's default distance or inner product (cosine where an engine has none).

Stages (VectorDBBench / qdrant / ann-benchmarks methodology, see README.md):
  load        build the index: build seconds, docs/s, RSS before/after build, index size on disk
  serial      one client, every sweep setting x every --k: recall@k and nDCG@k vs exact top-k
              (vector), nDCG@10, recall@k and R-precision vs human labels (text, k >= 10),
              p50/p95/p99/p99.9/mean latency
  filter      VectorDBBench filter cases (k = 100), scored against each case's own ground truth;
              per case a cold pass (first use of that filter) then a warm pass, both measured
The operating point is the library-default search setting ({}, the first point of every sweep);
the filter stage runs there, after 100 unmeasured warm-up queries. Text datasets keep the top 5
of the first 10 warm-up queries as example results. Memory: physical footprint (macOS
proc_pid_rusage) after the dataset loads and after build, plus the peak of every stage, in the
result's "memory" block.
"""

import argparse
import asyncio
import ctypes
import inspect
import json
import os
import platform
import resource
import subprocess
import time
import urllib.request
from importlib.metadata import version
from pathlib import Path

import numpy as np

from bench_data import DATA, check_docs, load, subset_gt_path
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
    """Exit unless the installed moss package is the newest release on PyPI.

    The suite always benchmarks the latest Moss; run.py checks this before every Moss run.

    Raises:
        SystemExit: The installed version is not PyPI's latest; the message gives the upgrade
            command.
        urllib.error.URLError: PyPI cannot be reached.
    """
    installed = version("moss")
    latest = json.load(urllib.request.urlopen("https://pypi.org/pypi/moss/json", timeout=10))[
        "info"
    ]["version"]
    if installed != latest:
        raise SystemExit(
            f"moss {installed} is installed but {latest} is the latest release; run: "
            "uv lock --upgrade-package moss && uv sync"
        )


async def search(eng: object, q: object, k: int, flt: dict | None = None) -> list[int]:
    """Run one query on any engine, awaiting it when the engine's search is a coroutine.

    Args:
        eng: Engine adapter (see engines.py); Moss's search is async, the others are synchronous.
        q: Query vector, or query text for a text-mode engine.
        k: Number of results.
        flt: Neutral filter (see engines.py), or None.

    Returns:
        Top-k doc ids, best first.
    """
    if inspect.iscoroutinefunction(eng.search):
        return await eng.search(q, k, flt)
    return eng.search(q, k, flt)


async def timed(
    eng: object, qs: list, k: int, flt: dict | None = None
) -> tuple[list[list[int]], list[float]]:
    """Run every query once, in order, and time each call.

    One client, no concurrency: each latency is the perf_counter time around one search() call.

    Args:
        eng: Engine adapter (see engines.py).
        qs: Query vectors, or query texts for a text-mode engine.
        k: Number of results per query.
        flt: Neutral filter applied to every query, or None.

    Returns:
        The result ids and the latency in seconds of every query, both in query order.
    """
    got, lat = [], []
    for q in qs:
        t0 = time.perf_counter()
        got.append(await search(eng, q, k, flt))
        lat.append(time.perf_counter() - t0)
    return got, lat


def subset(d: dict, docs: int | None, queries: int | None, stages: list[str]) -> dict:
    """Limit a vector dataset to its first docs and/or first queries.

    Fewer queries also cut their ground truth (plain and per filter). A doc subset gets its labels
    cut and loads its exact ground truth from data/<name>/gt_docs<N>.npy (bench_data.py
    subset-gt, which run_suite.sh runs), sliced to the queries kept; computing it here would
    inflate the memory baseline. The input dict is not modified.

    Args:
        d: Dataset as returned by bench_data.load().
        docs: Keep only this many docs; None or 0 keeps all.
        queries: Keep only this many queries; None or 0 keeps all.
        stages: Stages of this run; a doc subset cannot run the filter stage.

    Returns:
        A shallow copy of d with the subset applied and meta's n_base / n_queries updated.

    Raises:
        SystemExit: docs is set and: the stages include "filter" on a dataset with filter ground
            truth (it covers the full set), docs is outside 1..n_base - 1, or the cached ground
            truth is missing or older than the prepared base vectors.
    """
    d = dict(d, meta=dict(d["meta"]))
    if queries:
        d["queries"], d["gt"] = d["queries"][:queries], d["gt"][:queries]
        d["gt_filters"] = {t: g[:queries] for t, g in d.get("gt_filters", {}).items()}
        d["meta"]["n_queries"] = len(d["queries"])
    if docs:
        if "filter" in stages and d.get("gt_filters"):
            raise SystemExit(
                "--docs cannot be combined with the filter stage (filter ground truth covers the full set)"
            )
        name = d["meta"]["name"]
        check_docs(docs, d["meta"]["n_base"])
        path = subset_gt_path(name, docs)
        if not path.exists() or path.stat().st_mtime < (DATA / name / "base.npy").stat().st_mtime:
            raise SystemExit(  # missing, or older than the prepared vectors (re-prepared since)
                f"missing or stale {path}; run_suite.sh creates it, or run "
                f"bench_data.py subset-gt {name} {docs} under the watchdog"
            )
        d["base"], d["ids"] = np.asarray(d["base"][:docs]), d["ids"][:docs]
        d["gt"] = np.load(path)[: len(d["queries"])]  # cached for every query; rows are per query
        if "labels" in d:
            d["labels"] = d["labels"][:docs]
        d["meta"]["n_base"] = docs
    return d


def env() -> dict:
    """Collect the hardware and software versions recorded in every result file.

    Returns:
        CPU brand, core count, RAM in GB, OS, Python version, the short git commit and the installed
        version of every package in PACKAGES.
    """

    def sh(*cmd: str) -> str:
        """Run a command without a shell and return its stdout.

        Args:
            *cmd: Program and arguments.

        Returns:
            The command's stdout, stripped.
        """
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
    """Read this process's physical footprint and its peak since the last reset_peak().

    The footprint is Activity Monitor's "Memory": it excludes clean file-backed pages such as the
    memory-mapped base vectors.

    Returns:
        The current footprint and the interval peak, in MB.

    Raises:
        OSError: proc_pid_rusage fails.
    """
    r = RusageInfoV4()
    if LIBSYSTEM.proc_pid_rusage(os.getpid(), 4, ctypes.byref(r)) != 0:  # 4 = RUSAGE_INFO_V4
        raise OSError("proc_pid_rusage failed")
    return r.ri_phys_footprint / 2**20, r.ri_interval_max_phys_footprint / 2**20


def reset_peak() -> None:
    """Start a new footprint peak interval for footprint_mb().

    Calls libproc's private proc_reset_footprint_interval (verified on macOS 26.6). Reading the
    interval peak needs no sampling thread, so measured latencies are unaffected.

    Raises:
        OSError: proc_reset_footprint_interval fails.
    """
    if LIBSYSTEM.proc_reset_footprint_interval(os.getpid()) != 0:
        raise OSError("proc_reset_footprint_interval failed")


def disk_mb(eng: object) -> float:
    """Measure the allocated size of an engine's index directory, counted like du.

    Chroma, LanceDB, zvec and sqlite-vec keep their index in a temp dir (the adapter's `dir`); in
    text mode the adapter is wrapped and found as `.engine`.

    Args:
        eng: Engine adapter, possibly wrapped by QueryEmbedder.

    Returns:
        Allocated size in MB; 0 for in-memory engines (no `dir`).
    """
    d = getattr(getattr(eng, "engine", eng), "dir", None)
    return (
        sum(f.stat().st_blocks * 512 for f in Path(d).rglob("*") if f.is_file()) / 2**20
        if d
        else 0.0
    )


async def main(a: argparse.Namespace) -> dict:
    """Run the selected stages for one engine on one dataset.

    Loads the dataset (applying --docs / --queries) and builds the index (load stage). The serial
    stage runs every sweep setting at every k, after 100 unmeasured warm-up queries per setting. The
    operating point then gets 100 more warm-up queries (on text datasets, the top 5 of the first 10
    become example results), and the filter stage, when selected and the dataset has filters, runs
    each case cold then warm. Memory is read after load, after build and as the peak of each stage.

    Args:
        a: Parsed command-line arguments (see the parser at the bottom of this module).

    Returns:
        The result document: dataset meta, engine, metric, env, args, and the load, serial, filter,
        operating_point and memory blocks (text datasets add examples).

    Raises:
        SystemExit: The arguments do not fit the dataset (--docs on a text dataset, no --k of at
            least 10 on a text dataset, a k above the ground-truth width, unknown stages or filters)
            or the engine has no such --metric mode.
    """
    stages, ks = a.stages.split(","), [int(x) for x in a.k.split(",")]
    d = load(a.dataset)
    text = d["meta"]["kind"] == "text"
    if text and a.docs:
        raise SystemExit("--docs is not supported for text datasets (it would drop qrel documents)")
    if text:
        ks = [k for k in ks if k >= 10]  # nDCG@10 needs 10 results
        if not ks:
            raise SystemExit("text datasets need a --k of at least 10")
        if a.queries:
            d["queries_text"] = d["queries_text"][: a.queries]
        d["meta"] = dict(d["meta"], n_queries=len(d["queries_text"]))
    else:
        d = subset(d, a.docs, a.queries, stages)
        if max(ks) > d["gt"].shape[1]:  # recall@k needs k ground-truth neighbours
            raise SystemExit(f"--k up to {d['gt'].shape[1]} (ground truth width)")
    if bad := set(stages) - {"load", "serial", "filter"}:
        raise SystemExit(f"unknown --stages {sorted(bad)}")
    if (  # datasets without filter ground truth skip the filter stage (see below)
        "filter" in stages
        and d.get("gt_filters")
        and (bad := set(a.filters.split(",")) - set(d["gt_filters"]))
    ):
        raise SystemExit(f"unknown --filters {sorted(bad)} for {a.dataset}")
    try:
        eng = make_engine(a.engine, text, str(DATA / ".fastembed"), a.metric)
    except KeyError:
        raise SystemExit(
            f"{a.engine} already ranks by inner product by default; its default run serves --metric ip too"
        ) from None
    out: dict = {
        "dataset": d["meta"],
        "engine": a.engine,
        "metric": eng.metric,
        "env": env(),
        "args": vars(a),
        "serial": [],
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
    for params in eng.sweep:
        eng.set_search(params)
        todo = [k for k in ks if params.get("ef", k) >= k]  # HNSW needs ef >= k
        if not todo:
            continue
        await timed(eng, qs[:100], min(todo))  # warm-up for this setting, unmeasured
        for k in todo:
            got, lat = await timed(eng, qs, k)
            row = {
                "params": params,
                "k": k,
                "latency_ms": latency_summary(lat),
            }
            if text:
                by_q = {q["id"]: [str(x) for x in g] for q, g in zip(d["queries_text"], got)}
                qrels = {q["id"]: d["qrels"][q["id"]] for q in d["queries_text"]}
                row |= {
                    "ndcg@10": ndcg_qrels(by_q, qrels, 10),
                    f"recall@{k}": recall_qrels(by_q, qrels, k),
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
    out["operating_point"] = {}  # the library default
    eng.set_search({})
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
                    "latency_ms": latency_summary(lat),
                    "first_ms": lat[0] * 1000,
                }
            out["filter"].append(row)
            print(json.dumps(row), flush=True)
        peaks["filter"] = footprint_mb()[1]
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
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,  # run_suite.sh names the log from the exact --docs flag
    )
    p.add_argument("dataset")
    p.add_argument("engine", choices=list(ENGINES))
    p.add_argument(
        "--stages",
        default="serial,filter",
        help="load and serial always run; this selects filter",
    )
    p.add_argument("--k", default="1,10,50,100", help="text datasets use the values >= 10")
    p.add_argument("--queries", type=int, help="use only the first N queries")
    p.add_argument(
        "--docs",
        type=int,
        help="vector datasets: index only the first N docs (GT recomputed)",
    )
    p.add_argument("--filters", default="int_1p,int_99p,label_1p,label_50p")
    p.add_argument(
        "--metric",
        choices=["default", "ip"],
        default="default",
        help="the library's default distance, or inner product (cosine where an engine has none)",
    )
    p.add_argument(
        "--stamp",
        default=time.strftime("%Y%m%dT%H%M%S"),
        help="result file stamp; run_suite.sh passes the one in the log name",
    )
    args = p.parse_args()

    print(
        "args: " + json.dumps(vars(args)), flush=True
    )  # first log line: the exact arguments of this attempt

    if args.engine == "moss":
        ensure_latest_moss()
    res = asyncio.run(main(args))
    out_dir = RESULTS / args.dataset
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = ("-ip" if args.metric == "ip" else "") + (f"-docs{args.docs}" if args.docs else "")
    path = out_dir / f"{args.engine}{tag}-{args.stamp}.json"
    path.write_text(json.dumps(res, indent=1) + "\n")

    print(f"wrote {path}")
