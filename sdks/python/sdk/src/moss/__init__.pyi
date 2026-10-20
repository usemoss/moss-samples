from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
    final,
    overload,
)

DocsInput = Union[
    Iterable[DocumentInfo],
    Iterable[Mapping[str, Any]],
    Iterable[os.PathLike[str]],
    str,
    bytes,
    os.PathLike[str],
]
"""`DocumentInfo` objects, dicts, JSON array or JSON Lines text, or `.json`, `.jsonl`, `.ndjson`, `.txt`, `.md` or `.markdown` paths."""

Chunker = Callable[[str], List[str]]
"""Splits one document's text into chunk texts. Each chunk becomes a document `{id}#{n}` with metadata `parentId`."""


@final
class Chunking:
    """Bounded native chunking options. `chunk_size` 200 to 2000 (default 1200); `chunk_overlap` 0 to half of `chunk_size` (default 200, capped at half of `chunk_size`; pages mode only); `mode` `"pages"` or `"sentences"`; `markdown_header_depth` 1 to 6 (default 6)."""

    def __new__(
        cls,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        mode: Literal["pages", "sentences"] = "pages",
        markdown_header_depth: Optional[int] = None,
    ) -> Chunking: ...
    @property
    def chunk_size(self) -> int: ...
    @property
    def chunk_overlap(self) -> int: ...
    @property
    def mode(self) -> str: ...
    @property
    def markdown_header_depth(self) -> int: ...


@dataclass
class ParseFileInput:
    """One file for `MossClient.create_index_from_files`.

    `name` and `content_type` are required, plus `path` (a filesystem path) or
    `data` (raw bytes). `content_type` is `"application/pdf"` or, for DOCX,
    `"application/vnd.openxmlformats-officedocument.wordprocessingml.document"`.
    """

    name: str
    content_type: str
    path: Optional[str] = None
    data: Optional[bytes] = None


@dataclass
class ParseOptions:
    """How the server extracts text from uploaded documents.

    Every field is optional, and an omitted one uses the server default.
    `segmentation_method` is `"smart_layout_detection"` or `"page_by_page"`.
    `use_high_resolution` is slower and more faithful, useful for dense tables.
    `ocr_mode` is `"full_ocr"` for scanned documents with no text layer, or
    `"auto_ocr"` to run OCR only on the pages that appear to need it. `merge_tables`
    joins a table split across a page break into one segment. `chunk_size` is the
    target chunk length in characters, 200 to 2000 (default 1200), and `chunk_overlap`
    the characters consecutive chunks share, 0 to half of `chunk_size` (default 200).
    """

    use_high_resolution: Optional[bool] = None
    segmentation_method: Optional[str] = None
    ocr_mode: Optional[str] = None
    merge_tables: Optional[bool] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None


