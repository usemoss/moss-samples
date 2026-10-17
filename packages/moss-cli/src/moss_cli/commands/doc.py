"""moss doc {add, import, delete, get} commands."""

from __future__ import annotations

import asyncio
from typing import List, Optional, Sequence

import typer
from moss import GetDocumentsOptions, MossClient, MutationOptions
from rich.console import Console

from .. import output
from ..completion import complete_index_name
from ..config import resolve_credentials
from ..documents import load_documents
from ..job_waiter import wait_for_job

console = Console()
doc_app = typer.Typer(name="doc", help="Manage documents in an index")


def _client(ctx: typer.Context) -> MossClient:
    pid, pkey = resolve_credentials(
        ctx.obj.get("project_id"), ctx.obj.get("project_key"), ctx.obj.get("profile")
    )
    return MossClient(pid, pkey)


@doc_app.command(name="add")
def add(
    ctx: typer.Context,
    index_name: str = typer.Argument(
        ..., help="Index name", autocompletion=complete_index_name
    ),
    file: str = typer.Option(
        ..., "--file", "-f", help="Path to JSON/CSV document file, or '-' for stdin"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Credential profile name"
    ),
    upsert: bool = typer.Option(
        False, "--upsert", "-u", help="Update existing documents"
    ),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for job to complete"),
    poll_interval: float = typer.Option(
        2.0, "--poll-interval", help="Seconds between status checks"
    ),
    timeout: Optional[float] = typer.Option(
        None, "--timeout", help="Max seconds to wait (requires --wait)"
    ),
) -> None:
    """Add documents to an index."""
    _submit_documents(
        ctx,
        index_name=index_name,
        file=file,
        profile=profile,
        upsert=upsert,
        wait=wait,
        poll_interval=poll_interval,
        timeout=timeout,
        action="Adding",
    )


@doc_app.command(name="import")
def import_documents(
    ctx: typer.Context,
    index_name: str = typer.Argument(
        ..., help="Index name", autocompletion=complete_index_name
    ),
    file: str = typer.Option(
        ...,
        "--file",
        "-f",
        help="Path to a JSON/JSONL/CSV document file, or '-' for JSON stdin",
    ),
    id_column: str = typer.Option(
        "id", "--id-column", help="Source column to use as the document ID"
    ),
    text_column: str = typer.Option(
        "text", "--text-column", help="Source column to use as the document text"
    ),
    metadata_column: Optional[List[str]] = typer.Option(
        None,
        "--metadata-column",
        "--metadata-columns",
        help=(
            "Source column to copy into metadata. Repeat this option or pass "
            "comma-separated names."
        ),
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Credential profile name"
    ),
    upsert: bool = typer.Option(
        False, "--upsert", "-u", help="Update existing documents"
    ),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for job to complete"),
    poll_interval: float = typer.Option(
        2.0, "--poll-interval", help="Seconds between status checks"
    ),
    timeout: Optional[float] = typer.Option(
        None, "--timeout", help="Max seconds to wait (requires --wait)"
    ),
) -> None:
    """Bulk-import documents with optional source-column mapping."""
    _submit_documents(
        ctx,
        index_name=index_name,
        file=file,
        profile=profile,
        upsert=upsert,
        wait=wait,
        poll_interval=poll_interval,
        timeout=timeout,
        action="Importing",
        id_column=id_column,
        text_column=text_column,
        metadata_columns=_split_metadata_columns(metadata_column),
        require_documents=True,
    )


def _submit_documents(
    ctx: typer.Context,
    *,
    index_name: str,
    file: str,
    profile: Optional[str],
    upsert: bool,
    wait: bool,
    poll_interval: float,
    timeout: Optional[float],
    action: str,
    id_column: str = "id",
    text_column: str = "text",
    metadata_columns: Optional[Sequence[str]] = None,
    require_documents: bool = False,
) -> None:
    json_mode = ctx.obj.get("json_output", False)
    if profile:
        ctx.obj["profile"] = profile
    docs = load_documents(
        file,
        id_column=id_column,
        text_column=text_column,
        metadata_columns=metadata_columns,
        require_non_empty=require_documents,
    )
    if require_documents and not docs:
        raise typer.BadParameter(f"No documents found in {file}")
    client = _client(ctx)

    options = MutationOptions(upsert=True) if upsert else None

    if not json_mode:
        console.print(
            f"{action} {len(docs)} document(s) to [cyan]{index_name}[/cyan]"
            f"{' (upsert)' if upsert else ''}..."
        )

    result = asyncio.run(client.add_docs(index_name, docs, options))
    output.print_mutation_result(result, json_mode=json_mode)

    if wait:
        asyncio.run(
            wait_for_job(client, result.job_id, poll_interval, json_mode, timeout)
        )


def _split_metadata_columns(values: Optional[Sequence[str]]) -> Optional[List[str]]:
    if not values:
        return None

    columns: List[str] = []
    for value in values:
        columns.extend(name.strip() for name in value.split(","))
    return columns or None


@doc_app.command(name="delete")
def delete(
    ctx: typer.Context,
    index_name: str = typer.Argument(
        ..., help="Index name", autocompletion=complete_index_name
    ),
    ids: str = typer.Option(..., "--ids", "-i", help="Comma-separated document IDs"),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Credential profile name"
    ),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for job to complete"),
    poll_interval: float = typer.Option(
        2.0, "--poll-interval", help="Seconds between status checks"
    ),
    timeout: Optional[float] = typer.Option(
        None, "--timeout", help="Max seconds to wait (requires --wait)"
    ),
) -> None:
    """Delete documents from an index by ID."""
    json_mode = ctx.obj.get("json_output", False)
    if profile:
        ctx.obj["profile"] = profile
    client = _client(ctx)
    doc_ids = [i.strip() for i in ids.split(",") if i.strip()]

    if not doc_ids:
        output.print_error("No document IDs provided.", json_mode=json_mode)
        raise typer.Exit(1)

    if not json_mode:
        console.print(
            f"Deleting {len(doc_ids)} document(s) from [cyan]{index_name}[/cyan]..."
        )

    result = asyncio.run(client.delete_docs(index_name, doc_ids))
    output.print_mutation_result(result, json_mode=json_mode)

    if wait:
        asyncio.run(
            wait_for_job(client, result.job_id, poll_interval, json_mode, timeout)
        )


@doc_app.command(name="get")
def get(
    ctx: typer.Context,
    index_name: str = typer.Argument(
        ..., help="Index name", autocompletion=complete_index_name
    ),
    ids: Optional[str] = typer.Option(
        None, "--ids", "-i", help="Comma-separated document IDs (omit for all)"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Credential profile name"
    ),
) -> None:
    """Retrieve documents from an index."""
    json_mode = ctx.obj.get("json_output", False)
    if profile:
        ctx.obj["profile"] = profile
    client = _client(ctx)

    options = None
    if ids:
        doc_ids = [i.strip() for i in ids.split(",") if i.strip()]
        options = GetDocumentsOptions(doc_ids=doc_ids)

    docs = asyncio.run(client.get_docs(index_name, options))
    output.print_doc_table(docs, json_mode=json_mode)
