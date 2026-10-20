from __future__ import annotations

import asyncio
import unicodedata
import uuid
import weakref
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from moss_core import (
    Chunking,
    DocumentInfo,
    GetDocumentsOptions,
    IndexInfo,
    IndexManager,
    InvalidArgumentError,
    JobStatusResponse,
    LoadIndexesResult,
    ManageClient,
    MossError,
    MutationOptions,
    MutationResult,
    QueryOptions,
    SearchResult,
    to_document_infos,
    validate_index_name,
)

from .docs_input import Chunker, DocsInput, reject_chunking_for_custom
from .job_handle import JobHandle
from .manage_http import request_manage
from .session_index import SessionIndex
from .web_source import (
    CreateRefreshCadence,
    CreateWebSourceResult,
    DeleteWebSourceResult,
    RefreshCadence,
    ResyncWebSourceResult,
    UpdateWebSourceResult,
    WebSource,
    create_web_source_from_public,
    delete_web_source_from_public,
    update_web_source_from_public,
    web_source_from_public,
)


_DEVICE_ID_FILE = ".moss-device-id"
_MAX_IDENTITY_UTF8_BYTES = 256


def _is_valid_identity_id(value: str) -> bool:
    """Whether a persisted id is usable as a device identity.

    Mirrors the JS client's check: non-empty, no surrounding whitespace, at
    most 256 UTF-8 bytes, and free of control, format, or surrogate code points.
    """
    if not value or value.strip() != value:
        return False
    if len(value.encode("utf-8")) > _MAX_IDENTITY_UTF8_BYTES:
        return False
    return not any(
        unicodedata.category(ch) in ("Cc", "Cf", "Cs") or ch == "�"
        for ch in value
    )


def _resolve_cache_path_device_id(cache_path: Optional[str]) -> Optional[str]:
    """Read or create `<cache_path>/.moss-device-id` and return the id.

    An existing valid id is adopted, an invalid one is ignored, and a missing
    file is created with a fresh uuid. Returns `None` when no cache path is
    given or the file cannot be read or written. Mirrors the JS client's
    `resolveCachePathDeviceId`.
    """
    if not cache_path or not cache_path.strip():
        return None
    try:
        target = Path(cache_path) / _DEVICE_ID_FILE
        if target.exists():
            value = target.read_text(encoding="utf-8").strip()
            return value if _is_valid_identity_id(value) else None
        target.parent.mkdir(parents=True, exist_ok=True)
        new_id = str(uuid.uuid4())
        target.write_text(new_id, encoding="utf-8")
        return new_id
    except OSError:
        return None


def _ensure_cache_path_device_id(cache_path: Optional[str]) -> None:
    """Create `<cache_path>/.moss-device-id` when absent, never overwriting it."""
    _resolve_cache_path_device_id(cache_path)


@dataclass
class ParseFileInput:
    """
    Input descriptor for a single file in the parse pipeline.

    Either `path` (filesystem path, server/CLI use) or `data` (raw bytes,
    in-memory or browser use) must be provided. Both `name` and
    `content_type` are required. Supported `content_type` values are
    `"application/pdf"` and
    `"application/vnd.openxmlformats-officedocument.wordprocessingml.document"`
    (DOCX).
    """
    name: str
    content_type: str
    path: Optional[str] = None
    data: Optional[bytes] = None


@dataclass
class ParseOptions:
    """
    Controls how the server extracts text from uploaded documents.

    Every field is optional; omitted fields use the server defaults.

    Use `ocr_mode="full_ocr"` for scanned documents that have no text layer.
    `"auto_ocr"` runs OCR only on pages that appear to need it.

    `chunk_size` is the target length of each chunk in characters, 200 to
    2000 (default 1200). `chunk_overlap` is the number of characters
    consecutive chunks share, 0 to half of `chunk_size` (default 200, capped at
    half of `chunk_size`).
    """

    use_high_resolution: Optional[bool] = None
    segmentation_method: Optional[str] = None
    ocr_mode: Optional[str] = None
    merge_tables: Optional[bool] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None


