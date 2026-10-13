"""Turn results/<dataset>/*.json into results/report.html and results/summary.md.

report.html holds interactive Plotly charts and tables; summary.md holds the tables as markdown.

usage: $PWD/.venv/bin/python report.py
       then open results/report.html in a browser (works offline; plotly.js is inlined)

The page has a Charts tab and a Tables tab, a dataset picker and a metric switch: "inner product†"
(every engine in its inner-product mode, the datasets' cosine on unit vectors; --metric ip runs plus
the default run of engines already on inner product) or "library default" (each engine's default
metric). NOTES at the top explain the metric, the quality measures and how latency is measured.
Per dataset and metric, using each run key's newest result:
  sections  <dataset> · metric: <view> (full corpus) and <dataset> · corpus-size subsets (--docs)
  charts    numbered cards "Chart N · <dataset> · <measure>" with a subtitle (metric and the chart's
            specifics) and a description, all HTML so nothing is cut off. Vector datasets: latency
            at equal recall (fastest setting reaching recall@k >= target), recall vs latency (every
            sweep setting as a marker, Pareto line per engine as in ann-benchmarks, default ringed),
            latency at default settings (one k for every engine), index build time, memory,
            filtered search (with an unfiltered reference point). Text datasets: nDCG@10 vs latency
            and latency at k = 10, the depth nDCG@10 scores; build bars stack the corpus-embedding
            time (measured at prepare) on the non-Moss engines. Subsets: a scaling chart.
  tables    default settings (every k), equal recall (vector datasets), full serial sweep, filter
            cases (cold and warm, with the unfiltered reference), memory, example results (text),
            engines that did not finish (DNF). Click a header to sort; per-column value filters
            (CSS, no JS: tick values to show only them, nothing ticked = all, "clear filters"
            resets); the best value per column among the shown rows is bold.
Latency statistics: mean, p50, p95, p99 (p99.9 is left out: with at most 1,000 queries it is one of
the two slowest samples). Every measure axis says whether higher or lower is better. Axes: linear
from 0, except a recall vs latency latency axis whose values span more than LOG_SPAN x (log, titled
"(log scale)"); one fixed range for every dropdown view of the same unit; the quality axis of the
recall vs latency chart keeps one range across k.
Refuses to write anything (exit 1, "STALE <log>: <last line>") when an engine's newest attempt
failed but an older result for the same run would be shown.
Every chart: hover shows exact values and parameters; click a legend entry to hide an engine,
double-click to isolate it.
"""

import html
import itertools
import json
import math
import re
from pathlib import Path

import plotly.graph_objects as go

RESULTS = Path(__file__).parent / "results"
# Fixed engine -> (light hue, dark hue, marker, dash); validated categorical palette (8 hues, light
# and dark steps).
# Color follows the engine, never its rank. Two setups of one library share a hue and differ by
# dash and marker.
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
# p99.9 is left out: with at most 1,000 queries per pass it is one of the two slowest samples
LATENCY = {"mean": "mean", "p50": "p50", "p95": "p95", "p99": "p99"}
LOG_SPAN = 20  # a latency axis whose values span more than this factor is drawn on a log scale
MEMORY = ["index", "build peak", "search peak", "RSS increase over build", "on disk"]
STAGES = ["build", "serial", "filter"]
IP = {"ip", "dot"}  # metrics that are inner product (moss, zvec: ip; qdrant: dot)
METRIC_VIEWS = {"ip": "inner product†", "default": "library default"}  # page metric switch
# Chart key -> (measure, the title after the dataset; description shown under the subtitle).
CHARTS = {
    "equal": (
        "Latency at equal recall",
        "For each recall target, the mean latency of the fastest setting in the engine's sweep that "
        "reaches it: approximate engines are tuned up to the target, exact engines have one setting. "
        "Public benchmarks compare speed this way (Qdrant, VIBE, big-ann). recall@k ≥ 0.95 means the "
        "engine returned, on average over the queries, at least 95% of the true k nearest documents "
        "(found by exact search). The bar label names the setting used; an engine without a bar never "
        "reached the target. Dropdown: recall@k target.",
    ),
    "tradeoff": (
        "Recall vs latency",
        "One marker per search setting each engine was run with (its sweep, e.g. HNSW ef from 16 to "
        "1024). The line joins the settings that no other setting of the same engine beats on both "
        "recall and latency (Pareto frontier, as in ann-benchmarks); the ring marks the library-default "
        "setting. Exact engines have a single setting. Settings with ef below k are not run at that k, "
        "so the marker count varies with k. Dropdowns: latency statistic, k.",
    ),
    "tradeoff-text": (
        "nDCG@10 vs latency",
        "One marker per search setting each engine was run with, at k = 10, the depth nDCG@10 scores. "
        "The line joins the settings that no other setting of the same engine beats on both nDCG@10 "
        "and latency (Pareto frontier); the ring marks the library-default setting. Latency is end to "
        "end: it includes embedding the query. Dropdown: latency statistic.",
    ),
    "latency": (
        "Latency at default settings",
        "One bar per engine: its search latency with the library's default index and search "
        "settings, one query at a time over all queries, at the same k for every engine. Dropdown: "
        "latency statistic.",
    ),
    "build": (
        "Index build time",
        "Time to build each engine's index (ingest + index; client setup and Moss session setup "
        "excluded), or the docs indexed per second. Dropdown: measure.",
    ),
    "build-text": (
        "Index build time",
        "Moss embeds the corpus inside its build with its built-in model; the other engines index "
        "vectors embedded once at prepare (fastembed, batch 256), and that embedding time is stacked on "
        "their bars, so every bar covers embedding + indexing. Client setup and Moss session setup are "
        "excluded. Dropdown: measure.",
    ),
    "memory": (
        "Memory",
        "Memory each engine adds, in GB, as process footprint over the footprint after the dataset is "
        "loaded: index (after build), build peak, search peak, RSS increase over the build, and index "
        "files on disk (disk-backed engines keep part of their index in OS-cached files, which the "
        "footprint does not count). Dropdown: measure.",
    ),
    "filter": (
        "Filtered search",
        "Filtered search (VectorDBBench cases, from 99% of docs kept to 1%) at k = 100 with "
        "library-default settings, each case scored against its own exact ground truth. The first "
        "point, unfiltered, is the same engine's unfiltered result at k = 100 (not re-measured), so the "
        "drop from it is what the filter costs. Cold = the first pass over a filter, warm = the repeat "
        "pass. FAISS has no metadata filter: it evaluates the predicate into an id bitmap inside every "
        "query. Dropdown: recall or latency statistic.",
    ),
    "scaling": (
        "Scaling with corpus size",
        "How each engine changes with corpus size: its runs on the first 25k / 50k / 75k docs (exact "
        "ground truth over those docs) plus the full run, with library-default settings at the largest "
        "k. Dropdown: quality, latency statistic, memory or build time.",
    ),
}
FILTER_COLS = {"engine", "metric", "setting", "k", "filter", "target"}  # get value filters
TABLES = itertools.count()  # unique id per rendered table (scopes its filter CSS)


