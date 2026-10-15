"""Filter suite: filtered search against the same engine's unfiltered search, at default settings.

usage: ./run_suite.sh filter <dataset> <engine> [--metric ip] [--queries N] [--filters ...]

For vector datasets with VectorDBBench filter cases (cohere: int_<p>p keeps ids >= p% of n,
label_<p>p keeps the docs labelled label_<p>p). The engine stays at its library-default settings.
After 100 unmeasured warm-up queries: an unfiltered pass at k = 100 (the reference, measured in the
same process), then per filter case a cold pass (first use of that filter) and a warm pass (the same
pass again), each scored against the case's own exact ground truth.
"""

import argparse
import json

from harness import Run, cli, footprint_mb, measure_pass, reset_peak, warm_up

K = 100  # VectorDBBench filter cases are scored at k = 100


async def measure(run: Run) -> dict:
    """Measure the unfiltered reference, then each filter case cold and warm.

    Args:
        run: The built engine and dataset (see harness.Run).

    Returns:
        {"unfiltered": measure_pass() row, "cases": [{"filter", "cold", "warm"}]}.

    Raises:
        SystemExit: The dataset has no filter cases, or --filters names an unknown one.
    """
    d = run.d
    tags = run.a.filters.split(",")
    if not d.get("gt_filters"):
        raise SystemExit(f"{run.a.dataset} has no filter cases")
    if bad := set(tags) - set(d["gt_filters"]):
        raise SystemExit(f"unknown --filters {sorted(bad)} for {run.a.dataset}")
    await warm_up(run, K)
    reset_peak()
    out: dict = {"unfiltered": await measure_pass(run, K), "cases": []}
    print(json.dumps(out["unfiltered"]), flush=True)
    for tag in tags:
        row: dict = {"filter": tag}
        for p in ("cold", "warm"):  # cold: first use of this filter in the process; warm: again
            row[p] = await measure_pass(run, K, d["meta"]["filters"][tag], d["gt_filters"][tag])
        out["cases"].append(row)
        print(json.dumps(row), flush=True)
    run.memory["peak_footprint_mb"]["filter"] = footprint_mb()[1]
    return out


def more(p: argparse.ArgumentParser) -> None:
    """Add --filters to the common arguments.

    Args:
        p: The runner's argument parser.
    """
    p.add_argument("--filters", default="int_1p,int_99p,label_1p,label_50p")


if __name__ == "__main__":
    cli("filter", __doc__, measure, k=str(K), more=more)
