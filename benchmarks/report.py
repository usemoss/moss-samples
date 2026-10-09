"""Turn results/<dataset>/*.json into results/report.html (interactive Plotly charts + tables) and results/summary.md.

usage: $PWD/.venv/bin/python report.py        then open results/report.html in a browser (works offline; plotly.js is inlined)

The page has a Charts tab and a Tables tab, and a dataset picker. Per dataset, using each run key's newest result:
  sections  <dataset> (library-default metric), <dataset> · inner product (--metric ip runs, plus the default run of
            each engine whose default metric is already inner product) and <dataset>-subsets (--docs runs)
  charts    recall (vector) or nDCG@10 (text) vs latency (Pareto frontier per engine, the library-default setting
            ringed; dropdowns: latency statistic, k), latency at the operating point (bars; dropdown: statistic),
            build cost (bars; dropdown: build time / docs per s), memory (bars; dropdown: index, build and search
            peaks, RSS increase, disk), filtered search (line per engine across the filter cases; dropdown: warm
            recall, warm / cold latency, cold first-query latency); the -subsets section has a scaling chart instead
  tables    operating point, full serial sweep, filter cases (cold and warm), memory, engines that did not finish
            (DNF). Click a header to sort; the box filters rows by every word typed; the best value per column among
            the shown rows is bold.
Dropdowns list the mean first, then p50, p95, p99, p99.9. The operating point is the library-default search setting.
Axes: linear from 0, with one fixed range for every dropdown view of the same unit (switching mean / p50 ... p99.9
never moves the axis); the recall axis of the trade-off chart keeps one range across k.
Refuses to write anything (exit 1, "STALE <log>: <last line>") when an engine's newest attempt failed but an older
result for the same run would be shown.
Every chart: hover shows exact values and parameters; click a legend entry to hide an engine, double-click to isolate it.
Labels: recall@k is measured against the exact top-k; nDCG@10 and R-precision against human relevance labels.
Text datasets add R-precision and recall@k (human labels) columns and example results (top 5 of 10 queries per
engine, ✓ = labelled relevant).
"""

import html
import json
import re
from pathlib import Path

import plotly.graph_objects as go

RESULTS = Path(__file__).parent / "results"
# Fixed engine -> (light hue, dark hue, marker, dash); validated categorical palette (8 hues, light and dark steps).
# Color follows the engine, never its rank. Two setups of one library share a hue and differ by dash and marker.
STYLE = {
    "moss": ("#2a78d6", "#3987e5", "circle", "solid"),
    "chroma": ("#eb6834", "#d95926", "square", "solid"),
    "lancedb": ("#1baf7a", "#199e70", "triangle-up", "solid"),
    "lancedb-hnsw": ("#1baf7a", "#199e70", "pentagon", "dash"),
    "qdrant-local": ("#eda100", "#c98500", "diamond", "solid"),
    "faiss-flat": ("#e87ba4", "#d55181", "cross", "dash"),
    "faiss-hnsw": ("#e87ba4", "#d55181", "x", "solid"),
    "zvec": ("#008300", "#008300", "triangle-down", "solid"),
    "sqlite-vec": ("#4a3aa7", "#9085e9", "triangle-left", "solid"),
    "duckdb-vss": ("#e34948", "#e66767", "triangle-right", "solid"),
}
LATENCY = {"mean": "mean", "p50": "p50", "p95": "p95", "p99": "p99", "p99.9": "p999"}
MEMORY = ["index", "build peak", "search peak", "RSS increase over build", "on disk"]
STAGES = ["build", "serial", "filter"]
IP = {"ip", "dot"}  # metrics that are inner product (moss, zvec: ip; qdrant: dot)


def run_key(r: dict) -> str:
    """engine[-ip][-docsN], the name run_suite.sh gives a run's log and result."""
    a = r["args"]
    return (
        r["engine"]
        + ("-ip" if a.get("metric") == "ip" else "")
        + (f"-docs{a['docs']}" if a.get("docs") else "")
    )


