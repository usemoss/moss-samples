"""Shared pieces of the report_*.py page builders: loading a suite's results, chart and table
helpers, and the page shell. Each page builder reads only the suites it names and writes its
own page.

Results: results/<suite>/<dataset>/<run key>-<stamp>.json, run key = engine[-ip][-docsN]; the newest
stamp per run key wins. Logs: results/logs/<suite>-<dataset>-<run key>-<stamp>.log; a log without a
`wrote ` line is a failed attempt (DNF), and a failed newest attempt with an older result is STALE
(the page builder exits without writing).
"""

import html
import itertools
import json
import math
import os
import re
from pathlib import Path

import plotly.graph_objects as go

RESULTS = Path(
    os.environ.get("BENCH_RESULTS") or Path(__file__).parent / "results"
)  # BENCH_RESULTS: preview another dir
# Fixed engine -> (light hue, dark hue, marker, dash); validated categorical palette (8 hues, light
# and dark steps). Color follows the engine, never its rank. Two setups of one library share a hue
# and differ by dash and marker.
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
IP = {"ip", "dot"}  # result metrics that are inner product (moss, zvec: ip; qdrant: dot)
METRIC_VIEWS = {"ip": "inner product†", "default": "library default"}
FILTER_COLS = {"engine", "metric", "setting", "knob", "k", "filter", "target"}  # get value filters
TABLES = itertools.count()  # unique id per rendered table (scopes its filter CSS)
NOTES = {
    "metric": "Every document and query vector is scaled to unit length when the dataset "
    "is prepared. For unit vectors, cosine similarity equals the inner product and squared L2 distance "
    "equals 2 − 2 × inner product, so all three rank documents identically and give the same recall. "
    "The datasets are defined with cosine similarity, so the inner-product view (the default) runs every "
    "engine in its inner-product mode (cosine where an engine has no inner product), and every engine "
    "computes the same similarity. The library-default view runs each engine with its library's default "
    "metric (L2 for most), which can change speed but not the ranking. Moss, zvec and Qdrant use inner "
    "product by default and appear unchanged in both views.",
    "quality": "recall@k is the share of the true k nearest documents (found by exact search) "
    "that an engine returns in its top k, averaged over the queries: recall@100 ≥ 0.95 means at least "
    "95 of the true 100 on average, and 1.0 means the same results as exact search. Text datasets are "
    "scored with nDCG@10 against human relevance labels; their section explains it.",
    "latency": "Wall-clock time per query, one query at a time, over every measured query, "
    "after 100 unmeasured warm-up queries. Statistics: mean, p50, p95, p99; p99.9 is left out because "
    "with at most 1,000 queries it is one of the two slowest samples. Each configuration was measured "
    "in one run, without repeats. Engines differ in how many CPU cores one query uses; CPU time is not "
    "measured. Each engine returns its library's default result payload (e.g. Chroma: ids, metadata, "
    "documents and distances; LanceDB: every column, the vector included; FAISS: ids and distances), "
    "and a larger payload costs more as k grows. Exception: on dbpedia-openai-1m, FAISS-HNSW's first passes "
    "after its index build ran 1.2-2.4x slower than the same setting measured later in the run (k = 10, "
    "library default metric: 0.320 ms against 0.138 ms), so its default-settings latency and lowest "
    "Pareto point there are overstated.",
}
# Subsection heading of each note; the "metric" note only shows in the inner-product view.
NOTE_HEADINGS = {
    "metric": "† Inner product metric",
    "quality": "Quality measures: recall@k and nDCG@10",
    "latency": "How latency is measured",
}
NOTES_HEADING = "About these results"


def notes_html(keys: list[str]) -> str:
    """Render the notes as a headed section, one subsection per note.

    The metric note is marked note-ip so the page script shows it only in the inner-product view.

    Args:
        keys: Keys of NOTES, in display order.

    Returns:
        The HTML.
    """
    return f"<h2>{NOTES_HEADING}</h2>" + "".join(
        f"<div{' class=note-ip' if k == 'metric' else ''}><h3>{html.escape(NOTE_HEADINGS[k])}</h3>"
        f"<p>{html.escape(NOTES[k])}</p></div>"
        for k in keys
    )


