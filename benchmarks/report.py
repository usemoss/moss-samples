"""Turn results/<dataset>/*.json into results/report.html (interactive Plotly charts + tables) and results/summary.md.

usage: $PWD/.venv/bin/python report.py        then open results/report.html in a browser (works offline; plotly.js is inlined)

Per dataset, using each engine's newest full run (``-docs`` subset runs get their own section):
  charts  recall (vector) or nDCG@10 (text) vs speed (Pareto frontier per engine; dropdowns: speed metric = QPS / p50 / p95 / p99 / p99.9 /
          mean, and k), concurrency ladder (QPS, and latency with a metric dropdown), latency percentiles at the
          operating point (line per engine), build cost (dropdown: build time / docs per s), memory (dropdown: index,
          build and search peaks, RSS increase, disk; one point per engine), filtered search (line per engine across
          the filter cases; dropdown: warm recall, cold / warm latency and QPS, cold first-query latency); the
          <dataset>-subsets section (--docs runs) has a scaling-vs-corpus-size chart instead
Axes: log only where the values span 10x or more, titled "(log scale)"; recall, nDCG and memory are always linear.
  tables  operating point, full serial sweep, concurrency ladder, filter cases (cold and warm), memory, engines that
          did not finish (DNF)
Refuses to write anything (exit 1, "STALE <log>: <last line>") when an engine's newest attempt failed but an older
result for the same run would be shown.
Every chart: hover shows exact values and parameters; click a legend entry to hide an engine, double-click to isolate it.
Labels: recall@k is measured against the exact top-k; nDCG@10 and R-precision against human relevance labels.
Text datasets add R-precision columns and example results (top 5 of 10 queries per engine, ✓ = labelled relevant).
"""

import html
import json
import re
from pathlib import Path

import plotly.graph_objects as go

RESULTS = Path(__file__).parent / "results"
# Fixed engine -> (light hue, dark hue, marker, dash); validated categorical palette (8 hues, light and dark steps).
# Color follows the engine, never its rank. FAISS flat and HNSW share a hue and differ by dash and marker.
STYLE = {
    "moss": ("#2a78d6", "#3987e5", "circle", "solid"),
    "chroma": ("#eb6834", "#d95926", "square", "solid"),
    "lancedb": ("#1baf7a", "#199e70", "triangle-up", "solid"),
    "qdrant-local": ("#eda100", "#c98500", "diamond", "solid"),
    "faiss-flat": ("#e87ba4", "#d55181", "cross", "dash"),
    "faiss-hnsw": ("#e87ba4", "#d55181", "x", "solid"),
    "zvec": ("#008300", "#008300", "triangle-down", "solid"),
    "sqlite-vec": ("#4a3aa7", "#9085e9", "triangle-left", "solid"),
    "duckdb-vss": ("#e34948", "#e66767", "triangle-right", "solid"),
}
LATENCY = {"p50": "p50", "p95": "p95", "p99": "p99", "p99.9": "p999", "mean": "mean"}
MEMORY = ["index", "build peak", "search peak", "RSS increase over build", "on disk"]
STAGES = ["build", "serial", "filter", "concurrent"]


def newest_runs() -> dict[str, dict[str, dict]]:
    """{dataset: {engine[-docsN]: newest result}}; file names end in a sortable timestamp."""
    runs: dict[str, dict[str, dict]] = {}
    for p in sorted(RESULTS.glob("*/*.json")):
        r = json.loads(p.read_text())
        key = r["engine"] + (
            f"-docs{r['args']['docs']}" if r["args"].get("docs") else ""
        )
        runs.setdefault(p.parent.name, {})[key] = r | {
            "file": str(p.relative_to(RESULTS))
        }
    return runs


def attempts() -> list[tuple[str, str, bool, str, str]]:
    """Newest attempt per run: (dataset, run key, succeeded, last log line, log name). run_suite.sh names each log
    results/logs/<dataset>-<engine>[-docs<N>]-<stamp>.log and its result results/<dataset>/<engine>[-docs<N>]-<stamp>.json
    with the same stamp. run.py prints `wrote <path>` last, so a log without a `wrote ` line was killed, crashed or is
    still running. Other logs (fetch-, prepare-, ...) are skipped: their names do not match."""
    name = re.compile(
        rf"(.+)-((?:{'|'.join(map(re.escape, STYLE))})(?:-docs\d+)?)-(\d{{8}}T\d{{6}})"
    )
    newest: dict[tuple[str, str], tuple[str, str, bool, str, str]] = {}
    for log in sorted(
        (RESULTS / "logs").glob("*.log")
    ):  # same run key: sorted by stamp, the newest wins
        if not (m := name.fullmatch(log.stem)):
            continue
        text = log.read_text(errors="replace")
        last = (text.strip().splitlines() or ["(empty log)"])[-1][:160]
        ok = re.search(r"^wrote ", text, re.M) is not None
        newest[m[1], m[2]] = (m[1], m[2], ok, last, log.name)
    return list(newest.values())