def newest_runs() -> dict[str, dict[str, dict]]:
    """{dataset: {run key: newest result}}; file names end in a sortable timestamp."""
    runs: dict[str, dict[str, dict]] = {}
    for p in sorted(RESULTS.glob("*/*.json")):
        r = json.loads(p.read_text())
        runs.setdefault(p.parent.name, {})[run_key(r)] = r | {
            "file": str(p.relative_to(RESULTS))
        }
    return runs


def attempts() -> list[tuple[str, str, bool, str, str]]:
    """Newest attempt per run: (dataset, run key, succeeded, last log line, log name). run_suite.sh names each log
    results/logs/<dataset>-<engine>[-ip][-docs<N>]-<stamp>.log and its result
    results/<dataset>/<engine>[-ip][-docs<N>]-<stamp>.json with the same stamp. run.py prints `wrote <path>` last, so
    a log without a `wrote ` line was killed, crashed or is still running. Other logs (fetch-, prepare-, ...) are
    skipped: their names do not match."""
    engines = "|".join(map(re.escape, sorted(STYLE, key=len, reverse=True)))
    name = re.compile(rf"(.+)-((?:{engines})(?:-ip)?(?:-docs\d+)?)-(\d{{8}}T\d{{6}})")
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
    max of the serial / filter peaks that ran), RSS increase over the build, index size on disk."""
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


def single(r: dict) -> bool:
    """True for a one-point (exact) engine: its only sweep setting has no parameters."""
    return {json.dumps(row["params"]) for row in r["serial"]} == {"{}"}


def setting(params: dict, one: bool) -> str:
    """Display name of a sweep setting: exact (one-point engine), default (library default) or its parameters."""
    return "exact" if one else json.dumps(params) if params else "default"


def frontier(
    points: list[tuple[float, float, str, float]],
) -> list[tuple[float, float, str, float]]:
    """Pareto frontier (ann-benchmarks create_pointset), lower y is better: keep points no other point beats on
    both axes."""
    out, best = [], None
    for p in sorted(points, key=lambda p: -p[0]):
        if best is None or p[1] < best:
            out.append(p)
            best = p[1]
    return sorted(out)


def trace_style(engine: str) -> dict:
    """Plotly line/marker style for an engine (run keys reuse their engine's style)."""
    color, _, symbol, dash = STYLE.get(
        re.sub(r"(-ip)?(-docs\d+)?$", "", engine),
        ("#52514e", "#c3c2b7", "circle", "solid"),
    )
    return {
        "line": {"color": color, "width": 2, "dash": dash},
        "marker": {"color": color, "symbol": symbol, "size": 9},
    }


def yaxes(views: dict[str, list[float | None]]) -> dict[str, dict]:
    """Relayout keys for the y axis of each dropdown view (title -> values): linear from 0, and views with the same
    unit (the title's text after its last comma) share one fixed range, so switching mean / p50 ... p99.9 never
    moves the axis."""
    unit = {v: v.rsplit(", ", 1)[-1] for v in views}
    top: dict[str, float] = {}
    for v, xs in views.items():
        top[unit[v]] = max([top.get(unit[v], 0), *(x for x in xs if x is not None)])
    return {
        v: {
            "yaxis.title.text": v,
            "yaxis.range": [0, 1.05 * top[unit[v]] or 1],
        }
        for v in views
    }


def layout(fig: go.Figure, title: str, x: str, y: dict) -> go.Figure:
    """Shared layout: recessive grid, legend on the right (click to hide, double-click to isolate); `y` = one entry of yaxes()."""
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
    """Recall (vector) or nDCG@10 (text) vs latency, one Pareto line per (engine, k); an exact engine is a dotted line
    ending at its point, and a swept engine's library-default setting is ringed (it may sit off the frontier).
    Dropdowns pick the latency statistic and k."""
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
    label = metric_of(next(iter(runs.values()))).split(" ")[0]  # recall@k or nDCG@10
    fig, data = go.Figure(), {s: [] for s in LATENCY}

    def pts(
        rows: list[dict], s: str, one: bool
    ) -> list[tuple[float, float, str, float]]:
        """(headline, latency statistic s, setting, headline) per row."""
        return [
            (
                row["headline"],
                row["latency_ms"][LATENCY[s]],
                setting(row["params"], one),
                row["headline"],
            )
            for row in rows
        ]

    def add(trace: go.Scatter) -> None:
        """Add a trace drawn from the newest data[...] entry of the opening (mean) view."""
        p = data["mean"][-1]
        trace.update(
            x=[q[0] for q in p],
            y=[q[1] for q in p],
            customdata=[[q[2], q[3]] for q in p],
        )
        fig.add_trace(trace)

    for eng, r in runs.items():
        one = single(r)
        for k in ks:
            rows = [row for row in r["serial"] if row["k"] == k]
            if not rows:
                continue
            line = one and lo[k] < rows[0]["headline"]  # exact: one point per k
            for s in LATENCY:
                p = frontier(pts(rows, s, one))
                data[s].append([(lo[k], *p[0][1:]), p[0]] if line else p)
            style = trace_style(eng)
            if line:
                style["line"]["dash"], style["marker"]["size"] = "dot", [0, 9]
            common = {
                "legendgroup": eng,
                "visible": k == ks[-1],
                "meta": k,
                "hovertemplate": f"<b>{eng}</b> k={k}<br>%{{customdata[0]}}<br>{label} %{{customdata[1]:.4f}}"
                "<br>%{y:.3f} ms<extra></extra>",
            }
            add(
                go.Scatter(
                    name=f"{eng} (exact)" if line else eng,
                    showlegend=k == ks[-1],
                    mode="lines+markers",
                    **common,
                    **style,
                )
            )
            if one:
                continue
            for s in LATENCY:  # the ring: library-default setting
                data[s].append(pts([row for row in rows if not row["params"]], s, one))
            add(
                go.Scatter(
                    name=f"{eng} default",
                    showlegend=False,
                    mode="markers",
                    marker={
                        "color": style["marker"]["color"],
                        "symbol": "circle-open",
                        "size": 18,
                        "line": {"width": 2},
                    },
                    **common,
                )
            )
    ytitle = dict(
        zip(
            LATENCY,
            yaxes(
                {
                    f"{s} latency, ms (lower is better)": [
                        p[1] for t in data[s] for p in t
                    ]
                    for s in LATENCY
                },
            ).values(),
        )
    )
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
        for s in LATENCY
    ]
    k_buttons = [
        {
            "label": f"k = {k}",
            "method": "restyle",
            "args": [
                {
                    "visible": [tr.meta == k for tr in fig.data],
                    "showlegend": [
                        tr.meta == k and not tr.name.endswith(" default")
                        for tr in fig.data
                    ],
                }
            ],
        }
        for k in reversed(ks)
    ]
    fig.update_layout(updatemenus=[menu(speed_buttons, 0), menu(k_buttons, 0.3)])
    r0 = next(iter(runs.values()))
    xs = [p[0] for t in data["mean"] for p in t]
    pad = max(0.01, (max(xs) - min(xs)) * 0.03)
    fig = layout(
        fig,
        f"{name}: {metric_of(r0)} vs latency (Pareto frontier per engine; ring = library default)",
        metric_of(r0),
        ytitle["mean"],
    )
    return fig.update_xaxes(
        range=[min(xs) - pad, max(xs) + pad]
    )  # one range for every k


