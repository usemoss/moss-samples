"""
Simple benchmark: Try create_index with different doc counts.
Tox runs this in different environments (beta2, beta3) to compare versions.
"""

import asyncio
import random
import string
import time
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from typing import List, Optional

import pytest

from moss import DocumentInfo, MossClient

from .constants import TEST_MODEL_ID, TEST_PROJECT_ID, TEST_PROJECT_KEY


# Define the structure to hold benchmark results
@dataclass
class BenchResult:
    doc_count: int
    time_ms: Optional[float]
    success: bool
    error: str = ""


# Generate dummy documents with random deterministic text of fixed length 200
def _gen_docs(n: int, seed: int = 1337) -> List[DocumentInfo]:
    """Generate n dummy documents."""
    rng = random.Random(seed)
    alphabet = string.ascii_letters + "     "
    docs = []
    for i in range(n):
        txt = "".join(rng.choices(alphabet, k=200)).strip()
        try:
            docs.append(
                DocumentInfo(id=f"doc_{i}", text=f"Document {i}. {txt}", metadata={})
            )
        except TypeError:
            docs.append(DocumentInfo(id=f"doc_{i}", text=f"Document {i}. {txt}"))
    return docs


# Try to create index and measure time taken
async def _try_create_index(
    client: MossClient, index_name: str, doc_count: int
) -> BenchResult:
    """Try to create index, return result with timing."""
    docs = _gen_docs(doc_count)

    # Cleanup before
    try:
        await client.delete_index(index_name)
    except Exception:
        pass

    t0 = time.perf_counter()
    try:
        result = client.create_index(index_name, docs, TEST_MODEL_ID)
        if asyncio.iscoroutine(result):
            success = bool(await result)
        else:
            success = bool(result)

        t1 = time.perf_counter()
        time_ms = (t1 - t0) * 1000.0

        # Cleanup after
        try:
            await client.delete_index(index_name)
        except Exception:
            pass

        return BenchResult(
            doc_count=doc_count, time_ms=time_ms, success=success, error=""
        )

    except Exception as e:
        t1 = time.perf_counter()
        time_ms = (t1 - t0) * 1000.0
        err_msg = str(e)

        # Cleanup after (best effort)
        try:
            await client.delete_index(index_name)
        except Exception:
            pass

        return BenchResult(
            doc_count=doc_count, time_ms=time_ms, success=False, error=err_msg
        )


# The main benchmark test
@pytest.mark.asyncio
async def test_create_index_versions_bench():
    """Benchmark create_index across different doc counts."""
    doc_counts = [600, 800, 1000]

    try:
        sdk_version = pkg_version("moss")
    except PackageNotFoundError:
        sdk_version = "unknown"

    client = MossClient(TEST_PROJECT_ID, TEST_PROJECT_KEY)
    results = []

    for i, n in enumerate(doc_counts, 1):
        print(
            f"Running experiment {i}/{len(doc_counts)}: create_index with {n} documents...",
            flush=True,
            end=" ",
        )
        index_name = f"createindex-bench-{sdk_version.replace('.', '_')}-{n}"
        result = await _try_create_index(client, index_name, n)
        results.append(result)

        if result.success:
            print(f"✅ {result.time_ms:.1f}ms", flush=True)
        else:
            print("❌ failed", flush=True)

    # Print table
    print("\n" + "=" * 110)
    print(" CREATE_INDEX BENCHMARK")
    print("=" * 110)
    print(
        f"{'sdk_version':<16} | {'docs':>6} | {'time_taken':>14} | {'status':<15} | notes"
    )
    print("-" * 110)

    for r in results:
        if r.success:
            time_str = f"{r.time_ms:.1f} ms" if r.time_ms else "N/A"
            print(
                f"{sdk_version:<16} | {r.doc_count:>6} | {time_str:>14} | {'✅ success':<15} |"
            )
        else:
            # Classify error
            err_lower = r.error.lower()
            if "readtimeout" in err_lower or "timeout" in err_lower:
                note = "timeout (>30s)"
            elif "413" in r.error or "payload too large" in err_lower:
                note = "not supported (payload too large)"
            else:
                note = r.error[:60] + "..." if len(r.error) > 60 else r.error

            time_str = f"{r.time_ms:.1f} ms" if r.time_ms else "N/A"
            print(
                f"{sdk_version:<16} | {r.doc_count:>6} | {time_str:>14} | {'❌ failed':<15} | {note}"
            )

    print("=" * 110 + "\n")
