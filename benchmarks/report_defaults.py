"""Default-settings report: results/defaults.html and results/defaults.md.

Reads only results/defaults/ (full-corpus runs; --docs runs belong to report_scaling.py). Per
dataset and metric view: latency and quality at the library-default settings (one k for every
engine: 10 on text datasets, the depth nDCG@10 scores, else the largest k every run measured), index
build time (text datasets stack the corpus-embedding time on the non-Moss engines, which index
vectors embedded at prepare), memory; tables for every k, build and memory, example results (text)
and DNFs.

usage: $PWD/.venv/bin/python report_defaults.py   (report.py runs it with the other pages)
"""

import html
import math

import plotly.graph_objects as go

from report_common import (
    LATENCY,
    METRIC_VIEWS,
    TEXT_INTRO,
    Section,
    bars,
    check_stale,
    dnf_view,
    layout,
    load,
    mem_gb,
    menu,
    short,
    trace_style,
    write_page,
    yaxes,
)

SUITE = "defaults"


def chart_k(runs: dict[str, dict], text: bool) -> int | None:
    """The one k every chart uses: 10 on text datasets, else the largest k every run measured.

    Args:
        runs: Run key -> result.
        text: True for a text dataset.

    Returns:
        The k, or None when the runs share none (or a text run lacks k = 10).
    """
    common = set.intersection(*({row["k"] for row in r["rows"]} for r in runs.values()))
    return (10 if 10 in common else None) if text else max(common, default=None)


def embed_s(r: dict) -> float:
    """Corpus-embedding seconds measured at prepare, for a non-Moss run on a text dataset (else 0).

    Args:
        r: Result document.

    Returns:
        The dataset's corpus_embed_s for non-Moss text runs; 0.0 for Moss (it embeds inside its
        build) and vector datasets.
    """
    if r["dataset"]["kind"] != "text" or r["engine"] == "moss":
        return 0.0
    return r["dataset"]["corpus_embed_s"]


def build_chart(runs: dict[str, dict], text: bool) -> go.Figure:
    """Plot index build time (and docs/s) per engine; text datasets stack the corpus embedding.

    Args:
        runs: Run key -> result.
        text: True for a text dataset.

    Returns:
        The figure.
    """
    names = list(runs)
    idx = [r["load"]["build_s"] for r in runs.values()]
    if not text:
        return bars(
            {
                "build time, s (lower is better)": idx,
                "docs indexed per second (higher is better)": [
                    r["load"]["docs_per_s"] for r in runs.values()
                ],
            },
            names,
        )
    emb = [embed_s(r) for r in runs.values()]
    docs = [r["load"]["docs"] for r in runs.values()]
    views = {
        "build time incl. corpus embedding, s (lower is better)": (idx, emb),
        "docs per second incl. corpus embedding (higher is better)": (
            [n / (a + b) for n, a, b in zip(docs, idx, emb)],
            [0.0] * len(idx),
        ),
    }
    ax = yaxes({v: [a + b for a, b in zip(*ys)] for v, ys in views.items()})
    first = next(iter(views))
    hover = "<b>%{x}</b><br>%{fullData.name}: %{y:.3f}<extra></extra>"
    fig = go.Figure(
        [
            go.Bar(
                name="index build (engine color; Moss: embedding + index with its built-in model)",
                x=names,
                y=views[first][0],
                text=[f"{a:.4g}" for a in views[first][0]],
                textposition="inside",
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
                text=[f"total {a + b:.4g}" for a, b in zip(*views[first])],
                textposition="outside",
                cliponaxis=False,
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
                    {
                        "label": short(v),
                        "method": "update",
                        "args": [
                            {
                                "y": [a, b],
                                "text": [
                                    [f"{x:.4g}" for x in a],
                                    [f"total {x + y:.4g}" for x, y in zip(a, b)],
                                ],
                            },
                            ax[v],
                        ],
                    }
                    for v, (a, b) in views.items()
                ]
            )
        ],
    )
    fig = layout(fig, "engine", ax[first])
    fig.update_layout(legend={"orientation": "h", "y": -0.25, "title": {"text": ""}})
    return fig