def stale(
    runs: dict[str, dict[str, dict]], att: list[tuple[str, str, bool, str, str]]
) -> list[str]:
    """`STALE <log>: <last line>` for every failed newest attempt whose run key still has an older result."""
    return [
        f"STALE {log}: {last}"
        for ds, key, ok, last, log in att
        if not ok and key in runs.get(ds, {})
    ]


def mem_gb(r: dict) -> dict[str, float]:
    """One run's memory in GB: footprint over the post-load baseline (index after build, build peak, search peak =
    max of the serial / filter / concurrent peaks that ran), RSS increase over the build, index size on disk."""
    m, peaks = r["memory"], r["memory"]["peak_footprint_mb"]
    base = m["baseline_footprint_mb"]
    search = max(peaks[s] for s in STAGES[1:] if s in peaks)
    return {
        "index": (m["footprint_after_build_mb"] - base) / 1024,
        "build peak": (peaks["build"] - base) / 1024,
        "search peak": (search - base) / 1024,
        "RSS increase over build": (
            m["rss_after_build_mb"] - r["load"]["rss_before_build_mb"]
        )
        / 1024,
        "on disk": m["disk_mb"] / 1024,
    }


def metric_of(r: dict) -> str:
    """Label of the headline measure: nDCG@10 for text datasets, recall@k against the exact top-k for vector datasets."""
    return (
        "nDCG@10 (human labels)"
        if r["dataset"]["kind"] == "text"
        else "recall@k (vs exact top-k)"
    )


def at_op(r: dict) -> list[dict]:
    """Serial rows measured at the run's operating point (one per k)."""
    return [row for row in r["serial"] if row["params"] == r["operating_point"]]


def frontier(
    points: list[tuple[float, float, str, float]], higher_is_better: bool
) -> list[tuple[float, float, str, float]]:
    """Pareto frontier (ann-benchmarks create_pointset): keep points that no other point beats on both axes."""
    out, best = [], None
    for p in sorted(points, key=lambda p: -p[0]):
        if best is None or (p[1] > best if higher_is_better else p[1] < best):
            out.append(p)
            best = p[1]
    return sorted(out)


def trace_style(engine: str) -> dict:
    """Plotly line/marker style for an engine (subset runs reuse their engine's style)."""
    color, _, symbol, dash = STYLE.get(
        engine.split("-docs")[0], ("#52514e", "#c3c2b7", "circle", "solid")
    )
    return {
        "line": {"color": color, "width": 2, "dash": dash},
        "marker": {"color": color, "symbol": symbol, "size": 9},
    }


def yview(title: str, vals: list[float | None], log: bool = True) -> dict:
    """Relayout keys for a y axis showing `vals` (also used by dropdown buttons): log scale with 1-2-5 ticks and
    "(log scale)" in the title only when the values span 10x or more, since a narrower log axis labels its ticks
    with bare digits ("5" for 500); `log=False` forces linear (recall, nDCG, memory)."""
    v = [x for x in vals if x is not None and x > 0]
    log = log and bool(v) and max(v) >= 10 * min(v)
    return {
        "yaxis.title.text": f"{title} (log scale)" if log else title,
        "yaxis.type": "log" if log else "linear",
        "yaxis.dtick": "D2" if log else None,
        "yaxis.tickmode": "linear"
        if log
        else "auto",  # else a log->linear switch keeps whole-number ticks
    }


def layout(fig: go.Figure, title: str, x: str, y: dict) -> go.Figure:
    """Shared layout: recessive grid, legend on the right (click to hide, double-click to isolate); `y` = yview()."""
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="#fcfcfb",
        plot_bgcolor="#fcfcfb",
        title={
            "text": title,
            "x": 0,
            "y": 0.975,
            "yanchor": "top",
        },  # above the dropdown row
        height=540,
        hovermode="closest",
        legend={"title": {"text": "click / double-click"}},
        margin={"t": 130, "r": 20},
        xaxis_title=x,
        font={"family": "system-ui, sans-serif", "size": 13},
    )
    fig.update_layout({k.replace(".", "_"): v for k, v in y.items()})
    return fig


def menu(buttons: list[dict], x: float) -> dict:
    """A dropdown above the plot area."""
    return {
        "type": "dropdown",
        "buttons": buttons,
        "x": x,
        "xanchor": "left",
        "y": 1.14,
        "yanchor": "top",
        "showactive": True,
        # explicit ink and fill: readable in both themes (the dark-mode relayout changes the global font color)
        "font": {"color": "#0b0b0b"},
        "bgcolor": "#ffffff",
        "bordercolor": "#52514e",
    }


