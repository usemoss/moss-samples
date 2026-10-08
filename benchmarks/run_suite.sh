#!/bin/zsh
# Run engines x datasets, one process per pair, each under the watchdog; then rebuild the report.
# usage: ./run_suite.sh "<datasets>" "<engines>|all" [run.py options...]
#   e.g. ./run_suite.sh cohere-100k all --queries 200 --levels 1,4 --duration 3
# Logs: results/logs/<dataset>-<engine>.log; a killed or failed run appears as DNF in results/summary.md.
# Moss runs need MOSS_ENV_FILE (or MOSS_PROJECT_ID/KEY). Long runs: raise WATCHDOG_MAX_S (seconds, default 1200).
# Escape hatch: pkill -9 -f 'benchmarks/.venv/bin/python'
set -u
cd ${0:A:h}
datasets=(${=1})
engines=(${=2})
[[ $2 == all ]] && engines=(moss chroma lancedb qdrant-local faiss-flat faiss-hnsw zvec sqlite-vec duckdb-vss)
shift 2
# Moss is always benchmarked at its newest release: refresh the lock before any Moss run (run.py also refuses
# to run Moss unless the installed version equals the latest on PyPI). Commit uv.lock when it changes.
if (( ${engines[(Ie)moss]} )); then
  uv lock --upgrade-package moss && uv sync || { echo "could not update moss"; exit 1; }
fi
mkdir -p results/logs
for d in $datasets; do
  for e in $engines; do
    # The watchdog must wrap the python process itself (not `uv run`) so its RSS cap measures the benchmark.
    ./watchdog.sh results/logs/$d-$e.log .venv/bin/python run.py $d $e "$@" || echo "DNF $d $e (results/logs/$d-$e.log)"
  done
done
.venv/bin/python report.py
