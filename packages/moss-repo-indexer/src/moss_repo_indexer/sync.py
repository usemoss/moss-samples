"""End-to-end: resolve source → build documents → upload (unless dry_run)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from moss import DocumentInfo, MutationResult

from .clone import ResolvedSource, resolve_source
from .documents import build_documents
from .types import IndexOptions, SyncOptions
from .uploader import UploadOptions, upload_documents


@dataclass
class SyncResult:
    documents: list[DocumentInfo]
    mutation: MutationResult | None
    dry_run: bool
    repo_name: str
    root: str


async def sync(options: SyncOptions) -> SyncResult:
    """Index a local path or git URL into Moss."""
    resolved = resolve_source(options.source, options.index.ref)
    try:
        return await _sync_resolved(options, resolved)
    finally:
        resolved.close()


async def _sync_resolved(options: SyncOptions, resolved: ResolvedSource) -> SyncResult:
    index_opts = _with_repo_name(options.index, resolved.repo_name)
    documents = build_documents(resolved.root, index_opts)
    if options.dry_run:
        return SyncResult(
            documents=documents,
            mutation=None,
            dry_run=True,
            repo_name=resolved.repo_name,
            root=str(resolved.root),
        )

    mutation = await upload_documents(
        documents,
        options.creds,
        UploadOptions(upsert=options.upsert, replace=options.replace),
    )
    return SyncResult(
        documents=documents,
        mutation=mutation,
        dry_run=False,
        repo_name=resolved.repo_name,
        root=str(resolved.root),
    )


def _with_repo_name(options: IndexOptions, repo_name: str) -> IndexOptions:
    if options.repo_name:
        return options
    return replace(options, repo_name=repo_name)