def tradeoff(name: str, runs: dict[str, dict]) -> go.Figure:
    """Recall (vector) or nDCG@10 (text) vs speed, one Pareto line per (engine, k); an exact engine is a dotted line ending at its point. Dropdowns pick the speed metric and k."""
    speeds = {"serial QPS": ("qps", True)} | {
        f"{lbl} latency, ms": (key, False) for lbl, key in LATENCY.items()
    }
    ks = sorted({row["k"] for r in runs.values() for row in r["serial"]})
    lo = {
        k: min(
            row["headline"]
            for r in runs.values()
            for row in r["serial"]
            if row["k"] == k
        )
        for k in ks
    }  # an exact engine's line starts at the lowest value any engine reached at that k
    fig, data = go.Figure(), {s: [] for s in speeds}
    label = metric_of(next(iter(runs.values()))).split(" ")[0]  # recall@k or nDCG@10
    for eng, r in runs.items():
        for k in ks:
            rows = [row for row in r["serial"] if row["k"] == k]
            pts_by = {
                s: frontier(
                    [
                        (
                            row["headline"],
                            row["qps"] if key == "qps" else row["latency_ms"][key],
                            json.dumps(row["params"]) if row["params"] else "exact",
                            row["headline"],
                        )
                        for row in rows
                    ],
                    higher,
                )
                for s, (key, higher) in speeds.items()
            }
            line = (
                len(rows) == 1 and not rows[0]["params"] and lo[k] < rows[0]["headline"]
            )  # exact engine: one point per k
            for s, pts in pts_by.items():
                data[s].append([(lo[k], *pts[0][1:]), pts[0]] if line else pts)
            first = data["serial QPS"][-1]
            style = trace_style(eng)
            if line:
                style["line"]["dash"], style["marker"]["size"] = "dot", [0, 9]
            fig.add_trace(
                go.Scatter(
                    x=[p[0] for p in first],
                    y=[p[1] for p in first],
                    customdata=[[p[2], p[3]] for p in first],
                    name=f"{eng} (exact)" if line else eng,
                    legendgroup=eng,
                    showlegend=k == ks[-1],
                    visible=k == ks[-1],
                    mode="lines+markers",
                    meta=k,
                    hovertemplate=f"<b>{eng}</b> k={k}<br>%{{customdata[0]}}<br>{label} %{{customdata[1]:.4f}}"
                    "<br>%{y:.3f}<extra></extra>",
                    **style,
                )
            )
    ytitle = {
        s: yview(
            f"{s} ({'higher' if hi else 'lower'} is better)",
            [p[1] for t in data[s] for p in t],
        )
        for s, (_, hi) in speeds.items()
    }
    speed_buttons = [
        {
            "label": s,
            "method": "update",
            "args": [
                {
                    "x": [[p[0] for p in t] for t in data[s]],
                    "y": [[p[1] for p in t] for t in data[s]],
                    "customdata": [[[p[2], p[3]] for p in t] for t in data[s]],
                },
                ytitle[s],
            ],
        }
        for s in speeds
    ]
    k_buttons = [
        {
            "label": f"k = {k}",
            "method": "restyle",
            "args": [
                {
                    "visible": [tr.meta == k for tr in fig.data],
                    "showlegend": [tr.meta == k for tr in fig.data],
                }
            ],
        }
        for k in reversed(ks)
    ]
    fig.update_layout(updatemenus=[menu(speed_buttons, 0), menu(k_buttons, 0.3)])
    r0 = next(iter(runs.values()))
    return layout(
        fig,
        f"{name}: {metric_of(r0)} vs speed (Pareto frontier per engine)",
        metric_of(r0),
        ytitle["serial QPS"],
    )