class MossClient:
    """Semantic search client for vector similarity operations."""

    DEFAULT_MODEL_ID: ClassVar[str]

    def __init__(
        self,
        project_id: str,
        project_key: str,
        *,
        cache_path: Optional[str] = None,
    ) -> None: ...

    async def session(
        self,
        index_name: str,
        model_id: Optional[str] = None,
        *,
        artifact_version: Optional[str] = None,
        manifest_sha256: Optional[str] = None,
        auto_load_on_init: bool = True,
    ) -> SessionIndex:
        """Open a session. Loads the cloud index unless `auto_load_on_init` is False."""
        ...

    async def close(self) -> None:
        """Send the final usage telemetry, then free this client and its sessions."""
        ...

    def __enter__(self) -> MossClient: ...
    def __exit__(self, *exc_info: object) -> None: ...
    async def __aenter__(self) -> MossClient: ...
    async def __aexit__(self, *exc_info: object) -> None: ...

    @overload
    async def create_index(
        self,
        name: str,
        docs: DocsInput,
        model_id: Optional[str] = ...,
        *,
        wait: Literal[True] = ...,
        chunker: Optional[Chunker] = ...,
        chunking: Optional[Chunking] = ...,
    ) -> MutationResult: ...
    @overload
    async def create_index(
        self,
        name: str,
        docs: DocsInput,
        model_id: Optional[str] = ...,
        *,
        wait: Literal[False],
        chunker: Optional[Chunker] = ...,
        chunking: Optional[Chunking] = ...,
    ) -> JobHandle: ...
    @overload
    async def create_index(
        self,
        name: str,
        docs: DocsInput,
        model_id: Optional[str] = ...,
        *,
        wait: bool,
        chunker: Optional[Chunker] = ...,
        chunking: Optional[Chunking] = ...,
    ) -> MutationResult | JobHandle: ...

    async def create_index_from_files(
        self,
        name: str,
        files: List[ParseFileInput],
        model_id: Optional[str] = None,
        parse_options: Optional[ParseOptions] = None,
    ) -> MutationResult:
        """Create an index from PDF or DOCX files the server parses and embeds.

        The server extracts text chunks from the files, embeds them with the
        model and builds the index. A call takes at most 20 files.

        Args:
            name: Name of the new index.
            files: The files to upload.
            model_id: Embedding model, `moss-minilm` by default. `custom` is not
                supported, because the server computes the embeddings.
            parse_options: How the server extracts text. Pass
                `ParseOptions(ocr_mode="full_ocr")` for scanned documents.

        Raises:
            ValueError: If `model_id` is `custom`.
        """
        ...

    async def add_docs(
        self,
        name: str,
        docs: DocsInput,
        options: Optional[MutationOptions] = None,
        *,
        chunker: Optional[Chunker] = None,
        chunking: Optional[Chunking] = None,
    ) -> MutationResult: ...

    async def delete_docs(
        self,
        name: str,
        doc_ids: List[str],
    ) -> MutationResult: ...

    async def get_job_status(self, job_id: str) -> JobStatusResponse: ...

    async def wait_for_job(
        self,
        job_id: str,
        *,
        poll_interval_seconds: float = 2.0,
        timeout_seconds: float = 1800.0,
    ) -> JobStatusResponse: ...

    async def get_index(self, name: str) -> IndexInfo: ...

    async def list_indexes(self) -> List[IndexInfo]: ...

    async def delete_index(self, name: str) -> bool: ...

    async def get_docs(
        self,
        name: str,
        options: Optional[GetDocumentsOptions] = None,
    ) -> List[DocumentInfo]: ...

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
        refresh_cadence: Optional[Literal["daily", "weekly"]] = None,
        model_id: Optional[str] = None,
    ) -> CreateWebSourceResult: ...

    async def list_web_sources(
        self,
        index_name: Optional[str] = None,
    ) -> List[WebSource]: ...

    async def get_web_source(self, source_id: str) -> WebSource: ...

    async def update_web_source(
        self,
        source_id: str,
        *,
        refresh_cadence: Optional[Literal["daily", "weekly", "manual"]] = None,
        root_url: Optional[str] = None,
        include_paths: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None,
        max_depth: Optional[int] = None,
        max_pages: Optional[int] = None,
        resync: Optional[bool] = None,
    ) -> UpdateWebSourceResult: ...

    async def resync_web_source(self, source_id: str) -> ResyncWebSourceResult: ...

    async def delete_web_source(self, source_id: str) -> DeleteWebSourceResult: ...

    async def load_index(
        self,
        name: str,
        auto_refresh: bool = False,
        polling_interval_in_seconds: int = 600,
        cache_path: Optional[str] = None,
    ) -> str: ...

    async def unload_index(self, name: str) -> None: ...

    async def load_indexes(
        self,
        names: List[str],
        auto_refresh: bool = False,
        polling_interval_in_seconds: int = 600,
        cache_path: Optional[str] = None,
    ) -> LoadIndexesResult: ...

    async def unload_indexes(self, names: List[str]) -> None: ...

    async def was_served_stale(self, name: str) -> bool: ...

    async def query(
        self,
        name: str,
        query: str,
        options: Optional[QueryOptions] = None,
    ) -> SearchResult:
        """Search a loaded index in memory.

        A blank query with no options.embedding returns no results at every
        alpha and embeds nothing. With an embedding, a blank query ranks by it.
        """
        ...

    async def query_multi_index(
        self,
        names: List[str],
        query: str,
        options: Optional[QueryOptions] = None,
    ) -> SearchResult:
        """Search across multiple loaded indexes; returns the global top_k.

        All indexes must be loaded and share the same embedding model.
        options.alpha works as in query (default 0.8): 1.0 embedding-only,
        0.0 keyword-only, in between hybrid via Reciprocal Rank Fusion.
        Each result doc carries index_name set to its source index.
        A blank query with no options.embedding returns no results.
        """
        ...


