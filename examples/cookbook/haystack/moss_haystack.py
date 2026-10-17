"""Moss integration for Haystack pipelines.

This is a cookbook example, not a full production-grade DocumentStore.

Notably, ``MossDocumentStore.filter_documents`` supports the common
``filters=None`` case (returning all documents) but does not translate
Haystack's full filter DSL (``$eq``, ``$and``, ``$or``, ``$in``, ``$not``,
nested combinations) into Moss queries. Implementing that fully would
require a client-side filter evaluator, since Moss's ``get_docs`` does not
accept filters — and that creates a footgun on large indexes.

For filtered retrieval, use ``MossRetriever`` with
``QueryOptions(filter=...)`` at query time; Moss supports this natively
server-side.
"""

import asyncio
import json
import os
from typing import Any

from haystack import Document, component, default_from_dict, default_to_dict
from haystack.document_stores.types import DocumentStore, DuplicatePolicy
from haystack.utils import Secret
from moss import (
    DocumentInfo,
    GetDocumentsOptions,
    MossClient,
    MutationOptions,
    QueryOptions,
)


def _run_async(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    try:
        return asyncio.run(coro)
    except RuntimeError as e:
        if "cannot be called from a running event loop" in str(e):
            raise RuntimeError(
                "Cannot run sync in an existing event loop. "
                "Use nest_asyncio or run from a standard script."
            ) from e
        raise


_MOSS_TYPED_PREFIX = "__moss_typed__:"


def _serialize_metadata(meta: dict | None) -> dict | None:
    """Convert arbitrary-typed metadata to Moss string-only metadata.

    Moss only accepts string values in metadata. Non-string values are
    JSON-encoded and prefixed with ``__moss_typed__:`` so the deserializer
    can recover the original type. Plain strings are stored as-is.
    """
    if meta is None:
        return None

    result = {}
    for k, v in meta.items():
        if isinstance(v, str):
            result[k] = v
        else:
            result[k] = f"{_MOSS_TYPED_PREFIX}{json.dumps(v)}"
    return result


def _deserialize_metadata(meta: dict | None) -> dict:
    """Convert Moss string metadata back to original types.

    Values prefixed with ``__moss_typed__:`` are JSON-decoded to restore
    their original type. All other values are returned as plain strings.
    """
    if meta is None:
        return {}

    result = {}
    for k, v in meta.items():
        if isinstance(v, str) and v.startswith(_MOSS_TYPED_PREFIX):
            json_str = v[len(_MOSS_TYPED_PREFIX):]
            try:
                result[k] = json.loads(json_str)
            except (json.JSONDecodeError, TypeError):
                result[k] = v
        else:
            result[k] = v
    return result


def _haystack_doc_to_moss(doc: Document) -> DocumentInfo:
    """Convert Haystack Document to Moss DocumentInfo."""
    return DocumentInfo(
        id=doc.id,
        text=doc.content or "",
        metadata=_serialize_metadata(doc.meta),
        embedding=doc.embedding,
    )


def _moss_doc_to_haystack(doc: Any, score: float | None = None) -> Document:
    """Convert Moss DocumentInfo/QueryResultDocumentInfo to Haystack Document."""
    return Document(
        id=doc.id,
        content=doc.text,
        meta=_deserialize_metadata(getattr(doc, "metadata", None)),
        embedding=getattr(doc, "embedding", None),
        score=score if score is not None else getattr(doc, "score", None),
    )


# --- Document Store ---
class MossDocumentStore(DocumentStore):
    """Moss-backed document store implementing the Haystack DocumentStore protocol."""

    def __init__(
        self,
        project_id: str | None = None,
        project_key: Secret | None = None,
        index_name: str = "default",
        model_id: str = "moss-minilm",
    ):
        self.project_id = project_id or os.getenv("MOSS_PROJECT_ID")

        # Accept Secret, raw string, or fall back to env var
        if isinstance(project_key, Secret):
            self.project_key = project_key
        elif isinstance(project_key, str):
            self.project_key = Secret.from_token(project_key)
        else:
            self.project_key = Secret.from_env_var("MOSS_PROJECT_KEY")

        resolved_key = self.project_key.resolve_value()
        if not self.project_id or not resolved_key:
            raise ValueError(
                "Moss credentials required. Pass project_id/project_key "
                "or set MOSS_PROJECT_ID/MOSS_PROJECT_KEY env vars."
            )
        self.client = MossClient(self.project_id, resolved_key)
        self.index_name = index_name
        self.model_id = model_id
        self._index_created = False
        self._index_loaded = False

    def to_dict(self) -> dict[str, Any]:
        return default_to_dict(
            self,
            project_id=self.project_id,
            project_key=self.project_key.to_dict(),
            index_name=self.index_name,
            model_id=self.model_id,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MossDocumentStore":
        data["init_parameters"]["project_key"] = Secret.from_dict(
            data["init_parameters"]["project_key"]
        )
        return default_from_dict(cls, data)

    def count_documents(self) -> int:
        info = _run_async(self.client.get_index(self.index_name))
        return getattr(info, "doc_count", 0)

    def write_documents(
        self,
        documents: list[Document],
        policy: DuplicatePolicy = DuplicatePolicy.OVERWRITE,
    ) -> int:
        docs = [_haystack_doc_to_moss(doc) for doc in documents]

        if not self._index_created:
            try:
                _run_async(
                    self.client.create_index(self.index_name, docs, self.model_id)
                )
                self._index_created = True
                self._index_loaded = False
                return len(docs)
            except RuntimeError as e:
                if "already exists" not in str(e):
                    raise
                self._index_created = True
                # Index exists — fall through to add/upsert docs below

        if policy == DuplicatePolicy.SKIP:
            candidate_ids = [d.id for d in docs]
            existing = _run_async(
                self.client.get_docs(
                    self.index_name, GetDocumentsOptions(doc_ids=candidate_ids)
                )
            )
            existing_ids = {doc.id for doc in existing}
            docs = [d for d in docs if d.id not in existing_ids]
            if not docs:
                return 0

        options = (
            MutationOptions(upsert=True)
            if policy == DuplicatePolicy.OVERWRITE
            else None
        )
        _run_async(self.client.add_docs(self.index_name, docs, options))
        self._index_loaded = False
        return len(docs)

    def delete_documents(self, document_ids: list[str]) -> None:
        _run_async(self.client.delete_docs(self.index_name, document_ids))
        self._index_loaded = False

    def filter_documents(self, filters: dict | None = None) -> list[Document]:
        """Return documents from the index.

        When ``filters`` is None, returns every document in the index — the
        common case used by Haystack writers and evaluation helpers.

        Filtered retrieval is not supported through this method because Moss
        uses its own filter syntax (``$eq``, ``$and``, ``$in``, ``$near``)
        applied at query time. For filtered search, use ``MossRetriever``
        with ``QueryOptions(filter=...)``.
        """
        if filters:
            raise NotImplementedError(
                "Haystack-style filter_documents(filters=...) is not supported. "
                "For filtered retrieval, pass filters via QueryOptions to "
                "MossRetriever.run(). Call filter_documents(filters=None) to "
                "fetch all documents."
            )
        moss_docs = _run_async(self.client.get_docs(self.index_name))
        return [_moss_doc_to_haystack(doc) for doc in moss_docs]

    def load_index(self) -> None:
        """Download index for fast local querying."""
        if not self._index_loaded:
            _run_async(self.client.load_index(self.index_name))
            self._index_loaded = True


# --- Retriever ---
@component
class MossRetriever:
    """Haystack retriever component backed by Moss semantic search.

    Use in a Haystack Pipeline to retrieve documents from a Moss index.
    """

    def __init__(
        self,
        document_store: MossDocumentStore,
        top_k: int = 5,
        alpha: float = 0.8,
    ):
        self.document_store = document_store
        self.top_k = top_k
        self.alpha = alpha

    def load_index(self) -> None:
        """Load the Moss index for fast local queries."""
        self.document_store.load_index()

    def to_dict(self) -> dict[str, Any]:
        return default_to_dict(
            self,
            document_store=self.document_store.to_dict(),
            top_k=self.top_k,
            alpha=self.alpha,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MossRetriever":
        data["init_parameters"]["document_store"] = MossDocumentStore.from_dict(
            data["init_parameters"]["document_store"]
        )
        return default_from_dict(cls, data)

    @component.output_types(documents=list[Document])
    def run(
        self,
        query: str,
        top_k: int | None = None,
    ) -> dict[str, list[Document]]:
        """Run semantic search against Moss index.

        Args:
            query: Search query text.
            top_k: Override default number of results.

        Returns:
            {"documents": list[Document]} with scores.
        """
        self.document_store.load_index()

        resolved_top_k = top_k if top_k is not None else self.top_k
        opts = QueryOptions(top_k=resolved_top_k, alpha=self.alpha)

        results = _run_async(
            self.document_store.client.query(
                self.document_store.index_name, query, opts
            )
        )

        documents = [
            _moss_doc_to_haystack(doc, score=doc.score) for doc in results.docs
        ]

        return {"documents": documents}