def ladder(name: str, runs: dict[str, dict]) -> list[go.Figure]:
    """Concurrency ladder: QPS vs clients, and latency vs clients with a percentile dropdown (two charts)."""
    runs = {e: r for e, r in runs.items() if r["concurrent"]}
    if not runs:
        return []
    qps, lat = go.Figure(), go.Figure()
    for eng, r in runs.items():
        lv = [c["level"] for c in r["concurrent"]]
        qps.add_trace(
            go.Scatter(
                x=lv,
                y=[c["qps"] for c in r["concurrent"]],
                name=eng,
                mode="lines+markers",
                hovertemplate=f"<b>{eng}</b><br>%{{x}} clients<br>%{{y:.0f}} QPS<extra></extra>",
                **trace_style(eng),
            )
        )
        lat.add_trace(
            go.Scatter(
                x=lv,
                y=[c["latency_ms"]["p99"] for c in r["concurrent"]],
                name=eng,
                mode="lines+markers",
                hovertemplate=f"<b>{eng}</b><br>%{{x}} clients<br>%{{y:.3f}} ms<extra></extra>",
                **trace_style(eng),
            )
        )
    order = sorted(
        LATENCY.items(), key=lambda kv: kv[0] != "p99"
    )  # p99 first: the chart opens on p99
    lat_y = {
        lbl: yview(
            f"{lbl} latency, ms",
            [c["latency_ms"][key] for r in runs.values() for c in r["concurrent"]],
        )
        for lbl, key in order
    }
    lat.update_layout(
        updatemenus=[
            menu(
                [
                    {
                        "label": lbl,
                        "method": "update",
                        "args": [
                            {
                                "y": [
                                    [c["latency_ms"][key] for c in r["concurrent"]]
                                    for r in runs.values()
                                ]
                            },
                            lat_y[lbl],
                        ],
                    }
                    for lbl, key in order
                ],
                0,
            )
        ]
    )
    return [
        layout(
            qps,
            f"{name}: throughput vs concurrent clients (operating point)",
            "concurrent clients",
            yview("QPS", [y for t in qps.data for y in t.y]),
        ),
        layout(
            lat,
            f"{name}: latency vs concurrent clients (operating point)",
            "concurrent clients",
            lat_y["p99"],
        ),
    ]


def latency_lines(name: str, runs: dict[str, dict]) -> go.Figure:
    """Serial latency percentiles at the operating point (largest k): one line per engine from p50 to p99.9; hover
    adds the mean."""
    pcts = [p for p in LATENCY if p != "mean"]
    fig = go.Figure()
    for e, r in runs.items():
        lat = max(at_op(r), key=lambda row: row["k"])["latency_ms"]
        fig.add_trace(
            go.Scatter(
                x=pcts,
                y=[lat[LATENCY[p]] for p in pcts],
                name=e,
                mode="lines+markers",
                hovertemplate=f"<b>{e}</b><br>%{{x}}: %{{y:.3f}} ms<br>mean {lat['mean']:.3f} ms<extra></extra>",
                **trace_style(e),
            )
        )
    return layout(
        fig,
        f"{name}: serial latency percentiles at the operating point",
        "percentile",
        yview("latency, ms", [y for t in fig.data for y in t.y]),
    )


def build_bars(name: str, runs: dict[str, dict]) -> go.Figure:
    """Index build cost per engine; dropdown: build seconds, docs per second."""
    engines = list(runs)
    views = {
        "build time, s": [runs[e]["load"]["build_s"] for e in engines],
        "docs per second": [runs[e]["load"]["docs_per_s"] for e in engines],
    }
    fig = go.Figure(
        go.Bar(
            x=engines,
            y=views["build time, s"],
            marker={
                "color": [trace_style(e)["line"]["color"] for e in engines],
                "line": {"color": "#fcfcfb", "width": 2},
            },
            hovertemplate="<b>%{x}</b><br>build time, s: %{y:.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        updatemenus=[
            menu(
                [
                    {
                        "label": v,
                        "method": "update",
                        "args": [
                            {
                                "y": [vals],
                                "hovertemplate": f"<b>%{{x}}</b><br>{v}: %{{y:.2f}}<extra></extra>",
                            },
                            yview(v, vals),
                        ],
                    }
                    for v, vals in views.items()
                ],
                0,
            )
        ]
    )
    fig = layout(
        fig,
        f"{name}: index build",
        "engine",
        yview("build time, s", views["build time, s"]),
    )
    fig.update_layout(showlegend=False)
    return fig


def memory_lines(name: str, runs: dict[str, dict]) -> go.Figure:
    """Memory per engine in GB (see mem_gb): x = engine, one line through every engine's value for the measure the
    dropdown picks; each point keeps its engine's color and marker."""
    mem = {e: mem_gb(r) for e, r in runs.items()}
    engines = list(runs)
    marks = [trace_style(e)["marker"] for e in engines]

    def hover(m: str) -> str:
        """Hover text for one measure."""
        return f"<b>%{{x}}</b><br>{m}: %{{y:.3f}} GB<extra></extra>"

    fig = go.Figure(
        go.Scatter(
            x=engines,
            y=[mem[e][MEMORY[0]] for e in engines],
            mode="lines+markers",
            line={"color": "#52514e", "width": 1},
            marker={
                "color": [m["color"] for m in marks],
                "symbol": [m["symbol"] for m in marks],
                "size": 11,
            },
            hovertemplate=hover(MEMORY[0]),
        )
    )
    fig.update_layout(
        updatemenus=[
            menu(
                [
                    {
                        "label": m,
                        "method": "update",
                        "args": [
                            {
                                "y": [[mem[e][m] for e in engines]],
                                "hovertemplate": hover(m),
                            },
                            {"yaxis.title.text": f"{m}, GB"},
                        ],
                    }
                    for m in MEMORY
                ],
                0,
            )
        ]
    )
    fig = layout(
        fig,
        f"{name}: memory (footprint over the post-load baseline; on disk = index files)",
        "engine",
        yview(f"{MEMORY[0]}, GB", [], log=False),
    )
    fig.update_layout(showlegend=False)
    return fig


