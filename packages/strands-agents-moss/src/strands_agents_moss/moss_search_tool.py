#
# Copyright (c) 2025-2026, InferEdge Inc.
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Strands Agents tool adapter for Moss semantic search."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from moss import MossClient, QueryOptions
from strands import tool

__all__ = ["MossSearchTool"]

logger = logging.getLogger("strands_agents_moss")


class MossSearchTool:
    """Provides Moss semantic search as a Strands Agents tool.

    This class manages the MossClient lifecycle and exposes a ``tool``
    property that returns a Strands-compatible tool function ready to
    be passed to an ``Agent``.

    Usage::

        from strands import Agent
        from strands_agents_moss import MossSearchTool

        moss = MossSearchTool(
            project_id="...",
            project_key="...",
            index_name="my-faq-index",
        )
        await moss.load_index()

        agent = Agent(tools=[moss.tool])
        agent("What is your refund policy?")
    """

    def __init__(
        self,
        *,
        project_id: str | None = None,
        project_key: str | None = None,
        index_name: str,
        tool_name: str = "moss_search",
        tool_description: str | None = None,
        top_k: int = 5,
        alpha: float = 0.8,
        result_prefix: str = "Relevant knowledge base results:\n\n",
    ):
        """Initialize with Moss credentials and retrieval settings.

        Args:
            project_id: Moss project ID. Falls back to ``MOSS_PROJECT_ID`` env var.
            project_key: Moss project key. Falls back to ``MOSS_PROJECT_KEY`` env var.
            index_name: Name of the Moss index to query.
            tool_name: Name exposed to the LLM for tool selection.
            tool_description: Description exposed to the LLM. If ``None`` a sensible
                default is used.
            top_k: Number of results to retrieve per query.
            alpha: Blend between semantic (1.0) and keyword (0.0) scoring.
            result_prefix: Prefix prepended to formatted search results.
        """
        self._client = MossClient(project_id=project_id, project_key=project_key)
        self._index_name = index_name
        self._tool_name = tool_name
        self._tool_description = tool_description or (
            "Search the knowledge base using Moss semantic search. "
            "Returns the most relevant documents for a given query."
        )
        self._top_k = top_k
        self._alpha = alpha
        self._result_prefix = result_prefix
        self._index_loaded = False
        self._load_lock = asyncio.Lock()
        self._tool_fn = self._build_tool()

    async def load_index(self) -> None:
        """Pre-load the Moss index for fast queries.

        Call this before creating the Strands Agent so that the first
        tool invocation does not incur index-loading latency.

        This method is safe to call concurrently; only the first call
        will actually load the index.
        """
        async with self._load_lock:
            if self._index_loaded:
                return
            logger.info("Loading Moss index '%s'", self._index_name)
            await self._client.load_index(self._index_name)
            self._index_loaded = True
            logger.info("Moss index '%s' ready", self._index_name)

    @property
    def tool(self) -> Any:
        """Return the Strands-compatible tool function.

        Pass this to ``Agent(tools=[...])`` alongside any other tools.
        """
        return self._tool_fn

    async def search(self, query: str) -> str:
        """Query the Moss index and return formatted results.

        Args:
            query: The search query text.

        Returns:
            Formatted string of search results suitable for LLM context,
            or a short message if no results are found.
        """
        if not self._index_loaded:
            raise RuntimeError(
                f"Index '{self._index_name}' not loaded. Call await load_index() first."
            )

        result = await self._client.query(
            self._index_name,
            query,
            options=QueryOptions(top_k=self._top_k, alpha=self._alpha),
        )
        logger.info(
            "Moss query returned %d docs in %sms",
            len(result.docs),
            result.time_taken_ms,
        )

        return self._format_results(result.docs)

    def _build_tool(self) -> Any:
        """Create the Strands @tool-decorated async function bound to this instance."""
        instance = self

        @tool(name=instance._tool_name, description=instance._tool_description)
        async def moss_search(query: str) -> str:
            """Search the knowledge base.

            Args:
                query: The search query to find relevant documents.
            """
            return await instance.search(query)

        return moss_search

    def _format_results(self, documents: Sequence[Any]) -> str:
        """Format Moss search results into a numbered string."""
        if not documents:
            return "No relevant results found."

        lines = [self._result_prefix.rstrip(), ""]
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
        return "\n".join(lines).strip()
