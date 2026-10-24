"""Upload DocumentInfo rows to a Moss index."""

from __future__ import annotations

from dataclasses import dataclass

from moss import DocumentInfo, MossClient, MutationOptions, MutationResult

from .types import MossCreds


@dataclass
class UploadOptions:
    """Upload behavior.

    - default: create_index only (fails if the index already exists)
    - upsert=True: add_docs with upsert
    - replace=True: delete existing index then create_index (destructive)
    """

    upsert: bool = False
    replace: bool = False


async def upload_documents(
    documents: list[DocumentInfo],
    creds: MossCreds,
    options: UploadOptions | None = None,
) -> MutationResult:
    """Create an index or upsert documents into an existing index."""
    if not documents:
        raise ValueError("No documents to upload")

    opts = options or UploadOptions()
    if opts.upsert and opts.replace:
        raise ValueError("Pass only one of upsert=True or replace=True")

    client = MossClient(creds.project_id, creds.project_key)
    if opts.upsert:
        return await _upsert_documents(client, creds, documents)
    if opts.replace:
        return await _recreate_index(client, creds, documents)
    return await client.create_index(
        creds.index_name,
        documents,
        creds.model_name,
    )


async def _upsert_documents(
    client: MossClient,
    creds: MossCreds,
    documents: list[DocumentInfo],
) -> MutationResult:
    return await client.add_docs(
        creds.index_name,
        documents,
        MutationOptions(upsert=True),
    )


async def _recreate_index(
    client: MossClient,
    creds: MossCreds,
    documents: list[DocumentInfo],
) -> MutationResult:
    await _delete_index_if_present(client, creds.index_name)
    return await client.create_index(
        creds.index_name,
        documents,
        creds.model_name,
    )


async def _delete_index_if_present(client: MossClient, index_name: str) -> None:
    try:
        await client.delete_index(index_name)
    except Exception as exc:
        message = str(exc).lower()
        if "not found" in message or "does not exist" in message:
            return
        raise