def notes_md(keys: list[str]) -> list[str]:
    """Render the notes as markdown: a section heading, then one subsection per note.

    Args:
        keys: Keys of NOTES, in display order.

    Returns:
        Markdown lines.
    """
    return [f"## {NOTES_HEADING}", ""] + [
        x for k in keys for x in (f"### {NOTE_HEADINGS[k]}", "", NOTES[k], "")
    ]


TEXT_INTRO = (
    "Quality is nDCG@10: it scores the first 10 results against human relevance labels, each "
    "labelled-relevant result weighted by 1 / log2(rank + 1), divided by the score of a perfect "
    "ranking, so 1.0 means every labelled-relevant document is ranked first. Moss embeds text with its "
    "built-in model and by default blends keyword and vector scores (alpha 0.8); its alpha 1.0 setting "
    "is vector only, like the other engines, which search fastembed all-MiniLM-L6-v2 vectors. Latency "
    "is end to end: it includes embedding the query."
)


def load(suite: str) -> dict[str, dict[str, dict]]:
    """Load the newest result of every run key of a suite, per dataset.

    Args:
        suite: Suite name (results/<suite>/).

    Returns:
        {dataset: {run key: result}}; file names end in a sortable stamp, so the newest wins.
    """
    runs: dict[str, dict[str, dict]] = {}
    for p in sorted((RESULTS / suite).glob("*/*.json")):
        key = re.sub(r"-\d{8}T\d{6}$", "", p.stem)
        runs.setdefault(p.parent.name, {})[key] = json.loads(p.read_text())
    return runs


def attempts(suite: str) -> list[tuple[str, str, bool, str, str]]:
    """Find the newest attempt of every run of a suite from its logs, successful or not.

    A log without a `wrote ` line was killed, crashed or is still running.

    Args:
        suite: Suite name; its logs are results/logs/<suite>-<dataset>-<run key>-<stamp>.log.

    Returns:
        One (dataset, run key, succeeded, last log line (cut to 160 characters), log name) per run.
    """
    engines = "|".join(map(re.escape, sorted(STYLE, key=len, reverse=True)))
    name = re.compile(rf"{suite}-(.+)-((?:{engines})(?:-ip)?(?:-docs\d+)?)-(\d{{8}}T\d{{6}})")
    newest: dict[tuple[str, str], tuple[str, str, bool, str, str]] = {}
    for log in sorted((RESULTS / "logs").glob(f"{suite}-*.log")):  # sorted by stamp: newest wins
        if not (m := name.fullmatch(log.stem)):
            continue
        text = log.read_text(errors="replace")
        last = (text.strip().splitlines() or ["(empty log)"])[-1][:160]
        newest[m[1], m[2]] = (
            m[1],
            m[2],
            re.search(r"^wrote ", text, re.M) is not None,
            last,
            log.name,
        )
    return list(newest.values())


def check_stale(suite: str, runs: dict[str, dict[str, dict]]) -> list[tuple[str, str, str]]:
    """Exit if any run's newest attempt failed while an older result exists; list the DNFs.

    Args:
        suite: Suite name.
        runs: Its results, as returned by load().

    Returns:
        (dataset, run key, last log line) for every run that did not finish and has no result.

    Raises:
        SystemExit: STALE runs (an old number would stand in for a failed rerun); nothing is
            written.
    """
    att = attempts(suite)
    bad = [
        f"STALE {log}: {last}"
        for ds, key, ok, last, log in att
        if not ok and key in runs.get(ds, {})
    ]
    if bad:
        raise SystemExit(
            "\n".join(
                bad
                + [
                    "The newest attempt of these runs failed but an older result exists. Read the log, "
                    "then rerun, or move the old result out of results/ deliberately. Nothing was written."
                ]
            )
        )
    return [(ds, key, last) for ds, key, ok, last, _ in att if not ok]


