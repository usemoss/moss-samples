"""Load and map documents from JSON/JSONL/CSV files or stdin."""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path
from typing import (
    Any,
    Collection,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    TypedDict,
    cast,
)

import typer
from moss import DocumentInfo


class _MappingOptions(TypedDict):
    id_column: str
    text_column: str
    metadata_columns: Optional[List[str]]
    require_non_empty: bool


_Record = Tuple[Dict[str, Any], str]


def load_documents(
    file_path: str,
    *,
    id_column: str = "id",
    text_column: str = "text",
    metadata_columns: Optional[Sequence[str]] = None,
    require_non_empty: bool = False,
) -> List[DocumentInfo]:
    """Load documents and optionally map custom source columns.

    When ``metadata_columns`` is provided, those source fields are copied into
    metadata as strings. Otherwise, the existing ``metadata`` object is used.
    ``require_non_empty`` lets the import command reject blank IDs and text
    without changing legacy callers that use this loader for validation.
    """
    mapping = _mapping_options(
        id_column, text_column, metadata_columns, require_non_empty
    )

    if file_path == "-":
        return _parse_json(sys.stdin.read(), "stdin", mapping)

    path = Path(file_path)
    if not path.exists():
        raise typer.BadParameter(f"File not found: {file_path}")
    if not path.is_file():
        raise typer.BadParameter(f"Not a file: {file_path}")

    try:
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise typer.BadParameter(f"{file_path} is not valid UTF-8: {exc}") from exc

    if path.suffix.lower() == ".csv":
        return _parse_csv(content, file_path, mapping)
    if path.suffix.lower() == ".jsonl":
        return _parse_jsonl(content, file_path, mapping)
    return _parse_json(content, file_path, mapping)


def _mapping_options(
    id_column: str,
    text_column: str,
    metadata_columns: Optional[Sequence[str]],
    require_non_empty: bool,
) -> _MappingOptions:
    id_column = id_column.strip()
    text_column = text_column.strip()
    if not id_column:
        raise typer.BadParameter("ID column name cannot be empty")
    if not text_column:
        raise typer.BadParameter("Text column name cannot be empty")

    normalized_metadata: Optional[List[str]] = None
    if metadata_columns is not None:
        normalized_metadata = []
        for column in metadata_columns:
            name = column.strip()
            if not name:
                raise typer.BadParameter("Metadata column name cannot be empty")
            if name not in normalized_metadata:
                normalized_metadata.append(name)

    return {
        "id_column": id_column,
        "text_column": text_column,
        "metadata_columns": normalized_metadata,
        "require_non_empty": require_non_empty,
    }


def _parse_json(raw: str, source: str, mapping: _MappingOptions) -> List[DocumentInfo]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON in {source}: {exc}") from exc

    if isinstance(data, dict):
        if "documents" in data:
            data = data["documents"]
        elif "docs" in data:
            data = data["docs"]
        else:
            raise typer.BadParameter(
                "Expected a JSON array or an object with a 'documents' or "
                f"'docs' array in {source}"
            )
    if not isinstance(data, list):
        raise typer.BadParameter(
            f"Expected a JSON array of documents, got {type(data).__name__}"
        )

    records = []
    for index, item in enumerate(data):
        label = f"Document at index {index}"
        records.append((_require_record(item, label), label))
    return _records_to_docs(records, source, mapping)


def _parse_jsonl(raw: str, source: str, mapping: _MappingOptions) -> List[DocumentInfo]:
    records: List[_Record] = []
    for line_no, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(
                f"Invalid JSON on line {line_no} in {source}: {exc}"
            ) from exc
        label = f"JSONL line {line_no}"
        records.append((_require_record(item, label), label))
    return _records_to_docs(records, source, mapping)


def _parse_csv(
    content: str, source: str, mapping: _MappingOptions
) -> List[DocumentInfo]:
    # StringIO preserves newlines inside quoted fields; splitlines() does not.
    reader = csv.DictReader(io.StringIO(content, newline=""))
    fieldnames = reader.fieldnames
    if not fieldnames:
        raise typer.BadParameter(f"CSV in {source} is missing a header row")

    duplicate_headers = _duplicates(fieldnames)
    if duplicate_headers:
        names = ", ".join(repr(name) for name in duplicate_headers)
        raise typer.BadParameter(f"CSV in {source} has duplicate column(s): {names}")

    _validate_required_columns(fieldnames, mapping, source)
    _validate_metadata_column_names(fieldnames, mapping["metadata_columns"], source)

    docs = []
    for row in reader:
        label = f"CSV row {reader.line_num}"
        if None in row:
            raise typer.BadParameter(
                f"{label} in {source} has more values than the header row"
            )
        docs.append(_record_to_doc(row, label, mapping))
    return docs


