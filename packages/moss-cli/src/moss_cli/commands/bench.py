"""moss bench command — measure retrieval latency percentiles."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import typer
from moss import MossClient, QueryOptions
from rich.console import Console
from rich.table import Table

from .. import output
from ..completion import complete_index_name
from ..config import resolve_credentials

console = Console()


def _percentile(sorted_ms: list[float], p: float) -> float:
    """Return the p-th percentile (0–100) of a sorted list using linear interpolation."""
    if not sorted_ms:
        return 0.0
    n = len(sorted_ms)
    idx = (p / 100) * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    return sorted_ms[lo] + (idx - lo) * (sorted_ms[hi] - sorted_ms[lo])


def bench_command(
    ctx: typer.Context,
    index_name: str = typer.Argument(
        ..., help="Index name to benchmark", autocompletion=complete_index_name
    ),
    queries: list[str] | None = typer.Option(  # noqa: B008
        None, "--query", "-q", help="Query string (repeatable)"
    ),
    queries_file: Path | None = typer.Option(  # noqa: B008
        None, "--queries-file", "-f", help="File with one query per line"
    ),
    runs: int = typer.Option(20, "--runs", "-n", help="Number of timed runs per query"),
    top_k: int = typer.Option(10, "--top-k", "-k", help="Number of results per query"),
    alpha: float = typer.Option(
        0.8, "--alpha", "-a", help="Semantic weight (0.0=keyword, 1.0=semantic)"
    ),
    warmup: int = typer.Option(
        3, "--warmup", help="Number of warmup runs before timing (discarded)"
    ),
    cloud: bool = typer.Option(False, "--cloud", "-c", help="Query via cloud API"),
    profile: str | None = typer.Option(
        None, "--profile", help="Credential profile name"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Benchmark retrieval latency and report p50/p95/p99 percentiles."""
    json_mode = json_output or ctx.obj.get("json_output", False)
    if profile:
        ctx.obj["profile"] = profile

    all_queries: list[str] = list(queries or [])
    if queries_file:
        try:
            lines = queries_file.read_text().splitlines()
            all_queries.extend(ln.strip() for ln in lines if ln.strip())
        except OSError as e:
            output.print_error(f"Cannot read queries file: {e}", json_mode)
            raise typer.Exit(1)

    if not all_queries:
        output.print_error(
            "No queries provided. Use --query or --queries-file.", json_mode
        )
        raise typer.Exit(1)

    if runs < 1:
        output.print_error("--runs must be >= 1.", json_mode)
        raise typer.Exit(1)

    if warmup < 0:
        output.print_error("--warmup must be >= 0.", json_mode)
        raise typer.Exit(1)

    pid, pkey = resolve_credentials(
        ctx.obj.get("project_id"), ctx.obj.get("project_key"), ctx.obj.get("profile")
    )

    client = MossClient(pid, pkey)

    async def _run() -> None:
        if not cloud:
            if not json_mode:
                console.print(f"Loading index [cyan]{index_name}[/cyan] locally...")
            await client.load_index(index_name)

        options = QueryOptions(top_k=top_k) if cloud else QueryOptions(top_k=top_k, alpha=alpha)

        if not json_mode:
            q_word = "query" if len(all_queries) == 1 else "queries"
            console.print(
                f"Running [bold]{warmup * len(all_queries)}[/bold] warmup + "
                f"[bold]{runs * len(all_queries)}[/bold] timed iterations "
                f"across [bold]{len(all_queries)}[/bold] {q_word}..."
            )

        for q in all_queries:
            for _ in range(warmup):
                await client.query(index_name, q, options)

        # Store latencies by input position so repeated queries are each tracked separately,
        # preserving weighted-workload semantics.
        per_query: list[tuple[str, list[float]]] = [(q, []) for q in all_queries]
        for q, latencies in per_query:
            for _ in range(runs):
                t0 = time.perf_counter()
                await client.query(index_name, q, options)
                latencies.append((time.perf_counter() - t0) * 1000)

        all_latencies: list[float] = []
        query_stats = []
        for q, latencies in per_query:
            s = sorted(latencies)
            all_latencies.extend(s)
            query_stats.append(
                {
                    "query": q,
                    "runs": len(latencies),
                    "p50_ms": _percentile(s, 50),
                    "p95_ms": _percentile(s, 95),
                    "p99_ms": _percentile(s, 99),
                    "min_ms": s[0],
                    "max_ms": s[-1],
                }
            )

        overall_sorted = sorted(all_latencies)
        overall = {
            "p50_ms": _percentile(overall_sorted, 50),
            "p95_ms": _percentile(overall_sorted, 95),
            "p99_ms": _percentile(overall_sorted, 99),
            "min_ms": overall_sorted[0],
            "max_ms": overall_sorted[-1],
            "total_runs": len(overall_sorted),
        }

        if json_mode:
            print(
                json.dumps(
                    {"index": index_name, "queries": query_stats, "overall": overall},
                    indent=2,
                )
            )
            return

        if len(query_stats) > 1:
            table = Table(title=f"Benchmark — {index_name}")
            table.add_column("Query", max_width=40)
            table.add_column("p50 (ms)", justify="right")
            table.add_column("p95 (ms)", justify="right")
            table.add_column("p99 (ms)", justify="right")
            table.add_column("min (ms)", justify="right")
            table.add_column("max (ms)", justify="right")
            for qs in query_stats:
                table.add_row(
                    qs["query"][:40],
                    f"{qs['p50_ms']:.2f}",
                    f"{qs['p95_ms']:.2f}",
                    f"{qs['p99_ms']:.2f}",
                    f"{qs['min_ms']:.2f}",
                    f"{qs['max_ms']:.2f}",
                )
            console.print(table)

        console.print(f"\n[bold]Overall ({overall['total_runs']} runs)[/bold]")
        console.print(f"  p50: [cyan]{overall['p50_ms']:.2f} ms[/cyan]")
        console.print(f"  p95: [cyan]{overall['p95_ms']:.2f} ms[/cyan]")
        console.print(f"  p99: [cyan]{overall['p99_ms']:.2f} ms[/cyan]")
        console.print(
            f"  min: {overall['min_ms']:.2f} ms  max: {overall['max_ms']:.2f} ms"
        )

    asyncio.run(_run())
