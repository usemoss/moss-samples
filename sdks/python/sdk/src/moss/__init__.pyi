from __future__ import annotations

from typing import Any, Callable, ClassVar, Dict, List, Optional, Sequence, Union

QueryHook = Callable[[QueryMetrics], Any]

class QueryMetrics:
    index_name: str
    query: str
    duration_ms: float
    result_count: int
    is_local: bool
    top_k: Optional[int]
    alpha: Optional[float]
    engine_time_ms: Optional[int]
    error: Optional[Exception]

    def __init__(
        self,
        index_name: str,
        query: str,
        duration_ms: float,
        result_count: int,
        is_local: bool,
        top_k: Optional[int] = None,
        alpha: Optional[float] = None,
        engine_time_ms: Optional[int] = None,
        error: Optional[Exception] = None,
    ) -> None: ...
    @property
    def is_success(self) -> bool: ...
    def as_dict(self) -> Dict[str, Any]: ...

class MossClient:
    """Semantic search client for vector similarity operations."""

    DEFAULT_MODEL_ID: ClassVar[str]

    def __init__(
        self,
        project_id: str,
        project_key: str,
        *,
        on_query: Optional[Union[QueryHook, Sequence[QueryHook]]] = None,
    ) -> None: ...
    @property
    def on_query(self) -> Optional[Union[QueryHook, Sequence[QueryHook]]]: ...
    @on_query.setter
    def on_query(
        self, hook: Optional[Union[QueryHook, Sequence[QueryHook]]]
    ) -> None: ...
    async def create_index(
        self,
        name: str,
        docs: List[DocumentInfo],
        model_id: Optional[str] = ...,
    ) -> MutationResult: ...
    async def add_docs(
        self,
        name: str,
        docs: List[DocumentInfo],
        options: Optional[MutationOptions] = None,
    ) -> MutationResult: ...
    async def delete_docs(
        self,
        name: str,
        doc_ids: List[str],
    ) -> MutationResult: ...
    async def get_job_status(self, job_id: str) -> JobStatusResponse: ...
    async def get_index(self, name: str) -> IndexInfo: ...
    async def list_indexes(self) -> List[IndexInfo]: ...
    async def delete_index(self, name: str) -> bool: ...
    async def get_docs(
        self,
        name: str,
        options: Optional[GetDocumentsOptions] = None,
    ) -> List[DocumentInfo]: ...
    async def load_index(
        self,
        name: str,
        auto_refresh: bool = False,
        polling_interval_in_seconds: int = 600,
    ) -> str: ...
    async def unload_index(self, name: str) -> None: ...
    async def query(
        self,
        name: str,
        query: str,
        options: Optional[QueryOptions] = None,
        *,
        on_query: Optional[Union[QueryHook, Sequence[QueryHook]]] = None,
    ) -> SearchResult: ...

class MutationResult:
    """Return value from create_index/add_docs/delete_docs."""

    job_id: str
    index_name: str
    doc_count: int

class MutationOptions:
    """Options for add_docs (e.g. upsert behavior)."""

    upsert: Optional[bool]

    def __init__(self, upsert: Optional[bool] = None) -> None: ...

class GetDocumentsOptions:
    """Options for get_docs (e.g. filter by document IDs)."""

    doc_ids: Optional[List[str]]

    def __init__(self, doc_ids: Optional[List[str]] = None) -> None: ...

class JobStatus:
    """Enum-like class for job status values."""

    PENDING_UPLOAD: ClassVar[str]
    UPLOADING: ClassVar[str]
    BUILDING: ClassVar[str]
    COMPLETED: ClassVar[str]
    FAILED: ClassVar[str]

    value: str

class JobPhase:
    """Enum-like class for job phase values."""

    DOWNLOADING: ClassVar[str]
    DESERIALIZING: ClassVar[str]
    GENERATING_EMBEDDINGS: ClassVar[str]
    BUILDING_INDEX: ClassVar[str]
    UPLOADING: ClassVar[str]
    CLEANUP: ClassVar[str]

    value: str

class JobProgress:
    """Progress update for a job."""

    job_id: str
    status: JobStatus
    progress: float
    current_phase: Optional[JobPhase]

class JobStatusResponse:
    """Full status response from get_job_status."""

    job_id: str
    status: JobStatus
    progress: float
    current_phase: Optional[JobPhase]
    error: Optional[str]
    created_at: str
    updated_at: str
    completed_at: Optional[str]

class ModelRef:
    id: str
    version: str
    def __init__(self, id: str, version: str) -> None: ...

class QueryResultDocumentInfo:
    id: str
    text: str
    metadata: Optional[Dict[str, str]]
    score: float
    def __init__(
        self,
        id: str,
        text: str,
        metadata: Optional[Dict[str, str]] = ...,
        score: float = ...,
    ) -> None: ...

class DocumentInfo:
    id: str
    text: str
    metadata: Optional[Dict[str, str]]
    embedding: Optional[Sequence[float]]
    def __init__(
        self,
        id: str,
        text: str,
        metadata: Optional[Dict[str, str]] = ...,
        embedding: Optional[Sequence[float]] = ...,
    ) -> None: ...

class QueryOptions:
    embedding: Optional[Sequence[float]]
    top_k: Optional[int]
    alpha: Optional[float]
    filter: Optional[dict]
    def __init__(
        self,
        embedding: Optional[Sequence[float]] = ...,
        top_k: Optional[int] = ...,
        alpha: Optional[float] = ...,
        filter: Optional[dict] = ...,
    ) -> None: ...

class IndexInfo:
    id: str
    name: str
    version: str
    status: str
    doc_count: int
    created_at: str
    updated_at: str
    model: ModelRef
    def __init__(
        self,
        id: str,
        name: str,
        version: str,
        status: str,
        doc_count: int,
        created_at: str,
        updated_at: str,
        model: ModelRef,
    ) -> None: ...

class SearchResult:
    docs: List[QueryResultDocumentInfo]
    query: str
    index_name: Optional[str]
    time_taken_ms: Optional[int]
    def __init__(
        self,
        docs: List[QueryResultDocumentInfo],
        query: str,
        index_name: Optional[str] = None,
        time_taken_ms: Optional[int] = None,
    ) -> None: ...

class IndexStatus:
    NotStarted: ClassVar[str]
    Building: ClassVar[str]
    Ready: ClassVar[str]
    Failed: ClassVar[str]
    def __init__(self, value: str) -> None: ...

IndexStatusValues: Dict[str, str]

__version__: str

__all__ = [
    "MossClient",
    "QueryHook",
    "QueryMetrics",
    "DocumentInfo",
    "GetDocumentsOptions",
    "IndexInfo",
    "SearchResult",
    "QueryResultDocumentInfo",
    "ModelRef",
    "IndexStatus",
    "IndexStatusValues",
    "QueryOptions",
    "MutationResult",
    "MutationOptions",
    "JobStatus",
    "JobPhase",
    "JobProgress",
    "JobStatusResponse",
]
