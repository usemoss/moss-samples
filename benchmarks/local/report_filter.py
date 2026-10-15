"""Filtered-search report: results/filter.html and results/filter.md.

Reads only results/filter/. Per dataset and metric view, one card per engine: recall@100 (warm pass)
and mean latency (warm and cold passes) for each VectorDBBench filter case, from most to fewest docs
kept, next to the same engine's unfiltered search measured in the same run (library-default
settings, k = 100). A table lists every case with cold and warm recall and latency statistics.

usage: $PWD/.venv/bin/python report_filter.py   (report.py runs it with the other pages)
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from report_common import (
    LATENCY,
    METRIC_VIEWS,
    Section,
    check_stale,
    dnf_view,
    layout,
    load,
    trace_style,
    view,
    write_page,
)


def kept(tag: str) -> float:
    """Percent of docs a VectorDBBench filter case keeps: int_<p>p drops the first p% of ids,
    label_<p>p keeps p%.

    Args:
        tag: Filter case, e.g. "int_99p" or "label_50p".

    Returns:
        The percent of docs kept.
    """
    p = float(tag.split("_")[1].rstrip("p"))
    return 100 - p if tag.startswith("int") else p


def engine_chart(eng: str, r: dict) -> go.Figure:
    """Plot one engine: recall@100 (left) and mean latency (right) per filter case.

    The first x position is the unfiltered pass of the same run.

    Args:
        eng: Engine.
        r: Its filter result.

    Returns:
        The figure.
    """
    cases = sorted(r["cases"], key=lambda c: -kept(c["filter"]))
    xs = ["unfiltered (100% kept)"] + [
        f"{c['filter']} ({kept(c['filter']):g}% kept)" for c in cases
    ]
    u = r["unfiltered"]
    st = trace_style(eng)
    fig = make_subplots(rows=1, cols=2, horizontal_spacing=0.12)
    hover = "<b>%{x}</b><br>%{fullData.name}: %{y:.4g}<extra></extra>"
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=[u["quality"]] + [c["warm"]["quality"] for c in cases],
            name="recall@100 (warm)",
            mode="lines+markers",
            line=st["line"],
            marker=st["marker"],
            hovertemplate=hover,
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=[u["latency_ms"]["mean"]] + [c["warm"]["latency_ms"]["mean"] for c in cases],
            name="mean latency, warm pass",
            mode="lines+markers",
            line=st["line"],
            marker=st["marker"],
            hovertemplate=hover,
        ),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=xs[1:],
            y=[c["cold"]["latency_ms"]["mean"] for c in cases],
            name="mean latency, cold pass",
            mode="lines+markers",
            line=st["line"] | {"dash": "dot"},
            marker=st["marker"] | {"symbol": "circle-open"},
            hovertemplate=hover,
        ),
        row=1,
        col=2,
    )
    lat = [y for t in fig.data[1:] for y in t.y]
    fig = layout(
        fig,
        "filter case (share of docs kept)",
        {"yaxis.title.text": "recall@100 (higher is better)", "yaxis.range": [0, 1.05]},
        height=420,
    )
    fig.update_layout(
        xaxis2_title="filter case (share of docs kept)",
        yaxis2_title="mean latency, ms (lower is better)",
        yaxis2_range=[0, 1.05 * max(lat)],
        legend={"orientation": "h", "y": -0.45, "title": {"text": ""}},
        margin={"t": 30, "b": 150},
    )
    return fig


def section(ds: str, metric: str, runs: dict[str, dict], missing: list[str]) -> Section:
    """Build one dataset and metric view: a card per engine, then the table.

    Args:
        ds: Dataset.
        metric: Metric view.
        runs: Engine -> filter result.
        missing: DNF lines of this view.

    Returns:
        The section.
    """
    title = f"{ds} · metric: {METRIC_VIEWS[metric]}"
    if not runs:
        s = Section(
            ds,
            metric,
            title,
            "No filter run of this view has finished." if missing else "No runs in this view.",
        )
        if missing:
            s.add_table("Did not finish", ["engine and reason"], [[m] for m in missing])
        return s
    r0 = next(iter(runs.values()))
    intro = (
        f"{r0['dataset']['n_base']:,} docs, {r0['dataset']['n_queries']:,} queries, k = 100, library-default "
        "settings. Each case is scored against its own exact ground truth (the true 100 nearest documents among "
        "those the filter keeps). The unfiltered point is the same engine's unfiltered pass in the same run, so the "
        "change from it is what the filter costs. Cold = the first pass over a filter, warm = the same pass again. "
        "FAISS has no metadata filter: it evaluates the predicate into an id bitmap inside every query."
    )
    if missing:
        intro += f" Did not finish: {', '.join(m.split(':')[0] for m in missing)}."
    s = Section(ds, metric, title, intro)
    for eng, r in runs.items():
        s.card(
            f"Filtered search: {eng}",
            f"{eng} only · k = 100 · library-default settings",
            "Left: recall@100 of the warm pass per filter case (the cold pass's recall is in the table). Right: mean "
            "latency of the warm (solid) and cold (dotted) passes. The first point is unfiltered.",
            engine_chart(eng, r),
        )
    rows = []
    for e, r in runs.items():
        u = r["unfiltered"]
        rows.append(
            [
                e,
                r["metric"],
                "unfiltered",
                "100",
                f"{u['quality']:.4f}",
                f"{u['quality']:.4f}",
                *(f"{u['latency_ms'][key]:.3f}" for key in LATENCY.values()),
                "-",
                f"{u['first_ms']:.3f}",
            ]
        )
        for c in sorted(r["cases"], key=lambda c: -kept(c["filter"])):
            rows.append(
                [
                    e,
                    r["metric"],
                    c["filter"],
                    f"{kept(c['filter']):g}",
                    f"{c['cold']['quality']:.4f}",
                    f"{c['warm']['quality']:.4f}",
                    *(f"{c['warm']['latency_ms'][key]:.3f}" for key in LATENCY.values()),
                    f"{c['cold']['latency_ms']['mean']:.3f}",
                    f"{c['cold']['first_ms']:.3f}",
                ]
            )
    s.add_table(
        "Every case (latency statistics of the warm pass; cold mean and first query for comparison)",
        [
            "engine",
            "metric",
            "filter",
            "% kept",
            "recall@100 cold",
            "recall@100 warm",
            *(f"warm {st} ms" for st in LATENCY),
            "cold mean ms",
            "first query ms",
        ],
        rows,
    )
    if missing:
        s.add_table("Did not finish", ["engine and reason"], [[m] for m in missing])
    return s


def main() -> None:
    """Write results/filter.html and .md from results/filter/.

    Raises:
        SystemExit: STALE runs (see report_common.check_stale).
    """
    runs = load("filter")
    dnfs = check_stale("filter", runs)
    sections, shown = [], []
    for ds in sorted(set(runs) | {d for d, _, _ in dnfs}):
        for metric in METRIC_VIEWS:
            v = view(runs.get(ds, {}), metric)
            sections.append(section(ds, metric, v, dnf_view(dnfs, ds, metric)))
            shown += v.values()
    write_page(
        "filter",
        "Filtered search",
        "Each engine's search with a metadata filter (VectorDBBench cases, 99% to 1% of docs kept) against its own "
        "unfiltered search.",
        ["metric", "quality", "latency"],
        sections,
        shown,
    )


if __name__ == "__main__":
    main()
