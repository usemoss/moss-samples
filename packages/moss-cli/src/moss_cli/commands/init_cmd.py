"""moss init — interactive credential setup."""

from __future__ import annotations

import asyncio

import typer
from moss import MossClient
from rich.console import Console
from rich.prompt import Prompt

from ..config import (
    get_config_path,
    get_profile_credentials,
    get_selected_profile,
    set_profile_credentials,
)

console = Console()


def init_command(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", help="Overwrite existing config"),
    profile: str | None = typer.Option(
        None, "--profile", help="Profile name to save credentials under"
    ),
) -> None:
    """Save project credentials to ~/.moss/config.json."""
    path = get_config_path()
    selected_profile = profile or ctx.obj.get("profile") or get_selected_profile()

    existing_pid, _ = get_profile_credentials(selected_profile)
    if path.exists() and existing_pid and not force:
        console.print(f"[yellow]Config already exists at {path}[/yellow]")
        console.print(
            f"  Profile '{selected_profile}' Project ID: {existing_pid[:8]}..."
        )
        overwrite = Prompt.ask("Overwrite?", choices=["y", "n"], default="n")
        if overwrite != "y":
            raise typer.Abort()

    project_id = Prompt.ask("Project ID")
    project_key = Prompt.ask("Project Key", password=True)

    if not project_id or not project_key:
        console.print("[red]Both project ID and key are required.[/red]")
        raise typer.Exit(1)

    # Test credentials
    console.print("[dim]Validating credentials...[/dim]")
    try:
        client = MossClient(project_id, project_key)
        indexes = asyncio.run(client.list_indexes())
        console.print(f"[green]Authenticated. Found {len(indexes)} index(es).[/green]")
    except Exception as e:
        console.print(f"[red]Authentication failed: {e}[/red]")
        save_anyway = Prompt.ask("Save anyway?", choices=["y", "n"], default="n")
        if save_anyway != "y":
            raise typer.Exit(1)

    set_profile_credentials(selected_profile, project_id, project_key)
    console.print(
        f"[green]Config saved to {path}[/green] (profile: [cyan]{selected_profile}[/cyan])"
    )