def kept(tag: str) -> float:
    """Percent of docs a VectorDBBench filter case keeps: int_<p>p drops the first p% of ids, label_<p>p keeps p%."""
    p = float(tag.split("_")[1].rstrip("p"))
    return 100 - p if tag.startswith("int") else p


def filter_lines(name: str, runs: dict[str, dict]) -> go.Figure | None:
    """Filtered search: one line per engine across the filter cases, ordered from most to fewest docs kept; dropdown:
    warm recall@100, cold / warm latency percentiles and QPS, cold first-query latency. A case an engine did not run
    (different --filters) is left as a gap."""
    runs = {e: r for e, r in runs.items() if r["filter"]}
    if not runs:
        return None
    tags = sorted(
        dict.fromkeys(f["filter"] for r in runs.values() for f in r["filter"]),
        key=lambda t: -kept(t),
    )
    xs = [f"{t} ({kept(t):g}% kept)" for t in tags]
    by = {e: {f["filter"]: f for f in r["filter"]} for e, r in runs.items()}
    views: dict[str, tuple[str, str, str | None]] = {
        "warm recall@100": ("warm", "recall@100", None)
    }
    for p in ("warm", "cold"):
        views |= {
            f"{p} {lbl} latency, ms": (p, "latency_ms", key)
            for lbl, key in LATENCY.items()
        }
        views[f"{p} QPS"] = (p, "qps", None)
    views["cold first-query latency, ms"] = ("cold", "first_ms", None)

    def val(e: str, t: str, view: tuple[str, str, str | None]) -> float | None:
        """One engine's value for a filter case and dropdown view; None if the engine did not run that case."""
        if t not in by[e]:
            return None
        x = by[e][t][view[0]][view[1]]
        return x[view[2]] if view[2] else x

    ys = {
        v: [[val(e, t, view) for t in tags] for e in runs] for v, view in views.items()
    }
    fig = go.Figure()
    for e, y in zip(runs, ys["warm recall@100"]):
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=y,
                name=e,
                mode="lines+markers",
                hovertemplate=f"<b>{e}</b><br>%{{x}}<br>%{{y:.4g}}<extra></extra>",
                **trace_style(e),
            )
        )
    yaxes = {
        v: yview(v, [x for y in ys[v] for x in y], log="recall" not in v) for v in views
    }
    fig.update_layout(
        updatemenus=[
            menu(
                [
                    {"label": v, "method": "update", "args": [{"y": ys[v]}, yaxes[v]]}
                    for v in views
                ],
                0,
            )
        ]
    )
    return layout(
        fig,
        f"{name}: filtered search (VectorDBBench int / label cases)",
        "filter case (share of docs kept)",
        yaxes["warm recall@100"],
    )


def scaling(name: str, full: dict[str, dict], subs: dict[str, dict]) -> go.Figure:
    """Metric against corpus size per engine: its --docs runs plus its full run (if any), each at its own operating
    point and largest k; the dropdown picks the metric (log axes as in yview(); recall, nDCG and memory linear). Hover shows docs, queries used and the operating point."""
    r0 = next(iter(subs.values()))
    views = {
        "p50 latency, ms": (lambda r, row: row["latency_ms"]["p50"], True),
        "p99 latency, ms": (lambda r, row: row["latency_ms"]["p99"], True),
        "serial QPS": (lambda r, row: row["qps"], True),
        metric_of(r0): (lambda r, row: row["headline"], False),
        "index memory, GB": (lambda r, row: mem_gb(r)["index"], False),
        "build peak memory, GB": (lambda r, row: mem_gb(r)["build peak"], False),
        "build time, s": (lambda r, row: r["load"]["build_s"], True),
    }
    by: dict[str, list[tuple[dict, dict]]] = {}
    for r in [
        *subs.values(),
        *(r for e, r in full.items() if e in {s["engine"] for s in subs.values()}),
    ]:
        by.setdefault(r["engine"], []).append(
            (r, max(at_op(r), key=lambda row: row["k"]))
        )
    fig = go.Figure()
    for eng, pts in by.items():
        pts.sort(key=lambda p: p[0]["load"]["docs"])
        fig.add_trace(
            go.Scatter(
                x=[r["load"]["docs"] for r, _ in pts],
                y=[views["p50 latency, ms"][0](r, row) for r, row in pts],
                customdata=[
                    [
                        r["args"].get("queries") or r["dataset"]["n_queries"],
                        json.dumps(row["params"]) if row["params"] else "exact",
                    ]
                    for r, row in pts
                ],
                name=eng,
                mode="lines+markers",
                hovertemplate=f"<b>{eng}</b><br>%{{x:,}} docs, %{{customdata[0]}} queries<br>%{{customdata[1]}}"
                "<br>%{y:.4g}<extra></extra>",
                **trace_style(eng),
            )
        )
    ys = {
        v: [[f(r, row) for r, row in pts] for pts in by.values()]
        for v, (f, _) in views.items()
    }
    yaxes = {
        v: yview(v, [y for t in ys[v] for y in t], log) for v, (_, log) in views.items()
    }
    fig.update_layout(
        updatemenus=[
            menu(
                [
                    {"label": v, "method": "update", "args": [{"y": ys[v]}, yaxes[v]]}
                    for v in views
                ],
                0,
            )
        ]
    )
    fig = layout(
        fig,
        f"{name}: scaling with corpus size (operating point, largest k)",
        "docs",
        yaxes["p50 latency, ms"],
    )
    docs = [x for t in fig.data for x in t.x]
    if max(docs) >= 10 * min(
        docs
    ):  # same rule as yview(): log only over a decade or more
        fig.update_layout(xaxis_type="log", xaxis_title="docs (log scale)")
    return fig


