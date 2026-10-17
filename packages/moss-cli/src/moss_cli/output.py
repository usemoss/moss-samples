"""Output formatting: tables, JSON, search results."""

from __future__ import annotations

import json
import sys
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()
err_console = Console(stderr=True)


def _index_to_dict(info: Any) -> dict[str, Any]:
    return {
        "id": info.id,
        "name": info.name,
        "version": info.version,
        "status": info.status,
        "doc_count": info.doc_count,
        "created_at": info.created_at,
        "updated_at": info.updated_at,
        "model": {"id": info.model.id, "version": info.model.version},
    }


def _doc_to_dict(doc: Any) -> dict[str, Any]:
    d: dict[str, Any] = {"id": doc.id, "text": doc.text}
    meta = getattr(doc, "metadata", None)
    if meta is not None:
        d["metadata"] = dict(meta)
    emb = getattr(doc, "embedding", None)
    if emb is not None:
        d["embedding"] = list(emb)
    return d


def _result_doc_to_dict(doc: Any) -> dict[str, Any]:
    d: dict[str, Any] = {"id": doc.id, "text": doc.text, "score": doc.score}
    meta = getattr(doc, "metadata", None)
    if meta is not None:
        d["metadata"] = dict(meta)
    return d


def _search_result_to_dict(result: Any) -> dict[str, Any]:
    return {
        "query": result.query,
        "index_name": result.index_name,
        "time_taken_ms": result.time_taken_ms,
        "docs": [_result_doc_to_dict(d) for d in result.docs],
    }


def _mutation_to_dict(result: Any) -> dict[str, Any]:
    return {
        "job_id": result.job_id,
        "index_name": result.index_name,
        "doc_count": result.doc_count,
    }


def _job_status_to_dict(status: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "job_id": status.job_id,
        "status": status.status.value if hasattr(status.status, "value") else str(status.status),
        "progress": status.progress,
        "created_at": status.created_at,
        "updated_at": status.updated_at,
        "completed_at": status.completed_at,
    }
    phase = getattr(status, "current_phase", None)
    if phase is not None:
        d["current_phase"] = phase.value if hasattr(phase, "value") else str(phase)
    else:
        d["current_phase"] = None
    error = getattr(status, "error", None)
    if error is not None:
        d["error"] = error
    return d


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


# --- Public API ---


def print_index_table(indexes: list, json_mode: bool = False) -> None:
    if json_mode:
        _print_json([_index_to_dict(i) for i in indexes])
        return
    if not indexes:
        console.print("[dim]No indexes found.[/dim]")
        return
    table = Table(title="Indexes")
    table.add_column("Name", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Docs", justify="right")
    table.add_column("Model")
    table.add_column("Created")
    table.add_column("Updated")
    for idx in indexes:
        table.add_row(
            idx.name,
            idx.status,
            str(idx.doc_count),
            idx.model.id,
            idx.created_at,
            idx.updated_at,
        )
    console.print(table)


def print_index_detail(info: Any, json_mode: bool = False) -> None:
    if json_mode:
        _print_json(_index_to_dict(info))
        return
    console.print(f"[bold cyan]Index:[/bold cyan] {info.name}")
    console.print(f"  ID:         {info.id}")
    console.print(f"  Status:     {info.status}")
    console.print(f"  Documents:  {info.doc_count}")
    console.print(f"  Model:      {info.model.id} v{info.model.version}")
    console.print(f"  Version:    {info.version}")
    console.print(f"  Created:    {info.created_at}")
    console.print(f"  Updated:    {info.updated_at}")


def print_doc_table(docs: list, json_mode: bool = False) -> None:
    if json_mode:
        _print_json([_doc_to_dict(d) for d in docs])
        return
    if not docs:
        console.print("[dim]No documents found.[/dim]")
        return
    table = Table(title="Documents")
    table.add_column("ID", style="cyan")
    table.add_column("Text", max_width=80)
    table.add_column("Metadata")
    for doc in docs:
        meta = getattr(doc, "metadata", None)
        meta_str = json.dumps(dict(meta), default=str) if meta else ""
        text = doc.text
        if len(text) > 80:
            text = text[:77] + "..."
        table.add_row(doc.id, text, meta_str)
    console.print(table)


def print_search_results(result: Any, json_mode: bool = False) -> None:
    if json_mode:
        _print_json(_search_result_to_dict(result))
        return
    time_str = f" in {result.time_taken_ms}ms" if result.time_taken_ms else ""
    console.print(
        f'[bold]Query:[/bold] "{result.query}"  '
        f"[dim]index={result.index_name}{time_str}[/dim]\n"
    )
    if not result.docs:
        console.print("[dim]No results.[/dim]")
        return
    for i, doc in enumerate(result.docs, 1):
        meta = getattr(doc, "metadata", None)
        meta_str = f"  [dim]{json.dumps(dict(meta), default=str)}[/dim]" if meta else ""
        console.print(f"[bold cyan]{i}.[/bold cyan] [green]{doc.score:.4f}[/green]  {doc.id}")
        console.print(f"   {doc.text}")
        if meta_str:
            console.print(meta_str)
        console.print()


def print_mutation_result(result: Any, json_mode: bool = False) -> None:
    if json_mode:
        _print_json(_mutation_to_dict(result))
        return
    console.print("[green]Job submitted[/green]")
    console.print(f"  Job ID:  {result.job_id}")
    console.print(f"  Index:   {result.index_name}")
    console.print(f"  Docs:    {result.doc_count}")


def print_job_status(status: Any, json_mode: bool = False) -> None:
    if json_mode:
        _print_json(_job_status_to_dict(status))
        return
    status_val = (status.status.value if hasattr(status.status, "value") else str(status.status)).upper()
    color = "green" if status_val == "COMPLETED" else "red" if status_val == "FAILED" else "yellow"
    progress = float(status.progress)
    if progress > 1:
        progress /= 100.0
    console.print(f"[bold]Job:[/bold] {status.job_id}")
    console.print(f"  Status:   [{color}]{status_val}[/{color}]")
    console.print(f"  Progress: {progress:.0%}")
    phase = getattr(status, "current_phase", None)
    if phase is not None:
        phase_val = phase.value if hasattr(phase, "value") else str(phase)
        console.print(f"  Phase:    {phase_val}")
    error = getattr(status, "error", None)
    if error:
        console.print(f"  [red]Error: {error}[/red]")
    console.print(f"  Created:  {status.created_at}")
    console.print(f"  Updated:  {status.updated_at}")
    if status.completed_at:
        console.print(f"  Completed: {status.completed_at}")


def print_success(message: str, json_mode: bool = False) -> None:
    if json_mode:
        _print_json({"status": "ok", "message": message})
        return
    console.print(f"[green]{message}[/green]")


def print_error(message: str, json_mode: bool = False) -> None:
    if json_mode:
        print(json.dumps({"error": message}), file=sys.stderr)
    else:
        err_console.print(f"[red]{message}[/red]")
