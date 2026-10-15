#!/bin/zsh
# Run a command, killing it on memory pressure, RSS > WATCHDOG_MAX_RSS_GB (default 85% of RAM), or WATCHDOG_MAX_S
# seconds (default 1200). macOS only.
# usage: [WATCHDOG_MAX_S=7200] [WATCHDOG_MAX_RSS_GB=40] ./watchdog.sh <logfile> <cmd...>
# Stop: pkill -9 -f run_suite.sh; pkill -9 -f 'benchmarks/local/\.venv/bin/python'. Wrap the python process itself
# ($PWD/.venv/bin/python ... from benchmarks/local/), not `uv run`, or the RSS cap measures uv instead.
log=$1; shift
max_s=${WATCHDOG_MAX_S:-1200}
max_rss_kb=$(( ${WATCHDOG_MAX_RSS_GB:-0} * 1048576 ))
(( max_rss_kb )) || max_rss_kb=$(( $(sysctl -n hw.memsize) / 1024 * 85 / 100 ))
"$@" > "$log" 2>&1 &
pid=$!
echo "pid=$pid log=$log"
start=$SECONDS; peak=0; maxlvl=1
while kill -0 $pid 2>/dev/null; do
  lvl=$(sysctl -n kern.memorystatus_vm_pressure_level)  # 1 normal, 2 warn, 4 critical
  rss=$(ps -o rss= -p $pid 2>/dev/null | tr -d ' '); rss=${rss:-0}
  (( rss > peak )) && peak=$rss; (( lvl > maxlvl )) && maxlvl=$lvl
  if (( lvl > 1 || rss > max_rss_kb || SECONDS - start > max_s )); then
    kill -9 $pid
    echo "WATCHDOG KILLED pid=$pid: pressure_level=$lvl rss_mb=$((rss / 1024)) elapsed=$((SECONDS - start))s" | tee -a "$log"
    exit 1
  fi
  sleep 0.2
done
wait $pid; rc=$?
echo "watchdog: rc=$rc peak_rss_mb=$((peak / 1024)) max_pressure_level=$maxlvl elapsed=$((SECONDS - start))s" | tee -a "$log"
exit $rc