def _records_to_docs(
    records: Sequence[_Record], source: str, mapping: _MappingOptions
) -> List[DocumentInfo]:
    if records:
        available_names = {name for record, _ in records for name in record}
        _validate_metadata_column_names(
            available_names, mapping["metadata_columns"], source
        )
    return [_record_to_doc(record, label, mapping) for record, label in records]


def _require_record(item: Any, label: str) -> Dict[str, Any]:
    if not isinstance(item, dict):
        raise typer.BadParameter(f"{label}: expected object, got {type(item).__name__}")
    return item


def _record_to_doc(
    record: Dict[str, Any], label: str, mapping: _MappingOptions
) -> DocumentInfo:
    id_column = mapping["id_column"]
    text_column = mapping["text_column"]
    metadata_columns = mapping["metadata_columns"]
    doc_id = _required_value(record, id_column, "ID", label, mapping)
    text = _required_value(record, text_column, "text", label, mapping)

    consumed_columns = {id_column, text_column}
    if metadata_columns is not None:
        consumed_columns.update(metadata_columns)
        metadata = _mapped_metadata(record, metadata_columns)
    else:
        metadata = (
            None
            if "metadata" in consumed_columns
            else _parse_metadata(record.get("metadata"), label)
        )

    embedding = (
        None
        if "embedding" in consumed_columns
        else _parse_embedding(record.get("embedding"), label)
    )
    return DocumentInfo(
        id=str(doc_id), text=str(text), metadata=metadata, embedding=embedding
    )


def _required_value(
    record: Dict[str, Any],
    column: str,
    role: str,
    label: str,
    mapping: _MappingOptions,
) -> Any:
    if column not in record:
        raise typer.BadParameter(f"{label}: missing mapped {role} column '{column}'")
    value = record[column]
    if value is None:
        raise typer.BadParameter(
            f"{label}: mapped {role} column '{column}' has no value"
        )
    if mapping["require_non_empty"] and isinstance(value, str) and not value.strip():
        raise typer.BadParameter(f"{label}: mapped {role} column '{column}' is blank")
    return value


def _parse_metadata(value: Any, label: str) -> Optional[Dict[str, str]]:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(
                f"{label}: invalid JSON in 'metadata' column"
            ) from exc
    if value is None:
        return None
    if not isinstance(value, dict):
        raise typer.BadParameter(f"{label}: 'metadata' must be a JSON object")
    metadata = {
        str(key): _metadata_value(item)
        for key, item in value.items()
        if item is not None
    }
    return metadata


def _mapped_metadata(
    record: Dict[str, Any], metadata_columns: Sequence[str]
) -> Optional[Dict[str, str]]:
    metadata = {}
    for column in metadata_columns:
        value = record.get(column)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        metadata[column] = _metadata_value(value)
    return metadata or None


def _metadata_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _parse_embedding(value: Any, label: str) -> Optional[List[float]]:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(
                f"{label}: invalid JSON in 'embedding' column"
            ) from exc
    if value is None:
        return None
    if not isinstance(value, list) or not all(
        isinstance(item, (int, float)) and not isinstance(item, bool) for item in value
    ):
        raise typer.BadParameter(
            f"{label}: 'embedding' must be a JSON array of numbers"
        )
    return cast(List[float], value)


def _validate_required_columns(
    columns: Collection[str], mapping: _MappingOptions, source: str
) -> None:
    expected = (mapping["id_column"], mapping["text_column"])
    missing = [name for name in expected if name not in columns]
    if missing:
        formatted = ", ".join(repr(name) for name in missing)
        raise typer.BadParameter(
            f"{source}: mapped required column(s) not found: {formatted}"
        )


def _validate_metadata_column_names(
    names: Collection[str],
    metadata_columns: Optional[Sequence[str]],
    source: str,
) -> None:
    if metadata_columns is None:
        return
    missing = [name for name in metadata_columns if name not in names]
    if missing:
        formatted = ", ".join(repr(name) for name in missing)
        raise typer.BadParameter(
            f"{source}: mapped metadata column(s) not found: {formatted}"
        )


def _duplicates(names: Sequence[str]) -> List[str]:
    seen = set()
    duplicates = []
    for name in names:
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)
    return duplicates