def bars(
    name: str,
    title: str,
    views: dict[str, list[float]],
    engines: list[str],
    unit: str,
) -> go.Figure:
    """One bar per engine in its color, on a linear axis from 0 (a bar's length is its value); the dropdown picks
    the view (the first one opens)."""
    first = next(iter(views))

    def hover(v: str) -> str:
        """Hover text for one view."""
        return f"<b>%{{x}}</b><br>{v}: %{{y:.3f}} {unit}<extra></extra>"

    fig = go.Figure(
        go.Bar(
            x=engines,
            y=views[first],
            marker={
                "color": [trace_style(e)["line"]["color"] for e in engines],
                "line": {"color": "#fcfcfb", "width": 2},
            },
            hovertemplate=hover(first),
        )
    )
    ax = yaxes({f"{v}, {unit}" if unit else v: vals for v, vals in views.items()})
    ax = dict(zip(views, ax.values()))
    fig.update_layout(
        updatemenus=[
            menu(
                [
                    {
                        "label": v,
                        "method": "update",
                        "args": [{"y": [vals], "hovertemplate": hover(v)}, ax[v]],
                    }
                    for v, vals in views.items()
                ],
                0,
            )
        ]
    )
    fig = layout(fig, f"{name}: {title}", "engine", ax[first])
    fig.update_layout(showlegend=False)
    return fig