def run_key(r: dict) -> str:
    """Name a run as run_suite.sh names its log and result: engine[-ip][-docsN].

    Args:
        r: Result document, as written by run.py.

    Returns:
        The run key, e.g. "faiss-hnsw-ip" or "moss-docs25000".
    """
    a = r["args"]
    return (
        r["engine"]
        + ("-ip" if a.get("metric") == "ip" else "")
        + (f"-docs{a['docs']}" if a.get("docs") else "")
    )


def newest_runs() -> dict[str, dict[str, dict]]:
    """Load the newest result of every run key, per dataset.

    File names end in a sortable timestamp, so a later file of the same run key replaces an earlier
    one.

    Returns:
        {dataset: {run key: result}}; each result gets a "file" key with its path relative to
        results/.
    """
    runs: dict[str, dict[str, dict]] = {}
    for p in sorted(RESULTS.glob("*/*.json")):
        r = json.loads(p.read_text())
        runs.setdefault(p.parent.name, {})[run_key(r)] = r | {"file": str(p.relative_to(RESULTS))}
    return runs


def attempts() -> list[tuple[str, str, bool, str, str]]:
    """Find the newest attempt of every run from the logs, successful or not.

    run_suite.sh names each log results/logs/<dataset>-<engine>[-ip][-docs<N>]-<stamp>.log and its
    result results/<dataset>/<engine>[-ip][-docs<N>]-<stamp>.json with the same stamp. run.py prints
    `wrote <path>` last, so a log without a `wrote ` line was killed, crashed or is still running.
    Other logs (fetch-, prepare-, ...) are skipped: their names do not match.

    Returns:
        One (dataset, run key, succeeded, last log line, log file name) tuple per run; the last line
        is cut to 160 characters.
    """
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
    """List the runs whose newest attempt failed while an older result would still be shown.

    Args:
        runs: Newest results, as returned by newest_runs().
        att: Newest attempts, as returned by attempts().

    Returns:
        One `STALE <log>: <last line>` message per such run.
    """
    return [
        f"STALE {log}: {last}"
        for ds, key, ok, last, log in att
        if not ok and key in runs.get(ds, {})
    ]


def mem_gb(r: dict) -> dict[str, float]:
    """Summarize one run's memory in GB.

    Footprint measures are over the post-load baseline: index (after build), build peak and search
    peak (the max of the serial / filter peaks that ran). RSS increase is over the build; on disk is
    the size of the index directory.

    Args:
        r: Result document, as written by run.py.

    Returns:
        Value per MEMORY measure.
    """
    m, peaks = r["memory"], r["memory"]["peak_footprint_mb"]
    base = m["baseline_footprint_mb"]
    search = max(peaks[s] for s in STAGES[1:] if s in peaks)
    return {
        "index": (m["footprint_after_build_mb"] - base) / 1024,
        "build peak": (peaks["build"] - base) / 1024,
        "search peak": (search - base) / 1024,
        "RSS increase over build": (m["rss_after_build_mb"] - r["load"]["rss_before_build_mb"])
        / 1024,
        "on disk": m["disk_mb"] / 1024,
    }


def metric_of(r: dict) -> str:
    """Label the headline quality measure of a run.

    Args:
        r: Result document, as written by run.py.

    Returns:
        "nDCG@10 (human labels)" for a text dataset, "recall@k (vs exact top-k)" for a vector
        dataset.
    """
    return (
        "nDCG@10 (human labels)" if r["dataset"]["kind"] == "text" else "recall@k (vs exact top-k)"
    )


def at_op(r: dict) -> list[dict]:
    """Select the serial rows measured at the run's operating point (the library default).

    Args:
        r: Result document, as written by run.py.

    Returns:
        The operating point's serial rows, one per k.
    """
    return [row for row in r["serial"] if row["params"] == r["operating_point"]]


def single(r: dict) -> bool:
    """Tell whether a run is a one-point (exact) engine.

    Args:
        r: Result document, as written by run.py.

    Returns:
        True when every serial row has empty params (the sweep is only the library default).
    """
    return {json.dumps(row["params"]) for row in r["serial"]} == {"{}"}


def label(r: dict, params: dict) -> str:
    """Name a sweep setting of a run for display, naming Moss's text search modes.

    Args:
        r: Result document the setting belongs to.
        params: Sweep setting of one of its serial rows.

    Returns:
        setting()'s name; on text datasets, Moss's default and alpha 1.0 say what they search with.
    """
    name = setting(params, single(r))
    if r["engine"] == "moss" and r["dataset"]["kind"] == "text":
        name += " (vector only)" if params.get("alpha") == 1.0 else " (hybrid: keyword + vector)"
    return name


def setting(params: dict, one: bool) -> str:
    """Name a sweep setting for display.

    Args:
        params: Sweep setting of a serial row.
        one: True for a one-point (exact) engine, see single().

    Returns:
        "exact" for a one-point engine, "default" for the library default ({}), else the setting as
        JSON.
    """
    return "exact" if one else json.dumps(params) if params else "default"


