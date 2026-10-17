"""Main CLI entry point."""

from __future__ import annotations

import logging
from typing import Optional

import typer

from .commands.completions import completions_command
from .commands.doc import doc_app
from .commands.index import index_app
from .commands.init_cmd import init_command
from .commands.job import job_app
from .commands.profile import profile_app
from .commands.search import query_command
from .commands.sync import sync_command
from .commands.validate import validate_command
from .commands.version import version_command
from .output import print_error

app = typer.Typer(
    name="moss",
    help="Moss Semantic Search CLI",
    add_completion=True,
    no_args_is_help=True,
)

# Register subgroups
app.add_typer(index_app, name="index", help="Manage indexes")
app.add_typer(doc_app, name="doc", help="Manage documents")
app.add_typer(
    doc_app,
    name="documents",
    help="Manage documents (alias for 'doc')",
)
app.add_typer(job_app, name="job", help="Track background jobs")
app.add_typer(profile_app, name="profile", help="Manage auth profiles")

# Register top-level commands
app.command(name="query")(query_command)
app.command(name="init")(init_command)
app.command(name="version")(version_command)
app.command(name="validate")(validate_command)
app.command(name="sync")(sync_command)
app.command(name="completions")(completions_command)


@app.callback()
def main(
    ctx: typer.Context,
    project_id: Optional[str] = typer.Option(
        None, "--project-id", "-p", envvar="MOSS_PROJECT_ID", help="Project ID"
    ),
    project_key: Optional[str] = typer.Option(
        None, "--project-key", envvar="MOSS_PROJECT_KEY", help="Project key"
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        envvar="MOSS_PROFILE",
        help="Credential profile name",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output as JSON"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug logging"
    ),
) -> None:
    """Moss Semantic Search CLI."""
    ctx.ensure_object(dict)
    ctx.obj["project_id"] = project_id
    ctx.obj["project_key"] = project_key
    ctx.obj["profile"] = profile
    ctx.obj["json_output"] = json_output

    if verbose:
        logging.basicConfig(level=logging.DEBUG)


def run() -> None:
    """Entry point for the console script."""
    try:
        app()
    except (typer.Exit, typer.Abort, SystemExit):
        raise
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


if __name__ == "__main__":
    run()
