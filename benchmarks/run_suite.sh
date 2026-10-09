#!/bin/zsh
# Run engines x datasets, one process per pair, each under the watchdog; then rebuild the report.
# usage: ./run_suite.sh "<datasets>" "<engines>|all" [run.py options...]
#   e.g. ./run_suite.sh cohere-100k all --queries 200 --levels 1,4 --duration 3
# Each run gets one stamp: log results/logs/<dataset>-<engine>[-docs<N>]-<stamp>.log, result
# results/<dataset>/<engine>[-docs<N>]-<stamp>.json. A killed or failed run appears as DNF in results/summary.md.
# Moss runs need MOSS_ENV_FILE (or MOSS_PROJECT_ID/KEY). Long runs: raise WATCHDOG_MAX_S (seconds, default 1200).
# Stop (the loop first, or it logs a DNF and starts the next pair): pkill -9 -f run_suite.sh; pkill -9 -f 'benchmarks/\.venv/bin/python'
set -u
cd ${0:A:h}
datasets=(${=1})
engines=(${=2})
[[ $2 == all ]] && engines=(moss chroma lancedb qdrant-local faiss-flat faiss-hnsw zvec sqlite-vec duckdb-vss)
shift 2
(( ${@[(I)--docs=*]} )) && { echo 'write --docs N, not --docs=N'; exit 1; }  # the log name needs N
# Moss is always benchmarked at its newest release: refresh the lock before any Moss run (run.py also refuses
# to run Moss unless the installed version equals the latest on PyPI). Commit uv.lock when it changes.
if (( ${engines[(Ie)moss]} )); then
  uv lock --upgrade-package moss && uv sync || { echo "could not update moss"; exit 1; }
fi
mkdir -p results/logs
for d in $datasets; do
  for e in $engines; do
    key=$e; i=${@[(I)--docs]}; (( i )) && key=$e-docs${@[i+1]}
    stamp=$(date +%Y%m%dT%H%M%S); log=results/logs/$d-$key-$stamp.log
    # The watchdog wraps the python process itself (not `uv run`) so its RSS cap measures the benchmark; the absolute
    # interpreter path lets the stop pattern 'benchmarks/\.venv/bin/python' match.
    ./watchdog.sh $log $PWD/.venv/bin/python run.py $d $e --stamp $stamp "$@" || echo "DNF $d $key ($log)"
  done
done
$PWD/.venv/bin/python report.py