def frontier(points: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """Keep the Pareto frontier of (quality, latency, ...) points (ann-benchmarks create_pointset).

    Points are scanned fastest first (equal latency: higher quality first); a point is kept when its
    quality is higher than every point kept before it, so at equal quality only the fastest stays.
    Unlike ann-benchmarks, zero-quality points are not skipped.

    Args:
        points: (quality, latency, setting name) tuples, as built in tradeoff().

    Returns:
        The frontier points in ascending order (quality, then latency).
    """
    out, best = [], -math.inf
    for p in sorted(points, key=lambda p: (p[1], -p[0])):
        if p[0] > best:
            out.append(p)
            best = p[0]
    return sorted(out)


def trace_style(engine: str) -> dict:
    """Return the Plotly line and marker style of an engine.

    Run keys (engine-ip, engine-docsN) reuse their engine's style; an unknown engine gets a neutral
    gray circle.

    Args:
        engine: Engine name or run key.

    Returns:
        {"line": ..., "marker": ...} with the engine's light-theme color, dash and marker symbol.
    """
    color, _, symbol, dash = STYLE.get(
        re.sub(r"(-ip)?(-docs\d+)?( \(k=\d+\))?$", "", engine),
        ("#52514e", "#c3c2b7", "circle", "solid"),
    )
    return {
        "line": {"color": color, "width": 2, "dash": dash},
        "marker": {"color": color, "symbol": symbol, "size": 9},
    }


def yaxes(views: dict[str, list[float | None]], log: bool = False) -> dict[str, dict]:
    """Build the y-axis relayout of each dropdown view.

    Views with the same unit (the title's text after its last ", ") share one fixed range, so
    switching mean / p50 ... p99 never moves the axis. A linear axis runs from 0 to 5% above the
    unit's largest value. With log=True, a unit whose positive values span more than LOG_SPAN x gets
    a log axis instead: it spans those values with a 30% margin, its title ends in "(log scale)",
    and it gets 1-2-5 ticks labelled in full (Plotly's own log ticks read "5" for both 0.5 and 50).
    Narrower spans stay linear.

    Args:
        views: Axis title -> the values plotted in that view (None for a gap).
        log: Allow log axes.

    Returns:
        Axis title -> relayout keys: "yaxis.title.text", "yaxis.range" and "yaxis.type", plus
        "yaxis.tickvals" and "yaxis.ticktext" (None on a linear axis, which clears them).
    """
    unit = {v: v.rsplit(", ", 1)[-1] for v in views}
    vals: dict[str, list[float]] = {}
    for v, xs in views.items():
        vals.setdefault(unit[v], []).extend(x for x in xs if x is not None)
    out = {}
    for v in views:
        top, pos = max(vals[unit[v]], default=0), [x for x in vals[unit[v]] if x > 0]
        out[v] = {
            "yaxis.title.text": v,
            "yaxis.type": "linear",
            "yaxis.range": [0, 1.05 * top or 1],
            "yaxis.tickvals": None,
            "yaxis.ticktext": None,
        }
        if log and pos and max(pos) / min(pos) > LOG_SPAN:
            lo, hi = min(pos) / 1.3, max(pos) * 1.3
            ticks = [
                m * 10.0**e
                for e in range(math.floor(math.log10(lo)), math.ceil(math.log10(hi)))
                for m in (1, 2, 5)
                if lo <= m * 10.0**e <= hi
            ]
            out[v] = {
                "yaxis.title.text": f"{v} (log scale)",
                "yaxis.type": "log",
                "yaxis.range": [math.log10(lo), math.log10(hi)],
                "yaxis.tickvals": ticks,
                "yaxis.ticktext": [f"{t:g}" for t in ticks],
            }
    return out


def layout(fig: go.Figure, x: str, y: dict) -> go.Figure:
    """Apply the shared look: recessive grid, dropdown row on top, legend on the right.

    The chart's title, subtitle and description are HTML above the figure (see section()), where
    they wrap instead of being cut off.

    Args:
        fig: Figure to style, in place.
        x: X-axis title.
        y: Y-axis relayout of the opening view, one value of yaxes().

    Returns:
        fig.
    """
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="#fcfcfb",
        plot_bgcolor="#fcfcfb",
        height=500,
        hovermode="closest",
        legend={"title": {"text": "click / double-click"}},
        margin={"t": 60, "r": 20},
        xaxis_title=x,
        font={"family": "system-ui, sans-serif", "size": 13},
    )
    fig.update_layout({k.replace(".", "_"): v for k, v in y.items()})
    return fig


def menu(buttons: list[dict], x: float) -> dict:
    """Build a dropdown menu placed above the plot area.

    Args:
        buttons: Plotly updatemenu buttons.
        x: Left edge, as a fraction of the plot width.

    Returns:
        The updatemenu, with explicit colors readable in both themes.
    """
    return {
        "type": "dropdown",
        "buttons": buttons,
        "x": x,
        "xanchor": "left",
        "y": 1.02,
        "yanchor": "bottom",
        "showactive": True,
        # explicit ink and fill: readable in both themes (the dark-mode relayout changes the global
        # font color)
        "font": {"color": "#0b0b0b"},
        "bgcolor": "#ffffff",
        "bordercolor": "#52514e",
    }


def tradeoff(runs: dict[str, dict], text: bool) -> tuple[go.Figure, str]:
    """Plot quality vs latency: every sweep setting as a marker, plus each engine's Pareto line.

    Quality is recall@k (vector) or nDCG@10 (text). Each (engine, k) gets three traces: a marker per
    setting (the count never changes with the latency statistic), a line through the Pareto
    frontier of those settings (see frontier(); it depends on the statistic), and a ring on the
    library-default setting (swept engines only). Dropdowns pick the latency statistic and, on
    vector datasets, k (text datasets use k = 10, the depth nDCG@10 scores). The quality axis keeps
    one range across k; the latency axis follows yaxes(log=True).

    Args:
        runs: Run key -> result document.
        text: True for a text dataset.

    Returns:
        The figure and its subtitle.
    """
    ks = [10] if text else sorted({row["k"] for r in runs.values() for row in r["serial"]})
    q = "nDCG@10" if text else "recall@k"
    fig, data = go.Figure(), {s: [] for s in LATENCY}

    def pts(r: dict, rows: list[dict], s: str) -> list[tuple[float, float, str]]:
        """Turn serial rows into (quality, latency, setting name) points for one statistic.

        Args:
            r: Result document the rows belong to.
            rows: Serial rows of one engine at one k.
            s: Latency statistic, a key of LATENCY.

        Returns:
            One point per row.
        """
        return [
            (row["headline"], row["latency_ms"][LATENCY[s]], label(r, row["params"]))
            for row in rows
        ]

    def add(trace: go.Scatter) -> None:
        """Add a trace drawn from the newest data["mean"] entry (the opening view).

        Args:
            trace: Scatter trace without x, y and customdata.
        """
        p = data["mean"][-1]
        trace.update(x=[a[0] for a in p], y=[a[1] for a in p], customdata=[a[2] for a in p])
        fig.add_trace(trace)

    for eng, r in runs.items():
        for k in ks:
            rows = [row for row in r["serial"] if row["k"] == k]
            if not rows:
                continue
            style = trace_style(eng)
            common = {"legendgroup": eng, "visible": k == ks[-1], "meta": k}
            hover = (
                f"<b>{eng}</b> k={k}<br>%{{customdata}}<br>{q} %{{x:.4f}}<br>%{{y:.3f}} ms"
                "<extra></extra>"
            )
            for s in LATENCY:
                data[s].append(pts(r, rows, s))
            add(
                go.Scatter(
                    name=eng,
                    showlegend=k == ks[-1],
                    mode="markers",
                    marker=style["marker"],
                    hovertemplate=hover,
                    **common,
                )
            )
            for s in LATENCY:
                data[s].append(frontier(pts(r, rows, s)))
            add(
                go.Scatter(
                    name=f"{eng} frontier",
                    showlegend=False,
                    mode="lines",
                    line=style["line"],
                    hoverinfo="skip",
                    **common,
                )
            )
            if single(r):
                continue
            for s in LATENCY:  # the ring: library-default setting
                data[s].append(pts(r, [row for row in rows if not row["params"]], s))
            add(
                go.Scatter(
                    name=f"{eng} default",
                    showlegend=False,
                    mode="markers",
                    hovertemplate=hover,
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
                    f"{s} latency, ms (lower is better)": [p[1] for t in data[s] for p in t]
                    for s in LATENCY
                },
                log=True,
            ).values(),
        )
    )
    menus = [
        menu(
            [
                {
                    "label": s,
                    "method": "update",
                    "args": [
                        {
                            "x": [[p[0] for p in t] for t in data[s]],
                            "y": [[p[1] for p in t] for t in data[s]],
                            "customdata": [[p[2] for p in t] for t in data[s]],
                        },
                        ytitle[s],
                    ],
                }
                for s in LATENCY
            ],
            0,
        )
    ]
    if len(ks) > 1:
        legend = [tr.mode == "markers" and not tr.name.endswith(" default") for tr in fig.data]
        menus.append(
            menu(
                [
                    {
                        "label": f"k = {k}",
                        "method": "restyle",
                        "args": [
                            {
                                "visible": [tr.meta == k for tr in fig.data],
                                "showlegend": [
                                    tr.meta == k and lg for tr, lg in zip(fig.data, legend)
                                ],
                            }
                        ],
                    }
                    for k in reversed(ks)
                ],
                0.3,
            )
        )
    fig.update_layout(updatemenus=menus)
    xs = [p[0] for t in data["mean"] for p in t]
    pad = max(0.01, (max(xs) - min(xs)) * 0.03)
    quality = "nDCG@10 (human labels)" if text else "recall@k (vs exact search)"
    fig = layout(fig, f"{quality} (higher is better)", ytitle["mean"])
    fig.update_xaxes(range=[min(xs) - pad, max(xs) + pad])  # one range for every k
    return fig, (
        "every search setting · line = Pareto frontier · ring = library default · "
        + ("k = 10" if text else "k from the dropdown")
    )


