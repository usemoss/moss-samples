#!/bin/zsh
# Run one suite for engines x datasets, one watchdogged process per pair; then rebuild the reports.
# usage: ./run_suite.sh <suite> "<datasets>" "<engines>|all" [options...]
#   suites: defaults (suite_defaults.py), tuning (suite_tuning.py), filter (suite_filter.py)
#   e.g. ./run_suite.sh defaults cohere-100k all --queries 200 --metric ip
# Each run gets one stamp: log results/logs/<suite>-<dataset>-<engine>[-ip][-docs<N>]-<stamp>.log,
# result results/<suite>/<dataset>/<engine>[-ip][-docs<N>]-<stamp>.json. A pair that does not apply
# (harness.applies: no ip mode, exact engine for tuning, no filter cases, --docs outside defaults)
# is skipped with its reason. A killed or failed run appears as DNF in its report.
# Moss runs need MOSS_ENV_FILE (or MOSS_PROJECT_ID/KEY). Long runs: raise WATCHDOG_MAX_S (default 1200).
# Stop (the loop first): pkill -9 -f run_suite.sh; pkill -9 -f 'benchmarks/local/\.venv/bin/python'
set -u
cd ${0:A:h}
suite=$1
[[ -f suite_$suite.py ]] || { echo "unknown suite $suite (defaults, tuning, filter)"; exit 1; }
datasets=(${=2})
engines=(${=3})
[[ $3 == all ]] && engines=(moss chroma lancedb lancedb-hnsw qdrant-local faiss-flat faiss-hnsw zvec sqlite-vec duckdb-vss)
shift 3
(( ${@[(I)--docs=*]} + ${@[(I)--metric=*]} )) && { echo 'write --docs N / --metric ip, not --flag=value'; exit 1; }  # the log name needs them
# Moss is always benchmarked at its newest release: refresh the lock before any Moss run (the runner also
# refuses to run Moss unless the installed version equals the latest on PyPI). Commit uv.lock when it changes.
if (( ${engines[(Ie)moss]} )); then
  uv lock --upgrade-package moss && uv sync || { echo "could not update moss"; exit 1; }
fi
mkdir -p results/logs
metric=default; i=${@[(I)--metric]}; (( i )) && metric=${@[i+1]}
docs=""; i=${@[(I)--docs]}; (( i )) && docs=${@[i+1]}
# --docs N: exact ground truth over the first N docs, computed once per dataset in its own process
# (computing it inside the benchmark inflated the memory baseline); the runner refuses --docs without it.
if [[ -n $docs ]]; then
  for d in $datasets; do
    [[ -f data/$d/gt_docs$docs.npy && ! data/$d/base.npy -nt data/$d/gt_docs$docs.npy ]] && continue
    ./watchdog.sh results/logs/subset-gt-$d-$docs-$(date +%Y%m%dT%H%M%S).log \
      $PWD/.venv/bin/python bench_data.py subset-gt $d $docs || { echo "subset-gt $d $docs failed"; exit 1; }
  done
fi
for d in $datasets; do
  for e in $engines; do
    why=$($PWD/.venv/bin/python -c 'import sys; from harness import applies; print(applies(*sys.argv[1:5], int(sys.argv[5]) if sys.argv[5] else None))' \
      $suite $d $e $metric "$docs") || { echo "could not check $suite $d $e"; exit 1; }
    [[ -n $why ]] && { echo "skip $suite $d $e: $why"; continue; }
    key=$e; [[ $metric == ip ]] && key=$key-ip; [[ -n $docs ]] && key=$key-docs$docs
    stamp=$(date +%Y%m%dT%H%M%S); log=results/logs/$suite-$d-$key-$stamp.log
    # The watchdog wraps the python process itself (not `uv run`) so its RSS cap measures the benchmark; the
    # absolute interpreter path lets the stop pattern 'benchmarks/local/\.venv/bin/python' match.
    ./watchdog.sh $log $PWD/.venv/bin/python suite_$suite.py $d $e --stamp $stamp "$@" || echo "DNF $suite $d $key ($log)"
  done
done
# NO_REPORT=1 skips the page rebuild (a driver running many pairs builds the pages once at the end)
[[ ${NO_REPORT:-0} == 1 ]] || $PWD/.venv/bin/python report.py
