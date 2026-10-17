from __future__ import annotations

import asyncio
import logging
import os
import threading
import uuid
from collections.abc import Sequence
from typing import Any, ClassVar

import httpx
from moss_core import (
    CLOUD_API_MANAGE_URL,
    DocumentInfo,
    GetDocumentsOptions,
    IndexInfo,
    IndexManager,
    JobStatusResponse,
    ManageClient,
    MutationOptions,
    MutationResult,
    QueryResultDocumentInfo,
    SearchResult,
)

logger = logging.getLogger(__name__)


class QueryOptions:
    """Options for search queries."""

    def __init__(
        self,
        embedding: Sequence[float] | None = None,
        top_k: int | None = None,
        alpha: float | None = None,
        filter: dict | None = None,
        rerank: bool = False,
        rerank_top_k: int | None = None,
        rerank_model: str | None = None,
    ):
        if top_k is not None and (not isinstance(top_k, int) or top_k < 1):
            raise ValueError("top_k must be an integer >= 1")
        if alpha is not None and (
            not isinstance(alpha, (int, float)) or not (0.0 <= alpha <= 1.0)
        ):
            raise ValueError("alpha must be a float between 0.0 and 1.0")
        if embedding is not None:
            try:
                embedding = [float(x) for x in embedding]
            except (TypeError, ValueError):
                raise ValueError("embedding must be a sequence of numbers")
        if rerank_top_k is not None and (
            not isinstance(rerank_top_k, int) or rerank_top_k < 1
        ):
            raise ValueError("rerank_top_k must be an integer >= 1")
        if top_k is not None and rerank_top_k is not None and rerank_top_k < top_k:
            raise ValueError("rerank_top_k must be >= top_k")

        self.embedding = embedding
        self.top_k = top_k
        self.alpha = float(alpha) if alpha is not None else None
        self.filter = filter
        self.rerank = bool(rerank)
        self.rerank_top_k = rerank_top_k
        self.rerank_model = rerank_model


def _get_manage_url() -> str:
    """Manage URL, overridable via env for local development."""
    return os.getenv("MOSS_CLOUD_API_MANAGE_URL", CLOUD_API_MANAGE_URL)


def _get_query_url() -> str:
    """Query URL, derived from manage URL or overridable via env."""
    explicit = os.getenv("MOSS_CLOUD_QUERY_URL")
    if explicit:
        return explicit
    return _get_manage_url().replace("/v1/manage", "/query")