def bars(views: dict[str, list[float]], engines: list[str]) -> go.Figure:
    """Plot one bar per engine in its color on a linear axis from 0, with a view dropdown.

    A bar's length is its value, so the axis is never log; views with the same unit share one range
    (see yaxes()). The first view opens.

    Args:
        views: Axis title (measure, unit and direction) -> one value per engine.
        engines: Engine names (x axis), in the order of each view's values.

    Returns:
        The figure.
    """
    first = next(iter(views))

    def hover(v: str) -> str:
        """Build the hover template of one view: engine, then the measure without its direction.

        Args:
            v: Axis title of the view.

        Returns:
            A Plotly hovertemplate.
        """
        return f"<b>%{{x}}</b><br>{v.split(' (')[0]}: %{{y:.3f}}<extra></extra>"

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
    ax = yaxes(views)
    fig.update_layout(
        updatemenus=[
            menu(
                [
                    {
                        "label": short(v),
                        "method": "update",
                        "args": [{"y": [vals], "hovertemplate": hover(v)}, ax[v]],
                    }
                    for v, vals in views.items()
                ],
                0,
            )
        ]
    )
    fig = layout(fig, "engine", ax[first])
    fig.update_layout(showlegend=False)
    return fig


def short(view: str) -> str:
    """Dropdown label of a view: its axis title without unit and direction.

    Args:
        view: Axis title, e.g. "p95 latency, ms (lower is better)".

    Returns:
        The measure, e.g. "p95 latency".
    """
    return view.split(",")[0].split(" (")[0]


def latency_bars(runs: dict[str, dict], text: bool) -> tuple[go.Figure, str]:
    """Plot serial latency at the default settings per engine, at one k for every engine.

    The k is 10 on text datasets (the depth nDCG@10 scores), else the largest one every run
    measured at its default setting. If the runs share no such k, each bar uses its engine's
    largest k and names it in its label.

    Args:
        runs: Run key -> result document.
        text: True for a text dataset.

    Returns:
        Bar chart with a dropdown over mean, p50, p95, p99, and its subtitle.
    """
    common = set.intersection(*({row["k"] for row in at_op(r)} for r in runs.values()))
    k = (10 if 10 in common else None) if text else max(common, default=None)
    lat = {
        e: next(row for row in at_op(r) if row["k"] == k)
        if k
        else max(at_op(r), key=lambda row: row["k"])
        for e, r in runs.items()
    }
    fig = bars(
        {
            f"{s} latency, ms (lower is better)": [lat[e]["latency_ms"][key] for e in runs]
            for s, key in LATENCY.items()
        },
        list(runs) if k else [f"{e} (k={lat[e]['k']})" for e in runs],
    )
    return fig, (
        f"library-default index and search settings · k = {k} for every engine"
        if k
        else "library-default index and search settings · k differs, see the labels"
    )


TARGETS = (0.95, 0.99)  # equal-recall view: recall@k targets


def cheapest(r: dict, k: int, target: float) -> dict | None:
    """Find a run's cheapest setting that reaches a recall@k target.

    Args:
        r: Result document, as written by run.py.
        k: Recall cutoff.
        target: Minimum recall@k (the row's headline).

    Returns:
        The serial row at k with the lowest mean latency among those with headline >= target, or
        None when no setting reaches it.
    """
    ok = [row for row in r["serial"] if row["k"] == k and row["headline"] >= target]
    return min(ok, key=lambda row: row["latency_ms"]["mean"], default=None)


def equal_recall(runs: dict[str, dict]) -> tuple[go.Figure, str]:
    """Plot each engine's mean latency at the cheapest setting reaching each recall@k target.

    Any setting of the engine's sweep counts, not only the default; an exact engine has only one. An
    engine that never reaches the target has no bar and "not reached" as its label. Dropdown: k
    (largest first) and target (TARGETS); every view shares one latency range.

    Args:
        runs: Run key -> result document.

    Returns:
        The figure and its subtitle.
    """
    ks = sorted({row["k"] for r in runs.values() for row in r["serial"]})
    views = {f"recall@{k} ≥ {t}": (k, t) for k in reversed(ks) for t in TARGETS}
    rows = {v: [cheapest(r, k, t) for r in runs.values()] for v, (k, t) in views.items()}
    ys = {v: [row["latency_ms"]["mean"] if row else None for row in rows[v]] for v in views}
    text = {
        v: [
            label(r, row["params"]) if row else "not reached"
            for r, row in zip(runs.values(), rows[v])
        ]
        for v in views
    }
    ax = yaxes({f"mean latency at {v}, ms (lower is better)": ys[v] for v in views})
    ax = dict(zip(views, ax.values()))
    first = next(iter(views))
    fig = go.Figure(
        go.Bar(
            x=list(runs),
            y=ys[first],
            text=text[first],
            textposition="outside",
            cliponaxis=False,
            marker={
                "color": [trace_style(e)["line"]["color"] for e in runs],
                "line": {"color": "#fcfcfb", "width": 2},
            },
            hovertemplate="<b>%{x}</b><br>%{text}<br>mean %{y:.3f} ms<extra></extra>",
        )
    )
    fig.update_layout(
        updatemenus=[
            menu(
                [
                    {
                        "label": v,
                        "method": "update",
                        "args": [{"y": [ys[v]], "text": [text[v]]}, ax[v]],
                    }
                    for v in views
                ],
                0,
            )
        ]
    )
    fig = layout(fig, "engine (bar label: the setting used)", ax[first])
    fig.update_layout(showlegend=False)
    return fig, "fastest setting of each engine's sweep reaching the recall target (dropdown)"


