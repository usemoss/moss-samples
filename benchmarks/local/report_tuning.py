"""Tuning report: results/tuning.html and results/tuning.md.

Reads results/tuning/ (every search setting of tunable engines) and, for exact engines (one search
setting, "tunable": false), their results/defaults/ full-corpus runs. Per dataset and metric view:
  - latency at equal recall (vector datasets): each engine's fastest setting (mean latency) that
    reaches recall@k >= 0.95 / 0.99, any knob (the library default when within 5%); exact engines
    at their one setting;
  - quality vs latency: per engine only its best settings, the Pareto frontier of its primary knob
    (lowest mean latency for each quality level), one line per engine; exact engines as one point;
    vector datasets pick k from a dropdown, text datasets use k = 10;
  - secondary settings (engines with a second knob, e.g. LanceDB-HNSW refine_factor): one chart per
    engine against that engine's library default;
  - a table of every measured setting and the equal-recall table.

usage: $PWD/.venv/bin/python report_tuning.py   (report.py runs it with the other pages)
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from report_common import (
    LATENCY,
    METRIC_VIEWS,
    TEXT_INTRO,
    Section,
    bars,
    check_stale,
    dnf_view,
    frontier,
    layout,
    load,
    menu,
    setting,
    trace_style,
    view,
    write_page,
    yaxes,
)

TARGETS = (0.95, 0.99)  # equal-recall targets for recall@k


def points(rows: list[dict], r: dict) -> list[tuple[float, float, str]]:
    """(quality, mean latency, setting name) per row.

    Args:
        rows: Result rows.
        r: Their result document.

    Returns:
        One point per row.
    """
    return [
        (row["quality"], row["latency_ms"]["mean"], setting(r, row.get("params", {})))
        for row in rows
    ]


def k_menu(fig: go.Figure, ks: list[int]) -> None:
    """Add a k dropdown that shows the traces whose meta is that k (largest k first, open).

    Args:
        fig: Figure whose traces carry their k in meta.
        ks: k values, ascending.
    """
    legend = [tr.showlegend is not False for tr in fig.data]
    fig.update_layout(
        updatemenus=[
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
                ]
            )
        ]
    )


def frontier_chart(
    tun: dict[str, dict], exact: dict[str, dict], ks: list[int], text: bool
) -> go.Figure:
    """Plot each engine's Pareto frontier of its primary knob (mean latency).

    An exact engine has one setting: it is drawn as a dotted horizontal line at its latency, from
    the lowest quality any engine reached at that k to its own point, so every faster setting of
    another engine sits below the line. Hover shows the real quality at both ends.

    Args:
        tun: Engine -> tuning result.
        exact: Engine -> defaults result of exact engines.
        ks: k values to offer (one trace per engine and k).
        text: True for a text dataset (quality nDCG@10).

    Returns:
        The figure; the largest k opens.
    """
    q = "nDCG@10" if text else "recall@k"
    pts: dict[tuple[str, int], list[tuple[float, float, str]]] = {}
    for eng, r in sorted({**tun, **exact}.items()):
        for k in ks:
            rows = [
                row
                for row in r["rows"]
                if row["k"] == k and row.get("knob", "primary") == "primary"
            ]
            if rows:
                pts[eng, k] = (
                    [(a, b, "exact") for a, b, _ in points(rows, r)]
                    if eng in exact
                    else frontier(points(rows, r))
                )
    lo = {
        k: min(p[0] for (_, kk), ps in pts.items() if kk == k for p in ps)
        for k in ks
        if any(kk == k for _, kk in pts)
    }
    fig = go.Figure()
    for (eng, k), p in pts.items():
        st = trace_style(eng)
        custom = [[a[2], a[0]] for a in p]
        if eng in exact and lo[k] < p[0][0]:  # dotted reference line ending at the exact point
            p = [(lo[k], p[0][1], "exact"), p[0]]
            custom = [custom[0], custom[0]]
            st["line"]["dash"], st["marker"]["size"] = "dot", [0, 9]
        fig.add_trace(
            go.Scatter(
                x=[a[0] for a in p],
                y=[a[1] for a in p],
                customdata=custom,
                name=f"{eng} (exact)" if eng in exact else eng,
                mode="lines+markers",
                line=st["line"],
                marker=st["marker"],
                meta=k,
                visible=k == ks[-1],
                hovertemplate=f"<b>{eng}</b> k={k}<br>%{{customdata[0]}}<br>{q} %{{customdata[1]:.4f}}"
                "<br>mean %{y:.3f} ms<extra></extra>",
            )
        )
    ax = yaxes({"mean latency, ms (lower is better)": [y for t in fig.data for y in t.y]}, log=True)
    fig = layout(
        fig,
        f"{'nDCG@10 (human labels)' if text else 'recall@k (vs exact search)'} (higher is better)",
        next(iter(ax.values())),
    )
    xs = [x for t in fig.data for x in t.x]
    pad = max(0.01, (max(xs) - min(xs)) * 0.03)
    fig.update_xaxes(range=[min(xs) - pad, max(xs) + pad])  # one range for every k
    if len(ks) > 1:
        k_menu(fig, ks)
    return fig


def secondary_chart(eng: str, r: dict, ks: list[int], text: bool) -> go.Figure:
    """Plot one engine's secondary-knob settings next to its library default, per k.

    Two bar panels with one bar per setting (the default first, then each secondary setting):
    quality (left) and mean latency (right). Categories on x, so settings with equal quality never
    overlap.

    Args:
        eng: Engine.
        r: Its tuning result.
        ks: k values to offer.
        text: True for a text dataset.

    Returns:
        The figure; the largest k opens.
    """
    q = "nDCG@10 (human labels)" if text else "recall@k (vs exact search)"
    fig = make_subplots(rows=1, cols=2, horizontal_spacing=0.12)
    color = trace_style(eng)["line"]["color"]
    for k in ks:
        rows = [
            row
            for row in r["rows"]
            if row["k"] == k and (row["knob"] == "secondary" or not row["params"])
        ]
        names = [setting(r, row["params"]) for row in rows]
        common = {
            "meta": k,
            "visible": k == ks[-1],
            "showlegend": False,
            "marker": {"color": color},
        }
        fig.add_trace(
            go.Bar(
                x=names,
                y=[row["quality"] for row in rows],
                text=[f"{row['quality']:.4g}" for row in rows],
                textposition="outside",
                cliponaxis=False,
                name=f"{eng} quality",
                hovertemplate=f"<b>%{{x}}</b> k={k}<br>quality %{{y:.4f}}<extra></extra>",
                **common,
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Bar(
                x=names,
                y=[row["latency_ms"]["mean"] for row in rows],
                text=[f"{row['latency_ms']['mean']:.4g}" for row in rows],
                textposition="outside",
                cliponaxis=False,
                name=f"{eng} mean latency",
                hovertemplate=f"<b>%{{x}}</b> k={k}<br>mean %{{y:.3f}} ms<extra></extra>",
                **common,
            ),
            row=1,
            col=2,
        )
    lat = [y for t in fig.data[1::2] for y in t.y]
    fig = layout(
        fig,
        "setting",
        {"yaxis.title.text": f"{q} (higher is better)", "yaxis.range": [0, 1.05]},
        height=420,
    )
    fig.update_layout(
        xaxis2_title="setting",
        yaxis2_title="mean latency, ms (lower is better)",
        yaxis2_range=[0, 1.05 * max(lat)],
    )
    if len(ks) > 1:
        k_menu(fig, ks)
    return fig


def fastest(r: dict, k: int, target: float) -> dict | None:
    """A run's fastest row (mean latency) at k whose quality reaches a target, any knob.

    The library default ({}) wins when it reaches the target within 5% of the fastest row's
    latency, so a tuned setting that only beats it by noise is not shown as needed tuning.

    Args:
        r: Result (tuning or defaults).
        k: k.
        target: Minimum quality.

    Returns:
        The row, or None when no setting reaches the target.
    """
    ok = [row for row in r["rows"] if row["k"] == k and row["quality"] >= target]
    best = min(ok, key=lambda row: row["latency_ms"]["mean"], default=None)
    dflt = next((row for row in ok if not row.get("params")), None)
    if dflt and dflt["latency_ms"]["mean"] <= 1.05 * best["latency_ms"]["mean"]:
        return dflt
    return best


def section(
    ds: str, metric: str, tun: dict[str, dict], exact: dict[str, dict], missing: list[str]
) -> Section:
    """Build one dataset and metric view.

    Args:
        ds: Dataset.
        metric: Metric view.
        tun: Engine -> tuning result.
        exact: Engine -> defaults result of exact engines.
        missing: DNF lines of the tuning runs of this view.

    Returns:
        The section.
    """
    title = f"{ds} · metric: {METRIC_VIEWS[metric]}"
    if not tun:
        s = Section(
            ds,
            metric,
            title,
            "No tuning run of this view has finished." if missing else "No runs in this view.",
        )
        if missing:
            s.add_table("Did not finish", ["engine and reason"], [[m] for m in missing])
        return s
    r0 = next(iter(tun.values()))
    text = r0["dataset"]["kind"] == "text"
    intro = (
        f"{r0['dataset'].get('source', ds)}: {r0['dataset']['n_base']:,} documents, {r0['dataset']['n_queries']:,} "
        "queries. " + TEXT_INTRO
        if text
        else f"{r0['dataset']['n_base']:,} docs, {r0['dataset']['n_queries']:,} queries."
    )
    intro += (
        " Each tunable engine was measured at every setting of its search knob (HNSW ef from 16 to 1024, LanceDB IVF-PQ "
        "refine_factor, Moss alpha on text datasets); exact engines have one setting and come from the default-settings "
        "runs. Each benchmark builds its own index, and the Chroma, DuckDB-VSS, LanceDB and zvec builds are not reproducible "
        "(identical runs gave slightly different recall), so their default setting here can differ slightly from the "
        "default-settings page."
    )
    if missing:
        intro += f" Did not finish: {', '.join(m.split(':')[0] for m in missing)}."
    s = Section(ds, metric, title, intro)
    ks = [10] if text else sorted({row["k"] for r in tun.values() for row in r["rows"]})
    allr = {**tun, **exact}
    if not text:
        views = {f"recall@{k} ≥ {t}": (k, t) for k in reversed(ks) for t in TARGETS}
        names = sorted(allr)
        best = {v: [fastest(allr[e], k, t) for e in names] for v, (k, t) in views.items()}
        s.card(
            "Latency at equal recall",
            "fastest setting of each engine reaching the recall target (dropdown) · mean latency",
            "For each recall target, the mean latency of the fastest setting of each engine that reaches it: "
            "approximate engines tuned up to the target (any knob), exact engines at their one setting. Public "
            "benchmarks compare speed this way (Qdrant, VIBE, big-ann). recall@k ≥ 0.95 means the engine "
            "returned, on average over the queries, at least 95% of the true k nearest documents. The bar label "
            "names the setting; the library default is shown when it reaches the target within 5% of the "
            "fastest setting. An engine without a bar never reached the target. Dropdown: recall@k target.",
            bars(
                {
                    f"mean latency at {v}, ms (lower is better)": [
                        row and row["latency_ms"]["mean"] for row in best[v]
                    ]
                    for v in views
                },
                names,
                text={
                    f"mean latency at {v}, ms (lower is better)": [
                        ("exact" if e in exact else setting(allr[e], row.get("params", {})))
                        if row
                        else "not reached"
                        for e, row in zip(names, best[v])
                    ]
                    for v in views
                },
            ),
        )
    mean = {
        (e, row["k"]): row["latency_ms"]["mean"]
        for e, r in exact.items()
        for row in r["rows"]
        if row["k"] in ks
    }
    close = sorted(
        {
            f"{a} and {b}"
            for (a, k), x in mean.items()
            for (b, kk), y in mean.items()
            if a < b and k == kk and abs(x - y) < 0.1 * min(x, y)
        }
    )
    hidden = (
        f" The lines of {', '.join(close)} are within 10% in latency, so one can hide the other (hover or click "
        "the legend to tell them apart)."
        if close
        else ""
    )
    s.card(
        "nDCG@10 vs latency" if text else "Recall vs latency",
        "each engine's best settings (Pareto frontier) · mean latency · "
        + ("k = 10" if text else "k from the dropdown"),
        "For each engine, only its best settings of its primary search knob: those that no other setting of the same "
        "engine beats on both quality and mean latency (Pareto frontier, as in ann-benchmarks). A setting that is "
        "slower without being better is left out. An exact engine has one setting: a dotted horizontal line at its "
        "latency, ending at its point, so another engine's settings below the line are faster than it."
        + hidden
        + " "
        + ("" if text else "Settings with ef below k are not run at that k. ")
        + "Every measured setting is in the table below.",
        frontier_chart(tun, exact, ks, text),
    )
    for eng, r in sorted(tun.items()):
        if any(row["knob"] == "secondary" for row in r["rows"]):
            knob = sorted(
                {k for row in r["rows"] if row["knob"] == "secondary" for k in row["params"]}
            )
            s.card(
                f"{eng}: {', '.join(knob)} against its default",
                f"{eng} only · library default and each {', '.join(knob)} setting · mean latency · "
                + ("k = 10" if text else "k from the dropdown"),
                f"{eng}'s secondary search knob ({', '.join(knob)}), each setting at the default of the primary knob, "
                "next to the library default: quality (left) and mean latency (right), one bar per setting. Shown "
                "apart from the Pareto chart so each engine's main knob stays readable.",
                secondary_chart(eng, r, ks, text),
            )
    qcol = "nDCG@10" if text else "recall@k"
    s.add_table(
        "Every measured setting",
        ["engine", "metric", "knob", "setting", "k", qcol, *(f"{st} ms" for st in LATENCY)],
        [
            [
                e,
                r["metric"],
                row.get("knob", "exact"),
                setting(r, row.get("params", {})),
                str(row["k"]),
                f"{row['quality']:.4f}",
                *(f"{row['latency_ms'][key]:.3f}" for key in LATENCY.values()),
            ]
            for e, r in sorted(allr.items())
            for row in r["rows"]
            if not text or row["k"] == 10
        ],
    )
    if not text:
        s.add_table(
            "Equal recall (fastest setting reaching each recall@k target)",
            ["engine", "k", "target", "setting", "recall@k", "mean ms"],
            [
                [
                    e,
                    str(k),
                    str(t),
                    ("exact" if e in exact else setting(allr[e], row.get("params", {})))
                    if row
                    else "not reached",
                    f"{row['quality']:.4f}" if row else "-",
                    f"{row['latency_ms']['mean']:.3f}" if row else "-",
                ]
                for k in ks
                for t in TARGETS
                for e in sorted(allr)
                for row in [fastest(allr[e], k, t)]
            ],
        )
    if missing:
        s.add_table("Did not finish", ["engine and reason"], [[m] for m in missing])
    return s


def main() -> None:
    """Write results/tuning.html and .md from results/tuning/ and exact engines' defaults runs.

    Raises:
        SystemExit: STALE tuning or defaults runs (see report_common.check_stale).
    """
    tun_all, dft_all = load("tuning"), load("defaults")
    dnfs = check_stale("tuning", tun_all)
    check_stale("defaults", dft_all)
    sections, shown = [], []
    for ds in sorted(set(tun_all) | {d for d, _, _ in dnfs}):
        for metric in METRIC_VIEWS:
            tun = view(tun_all.get(ds, {}), metric)
            exact = {
                k: r
                for k, r in view(dft_all.get(ds, {}), metric).items()
                if "-docs" not in k and r.get("tunable") is False
            }
            sections.append(section(ds, metric, tun, exact, dnf_view(dnfs, ds, metric)))
            shown += [*tun.values(), *exact.values()]
    write_page(
        "tuning",
        "Tuning: quality vs latency",
        "What each engine reaches when its search settings are tuned: speed at equal recall, and each engine's best "
        "quality-latency trade-off.",
        ["metric", "quality", "latency"],
        sections,
        shown,
    )


if __name__ == "__main__":
    main()
