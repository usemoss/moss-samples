"""moss sync — upsert documents from a directory, optionally watching for changes."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from moss import MossClient, MutationOptions
from rich.console import Console

from .. import output
from ..completion import complete_index_name
from ..config import resolve_credentials
from ..documents import load_documents
from ..job_waiter import wait_for_job

console = Console()


def _client(ctx: typer.Context) -> MossClient:
    pid, pkey = resolve_credentials(
        ctx.obj.get("project_id"), ctx.obj.get("project_key"), ctx.obj.get("profile")
    )
    return MossClient(pid, pkey)


def _scan(directory: Path, exts: set[str]) -> dict[Path, float]:
    """Return {path: mtime} for all files matching the given extensions."""
    result: dict[Path, float] = {}
    for ext in exts:
        for p in directory.glob(f"**/*.{ext}"):
            result[p] = p.stat().st_mtime
    return result


async def _upsert_file(
    client: MossClient,
    index_name: str,
    path: Path,
    json_mode: bool,
    wait: bool,
    poll_interval: float,
    timeout: float | None,
) -> None:
    try:
        docs = load_documents(str(path))
    except typer.BadParameter as e:
        output.print_error(f"{path.name}: {e}", json_mode=json_mode)
        return

    if not docs:
        return

    if not json_mode:
        console.print(f"  [cyan]{path.name}[/cyan]: upserting {len(docs)} doc(s)...")

    result = await client.add_docs(index_name, docs, MutationOptions(upsert=True))
    output.print_mutation_result(result, json_mode=json_mode)

    if wait:
        await wait_for_job(client, result.job_id, poll_interval, json_mode, timeout)


def sync_command(
    ctx: typer.Context,
    directory: Path = typer.Argument(..., help="Directory containing document files"),
    index_name: str = typer.Argument(..., help="Index to upsert documents into", autocompletion=complete_index_name),
    watch: bool = typer.Option(False, "--watch", "-w", help="Keep watching for file changes"),
    ext: str = typer.Option("json,jsonl,csv", "--ext", help="Comma-separated file extensions to include"),
    scan_interval: float = typer.Option(2.0, "--scan-interval", help="Seconds between directory scans (watch mode)"),
    wait: bool = typer.Option(False, "--wait", help="Wait for each upsert job to complete"),
    poll_interval: float = typer.Option(2.0, "--poll-interval", help="Seconds between job status checks"),
    timeout: float | None = typer.Option(None, "--timeout", help="Max seconds to wait per job (requires --wait)"),
    profile: str | None = typer.Option(None, "--profile", help="Credential profile name"),
) -> None:
    """Sync documents from a directory into an index.

    Loads all JSON/JSONL/CSV files in DIRECTORY and upserts their documents into
    INDEX_NAME. With --watch, re-upserts any file that is added or modified.
    """
    json_mode = ctx.obj.get("json_output", False)
    if profile:
        ctx.obj["profile"] = profile

    if not directory.exists() or not directory.is_dir():
        output.print_error(f"Not a directory: {directory}", json_mode=json_mode)
        raise typer.Exit(1)

    exts = {e.strip().lstrip(".") for e in ext.split(",") if e.strip()}
    client = _client(ctx)

    async def run() -> None:
        # --- initial sync ---
        file_mtimes = _scan(directory, exts)

        if not file_mtimes:
            if not json_mode:
                console.print(f"[yellow]No matching files found in {directory}[/yellow]")
            if not watch:
                return

        if not json_mode and file_mtimes:
            console.print(f"Syncing [bold]{len(file_mtimes)}[/bold] file(s) into [cyan]{index_name}[/cyan]...")

        for path in sorted(file_mtimes):
            await _upsert_file(client, index_name, path, json_mode, wait, poll_interval, timeout)

        if not watch:
            return

        if not json_mode:
            console.print(
                f"\n[green]Watching[/green] [cyan]{directory}[/cyan] — "
                f"Ctrl+C to stop."
            )

        try:
            while True:
                await asyncio.sleep(scan_interval)
                new_mtimes = _scan(directory, exts)

                changed = [
                    p for p, mtime in new_mtimes.items()
                    if p not in file_mtimes or file_mtimes[p] != mtime
                ]
                added = [p for p in new_mtimes if p not in file_mtimes]

                for path in sorted(set(changed) | set(added)):
                    label = "added" if path in added else "changed"
                    if not json_mode:
                        console.print(f"[dim]{label}:[/dim] {path.name}")
                    await _upsert_file(client, index_name, path, json_mode, wait, poll_interval, timeout)

                file_mtimes = new_mtimes

        except (KeyboardInterrupt, asyncio.CancelledError):
            if not json_mode:
                console.print("\n[yellow]Stopped.[/yellow]")

    asyncio.run(run())
