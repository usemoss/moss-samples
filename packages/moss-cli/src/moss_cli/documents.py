"""Load documents from JSON/CSV files or stdin."""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path
from typing import Any, List, Optional

import typer
from moss import DocumentInfo


def load_documents(file_path: str) -> List[DocumentInfo]:
    """Load documents from a JSON/CSV file or stdin ('-')."""
    if file_path == "-":
        raw = sys.stdin.read()
        return _parse_json_docs(raw, source="stdin")

    path = Path(file_path)
    if not path.exists():
        raise typer.BadParameter(f"File not found: {file_path}")

    suffix = path.suffix.lower()
    content = path.read_text(encoding="utf-8-sig")

    if suffix == ".csv":
        return _parse_csv_docs(content)
    elif suffix == ".jsonl":
        return _parse_jsonl_docs(content, source=file_path)
    elif suffix == ".json":
        return _parse_json_docs(content, source=file_path)
    else:
        return _parse_json_docs(content, source=file_path)


def _parse_json_docs(raw: str, source: str = "input") -> List[DocumentInfo]:
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


def _parse_jsonl_docs(raw: str, source: str = "input") -> List[DocumentInfo]:
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


def _parse_csv_docs(content: str) -> List[DocumentInfo]:
    reader = csv.DictReader(io.StringIO(content, newline=""))
    if reader.fieldnames is None:
        raise typer.BadParameter("CSV is empty: expected a header row")

    reader.fieldnames = [(name or "").strip() for name in reader.fieldnames]

    seen = set()
    dupes = set()
    for name in reader.fieldnames:
        if not name:
            continue
        if name in seen:
            dupes.add(name)
        else:
            seen.add(name)
    if dupes:
        raise typer.BadParameter(
            f"CSV header has duplicate column name(s): {', '.join(sorted(dupes))}"
        )

    missing = [name for name in ("id", "text") if name not in reader.fieldnames]
    if missing:
        raise typer.BadParameter(
            f"CSV header is missing required column(s): {', '.join(missing)}"
        )

    docs = []
    for row in reader:
        line_no = reader.line_num
        doc_id = row.get("id")
        text = row.get("text")
        if not doc_id or text is None:
            raise typer.BadParameter(
                f"CSV line {line_no}: empty value in required 'id' or 'text' column"
            )

        metadata = _parse_csv_json(row.get("metadata"), "metadata", line_no)
        embedding = _parse_csv_json(row.get("embedding"), "embedding", line_no)

        docs.append(
            DocumentInfo(
                id=doc_id,
                text=text,
                metadata=metadata,
                embedding=embedding,
            )
        )
    return docs


def _parse_csv_json(value: Optional[str], column: str, line_no: int) -> Any:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        raise typer.BadParameter(
            f"CSV line {line_no}: invalid JSON in '{column}' column"
        )


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
