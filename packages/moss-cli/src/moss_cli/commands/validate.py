"""moss validate — check document files without uploading."""

from __future__ import annotations

import json
from collections import Counter

import typer
from rich.console import Console

from ..documents import load_documents

console = Console()


def validate_command(
    ctx: typer.Context,
    file: str = typer.Option(
        ..., "--file", "-f", help="Path to JSON/JSONL/CSV file, or '-' for stdin"
    ),
) -> None:
    """Validate a document file format without uploading."""
    json_mode = ctx.obj.get("json_output", False)

    try:
        docs = load_documents(file)
    except typer.BadParameter as e:
        _report(json_mode, valid=False, doc_count=0, issues=[str(e)])
        raise typer.Exit(1)
    except SystemExit:
        raise
    except Exception as e:
        _report(json_mode, valid=False, doc_count=0, issues=[str(e)])
        raise typer.Exit(1)

    issues: list[str] = []

    if not docs:
        issues.append("File contains 0 documents")

    id_counts = Counter(d.id for d in docs)
    for doc_id, count in id_counts.items():
        if count > 1:
            issues.append(f"Duplicate ID '{doc_id}' appears {count} times")

    for i, doc in enumerate(docs):
        if not doc.text or not doc.text.strip():
            issues.append(f"Document {i} (id='{doc.id}'): empty text")
        if doc.metadata is not None and not isinstance(doc.metadata, dict):
            issues.append(f"Document '{doc.id}': metadata must be an object, got {type(doc.metadata).__name__}")
        if doc.embedding is not None:
            emb = doc.embedding
            if not isinstance(emb, (list, tuple)) or not all(isinstance(x, (int, float)) for x in emb):
                issues.append(f"Document '{doc.id}': embedding must be a list of numbers")

    _report(json_mode, valid=len(issues) == 0, doc_count=len(docs), issues=issues)

    if issues:
        raise typer.Exit(1)


def _report(json_mode: bool, valid: bool, doc_count: int, issues: list[str]) -> None:
    if json_mode:
        print(json.dumps({"valid": valid, "doc_count": doc_count, "issues": issues}, indent=2))
        return

    if valid:
        console.print(f"[green]✓ Valid[/green] — {doc_count} document(s) ready to upload.")
    else:
        console.print(f"[red]✗ {len(issues)} issue(s) found[/red] in {doc_count} document(s):")
        for issue in issues:
            console.print(f"  [red]•[/red] {issue}")
