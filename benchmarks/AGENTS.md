# Agent rules for `benchmarks/`

Standard vector-search benchmark (Moss vs local engines). Methodology, commands and facts are in [README.md](README.md).

- **Confirm before heavy jobs.** Every 1M-scale prepare or run, and the full suite, needs explicit user confirmation each time (earlier approval does not carry over).
- **Smoke-test on `cohere-100k` first.**
- **Never `uv run` a benchmark.** Use `./run_suite.sh ...` or `./watchdog.sh <log> .venv/bin/python ...` so the watchdog sees python's RSS.
- **Escape hatch, in order:** `pkill -9 -f run_suite.sh` (stops the loop), then `pkill -9 -f '\.venv/bin/python (run|bench_data|report)\.py'`
- **Never read `.env` files.** Pass credentials with `MOSS_ENV_FILE=/path/to/.env` (or `MOSS_PROJECT_ID` / `MOSS_PROJECT_KEY`).
- **Moss runs consume metered session minutes**, and every run rebuilds the index. Never push Moss sessions.
- **Report numbers only from `results/`** (`results/summary.md`, `results/*/*.json`).
- **Latest Moss only.** `run_suite.sh` upgrades `moss`; commit `uv.lock` after an upgrade.
- **Lint:**
  - `uvx ruff@0.15.22 check benchmarks`
  - `uvx ruff@0.15.22 check --select D100,D101,D102,D103,D104,D105,D106,D107 benchmarks`
- Every module, class and function (nested helpers too) keeps a docstring. No committed tests.
