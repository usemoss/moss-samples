#
# Copyright (c) 2025-2026, InferEdge Inc.
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""ElevenLabs ClientTool adapter for Moss semantic search."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from moss import MossClient, QueryOptions

__all__ = ["MossClientTool"]

logger = logging.getLogger("elevenlabs_moss")


class MossClientTool:
    """Registers Moss semantic search as an ElevenLabs client tool.

    Usage::

        from elevenlabs.conversational_ai.conversation import ClientTools
        from elevenlabs_moss import MossClientTool

        moss_tool = MossClientTool(
            project_id="...",
            project_key="...",
            index_name="my-faq-index",
        )
        await moss_tool.load_index()

        client_tools = ClientTools()
        moss_tool.register(client_tools)

        # Pass client_tools to Conversation(...)
    """

    def __init__(
        self,
        *,
        project_id: str | None = None,
        project_key: str | None = None,
        index_name: str,
        tool_name: str = "search_knowledge_base",
        top_k: int = 5,
        alpha: float = 0.8,
        result_prefix: str = "Relevant knowledge base results:\n\n",
    ):
        """Initialize with Moss credentials and retrieval settings.

        Args:
            project_id: Moss project ID. Falls back to ``MOSS_PROJECT_ID`` env var.
            project_key: Moss project key. Falls back to ``MOSS_PROJECT_KEY`` env var.
            index_name: Name of the Moss index to query.
            tool_name: Tool name registered with ElevenLabs (must match dashboard config).
            top_k: Number of results to retrieve per query.
            alpha: Blend between semantic (1.0) and keyword (0.0) scoring.
            result_prefix: Prefix prepended to formatted search results.
        """
        self._client = MossClient(project_id=project_id, project_key=project_key)
        self._index_name = index_name
        self._tool_name = tool_name
        self._top_k = top_k
        self._alpha = alpha
        self._result_prefix = result_prefix
        self._index_loaded = False

    async def load_index(self) -> None:
        """Pre-load the Moss index for fast queries.

        Call this before starting the ElevenLabs conversation so that the
        first tool invocation does not incur index-loading latency.
        """
        logger.info("Loading Moss index '%s'", self._index_name)
        await self._client.load_index(self._index_name)
        self._index_loaded = True
        logger.info("Moss index '%s' ready", self._index_name)

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

    def register(self, client_tools: Any) -> None:
        """Register this tool with an ElevenLabs ClientTools instance.

        Args:
            client_tools: An ``elevenlabs.conversational_ai.conversation.ClientTools``
                instance. The tool is registered as async.
        """
        client_tools.register(self._tool_name, self._callback, is_async=True)
        logger.info("Registered Moss tool '%s' with ElevenLabs ClientTools", self._tool_name)

    async def _callback(self, params: dict) -> str:
        """Async callback invoked by ElevenLabs when the agent calls this tool.

        Expects ``params`` to contain a ``query`` key with the user's question.
        Returns a formatted string of search results.
        """
        query = (params.get("query") or "").strip()
        if not query:
            return "No query provided."

        try:
            return await self.search(query)
        except Exception:
            logger.exception("Moss search failed for query '%s'", query)
            return "Search unavailable. Please try again later."

    def _format_results(self, documents: Sequence[Any]) -> str:
        """Format Moss search results into a numbered string."""
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
