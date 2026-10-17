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
"""

from moss_core import (
    DocumentInfo,
    GetDocumentsOptions,
    IndexInfo,
    IndexStatus,
    IndexStatusValues,
    JobPhase,
    JobProgress,
    JobStatus,
    JobStatusResponse,
    ModelRef,
    MutationOptions,
    MutationResult,
    QueryResultDocumentInfo,
    SearchResult,
)

from .client.moss_client import MossClient, QueryOptions

__version__ = "1.0.0b19"

__all__ = [
    "MossClient",
    # Core data types
    "DocumentInfo",
    "GetDocumentsOptions",
    "IndexInfo",
    "SearchResult",
    "QueryResultDocumentInfo",
    "ModelRef",
    "IndexStatus",
    "IndexStatusValues",
    "QueryOptions",
    # Mutation types
    "MutationResult",
    "MutationOptions",
    "JobStatus",
    "JobPhase",
    "JobProgress",
    "JobStatusResponse",
]