def view(runs: dict[str, dict], metric: str) -> dict[str, dict]:
    """Select one metric view of a dataset's runs, keyed by run key without "-ip".

    The inner-product view takes every --metric ip run plus the default run of each engine whose
    default metric is already inner product; the library-default view takes every default run.

    Args:
        runs: Run key -> result, for one dataset.
        metric: "ip" or "default".

    Returns:
        Run key (no "-ip") -> result, sorted by key.
    """
    strip = lambda k: re.sub(r"-ip(?=$|-docs)", "", k)  # noqa: E731
    if metric == "ip":
        pick = {strip(k): r for k, r in runs.items() if "-ip" in k}
        pick |= {
            k: r for k, r in runs.items() if "-ip" not in k and r["metric"] in IP and k not in pick
        }
    else:
        pick = {k: r for k, r in runs.items() if "-ip" not in k}
    return {k: pick[k] for k in sorted(pick)}


def dnf_view(dnfs: list[tuple[str, str, str]], ds: str, metric: str) -> list[str]:
    """The DNF lines of one dataset and metric view.

    Args:
        dnfs: (dataset, run key, last log line), as returned by check_stale().
        ds: Dataset.
        metric: "ip" or "default".

    Returns:
        "<run key>: DNF, <last log line>" per run of that view that did not finish.
    """
    return [
        f"{re.sub(r'-ip(?=$|-docs)', '', k)}: DNF, {last}"
        for d, k, last in dnfs
        if d == ds and ("-ip" in k) == (metric == "ip")
    ]


def setting(r: dict, params: dict) -> str:
    """Name a search setting for display.

    Args:
        r: Result document the setting belongs to.
        params: The setting; {} is the library default.

    Returns:
        "default" or the setting, e.g. "ef 64"; Moss's text settings say what they search with.
    """
    name = ", ".join(f"{k} {v}" for k, v in params.items()) if params else "default"
    if r["engine"] == "moss" and r["dataset"]["kind"] == "text":
        name += " (vector only)" if params.get("alpha") == 1.0 else " (hybrid: keyword + vector)"
    return name


def frontier(points: list[tuple]) -> list[tuple]:
    """Keep the Pareto frontier of (quality, latency, ...) points (ann-benchmarks create_pointset).

    Points are scanned fastest first (equal latency: higher quality first); a point is kept when its
    quality is higher than every point kept before it, so at equal quality only the fastest stays.

    Args:
        points: (quality, latency, ...) tuples.

    Returns:
        The frontier points, by ascending quality (and latency).
    """
    out, best = [], -math.inf
    for p in sorted(points, key=lambda p: (p[1], -p[0])):
        if p[0] > best:
            out.append(p)
            best = p[0]
    return sorted(out, key=lambda p: (p[0], p[1]))


def trace_style(engine: str) -> dict:
    """Return the Plotly line and marker style of an engine (run keys reuse their engine's style).

    Args:
        engine: Engine name or run key.

    Returns:
        {"line": ..., "marker": ...}; an unknown engine gets a neutral gray circle.
    """
    color, _, symbol, dash = STYLE.get(
        re.sub(r"(-ip)?(-docs\d+)?$", "", engine), ("#52514e", "#c3c2b7", "circle", "solid")
    )
    return {
        "line": {"color": color, "width": 2, "dash": dash},
        "marker": {"color": color, "symbol": symbol, "size": 9},
    }


def yaxes(
    views: dict[str, list[float | None]], log: bool = False, axis: str = "yaxis"
) -> dict[str, dict]:
    """Build the axis relayout of each dropdown view.

    Views with the same unit (the title's text after its last ", ") share one fixed range, so
    switching statistics never moves the axis. A linear axis runs from 0 to 5% above the unit's
    largest value. With log=True, a unit whose positive values span more than LOG_SPAN x gets a log
    axis: it spans those values with a 30% margin, its title ends in "(log scale)", and it gets
    1-2-5 ticks labelled in full.

    Args:
        views: Axis title -> the values plotted in that view (None for a gap).
        log: Allow log axes.
        axis: Plotly axis name ("yaxis", "yaxis2", ...).

    Returns:
        Axis title -> relayout keys: "<axis>.title.text", ".type", ".range", ".tickvals" and
        ".ticktext" (None on a linear axis, which clears them).
    """
    unit = {v: v.rsplit(", ", 1)[-1] for v in views}
    vals: dict[str, list[float]] = {}
    for v, xs in views.items():
        vals.setdefault(unit[v], []).extend(x for x in xs if x is not None)
    out = {}
    for v in views:
        top, pos = max(vals[unit[v]], default=0), [x for x in vals[unit[v]] if x > 0]
        out[v] = {
            f"{axis}.title.text": v,
            f"{axis}.type": "linear",
            f"{axis}.range": [0, 1.05 * top or 1],
            f"{axis}.tickvals": None,
            f"{axis}.ticktext": None,
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
                f"{axis}.title.text": f"{v} (log scale)",
                f"{axis}.type": "log",
                f"{axis}.range": [math.log10(lo), math.log10(hi)],
                f"{axis}.tickvals": ticks,
                f"{axis}.ticktext": [f"{t:g}" for t in ticks],
            }
    return out