class MossClient:
    """
    Semantic search client for vector similarity operations.

    All mutations and reads go through the Rust ManageClient.
    Querying runs on the local IndexManager; an index must be loaded with
    load_index() (or load_indexes()) before it can be queried. Call close(),
    or use the client as a context manager, to send the final usage report.

    Example:
        ```python
        from moss import MossClient, DocumentInfo

        async with MossClient("project-id", "project-key") as client:
            docs = [DocumentInfo(id="1", text="Machine learning fundamentals")]
            result = await client.create_index("my-index", docs, "moss-minilm")

            await client.load_index("my-index")
            results = await client.query("my-index", "AI and neural networks")
        ```
    """

    DEFAULT_MODEL_ID = "moss-minilm"

    _closed = False

    def __init__(
        self,
        project_id: str,
        project_key: str,
        *,
        cache_path: Optional[str] = None,
    ) -> None:
        """Create a client.

        `cache_path` is a client-level default for the on-disk index cache and
        the `.moss-device-id` directory. A per-call `cache_path` on
        `load_index` / `load_indexes` overrides it; it overrides the native
        default (`~/.moss`). Sessions from this client save to
        `<cache_path>/sessions/<project id>/` when `save_to_disk` gets no directory.
        Parity with the JS SDK's `MossClientOptions`.
        """
        self._project_id = project_id
        self._project_key = project_key
        self._cache_path = cache_path
        self._client_id = str(uuid.uuid4())
        self._manage = ManageClient(project_id, project_key, client_id=self._client_id)
        self._manager = IndexManager(project_id, project_key, client_id=self._client_id)
        self._sessions: "weakref.WeakSet[SessionIndex]" = weakref.WeakSet()
        # Adopt the client cache_path's persistent device identity now, before
        # any load. Otherwise a session() opened first reads and pins the native
        # home-directory default, and later cache-path adoption is a no-op, so
        # session-first deployments would bill under the wrong device. The id is
        # pinned once here; per-call load precedence is unchanged. Mirrors the
        # JS client, which adopts the cache_path id at construction.
        cache_path_device_id = _resolve_cache_path_device_id(cache_path)
        if cache_path_device_id is not None:
            self._manager.set_identity(None, None, cache_path_device_id)

    # -- Mutations (via Rust ManageClient) --------------------------

    async def create_index(
        self,
        name: str,
        docs: DocsInput,
        model_id: Optional[str] = None,
        *,
        wait: bool = True,
        chunker: Optional[Chunker] = None,
        chunking: Optional[Chunking] = None,
    ) -> "MutationResult | JobHandle":
        """Create a new index and populate it with documents.

        `docs` can be `DocumentInfo` objects, dicts with the same fields, JSON array or
        JSON Lines text, or paths to `.json`, `.jsonl`, `.ndjson`, `.txt`, `.md` or
        `.markdown` files. Text and markdown files are chunked natively into documents
        `{path}#{n}` with metadata `parentId`. `chunker`, a function from text to a list
        of chunk texts, replaces that and applies to every document. `chunking`, a `Chunking`, chunks with bounded native options instead (it also chunks `DocumentInfo`, dict and JSON input); pass `chunker` or `chunking`, not both.

        With `wait=True` (default) this blocks until the build finishes and
        returns a `MutationResult`. With `wait=False` it submits the
        build and returns a `JobHandle` immediately (fire-and-forget):
        poll it with `handle.status()` / `handle.wait()`, or reconnect later
        via `get_job_status(handle.job_id)` / `wait_for_job(handle.job_id)`.

        `wait` is keyword-only so a stray positional argument can't silently
        flip the return type.
        """
        self._ensure_open()
        reject_chunking_for_custom(chunker, chunking, model_id)
        resolved_docs = await asyncio.to_thread(to_document_infos, docs, chunker, chunking)
        resolved_model_id = self._resolve_model_id(resolved_docs, model_id)
        if wait:
            return await asyncio.to_thread(
                self._manage.create_index, name, resolved_docs, resolved_model_id,
            )
        submitted = await asyncio.to_thread(
            self._manage.submit_index, name, resolved_docs, resolved_model_id,
        )
        return JobHandle(self, submitted.job_id)

    async def create_index_from_files(
        self,
        name: str,
        files: List[ParseFileInput],
        model_id: Optional[str] = None,
        parse_options: Optional[ParseOptions] = None,
    ) -> MutationResult:
        """
        Create a new index by uploading raw files (PDF or DOCX) for
        server-side parsing and embedding.

        The server parses the files, generates text chunks, embeds them using the
        specified model, and builds a searchable index. At most 20 files per call.

        Args:
            name: Name for the new index.
            files: List of ParseFileInput — each requires a name and content_type,
                   plus at least one of path (filesystem path) or data (raw bytes).
            model_id: Embedding model. Defaults to 'moss-minilm'. 'custom' is not
                      supported because the parse pipeline generates embeddings
                      server-side.
            parse_options: Optional extraction controls. Pass
                      ParseOptions(ocr_mode="full_ocr") for scanned documents
                      with no text layer, and chunk_size / chunk_overlap
                      (characters) to control how the text is split.

        Raises:
            ValueError: If model_id is 'custom'.
        """
        self._ensure_open()
        resolved = model_id or self.DEFAULT_MODEL_ID
        if resolved == "custom":
            raise ValueError(
                "create_index_from_files does not support model_id='custom' — "
                "the parse pipeline generates embeddings server-side. "
                "Use create_index() with pre-computed embeddings instead."
            )
        from moss_core import ParseFileInput as CoreParseFileInput
        core_files = [
            CoreParseFileInput(f.name, f.content_type, path=f.path, data=f.data)
            for f in files
        ]
        core_options = None
        if parse_options is not None:
            from moss_core import ParseOptions as CoreParseOptions

            core_options = CoreParseOptions(
                use_high_resolution=parse_options.use_high_resolution,
                segmentation_method=parse_options.segmentation_method,
                ocr_mode=parse_options.ocr_mode,
                merge_tables=parse_options.merge_tables,
                chunk_size=parse_options.chunk_size,
                chunk_overlap=parse_options.chunk_overlap,
            )
        return await asyncio.to_thread(
            self._manage.create_index_from_files,
            name,
            core_files,
            resolved,
            core_options,
        )

    async def add_docs(
        self,
        name: str,
        docs: DocsInput,
        options: Optional[MutationOptions] = None,
        *,
        chunker: Optional[Chunker] = None,
        chunking: Optional[Chunking] = None,
    ) -> MutationResult:
        """Add or update documents in an index. `docs`, `chunker` and `chunking` work as in `create_index`."""
        self._ensure_open()
        resolved_docs = await asyncio.to_thread(to_document_infos, docs, chunker, chunking)
        return await asyncio.to_thread(
            self._manage.add_docs, name, resolved_docs, options,
        )

    async def delete_docs(
        self,
        name: str,
        doc_ids: List[str],
    ) -> MutationResult:
        """Delete documents from an index by their IDs."""
        self._ensure_open()
        return await asyncio.to_thread(
            self._manage.delete_docs, name, doc_ids,
        )

    async def get_job_status(self, job_id: str) -> JobStatusResponse:
        """Get the status of a bulk operation job."""
        self._ensure_open()
        return await asyncio.to_thread(self._manage.get_job_status, job_id)

    async def wait_for_job(
        self,
        job_id: str,
        *,
        poll_interval_seconds: float = 2.0,
        timeout_seconds: float = 1800.0,
    ) -> JobStatusResponse:
        """Block until a submitted build job reaches a terminal state.

        Polls `get_job_status()` on an interval (parking no threads), so a
        caller holding only a `job_id` — e.g. reconnecting in a fresh process
        after `create_index(..., wait=False)` — can block on it, not just poll.

        Returns the terminal `JobStatusResponse` on success.

        Raises:
            RuntimeError: if the job ends in a `failed` state.
            TimeoutError: if it does not finish within `timeout_seconds`.
        """
        self._ensure_open()
        elapsed = 0.0
        while True:
            status = await self.get_job_status(job_id)
            state = status.status.value
            if state == "completed":
                return status
            if state == "failed":
                raise RuntimeError(
                    f"Moss job {job_id} failed: {getattr(status, 'error', None)}"
                )
            if elapsed >= timeout_seconds:
                raise TimeoutError(
                    f"Moss job {job_id} did not finish within {int(timeout_seconds)}s"
                )
            await asyncio.sleep(poll_interval_seconds)
            elapsed += poll_interval_seconds

    # -- Read operations (via Rust ManageClient) --------------------

    async def get_index(self, name: str) -> IndexInfo:
        """Get information about a specific index."""
        self._ensure_open()
        return await asyncio.to_thread(self._manage.get_index, name)

    async def list_indexes(self) -> List[IndexInfo]:
        """List all indexes with their information."""
        self._ensure_open()
        return await asyncio.to_thread(self._manage.list_indexes)

    async def delete_index(self, name: str) -> bool:
        """Delete an index and all its data."""
        self._ensure_open()
        return await asyncio.to_thread(self._manage.delete_index, name)

    async def get_docs(
        self,
        name: str,
        options: Optional[GetDocumentsOptions] = None,
    ) -> List[DocumentInfo]:
        """Retrieve documents from an index."""
        self._ensure_open()
        return await asyncio.to_thread(self._manage.get_docs, name, options)

    # -- Web sources (pure HTTP /v1/manage, X-Project-Key) ----------

    async def create_web_source(
        self,
        root_url: str,
        index_name: str,
        *,
        max_pages: Optional[int] = None,
        max_documents: Optional[int] = None,
        max_depth: Optional[int] = None,
        include_paths: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None,
        respect_robots: Optional[bool] = None,
        parse_documents: Optional[bool] = None,
        refresh_cadence: Optional[CreateRefreshCadence] = None,
        model_id: Optional[str] = None,
    ) -> CreateWebSourceResult:
        """POST `createWebSource` and return the typed source plus `job_id`.

        Poll with `get_job_status()`. Server-release notes: see the
        package README Web sources section.
        """
        self._ensure_open()
        validate_index_name(index_name)
        payload = {
            "rootUrl": root_url,
            "indexName": index_name,
            "maxPages": max_pages,
            "maxDocuments": max_documents,
            "maxDepth": max_depth,
            "includePaths": include_paths,
            "excludePaths": exclude_paths,
            "respectRobots": respect_robots,
            "parseDocuments": parse_documents,
            "refreshCadence": refresh_cadence,
            "modelId": model_id,
        }
        data = await asyncio.to_thread(
            request_manage,
            self._project_id,
            self._project_key,
            "createWebSource",
            payload,
        )
        return create_web_source_from_public(data)

    async def list_web_sources(
        self,
        index_name: Optional[str] = None,
    ) -> List[WebSource]:
        """POST `listWebSources` and return the typed sources.

        When `index_name` is given, only sources for that index are returned.
        """
        self._ensure_open()
        payload = {"indexName": index_name} if index_name is not None else None
        data = await asyncio.to_thread(
            request_manage,
            self._project_id,
            self._project_key,
            "listWebSources",
            payload,
        )
        sources = [
            web_source_from_public(item) for item in (data.get("sources") or [])
        ]
        if index_name is None:
            return sources
        return [source for source in sources if source.index_name == index_name]

    async def get_web_source(self, source_id: str) -> WebSource:
        """POST `getWebSource` and return the typed source."""
        self._ensure_open()
        data = await asyncio.to_thread(
            request_manage,
            self._project_id,
            self._project_key,
            "getWebSource",
            {"sourceId": source_id},
        )
        return web_source_from_public(data)

    async def update_web_source(
        self,
        source_id: str,
        *,
        refresh_cadence: Optional[RefreshCadence] = None,
        root_url: Optional[str] = None,
        include_paths: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None,
        max_depth: Optional[int] = None,
        max_pages: Optional[int] = None,
        resync: Optional[bool] = None,
    ) -> UpdateWebSourceResult:
        """POST `updateWebSource` and return the typed source.

        `job_id` is present when `resync` is true and the server enqueued
        a crawl; poll with `get_job_status()`. `refresh_cadence` is live
        today. Other fields: see the package README Web sources section.
        """
        self._ensure_open()
        payload = {
            "sourceId": source_id,
            "refreshCadence": refresh_cadence,
            "rootUrl": root_url,
            "includePaths": include_paths,
            "excludePaths": exclude_paths,
            "maxDepth": max_depth,
            "maxPages": max_pages,
            "resync": resync,
        }
        data = await asyncio.to_thread(
            request_manage,
            self._project_id,
            self._project_key,
            "updateWebSource",
            payload,
        )
        return update_web_source_from_public(data)

    async def resync_web_source(self, source_id: str) -> ResyncWebSourceResult:
        """POST `resyncWebSource` and return `job_id` for `get_job_status()`.

        See the package README Web sources section.
        """
        self._ensure_open()
        data = await asyncio.to_thread(
            request_manage,
            self._project_id,
            self._project_key,
            "resyncWebSource",
            {"sourceId": source_id},
        )
        return ResyncWebSourceResult(
            id=str(data["id"]),
            job_id=str(data["jobId"]),
            status=data.get("status"),
            index_name=data.get("indexName"),
        )

    async def delete_web_source(self, source_id: str) -> DeleteWebSourceResult:
        """POST `deleteWebSource` and return `deleted` plus `id`.

        `purge_job_id` is present when a purge was enqueued; poll with
        `get_job_status()`. Does not delete the index.
        """
        self._ensure_open()
        data = await asyncio.to_thread(
            request_manage,
            self._project_id,
            self._project_key,
            "deleteWebSource",
            {"sourceId": source_id},
        )
        return delete_web_source_from_public(data, source_id)

    # -- Index loading & querying -----------------------------------

    async def load_index(
        self,
        name: str,
        auto_refresh: bool = False,
        polling_interval_in_seconds: int = 600,
        cache_path: Optional[str] = None,
    ) -> str:
        """
        Downloads an index from the cloud into memory for fast local querying.

        query() requires the index to be loaded; queries then run entirely
        in-memory (~1-10ms) with no network round-trip.

        `cache_path` persists the downloaded index under that directory and
        reuses it on later loads while the cloud copy is unchanged, so restarts
        skip the download. Auto-refresh writes through to the same cache. The
        cloud is still contacted on every load to check for a newer version.
        When omitted, the client-level `cache_path` is used.
        """
        self._ensure_open()
        effective_cache_path = cache_path if cache_path is not None else self._cache_path
        _ensure_cache_path_device_id(effective_cache_path)
        try:
            # The transactional core warms the query model during load_index,
            # so there is no separate warm call here. A second load_query_model
            # would re-raise the stale-warm failure that a stale-but-successful
            # load deliberately tolerates.
            await asyncio.to_thread(
                self._manager.load_index,
                name,
                auto_refresh,
                polling_interval_in_seconds,
                effective_cache_path,
            )
            return name
        except MossError:
            raise
        except RuntimeError as e:
            raise RuntimeError(f"Failed to load index '{name}': {e}") from e

    async def unload_index(self, name: str) -> None:
        """Unload an index from memory."""
        self._ensure_open()
        try:
            await asyncio.to_thread(self._manager.unload_index, name)
        except MossError:
            raise
        except RuntimeError as e:
            raise RuntimeError(f"Failed to unload index '{name}': {e}") from e

    async def load_indexes(
        self,
        names: List[str],
        auto_refresh: bool = False,
        polling_interval_in_seconds: int = 600,
        cache_path: Optional[str] = None,
    ) -> LoadIndexesResult:
        """
        Bulk-load many indexes into memory. Best-effort: failures on individual
        names do not roll back successes. Returns a LoadIndexesResult with
        `loaded` (list of names) and `failed` (dict mapping name -> error).

        `auto_refresh`, `polling_interval_in_seconds` and `cache_path`
        apply uniformly to the whole batch (see `load_index`). A per-call
        `cache_path` overrides the client-level one. The embedding model
        warm-up is deduplicated across successfully-loaded indexes that share a
        model.
        """
        self._ensure_open()
        effective_cache_path = cache_path if cache_path is not None else self._cache_path
        _ensure_cache_path_device_id(effective_cache_path)
        return await asyncio.to_thread(
            self._manager.load_indexes,
            names,
            auto_refresh,
            polling_interval_in_seconds,
            effective_cache_path,
        )

    async def unload_indexes(self, names: List[str]) -> None:
        """Bulk-unload many indexes. Idempotent for names that aren't loaded."""
        self._ensure_open()
        await asyncio.to_thread(self._manager.unload_indexes, names)

    async def was_served_stale(self, name: str) -> bool:
        """Whether `name` is currently served from a stale on-disk snapshot.

        `True` when the index was loaded from cache because the cloud was
        unreachable, before any refresh reconfirmed it. The refresh poller,
        which a stale load starts on its own, clears this once the cloud
        returns. Raises `RuntimeError` when the index is not loaded.

        While the cloud is unreachable, a built-in embedding model cannot be
        opened, so text queries with `alpha` above 0 fail. Keyword-only
        queries (`alpha` 0) and queries that pass their own `embedding` keep
        working, and a later refresh or query warms the model once the cloud returns.
        """
        self._ensure_open()
        return await asyncio.to_thread(self._manager.was_served_stale, name)

    async def query(
        self,
        name: str,
        query: str,
        options: Optional[QueryOptions] = None,
    ) -> SearchResult:
        """
        Perform a semantic similarity search against a locally loaded index.

        The index must have been loaded with `load_index` / `load_indexes`;
        queries run in-memory with no network round-trip. Querying an index
        that is not loaded raises `MossError` with code `NOT_FOUND`.

        A blank `query` (empty or only whitespace) with no
        `options.embedding` returns no results at every `alpha`, without
        running the embedding model. With an embedding, a blank `query` ranks
        by the embedding alone. An embedding holding NaN or infinity, or one
        whose length differs from the index dimension, raises at every `alpha`.

        Args:
            options: Query options (top_k, alpha, embedding, filter, min_score,
                candidate_depth). top_k defaults to 5, and 0 returns no results.
                Each result's score is its relevance to the query from 0 to 1.
                Results are ordered by hybrid relevance, so a lower result can
                show a higher score. min_score drops results below the floor;
                a query returns up to top_k results that clear it, in hybrid
                order. candidate_depth sets how many hits a hybrid query ranks
                on each signal before fusion (default 2 * top_k); keyword-only
                and vector-only queries ignore it. Example filter:
                QueryOptions(filter={"$and": [
                    {"field": "city", "condition": {"$eq": "NYC"}},
                    {"field": "price", "condition": {"$lt": "50"}},
                ]})
        """
        self._ensure_open()
        is_loaded = await asyncio.to_thread(self._manager.has_index, name)
        if not is_loaded:
            error = MossError(
                f"Index '{name}' is not loaded. Call load_index('{name}') or "
                "load_indexes([...]) before querying; queries run locally and "
                "there is no cloud query fallback."
            )
            error.code = "NOT_FOUND"
            raise error

        # An unload_index racing the check above makes the local query fail
        # with the core's typed "Index not loaded" error, which is surfaced as-is.
        return await self._query_local(name, query, options)

    async def query_multi_index(
        self,
        names: List[str],
        query: str,
        options: Optional[QueryOptions] = None,
    ) -> SearchResult:
        """
        Search across multiple loaded indexes and return the global top-K.

        All requested indexes must be loaded locally (via `load_index` /
        `load_indexes`) and share the same embedding model. Each result
        document is tagged with its source `index_name`.

        `options.alpha` selects the signal mix exactly as in single-index
        `query` (default `0.8`): `1.0` is embedding-only, `0.0` is
        keyword-only, and values in between fuse both signals. Each result's
        `score` is its relevance to the query from 0 to 1, as in
        single-index `query`. Results are ordered by hybrid relevance,
        so a lower result can show a higher score. `min_score` drops results
        below the floor; a query returns up to `top_k` results that clear it,
        in hybrid order. Keyword scoring runs each index's own BM25 and merges
        the hits by score before fusion, so BM25 statistics stay per-corpus
        (the same per-shard merge search engines use by default).
        Keyword-only queries never embed the text, so they also work on
        custom-model indexes without `options.embedding`. A blank `query`
        with no `options.embedding` returns no results and embeds nothing.
        `options.top_k` of 0 returns no results.

        `options.top_k` is the **global** cap across the merged result, not
        per-index. `options.filter` and `options.embedding` work as in
        single-index `query`.

        Args:
            names: Names of indexes to search; must be non-empty and all loaded.
            query: The query text.
            options: Query options (top_k, alpha, embedding, filter, min_score,
                candidate_depth). `candidate_depth` sets the length of each
                global per-signal list before fusion, as in `query`.

        Returns:
            A `SearchResult` whose `docs` carry `index_name` set per result.
        """
        self._ensure_open()
        if not names:
            raise InvalidArgumentError("query_multi_index requires at least one index name")

        top_k_raw = getattr(options, "top_k", None)
        top_k = 10 if top_k_raw is None else top_k_raw
        alpha_raw = getattr(options, "alpha", None)
        alpha = 0.8 if alpha_raw is None else alpha_raw
        query_embedding = getattr(options, "embedding", None)
        filter = getattr(options, "filter", None)
        min_score = getattr(options, "min_score", None)
        candidate_depth = getattr(options, "candidate_depth", None)

        if query_embedding is not None:
            return await asyncio.to_thread(
                self._manager.query_multi_index,
                names,
                query,
                list(query_embedding),
                top_k,
                filter,
                alpha=alpha,
                min_score=min_score,
                candidate_depth=candidate_depth,
            )

        # An index that cannot embed text raises InvalidArgumentError, a ValueError.
        return await asyncio.to_thread(
            self._manager.query_multi_index_text,
            names,
            query,
            top_k,
            filter,
            alpha=alpha,
            min_score=min_score,
            candidate_depth=candidate_depth,
        )

    # -- Local in-session indexing ----------------------------------

    async def session(
        self,
        index_name: str,
        model_id: Optional[str] = None,
        *,
        artifact_version: Optional[str] = None,
        manifest_sha256: Optional[str] = None,
        auto_load_on_init: bool = True,
    ) -> SessionIndex:
        """
        Create or resume a local session index.

        If a cloud index with the given name already exists, it is automatically
        loaded into the session, and the session takes its model. If not, the
        session starts empty. In both cases the workflow is the same: add new
        docs, query, push at the end.

        With `auto_load_on_init=False` the session skips that load and
        starts empty with `model_id`, so `load_from_disk` can restore it
        with no index download. A `push_index` before any load replaces the
        cloud index with this session's documents.

        Args:
            index_name: Cloud index name. Used to check for an existing index on
                        creation and as the push target when push_index() is called.
            model_id: Embedding model to use locally. Defaults to "moss-minilm".
                      Other options: "moss-mediumlm", "custom".
            artifact_version: Immutable publisher version for a foundation model.
            manifest_sha256: Authoritative SHA-256 of that version's publisher manifest.
            auto_load_on_init: Load an existing cloud index into the session
                      before returning. Defaults to True.

        Returns:
            SessionIndex: A local index ready to use.

        Raises:
            RuntimeError: If project credentials are invalid.
            ValueError: If an existing cloud index uses a different model than
                        the explicit model_id passed to session().
        """
        self._ensure_open()
        resolved_model_id = model_id or self.DEFAULT_MODEL_ID

        session = SessionIndex._create(
            name=index_name,
            model_id=resolved_model_id,
            project_id=self._project_id,
            project_key=self._project_key,
            client_id=self._client_id,
            artifact_version=artifact_version,
            manifest_sha256=manifest_sha256,
            client_cache_path=self._cache_path,
        )
        self._sessions.add(session)
        try:
            self._apply_session_identity(session)

            # Load from cloud if the index exists. This downloads the binary
            # artifact and deserializes it in place (no re-embedding).
            # Returns 0 silently if the index does not exist yet. An existing
            # index, even an empty one, moves the session to its model.
            if auto_load_on_init:
                await asyncio.to_thread(session._inner.load_index, index_name)
                if model_id is not None and session.model_id != resolved_model_id:
                    raise ValueError(
                        f"Existing session index '{index_name}' uses "
                        f"model_id='{session.model_id}', but session() was called "
                        f"with model_id='{resolved_model_id}'. Omit model_id to adopt "
                        "the stored model or pass the matching model_id."
                    )

            # Pre-warm the embedding model so the first add_docs call is fast.
            # Model loading (~100-150ms) is paid once here rather than hidden
            # inside the first add_docs.
            if session.model_id != "custom":
                await session._get_embedding_service()
        except Exception:
            self._sessions.discard(session)
            await session.close()
            raise

        return session

    # -- Lifecycle --------------------------------------------------

    async def close(self) -> None:
        """
        Send the final usage telemetry and free the native memory of this client and its sessions.

        Closes every live session this client opened, and the index manager, together,
        waiting until their telemetry is delivered or 2 seconds pass. Safe to call more
        than once. Afterwards every method raises `RuntimeError`. Leaving an
        `async with` or `with` block calls it.
        """
        await asyncio.gather(*(asyncio.to_thread(close) for close in self._begin_close()))

    def __enter__(self) -> "MossClient":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        closes = self._begin_close()
        with ThreadPoolExecutor(max_workers=len(closes) or 1) as pool:
            list(pool.map(lambda close: close(), closes))

    async def __aenter__(self) -> "MossClient":
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    # -- Internal ---------------------------------------------------

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("MossClient is closed")

    def _begin_close(self) -> List[Callable[[], None]]:
        """Mark the client closed and return the native closes it still has to run."""
        if self._closed:
            return []
        self._closed = True
        closes: List[Callable[[], None]] = [session._inner.close for session in self._sessions]
        self._sessions.clear()
        closes.append(self._manager.close)
        return closes

    def _apply_session_identity(self, session: SessionIndex) -> None:
        """Copy the manager's resolved device identity onto a new session."""
        device_id, moss_device_id = self._manager.device_identity()
        if device_id is None and moss_device_id is None:
            return
        session._inner.set_identity(device_id, None, moss_device_id)

    async def _query_local(
        self,
        name: str,
        query: str,
        options: Optional[QueryOptions],
    ) -> SearchResult:
        top_k_raw = getattr(options, "top_k", None)
        top_k = 5 if top_k_raw is None else top_k_raw
        alpha_raw = getattr(options, "alpha", None)
        alpha = 0.8 if alpha_raw is None else alpha_raw
        query_embedding = getattr(options, "embedding", None)
        filter = getattr(options, "filter", None)
        min_score = getattr(options, "min_score", None)
        candidate_depth = getattr(options, "candidate_depth", None)

        if query_embedding is None:
            # An index that cannot embed text raises InvalidArgumentError, a ValueError.
            return await asyncio.to_thread(
                self._manager.query_text,
                name,
                query,
                top_k,
                alpha,
                filter,
                min_score,
                candidate_depth,
            )

        return await asyncio.to_thread(
            self._manager.query,
            name,
            query,
            list(query_embedding),
            top_k,
            alpha,
            filter,
            min_score,
            candidate_depth,
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