class MossClient:
    """
    Semantic search client for vector similarity operations.

    All mutations and reads go through the Rust ManageClient.
    Querying uses the local IndexManager when the index is loaded,
    otherwise falls back to the cloud query API.

    Example:
        ```python
        from moss import MossClient, DocumentInfo

        client = MossClient("project-id", "project-key")

        docs = [DocumentInfo(id="1", text="Machine learning fundamentals")]
        result = await client.create_index("my-index", docs, "moss-minilm")

        await client.load_index("my-index")
        results = await client.query("my-index", "AI and neural networks")
        ```
    """

    DEFAULT_MODEL_ID = "moss-minilm"
    _cross_encoder_cache: ClassVar[dict[str, Any]] = {}
    _cross_encoder_locks: ClassVar[dict[str, threading.Lock]] = {}
    _cache_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, project_id: str, project_key: str) -> None:
        self._project_id = project_id
        self._project_key = project_key
        self._client_id = str(uuid.uuid4())
        manage_url = _get_manage_url()
        self._manage = ManageClient(
            project_id, project_key, manage_url, self._client_id
        )
        self._manager = IndexManager(
            project_id, project_key, manage_url, self._client_id
        )

    # -- Mutations (via Rust ManageClient) --------------------------

    async def create_index(
        self,
        name: str,
        docs: list[DocumentInfo],
        model_id: str | None = None,
    ) -> MutationResult:
        """Create a new index and populate it with documents."""
        resolved_model_id = self._resolve_model_id(docs, model_id)
        return await asyncio.to_thread(
            self._manage.create_index,
            name,
            docs,
            resolved_model_id,
        )

    async def add_docs(
        self,
        name: str,
        docs: list[DocumentInfo],
        options: MutationOptions | None = None,
    ) -> MutationResult:
        """Add or update documents in an index."""
        return await asyncio.to_thread(
            self._manage.add_docs,
            name,
            docs,
            options,
        )

    async def delete_docs(
        self,
        name: str,
        doc_ids: list[str],
    ) -> MutationResult:
        """Delete documents from an index by their IDs."""
        return await asyncio.to_thread(
            self._manage.delete_docs,
            name,
            doc_ids,
        )

    async def get_job_status(self, job_id: str) -> JobStatusResponse:
        """Get the status of a bulk operation job."""
        return await asyncio.to_thread(self._manage.get_job_status, job_id)

    # -- Read operations (via Rust ManageClient) --------------------

    async def get_index(self, name: str) -> IndexInfo:
        """Get information about a specific index."""
        return await asyncio.to_thread(self._manage.get_index, name)

    async def list_indexes(self) -> list[IndexInfo]:
        """List all indexes with their information."""
        return await asyncio.to_thread(self._manage.list_indexes)

    async def delete_index(self, name: str) -> bool:
        """Delete an index and all its data."""
        return await asyncio.to_thread(self._manage.delete_index, name)

    async def get_docs(
        self,
        name: str,
        options: GetDocumentsOptions | None = None,
    ) -> list[DocumentInfo]:
        """Retrieve documents from an index."""
        return await asyncio.to_thread(self._manage.get_docs, name, options)

    # -- Index loading & querying -----------------------------------

    async def load_index(
        self,
        name: str,
        auto_refresh: bool = False,
        polling_interval_in_seconds: int = 600,
    ) -> str:
        """
        Downloads an index from the cloud into memory for fast local querying.

        Without load_index(), query() falls back to the cloud API (~100-500ms).
        With load_index(), queries run entirely in-memory (~1-10ms).
        """
        try:
            await asyncio.to_thread(
                self._manager.load_index,
                name,
                auto_refresh,
                polling_interval_in_seconds,
            )
            await asyncio.to_thread(self._manager.load_query_model, name)
            return name
        except RuntimeError as e:
            raise RuntimeError(f"Failed to load index '{name}': {e}") from e

    async def unload_index(self, name: str) -> None:
        """Unload an index from memory."""
        try:
            await asyncio.to_thread(self._manager.unload_index, name)
        except RuntimeError as e:
            raise RuntimeError(f"Failed to unload index '{name}': {e}") from e

    async def query(
        self,
        name: str,
        query: str,
        options: QueryOptions | None = None,
    ) -> SearchResult:
        """
        Perform a semantic similarity search.

        If the index is loaded locally (via load_index), queries run in-memory.
        Otherwise, falls back to the cloud query API.

        Args:
            options: Query options (top_k, alpha, embedding, filter, rerank, etc).
        """
        is_loaded = await asyncio.to_thread(self._manager.has_index, name)

        rerank = getattr(options, "rerank", False) is True
        override_top_k = None
        if rerank:
            candidate_pool = getattr(options, "rerank_top_k", None) or 50
            final_top_k = getattr(options, "top_k", None) or 5
            override_top_k = max(candidate_pool, final_top_k)

        if is_loaded:
            result = await self._query_local(name, query, options, override_top_k)
        else:
            if getattr(options, "filter", None) is not None:
                logger.warning(
                    "Metadata filter ignored: filtering is only supported for locally loaded indexes. "
                    "Call load_index('%s') first.",
                    name,
                )
            result = await self._query_cloud(name, query, options, override_top_k)

        if rerank:
            result = await self._rerank_results(query, result, options)

        return result

    # -- Internal ---------------------------------------------------

    async def _query_local(
        self,
        name: str,
        query: str,
        options: QueryOptions | None,
        override_top_k: int | None = None,
    ) -> SearchResult:
        top_k = (
            override_top_k
            if override_top_k is not None
            else (getattr(options, "top_k", None) or 5)
        )
        alpha = getattr(options, "alpha", None)
        if alpha is None:
            alpha = 0.8
        query_embedding = getattr(options, "embedding", None)
        filter = getattr(options, "filter", None)

        if query_embedding is None:
            try:
                return await asyncio.to_thread(
                    self._manager.query_text,
                    name,
                    query,
                    top_k,
                    alpha,
                    filter,
                )
            except RuntimeError as e:
                if "requires explicit query embeddings" in str(e):
                    raise ValueError(
                        "This index uses custom embeddings. "
                        "Query embeddings must be provided via QueryOptions.embedding."
                    ) from e
                raise

        return await asyncio.to_thread(
            self._manager.query,
            name,
            query,
            list(query_embedding),
            top_k,
            alpha,
            filter,
        )

    async def _query_cloud(
        self,
        name: str,
        query: str,
        options: QueryOptions | None,
        override_top_k: int | None = None,
    ) -> SearchResult:
        """Fallback: query via the cloud API when the index is not loaded locally."""
        top_k = (
            override_top_k
            if override_top_k is not None
            else (getattr(options, "top_k", None) or 10)
        )
        query_embedding = getattr(options, "embedding", None)

        request_body: dict[str, Any] = {
            "query": query,
            "indexName": name,
            "projectId": self._project_id,
            "projectKey": self._project_key,
            "topK": top_k,
        }
        if query_embedding is not None:
            request_body["queryEmbedding"] = list(query_embedding)

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    _get_query_url(),
                    headers={"Content-Type": "application/json"},
                    json=request_body,
                )
                if not response.is_success:
                    raise Exception(f"HTTP error! status: {response.status_code}")
                data = response.json()
        except httpx.RequestError as error:
            raise Exception(f"Cloud query request failed: {error!s}")

        return self._dict_to_search_result(data)

    @staticmethod
    def _dict_to_search_result(data: dict) -> SearchResult:
        docs = [
            QueryResultDocumentInfo(
                id=d.get("id", ""),
                text=d.get("text", ""),
                metadata=d.get("metadata"),
                score=float(d.get("score", 0.0)),
            )
            for d in data.get("docs", [])
        ]
        return SearchResult(
            docs=docs,
            query=data.get("query", ""),
            index_name=data.get("indexName"),
            time_taken_ms=data.get("timeTakenMs"),
        )

    async def _rerank_results(
        self, query: str, search_result: SearchResult, options: QueryOptions | None
    ) -> SearchResult:
        if not search_result.docs:
            return search_result

        try:
            from sentence_transformers import CrossEncoder
        except ImportError:
            raise ImportError(
                "The 'sentence-transformers' package is required for reranking. "
                "Install it with: pip install 'moss[rerank]'"
            )

        model_name = (
            getattr(options, "rerank_model", None)
            or "cross-encoder/ms-marco-MiniLM-L-6-v2"
        )

        def do_rerank() -> SearchResult:
            with self.__class__._cache_lock:
                if model_name not in self.__class__._cross_encoder_locks:
                    self.__class__._cross_encoder_locks[model_name] = threading.Lock()

            model_lock = self.__class__._cross_encoder_locks[model_name]

            with model_lock:
                if model_name not in self.__class__._cross_encoder_cache:
                    self.__class__._cross_encoder_cache[model_name] = CrossEncoder(
                        model_name
                    )

                model = self.__class__._cross_encoder_cache[model_name]

                local_docs = search_result.docs
                pairs = [[query, doc.text] for doc in local_docs]
                scores = model.predict(pairs)

            for doc, score in zip(local_docs, scores):
                doc.score = float(score)

            local_docs.sort(key=lambda d: d.score, reverse=True)

            original_top_k = getattr(options, "top_k", None) or 5
            search_result.docs = local_docs[:original_top_k]
            return search_result

        return await asyncio.to_thread(do_rerank)

    def _resolve_model_id(
        self,
        docs: list[DocumentInfo],
        model_id: str | None,
    ) -> str:
        if model_id is not None:
            return model_id
        has_embeddings = any(
            getattr(doc, "embedding", None) is not None for doc in docs
        )
        return "custom" if has_embeddings else self.DEFAULT_MODEL_ID
