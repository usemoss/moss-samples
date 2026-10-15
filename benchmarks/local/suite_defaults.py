"""Default-settings suite: build, memory, latency and quality at the library-default settings.

usage: ./run_suite.sh defaults <dataset> <engine> [--metric ip] [--queries N] [--docs N] [--k ...]

The engine is built (harness.build: open_s, build_s, docs/s, memory baseline, after-build footprint,
build peak, disk) and left at its library-default index and search settings: no set_search() call.
After 100 unmeasured warm-up queries, one pass over the measured queries per k in --k: latency
(mean, p50, p95, p99, p99.9) and quality (recall@k / nDCG@k vs exact top-k, or nDCG@10, recall@k
and R-precision vs human labels on text datasets). The search-stage footprint peak covers those
passes. Text datasets keep the top 5 of the first 10 queries, from an unmeasured pass at k = 10, as
example results. --docs runs feed the scaling report.
"""

import json

from harness import Run, cli, footprint_mb, measure_pass, reset_peak, timed, warm_up


async def measure(run: Run) -> dict:
    """Measure every k at the library-default search setting.

    Args:
        run: The built engine and dataset (see harness.Run).

    Returns:
        {"rows": one measure_pass() row per k} plus, on text datasets, "examples".
    """
    await warm_up(run, min(run.ks))
    reset_peak()
    rows = []
    for k in run.ks:
        rows.append(await measure_pass(run, k))
        print(json.dumps(rows[-1]), flush=True)
    run.memory["peak_footprint_mb"]["search"] = footprint_mb()[1]
    out: dict = {"rows": rows}
    if run.text:  # top 5 of the first 10 queries; corpus position = id
        ex, _ = await timed(run.eng, run.qs[:10], 10)
        out["examples"] = [
            {
                "query": q["text"],
                "results": [
                    {
                        "text": run.d["corpus"][i]["text"][:240],
                        "relevant": str(i) in run.d["qrels"][q["id"]],
                    }
                    for i in g[:5]
                ],
            }
            for q, g in zip(run.d["queries_text"][:10], ex)
        ]
    return out


if __name__ == "__main__":
    cli("defaults", __doc__, measure, docs=True)
