# Agent rules for `benchmarks/local/`

Standard vector-search benchmark (Moss vs local engines). Methodology, commands and facts are in [README.md](README.md).

- **Confirm before heavy jobs.** Every 1M-scale prepare or run, and the full suite, needs explicit user confirmation each time (earlier approval does not carry over).
- **Smoke-test on `cohere-100k` first.**
- **Modular suites.** Each benchmark (`suite_<name>.py` runner, `report_<name>.py` page) reads and writes only its own results; shared code is `bench_data.py`, `engines.py`, `metrics.py`, `harness.py`, `report_common.py`. Change one benchmark without touching another's files; a change to shared code must be checked against every page.
- **Never `uv run` a benchmark.** Run engines with `./run_suite.sh <suite> ...` (also for one pair: it names the log and result with one shared stamp) and fetch / prepare / subset-gt with `./watchdog.sh results/logs/<step>-<name>-<stamp>.log $PWD/.venv/bin/python ...` (`run_suite.sh` runs `bench_data.py subset-gt` itself before `--docs` runs; those `subset-gt-*` logs are auxiliary, never DNF rows) from `benchmarks/local/` (absolute interpreter) so the watchdog sees python's RSS and the escape hatch matches.
- **Escape hatch:** `pkill -9 -f run_suite.sh; pkill -9 -f 'benchmarks/local/\.venv/bin/python'` (the loop first). It kills every benchmark python: run `pgrep -fl 'benchmarks/local/\.venv/bin/python'` first and do not kill jobs you did not start.
- **Never read `.env` files.** Pass credentials with `MOSS_ENV_FILE=/path/to/.env` (or `MOSS_PROJECT_ID` / `MOSS_PROJECT_KEY`).
- **Moss runs consume metered session minutes**, and every run rebuilds the index. Never push Moss sessions.
- **Report numbers only from `results/`** (`results/<page>.md`, `results/<suite>/*/*.json`).
- **A page not built because of `STALE`** (shown on `results/index.html`; `report.py` exits 1) means a rerun failed while an older result exists. Read the log and tell the user; never move or delete results to get past it without the user's OK.
- **Latest Moss only.** `run_suite.sh` upgrades `moss`; commit `uv.lock` after an upgrade.
- **Lint:**
  - `uvx ruff@0.15.22 check benchmarks/local`
  - `uvx ruff@0.15.22 check --select D100,D101,D102,D103,D104,D105,D106,D107 benchmarks/local`
- Every module, class and function (nested helpers too) keeps a docstring. No committed tests.
