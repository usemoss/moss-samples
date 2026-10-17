from __future__ import annotations

import asyncio
import inspect
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

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
    QueryOptions,
    QueryResultDocumentInfo,
    SearchResult,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QueryMetrics:
    """
    Metrics and timing data for a single query execution.

    Emitted to user-provided callbacks/sinks when querying an index.

    Attributes:
        index_name: Name of the queried index.
        query: The search query string.
        duration_ms: Total query execution duration in milliseconds.
        result_count: Number of results returned (0 if error or no matches).
        is_local: True if executed locally in-memory via IndexManager, False if fallback to cloud API.
        top_k: Top-k parameter passed to the query, if specified.
        alpha: Alpha parameter (hybrid weight) passed to the query, if specified.
        engine_time_ms: Engine-reported execution time in milliseconds, if available from the search result.
        error: Exception raised during query execution, or None if successful.
    """

    index_name: str
    query: str
    duration_ms: float
    result_count: int
    is_local: bool
    top_k: Optional[int] = None
    alpha: Optional[float] = None
    engine_time_ms: Optional[int] = None
    error: Optional[Exception] = None

    @property
    def is_success(self) -> bool:
        """True if the query completed successfully without raising an exception."""
        return self.error is None

    def as_dict(self) -> Dict[str, Any]:
        """Convert metrics to a dictionary suitable for logging or serialization."""
        return {
            "index_name": self.index_name,
            "query": self.query,
            "duration_ms": self.duration_ms,
            "result_count": self.result_count,
            "is_local": self.is_local,
            "top_k": self.top_k,
            "alpha": self.alpha,
            "engine_time_ms": self.engine_time_ms,
            "is_success": self.is_success,
            "error": str(self.error) if self.error is not None else None,
        }


QueryHook = Callable[[QueryMetrics], Any]


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

    def __init__(
        self,
        project_id: str,
        project_key: str,
        *,
        on_query: Optional[Union[QueryHook, Sequence[QueryHook]]] = None,
    ) -> None:
        self._project_id = project_id
        self._project_key = project_key
        self._on_query = on_query
        self._client_id = str(uuid.uuid4())
        manage_url = _get_manage_url()
        self._manage = ManageClient(
            project_id, project_key, manage_url, self._client_id
        )
        self._manager = IndexManager(
            project_id, project_key, manage_url, self._client_id
        )

    @property
    def on_query(self) -> Optional[Union[QueryHook, Sequence[QueryHook]]]:
        """Get the configured query metrics hook(s)."""
        return self._on_query

    @on_query.setter
    def on_query(self, hook: Optional[Union[QueryHook, Sequence[QueryHook]]]) -> None:
        """Set or update the query metrics hook(s)."""
        self._on_query = hook

    # -- Mutations (via Rust ManageClient) --------------------------

    async def create_index(
        self,
        name: str,
        docs: List[DocumentInfo],
        model_id: Optional[str] = None,
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
        docs: List[DocumentInfo],
        options: Optional[MutationOptions] = None,
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
        doc_ids: List[str],
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

    async def list_indexes(self) -> List[IndexInfo]:
        """List all indexes with their information."""
        return await asyncio.to_thread(self._manage.list_indexes)

    async def delete_index(self, name: str) -> bool:
        """Delete an index and all its data."""
        return await asyncio.to_thread(self._manage.delete_index, name)

    async def get_docs(
        self,
        name: str,
        options: Optional[GetDocumentsOptions] = None,
    ) -> List[DocumentInfo]:
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
        options: Optional[QueryOptions] = None,
        *,
        on_query: Optional[Union[QueryHook, Sequence[QueryHook]]] = None,
    ) -> SearchResult:
        """
        Perform a semantic similarity search.

        If the index is loaded locally (via load_index), queries run in-memory.
        Otherwise, falls back to the cloud query API.

        Args:
            name: Name of the target index to search.
            query: The search query text.
            options: Query options (top_k, alpha, embedding, filter). Example filter:
                QueryOptions(filter={"$and": [
                    {"field": "city", "condition": {"$eq": "NYC"}},
                    {"field": "price", "condition": {"$lt": "50"}},
                ]})
            on_query: Optional callback or sequence of callbacks invoked with QueryMetrics.
        """
        start_time = time.perf_counter()
        is_local = False
        result_count = 0
        engine_time_ms = None
        error: Optional[Exception] = None
        try:
            is_loaded = await asyncio.to_thread(self._manager.has_index, name)

            if is_loaded:
                is_local = True
                result = await self._query_local(name, query, options)
            else:
                is_local = False
                if getattr(options, "filter", None) is not None:
                    logger.warning(
                        "Metadata filter ignored: filtering is only supported for locally loaded indexes. "
                        "Call load_index('%s') first.",
                        name,
                    )
                result = await self._query_cloud(name, query, options)

            result_count = len(result.docs)
            engine_time_ms = result.time_taken_ms
            return result
        except Exception as e:
            error = e
            raise
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            metrics = QueryMetrics(
                index_name=name,
                query=query,
                duration_ms=duration_ms,
                result_count=result_count,
                is_local=is_local,
                top_k=getattr(options, "top_k", None),
                alpha=getattr(options, "alpha", None),
                engine_time_ms=engine_time_ms,
                error=error,
            )
            await self._emit_metrics(
                metrics,
                on_query=on_query,
            )

    async def _emit_metrics(
        self,
        metrics: QueryMetrics,
        on_query: Optional[Union[QueryHook, Sequence[QueryHook]]] = None,
        options_on_query: Optional[Union[QueryHook, Sequence[QueryHook]]] = None,
    ) -> None:
        hooks: List[QueryHook] = []
        for src in (self._on_query, options_on_query, on_query):
            if src is not None:
                if isinstance(src, (list, tuple, set)):
                    for h in src:
                        if callable(h) and h not in hooks:
                            hooks.append(h)
                elif callable(src) and src not in hooks:
                    hooks.append(src)

        for hook in hooks:
            try:
                res = hook(metrics)
                if inspect.isawaitable(res):
                    await res
            except Exception as e:
                logger.warning(
                    "Error executing query metrics hook %r: %s",
                    hook,
                    e,
                    exc_info=True,
                )

    # -- Internal ---------------------------------------------------

    async def _query_local(
        self,
        name: str,
        query: str,
        options: Optional[QueryOptions],
    ) -> SearchResult:
        top_k = getattr(options, "top_k", None)
        if top_k is None:
            top_k = 5
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
        options: Optional[QueryOptions],
    ) -> SearchResult:
        """Fallback: query via the cloud API when the index is not loaded locally."""
        top_k = getattr(options, "top_k", None) or 10
        query_embedding = getattr(options, "embedding", None)

        request_body: Dict[str, Any] = {
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
            raise Exception(f"Cloud query request failed: {str(error)}")

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

    def _resolve_model_id(
        self,
        docs: List[DocumentInfo],
        model_id: Optional[str],
    ) -> str:
        if model_id is not None:
            return model_id
        has_embeddings = any(
            getattr(doc, "embedding", None) is not None for doc in docs
        )
        return "custom" if has_embeddings else self.DEFAULT_MODEL_ID