def latency_bars(name: str, runs: dict[str, dict]) -> go.Figure:
    """Serial latency at the operating point (largest k) per engine; dropdown: mean, p50 ... p99.9."""
    lat = {e: max(at_op(r), key=lambda row: row["k"]) for e, r in runs.items()}
    k = max(row["k"] for row in lat.values())
    return bars(
        name,
        f"serial latency at the operating point (library default, k = {k})",
        {
            f"{s} latency": [lat[e]["latency_ms"][key] for e in runs]
            for s, key in LATENCY.items()
        },
        list(runs),
        "ms",
    )


def build_bars(name: str, runs: dict[str, dict]) -> go.Figure:
    """Index build cost per engine; dropdown: build seconds, docs per second."""
    return bars(
        name,
        "index build",
        {
            "build time, s": [r["load"]["build_s"] for r in runs.values()],
            "docs per second": [r["load"]["docs_per_s"] for r in runs.values()],
        },
        list(runs),
        "",
    )


def memory_bars(name: str, runs: dict[str, dict]) -> go.Figure:
    """Memory per engine in GB (see mem_gb); dropdown: index, build peak, search peak, RSS increase, on disk."""
    mem = {e: mem_gb(r) for e, r in runs.items()}
    return bars(
        name,
        "memory (footprint over the post-load baseline; on disk = index files)",
        {m: [mem[e][m] for e in runs] for m in MEMORY},
        list(runs),
        "GB",
    )


def kept(tag: str) -> float:
    """Percent of docs a VectorDBBench filter case keeps: int_<p>p drops the first p% of ids, label_<p>p keeps p%."""
    p = float(tag.split("_")[1].rstrip("p"))
    return 100 - p if tag.startswith("int") else p


def filter_lines(name: str, runs: dict[str, dict]) -> go.Figure | None:
    """Filtered search: one line per engine across the filter cases, ordered from most to fewest docs kept; dropdown:
    warm recall@100, warm then cold latency (mean, p50 ... p99.9), cold first-query latency. A case an engine did not
    run (different --filters) is left as a gap."""
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
    ax = yaxes({v: [x for y in ys[v] for x in y] for v in views})
    fig.update_layout(
        updatemenus=[
            menu(
                [
                    {"label": v, "method": "update", "args": [{"y": ys[v]}, ax[v]]}
                    for v in views
                ],
                0,
            )
        ]
    )
    return layout(
        fig,
        f"{name}: filtered search at the operating point (VectorDBBench int / label cases)",
        "filter case (share of docs kept)",
        ax["warm recall@100"],
    )


