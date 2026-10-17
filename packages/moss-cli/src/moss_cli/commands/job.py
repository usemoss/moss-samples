"""moss job status command."""

from __future__ import annotations

import asyncio

import typer
from moss import MossClient

from .. import output
from ..config import resolve_credentials
from ..job_waiter import wait_for_job

job_app = typer.Typer(name="job", help="Track background jobs")


def _client(ctx: typer.Context) -> MossClient:
    pid, pkey = resolve_credentials(
        ctx.obj.get("project_id"), ctx.obj.get("project_key"), ctx.obj.get("profile")
    )
    return MossClient(pid, pkey)


@job_app.command(name="status")
def status(
    ctx: typer.Context,
    job_id: str = typer.Argument(..., help="Job ID"),
    profile: str | None = typer.Option(
        None, "--profile", help="Credential profile name"
    ),
    wait: bool = typer.Option(False, "--wait", "-w", help="Poll until job completes"),
    poll_interval: float = typer.Option(2.0, "--poll-interval", help="Seconds between status checks"),
) -> None:
    """Get the status of a background job."""
    json_mode = ctx.obj.get("json_output", False)
    if profile:
        ctx.obj["profile"] = profile
    client = _client(ctx)

    if wait:
        asyncio.run(wait_for_job(client, job_id, poll_interval, json_mode))
    else:
        result = asyncio.run(client.get_job_status(job_id))
        output.print_job_status(result, json_mode=json_mode)
