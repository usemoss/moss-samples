"""Scaling report: results/scaling.html and results/scaling.md.

Reads only results/defaults/: the --docs runs (the first N docs of a vector dataset, exact ground
truth over those docs) and, when present, the same engine's full-corpus run. Per dataset and metric
view, one chart: a line per engine over corpus size, at library-default settings and one k (the
largest every run measured); the dropdown picks quality, a latency statistic, index or build peak
memory, or build time. A table lists every point.

usage: $PWD/.venv/bin/python report_scaling.py   (report.py runs it with the other pages)
"""

import re

import plotly.graph_objects as go

from report_common import (
    LATENCY,
    METRIC_VIEWS,
    Section,
    check_stale,
    dnf_view,
    layout,
    load,
    mem_gb,
    menu,
    short,
    trace_style,
    view,
    write_page,
    yaxes,
)


def section(ds: str, metric: str, runs: dict[str, dict], missing: list[str]) -> Section:
    """Build one dataset and metric view.

    Args:
        ds: Dataset.
        metric: Metric view.
        runs: Run key -> result: --docs runs (engine-docsN) and full runs (engine) of this view.
        missing: DNF lines of the --docs runs of this view.

    Returns:
        The section.
    """
    title = f"{ds} · metric: {METRIC_VIEWS[metric]}"
    subs = {k: r for k, r in runs.items() if "-docs" in k}
    if not subs:
        s = Section(
            ds,
            metric,
            title,
            "No corpus-size run of this view has finished." if missing else "No runs in this view.",
        )
        if missing:
            s.add_table("Did not finish", ["engine and reason"], [[m] for m in missing])
        return s
    engines = sorted({k.split("-docs")[0] for k in subs})
    by = {
        e: sorted(
            [r for k, r in runs.items() if re.sub(r"-docs\d+$", "", k) == e],
            key=lambda r: r["load"]["docs"],
        )
        for e in engines
    }
    k = max(
        set.intersection(*({row["k"] for row in r["rows"]} for rs in by.values() for r in rs)),
        default=None,
    )
    intro = (
        f"Each engine on the first 25k / 50k / 75k docs of {ds}, with exact ground truth over those docs, plus its "
        "full-corpus run when it exists, at library-default settings."
    )
    if missing:
        intro += f" Did not finish: {', '.join(m.split(':')[0] for m in missing)}."
    s = Section(ds, metric, title, intro)
    if k is None:
        s.add_html("<p>The runs share no k, so there is no chart; see the table.</p>")
        return s
    at = lambda r: next(row for row in r["rows"] if row["k"] == k)  # noqa: E731
    views = {f"recall@{k} (vs exact search) (higher is better)": lambda r: at(r)["quality"]}
    views |= {
        f"{st} latency, ms (lower is better)": (lambda key: lambda r: at(r)["latency_ms"][key])(key)
        for st, key in LATENCY.items()
    }
    views |= {
        "index memory, GB (lower is better)": lambda r: mem_gb(r)["index"],
        "build peak memory, GB (lower is better)": lambda r: mem_gb(r)["build peak"],
        "build time, s (lower is better)": lambda r: r["load"]["build_s"],
    }
    ys = {v: [[f(r) for r in by[e]] for e in engines] for v, f in views.items()}
    first = next(iter(views))
    fig = go.Figure()
    for e, y in zip(engines, ys[first]):
        fig.add_trace(
            go.Scatter(
                x=[r["load"]["docs"] for r in by[e]],
                y=y,
                name=e,
                mode="lines+markers",
                **trace_style(e),
                hovertemplate=f"<b>{e}</b><br>%{{x:,}} docs<br>%{{y:.4g}}<extra></extra>",
            )
        )
    ax = yaxes({v: [x for t in ys[v] for x in t] for v in views})
    fig.update_layout(
        updatemenus=[
            menu(
                [
                    {"label": short(v), "method": "update", "args": [{"y": ys[v]}, ax[v]]}
                    for v in views
                ]
            )
        ]
    )
    fig = layout(fig, "docs in the index", ax[first])
    fig.update_xaxes(range=[0, 1.05 * max(x for t in fig.data for x in t.x)])
    s.card(
        "Scaling with corpus size",
        f"library-default settings · k = {k} · first N docs, then the full corpus",
        "How each engine's quality, latency, memory and build time change with the number of indexed docs. "
        "Exact engines all score recall 1.0, so their lines overlap in the recall view (hover or click the legend "
        "to tell them apart). Dropdown: measure.",
        fig,
    )
    s.add_table(
        "Every point",
        [
            "engine",
            "metric",
            "docs",
            f"recall@{k}",
            *(f"{st} ms" for st in LATENCY),
            "build s",
            "index GB",
        ],
        [
            [
                e,
                r["metric"],
                f"{r['load']['docs']}",
                f"{at(r)['quality']:.4f}",
                *(f"{at(r)['latency_ms'][key]:.3f}" for key in LATENCY.values()),
                f"{r['load']['build_s']:.2f}",
                f"{mem_gb(r)['index']:.2f}",
            ]
            for e in engines
            for r in by[e]
        ],
    )
    if missing:
        s.add_table("Did not finish", ["engine and reason"], [[m] for m in missing])
    return s


def main() -> None:
    """Write results/scaling.html and .md from the defaults suite's --docs and full runs.

    Raises:
        SystemExit: STALE runs (see report_common.check_stale).
    """
    runs = load("defaults")
    dnfs = check_stale("defaults", runs)
    sections, shown = [], []
    for ds in sorted(set(runs)):
        if not any("-docs" in k for k in runs[ds]) and not any(
            "-docs" in k for d, k, _ in dnfs if d == ds
        ):
            continue
        for metric in METRIC_VIEWS:
            v = view(runs[ds], metric)
            bases = {k.split("-docs")[0] for k in v if "-docs" in k}
            v = {k: r for k, r in v.items() if "-docs" in k or k in bases}
            missing = [m for m in dnf_view(dnfs, ds, metric) if "-docs" in m.split(":")[0]]
            sections.append(section(ds, metric, v, missing))
            shown += v.values()
    write_page(
        "scaling",
        "Scaling with corpus size",
        "Each engine at library-default settings on growing prefixes of a dataset.",
        ["metric", "quality", "latency"],
        sections,
        shown,
    )


if __name__ == "__main__":
    main()
