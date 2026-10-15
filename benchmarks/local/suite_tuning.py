"""Tuning suite: latency and quality at every search setting an engine offers.

usage: ./run_suite.sh tuning <dataset> <engine> [--metric ip] [--queries N] [--k ...]

For engines with search settings to tune (engine.sweep with more than one setting, or engine.extra);
exact engines have a single setting and are measured by the defaults suite only. Each setting of the
primary knob (engine.sweep, e.g. HNSW ef; {} = the library default) and then of the secondary knob
(engine.extra, e.g. LanceDB-HNSW's refine_factor) is applied with set_search(), warmed up with the
100 unmeasured queries, then measured with one pass per k (settings with ef below k are skipped at
that k). Each row records its knob ("primary" or "secondary") and setting.
"""

import json

from harness import Run, cli, measure_pass, warm_up


async def measure(run: Run) -> dict:
    """Measure every setting of the primary then the secondary knob, at every k.

    Args:
        run: The built engine and dataset (see harness.Run).

    Returns:
        {"rows": measure_pass() rows with "knob" and "params" added}.

    Raises:
        SystemExit: The engine has a single search setting (exact search).
    """
    eng = run.eng
    if len(eng.sweep) < 2 and not eng.extra:
        raise SystemExit(f"{run.a.engine} has one search setting; the defaults suite measures it")
    rows = []
    for knob, settings in (("primary", eng.sweep), ("secondary", eng.extra)):
        for params in settings:
            eng.set_search(params)
            todo = [k for k in run.ks if params.get("ef", k) >= k]  # HNSW needs ef >= k
            if not todo:
                continue
            await warm_up(run, min(todo))
            for k in todo:
                rows.append({"knob": knob, "params": params} | await measure_pass(run, k))
                print(json.dumps(rows[-1]), flush=True)
    eng.set_search({})
    return {"rows": rows}


if __name__ == "__main__":
    cli("tuning", __doc__, measure)