def section(ds: str, metric: str, runs: dict[str, dict], missing: list[str]) -> Section:
    """Build one dataset and metric view: charts, then tables.

    Args:
        ds: Dataset.
        metric: Metric view.
        runs: Run key -> result of this view (full corpus).
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
            "No run of this view has finished." if missing else "No runs in this view.",
        )
        if missing:
            s.add_table("Did not finish", ["engine and reason"], [[m] for m in missing])
        return s
    r0 = next(iter(runs.values()))
    text = r0["dataset"]["kind"] == "text"
    n = sorted({row["latency_ms"]["n"] for r in runs.values() for row in r["rows"]})
    queries = f"{n[0]:,}" if len(n) == 1 else f"{n[0]:,} to {n[-1]:,} (differs by engine)"
    intro = (
        f"{r0['dataset'].get('source', ds)}: {r0['dataset']['n_base']:,} documents, {queries} queries. "
        + TEXT_INTRO
        if text
        else f"{r0['dataset']['n_base']:,} docs, {queries} queries. Every engine uses its library's default "
        "index and search settings."
    )
    if missing:
        intro += f" Did not finish: {', '.join(m.split(':')[0] for m in missing)}."
    s = Section(ds, metric, title, intro)
    k = chart_k(runs, text)
    if k is None:
        s.add_html("<p>The runs share no k, so there are no charts; see the tables.</p>")
    else:
        at = {e: next(row for row in r["rows"] if row["k"] == k) for e, r in runs.items()}
        s.card(
            "Latency at default settings",
            f"library-default index and search settings · k = {k} for every engine",
            "One bar per engine: its search latency with the library's default index and search settings, one "
            "query at a time over all queries. Dropdown: latency statistic.",
            bars(
                {
                    f"{st} latency, ms (lower is better)": [at[e]["latency_ms"][key] for e in runs]
                    for st, key in LATENCY.items()
                },
                list(runs),
            ),
        )
        q = "nDCG@10 (human labels)" if text else f"recall@{k} (vs exact search)"
        s.card(
            "Quality at default settings",
            f"library-default index and search settings · k = {k} for every engine",
            (
                "nDCG@10 of each engine's results against the human relevance labels (see the intro)."
                if text
                else f"Share of the true {k} nearest documents (exact search) each engine returns in its top {k}, "
                "averaged over the queries; exact engines score 1.0 (just under when the ground truth has "
                "near-ties at rank k)."
            ),
            bars({f"{q} (higher is better)": [at[e]["quality"] for e in runs]}, list(runs)),
        )
    s.card(
        "Index build time",
        ("corpus embedding + ingest + index" if text else "ingest + index from vectors")
        + " · client and Moss session setup excluded",
        (
            "Moss embeds the corpus inside its build with its built-in model; the other engines index vectors "
            "embedded once at prepare (fastembed, batch 256), and that embedding time is stacked on their bars, "
            "so every bar covers embedding + indexing. Dropdown: measure."
            if text
            else "Time to build each engine's index (ingest + index), or the docs indexed per second. Dropdown: "
            "measure."
        ),
        build_chart(runs, text),
    )
    mem = {e: mem_gb(r) for e, r in runs.items()}
    s.card(
        "Memory",
        "process footprint over the footprint after loading the dataset · on disk = index files",
        "Memory each engine adds, in GB: index (after build), build peak, search peak (during the measured "
        "passes), RSS increase over the build, and index files on disk (disk-backed engines keep part of "
        "their index in OS-cached files, which the footprint does not count). Dropdown: measure.",
        bars(
            {
                f"{m}, GB (lower is better)": [mem[e][m] for e in runs]
                for m in mem[next(iter(runs))]
            },
            list(runs),
        ),
    )
    qcols = (
        ["nDCG@10", "R-precision", "recall@k (human labels)"] if text else ["recall@k", "nDCG@k"]
    )
    s.add_table(
        "Default settings, every k",
        ["engine", "metric", "k", *qcols, *(f"{st} ms" for st in LATENCY)],
        [
            [
                e,
                r["metric"],
                str(row["k"]),
                *qcells(row, text),
                *(f"{row['latency_ms'][key]:.3f}" for key in LATENCY.values()),
            ]
            for e, r in runs.items()
            for row in r["rows"]
        ],
    )
    s.add_table(
        "Build and memory",
        [
            "engine",
            "metric",
            "session open s",
            "build s",
            *(["corpus embed s"] if text else []),
            "docs/s",
            "baseline footprint GB",
            "index GB",
            "build peak GB",
            "search peak GB",
            "RSS increase over build GB",
            "on disk GB",
            "process peak RSS GB",
        ],
        [
            [
                e,
                r["metric"],
                f"{r['load']['open_s']:.2f}",
                f"{r['load']['build_s']:.2f}",
                *([f"{embed_s(r):.1f}" if r["engine"] != "moss" else "in build"] if text else []),
                f"{r['load']['docs_per_s']:.0f}",
                f"{r['memory']['baseline_footprint_mb'] / 1024:.2f}",
                *(f"{mem[e][m]:.2f}" if not math.isnan(mem[e][m]) else "-" for m in mem[e]),
                f"{r['load']['peak_rss_mb'] / 1024:.2f}",
            ]
            for e, r in runs.items()
        ],
    )
    if text:
        s.add_html(examples(runs))
    if missing:
        s.add_table("Did not finish", ["engine and reason"], [[m] for m in missing])
    return s


def qcells(row: dict, text: bool) -> list[str]:
    """Format a row's quality cells for the every-k table.

    Args:
        row: Result row (one k).
        text: True for a text dataset.

    Returns:
        nDCG@10, R-precision and recall@k (text) or recall@k and nDCG@k (vector), 4 decimals.
    """
    k = row["k"]
    keys = ["ndcg@10", "r_precision", f"recall@{k}"] if text else [f"recall@{k}", f"ndcg@{k}"]
    return [f"{row[x]:.4f}" for x in keys]


def examples(runs: dict[str, dict]) -> str:
    """Render each engine's example results as HTML (text datasets).

    One collapsed block per query (the first 10) lists each engine's top 5 at k = 10; ✓ marks a
    result labelled relevant in the dataset.

    Args:
        runs: Run key -> result.

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


def main() -> None:
    """Write results/defaults.html and .md from results/defaults/ (full-corpus runs).

    Raises:
        SystemExit: STALE runs (see report_common.check_stale).
    """
    from report_common import view

    runs = load(SUITE)
    dnfs = check_stale(SUITE, runs)
    sections, shown = [], []
    for ds in sorted(set(runs) | {d for d, _, _ in dnfs}):
        for metric in METRIC_VIEWS:
            v = {k: r for k, r in view(runs.get(ds, {}), metric).items() if "-docs" not in k}
            missing = [m for m in dnf_view(dnfs, ds, metric) if "-docs" not in m.split(":")[0]]
            sections.append(section(ds, metric, v, missing))
            shown += v.values()
    write_page(
        "defaults",
        "Default settings",
        "Each engine with its library's default index and search settings, as a user gets it without tuning: "
        "latency, quality, index build time and memory.",
        ["metric", "quality", "latency"],
        sections,
        shown,
    )


if __name__ == "__main__":
    main()
