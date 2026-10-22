"""
Moss Semantic Search SDK

Powerful Python SDK for semantic search using state-of-the-art embedding models.

Example:
    ```python
    from moss import MossClient, DocumentInfo

    client = MossClient('your-project-id', 'your-project-key')

    docs = [DocumentInfo(id="1", text="Example document")]

    result = await client.create_index('my-index', docs, 'moss-minilm')

    await client.load_index('my-index')
    results = await client.query('my-index', 'search query')
    ```

Local-first session indexing:
    ```python
    session = await client.session("call-abc123")

    await session.add_docs([DocumentInfo(id="1", text="Customer asked about billing")])
    results = await session.query("billing issue")

    result = await session.push_index()
    ```
"""

from moss_core import (
    Chunking,
    DocumentInfo,
    GetDocumentsOptions,
    IndexInfo,
    IndexStatus,
    IndexStatusValues,
    InvalidArgumentError,
    JobPhase,
    JobProgress,
    JobStatus,
    JobStatusResponse,
    LoadIndexesResult,
    ModelRef,
    MossError,
    MutationOptions,
    MutationResult,
    ParentGrouping,
    PushIndexResult,
    QueryOptions,
    QueryResultDocumentInfo,
    SearchResult,
)

from .client.docs_input import Chunker, DocsInput
from .client.job_handle import JobHandle
from .client.manage_http import ManageApiError
from .client.moss_client import MossClient, ParseFileInput, ParseOptions
from .client.session_index import SessionIndex
from .client.web_source import (
    CreateWebSourceResult,
    DeleteWebSourceResult,
    ResyncWebSourceResult,
    UpdateWebSourceResult,
    WebSource,
)

from importlib import import_module as _import_module
from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("moss")
except PackageNotFoundError:  # source tree not installed as a distribution
    __version__ = "0.0.0+unknown"

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
    # Inference
    "MossInference",
]


def __getattr__(name: str) -> object:
    """Load `moss.inference` on first use, so `import moss` leaves httpx unloaded."""
    if name == "inference":
        return _import_module(".inference", __name__)
    if name == "MossInference":
        return _import_module(".inference", __name__).MossInference
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
