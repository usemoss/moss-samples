"""
Moss SDK - Opt-In Metrics & Tracing Hooks Sample

Demonstrates how to wire user-provided telemetry sinks to Moss query operations.
Supports client-wide hooks and per-query hooks for observing:
- Query latency / timing (wall-clock duration in milliseconds)
- Query counts and success/failure status
- Result document counts and local vs. cloud execution

Required Environment Variables:
- MOSS_PROJECT_ID: Your Moss project ID
- MOSS_PROJECT_KEY: Your Moss project key
- MOSS_INDEX_NAME: Name of existing index (optional; falls back to 'support-faq')
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, List

from dotenv import load_dotenv
from moss import DocumentInfo, MossClient, QueryOptions

try:
    from moss import QueryMetrics  # type: ignore[attr-defined]
except ImportError:
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class QueryMetrics:  # type: ignore[no-redef]
        index_name: str
        query: str
        duration_ms: float
        result_count: int
        is_local: bool
        top_k: int | None = None
        alpha: float | None = None
        engine_time_ms: int | None = None
        error: Exception | None = None

        @property
        def is_success(self) -> bool:
            return self.error is None

        def as_dict(self) -> dict[str, Any]:
            return {
                "index_name": self.index_name,
                "query": self.query,
                "duration_ms": self.duration_ms,
                "result_count": self.result_count,
                "is_local": self.is_local,
                "top_k": self.top_k,
                "alpha": self.alpha,
                "engine_time_ms": self.engine_time_ms,
                "is_success": self.is_success,
                "error": str(self.error) if self.error is not None else None,
            }


load_dotenv()
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("moss.metrics.sample")


# ---------------------------------------------------------------------------
# Example Telemetry Sinks
# ---------------------------------------------------------------------------


class InMemoryMetricsCollector:
    """Example custom metrics collector (e.g. StatsD / Prometheus / Datadog)."""

    def __init__(self) -> None:
        self.total_queries: int = 0
        self.successful_queries: int = 0
        self.failed_queries: int = 0
        self.latencies_ms: List[float] = []
        self.total_docs_returned: int = 0

    def record(self, metrics: QueryMetrics) -> None:
        self.total_queries += 1
        self.latencies_ms.append(metrics.duration_ms)

        if metrics.is_success:
            self.successful_queries += 1
            self.total_docs_returned += metrics.result_count
        else:
            self.failed_queries += 1

        logger.info(
            "Metrics Sink Recorded: index=%s, latency=%.2fms, docs=%d, local=%s, status=%s",
            metrics.index_name,
            metrics.duration_ms,
            metrics.result_count,
            metrics.is_local,
            "SUCCESS" if metrics.is_success else f"ERROR({metrics.error})",
        )

    def print_summary(self) -> None:
        avg_latency = (
            sum(self.latencies_ms) / len(self.latencies_ms)
            if self.latencies_ms
            else 0.0
        )
        print("\n" + "=" * 50)
        print("Metrics Sink Summary")
        print("=" * 50)
        print(f"Total Queries:      {self.total_queries}")
        print(f"Successful:         {self.successful_queries}")
        print(f"Failed:             {self.failed_queries}")
        print(f"Avg Latency:        {avg_latency:.2f} ms")
        print(
            f"Min Latency:        {min(self.latencies_ms) if self.latencies_ms else 0.0:.2f} ms"
        )
        print(
            f"Max Latency:        {max(self.latencies_ms) if self.latencies_ms else 0.0:.2f} ms"
        )
        print(f"Total Docs Yielded: {self.total_docs_returned}")
        print("=" * 50)


async def async_tracing_span(metrics: QueryMetrics) -> None:
    """Example async tracing hook (e.g. OpenTelemetry / Jaeger span exporter)."""
    # Simulate non-blocking async export
    await asyncio.sleep(0.001)
    payload = metrics.as_dict()
    logger.info("Async Tracer Span Exported: %s", payload)


# ---------------------------------------------------------------------------
# Main Sample Flow
# ---------------------------------------------------------------------------


async def metrics_sample():
    print("=" * 50)
    print("Moss SDK - Opt-In Metrics & Tracing Hooks")
    print("=" * 50)

    project_id = os.getenv("MOSS_PROJECT_ID", "test-project")
    project_key = os.getenv("MOSS_PROJECT_KEY", "test-key")
    index_name = os.getenv("MOSS_INDEX_NAME", "metrics-sample-faq")

    collector = InMemoryMetricsCollector()

    # Initialize client with a global metrics hook and an async tracing hook
    client = MossClient(
        project_id,
        project_key,
        on_query=[collector.record, async_tracing_span],
    )

    try:
        # Create a small local dataset if needed
        docs = [
            DocumentInfo(id="1", text="Standard shipping takes 3-5 business days."),
            DocumentInfo(id="2", text="Express shipping delivers within 24 hours."),
            DocumentInfo(
                id="3", text="Returns are accepted within 30 days of purchase."
            ),
        ]
        print(f"\nCreating/loading index '{index_name}'...")
        await client.create_index(index_name, docs)
        await client.load_index(index_name)

        print("\nExecuting queries with metrics hooks enabled...")

        # Query 1: standard query (triggers global metrics and tracer hooks)
        await client.query(
            index_name,
            "how fast is expedited delivery?",
            QueryOptions(top_k=2),
        )

        # Query 2: with an additional per-query hook
        def custom_per_query_hook(m: QueryMetrics):
            logger.info("Per-query hook triggered for query='%s'", m.query)

        await client.query(
            index_name,
            "what is the return window?",
            QueryOptions(top_k=2),
            on_query=custom_per_query_hook,
        )

        # Query 3: keyword-heavy query (alpha=0.2)
        await client.query(
            index_name,
            "shipping 30 days policy",
            QueryOptions(top_k=2, alpha=0.2),
        )

    except Exception as e:
        logger.warning("Query or setup encountered error (expected if offline): %s", e)

    # Print collected metrics
    collector.print_summary()


if __name__ == "__main__":
    asyncio.run(metrics_sample())
