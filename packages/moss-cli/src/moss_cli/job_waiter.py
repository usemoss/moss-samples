"""Poll job status with a rich progress bar."""

from __future__ import annotations

import asyncio
import json
import sys
import time

from moss import MossClient
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from . import output

console = Console()


def _status_str(status_obj: object) -> str:
    raw = status_obj.status.value if hasattr(status_obj.status, "value") else str(status_obj.status)
    return raw.upper()


def _progress_float(status_obj: object) -> float:
    p = float(status_obj.progress)
    return p / 100.0 if p > 1 else p


def _timeout_exit(job_id: str, timeout: float, json_mode: bool) -> None:
    msg = f"Timed out after {timeout:.0f}s waiting for job {job_id}"
    if json_mode:
        print(json.dumps({"error": msg}), file=sys.stderr)
    else:
        console.print(f"[red]{msg}[/red]")
    raise SystemExit(1)


async def wait_for_job(
    client: MossClient,
    job_id: str,
    poll_interval: float = 2.0,
    json_mode: bool = False,
    timeout: float | None = None,
) -> None:
    """Poll job status until terminal state, showing progress."""
    terminal = {"COMPLETED", "FAILED"}
    deadline = time.monotonic() + timeout if timeout is not None else None

    if json_mode:
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                _timeout_exit(job_id, timeout, json_mode)
            status = await client.get_job_status(job_id)
            status_val = _status_str(status)
            if status_val in terminal:
                output.print_job_status(status, json_mode=True)
                if status_val == "FAILED":
                    raise SystemExit(1)
                return
            await asyncio.sleep(poll_interval)

    with Live(Spinner("dots", text="Waiting for job..."), console=console, transient=True) as live:
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                _timeout_exit(job_id, timeout, json_mode)
            status = await client.get_job_status(job_id)
            status_val = _status_str(status)

            phase = getattr(status, "current_phase", None)
            phase_str = ""
            if phase is not None:
                phase_str = f" ({phase.value if hasattr(phase, 'value') else str(phase)})"

            timeout_str = ""
            if deadline is not None:
                remaining = max(0.0, deadline - time.monotonic())
                timeout_str = f" [dim](timeout in {remaining:.0f}s)[/dim]"

            progress_pct = f"{_progress_float(status):.0%}"
            text = Text.from_markup(
                f"[yellow]{status_val}[/yellow] {progress_pct}{phase_str}{timeout_str}"
            )
            live.update(Spinner("dots", text=text))

            if status_val in terminal:
                break
            await asyncio.sleep(poll_interval)

    output.print_job_status(status, json_mode=False)
    if status_val == "FAILED":
        raise SystemExit(1)
