"""Timing and statistics utilities for benchmarks."""

import math
import statistics
import time


class Timer:
    """Context manager that records wall-clock time in milliseconds."""

    def __init__(self):
        self.elapsed_ms: float = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_):
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000


class BenchmarkResult:
    """Collects latency measurements and computes summary statistics."""

    def __init__(self, name: str, latencies_ms: list[float]):
        self.name = name
        self.latencies_ms = sorted(latencies_ms)
        self.count = len(latencies_ms)

    @property
    def mean(self) -> float:
        return statistics.mean(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def stdev(self) -> float:
        return (
            statistics.stdev(self.latencies_ms)
            if len(self.latencies_ms) >= 2
            else 0.0
        )

    @property
    def p50(self) -> float:
        return self._percentile(0.50)

    @property
    def p95(self) -> float:
        return self._percentile(0.95)

    @property
    def p99(self) -> float:
        return self._percentile(0.99)

    def _percentile(self, p: float) -> float:
        if not self.latencies_ms:
            return 0.0
        idx = max(int(math.ceil(p * self.count)) - 1, 0)
        return self.latencies_ms[idx]

    def summary(self) -> str:
        return (
            f"  {self.name}\n"
            f"    iterations : {self.count}\n"
            f"    mean       : {self.mean:.3f} ms\n"
            f"    stdev      : {self.stdev:.3f} ms\n"
            f"    P50        : {self.p50:.3f} ms\n"
            f"    P95        : {self.p95:.3f} ms\n"
            f"    P99        : {self.p99:.3f} ms"
        )
