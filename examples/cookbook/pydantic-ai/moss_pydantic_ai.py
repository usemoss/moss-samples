from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from moss import MossClient, QueryOptions
from pydantic_ai import Tool

__all__ = ["MossSearchTool"]


class MossSearchTool:
    """Moss semantic search exposed as a Pydantic AI tool."""

    _TOOL_DESCRIPTION = (
        "Use this tool whenever the user asks for information that should come from the Moss "
        "knowledge base, such as refunds, account help, support policies, or product facts. "
        "Pass the user's question as the query and use the returned results to answer."
    )

    def __init__(
        self,
        *,
        client: MossClient,
        index_name: str,
        tool_name: str = "moss_search",
        top_k: int = 5,
        alpha: float = 0.8,
    ) -> None:
        """Initialize with a shared MossClient and retrieval settings."""
        self._client = client
        self._index_name = index_name
        self._tool_name = tool_name
        self._top_k = top_k
        self._alpha = alpha
        self._tool_obj = self._build_tool()

    async def load_index(self) -> None:
        """Pre-load the Moss index into memory for fast queries."""
        await self._client.load_index(self._index_name)

    async def search(self, query: str) -> str:
        """Query the Moss index and return formatted results."""
        result = await self._client.query(
            self._index_name,
            query,
            QueryOptions(top_k=self._top_k, alpha=self._alpha),
        )
        return self._format_results(result.docs)

    @property
    def tool(self) -> Tool:
        """Return the ``pydantic_ai.Tool`` to pass to an Agent."""
        return self._tool_obj

    def _build_tool(self) -> Tool:
        """Build a Pydantic AI Tool wrapping :meth:`search`."""
        instance = self

        async def moss_search(query: str) -> str:
            """Search the knowledge base for relevant documents.

            Args:
                query: Natural-language question or lookup text.
            """
            return await instance.search(query)

        return Tool(
            moss_search,
            takes_ctx=False,
            name=self._tool_name,
            description=self._TOOL_DESCRIPTION,
        )

    @staticmethod
    def _format_results(documents: Sequence[Any]) -> str:
        """Format Moss search results into a numbered string."""
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