def build_bars(runs: dict[str, dict]) -> tuple[go.Figure, str]:
    """Plot index build cost per engine.

    On text datasets the non-Moss engines index vectors embedded once at prepare, so their bars
    stack that corpus-embedding time (the dataset's corpus_embed_s) on the index build; Moss embeds
    inside its build, so its bar is one piece.

    Args:
        runs: Run key -> result document.

    Returns:
        Bar chart with a dropdown over build seconds and docs per second, and its subtitle.
    """
    if next(iter(runs.values()))["dataset"]["kind"] != "text":
        fig = bars(
            {
                "build time, s (lower is better)": [r["load"]["build_s"] for r in runs.values()],
                "docs indexed per second (higher is better)": [
                    r["load"]["docs_per_s"] for r in runs.values()
                ],
            },
            list(runs),
        )
        return fig, "ingest + index from vectors · client and Moss session setup excluded"
    idx = [r["load"]["build_s"] for r in runs.values()]
    emb = [embed_s(r) or 0.0 for r in runs.values()]
    docs = [r["load"]["docs"] for r in runs.values()]
    views = {
        "build time incl. corpus embedding, s (lower is better)": (idx, emb),
        "docs per second incl. corpus embedding (higher is better)": (
            [n / (a + b) for n, a, b in zip(docs, idx, emb)],
            [0.0] * len(idx),
        ),
    }
    ax = yaxes({v: [a + b for a, b in zip(*ys)] for v, ys in views.items()})
    first, names = next(iter(views)), list(runs)
    hover = "<b>%{x}</b><br>%{fullData.name}: %{y:.3f}<extra></extra>"
    fig = go.Figure(
        [
            go.Bar(
                name="index build (bar in the engine color; Moss: embedding + index with its built-in model)",
                x=names,
                y=views[first][0],
                marker={
                    "color": [trace_style(e)["line"]["color"] for e in names],
                    "line": {"color": "#fcfcfb", "width": 2},
                },
                hovertemplate=hover,
            ),
            go.Bar(
                name="corpus embedding (fastembed all-MiniLM-L6-v2 @512, measured once at prepare)",
                x=names,
                y=views[first][1],
                marker={
                    "color": "#c3c2b7",
                    "pattern": {"shape": "/"},
                    "line": {"color": "#fcfcfb", "width": 2},
                },
                hovertemplate=hover,
            ),
        ]
    )
    fig.update_layout(
        barmode="stack",
        updatemenus=[
            menu(
                [
                    {"label": short(v), "method": "update", "args": [{"y": [a, b]}, ax[v]]}
                    for v, (a, b) in views.items()
                ],
                0,
            )
        ],
    )
    fig = layout(fig, "engine", ax[first])
    fig.update_layout(legend={"orientation": "h", "y": -0.25, "title": {"text": ""}})
    return fig, "corpus embedding + ingest + index · client and Moss session setup excluded"


def embed_s(r: dict) -> float | None:
    """Corpus-embedding seconds measured at prepare, for a non-Moss run on a text dataset.

    Args:
        r: Result document, as written by run.py.

    Returns:
        The dataset's corpus_embed_s, or None for Moss (it embeds inside its build) and vector
        datasets.
    """
    if r["dataset"]["kind"] != "text" or r["engine"] == "moss":
        return None
    return r["dataset"].get("corpus_embed_s")


def memory_bars(runs: dict[str, dict]) -> tuple[go.Figure, str]:
    """Plot memory per engine in GB (see mem_gb()).

    Args:
        runs: Run key -> result document.

    Returns:
        Bar chart with a dropdown over index, build peak, search peak, RSS increase and on disk,
        and its subtitle.
    """
    mem = {e: mem_gb(r) for e, r in runs.items()}
    fig = bars(
        {f"{m}, GB (lower is better)": [mem[e][m] for e in runs] for m in MEMORY}, list(runs)
    )
    return (
        fig,
        "process footprint over the footprint after loading the dataset · on disk = index files",
    )


def kept(tag: str) -> float:
    """Percent of docs a VectorDBBench filter case keeps.

    int_<p>p drops the first p% of ids; label_<p>p keeps p%.

    Args:
        tag: Filter case tag, e.g. "int_99p" or "label_50p".

    Returns:
        The percent of docs kept.
    """
    p = float(tag.split("_")[1].rstrip("p"))
    return 100 - p if tag.startswith("int") else p


def unfiltered(r: dict) -> dict | None:
    """The serial row a filter case compares with: the default setting at k = 100.

    Args:
        r: Result document, as written by run.py.

    Returns:
        That serial row, or None when the run did not measure k = 100.
    """
    return next((row for row in at_op(r) if row["k"] == 100), None)


def filter_lines(runs: dict[str, dict]) -> tuple[go.Figure, str] | None:
    """Plot filtered search: one line per engine across the filter cases.

    Cases are ordered from most to fewest docs kept, after an "unfiltered" point: the same engine's
    serial result at k = 100 (see unfiltered()), not re-measured. Dropdown: warm recall@100, warm
    then cold latency (mean, p50, p95, p99), cold first-query latency. A case an engine did not run
    (different --filters) is left as a gap.

    Args:
        runs: Run key -> result document; runs without filter rows are skipped.

    Returns:
        The figure and its subtitle, or None when no run has filter rows.
    """
    runs = {e: r for e, r in runs.items() if r["filter"]}
    if not runs:
        return None
    tags = [
        "unfiltered",
        *sorted(
            dict.fromkeys(f["filter"] for r in runs.values() for f in r["filter"]),
            key=lambda t: -kept(t),
        ),
    ]
    xs = ["unfiltered (100% kept)"] + [f"{t} ({kept(t):g}% kept)" for t in tags[1:]]
    by = {e: {f["filter"]: f for f in r["filter"]} for e, r in runs.items()}
    views: dict[str, tuple[str, str, str | None]] = {
        "warm recall@100 (higher is better)": ("warm", "recall@100", None)
    }
    for p in ("warm", "cold"):
        views |= {
            f"{p} {lbl} latency, ms (lower is better)": (p, "latency_ms", key)
            for lbl, key in LATENCY.items()
        }
    views["cold first-query latency (one query per case), ms (lower is better)"] = (
        "cold",
        "first_ms",
        None,
    )

    def val(e: str, t: str, view: tuple[str, str, str | None]) -> float | None:
        """Look up one engine's value for a filter case and dropdown view.

        Args:
            e: Run key.
            t: Filter case tag.
            view: (pass, field, statistic): "warm" or "cold"; "recall@100", "latency_ms" or
                "first_ms"; the LATENCY key for latency_ms, else None.

        Returns:
            The value, or None if the engine did not run that case.
        """
        if t == "unfiltered":
            row = unfiltered(runs[e])
            if row is None or view[1] == "first_ms":
                return None
            return row["headline"] if view[1] == "recall@100" else row["latency_ms"][view[2]]
        if t not in by[e]:
            return None
        x = by[e][t][view[0]][view[1]]
        return x[view[2]] if view[2] else x

    first = next(iter(views))
    ys = {v: [[val(e, t, view) for t in tags] for e in runs] for v, view in views.items()}
    fig = go.Figure()
    for e, y in zip(runs, ys[first]):
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
                    {"label": short(v), "method": "update", "args": [{"y": ys[v]}, ax[v]]}
                    for v in views
                ],
                0,
            )
        ]
    )
    fig = layout(fig, "filter case (share of docs kept)", ax[first])
    return fig, "VectorDBBench int / label filter cases · library-default settings · k = 100"


