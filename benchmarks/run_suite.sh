#!/bin/zsh
# Run engines x datasets, one process per pair, each under the watchdog; then rebuild the report.
# usage: ./run_suite.sh "<datasets>" "<engines>|all" [run.py options...]
#   e.g. ./run_suite.sh cohere-100k all --queries 200 --metric ip
# Each run gets one stamp: log results/logs/<dataset>-<engine>[-ip][-docs<N>]-<stamp>.log, result
# results/<dataset>/<engine>[-ip][-docs<N>]-<stamp>.json. A killed or failed run appears as DNF in results/summary.md.
# Moss runs need MOSS_ENV_FILE (or MOSS_PROJECT_ID/KEY). Long runs: raise WATCHDOG_MAX_S (seconds, default 1200).
# Stop (the loop first, or it logs a DNF and starts the next pair): pkill -9 -f run_suite.sh; pkill -9 -f 'benchmarks/\.venv/bin/python'
set -u
cd ${0:A:h}
datasets=(${=1})
engines=(${=2})
[[ $2 == all ]] && engines=(moss chroma lancedb lancedb-hnsw qdrant-local faiss-flat faiss-hnsw zvec sqlite-vec duckdb-vss)
shift 2
(( ${@[(I)--docs=*]} + ${@[(I)--metric=*]} )) && { echo 'write --docs N / --metric ip, not --flag=value'; exit 1; }  # the log name needs them
# Moss is always benchmarked at its newest release: refresh the lock before any Moss run (run.py also refuses
# to run Moss unless the installed version equals the latest on PyPI). Commit uv.lock when it changes.
if (( ${engines[(Ie)moss]} )); then
  uv lock --upgrade-package moss && uv sync || { echo "could not update moss"; exit 1; }
fi
mkdir -p results/logs
# --docs N: exact ground truth over the first N docs, computed once per dataset in its own process
# (computing it inside run.py inflated the memory baseline); run.py refuses --docs without it.
i=${@[(I)--docs]}
if (( i )); then
  for d in $datasets; do
    [[ -f data/$d/gt_docs${@[i+1]}.npy && ! data/$d/base.npy -nt data/$d/gt_docs${@[i+1]}.npy ]] && continue
    ./watchdog.sh results/logs/subset-gt-$d-${@[i+1]}-$(date +%Y%m%dT%H%M%S).log \
      $PWD/.venv/bin/python bench_data.py subset-gt $d ${@[i+1]} || { echo "subset-gt $d ${@[i+1]} failed"; exit 1; }
  done
fi
# --metric ip: engines whose default metric is already inner product have no ip mode; the report reuses their default run
skip=()
i=${@[(I)--metric]}; (( i )) && [[ ${@[i+1]} == ip ]] && skip=($($PWD/.venv/bin/python -c \
  'from engines import ENGINES; print(*[n for n, f in ENGINES.items() if "ip" not in f().METRICS])'))
for d in $datasets; do
  for e in $engines; do
    (( ${skip[(Ie)$e]} )) && { echo "skip $e: its default metric is already inner product"; continue; }
    key=$e; i=${@[(I)--metric]}; (( i )) && [[ ${@[i+1]} == ip ]] && key=$key-ip
    i=${@[(I)--docs]}; (( i )) && key=$key-docs${@[i+1]}
    stamp=$(date +%Y%m%dT%H%M%S); log=results/logs/$d-$key-$stamp.log
    # The watchdog wraps the python process itself (not `uv run`) so its RSS cap measures the benchmark; the absolute
    # interpreter path lets the stop pattern 'benchmarks/\.venv/bin/python' match.
    ./watchdog.sh $log $PWD/.venv/bin/python run.py $d $e --stamp $stamp "$@" || echo "DNF $d $key ($log)"
  done
done
$PWD/.venv/bin/python report.py