class MossError(RuntimeError):
    """A failure reported by the Moss core.

    `code` is a stable string a caller can branch on: `INVALID_ARGUMENT`,
    `NOT_FOUND`, `UNAUTHORIZED`, `NETWORK`, `DESERIALIZATION`,
    `MODEL_UNAVAILABLE` or `INTERNAL`. The message is fixed for each kind of
    failure. `detail` is the core error text, for logs and support rather
    than a stable contract, or `None` when there is none.
    """

    code: Optional[str]
    detail: Optional[str]


class InvalidArgumentError(MossError, ValueError):
    """A `MossError` with code `INVALID_ARGUMENT`. Also a `ValueError`."""


class ManageApiError(RuntimeError):
    """HTTP error from POST /v1/manage."""

    status: int
    body: str

    def __init__(self, status: int, body: str) -> None: ...


@dataclass(frozen=True)
class WebSource:
    """A web source: a site the service crawls into an index."""

    id: str
    index_name: str
    root_url: str
    max_pages: int
    max_documents: int
    max_depth: int
    respect_robots: bool
    parse_documents: bool
    refresh_cadence: Literal["daily", "weekly", "manual"]
    next_refresh_at: Optional[str]
    last_crawled_at: Optional[str]
    last_page_count: Optional[int]
    last_doc_count: Optional[int]
    status: Literal["idle", "crawling", "failed", "removing"]
    last_error_code: Optional[str]
    include_paths: Optional[List[str]] = None
    exclude_paths: Optional[List[str]] = None
    created_at: Optional[str] = None


@dataclass(frozen=True)
class CreateWebSourceResult(WebSource):
    """The new web source and the `job_id` of its first crawl, for `get_job_status`."""

    job_id: str = field(kw_only=True)


@dataclass(frozen=True)
class UpdateWebSourceResult(WebSource):
    """The updated web source, and the `job_id` of a crawl when `resync` started one."""

    job_id: Optional[str] = field(default=None, kw_only=True)


@dataclass(frozen=True)
class ResyncWebSourceResult:
    """The `job_id` of the crawl a resync started, for `get_job_status`."""

    id: str
    job_id: str
    status: Optional[str] = None
    index_name: Optional[str] = None


@dataclass(frozen=True)
class DeleteWebSourceResult:
    """Whether the web source was deleted. Its index stays.

    `purge_job_id` is the job that removes the source's documents, when one was started.
    """

    deleted: bool
    id: str
    purge_job_id: Optional[str] = None


