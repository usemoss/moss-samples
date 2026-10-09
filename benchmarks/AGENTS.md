# Agent rules for `benchmarks/`

Standard vector-search benchmark (Moss vs local engines). Methodology, commands and facts are in [README.md](README.md).

- **Confirm before heavy jobs.** Every 1M-scale prepare or run, and the full suite, needs explicit user confirmation each time (earlier approval does not carry over).
- **Smoke-test on `cohere-100k` first.**
- **Never `uv run` a benchmark.** Run engines with `./run_suite.sh ...` (also for one pair: it names the log and result with one shared stamp) and fetch / prepare with `./watchdog.sh results/logs/<step>-<name>-<stamp>.log $PWD/.venv/bin/python ...` from `benchmarks/` (absolute interpreter) so the watchdog sees python's RSS and the escape hatch matches.
- **Escape hatch:** `pkill -9 -f run_suite.sh; pkill -9 -f 'benchmarks/\.venv/bin/python'` (the loop first). It kills every benchmark python: run `pgrep -fl 'benchmarks/\.venv/bin/python'` first and do not kill jobs you did not start.
- **Never read `.env` files.** Pass credentials with `MOSS_ENV_FILE=/path/to/.env` (or `MOSS_PROJECT_ID` / `MOSS_PROJECT_KEY`).
- **Moss runs consume metered session minutes**, and every run rebuilds the index. Never push Moss sessions.
- **Report numbers only from `results/`** (`results/summary.md`, `results/*/*.json`).
- **`report.py` exit 1 with `STALE` lines** means a rerun failed while an older result exists. Read the log and tell the user; never move or delete results to get past it without the user's OK.
- **Latest Moss only.** `run_suite.sh` upgrades `moss`; commit `uv.lock` after an upgrade.
- **Lint:**
  - `uvx ruff@0.15.22 check benchmarks`
  - `uvx ruff@0.15.22 check --select D100,D101,D102,D103,D104,D105,D106,D107 benchmarks`
- Every module, class and function (nested helpers too) keeps a docstring. No committed tests.