def table(head: list[str], rows: list[list[str]]) -> tuple[list[str], str]:
    """(markdown lines, html) for one table."""
    md = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + [
        "| " + " | ".join(r) + " |" for r in rows
    ]
    th = "".join(f"<th>{html.escape(h)}</th>" for h in head)
    tb = "".join(
        "<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>"
        for r in rows
    )
    return (
        md,
        f"<div class='tw'><table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></div>",
    )


def examples(runs: dict[str, dict]) -> str:
    """HTML: each engine's top 5 for the first 10 queries at its operating point (text datasets); ✓ = labelled
    relevant in the dataset. One collapsed block per query. Empty string when no run has examples."""
    runs = {e: r for e, r in runs.items() if r.get("examples")}
    if not runs:
        return ""
    out = [
        "<h3>Example results (top 5 at the operating point; ✓ = labelled relevant in the dataset)</h3>"
    ]
    for i, ex in enumerate(next(iter(runs.values()))["examples"]):
        rows = "".join(
            f"<tr><td>{html.escape(e)}</td><td>{n}</td><td>{'✓' if x['relevant'] else ''}</td>"
            f"<td class='snip'>{html.escape(x['text'])}</td></tr>"
            for e, r in runs.items()
            for n, x in enumerate(r["examples"][i]["results"], 1)
        )
        out.append(
            f"<details><summary>{html.escape(ex['query'])}</summary><div class='tw'><table><thead><tr><th>engine</th>"
            f"<th>rank</th><th>relevant</th><th>result (first 240 characters)</th></tr></thead><tbody>{rows}</tbody>"
            "</table></div></details>"
        )
    return "".join(out)


