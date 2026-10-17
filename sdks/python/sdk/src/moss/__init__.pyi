from collections.abc import Sequence
from typing import ClassVar

class MossClient:
    """Semantic search client for vector similarity operations."""

    DEFAULT_MODEL_ID: ClassVar[str]

    def __init__(self, project_id: str, project_key: str) -> None: ...
    async def create_index(
        self,
        name: str,
        docs: list[DocumentInfo],
        model_id: str | None = ...,
    ) -> MutationResult: ...
    async def add_docs(
        self,
        name: str,
        docs: list[DocumentInfo],
        options: MutationOptions | None = None,
    ) -> MutationResult: ...
    async def delete_docs(
        self,
        name: str,
        doc_ids: list[str],
    ) -> MutationResult: ...
    async def get_job_status(self, job_id: str) -> JobStatusResponse: ...
    async def get_index(self, name: str) -> IndexInfo: ...
    async def list_indexes(self) -> list[IndexInfo]: ...
    async def delete_index(self, name: str) -> bool: ...
    async def get_docs(
        self,
        name: str,
        options: GetDocumentsOptions | None = None,
    ) -> list[DocumentInfo]: ...
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
        options: QueryOptions | None = None,
    ) -> SearchResult: ...

class MutationResult:
    """Return value from create_index/add_docs/delete_docs."""

    job_id: str
    index_name: str
    doc_count: int

class MutationOptions:
    """Options for add_docs (e.g. upsert behavior)."""

    upsert: bool | None

    def __init__(self, upsert: bool | None = None) -> None: ...

class GetDocumentsOptions:
    """Options for get_docs (e.g. filter by document IDs)."""

    doc_ids: list[str] | None

    def __init__(self, doc_ids: list[str] | None = None) -> None: ...

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
    current_phase: JobPhase | None

class JobStatusResponse:
    """Full status response from get_job_status."""

    job_id: str
    status: JobStatus
    progress: float
    current_phase: JobPhase | None
    error: str | None
    created_at: str
    updated_at: str
    completed_at: str | None

class ModelRef:
    id: str
    version: str
    def __init__(self, id: str, version: str) -> None: ...

class QueryResultDocumentInfo:
    id: str
    text: str
    metadata: dict[str, str] | None
    score: float
    def __init__(
        self,
        id: str,
        text: str,
        metadata: dict[str, str] | None = ...,
        score: float = ...,
    ) -> None: ...

class DocumentInfo:
    id: str
    text: str
    metadata: dict[str, str] | None
    embedding: Sequence[float] | None
    def __init__(
        self,
        id: str,
        text: str,
        metadata: dict[str, str] | None = ...,
        embedding: Sequence[float] | None = ...,
    ) -> None: ...

class QueryOptions:
    embedding: Sequence[float] | None
    top_k: int | None
    alpha: float | None
    filter: dict | None
    rerank: bool
    rerank_top_k: int | None
    rerank_model: str | None
    def __init__(
        self,
        embedding: Sequence[float] | None = ...,
        top_k: int | None = ...,
        alpha: float | None = ...,
        filter: dict | None = ...,
        rerank: bool = ...,
        rerank_top_k: int | None = ...,
        rerank_model: str | None = ...,
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
    docs: list[QueryResultDocumentInfo]
    query: str
    index_name: str | None
    time_taken_ms: int | None
    def __init__(
        self,
        docs: list[QueryResultDocumentInfo],
        query: str,
        index_name: str | None = None,
        time_taken_ms: int | None = None,
    ) -> None: ...

class IndexStatus:
    NotStarted: ClassVar[str]
    Building: ClassVar[str]
    Ready: ClassVar[str]
    Failed: ClassVar[str]
    def __init__(self, value: str) -> None: ...

IndexStatusValues: dict[str, str]

__version__: str

__all__ = [
    "DocumentInfo",
    "GetDocumentsOptions",
    "IndexInfo",
    "IndexStatus",
    "IndexStatusValues",
    "JobPhase",
    "JobProgress",
    "JobStatus",
    "JobStatusResponse",
    "ModelRef",
    "MossClient",
    "MutationOptions",
    "MutationResult",
    "QueryOptions",
    "QueryResultDocumentInfo",
    "SearchResult",
]