def scaling(name: str, full: dict[str, dict], subs: dict[str, dict]) -> go.Figure:
    """Metric against corpus size per run key (engine and metric mode): its --docs runs plus its full-corpus run in
    `full` (if any), each at its operating point and largest k; the dropdown picks the metric (axes as in yaxes();
    docs on a linear axis from 0). Hover shows docs, queries used and the setting."""
    r0 = next(iter(subs.values()))
    views = {metric_of(r0): lambda r, row: row["headline"]}
    views |= {
        f"{s} latency, ms": lambda r, row, key=key: row["latency_ms"][key]
        for s, key in LATENCY.items()
    }
    views |= {
        "index memory, GB": lambda r, row: mem_gb(r)["index"],
        "build peak memory, GB": lambda r, row: mem_gb(r)["build peak"],
        "build time, s": lambda r, row: r["load"]["build_s"],
    }
    bases = {k.split("-docs")[0] for k in subs}
    by: dict[str, list[tuple[dict, dict]]] = {}
    for key, r in [*subs.items(), *((k, r) for k, r in full.items() if k in bases)]:
        by.setdefault(key.split("-docs")[0], []).append(
            (r, max(at_op(r), key=lambda row: row["k"]))
        )
    first = next(iter(views))
    fig = go.Figure()
    for eng, pts in by.items():
        pts.sort(key=lambda p: p[0]["load"]["docs"])
        fig.add_trace(
            go.Scatter(
                x=[r["load"]["docs"] for r, _ in pts],
                y=[views[first](r, row) for r, row in pts],
                customdata=[
                    [
                        r["args"].get("queries") or r["dataset"]["n_queries"],
                        setting(row["params"], single(r)),
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
        for v, f in views.items()
    }
    ax = yaxes({v: [y for t in ys[v] for y in t] for v in views})
    fig.update_layout(
        updatemenus=[
            menu(
                [
                    {"label": v, "method": "update", "args": [{"y": ys[v]}, ax[v]]}
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
        ax[first],
    )
    return fig.update_xaxes(range=[0, 1.05 * max(x for t in fig.data for x in t.x)])


def better(col: str) -> str:
    """Which way a table column improves: "hi" (recall, nDCG, R-precision), "lo" (ms, s, GB), "" (labels and the
    shared post-load baseline)."""
    if re.search(r"recall|nDCG|R-precision", col):
        return "hi"
    if re.search(r"\b(ms|s|GB)$", col) and "baseline" not in col:
        return "lo"
    return ""


def table(head: list[str], rows: list[list[str]]) -> tuple[list[str], str]:
    """(markdown lines, html) for one table; the html is sortable and filterable (see PAGE's script)."""
    md = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + [
        "| " + " | ".join(r) + " |" for r in rows
    ]
    th = "".join(
        f"<th data-better='{better(h)}' title='click to sort'>{html.escape(h)}</th>"
        for h in head
    )
    tb = "".join(
        "<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>"
        for r in rows
    )
    return (
        md,
        "<input class='flt' type='search' placeholder='filter rows: every word must match a cell (numbers exactly)'>"
        f"<div class='tw'><table class='sortable'><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></div>",
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
) -> tuple[list[str], list, list[str]]:
    """Markdown lines, chart-tab parts (HTML fragments and figures) and table-tab HTML fragments for one section."""
    head = f"<h2>{html.escape(title)}</h2>"
    if not runs:  # only failed attempts: heading and the DNF table, no charts
        md = [f"## {title}", "", "No run finished.", "", "### Did not finish", ""]
        m, h = table(["engine and reason"], [[x] for x in missing])
        return (
            md + m + [""],
            [f"{head}<p>No run finished; see the Tables tab.</p>"],
            [f"{head}<p>No run finished.</p><h3>Did not finish</h3>{h}"],
        )
    r0 = next(iter(runs.values()))
    text = r0["dataset"]["kind"] == "text"
    n = sorted({row["latency_ms"]["n"] for r in runs.values() for row in r["serial"]})
    queries = (
        f"{n[0]:,}" if len(n) == 1 else f"{n[0]:,} to {n[-1]:,} (differs by engine)"
    )
    intro = (
        "Runs on the first N docs (--docs, ground truth recomputed); the scaling chart adds the full run when it exists."
        if title.endswith("-subsets")
        else f"{r0['dataset']['n_base']:,} docs, {queries} queries. Every engine runs with its library's default "
        "index and search settings; the operating point is the default search setting."
    )
    if missing:
        intro += f" Did not finish: {', '.join(m.split(':')[0] for m in missing)}."
    md = [f"## {title}", "", intro, ""]
    charts = [f"{head}<p>{html.escape(intro)}</p>", *figs]
    tables = [f"{head}<p>{html.escape(intro)}</p>"]

    def add(name: str, cols: list[str], rows: list[list[str]]) -> None:
        """Append one table to the markdown and the Tables tab."""
        m, h = table(cols, rows)
        md.extend(["", f"### {name}", "", *m])
        tables.append(f"<h3>{html.escape(name)}</h3>{h}")

    def quality(row: dict) -> list[str]:
        """Headline, then (text) R-precision and recall@k against the human labels."""
        q = row.get(f"recall@{row['k']}")
        return [
            f"{row['headline']:.4f}",
            *(
                [f"{row['r_precision']:.4f}", f"{q:.4f}" if q is not None else "-"]
                if text
                else []
            ),
        ]

    qcols = [
        metric_of(r0),
        *(["R-precision", "recall@k (human labels)"] if text else []),
    ]
    lat_cols = [f"{s} ms" for s in LATENCY]
    op = []
    for e, r in runs.items():
        g = mem_gb(r)
        for row in at_op(r):
            op.append(
                [
                    e,
                    r.get("metric", "-"),
                    setting(row["params"], single(r)),
                    str(row["k"]),
                    *quality(row),
                    *(f"{row['latency_ms'][key]:.3f}" for key in LATENCY.values()),
                    f"{r['load']['build_s']:.1f}",
                    f"{g['index']:.2f}",
                    f"{g['build peak']:.2f}",
                    f"{g['on disk']:.2f}",
                ]
            )
    add(
        "Operating point (library default)",
        [
            "engine",
            "metric",
            "setting",
            "k",
            *qcols,
            *lat_cols,
            "build s",
            "index GB",
            "build peak GB",
            "disk GB",
        ],
        op,
    )
    add(
        "Full serial sweep",
        ["engine", "setting", "k", *qcols, *lat_cols],
        [
            [
                e,
                setting(row["params"], single(r)),
                str(row["k"]),
                *quality(row),
                *(f"{row['latency_ms'][key]:.3f}" for key in LATENCY.values()),
            ]
            for e, r in runs.items()
            for row in r["serial"]
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
                for p in ("warm", "cold")
                for x in ("mean", "p50", "p99")
            ),
        ]
        for e, r in runs.items()
        for f in r["filter"]
    ]
    if filt:
        add(
            "Filtered search (k=100 at the operating point; cold = first use of the filter, warm = second pass)",
            [
                "engine",
                "filter",
                "recall@100 cold",
                "recall@100 warm",
                "cold first query ms",
                *(
                    f"{p} {x} ms"
                    for p in ("warm", "cold")
                    for x in ("mean", "p50", "p99")
                ),
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
        "Memory (footprint values are over the post-load baseline)",
        [
            "engine",
            "baseline footprint GB",
            "index GB",
            "build peak GB",
            "serial peak GB",
            "filter peak GB",
            "RSS increase over build GB",
            "on disk GB",
            "process peak RSS (whole run) GB",
        ],
        mem_rows,
    )
    tables.append(examples(runs))
    if missing:
        add("Did not finish", ["engine and reason"], [[m] for m in missing])
    return md + [""], charts, tables


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Moss vector benchmark</title><style>
:root{--surface:#fcfcfb;--ink:#0b0b0b;--muted:#52514e;--rule:#e4e3df;--best:#e3eefb}
@media (prefers-color-scheme:dark){:root{--surface:#1a1a19;--ink:#ffffff;--muted:#c3c2b7;--rule:#3a3a37;--best:#1f3550}}
body{background:var(--surface);color:var(--ink);font:15px/1.5 system-ui,sans-serif;margin:0 auto;max-width:1200px;
padding:16px}h2{margin-top:48px;border-top:1px solid var(--rule);padding-top:16px}p{color:var(--muted)}
nav{position:sticky;top:0;background:var(--surface);padding:8px 0;border-bottom:1px solid var(--rule);z-index:10;
display:flex;gap:8px;flex-wrap:wrap;align-items:center}
nav button,nav select,input.flt{font:inherit;color:var(--ink);background:var(--surface);border:1px solid var(--rule);
border-radius:6px;padding:4px 12px}nav button[aria-pressed=true]{border-color:var(--ink);font-weight:600}
input.flt{display:block;margin:4px 0 6px;width:min(360px,100%)}
.tw{overflow-x:auto}table{border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:13px}
th,td{border-bottom:1px solid var(--rule);padding:4px 10px;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}table.sortable th{cursor:pointer;user-select:none}
th[data-dir=asc]::after{content:" ▲"}th[data-dir=desc]::after{content:" ▼"}td.best{font-weight:700;background:var(--best)}
td.snip{white-space:normal;text-align:left;min-width:320px}summary{cursor:pointer;margin:6px 0}
</style></head><body><h1>Moss vector benchmark</h1><p>__ENV__</p>
<nav><button data-tab="charts" aria-pressed="true">Charts</button><button data-tab="tables" aria-pressed="false">Tables</button>
<label>dataset <select id="ds">__OPTIONS__</select></label></nav>
<p>Charts: hover any point or bar for exact values; click a legend entry to hide an engine, double-click to isolate it;
dropdowns above each chart switch the measure. Tables: click a header to sort; type in a table's box to filter its rows (each word must match a cell; numbers match exactly);
the best value per column among the shown rows is bold.</p>__BODY__
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
// Tabs and dataset picker: show one tab's sections for one dataset; resize the charts that just became visible.
let tab = "charts";
const show = () => {
  const ds = document.getElementById("ds").value;
  for (const s of document.querySelectorAll("section"))
    s.hidden = s.dataset.tab !== tab || s.dataset.ds !== ds;
  for (const b of document.querySelectorAll("nav button")) b.setAttribute("aria-pressed", b.dataset.tab === tab);
  for (const el of document.querySelectorAll("section:not([hidden]) .js-plotly-plot")) Plotly.Plots.resize(el);
};
for (const b of document.querySelectorAll("nav button")) b.onclick = () => { tab = b.dataset.tab; show(); };
document.getElementById("ds").onchange = show;
show();
// Tables: sort on header click, filter by words, bold the best value per column among the shown rows.
const num = td => { const v = parseFloat(td.textContent); return isNaN(v) ? null : v; };
const best = t => {
  for (const td of t.querySelectorAll("td.best")) td.classList.remove("best");
  const rows = [...t.tBodies[0].rows].filter(r => !r.hidden);
  [...t.tHead.rows[0].cells].forEach((th, i) => {
    if (!th.dataset.better) return;
    const vals = rows.map(r => num(r.cells[i])).filter(v => v !== null);
    if (!vals.length) return;
    const b = th.dataset.better === "hi" ? Math.max(...vals) : Math.min(...vals);
    rows.forEach(r => { if (num(r.cells[i]) === b) r.cells[i].classList.add("best"); });
  });
};
for (const t of document.querySelectorAll("table.sortable")) {
  [...t.tHead.rows[0].cells].forEach((th, i) => th.onclick = () => {
    const dir = th.dataset.dir === "asc" ? "desc" : "asc";
    for (const h of t.tHead.rows[0].cells) delete h.dataset.dir;
    th.dataset.dir = dir;
    const key = r => num(r.cells[i]) ?? r.cells[i].textContent;
    const rows = [...t.tBodies[0].rows].sort((a, b) => {
      const x = key(a), y = key(b);
      const c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
      return dir === "asc" ? c : -c;
    });
    t.tBodies[0].append(...rows);
  });
  const box = t.closest(".tw").previousElementSibling;
  box.oninput = () => {
    const words = box.value.toLowerCase().split(/\\s+/).filter(Boolean);
    // a word matches a number cell exactly ("100" is not 0.1003) and a text cell anywhere in it
    const hit = (td, w) => num(td) !== null && /^[-\\d.]+$/.test(td.textContent)
      ? td.textContent === w : td.textContent.toLowerCase().includes(w);
    for (const r of t.tBodies[0].rows) r.hidden = !words.every(w => [...r.cells].some(td => hit(td, w)));
    best(t);
  };
  best(t);
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
    envs = [r["env"] for ds in runs.values() for r in ds.values()]
    env, versions = envs[0], {}
    for e in (
        envs
    ):  # every version used across runs (run_suite.sh upgrades moss between runs)
        for pkg, v in e["versions"].items():
            versions.setdefault(pkg, set()).add(v)
    env_line = (
        f"Hardware: {env['cpu']}, {env['cores']} cores, {env['ram_gb']} GB, {env['os']}. "
        "Versions: "
        + ", ".join(p + " " + " / ".join(sorted(v)) for p, v in versions.items())
        + "."
    )
    md = [
        "# Benchmark results",
        "",
        env_line,
        "",
        "Interactive charts: report.html",
        "",
    ]
    body: list[tuple[str, str, object]] = []  # (dataset, tab, HTML fragment or figure)
    names = sorted(set(runs) | {ds for ds, _, ok, _, _ in att if not ok})
    for name in names:
        have = runs.get(name, {})
        dnfs = [(key, last) for ds, key, ok, last, _ in att if ds == name and not ok]
        full = {k: r for k, r in have.items() if not re.search(r"-ip|-docs", k)}
        ip = {k[:-3]: r for k, r in have.items() if k.endswith("-ip")}
        if ip:  # engines without an ip mode: their default run already ranks by inner product
            ip |= {
                k: r for k, r in full.items() if r.get("metric") in IP and k not in ip
            }
        groups = [
            (name, full, lambda k: not re.search(r"-ip|-docs", k)),
            (f"{name} · inner product", ip, lambda k: k.endswith("-ip")),
            (
                f"{name}-subsets",
                {k: r for k, r in have.items() if "-docs" in k},
                lambda k: "-docs" in k,
            ),
        ]
        for title, rs, mine in groups:
            missing = [f"{k}: DNF, {last}" for k, last in dnfs if mine(k)]
            if not rs and not missing:
                continue
            figs = []
            if rs and title.endswith("-subsets"):
                figs = [
                    scaling(
                        name, {k: r for k, r in have.items() if "-docs" not in k}, rs
                    )
                ]
            elif rs:
                figs = [
                    tradeoff(title, rs),
                    latency_bars(title, rs),
                    build_bars(title, rs),
                    memory_bars(title, rs),
                ]
                figs += [fb] if (fb := filter_lines(title, rs)) else []
            m, charts, tables = section(title, rs, figs, missing)
            md += m
            body += [(name, "charts", p) for p in charts]
            body += [(name, "tables", p) for p in tables]
    parts, first, i = [], True, 0
    for ds in names:
        for tab in ("charts", "tables"):
            parts.append(f"<section data-tab='{tab}' data-ds='{html.escape(ds)}'>")
            for p in (p for d, t, p in body if (d, t) == (ds, tab)):
                if isinstance(p, go.Figure):
                    parts.append(
                        p.to_html(
                            full_html=False,
                            include_plotlyjs=first,
                            div_id=f"fig{i}",
                            config={"displaylogo": False, "responsive": True},
                        )
                    )
                    first, i = False, i + 1
                else:
                    parts.append(p)
            parts.append("</section>")
    dark = json.dumps(
        {light: dark for light, dark, _, _ in STYLE.values()}
        | {"#fcfcfb": "#1a1a19", "#52514e": "#c3c2b7"}
    )
    page = (
        PAGE.replace("__ENV__", html.escape(env_line))
        .replace(
            "__OPTIONS__", "".join(f"<option>{html.escape(n)}</option>" for n in names)
        )
        .replace("__BODY__", "\n".join(parts))
        .replace("__DARK__", dark)
    )
    (RESULTS / "report.html").write_text(page)
    (RESULTS / "summary.md").write_text("\n".join(md) + "\n")
    print(f"wrote {RESULTS / 'report.html'} and {RESULTS / 'summary.md'}")


if __name__ == "__main__":
    main()
