"""Shared measurement harness for the suite_*.py runners (one engine, one dataset, one process).

Each runner (suite_defaults.py, suite_tuning.py, suite_filter.py) calls cli() with its own measure
coroutine. cli() parses the common arguments, prints "args: {...}" as the first log line, checks the
Moss version, loads the dataset (--docs / --queries applied), creates the engine, runs its untimed
open() (the Moss session) and the timed build (with memory readings), picks the 100 unmeasured
warm-up queries, then awaits measure(run) and writes the result to
results/<suite>/<dataset>/<engine>[-ip][-docs<N>]-<stamp>.json. run_suite.sh passes the stamp of
the log, results/logs/<suite>-<dataset>-<engine>[-ip][-docs<N>]-<stamp>.log.

Shared pieces a runner uses: timed() (one client, one query at a time, perf_counter around each
search call), measure_pass() (timed + quality: recall@k and nDCG@k vs the exact top-k on vector
datasets; nDCG@10, recall@k and R-precision vs human labels on text datasets), footprint_mb() /
reset_peak() (macOS physical footprint and its interval peak), warm_up().
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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path

import numpy as np

from bench_data import DATA, check_docs, load, subset_gt_path
from engines import MossTextEngine, make_engine
from metrics import latency_summary, ndcg_gt, ndcg_qrels, r_precision, recall, recall_qrels

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

    The suite always benchmarks the latest Moss; cli() checks this before every Moss run.

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


def subset(d: dict, docs: int | None, queries: int | None) -> dict:
    """Limit a vector dataset to its first docs and/or first queries.

    Fewer queries also cut their ground truth (plain and per filter). A doc subset gets its labels
    cut and loads its exact ground truth from data/<name>/gt_docs<N>.npy (bench_data.py
    subset-gt, which run_suite.sh runs), sliced to the queries kept; computing it here would
    inflate the memory baseline. The input dict is not modified.

    Args:
        d: Dataset as returned by bench_data.load().
        docs: Keep only this many docs; None or 0 keeps all.
        queries: Keep only this many queries; None or 0 keeps all.

    Returns:
        A shallow copy of d with the subset applied and meta's n_base / n_queries updated.

    Raises:
        SystemExit: docs is set and outside 1..n_base - 1, or its cached ground truth is missing
            or older than the prepared base vectors.
    """
    d = dict(d, meta=dict(d["meta"]))
    if queries:
        d["queries"], d["gt"] = d["queries"][:queries], d["gt"][:queries]
        d["gt_filters"] = {t: g[:queries] for t, g in d.get("gt_filters", {}).items()}
        d["meta"]["n_queries"] = len(d["queries"])
    if docs:
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
        CPU brand, core count, RAM in GB, OS, Python version, the short git commit, whether
        benchmarks/ has uncommitted changes to tracked files, and the installed version of every
        package in PACKAGES.
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
        "git_dirty": bool(sh("git", "status", "--porcelain", "--untracked-files=no", ".")),
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


def warmup_set(d: dict, all_q: object, measured: int, text: bool) -> tuple[list, str]:
    """Pick 100 warm-up queries that are never measured.

    Warming up on measured queries made those queries faster in their measured pass (zvec 5-9%,
    chroma about 6% on cohere-100k), so the warm-up uses the queries after the measured ones when
    at least 100 exist (--queries below the total). Otherwise a text dataset uses its train-split
    warm-up queries (warmup.jsonl; warming up on corpus texts left Chroma and LanceDB's first
    measured pass on scifact 1.3-1.6x slower in mean latency), and a vector dataset uses 100
    indexed docs as queries.

    Args:
        d: Dataset after subsetting.
        all_q: Every query of the dataset (vectors, or text rows), before --queries.
        measured: Number of measured queries (the first `measured` of all_q).
        text: True for a text dataset.

    Returns:
        The warm-up queries and their source: "queries", "train queries", "doc vectors" or
        "corpus texts".
    """
    spare = all_q[measured : measured + 100]
    if len(spare) == 100:
        return ([q["text"] for q in spare] if text else list(spare)), "queries"
    if text and d.get("warmup_text"):
        return [q["text"] for q in d["warmup_text"]], "train queries"
    if text:
        return [c["text"] for c in d["corpus"][:100]], "corpus texts"
    return list(np.asarray(d["base"][:100])), "doc vectors"


@dataclass
class Run:
    """One engine on one dataset, built and ready to search; what a suite's measure() receives.

    Attributes:
        a: Parsed arguments.
        d: Dataset after --docs / --queries.
        eng: Built engine adapter, at its library-default search setting.
        text: True for a text dataset.
        qs: Measured queries (vectors, or texts on text datasets), in order.
        ks: k values to measure (text datasets: those >= 10).
        warm_qs: 100 unmeasured warm-up queries (see warmup_set).
        memory: Memory block of the result; measure() may add stage peaks to its
            "peak_footprint_mb".
    """

    a: argparse.Namespace
    d: dict
    eng: object
    text: bool
    qs: list
    ks: list[int]
    warm_qs: list
    memory: dict = field(default_factory=dict)


async def warm_up(run: Run, k: int) -> None:
    """Run the 100 warm-up queries once, unmeasured.

    Args:
        run: The run.
        k: Number of results per query.
    """
    await timed(run.eng, run.warm_qs, k)


async def measure_pass(
    run: Run, k: int, flt: dict | None = None, gt: np.ndarray | None = None
) -> dict:
    """Time one pass over every measured query and score it.

    Args:
        run: The run.
        k: Number of results per query.
        flt: Neutral filter applied to every query, or None.
        gt: Ground truth for a filtered pass (vector datasets); None uses the dataset's.

    Returns:
        {"k", "latency_ms" (latency_summary), "first_ms" (the first query's latency), "quality"
        (nDCG@10 on text datasets, recall@k on vector datasets)} plus the measures behind it:
        recall@k and nDCG@k (vector) or nDCG@10, recall@k and R-precision (text).
    """
    got, lat = await timed(run.eng, run.qs, k, flt)
    row = {"k": k, "latency_ms": latency_summary(lat), "first_ms": lat[0] * 1000}
    if run.text:
        by_q = {q["id"]: [str(x) for x in g] for q, g in zip(run.d["queries_text"], got)}
        qrels = {q["id"]: run.d["qrels"][q["id"]] for q in run.d["queries_text"]}
        row |= {
            "ndcg@10": ndcg_qrels(by_q, qrels, 10),
            f"recall@{k}": recall_qrels(by_q, qrels, k),
            "r_precision": r_precision(by_q, qrels),
        }
        row["quality"] = row["ndcg@10"]
    else:
        g = run.d["gt"] if gt is None else gt
        row |= {f"recall@{k}": recall(got, g, k), f"ndcg@{k}": ndcg_gt(got, g, k)}
        row["quality"] = row[f"recall@{k}"]
    return row


async def call(x: object) -> object:
    """Await x if it is awaitable (Moss adapters are async), else return it."""
    return await x if inspect.isawaitable(x) else x


async def build(a: argparse.Namespace, measure: Callable[[Run], Awaitable[dict]]) -> dict:
    """Load, open, build, then run a suite's measure() and assemble its result document.

    Loads the dataset (applying --docs / --queries), creates the engine for --metric, runs its
    untimed open() (recorded as open_s), reads the memory baseline, builds the index (timed as
    build_s, with the build-stage footprint peak) and picks the warm-up queries. measure() then
    runs on the built engine; the engine is closed afterwards.

    Args:
        a: Parsed arguments (see cli()).
        measure: The suite's coroutine; returns its result blocks.

    Returns:
        {"suite", "dataset" (meta), "engine", "metric", "env", "args", "warmup" (source),
        "tunable" (more than one search setting), "load", "memory"} plus measure()'s blocks.

    Raises:
        SystemExit: The arguments do not fit the dataset (--docs on a text dataset, no k of at
            least 10 on a text dataset, a k above the ground-truth width) or the engine has no
            such --metric mode.
    """
    ks = [int(x) for x in a.k.split(",")]
    d = load(a.dataset)
    text = d["meta"]["kind"] == "text"
    all_q = d["queries_text"] if text else d["queries"]  # before --queries: spares warm up
    if text:
        if getattr(a, "docs", None):
            raise SystemExit(
                "--docs is not supported for text datasets (it would drop qrel documents)"
            )
        ks = [k for k in ks if k >= 10]  # nDCG@10 needs 10 results
        if not ks:
            raise SystemExit("text datasets need a --k of at least 10")
        if a.queries:
            d["queries_text"] = d["queries_text"][: a.queries]
        d["meta"] = dict(d["meta"], n_queries=len(d["queries_text"]))
    else:
        d = subset(d, getattr(a, "docs", None), a.queries)
        if max(ks) > d["gt"].shape[1]:  # recall@k needs k ground-truth neighbours
            raise SystemExit(f"--k up to {d['gt'].shape[1]} (ground truth width)")
    try:
        eng = make_engine(a.engine, text, str(DATA / ".fastembed"), a.metric)
    except KeyError:
        raise SystemExit(
            f"{a.engine} already ranks by inner product by default; its default run serves --metric ip too"
        ) from None
    t_open = time.perf_counter()  # outside build_s: Moss session (auth, cloud lookup, model)
    await call(eng.open())
    open_s = time.perf_counter() - t_open
    mem: dict = {"baseline_footprint_mb": footprint_mb()[0], "peak_footprint_mb": {}}
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
        await call(eng.build(d["ids"], d["base"], meta))
    build_s = time.perf_counter() - t0
    mem["peak_footprint_mb"]["build"] = footprint_mb()[1]
    n = len(d["ids"])
    load_block = {
        "docs": n,
        "open_s": open_s,
        "build_s": build_s,
        "docs_per_s": n / build_s,
        "rss_before_build_mb": rss0,
        "rss_after_build_mb": rss_mb(),
    }
    mem |= {
        "footprint_after_build_mb": footprint_mb()[0],
        "rss_after_build_mb": load_block["rss_after_build_mb"],
        "disk_mb": disk_mb(eng),
    }
    print(json.dumps(load_block | mem), flush=True)
    qs = [q["text"] for q in d["queries_text"]] if text else list(d["queries"])
    warm_qs, warm_src = warmup_set(d, all_q, len(qs), text)
    run = Run(a, d, eng, text, qs, ks, warm_qs, mem)
    blocks = await measure(run)
    await call(eng.close())
    load_block["peak_rss_mb"] = (
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20
    )  # bytes on macOS
    return {
        "suite": a.suite,
        "dataset": d["meta"],
        "engine": a.engine,
        "metric": eng.metric,
        "env": env(),
        "args": vars(a),
        "warmup": warm_src,
        "tunable": len(eng.sweep) > 1 or bool(eng.extra),  # False: exact, one search setting
        "load": load_block,
        "memory": mem,
    } | blocks


def run_key(engine: str, metric: str, docs: int | None) -> str:
    """Name a run as run_suite.sh names its log and result: engine[-ip][-docsN].

    Args:
        engine: Engine name.
        metric: Metric mode, "default" or "ip".
        docs: --docs value, or None.

    Returns:
        The run key, e.g. "faiss-hnsw-ip" or "moss-docs25000".
    """
    return engine + ("-ip" if metric == "ip" else "") + (f"-docs{docs}" if docs else "")


def cli(
    suite: str,
    doc: str,
    measure: Callable[[Run], Awaitable[dict]],
    docs: bool = False,
    k: str = "1,10,50,100",
    more: Callable[[argparse.ArgumentParser], None] | None = None,
) -> None:
    """Parse the common arguments, run one suite measurement and write its result file.

    Args:
        suite: Suite name; results go to results/<suite>/<dataset>/.
        doc: The runner's module docstring (the --help text).
        measure: The suite's coroutine (see build()).
        docs: Offer --docs (index only the first N docs of a vector dataset).
        k: Default --k list.
        more: Adds the runner's own arguments to the parser.
    """
    from engines import ENGINES

    p = argparse.ArgumentParser(
        description=doc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,  # run_suite.sh names the log from the exact flags
    )
    p.add_argument("dataset")
    p.add_argument("engine", choices=list(ENGINES))
    p.add_argument("--k", default=k, help="k values; text datasets use those >= 10")
    p.add_argument("--queries", type=int, help="use only the first N queries")
    if docs:
        p.add_argument("--docs", type=int, help="vector datasets: index only the first N docs")
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
    if more:
        more(p)
    a = p.parse_args()
    a.suite = suite
    print("args: " + json.dumps(vars(a)), flush=True)  # first log line: the exact arguments
    if a.engine == "moss":
        ensure_latest_moss()
    res = asyncio.run(build(a, measure))
    out = RESULTS / suite / a.dataset
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{run_key(a.engine, a.metric, getattr(a, 'docs', None))}-{a.stamp}.json"
    path.write_text(json.dumps(res, indent=1) + "\n")
    print(f"wrote {path}")


def applies(suite: str, dataset: str, engine: str, metric: str, docs: int | None) -> str:
    """Tell whether a suite run makes sense for a pair; run_suite.sh asks before each run.

    Args:
        suite: "defaults", "tuning" or "filter".
        dataset: Prepared dataset name.
        engine: Engine name, a key of ENGINES.
        metric: "default" or "ip".
        docs: --docs value, or None.

    Returns:
        "" when it applies, else the reason to skip it.
    """
    from engines import ENGINES, MossTextEngine

    meta = json.loads((DATA / dataset / "meta.json").read_text())
    text = meta["kind"] == "text"
    cls = ENGINES[engine]
    if metric == "ip" and "ip" not in getattr(cls, "func", cls).METRICS:
        return (
            f"{engine}: its default metric is already inner product (the default run serves both)"
        )
    if docs and (text or suite != "defaults"):
        return "--docs applies to the defaults suite on vector datasets only"
    if suite == "filter" and not meta.get("filters"):
        return f"{dataset} has no filter cases"
    if suite == "tuning":
        eng = MossTextEngine if text and engine == "moss" else cls(metric)
        if len(eng.sweep) < 2 and not eng.extra:
            return f"{engine} has one search setting (exact); the defaults suite measures it"
    return ""