def section(
    title: str, runs: dict[str, dict], figs: list[go.Figure], missing: list[str]
) -> tuple[list[str], list]:
    """Markdown lines and an ordered list of HTML fragments / figures for one dataset or its --docs subsets."""
    if not runs:  # only failed attempts: heading and the DNF table, no charts
        md = [f"## {title}", "", "No run finished.", "", "### Did not finish", ""]
        m, h = table(["engine and reason"], [[x] for x in missing])
        return md + m + [""], [
            f"<h2>{html.escape(title)}</h2><p>No run finished.</p><h3>Did not finish</h3>{h}"
        ]
    r0 = next(iter(runs.values()))
    text = r0["dataset"]["kind"] == "text"
    intro = (
        "Runs on the first N docs (--docs, ground truth recomputed); the scaling chart adds the full run when it exists."
        if title.endswith("-subsets")
        else f"{r0['dataset']['n_base']:,} docs, {r0['dataset'].get('n_queries')} queries. Operating point = fastest "
        "sweep setting with recall@k >= --target-recall (text datasets: highest nDCG@10)."
    )
    md, parts = (
        [f"## {title}", "", intro, ""],
        [f"<h2>{html.escape(title)}</h2><p>{html.escape(intro)}</p>", *figs],
    )

    def add(name: str, head: list[str], rows: list[list[str]]) -> None:
        """Append one table to both outputs."""
        m, h = table(head, rows)
        md.extend(["", f"### {name}", "", *m])
        parts.append(f"<h3>{html.escape(name)}</h3>{h}")

    op = []
    for e, r in runs.items():
        best = max(r["concurrent"], key=lambda c: c["qps"], default=None)
        g = mem_gb(r)
        for row in at_op(r):
            lat = row["latency_ms"]
            op.append(
                [
                    e,
                    json.dumps(row["params"]) if row["params"] else "exact",
                    str(row["k"]),
                    f"{row['headline']:.4f}",
                    *([f"{row['r_precision']:.4f}"] if text else []),
                    f"{lat['p50']:.3f}",
                    f"{lat['p95']:.3f}",
                    f"{lat['p99']:.3f}",
                    f"{lat['mean']:.3f}",
                    f"{row['qps']:.0f}",
                    f"{best['qps']:.0f} @ {best['level']}" if best else "-",
                    f"{r['load']['build_s']:.1f}",
                    f"{g['index']:.2f}",
                    f"{g['build peak']:.2f}",
                    f"{g['on disk']:.2f}",
                ]
            )
    add(
        "Operating point",
        [
            "engine",
            "params",
            "k",
            metric_of(r0),
            *(["R-precision"] if text else []),
            "p50 ms",
            "p95 ms",
            "p99 ms",
            "mean ms",
            "serial QPS",
            "max QPS @ clients",
            "build s",
            "index GB",
            "build peak GB",
            "disk GB",
        ],
        op,
    )
    add(
        "Full serial sweep",
        [
            "engine",
            "params",
            "k",
            metric_of(r0),
            *(["R-precision"] if text else []),
            "p50 ms",
            "p99 ms",
            "mean ms",
            "QPS",
        ],
        [
            [
                e,
                json.dumps(row["params"]) if row["params"] else "exact",
                str(row["k"]),
                f"{row['headline']:.4f}",
                *([f"{row['r_precision']:.4f}"] if text else []),
                f"{row['latency_ms']['p50']:.3f}",
                f"{row['latency_ms']['p99']:.3f}",
                f"{row['latency_ms']['mean']:.3f}",
                f"{row['qps']:.0f}",
            ]
            for e, r in runs.items()
            for row in r["serial"]
        ],
    )
    conc = {e: r["concurrent"] for e, r in runs.items() if r["concurrent"]}
    if conc:
        levels = [c["level"] for c in next(iter(conc.values()))]
        add(
            "Concurrency ladder (QPS / p99 ms)",
            ["engine"] + [f"{lv} clients" for lv in levels],
            [
                [e] + [f"{c['qps']:.0f} / {c['latency_ms']['p99']:.2f}" for c in cs]
                for e, cs in conc.items()
            ],
        )
    filt = [
        [
            e,
            f["filter"],
            f"{f['cold']['recall@100']:.4f}",
            f"{f['warm']['recall@100']:.4f}",
            f"{f['cold']['first_ms']:.3f}",
            *(
                f"{f[p]['latency_ms'][x]:.3f}"
                for p in ("cold", "warm")
                for x in ("p50", "p99", "mean")
            ),
            f"{f['cold']['qps']:.0f}",
            f"{f['warm']['qps']:.0f}",
        ]
        for e, r in runs.items()
        for f in r["filter"]
    ]
    if filt:
        add(
            "Filtered search (k=100; cold = first use of the filter, warm = second pass)",
            [
                "engine",
                "filter",
                "recall@100 cold",
                "recall@100 warm",
                "cold first query ms",
                "cold p50 ms",
                "cold p99 ms",
                "cold mean ms",
                "warm p50 ms",
                "warm p99 ms",
                "warm mean ms",
                "cold QPS",
                "warm QPS",
            ],
            filt,
        )
    mem_rows = []
    for e, r in runs.items():
        m, g = r["memory"], mem_gb(r)
        base, peaks = m["baseline_footprint_mb"], m["peak_footprint_mb"]
        mem_rows.append(
            [
                e,
                f"{base / 1024:.2f}",
                f"{g['index']:.2f}",
                *(
                    f"{(peaks[s] - base) / 1024:.2f}" if s in peaks else "-"
                    for s in STAGES
                ),
                f"{g['RSS increase over build']:.2f}",
                f"{g['on disk']:.2f}",
                f"{r['load']['peak_rss_mb'] / 1024:.2f}",
            ]
        )
    add(
        "Memory (GB; footprint values are over the post-load baseline)",
        [
            "engine",
            "baseline footprint",
            "index",
            "build peak",
            "serial peak",
            "filter peak",
            "concurrent peak",
            "RSS increase over build",
            "on disk",
            "process peak RSS (whole run)",
        ],
        mem_rows,
    )
    parts.append(examples(runs))
    if missing:
        add("Did not finish", ["engine and reason"], [[m] for m in missing])
    return md + [""], parts


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Moss vector benchmark</title><style>
:root{--surface:#fcfcfb;--ink:#0b0b0b;--muted:#52514e;--rule:#e4e3df}
@media (prefers-color-scheme:dark){:root{--surface:#1a1a19;--ink:#ffffff;--muted:#c3c2b7;--rule:#3a3a37}}
body{background:var(--surface);color:var(--ink);font:15px/1.5 system-ui,sans-serif;margin:0 auto;max-width:1200px;
padding:16px}h2{margin-top:48px;border-top:1px solid var(--rule);padding-top:16px}p{color:var(--muted)}
.tw{overflow-x:auto}table{border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:13px}
th,td{border-bottom:1px solid var(--rule);padding:4px 10px;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
td.snip{white-space:normal;text-align:left;min-width:320px}summary{cursor:pointer;margin:6px 0}
</style></head><body><h1>Moss vector benchmark</h1><p>__ENV__</p>
<p>Hover any point or bar for exact values. Click a legend entry to hide an engine; double-click to isolate it.
Dropdowns above each chart switch the metric.</p>__BODY__
<script>
// Dark mode: the same hues stepped for the dark surface (validated palette), applied after Plotly renders.
const DARK = __DARK__;
if (matchMedia("(prefers-color-scheme: dark)").matches) {
  const swap = c => Array.isArray(c) ? c.map(swap) : (DARK[c] || c);
  for (const el of document.querySelectorAll(".js-plotly-plot")) {
    Plotly.relayout(el, {paper_bgcolor: "#1a1a19", plot_bgcolor: "#1a1a19", "font.color": "#ffffff",
      "xaxis.gridcolor": "#3a3a37", "yaxis.gridcolor": "#3a3a37"});
    el.data.forEach((t, i) => Plotly.restyle(el, {"marker.color": [swap(t.marker && t.marker.color)],
      "line.color": [swap(t.line && t.line.color)],
      "marker.line.color": [swap(t.marker && t.marker.line && t.marker.line.color)]}, [i]));
  }
}
</script></body></html>"""


def main() -> None:
    """Write results/report.html (interactive) and results/summary.md for every dataset with results."""
    runs = newest_runs()
    if not runs:
        raise SystemExit("no results/<dataset>/*.json yet")
    att = attempts()
    if bad := stale(runs, att):
        raise SystemExit(
            "\n".join(
                [
                    *bad,
                    "The newest attempt of these runs failed (killed, crashed or still running) but an older result "
                    "exists. Read the log, then rerun, or move the old result out of results/ deliberately. "
                    "Nothing was written.",
                ]
            )
        )
    env = next(iter(next(iter(runs.values())).values()))["env"]
    env_line = (
        f"Hardware: {env['cpu']}, {env['cores']} cores, {env['ram_gb']} GB, {env['os']}. "
        f"Versions: {', '.join(f'{p} {v}' for p, v in env['versions'].items())}."
    )
    md, parts = (
        [
            "# Benchmark results",
            "",
            env_line,
            "",
            "Interactive charts: report.html",
            "",
        ],
        [],
    )
    for name in sorted(set(runs) | {ds for ds, _, ok, _, _ in att if not ok}):
        full = {e: r for e, r in runs.get(name, {}).items() if "-docs" not in e}
        subs = {e: r for e, r in runs.get(name, {}).items() if "-docs" in e}
        dnfs = [(key, last) for ds, key, ok, last, _ in att if ds == name and not ok]
        dnf_full = [f"{k}: DNF, {last}" for k, last in dnfs if "-docs" not in k]
        dnf_subs = [f"{k}: DNF, {last}" for k, last in dnfs if "-docs" in k]
        if full or dnf_full:
            figs = []
            if full:
                figs = [
                    tradeoff(name, full),
                    *ladder(name, full),
                    latency_lines(name, full),
                    build_bars(name, full),
                    memory_lines(name, full),
                ]
                fb = filter_lines(name, full)
                figs += [fb] if fb else []
            m, p = section(name, full, figs, dnf_full)
            md += m
            parts += p
        if subs or dnf_subs:
            m, p = section(
                f"{name}-subsets",
                subs,
                [scaling(name, full, subs)] if subs else [],
                dnf_subs,
            )
            md += m
            parts += p
    body, first = [], True
    for i, p in enumerate(parts):
        if isinstance(p, go.Figure):
            body.append(
                p.to_html(
                    full_html=False,
                    include_plotlyjs=first,
                    div_id=f"fig{i}",
                    config={"displaylogo": False, "responsive": True},
                )
            )
            first = False
        else:
            body.append(p)
    dark = json.dumps(
        {light: dark for light, dark, _, _ in STYLE.values()}
        | {"#fcfcfb": "#1a1a19", "#52514e": "#c3c2b7"}
    )
    page = (
        PAGE.replace("__ENV__", html.escape(env_line))
        .replace("__BODY__", "\n".join(body))
        .replace("__DARK__", dark)
    )
    (RESULTS / "report.html").write_text(page)
    (RESULTS / "summary.md").write_text("\n".join(md) + "\n")
    print(f"wrote {RESULTS / 'report.html'} and {RESULTS / 'summary.md'}")


if __name__ == "__main__":
    main()
