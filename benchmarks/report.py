"""Build every report page, each in its own process, then the index page results/index.html.

usage: $PWD/.venv/bin/python report.py   (run_suite.sh runs it after every suite)

Pages (one module each; a page reads only the suites it names, so one failing page cannot stop
another): report_defaults.py -> defaults.html (suite defaults), report_tuning.py -> tuning.html
(suites tuning + defaults for exact engines), report_filter.py -> filter.html (suite filter),
report_scaling.py -> scaling.html (suite defaults, --docs runs). index.html links every page and
shows whether it was built; a failed page shows its error. Exit 1 if any page failed.
"""

import html
import subprocess
import sys
from pathlib import Path

from report_common import NOTES, RESULTS

HERE = Path(__file__).parent
PAGES = {  # module -> (page, title, what it shows)
    "report_defaults": (
        "defaults",
        "Default settings",
        "latency, quality, build time and memory as each library ships",
    ),
    "report_tuning": (
        "tuning",
        "Tuning: quality vs latency",
        "speed at equal recall and each engine's best trade-off",
    ),
    "report_filter": (
        "filter",
        "Filtered search",
        "each engine's filtered search against its own unfiltered search",
    ),
    "report_scaling": (
        "scaling",
        "Scaling with corpus size",
        "quality, latency, memory and build time vs corpus size",
    ),
}


def main() -> None:
    """Run every page builder in its own process and write results/index.html and index.md.

    Raises:
        SystemExit: Exit 1 when a page builder failed (its error is on the index page).
    """
    RESULTS.mkdir(exist_ok=True)
    rows, md, failed = [], ["# Moss vector benchmark", ""], 0
    for mod, (page, title, what) in PAGES.items():
        p = subprocess.run(
            [sys.executable, str(HERE / f"{mod}.py")], capture_output=True, text=True
        )
        ok = p.returncode == 0
        failed += not ok
        err = (p.stderr or p.stdout).strip().splitlines()[-3:]
        status = "" if ok else f"<pre>{html.escape(chr(10).join(err))}</pre>"
        link = (
            f"<a href='{page}.html'>{html.escape(title)}</a>"
            if ok
            else html.escape(title) + " (not built)"
        )
        rows.append(f"<li>{link}: {html.escape(what)}{status}</li>")
        md.append(
            f"- [{title}]({page}.md): {what}"
            + ("" if ok else " (not built: " + " / ".join(err) + ")")
        )
        print(f"{mod}: {'ok' if ok else 'FAILED'}" + ("" if ok else "\n  " + "\n  ".join(err)))
    notes = "".join(f"<p>{html.escape(n)}</p>" for n in NOTES.values())
    (RESULTS / "index.html").write_text(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
        "content='width=device-width,initial-scale=1'><title>Moss vector benchmark</title><style>"
        ":root{--surface:#fcfcfb;--ink:#0b0b0b;--muted:#52514e}@media (prefers-color-scheme:dark){:root{"
        "--surface:#1a1a19;--ink:#ffffff;--muted:#c3c2b7}}body{background:var(--surface);color:var(--ink);"
        "font:15px/1.5 system-ui,sans-serif;margin:0 auto;max-width:1000px;padding:16px}p{color:var(--muted)}"
        "a{color:inherit}li{margin:6px 0}</style></head><body><h1>Moss vector benchmark</h1>"
        "<p>Moss and nine local vector-search engine setups on public datasets. Each benchmark has its own page, "
        "built from its own runs.</p><ul>" + "".join(rows) + "</ul>" + notes + "</body></html>"
    )
    (RESULTS / "index.md").write_text("\n".join(md + ["", *NOTES.values()]) + "\n")
    print(f"wrote {RESULTS / 'index.html'}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
