"""Turn results/<dataset>/*.json into results/report.html (interactive Plotly charts + tables) and results/summary.md.

usage: uv run python report.py        then open results/report.html in a browser (works offline; plotly.js is inlined)

Per dataset, using each engine's newest full run (``-docs`` subset runs get their own section):
  charts  precision vs speed (Pareto frontier per engine; dropdowns: speed metric = QPS / p50 / p95 / p99 / p99.9 /
          mean, and k), concurrency ladder (QPS, and latency with a metric dropdown), latency at the operating point,
          build cost (dropdown: build time / docs per s / peak RSS), filtered search (dropdown: recall / latency / QPS)
  tables  operating point, full serial sweep, concurrency ladder, filter cases, engines that did not finish (DNF)
Every chart: hover shows exact values and parameters; click a legend entry to hide an engine, double-click to isolate it.
Text datasets use nDCG@10 where vector datasets use recall@k.
"""

import html
import json
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
PATTERNS = [
    "",
    "/",
    ".",
    "x",
    "-",
]  # texture tells series apart inside an engine's bar group
LATENCY = {"p50": "p50", "p95": "p95", "p99": "p99", "p99.9": "p999", "mean": "mean"}


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


def metric_of(r: dict) -> str:
    """Name of the headline precision: nDCG@10 for text datasets, recall@k for vector datasets."""
    return "nDCG@10" if r["dataset"]["kind"] == "text" else "recall@k"


def at_op(r: dict) -> list[dict]:
    """Serial rows measured at the run's operating point (one per k)."""
    return [row for row in r["serial"] if row["params"] == r["operating_point"]]


def frontier(
    points: list[tuple[float, float, str]], higher_is_better: bool
) -> list[tuple[float, float, str]]:
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


def layout(fig: go.Figure, title: str, x: str, y: str, ylog: bool = False) -> go.Figure:
    """Shared layout: recessive grid, legend on the right (click to hide, double-click to isolate)."""
    fig.update_layout(
        template="plotly_white", paper_bgcolor="#fcfcfb", plot_bgcolor="#fcfcfb",
        title={"text": title, "x": 0, "y": 0.975, "yanchor": "top"},  # above the dropdown row
        height=540,
        hovermode="closest",
        legend={"title": {"text": "click / double-click"}},
        margin={"t": 130, "r": 20},
        xaxis_title=x,
        yaxis_title=y,
        yaxis_type="log" if ylog else "linear",
        yaxis_dtick="D2" if ylog else None,  # log ticks at 1-2-5 only
        font={"family": "system-ui, sans-serif", "size": 13},
    )
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
    """Precision vs speed, one Pareto line per (engine, k); dropdowns pick the speed metric and k."""
    speeds = {"serial QPS": ("qps", True)} | {
        f"{lbl} latency, ms": (key, False) for lbl, key in LATENCY.items()
    }
    ks = sorted({row["k"] for r in runs.values() for row in r["serial"]})
    fig, data = go.Figure(), {s: [] for s in speeds}
    for eng, r in runs.items():
        for k in ks:
            rows = [row for row in r["serial"] if row["k"] == k]
            for s, (key, higher) in speeds.items():
                pts = [
                    (
                        row["precision"],
                        row["qps"] if key == "qps" else row["latency_ms"][key],
                        json.dumps(row["params"]) if row["params"] else "exact",
                    )
                    for row in rows
                ]
                data[s].append(frontier(pts, higher) if pts else [])
            first = data["serial QPS"][-1]
            fig.add_trace(
                go.Scatter(
                    x=[p[0] for p in first],
                    y=[p[1] for p in first],
                    customdata=[[p[2]] for p in first],
                    name=eng,
                    legendgroup=eng,
                    showlegend=k == ks[-1],
                    visible=k == ks[-1],
                    mode="lines+markers",
                    meta=k,
                    hovertemplate=f"<b>{eng}</b> k={k}<br>%{{customdata[0]}}<br>precision %{{x:.4f}}"
                    "<br>%{y:.3f}<extra></extra>",
                    **trace_style(eng),
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
                    "customdata": [[[p[2]] for p in t] for t in data[s]],
                },
                {"yaxis.title.text": f"{s} ({'higher' if hi else 'lower'} is better)"},
            ],
        }
        for s, (_, hi) in speeds.items()
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
        "serial QPS (higher is better)",
        ylog=True,
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
                            {"yaxis.title.text": f"{lbl} latency, ms"},
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
            "QPS",
            True,
        ),
        layout(
            lat,
            f"{name}: latency vs concurrent clients (operating point)",
            "concurrent clients",
            "p99 latency, ms",
            True,
        ),
    ]


