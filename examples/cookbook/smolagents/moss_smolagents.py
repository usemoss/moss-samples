from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from moss import MossClient, QueryOptions
from smolagents import Tool

__all__ = ["MossSearchTool"]


class MossSearchTool(Tool):
    """Moss semantic search tool for smolagents."""

    name = "moss_search"
    description = (
        "Use this tool to search the local knowledge base for relevant documents. "
        "Useful when you need factual answers about account settings, support policies, "
        "refunds, support hours, or product features."
    )
    inputs = {
        "query": {
            "type": "string",
            "description": "The search query to look up in the knowledge base.",
        }
    }
    output_type = "string"

    def __init__(
        self,
        *,
        client: MossClient | None = None,
        project_id: str | None = None,
        project_key: str | None = None,
        index_name: str,
        tool_name: str = "moss_search",
        top_k: int = 5,
        alpha: float = 0.8,
        **kwargs: Any,
    ) -> None:
        """Initialize the Moss search tool.

        Args:
            client: An existing MossClient instance.
            project_id: Moss project ID (required if client is not provided).
            project_key: Moss project key (required if client is not provided).
            index_name: Name of the Moss index to query.
            tool_name: Custom name for the tool exposed to the agent.
            top_k: Number of search results to retrieve.
            alpha: Hybrid search balance (0.0 = keyword only, 1.0 = semantic only).
            **kwargs: Additional keyword arguments passed to the parent Tool class.
        """
        super().__init__(**kwargs)

        if client is not None:
            self._client = client
        elif project_id is not None and project_key is not None:
            self._client = MossClient(project_id, project_key)
        else:
            raise ValueError(
                "Either a 'client' instance or both 'project_id' and 'project_key' must be provided."
            )

        self._index_name = index_name
        self.name = tool_name
        self._top_k = top_k
        self._alpha = alpha

    async def load_index(self) -> None:
        """Pre-load the Moss index into local memory for fast querying."""
        await self._client.load_index(self._index_name)

    def forward(self, query: str) -> str:
        """Query the Moss index and return formatted results."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            try:
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(self._search(query))
            except ImportError:
                raise RuntimeError(
                    "MossSearchTool.forward() cannot be called from a running event loop. "
                    "Please run this tool in a standard script or install 'nest-asyncio' for notebook/active-loop support."
                )
        else:
            return asyncio.run(self._search(query))

    async def _search(self, query: str) -> str:
        """Asynchronous execution of the search query against Moss."""
        result = await self._client.query(
            self._index_name,
            query,
            QueryOptions(top_k=self._top_k, alpha=self._alpha),
        )
        return self._format_results(result.docs)

    @staticmethod
    def _format_results(documents: Sequence[Any]) -> str:
        """Format Moss query results into a readable list of items."""
        if not documents:
            return "No relevant results found."

        lines = ["Relevant knowledge base results:", ""]
        for idx, doc in enumerate(documents, start=1):
            meta = doc.metadata or {}
            extras = []
            if source := meta.get("source"):
                extras.append(f"source={source}")
            if (score := getattr(doc, "score", None)) is not None:
                extras.append(f"score={score:.3f}")
            suffix = f" ({', '.join(extras)})" if extras else ""
            text = getattr(doc, "text", "") or ""
            lines.append(f"{idx}. {text}{suffix}")
        return "\n".join(lines)