def scaling(name: str, full: dict[str, dict], subs: dict[str, dict]) -> tuple[go.Figure, str]:
    """Plot each measure against corpus size, one line per engine.

    A line joins an engine's --docs runs and, if present, its full-corpus run, each at its default
    setting and largest k. The dropdown picks the measure: quality, latency statistic, index or
    build peak memory, build time (axes as in yaxes(); docs on a linear axis from 0). Hover shows
    docs, queries used and the setting.

    Args:
        name: Dataset name.
        full: Engine -> result of the full-corpus runs; only engines that also have --docs runs are
            drawn.
        subs: Run key (engine-docsN) -> result of the --docs runs.

    Returns:
        The figure and its subtitle.
    """
    views = {"recall@k (vs exact search) (higher is better)": lambda r, row: row["headline"]}
    views |= {
        f"{s} latency, ms (lower is better)": lambda r, row, key=key: row["latency_ms"][key]
        for s, key in LATENCY.items()
    }
    views |= {
        "index memory, GB (lower is better)": lambda r, row: mem_gb(r)["index"],
        "build peak memory, GB (lower is better)": lambda r, row: mem_gb(r)["build peak"],
        "build time, s (lower is better)": lambda r, row: r["load"]["build_s"],
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
                        label(r, row["params"]),
                    ]
                    for r, row in pts
                ],
                name=eng,
                mode="lines+markers",
                hovertemplate=f"<b>{eng}</b><br>%{{x:,}} docs, %{{customdata[0]}} queries"
                "<br>%{customdata[1]}<br>%{y:.4g}<extra></extra>",
                **trace_style(eng),
            )
        )
    ys = {v: [[f(r, row) for r, row in pts] for pts in by.values()] for v, f in views.items()}
    ax = yaxes({v: [y for t in ys[v] for y in t] for v in views})
    fig.update_layout(
        updatemenus=[
            menu(
                [
                    {"label": short(v), "method": "update", "args": [{"y": ys[v]}, ax[v]]}
                    for v in views
                ],
                0,
            )
        ]
    )
    fig = layout(fig, "docs in the index", ax[first])
    fig.update_xaxes(range=[0, 1.05 * max(x for t in fig.data for x in t.x)])
    k = max(row["k"] for r in subs.values() for row in at_op(r))
    return fig, f"first N docs of {name} · library-default settings · k = {k}"
def better(col: str) -> str:
    """Tell which way a table column improves, for bolding its best value.

    Args:
        col: Column header.

    Returns:
        "hi" for recall, nDCG and R-precision, "lo" for columns in ms, s or GB, "" for labels and
        the shared post-load baseline.
    """
    if re.search(r"recall|nDCG|R-precision", col):
        return "hi"
    if re.search(r"\b(ms|s|GB)$", col) and "baseline" not in col:
        return "lo"
    return ""


def table(head: list[str], rows: list[list[str]]) -> tuple[list[str], str]:
    """Render one table as markdown and as sortable HTML with per-column value filters.

    Each FILTER_COLS column gets a list of its values, unticked: nothing ticked shows every row,
    ticking values shows only those (OR within a column, AND across columns), and "clear filters"
    (a plain form reset) unticks everything. The filtering is pure CSS (:has()), one rule per value;
    rows carry value indices, so no value needs CSS escaping. PAGE's script adds sorting and
    best-value bolding.

    Args:
        head: Column headers.
        rows: Rows of cell strings.

    Returns:
        The markdown lines and the HTML.
    """
    md = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + [
        "| " + " | ".join(r) + " |" for r in rows
    ]
    n, cat = next(TABLES), [i for i, h in enumerate(head) if h in FILTER_COLS]
    order = lambda v: (0, float(v), v) if re.fullmatch(r"-?[\d.]+", v) else (1, 0.0, v)  # noqa: E731
    idx = {c: {v: i for i, v in enumerate(sorted({r[c] for r in rows}, key=order))} for c in cat}
    css = "".join(
        f"#tf{n}:has(input[data-c='{c}']:checked):has(input[data-c='{c}'][data-v='{i}']:not(:checked)) "
        f"tr[data-c{c}='{i}']{{display:none}}"
        for c in cat
        for i in idx[c].values()
    )
    boxes = "".join(
        f"<details><summary>{html.escape(head[c])}</summary>"
        + "".join(
            f"<label><input type=checkbox data-c='{c}' data-v='{i}'>{html.escape(v)}</label>"
            for v, i in idx[c].items()
        )
        + "</details>"
        for c in cat
    )
    th = "".join(
        f"<th data-better='{better(h)}' title='click to sort'>{html.escape(h)}</th>" for h in head
    )
    tb = "".join(
        "<tr "
        + " ".join(f"data-c{c}='{idx[c][r[c]]}'" for c in cat)
        + ">"
        + "".join(f"<td>{html.escape(x)}</td>" for x in r)
        + "</tr>"
        for r in rows
    )
    return (
        md,
        f"<style>{css}</style><div id='tf{n}' class='tf'><form class='cf'>{boxes}"
        "<input type=reset value='clear filters'></form>"
        f"<div class='tw'><table class='sortable'><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></div></div>",
    )