class SessionIndex:
    """Local in-session index for real-time indexing and querying."""

    @property
    def name(self) -> str:
        """The index name."""
        ...
    @property
    def doc_count(self) -> int:
        """Number of documents in the session."""
        ...
    @property
    def model_id(self) -> str:
        """The embedding model, or "custom". A load moves the session to its model."""
        ...

    async def add_docs(
        self,
        docs: DocsInput,
        options: Optional[MutationOptions] = None,
        *,
        chunker: Optional[Chunker] = None,
        chunking: Optional[Chunking] = None,
    ) -> Tuple[int, int]: ...

    async def delete_docs(self, doc_ids: List[str]) -> int: ...

    async def get_docs(
        self,
        options: Optional[GetDocumentsOptions] = None,
    ) -> List[DocumentInfo]: ...

    async def query(
        self,
        query: str,
        options: Optional[QueryOptions] = None,
    ) -> SearchResult:
        """Search the session in memory.

        A blank query with no options.embedding returns no results at every
        alpha and embeds nothing. With an embedding, a blank query ranks by it.
        """
        ...

    async def push_index(self) -> PushIndexResult: ...

    async def save_to_disk(self, cache_path: Optional[str] = None) -> None:
        """Save the session under `<cache_path>/<name>/` for `load_from_disk`.

        A failed or interrupted save leaves the last saved snapshot loadable.
        A relative `cache_path` resolves against the current working directory,
        and `~` is not expanded. Without `cache_path` the snapshot goes in
        `sessions/<project id>/` under the client's `cache_path`, else
        `MOSS_SESSION_CACHE_PATH`, which only session snapshots read, else `moss`
        in the default cache directory, such as `~/.cache` on macOS and Linux.
        """
        ...

    async def load_from_disk(
        self, cache_path: Optional[str] = None, *, rebuild_legacy: bool = True
    ) -> int:
        """Restore a session saved by `save_to_disk` and return the documents loaded.

        Without `cache_path` it reads the directory `save_to_disk` uses without one.

        The session takes the snapshot's documents and model. With
        `rebuild_legacy` true, a session opened with a built-in model rebuilds
        a snapshot of that model that an older core saved without a model artifact
        identity: it re-embeds the documents and saves the snapshot back, which
        needs the cloud. A rebuild that cannot load the model raises `MossError`
        with code `MODEL_UNAVAILABLE` and changes nothing. With
        `rebuild_legacy=False` such a snapshot loads as a custom-model session.
        """
        ...

    async def close(self) -> None:
        """Send the final usage telemetry, then free the session's native memory."""
        ...

    def __enter__(self) -> SessionIndex: ...
    def __exit__(self, *exc_info: object) -> None: ...
    async def __aenter__(self) -> SessionIndex: ...
    async def __aexit__(self, *exc_info: object) -> None: ...


@final
class PushIndexResult:
    """Result from SessionIndex.push_index()."""

    @property
    def job_id(self) -> str: ...
    @property
    def index_name(self) -> str: ...
    @property
    def doc_count(self) -> int: ...
    @property
    def status(self) -> str: ...


@final
class MutationResult:
    """Return value from create_index/add_docs/delete_docs."""

    @property
    def job_id(self) -> str: ...
    @property
    def index_name(self) -> str: ...
    @property
    def doc_count(self) -> int: ...


class JobHandle:
    """Returned by create_index(..., wait=False) for an in-flight build.

    `client.get_job_status(job_id)` and `client.wait_for_job(job_id)` reach the
    same build from another process.
    """

    def __init__(self, client: MossClient, job_id: str) -> None: ...
    @property
    def job_id(self) -> str: ...
    async def status(self) -> JobStatusResponse: ...
    async def wait(self) -> JobStatusResponse: ...


@final
class MutationOptions:
    """Options for add_docs.

    `upsert` is whether a document replaces a stored one with the same ID.
    `SessionIndex.add_docs` applies it locally and treats `None` as `True`.
    `MossClient.add_docs` sends it only when set, and the cloud service decides how to apply it.
    """

    upsert: Optional[bool]

    def __new__(cls, upsert: Optional[bool] = None) -> MutationOptions: ...


@final
class ParentGrouping:
    """Collapse sibling documents sharing `parent_field` into one result per
    unit, assembled in `order_field` order (numbers first, then text)."""

    parent_field: str
    order_field: str

    def __new__(cls, parent_field: str, order_field: str) -> ParentGrouping: ...