def grouped_bars(
    fig: go.Figure, engines: list[str], series: dict[str, list[float]], fmt: str
) -> None:
    """Grouped bars: x = engine (engine hue), one bar per series told apart by texture; hover shows the value."""
    for j, (lab, vals) in enumerate(series.items()):
        fig.add_trace(
            go.Bar(
                x=engines,
                y=vals,
                name=lab,
                marker={
                    "color": [trace_style(e)["line"]["color"] for e in engines],
                    "pattern": {"shape": PATTERNS[j % len(PATTERNS)]},
                    "line": {"color": "#fcfcfb", "width": 2},
                },
                hovertemplate=f"<b>%{{x}}</b><br>{lab}: %{{y:{fmt}}}<extra></extra>",
            )
        )
    fig.update_layout(barmode="group")


def latency_bars(name: str, runs: dict[str, dict]) -> go.Figure:
    """Serial latency percentiles at the operating point (largest k) per engine; legend keys series by texture."""
    rows = {e: max(at_op(r), key=lambda row: row["k"]) for e, r in runs.items()}
    fig = go.Figure()
    grouped_bars(
        fig,
        list(rows),
        {
            lbl: [rows[e]["latency_ms"][key] for e in rows]
            for lbl, key in LATENCY.items()
        },
        ".3f",
    )
    fig = layout(
        fig,
        f"{name}: serial latency at the operating point",
        "engine",
        "latency, ms",
        True,
    )
    fig.update_layout(legend={"title": {"text": "percentile (texture)"}})
    return fig


def build_bars(name: str, runs: dict[str, dict]) -> go.Figure:
    """Index build cost per engine; dropdown: build seconds, docs per second, peak RSS."""
    engines = list(runs)
    views = {
        "build time, s": [runs[e]["load"]["build_s"] for e in engines],
        "docs per second": [runs[e]["load"]["docs_per_s"] for e in engines],
        "peak RSS, GB": [runs[e]["load"]["peak_rss_mb"] / 1024 for e in engines],
    }
    fig = go.Figure()
    grouped_bars(fig, engines, {"build time, s": views["build time, s"]}, ".2f")
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
                            {"yaxis.title.text": v},
                        ],
                    }
                    for v, vals in views.items()
                ],
                0,
            )
        ]
    )
    fig = layout(fig, f"{name}: index build", "engine", "build time, s", True)
    fig.update_layout(showlegend=False)
    return fig


def filter_bars(name: str, runs: dict[str, dict]) -> go.Figure | None:
    """Filtered search per engine and filter case; dropdown: recall@100, p50 / p99 latency, QPS."""
    runs = {e: r for e, r in runs.items() if r["filter"]}
    if not runs:
        return None
    engines, tags = (
        list(runs),
        [f["filter"] for f in next(iter(runs.values()))["filter"]],
    )
    by = {e: {f["filter"]: f for f in r["filter"]} for e, r in runs.items()}
    views = {
        "recall@100": ("recall@100", None),
        "p50 latency, ms": ("latency_ms", "p50"),
        "p99 latency, ms": ("latency_ms", "p99"),
        "QPS": ("qps", None),
    }

    def val(f: dict, view: tuple[str, str | None]) -> float:
        """One filter row's value for a dropdown view."""
        return f[view[0]][view[1]] if view[1] else f[view[0]]

    fig = go.Figure()
    grouped_bars(
        fig,
        engines,
        {t: [by[e][t]["recall@100"] for e in engines] for t in tags},
        ".4f",
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
                                "y": [
                                    [val(by[e][t], view) for e in engines] for t in tags
                                ]
                            },
                            {
                                "yaxis.title.text": v,
                                "yaxis.type": "linear"
                                if v.startswith("recall")
                                else "log",
                            },
                        ],
                    }
                    for v, view in views.items()
                ],
                0,
            )
        ]
    )
    fig = layout(
        fig,
        f"{name}: filtered search (VectorDBBench int / label cases)",
        "engine",
        "recall@100",
    )
    fig.update_layout(legend={"title": {"text": "filter case (texture)"}})
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