def examples(runs: dict[str, dict]) -> str:
    """Render each engine's example results as HTML (text datasets).

    One collapsed block per query (the first 10) lists each engine's top 5 with default settings; ✓
    marks a result labelled relevant in the dataset.

    Args:
        runs: Run key -> result document.

    Returns:
        The HTML, or "" when no run has examples.
    """
    runs = {e: r for e, r in runs.items() if r.get("examples")}
    if not runs:
        return ""
    out = [
        "<h3>Example results (top 5 with default settings; ✓ = labelled relevant in the dataset)</h3>"
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
    title: str,
    ds: str,
    metric: str,
    runs: dict[str, dict],
    figs: list[tuple[str, go.Figure, str]],
    missing: list[str],
) -> tuple[list[str], list, list[str]]:
    """Render one report section as markdown, chart-tab parts and table-tab parts.

    The intro gives docs, queries, what the quality measure means (text datasets) and the engines
    that did not finish. Each chart gets a numbered card: "Chart N · <dataset> · <measure>", a
    subtitle (metric and the chart's specifics) and a description, all HTML so they wrap. Tables:
    default settings, equal recall (vector datasets), full serial sweep, filtered search (when any),
    memory, example results (text datasets) and DNF. A section with only failed attempts gets its
    heading and the DNF table.

    Args:
        title: Section title.
        ds: Dataset name.
        metric: Metric view, a key of METRIC_VIEWS.
        runs: Run key -> result document of this section.
        figs: (CHARTS key, figure, subtitle) in display order.
        missing: "<run key>: DNF, <last log line>" for each run that did not finish.

    Returns:
        The markdown lines, the chart-tab parts (HTML fragments and figures) and the table-tab HTML
        fragments.
    """
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
    queries = f"{n[0]:,}" if len(n) == 1 else f"{n[0]:,} to {n[-1]:,} (differs by engine)"
    if "-docs" in next(iter(runs)):
        intro = (
            f"Each engine on the first N docs of {ds}, with exact ground truth over those docs; the "
            "scaling chart adds the full run when it exists."
        )
    elif text:
        intro = (
            f"{r0['dataset'].get('source', ds)}: {r0['dataset']['n_base']:,} documents, {queries} "
            "queries with human relevance labels. Quality is nDCG@10: it scores the first 10 results "
            "against the labels, each labelled-relevant result weighted by 1 / log2(rank + 1), divided "
            "by the score of a perfect ranking, so 1.0 means every labelled-relevant document is ranked "
            "first. Moss embeds text with its built-in model and by default blends keyword and vector "
            "scores (alpha 0.8); its alpha 1.0 setting is vector only, like the other engines, which "
            "search fastembed all-MiniLM-L6-v2 vectors. Charts use k = 10; the tables list every k."
        )
    else:
        intro = (
            f"{r0['dataset']['n_base']:,} docs, {queries} queries. Every engine uses its library's "
            "default index and search settings; the recall vs latency chart adds the other search "
            "settings each engine was swept over."
        )
    if missing:
        intro += f" Did not finish: {', '.join(m.split(':')[0] for m in missing)}."
    md = [f"## {title}", "", intro, ""]
    charts = [f"{head}<p>{html.escape(intro)}</p>"]
    md += ["Charts (in report.html):", ""] if figs else []
    for i, (key, fig, sub) in enumerate(figs, 1):
        measure, about = CHARTS[key]
        sub = f"metric: {METRIC_VIEWS[metric]} · {sub}"
        md += [f"- Chart {i} · {ds} · {measure} ({sub})"]
        charts += [
            f"<hr><figure class='chart'><figcaption><h3>Chart {i} · {html.escape(ds)} · "
            f"{html.escape(measure)}</h3><p class='sub'>{html.escape(sub)}</p>"
            f"<p class='about'>{html.escape(about)}</p></figcaption>",
            fig,
            "</figure>",
        ]
    md += [""] if figs else []
    tables = [f"{head}<p>{html.escape(intro)}</p>"]

    def add(name: str, cols: list[str], rows: list[list[str]]) -> None:
        """Append one table to the markdown and the Tables tab.

        Args:
            name: Table heading.
            cols: Column headers.
            rows: Rows of cell strings.
        """
        m, h = table(cols, rows)
        md.extend(["", f"### {name}", "", *m])
        tables.append(f"<h3>{html.escape(name)}</h3>{h}")

    def quality(row: dict) -> list[str]:
        """Format a serial row's quality cells.

        Args:
            row: Serial row.

        Returns:
            The headline, then (text datasets) R-precision and recall@k against the human labels
            ("-" when recall@k is missing).
        """
        q = row.get(f"recall@{row['k']}")
        return [
            f"{row['headline']:.4f}",
            *([f"{row['r_precision']:.4f}", f"{q:.4f}" if q is not None else "-"] if text else []),
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
                    label(r, row["params"]),
                    str(row["k"]),
                    *quality(row),
                    *(f"{row['latency_ms'][key]:.3f}" for key in LATENCY.values()),
                    f"{r['load']['build_s']:.1f}",
                    *([f"{embed_s(r):.1f}" if embed_s(r) is not None else "in build"] if text else []),
                    f"{g['index']:.2f}",
                    f"{g['build peak']:.2f}",
                    f"{g['on disk']:.2f}",
                ]
            )
    add(
        "Default settings (library-default index and search settings, every k)",
        [
            "engine",
            "metric",
            "setting",
            "k",
            *qcols,
            *lat_cols,
            "build s",
            *(["corpus embed s"] if text else []),
            "index GB",
            "build peak GB",
            "disk GB",
        ],
        op,
    )
    if not text:
        add(
            "Equal recall (cheapest setting reaching each recall@k target, by mean latency)",
            ["engine", "k", "target", "setting", *qcols, *lat_cols],
            [
                [
                    e,
                    str(k),
                    f"{t}",
                    label(r, row["params"]) if row else "not reached",
                    f"{row['headline']:.4f}" if row else "-",
                    *(f"{row['latency_ms'][key]:.3f}" if row else "-" for key in LATENCY.values()),
                ]
                for k in sorted({row["k"] for r in runs.values() for row in r["serial"]})
                for t in TARGETS
                for e, r in runs.items()
                for row in [cheapest(r, k, t)]
            ],
        )
    add(
        "Full serial sweep",
        ["engine", "setting", "k", *qcols, *lat_cols],
        [
            [
                e,
                label(r, row["params"]),
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
            f"{u['headline']:.4f}" if u else "-",
            f"{u['latency_ms']['mean']:.3f}" if u else "-",
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
        for u in [unfiltered(r)]
        for f in r["filter"]
    ]
    if filt:
        add(
            "Filtered search (k = 100, default settings; cold = first pass over a filter, warm = second pass)",
            [
                "engine",
                "filter",
                "unfiltered recall@100",
                "unfiltered mean ms",
                "recall@100 cold",
                "recall@100 warm",
                "cold first query ms",
                *(f"{p} {x} ms" for p in ("warm", "cold") for x in ("mean", "p50", "p99")),
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
                *(f"{(peaks[s] - base) / 1024:.2f}" if s in peaks else "-" for s in STAGES),
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


NOTES = [
    "† Metric. Every document and query vector is scaled to unit length when the dataset is prepared. "
    "For unit vectors, cosine similarity equals the inner product and squared L2 distance equals "
    "2 − 2 × inner product, so all three rank documents identically and give the same recall. The "
    "datasets are defined with cosine similarity, so the inner-product view (the default) runs every "
    "engine in its inner-product mode (cosine where an engine has no inner product), and every engine "
    "computes the same similarity. The library-default view runs each engine with its library's "
    "default metric (L2 for most), which can change speed but not the ranking. Moss, zvec and Qdrant "
    "use inner product by default and appear unchanged in both views.",
    "Quality. recall@k is the share of the true k nearest documents (found by exact search) that an "
    "engine returns in its top k, averaged over the queries: recall@100 ≥ 0.95 means at least 95 of "
    "the true 100 on average, and 1.0 means the same results as exact search. Text datasets are "
    "scored with nDCG@10 against human relevance labels; their section explains it.",
    "Latency. Wall-clock time per query, one query at a time, over every measured query, after 100 "
    "unmeasured warm-up queries per setting. Statistics: mean, p50, p95, p99; p99.9 is left out "
    "because with at most 1,000 queries it is one of the two slowest samples. Each configuration "
    "was measured in one run, without repeats. Engines differ in how many CPU cores one query uses; "
    "CPU time is not measured. Each engine returns its library's default result payload (e.g. "
    "Chroma: ids, metadata, documents and distances; LanceDB: every column, the vector included; "
    "FAISS: ids and distances), and a larger payload costs more as k grows.",
]


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
.tf form{margin:4px 0 6px}.tf details{display:inline-block;margin:0 12px 4px 0;vertical-align:top}
.tf label{display:block;font-size:13px}.tf input[type=reset]{font:inherit;color:var(--ink);background:var(--surface);
border:1px solid var(--rule);border-radius:6px;padding:2px 10px}
.tw{overflow-x:auto}table{border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:13px}
th,td{border-bottom:1px solid var(--rule);padding:4px 10px;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}table.sortable th{cursor:pointer;user-select:none}
th[data-dir=asc]::after{content:" ▲"}th[data-dir=desc]::after{content:" ▼"}td.best{font-weight:700;background:var(--best)}
td.snip{white-space:normal;text-align:left;min-width:320px}summary{cursor:pointer;margin:6px 0}
figure.chart{margin:0;border:1px solid var(--rule);border-radius:8px;padding:12px 16px}figure.chart h3{margin:0 0 4px}
p.about{margin:0;max-width:900px}p.sub{margin:0 0 6px;color:var(--ink)}
.notes p{max-width:1000px;margin:6px 0}hr{border:0;border-top:2px solid var(--rule);margin:32px 0}
</style></head><body><h1>Moss vector benchmark</h1><p>__ENV__</p>
<nav><button data-tab="charts" aria-pressed="true">Charts</button><button data-tab="tables" aria-pressed="false">Tables</button>
<label>dataset <select id="ds">__OPTIONS__</select></label>
<label>metric <select id="metric">__METRICS__</select></label></nav>
<div class="notes">__NOTES__</div>
<p>Charts: hover any point or bar for exact values; click a legend entry to hide an engine, double-click to isolate it;
dropdowns above each chart switch the measure. Tables: click a header to sort; open a column's value list and tick values
to show only those rows (nothing ticked = all rows; "clear filters" unticks everything); the best value per column among
the shown rows is bold.</p>__BODY__
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
  const ds = document.getElementById("ds").value, metric = document.getElementById("metric").value;
  for (const s of document.querySelectorAll("section"))
    s.hidden = s.dataset.tab !== tab || s.dataset.ds !== ds || s.dataset.metric !== metric;
  for (const b of document.querySelectorAll("nav button")) b.setAttribute("aria-pressed", b.dataset.tab === tab);
  for (const el of document.querySelectorAll("section:not([hidden]) .js-plotly-plot")) Plotly.Plots.resize(el);
};
for (const b of document.querySelectorAll("nav button")) b.onclick = () => { tab = b.dataset.tab; show(); };
document.getElementById("ds").onchange = document.getElementById("metric").onchange = show;
show();
// Tables: sort on header click, bold the best value per column among the shown rows (value filters are CSS).
const num = td => { const v = parseFloat(td.textContent); return isNaN(v) ? null : v; };
const best = t => {
  for (const td of t.querySelectorAll("td.best")) td.classList.remove("best");
  const rows = [...t.tBodies[0].rows].filter(r => getComputedStyle(r).display !== "none");
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
  const f = t.closest(".tf");  // re-bold after a value filter changes or "clear filters" (reset fires first)
  f.addEventListener("change", () => best(t));
  f.addEventListener("reset", () => setTimeout(() => best(t)));
  best(t);
}
</script></body></html>"""


def main() -> None:
    """Write results/report.html and results/summary.md for every dataset with results.

    Each dataset gets one view per metric (METRIC_VIEWS, switched on the page; both in the
    markdown), each with a full-corpus section and, when there are --docs runs, a subsets section,
    with their charts and tables. The inner-product view takes every --metric ip run plus the
    default run of each engine whose default metric is already inner product. A dataset with only
    failed attempts gets DNF sections. plotly.js is inlined once, so the page works offline.

    Raises:
        SystemExit: There are no results, or a run's newest attempt failed while an older result
            exists (STALE; nothing is written).
    """
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
    for e in envs:  # every version used across runs (run_suite.sh upgrades moss between runs)
        for pkg, v in e["versions"].items():
            versions.setdefault(pkg, set()).add(v)
    env_line = (
        f"Hardware: {env['cpu']}, {env['cores']} cores, {env['ram_gb']} GB, {env['os']}. "
        "Versions: " + ", ".join(p + " " + " / ".join(sorted(v)) for p, v in versions.items()) + "."
    )
    md = ["# Benchmark results", "", env_line, "", "Interactive charts: report.html", ""]
    md += [x for n in NOTES for x in (n, "")]
    body: list[tuple[str, str, str, object]] = []  # (dataset, tab, metric, HTML fragment or figure)
    names = sorted(set(runs) | {ds for ds, _, ok, _, _ in att if not ok})
    for name in names:
        have = runs.get(name, {})
        dnfs = [(key, last) for ds, key, ok, last, _ in att if ds == name and not ok]
        for metric, view in METRIC_VIEWS.items():
            if metric == "ip":  # --metric ip runs, else the default run of an engine that is ip already
                pick = {
                    re.sub(r"-ip(?=$|-docs)", "", k): r for k, r in have.items() if "-ip" in k
                }
                pick |= {
                    k: r
                    for k, r in have.items()
                    if "-ip" not in k and r.get("metric") in IP and k not in pick
                }
                dnf = [(re.sub(r"-ip(?=$|-docs)", "", k), last) for k, last in dnfs if "-ip" in k]
            else:
                pick = {k: r for k, r in have.items() if "-ip" not in k}
                dnf = [(k, last) for k, last in dnfs if "-ip" not in k]
            full = {k: pick[k] for k in sorted(pick) if "-docs" not in k}
            subs = {k: pick[k] for k in sorted(pick) if "-docs" in k}
            for title, rs, sub in (
                (f"{name} · metric: {view}", full, False),
                (f"{name} · corpus-size subsets · metric: {view}", subs, True),
            ):
                missing = [f"{k}: DNF, {last}" for k, last in dnf if ("-docs" in k) == sub]
                if not rs and not missing:
                    continue
                figs: list = []
                if rs and sub:
                    figs = [("scaling", *scaling(name, full, rs))]
                elif rs:
                    text = next(iter(rs.values()))["dataset"]["kind"] == "text"
                    figs = [
                        *([] if text else [("equal", *equal_recall(rs))]),
                        ("tradeoff-text" if text else "tradeoff", *tradeoff(rs, text)),
                        ("latency", *latency_bars(rs, text)),
                        ("build-text" if text else "build", *build_bars(rs)),
                        ("memory", *memory_bars(rs)),
                    ]
                    if fb := filter_lines(rs):
                        figs.append(("filter", *fb))
                m, charts, tables = section(title, name, metric, rs, figs, missing)
                md += m
                body += [(name, "charts", metric, p) for p in charts]
                body += [(name, "tables", metric, p) for p in tables]
    parts, first, i = [], True, 0
    for ds in names:
        for metric in METRIC_VIEWS:
            for tab in ("charts", "tables"):
                parts.append(
                    f"<section data-tab='{tab}' data-ds='{html.escape(ds)}' data-metric='{metric}'>"
                )
                for p in (p for d, t, m, p in body if (d, t, m) == (ds, tab, metric)):
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
        .replace("__OPTIONS__", "".join(f"<option>{html.escape(n)}</option>" for n in names))
        .replace(
            "__METRICS__",
            "".join(f"<option value='{m}'>{html.escape(v)}</option>" for m, v in METRIC_VIEWS.items()),
        )
        .replace("__NOTES__", "".join(f"<p>{html.escape(n)}</p>" for n in NOTES))
        .replace("__BODY__", "\n".join(parts))
        .replace("__DARK__", dark)
    )
    (RESULTS / "report.html").write_text(page)
    (RESULTS / "summary.md").write_text("\n".join(md) + "\n")
    print(f"wrote {RESULTS / 'report.html'} and {RESULTS / 'summary.md'}")


if __name__ == "__main__":
    main()