@final
class GetDocumentsOptions:
    """Options for `get_docs`, a deterministic retrieval with no query vector."""

    doc_ids: Optional[List[str]]
    filter: Optional[Dict[str, Any]]
    sort_by: Optional[str]
    ascending: Optional[bool]
    group_by: Optional[ParentGrouping]

    def __new__(
        cls,
        doc_ids: Optional[List[str]] = None,
        filter: Optional[Dict[str, Any]] = None,
        sort_by: Optional[str] = None,
        ascending: Optional[bool] = None,
        group_by: Optional[ParentGrouping] = None,
    ) -> GetDocumentsOptions: ...


@final
class JobStatus:
    """Enum-like class for job status values."""

    PENDING_UPLOAD: ClassVar[str]
    UPLOADING: ClassVar[str]
    BUILDING: ClassVar[str]
    COMPLETED: ClassVar[str]
    FAILED: ClassVar[str]

    @property
    def value(self) -> str: ...


@final
class JobPhase:
    """Enum-like class for job phase values."""

    DOWNLOADING: ClassVar[str]
    DESERIALIZING: ClassVar[str]
    GENERATING_EMBEDDINGS: ClassVar[str]
    BUILDING_INDEX: ClassVar[str]
    UPLOADING: ClassVar[str]
    CLEANUP: ClassVar[str]
    WAITING_FOR_PARSER: ClassVar[str]
    PARSING: ClassVar[str]
    PARSING_COMPLETE: ClassVar[str]
    QUEUED: ClassVar[str]
    CRAWLING: ClassVar[str]
    PARSING_DOCUMENTS: ClassVar[str]

    @property
    def value(self) -> str: ...


@final
class JobProgress:
    """Progress update for a job."""

    @property
    def job_id(self) -> str: ...
    @property
    def status(self) -> JobStatus: ...
    @property
    def progress(self) -> float: ...
    @property
    def current_phase(self) -> Optional[JobPhase]: ...


@final
class JobStatusResponse:
    """Full status response from get_job_status."""

    @property
    def job_id(self) -> str: ...
    @property
    def status(self) -> JobStatus: ...
    @property
    def progress(self) -> float: ...
    @property
    def current_phase(self) -> Optional[JobPhase]: ...
    @property
    def error(self) -> Optional[str]: ...
    @property
    def created_at(self) -> str: ...
    @property
    def updated_at(self) -> str: ...
    @property
    def completed_at(self) -> Optional[str]: ...


@final
class ModelRef:
    id: str
    version: str
    def __new__(cls, id: str, version: str) -> ModelRef: ...


@final
class QueryResultDocumentInfo:
    id: str
    text: str
    metadata: Optional[Dict[str, str]]
    score: float
    """Relevance to the query from 0 to 1.

    It comes from vector similarity alone, so alpha and rank never change it.
    Results are ordered by hybrid relevance, so a lower result can show a
    higher score. A keyword-only query (alpha 0, or an index without vectors)
    scores every hit 0. Scores depend on the embedding model: tune min_score
    on your own queries.
    """
    index_name: Optional[str]
    payload: Optional[str]
    def __new__(
        cls,
        id: str,
        text: str,
        metadata: Optional[Dict[str, str]] = None,
        score: float = 0.0,
        index_name: Optional[str] = None,
        payload: Optional[str] = None,
    ) -> QueryResultDocumentInfo: ...


@final
class DocumentInfo:
    id: str
    text: str
    metadata: Optional[Dict[str, str]]
    embedding: Optional[Sequence[float]]
    payload: Optional[str]
    def __new__(
        cls,
        id: str,
        text: str,
        metadata: Optional[Dict[str, str]] = None,
        embedding: Optional[Sequence[float]] = None,
        payload: Optional[str] = None,
    ) -> DocumentInfo: ...


