"""Load documents from JSON/CSV files or stdin."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

import typer
from moss import DocumentInfo


def load_documents(file_path: str) -> list[DocumentInfo]:
    """Load documents from a JSON/CSV file or stdin ('-')."""
    if file_path == "-":
        raw = sys.stdin.read()
        return _parse_json_docs(raw, source="stdin")

    path = Path(file_path)
    if not path.exists():
        raise typer.BadParameter(f"File not found: {file_path}")

    suffix = path.suffix.lower()
    content = path.read_text()

    if suffix == ".csv":
        return _parse_csv_docs(content)
    elif suffix == ".jsonl":
        return _parse_jsonl_docs(content, source=file_path)
    elif suffix == ".json":
        return _parse_json_docs(content, source=file_path)
    else:
        return _parse_json_docs(content, source=file_path)


def _parse_json_docs(raw: str, source: str = "input") -> list[DocumentInfo]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise typer.BadParameter(f"Invalid JSON in {source}: {e}")

    if isinstance(data, dict):
        data = data.get("documents", data.get("docs", []))

    if not isinstance(data, list):
        raise typer.BadParameter(
            f"Expected a JSON array of documents, got {type(data).__name__}"
        )

    return [_dict_to_doc(d, i) for i, d in enumerate(data)]


def _parse_jsonl_docs(raw: str, source: str = "input") -> list[DocumentInfo]:
    docs = []
    for line_no, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise typer.BadParameter(f"Invalid JSON on line {line_no} in {source}: {e}")
        docs.append(_dict_to_doc(obj, line_no - 1))
    return docs


def _parse_csv_docs(content: str) -> list[DocumentInfo]:
    reader = csv.DictReader(content.splitlines())
    docs = []
    for i, row in enumerate(reader):
        if "id" not in row or "text" not in row:
            raise typer.BadParameter(
                f"CSV row {i + 1}: missing required 'id' or 'text' column"
            )
        metadata = None
        if row.get("metadata"):
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                raise typer.BadParameter(
                    f"CSV row {i + 1}: invalid JSON in 'metadata' column"
                )

        embedding = None
        if row.get("embedding"):
            try:
                embedding = json.loads(row["embedding"])
            except json.JSONDecodeError:
                raise typer.BadParameter(
                    f"CSV row {i + 1}: invalid JSON in 'embedding' column"
                )

        docs.append(
            DocumentInfo(
                id=row["id"],
                text=row["text"],
                metadata=metadata,
                embedding=embedding,
            )
        )
    return docs


def _dict_to_doc(d: Any, index: int) -> DocumentInfo:
    if not isinstance(d, dict):
        raise typer.BadParameter(f"Document at index {index}: expected object, got {type(d).__name__}")
    if "id" not in d or "text" not in d:
        raise typer.BadParameter(f"Document at index {index}: missing required 'id' or 'text' field")
    return DocumentInfo(
        id=str(d["id"]),
        text=str(d["text"]),
        metadata=d.get("metadata"),
        embedding=d.get("embedding"),
    )
