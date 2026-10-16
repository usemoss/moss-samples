"""moss completions command — output shell completion scripts."""

from __future__ import annotations

import importlib
from enum import Enum
from typing import Callable, Optional

import typer

from .. import output

PROG_NAME = "moss"
_UNAVAILABLE = "Shell completion is unavailable in this Typer installation."
# Where `get_completion_script` has lived across Typer releases, most public first.
_COMPLETION_SCRIPT_MODULES = (
    "typer.main",
    "typer.completion",
    "typer._completion_shared",
)


def _resolve_get_completion_script() -> Optional[Callable[..., str]]:
    """Return Typer's ``get_completion_script`` from the first module that exposes it."""
    for module_name in _COMPLETION_SCRIPT_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        get_completion_script = getattr(module, "get_completion_script", None)
        if get_completion_script is not None:
            return get_completion_script
    return None


class Shell(str, Enum):
    bash = "bash"
    zsh = "zsh"


def completions_command(
    ctx: typer.Context,
    shell: Shell = typer.Argument(
        ..., help="Shell to generate the completion script for."
    ),
) -> None:
    """Output a shell completion script for Bash or Zsh.

    Tab-completion covers commands, subcommands, global flags, and index names.

    Bash:

        moss completions bash >> ~/.bashrc

    Zsh:

        moss completions zsh >> ~/.zshrc

    Then restart your shell (or 'source' the file) to activate it.
    """
    json_mode = ctx.obj.get("json_output", False) if ctx.obj else False

    get_completion_script = _resolve_get_completion_script()
    if get_completion_script is None:
        output.print_error(_UNAVAILABLE, json_mode)
        raise typer.Exit(1)

    complete_var = "_{}_COMPLETE".format(PROG_NAME.replace("-", "_").upper())
    script = get_completion_script(
        prog_name=PROG_NAME, complete_var=complete_var, shell=shell.value
    )
    # Emit the raw script with no Rich markup so it can be piped or redirected
    # to a file verbatim.
    typer.echo(script)