@final
class QueryOptions:
    embedding: Optional[Sequence[float]]
    """Query vector. At every alpha its components must be finite and its length the index dimension."""
    top_k: Optional[int]
    """Most results to return (5 by default, 10 for query_multi_index); 0 returns none."""
    alpha: Optional[float]
    filter: Optional[Dict[str, Any]]
    group_by: Optional[ParentGrouping]
    min_score: Optional[float]
    """Drops results whose score is below this floor, from 0 to 1.

    A query returns up to top_k results that clear it, in hybrid order.
    Not allowed on keyword-only queries (alpha 0).
    """
    candidate_depth: Optional[int]
    """How many hits a hybrid query ranks on each signal before fusion.

    A hit outside both lists is never returned, so a deeper list raises recall
    and query time. Defaults to 2 * top_k. A set value must be at least 1 and is
    raised to top_k when below it. Keyword-only and vector-only queries (alpha 0
    or 1) ignore it. Used by MossClient.query and query_multi_index.
    SessionIndex.query ignores it.
    """
    def __new__(
        cls,
        embedding: Optional[Sequence[float]] = None,
        top_k: Optional[int] = None,
        alpha: Optional[float] = None,
        filter: Optional[Dict[str, Any]] = None,
        group_by: Optional[ParentGrouping] = None,
        min_score: Optional[float] = None,
        candidate_depth: Optional[int] = None,
    ) -> QueryOptions: ...


@final
class IndexInfo:
    id: str
    name: str
    version: str
    status: str
    doc_count: int
    created_at: str
    updated_at: str
    model: ModelRef
    def __new__(
        cls,
        id: str,
        name: str,
        version: str,
        status: str,
        doc_count: int,
        created_at: str,
        updated_at: str,
        model: ModelRef,
    ) -> IndexInfo: ...


@final
class SearchResult:
    docs: List[QueryResultDocumentInfo]
    query: str
    index_name: Optional[str]
    time_taken_ms: Optional[int]
    model_id: Optional[str]
    """Embedding model of the index the query ran on, when known."""
    def __new__(
        cls,
        docs: List[QueryResultDocumentInfo],
        query: str,
        index_name: Optional[str] = None,
        time_taken_ms: Optional[int] = None,
        model_id: Optional[str] = None,
    ) -> SearchResult: ...


@final
class IndexStatus:
    NotStarted: ClassVar[str]
    Building: ClassVar[str]
    Ready: ClassVar[str]
    Failed: ClassVar[str]
    value: str
    def __new__(cls, value: str) -> IndexStatus: ...


@final
class LoadIndexesResult:
    """Outcome of a load_indexes call. Best-effort: indexes that succeed are
    retained even if others fail."""

    loaded: List[str]
    failed: Dict[str, str]
    """Fixed public message for each index that failed to load."""
    failed_codes: Dict[str, str]
    """Error code, such as `"NOT_FOUND"`, for each index that failed to load."""
    def __new__(
        cls,
        loaded: List[str] = ...,
        failed: Dict[str, str] = ...,
        failed_codes: Dict[str, str] = ...,
    ) -> LoadIndexesResult: ...


IndexStatusValues: Dict[str, str]

__version__: str

__all__ = [
    "MossClient",
    "ParseFileInput",
    "ParseOptions",
    "DocsInput",
    "Chunker",
    "Chunking",
    "SessionIndex",
    "JobHandle",
    "PushIndexResult",
    "ManageApiError",
    "MossError",
    "InvalidArgumentError",
    "WebSource",
    "CreateWebSourceResult",
    "UpdateWebSourceResult",
    "ResyncWebSourceResult",
    "DeleteWebSourceResult",
    # Core data types
    "DocumentInfo",
    "GetDocumentsOptions",
    "ParentGrouping",
    "IndexInfo",
    "SearchResult",
    "QueryResultDocumentInfo",
    "ModelRef",
    "IndexStatus",
    "IndexStatusValues",
    "QueryOptions",
    "LoadIndexesResult",
    # Mutation types
    "MutationResult",
    "MutationOptions",
    "JobStatus",
    "JobPhase",
    "JobProgress",
    "JobStatusResponse",
]
