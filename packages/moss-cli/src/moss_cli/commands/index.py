"""moss index {create, list, get, delete} commands."""

from __future__ import annotations

import asyncio

import typer
from moss import MossClient
from rich.console import Console

from .. import output
from ..completion import complete_index_name
from ..config import resolve_credentials
from ..documents import load_documents
from ..job_waiter import wait_for_job

console = Console()
index_app = typer.Typer(name="index", help="Manage indexes")


def _client(ctx: typer.Context) -> MossClient:
    pid, pkey = resolve_credentials(
        ctx.obj.get("project_id"), ctx.obj.get("project_key"), ctx.obj.get("profile")
    )
    return MossClient(pid, pkey)


@index_app.command(name="create")
def create(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Index name"),
    file: str = typer.Option(..., "--file", "-f", help="Path to JSON/CSV document file, or '-' for stdin"),
    model: str | None = typer.Option(None, "--model", "-m", help="Model ID (default: moss-minilm)"),
    profile: str | None = typer.Option(
        None, "--profile", help="Credential profile name"
    ),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for job to complete"),
    poll_interval: float = typer.Option(2.0, "--poll-interval", help="Seconds between status checks"),
    timeout: float | None = typer.Option(None, "--timeout", help="Max seconds to wait (requires --wait)"),
) -> None:
    """Create a new index with documents."""
    json_mode = ctx.obj.get("json_output", False)
    if profile:
        ctx.obj["profile"] = profile
    client = _client(ctx)
    docs = load_documents(file)

    if not json_mode:
        console.print(f"Creating index [cyan]{name}[/cyan] with {len(docs)} document(s)...")

    result = asyncio.run(client.create_index(name, docs, model))
    output.print_mutation_result(result, json_mode=json_mode)

    if wait:
        asyncio.run(wait_for_job(client, result.job_id, poll_interval, json_mode, timeout))


@index_app.command(name="list")
def list_indexes(
    ctx: typer.Context,
    profile: str | None = typer.Option(
        None, "--profile", help="Credential profile name"
    ),
) -> None:
    """List all indexes."""
    json_mode = ctx.obj.get("json_output", False)
    if profile:
        ctx.obj["profile"] = profile
    client = _client(ctx)
    indexes = asyncio.run(client.list_indexes())
    output.print_index_table(indexes, json_mode=json_mode)


@index_app.command(name="get")
def get(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Index name", autocompletion=complete_index_name),
    profile: str | None = typer.Option(
        None, "--profile", help="Credential profile name"
    ),
) -> None:
    """Get details of an index."""
    json_mode = ctx.obj.get("json_output", False)
    if profile:
        ctx.obj["profile"] = profile
    client = _client(ctx)
    info = asyncio.run(client.get_index(name))
    output.print_index_detail(info, json_mode=json_mode)


@index_app.command(name="delete")
def delete(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Index name", autocompletion=complete_index_name),
    profile: str | None = typer.Option(
        None, "--profile", help="Credential profile name"
    ),
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Skip confirmation"),
) -> None:
    """Delete an index."""
    json_mode = ctx.obj.get("json_output", False)
    if profile:
        ctx.obj["profile"] = profile
    if not confirm and not json_mode:
        typer.confirm(f"Delete index '{name}'?", abort=True)

    client = _client(ctx)
    result = asyncio.run(client.delete_index(name))

    if result:
        output.print_success(f"Index '{name}' deleted.", json_mode=json_mode)
    else:
        output.print_error(f"Failed to delete index '{name}'.", json_mode=json_mode)
        raise typer.Exit(1)