def layout(fig: go.Figure, x: str, y: dict, height: int = 480) -> go.Figure:
    """Apply the shared look: recessive grid, dropdown row on top, legend on the right.

    Titles, subtitles and descriptions are HTML above the figure (see card()).

    Args:
        fig: Figure to style, in place.
        x: X-axis title.
        y: Y-axis relayout of the opening view, one value of yaxes().
        height: Figure height in px.

    Returns:
        fig.
    """
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="#fcfcfb",
        plot_bgcolor="#fcfcfb",
        height=height,
        hovermode="closest",
        legend={"title": {"text": "click / double-click"}},
        margin={"t": 60, "r": 20},
        xaxis_title=x,
        font={"family": "system-ui, sans-serif", "size": 13},
    )
    fig.update_layout({k.replace(".", "_"): v for k, v in y.items()})
    return fig


def menu(buttons: list[dict], x: float = 0) -> dict:
    """Build a dropdown menu above the plot area, readable in both themes.

    Args:
        buttons: Plotly updatemenu buttons.
        x: Left edge, as a fraction of the plot width.

    Returns:
        The updatemenu.
    """
    return {
        "type": "dropdown",
        "buttons": buttons,
        "x": x,
        "xanchor": "left",
        "y": 1.02,
        "yanchor": "bottom",
        "showactive": True,
        "font": {"color": "#0b0b0b"},
        "bgcolor": "#ffffff",
        "bordercolor": "#52514e",
    }


def short(view: str) -> str:
    """Dropdown label of a view: its axis title without unit and direction.

    Args:
        view: Axis title, e.g. "p95 latency, ms (lower is better)".

    Returns:
        The measure, e.g. "p95 latency".
    """
    return view.split(",")[0].split(" (")[0]


def bars(
    views: dict[str, list[float | None]],
    engines: list[str],
    text: dict[str, list[str]] | None = None,
) -> go.Figure:
    """Plot one bar per engine in its color on a linear axis from 0, with a view dropdown.

    Every bar is labelled with its value (4 significant digits), so a bar too short to see on a
    shared linear axis is still readable; an optional per-view label (e.g. the setting used) comes
    before the value.

    Args:
        views: Axis title (measure, unit and direction) -> one value per engine (None = no bar).
        engines: Engine names (x axis), in the order of each view's values.
        text: Optional bar label per view, one per engine.

    Returns:
        The figure; the first view opens.
    """
    first = next(iter(views))

    def labels(v: str) -> list[str]:
        """Bar labels of one view: "<label> · <value>", the value, or the label alone (no bar)."""
        out = []
        for i, y in enumerate(views[v]):
            t = text[v][i] if text else ""
            out.append(t if y is None else f"{t} · {y:.4g}" if t else f"{y:.4g}")
        return out

    def hover(v: str) -> str:
        """Hover template of one view: engine, measure, value (and the bar label)."""
        return (
            f"<b>%{{x}}</b><br>{short(v)}: %{{y:.4g}}"
            + ("<br>%{text}" if text else "")
            + "<extra></extra>"
        )

    fig = go.Figure(
        go.Bar(
            x=engines,
            y=views[first],
            text=labels(first),
            textposition="outside",
            cliponaxis=False,
            marker={
                "color": [trace_style(e)["line"]["color"] for e in engines],
                "line": {"color": "#fcfcfb", "width": 2},
            },
            hovertemplate=hover(first),
        )
    )
    ax = yaxes(views)
    if len(views) > 1:
        fig.update_layout(
            updatemenus=[
                menu(
                    [
                        {
                            "label": short(v),
                            "method": "update",
                            "args": [
                                {"y": [vals], "text": [labels(v)], "hovertemplate": hover(v)},
                                ax[v],
                            ],
                        }
                        for v, vals in views.items()
                    ]
                )
            ]
        )
    fig = layout(fig, "engine" + (" (bar label: the setting used)" if text else ""), ax[first])
    fig.update_layout(showlegend=False)
    return fig


