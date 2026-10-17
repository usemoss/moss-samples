"""moss query command."""

from __future__ import annotations

import asyncio
import json
import sys

import typer
from moss import MossClient, QueryOptions
from rich.console import Console

from .. import output
from ..completion import complete_index_name
from ..config import resolve_credentials

console = Console()


def _parse_set_command(line: str) -> tuple[str | None, str | None]:
    parts = line.strip().split()
    if len(parts) != 3 or parts[0] != "/set":
        return None, "Usage: /set <alpha|top-k> <value>"

    key = parts[1].lower()
    if key not in {"alpha", "top-k", "topk"}:
        return None, "Unknown setting. Supported: alpha, top-k"

    if key == "alpha":
        try:
            alpha = float(parts[2])
        except ValueError:
            return None, "Invalid alpha. Must be a number between 0.0 and 1.0."
        if not 0.0 <= alpha <= 1.0:
            return None, "Invalid alpha. Must be between 0.0 and 1.0."
        return f"alpha={alpha}", None

    try:
        top_k = int(parts[2])
    except ValueError:
        return None, "Invalid top-k. Must be a positive integer."
    if top_k < 1:
        return None, "Invalid top-k. Must be >= 1."
    return f"top_k={top_k}", None


def query_command(
    ctx: typer.Context,
    index_name: str = typer.Argument(..., help="Index name", autocompletion=complete_index_name),
    query_text: str | None = typer.Argument(None, help="Search query (reads from stdin if omitted)"),
    profile: str | None = typer.Option(
        None, "--profile", help="Credential profile name"
    ),
    top_k: int = typer.Option(10, "--top-k", "-k", help="Number of results"),
    alpha: float = typer.Option(0.8, "--alpha", "-a", help="Semantic weight (0.0=keyword, 1.0=semantic)"),
    filter_json: str | None = typer.Option(None, "--filter", help="Metadata filter as JSON string"),
    cloud: bool = typer.Option(False, "--cloud", "-c", help="Query via cloud API instead of downloading the index"),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Start interactive query session for multiple queries against one loaded index",
    ),
) -> None:
    """Query an index. Downloads the index and queries on-device by default. Use --cloud to skip the download and query via the cloud API."""
    json_mode = ctx.obj.get("json_output", False)
    if profile:
        ctx.obj["profile"] = profile

    # Resolve query text from stdin when piped.
    # In interactive mode this becomes the initial query before entering the prompt loop.
    if query_text is None and not sys.stdin.isatty():
        piped_query = sys.stdin.read().strip()
        if piped_query:
            query_text = piped_query
        elif not interactive:
            output.print_error("Empty query from stdin.", json_mode)
            raise typer.Exit(1)

    # Non-interactive mode still requires either arg query or piped stdin input.
    if not interactive and query_text is None:
        output.print_error("No query provided. Pass as argument or pipe via stdin.", json_mode)
        raise typer.Exit(1)

    # Parse filter
    parsed_filter = None
    if filter_json:
        try:
            parsed_filter = json.loads(filter_json)
        except json.JSONDecodeError as e:
            output.print_error(f"Invalid --filter JSON: {e}", json_mode)
            raise typer.Exit(1)

    pid, pkey = resolve_credentials(
        ctx.obj.get("project_id"), ctx.obj.get("project_key"), ctx.obj.get("profile")
    )
    if cloud and parsed_filter:
        output.print_error(
            "Metadata filters are only supported for local queries. Remove --cloud or --filter.",
            json_mode,
        )
        raise typer.Exit(1)
    if interactive and json_mode:
        output.print_error(
            "Interactive mode is not supported with --json. Remove --interactive or --json.",
            json_mode,
        )
        raise typer.Exit(1)
    if interactive and cloud:
        output.print_error(
            "Interactive mode currently supports local queries only. Remove --cloud.",
            json_mode,
        )
        raise typer.Exit(1)

    client = MossClient(pid, pkey)

    async def _run() -> None:
        if not cloud:
            if not json_mode:
                console.print(f"Loading index [cyan]{index_name}[/cyan] locally...")
            await client.load_index(index_name)

        if interactive:
            current_top_k = top_k
            current_alpha = alpha

            if not json_mode:
                console.print(
                    "Interactive mode started. Type queries, [/set alpha <value>], "
                    "[/set top-k <value>], or [/exit].",
                    markup=False,
                )
                console.print(
                    f"Session defaults: top-k={current_top_k}, alpha={current_alpha}"
                )

            async def run_query(text: str) -> None:
                options = QueryOptions(top_k=current_top_k, alpha=current_alpha, filter=parsed_filter)
                result = await client.query(index_name, text, options)
                output.print_search_results(result, json_mode=json_mode)

            if query_text:
                await run_query(query_text)

            # When stdin is redirected (non-TTY), an interactive prompt cannot be sustained.
            # In that case, run any piped initial query and exit with an explicit message.
            if not sys.stdin.isatty():
                if not json_mode:
                    console.print(
                        "Interactive stdin is not a TTY; exiting after piped input.",
                        style="yellow",
                    )
                return

            while True:
                try:
                    line = (await asyncio.to_thread(input, "moss> ")).strip()
                except (EOFError, KeyboardInterrupt):
                    break

                if not line:
                    continue
                if line == "/exit":
                    break
                if line == "/set" or line.startswith("/set "):
                    parsed, err = _parse_set_command(line)
                    if err:
                        output.print_error(err, json_mode)
                        continue
                    if parsed is None:
                        output.print_error("Invalid /set command.", json_mode)
                        continue
                    if parsed.startswith("alpha="):
                        current_alpha = float(parsed.split("=", 1)[1])
                    else:
                        current_top_k = int(parsed.split("=", 1)[1])
                    if not json_mode:
                        console.print(
                            f"Session defaults updated: top-k={current_top_k}, alpha={current_alpha}"
                        )
                    continue

                try:
                    await run_query(line)
                except Exception as e:
                    output.print_error(f"Query failed: {e}", json_mode)
                    continue

            if not json_mode:
                console.print("Exiting interactive session.")
            return

        options = QueryOptions(top_k=top_k, alpha=alpha, filter=parsed_filter)
        result = await client.query(index_name, query_text, options)
        output.print_search_results(result, json_mode=json_mode)

    asyncio.run(_run())
