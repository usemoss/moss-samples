#!/usr/bin/env python3
"""Run all benchmarks and produce a comparison table.

Usage:
    python run_all.py                 # run all
    python run_all.py moss qdrant     # run specific benchmarks
"""

import sys
import time
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

BENCHMARKS = {
    "moss": ("Moss", "bench_moss"),
    "pinecone": ("Pinecone", "bench_pinecone"),
    "qdrant": ("Qdrant", "bench_qdrant"),
    "chroma": ("ChromaDB", "bench_chroma"),
}


def main():
    targets = sys.argv[1:] or list(BENCHMARKS.keys())

    # Validate targets
    for t in targets:
        if t not in BENCHMARKS:
            print(f"Unknown benchmark: {t}")
            print(f"Available: {', '.join(BENCHMARKS.keys())}")
            sys.exit(1)

    print("=" * 70)
    print("  Benchmark Suite")
    print(f"  Date: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"  Running: {', '.join(targets)}")
    print("=" * 70)

    results = {}

    for key in targets:
        name, module_name = BENCHMARKS[key]

        print(f"\n{'#' * 70}")
        print(f"# {name}")
        print(f"{'#' * 70}\n")

        try:
            module = __import__(module_name)
            start = time.time()
            result = module.run()
            elapsed = time.time() - start
            results[key] = result
            print(f"\n  [{name}] completed in {elapsed:.1f}s")
        except Exception as e:
            print(f"\n  [{name}] FAILED: {e}")
            import traceback

            traceback.print_exc()

    # --- Comparison table ---
    if len(results) > 1:
        print(f"\n{'=' * 70}")
        print("  Comparison Table")
        print(f"{'=' * 70}")
        print(
            f"\n  {'System':<20} {'P50':>10} {'P95':>10} {'P99':>10} {'Mean':>10}"
        )
        print(
            f"  {'------':<20} {'---':>10} {'---':>10} {'---':>10} {'----':>10}"
        )
        for key in targets:
            if key in results:
                r = results[key]
                name = BENCHMARKS[key][0]
                print(
                    f"  {name:<20} {r.p50:>8.1f}ms {r.p95:>8.1f}ms "
                    f"{r.p99:>8.1f}ms {r.mean:>8.1f}ms"
                )

    print(f"\n{'=' * 70}")
    print("  All benchmarks completed.")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
