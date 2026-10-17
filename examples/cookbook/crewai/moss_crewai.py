import asyncio
import uuid
from typing import Any

from crewai.tools import BaseTool
from moss import (
    DocumentInfo,
    GetDocumentsOptions,
    MossClient,
    MutationOptions,
    QueryOptions,
)
from pydantic import BaseModel, Field, PrivateAttr


class MossBaseTool(BaseTool):
    """Base class for all Moss tools. Handles shared client and sync wrapper."""

    _client: Any = PrivateAttr()

    def __init__(self, client: MossClient, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client = client

    def _run(self, *args: Any, **kwargs: Any) -> str:
        """Synchronous execution — wraps _arun() for CrewAI's @abstractmethod requirement."""
        try:
            return asyncio.run(self._arun(*args, **kwargs))
        except RuntimeError as e:
            if "cannot be called from a running event loop" in str(e):
                raise RuntimeError(
                    f"{self.__class__.__name__}._run() cannot be called from a "
                    "running event loop. Use async mode or call from a standard script."
                ) from e
            raise


class MossSearchInput(BaseModel):
    """Input schema for MossSearchTool."""

    query: str = Field(description="The search query text")


class MossSearchTool(MossBaseTool):
    """Semantic search tool powered by Moss."""

    name: str = "moss_search"
    description: str = (
        "Search a knowledge base using Moss semantic search. "
        "Returns the most relevant documents for a given query."
    )
    args_schema: type[BaseModel] = MossSearchInput

    index_name: str = Field(description="Name of the Moss index to search")
    top_k: int = Field(default=5, description="Number of results to return")
    alpha: float = Field(
        default=0.8,
        description="Hybrid search balance (0=keyword, 1=semantic)",
    )

    _index_loaded: bool = PrivateAttr(default=False)

    async def _ensure_loaded(self) -> None:
        if not self._index_loaded:
            await self._client.load_index(self.index_name)
            self._index_loaded = True

    async def _arun(self, query: str) -> str:
        """Async search against Moss index."""
        await self._ensure_loaded()
        results = await self._client.query(
            self.index_name,
            query,
            QueryOptions(top_k=self.top_k, alpha=self.alpha),
        )
        if not results.docs:
            return "No relevant information found."
        return "\n\n".join(
            f"Result {i + 1} (score: {doc.score:.2f}):\n{doc.text}"
            for i, doc in enumerate(results.docs)
        )


# --- Document Management ---


class MossAddDocsInput(BaseModel):
    """Input schema for MossAddDocsTool."""

    texts: list[str] = Field(description="List of text documents to add")
    ids: list[str] | None = Field(
        default=None,
        description="Optional document IDs (auto-generated if omitted)",
    )
    upsert: bool = Field(
        default=False,
        description="If True, update existing documents with the same ID instead of failing",
    )


class MossAddDocsTool(MossBaseTool):
    """Add documents to a Moss index."""

    name: str = "moss_add_docs"
    description: str = "Add text documents to a Moss semantic search index."
    args_schema: type[BaseModel] = MossAddDocsInput

    index_name: str = Field(description="Name of the Moss index")

    async def _arun(
        self, texts: list[str], ids: list[str] | None = None, upsert: bool = False
    ) -> str:
        """Async add documents to Moss index."""
        docs = [
            DocumentInfo(
                id=ids[i] if ids and i < len(ids) else str(uuid.uuid4()),
                text=text,
            )
            for i, text in enumerate(texts)
        ]
        options = MutationOptions(upsert=True) if upsert else None
        await self._client.add_docs(self.index_name, docs, options)
        action = "upserted" if upsert else "added"
        return f"Successfully {action} {len(docs)} documents."


class MossDeleteDocsInput(BaseModel):
    """Input schema for MossDeleteDocsTool."""

    doc_ids: list[str] = Field(description="List of document IDs to delete")


class MossDeleteDocsTool(MossBaseTool):
    """Delete documents from a Moss index by their IDs."""

    name: str = "moss_delete_docs"
    description: str = "Delete specific documents from a Moss index by their IDs."
    args_schema: type[BaseModel] = MossDeleteDocsInput

    index_name: str = Field(description="Name of the Moss index")

    async def _arun(self, doc_ids: list[str]) -> str:
        """Async delete documents from Moss index."""
        await self._client.delete_docs(self.index_name, doc_ids)
        return f"Successfully deleted {len(doc_ids)} documents."


class MossGetDocsInput(BaseModel):
    """Input schema for MossGetDocsTool."""

    doc_ids: list[str] | None = Field(
        default=None,
        description="Optional list of document IDs to retrieve. If omitted, returns all documents.",
    )


class MossGetDocsTool(MossBaseTool):
    """Retrieve documents from a Moss index."""

    name: str = "moss_get_docs"
    description: str = (
        "Retrieve documents from a Moss index. "
        "Can fetch specific documents by ID or all documents."
    )
    args_schema: type[BaseModel] = MossGetDocsInput

    index_name: str = Field(description="Name of the Moss index")

    async def _arun(self, doc_ids: list[str] | None = None) -> str:
        """Async retrieve documents from Moss index."""
        options = None
        if doc_ids:
            options = GetDocumentsOptions(doc_ids=doc_ids)
        docs = await self._client.get_docs(self.index_name, options)
        if not docs:
            return "No documents found."
        lines = []
        for doc in docs:
            text_preview = doc.text[:150] + "..." if len(doc.text) > 150 else doc.text
            lines.append(f"[{doc.id}] {text_preview}")
        return f"Retrieved {len(docs)} documents:\n" + "\n".join(lines)


# --- Index Management ---


class MossGetIndexInput(BaseModel):
    """Input schema for MossGetIndexTool."""

    index_name: str = Field(description="Name of the index to get info for")


class MossGetIndexTool(MossBaseTool):
    """Get detailed information about a specific Moss index."""

    name: str = "moss_get_index"
    description: str = "Get information about a specific Moss index, including document count and status."
    args_schema: type[BaseModel] = MossGetIndexInput

    async def _arun(self, index_name: str) -> str:
        """Async get info about a specific Moss index."""
        info = await self._client.get_index(index_name)
        name = getattr(info, "name", index_name)
        doc_count = getattr(info, "doc_count", "?")
        status = getattr(info, "status", "?")
        return f"Index '{name}': {doc_count} docs, status: {status}"


class MossListIndexesInput(BaseModel):
    """Input schema for MossListIndexesTool."""

    # No input needed


class MossListIndexesTool(MossBaseTool):
    """List all available Moss indexes."""

    name: str = "moss_list_indexes"
    description: str = (
        "List all available indexes in the Moss project with their details."
    )
    args_schema: type[BaseModel] = MossListIndexesInput

    async def _arun(self) -> str:
        """Async list all Moss indexes."""
        indexes = await self._client.list_indexes()
        if not indexes:
            return "No indexes found."
        lines = []
        for idx in indexes:
            name = getattr(idx, "name", "unknown")
            doc_count = getattr(idx, "doc_count", "?")
            status = getattr(idx, "status", "?")
            lines.append(f"- {name} ({doc_count} docs, status: {status})")
        return "Indexes:\n" + "\n".join(lines)


class MossCreateIndexInput(BaseModel):
    """Input schema for MossCreateIndexTool."""

    index_name: str = Field(description="Name for the new index")
    texts: list[str] = Field(description="List of text documents to index")
    ids: list[str] | None = Field(
        default=None,
        description="Optional document IDs (auto-generated if omitted)",
    )


class MossCreateIndexTool(MossBaseTool):
    """Create a new Moss index with documents."""

    name: str = "moss_create_index"
    description: str = (
        "Create a new Moss semantic search index and populate it with documents."
    )
    args_schema: type[BaseModel] = MossCreateIndexInput

    async def _arun(
        self, index_name: str, texts: list[str], ids: list[str] | None = None
    ) -> str:
        """Async create a new Moss index."""
        docs = [
            DocumentInfo(
                id=ids[i] if ids and i < len(ids) else str(uuid.uuid4()),
                text=text,
            )
            for i, text in enumerate(texts)
        ]
        await self._client.create_index(index_name, docs)
        return f"Successfully created index '{index_name}' with {len(docs)} documents."


class MossDeleteIndexInput(BaseModel):
    """Input schema for MossDeleteIndexTool."""

    index_name: str = Field(description="Name of the index to delete")


class MossDeleteIndexTool(MossBaseTool):
    """Delete a Moss index and all its data."""

    name: str = "moss_delete_index"
    description: str = (
        "Delete a Moss index and all its documents. This action is irreversible."
    )
    args_schema: type[BaseModel] = MossDeleteIndexInput

    async def _arun(self, index_name: str) -> str:
        """Async delete a Moss index."""
        await self._client.delete_index(index_name)
        return f"Successfully deleted index '{index_name}'."


# --- Factory ---


def moss_tools(
    client: MossClient,
    index_name: str,
    top_k: int = 5,
    alpha: float = 0.8,
) -> list[BaseTool]:
    """Create all Moss tools with a shared MossClient.

    Args:
        client: A shared MossClient instance.
        index_name: Default index name for document/search tools.
        top_k: Default number of search results.
        alpha: Hybrid search balance.

    Returns: [search, add_docs, delete_docs, get_docs, get_index,
              list_indexes, create_index, delete_index]
    """
    return [
        MossSearchTool(client=client, index_name=index_name, top_k=top_k, alpha=alpha),
        MossAddDocsTool(client=client, index_name=index_name),
        MossDeleteDocsTool(client=client, index_name=index_name),
        MossGetDocsTool(client=client, index_name=index_name),
        MossGetIndexTool(client=client),
        MossListIndexesTool(client=client),
        MossCreateIndexTool(client=client),
        MossDeleteIndexTool(client=client),
    ]
