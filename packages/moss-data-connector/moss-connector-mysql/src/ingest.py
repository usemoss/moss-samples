"""Copy rows into a Moss index."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from moss import DocumentInfo, MossClient, MutationResult


def _replace_doc_id(doc: DocumentInfo) -> DocumentInfo:
    return DocumentInfo(
        id=str(uuid.uuid4()),
        text=doc.text,
        metadata=getattr(doc, "metadata", None),
        embedding=getattr(doc, "embedding", None),
    )


async def ingest(
    source: Iterable[DocumentInfo],
    project_id: str,
    project_key: str,
    index_name: str,
    model_id: str | None = None,
    auto_id: bool = False,
) -> MutationResult | None:
    """Copy every `DocumentInfo` from `source` into a fresh Moss index."""
    if auto_id:
        docs = [_replace_doc_id(doc) for doc in source]
    else:
        docs = list(source)
    if not docs:
        return None
    client = MossClient(project_id, project_key)
    return await client.create_index(index_name, docs, model_id=model_id)