def better(col: str) -> str:
    """Tell which way a table column improves, for bolding its best value.

    Args:
        col: Column header.

    Returns:
        "hi" for quality columns, "lo" for columns in ms, s or GiB (not the baseline), "" otherwise.
    """
    if re.search(r"recall|nDCG|R-precision|docs/s", col):
        return "hi"
    if re.search(r"\b(ms|s|GiB)$", col) and "baseline" not in col:
        return "lo"
    return ""


def table(head: list[str], rows: list[list[str]]) -> tuple[list[str], str]:
    """Render one table as markdown and as sortable HTML with per-column value filters.

    Each FILTER_COLS column gets a list of its values, unticked: nothing ticked shows every row,
    ticking values shows only those (OR within a column, AND across columns), and "clear filters"
    (a form reset) unticks everything. The filtering is pure CSS (:has()); rows carry value
    indices. PAGE's script adds sorting and best-value bolding.

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
    return md, (
        f"<style>{css}</style><div id='tf{n}' class='tf'><form class='cf'>{boxes}"
        "<input type=reset value='clear filters'></form>"
        f"<div class='tw'><table class='sortable'><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></div></div>"
    )


class Section:
    """One dataset and metric view of a page: intro, numbered chart cards, tables, markdown."""

    def __init__(self, ds: str, metric: str, title: str, intro: str) -> None:
        """Start a section.

        Args:
            ds: Dataset name.
            metric: Metric view, a key of METRIC_VIEWS.
            title: Section heading.
            intro: Intro paragraph.
        """
        self.ds, self.metric, self.n = ds, metric, 0
        self.html: list = [f"<h2>{html.escape(title)}</h2><p>{html.escape(intro)}</p>"]
        self.md = [f"## {title}", "", intro, ""]

    def card(self, measure: str, sub: str, about: str, fig: go.Figure) -> None:
        """Add a numbered chart card: "Chart N · <dataset> · <measure>", subtitle, description.

        Args:
            measure: What the chart shows (the title after the dataset).
            sub: Subtitle: specifics (k, setting, ...); the metric view is prepended.
            about: Description.
            fig: The figure.
        """
        self.n += 1
        sub = f"metric: {METRIC_VIEWS[self.metric]} · {sub}"
        self.md += [f"- Chart {self.n} · {self.ds} · {measure} ({sub})"]
        self.html += [
            f"<hr><figure class='chart'><figcaption><h3>Chart {self.n} · {html.escape(self.ds)} · "
            f"{html.escape(measure)}</h3><p class='sub'>{html.escape(sub)}</p>"
            f"<p class='about'>{html.escape(about)}</p></figcaption>",
            fig,
            "</figure>",
        ]

    def add_table(self, name: str, head: list[str], rows: list[list[str]]) -> None:
        """Add a table (HTML and markdown) under a heading.

        Args:
            name: Table heading.
            head: Column headers.
            rows: Rows of cell strings.
        """
        m, h = table(head, rows)
        self.md += ["", f"### {name}", "", *m]
        self.html.append(f"<h3>{html.escape(name)}</h3>{h}")

    def add_html(self, fragment: str) -> None:
        """Add a raw HTML fragment (already escaped).

        Args:
            fragment: HTML.
        """
        self.html.append(fragment)


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title><style>
:root{--surface:#fcfcfb;--ink:#0b0b0b;--muted:#52514e;--rule:#e4e3df;--best:#e3eefb}
@media (prefers-color-scheme:dark){:root{--surface:#1a1a19;--ink:#ffffff;--muted:#c3c2b7;--rule:#3a3a37;--best:#1f3550}}
body{background:var(--surface);color:var(--ink);font:15px/1.5 system-ui,sans-serif;margin:0 auto;max-width:1200px;
padding:16px}h2{margin-top:48px;border-top:1px solid var(--rule);padding-top:16px}p{color:var(--muted)}a{color:inherit}
nav{position:sticky;top:0;background:var(--surface);padding:8px 0;border-bottom:1px solid var(--rule);z-index:10;
display:flex;gap:8px;flex-wrap:wrap;align-items:center}
nav select{font:inherit;color:var(--ink);background:var(--surface);border:1px solid var(--rule);border-radius:6px;padding:4px 12px}
.tf form{margin:4px 0 6px}.tf details{display:inline-block;margin:0 12px 4px 0;vertical-align:top}
.tf label{display:block;font-size:13px}.tf input[type=reset]{font:inherit;color:var(--ink);background:var(--surface);
border:1px solid var(--rule);border-radius:6px;padding:2px 10px}
.tw{overflow-x:auto}table{border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:13px}
th,td{border-bottom:1px solid var(--rule);padding:4px 10px;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}table.sortable th{cursor:pointer;user-select:none}
th[data-dir=asc]::after{content:" ▲"}th[data-dir=desc]::after{content:" ▼"}td.best{font-weight:700;background:var(--best)}
td.snip{white-space:normal;text-align:left;min-width:320px}summary{cursor:pointer;margin:6px 0}
figure.chart{margin:0;border:1px solid var(--rule);border-radius:8px;padding:12px 16px}figure.chart h3{margin:0 0 4px}
p.about{margin:0;max-width:900px}p.sub{margin:0 0 6px;color:var(--ink)}hr{border:0;border-top:2px solid var(--rule);margin:32px 0}
.notes p{max-width:1000px;margin:4px 0 12px}.notes h3{margin:12px 0 0}
</style></head><body><p><a href="index.html">← all benchmarks</a></p><h1>__TITLE__</h1><p>__LEAD__</p><p>__ENV__</p>
<nav><label>dataset <select id="ds">__OPTIONS__</select></label>
<label>metric <select id="metric">__METRICS__</select></label></nav>
<div class="notes">__NOTES__</div>
<p>Charts: hover any point or bar for exact values; click a legend entry to hide an engine, double-click to isolate it;
dropdowns above a chart switch the measure. Tables: click a header to sort; open a column's value list and tick values
to show only those rows (nothing ticked = all rows; "clear filters" unticks everything); the best value per column among
the shown rows is bold.</p>__BODY__
<script>
// Dark mode: the same hues stepped for the dark surface (validated palette), applied after Plotly renders.
const DARK = __DARK__;
if (matchMedia("(prefers-color-scheme: dark)").matches) {
  const swap = c => Array.isArray(c) ? c.map(swap) : (DARK[c] || c);
  for (const el of document.querySelectorAll(".js-plotly-plot")) {
    const ax = Object.keys(el.layout).filter(k => /^[xy]axis\\d*$/.test(k));
    Plotly.relayout(el, Object.assign({paper_bgcolor: "#1a1a19", plot_bgcolor: "#1a1a19", "font.color": "#ffffff"},
      ...ax.map(a => ({[a + ".gridcolor"]: "#3a3a37"}))));
    el.data.forEach((t, i) => Plotly.restyle(el, {"marker.color": [swap(t.marker && t.marker.color)],
      "line.color": [swap(t.line && t.line.color)],
      "marker.line.color": [swap(t.marker && t.marker.line && t.marker.line.color)]}, [i]));
  }
}
// Dataset and metric pickers: show one section; resize the charts that just became visible.
const show = () => {
  const ds = document.getElementById("ds").value, metric = document.getElementById("metric").value;
  for (const s of document.querySelectorAll("section")) s.hidden = s.dataset.ds !== ds || s.dataset.metric !== metric;
  for (const n of document.querySelectorAll(".note-ip")) n.hidden = metric !== "ip";  // the † note explains this view
  for (const el of document.querySelectorAll("section:not([hidden]) .js-plotly-plot")) Plotly.Plots.resize(el);
};
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


def env_line(results: list[dict]) -> str:
    """Summarize hardware and every package version used across a page's results.

    Args:
        results: Result documents.

    Returns:
        "Hardware: ... Versions: ..." (several versions of one package are joined with " / "; runs
        from uncommitted code are flagged).
    """
    if not results:
        return ""
    env, versions = results[0]["env"], {}
    for r in results:
        for pkg, v in r["env"]["versions"].items():
            versions.setdefault(pkg, set()).add(v)
    commits = sorted(
        {r["env"]["git"] + ("+uncommitted" if r["env"].get("git_dirty") else "") for r in results}
    )
    return (
        f"Hardware: {env['cpu']}, {env['cores']} cores, {env['ram_gb']} GiB, {env['os']}. Versions: "
        + ", ".join(p + " " + " / ".join(sorted(v)) for p, v in versions.items())
        + f". Code: {', '.join(commits)}."
    )


def write_page(
    name: str, title: str, lead: str, notes: list[str], sections: list[Section], results: list[dict]
) -> None:
    """Write results/<name>.html and results/<name>.md.

    plotly.js is inlined once, so the page works offline. Sections are shown one at a time by the
    dataset and metric pickers.

    Args:
        name: File stem.
        title: Page title.
        lead: One-paragraph summary under the title.
        notes: Keys of NOTES shown on the page.
        sections: The page's sections.
        results: Every result shown (for the environment line).
    """
    parts, first, i = [], True, 0
    for s in sections:
        parts.append(f"<section data-ds='{html.escape(s.ds)}' data-metric='{s.metric}'>")
        for p in s.html:
            if isinstance(p, go.Figure):
                parts.append(
                    p.to_html(
                        full_html=False,
                        include_plotlyjs=first,
                        div_id=f"{name}{i}",
                        config={"displaylogo": False, "responsive": True},
                    )
                )
                first, i = False, i + 1
            else:
                parts.append(p)
        parts.append("</section>")
    dsets = list(dict.fromkeys(s.ds for s in sections))
    dark = json.dumps(
        {light: dark for light, dark, _, _ in STYLE.values()}
        | {"#fcfcfb": "#1a1a19", "#52514e": "#c3c2b7"}
    )
    env = env_line(results)
    page = (
        PAGE.replace("__TITLE__", html.escape(title))
        .replace("__LEAD__", html.escape(lead))
        .replace("__ENV__", html.escape(env))
        .replace("__OPTIONS__", "".join(f"<option>{html.escape(d)}</option>" for d in dsets))
        .replace(
            "__METRICS__",
            "".join(
                f"<option value='{m}'>{html.escape(v)}</option>" for m, v in METRIC_VIEWS.items()
            ),
        )
        .replace("__NOTES__", notes_html(notes))
        .replace("__BODY__", "\n".join(parts) if parts else "<p>No results yet.</p>")
        .replace("__DARK__", dark)
    )
    (RESULTS / f"{name}.html").write_text(page)
    md = [f"# {title}", "", lead, "", env, "", *notes_md(notes)]
    md += [x for s in sections for x in s.md + [""]]
    (RESULTS / f"{name}.md").write_text("\n".join(md) + "\n")
    print(f"wrote {RESULTS / name}.html and .md")


def mem_gb(r: dict) -> dict[str, float]:
    """Summarize one run's memory in GiB (2**30 bytes) over the post-load baseline.

    Args:
        r: Result document.

    Returns:
        index (after build), build peak, search peak (the run's search-stage peak, when measured),
        RSS increase over build, on disk.
    """
    m, peaks = r["memory"], r["memory"]["peak_footprint_mb"]
    base = m["baseline_footprint_mb"]
    return {
        "index": (m["footprint_after_build_mb"] - base) / 1024,
        "build peak": (peaks["build"] - base) / 1024,
        "search peak": (peaks["search"] - base) / 1024 if "search" in peaks else math.nan,
        "RSS increase over build": (m["rss_after_build_mb"] - r["load"]["rss_before_build_mb"])
        / 1024,
        "on disk": m["disk_mb"] / 1024,
    }
