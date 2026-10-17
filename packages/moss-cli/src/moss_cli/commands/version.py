"""moss version command."""

from __future__ import annotations

import typer
from rich.console import Console

console = Console()


def version_command(ctx: typer.Context) -> None:
    """Print CLI and SDK version information."""
    import moss

    import moss_cli

    json_mode = ctx.obj.get("json_output", False)

    if json_mode:
        import json

        print(json.dumps({"cli": moss_cli.__version__, "sdk": moss.__version__}))
    else:
        console.print(f"moss-cli  {moss_cli.__version__}")
        console.print(f"moss SDK  {moss.__version__}")
