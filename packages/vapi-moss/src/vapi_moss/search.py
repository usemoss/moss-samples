#
# Copyright (c) 2025-2026, InferEdge Inc.
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Moss semantic search adapter for VAPI Custom Knowledge Base webhooks."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from moss import MossClient, QueryOptions

__all__ = ["MossVapiSearch", "VapiSearchResult"]

logger = logging.getLogger("vapi_moss")


@dataclass
class VapiSearchResult:
    """Result from a VAPI-formatted Moss search.

    Attributes:
        documents: List of documents in VAPI's expected shape.
        time_taken_ms: Moss query latency in milliseconds, if available.
    """

    documents: list[dict[str, Any]] = field(default_factory=list)
    time_taken_ms: int | None = None


class MossVapiSearch:
    """Moss semantic search formatted for VAPI Custom Knowledge Base responses.

    Usage::

        from vapi_moss import MossVapiSearch

        search = MossVapiSearch(
            project_id="...",
            project_key="...",
            index_name="my-faq-index",
        )
        await search.load_index()

        result = await search.search("return policy")
        # result.documents -> [{"content": "...", "similarity": 0.92}, ...]
        # result.time_taken_ms -> 3
    """

    def __init__(
        self,
        *,
        project_id: str | None = None,
        project_key: str | None = None,
        index_name: str,
        top_k: int = 5,
        alpha: float = 0.8,
    ):
        """Initialize with Moss credentials and retrieval settings.

        Args:
            project_id: Moss project ID. Falls back to ``MOSS_PROJECT_ID`` env var.
            project_key: Moss project key. Falls back to ``MOSS_PROJECT_KEY`` env var.
            index_name: Name of the Moss index to query.
            top_k: Number of results to retrieve per query.
            alpha: Blend between semantic (1.0) and keyword (0.0) scoring.
        """
        self._client = MossClient(project_id=project_id, project_key=project_key)
        self._index_name = index_name
        self._top_k = top_k
        self._alpha = alpha
        self._index_loaded = False

    async def load_index(self) -> None:
        """Pre-load the Moss index for fast queries.

        Raises on failure so the caller can fail closed at startup.
        """
        logger.info("Loading Moss index '%s'", self._index_name)
        await self._client.load_index(self._index_name)
        self._index_loaded = True
        logger.info("Moss index '%s' ready", self._index_name)

    async def search(self, query: str) -> VapiSearchResult:
        """Query the Moss index and return VAPI-formatted documents.

        Args:
            query: The search query text.

        Returns:
            VapiSearchResult with documents and timing data.
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

        return VapiSearchResult(
            documents=self._format_results(result.docs),
            time_taken_ms=result.time_taken_ms,
        )

    @staticmethod
    def _format_results(documents: Sequence[Any]) -> list[dict[str, Any]]:
        """Format Moss search results into VAPI's document shape."""
        results = []
        for doc in documents:
            entry: dict[str, Any] = {"content": getattr(doc, "text", "") or ""}
            score = getattr(doc, "score", None)
            if score is not None:
                entry["similarity"] = float(score)
            results.append(entry)
        return results