def dnf(name: str, runs: dict[str, dict]) -> list[str]:
    """Engines with a log in results/logs/<dataset>-<engine>.log but no result file, with the log's last line."""
    out = []
    for log in sorted((RESULTS / "logs").glob(f"{name}-*.log")):
        eng = log.stem[len(name) + 1 :]
        if eng not in runs:
            lines = log.read_text().strip().splitlines() or ["(empty log)"]
            out.append(f"{eng}: DNF, {lines[-1][:160]}")
    return out


def section(name: str, runs: dict[str, dict]) -> tuple[list[str], list]:
    """Markdown lines and an ordered list of HTML fragments / figures for one dataset."""
    r0 = next(iter(runs.values()))
    intro = (
        f"{r0['dataset']['n_base']:,} docs, {r0['dataset'].get('n_queries')} queries. Operating point = fastest "
        "sweep setting with precision >= target recall (text datasets: most accurate setting)."
    )
    md, parts = (
        [f"## {name}", "", intro, ""],
        [f"<h2>{html.escape(name)}</h2><p>{html.escape(intro)}</p>"],
    )
    parts += [
        tradeoff(name, runs),
        *ladder(name, runs),
        latency_bars(name, runs),
        build_bars(name, runs),
    ]
    fb = filter_bars(name, runs)
    parts += [fb] if fb else []

    def add(title: str, head: list[str], rows: list[list[str]]) -> None:
        """Append one table to both outputs."""
        m, h = table(head, rows)
        md.extend(["", f"### {title}", "", *m])
        parts.append(f"<h3>{html.escape(title)}</h3>{h}")

    op = []
    for e, r in runs.items():
        best = max(r["concurrent"], key=lambda c: c["qps"], default=None)
        for row in at_op(r):
            lat = row["latency_ms"]
            op.append(
                [
                    e,
                    json.dumps(row["params"]) if row["params"] else "exact",
                    str(row["k"]),
                    f"{row['precision']:.4f}",
                    f"{lat['p50']:.3f}",
                    f"{lat['p95']:.3f}",
                    f"{lat['p99']:.3f}",
                    f"{lat['mean']:.3f}",
                    f"{row['qps']:.0f}",
                    f"{best['qps']:.0f} @ {best['level']}" if best else "-",
                    f"{r['load']['build_s']:.1f}",
                    f"{r['load']['peak_rss_mb'] / 1024:.2f}",
                ]
            )
    add(
        "Operating point",
        [
            "engine",
            "params",
            "k",
            metric_of(r0),
            "p50 ms",
            "p95 ms",
            "p99 ms",
            "mean ms",
            "serial QPS",
            "max QPS @ clients",
            "build s",
            "peak RSS GB",
        ],
        op,
    )
    add(
        "Full serial sweep",
        ["engine", "params", "k", metric_of(r0), "p50 ms", "p99 ms", "mean ms", "QPS"],
        [
            [
                e,
                json.dumps(row["params"]) if row["params"] else "exact",
                str(row["k"]),
                f"{row['precision']:.4f}",
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
            f"{f['recall@100']:.4f}",
            f"{f['latency_ms']['p50']:.3f}",
            f"{f['latency_ms']['p99']:.3f}",
            f"{f['qps']:.0f}",
        ]
        for e, r in runs.items()
        for f in r["filter"]
    ]
    if filt:
        add(
            "Filtered search (k=100)",
            ["engine", "filter", "recall@100", "p50 ms", "p99 ms", "QPS"],
            filt,
        )
    missing = [] if name.endswith("-subsets") else dnf(name, runs)
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
    for name in sorted(runs):
        groups = {
            name: {e: r for e, r in runs[name].items() if "-docs" not in e},
            f"{name}-subsets": {e: r for e, r in runs[name].items() if "-docs" in e},
        }
        for title, group in groups.items():
            if group:
                m, p = section(title, group)
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
    dark = json.dumps({light: dark for light, dark, _, _ in STYLE.values()} | {"#fcfcfb": "#1a1a19"})
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
