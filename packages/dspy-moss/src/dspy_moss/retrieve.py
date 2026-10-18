#
# Copyright (c) 2025-2026, InferEdge Inc.
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""DSPy retrieval module backed by Moss semantic search."""

from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import dspy
from moss import DocumentInfo, MossClient, MutationOptions, QueryOptions


class _DotDict(dict):
    """Dict with attribute-style read access, compatible with DSPy passage objects."""

    __getattr__ = dict.get  # type: ignore[assignment]


__all__ = ["MossRM"]

logger = logging.getLogger("dspy_moss")


class MossRM(dspy.Retrieve):
    """DSPy retrieval module that uses Moss for sub-10ms semantic search.

    Integrates with DSPy's RM interface so it can be set as the default
    retriever via ``dspy.configure(rm=MossRM(...))``, or used directly as
    a tool in ``dspy.ReAct``.

    Args:
        index_name: Name of the Moss index to query.
        moss_client: An existing ``MossClient`` instance. When omitted, one
            is created from ``project_id`` / ``project_key`` (or their env-var
            equivalents ``MOSS_PROJECT_ID`` / ``MOSS_PROJECT_KEY``).
        project_id: Moss project ID. Falls back to ``MOSS_PROJECT_ID`` env var.
        project_key: Moss project key. Falls back to ``MOSS_PROJECT_KEY`` env var.
        k: Default number of passages to retrieve per query (default: 3).
        alpha: Hybrid search blend — 1.0 = pure semantic, 0.0 = pure keyword
            (default: 0.8).

    Examples::

        import dspy
        from dspy_moss import MossRM

        rm = MossRM("my-index")          # reads MOSS_PROJECT_ID / KEY from env
        dspy.configure(lm=dspy.LM("openai/gpt-4o"), rm=rm)

        retrieve = dspy.Retrieve(k=3)
        result = retrieve("What is the refund policy?")
        print(result.passages)
    """

    def __init__(
        self,
        index_name: str,
        moss_client: MossClient | None = None,
        project_id: str | None = None,
        project_key: str | None = None,
        k: int = 3,
        alpha: float = 0.8,
    ):
        """Initialize the MossRM retrieval module."""
        if moss_client is None:
            resolved_id = project_id or os.getenv("MOSS_PROJECT_ID") or ""
            resolved_key = project_key or os.getenv("MOSS_PROJECT_KEY") or ""
            if not resolved_id or not resolved_key:
                raise ValueError(
                    "Moss credentials required. Provide moss_client or project_id/project_key, "
                    "or set MOSS_PROJECT_ID and MOSS_PROJECT_KEY environment variables."
                )
            moss_client = MossClient(resolved_id, resolved_key)

        self._index_name = index_name
        self._client = moss_client
        self._alpha = alpha
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dspy-moss")
        super().__init__(k=k)

    # ------------------------------------------------------------------
    # Async helper
    # ------------------------------------------------------------------

    def _run(self, coro: Any) -> Any:
        """Run a coroutine from sync context, safe inside a running event loop."""
        try:
            asyncio.get_running_loop()
            in_running_loop = True
        except RuntimeError:
            in_running_loop = False

        if in_running_loop:
            return self._executor.submit(asyncio.run, coro).result()
        return asyncio.run(coro)

    def close(self) -> None:
        """Release the background executor used when called inside an event loop."""
        self._executor.shutdown(wait=True)

    def __enter__(self) -> MossRM:
        """Return this retriever for use as a context manager."""
        return self

    def __exit__(self, *_exc_info: object) -> None:
        """Release executor resources when leaving a context manager."""
        self.close()

    # ------------------------------------------------------------------
    # Index loading
    # ------------------------------------------------------------------

    def load_index(
        self,
        auto_refresh: bool = False,
        polling_interval_in_seconds: int = 600,
    ) -> None:
        """Load the index into memory for fast local queries.

        Without this, every query falls back to the cloud API. Call once at
        startup before any ``forward()`` or ``dspy.Retrieve`` calls.

        Args:
            auto_refresh: Reload automatically when the cloud index is updated.
            polling_interval_in_seconds: Refresh interval when ``auto_refresh=True``.
        """
        logger.info("Loading Moss index '%s' into memory", self._index_name)
        self._run(
            self._client.load_index(
                self._index_name,
                auto_refresh=auto_refresh,
                polling_interval_in_seconds=polling_interval_in_seconds,
            )
        )
        logger.info("Moss index '%s' ready", self._index_name)

    def forward(
        self,
        query_or_queries: str | list[str],
        k: int | None = None,
        **kwargs: Any,
    ) -> list[_DotDict]:
        """Retrieve the top-k passages for one or more queries.

        Returns a list of dot-accessible dicts (``long_text``, ``id``,
        ``score``, ``metadata``). DSPy's ``Retrieve`` base class wraps this
        list in a ``Prediction`` and extracts ``long_text`` from each item.

        Args:
            query_or_queries: A single query string or a list of query strings.
            k: Number of passages to retrieve. Defaults to ``self.k``.
            **kwargs: Additional keyword arguments.
        """
        k = k if k is not None else self.k
        queries = (
            [query_or_queries]
            if isinstance(query_or_queries, str)
            else query_or_queries
        )
        queries = [q for q in queries if q]

        option_kwargs = dict(kwargs)
        top_k = option_kwargs.pop("top_k", k)
        alpha = option_kwargs.pop("alpha", self._alpha)

        passages = []
        for query in queries:
            result = self._run(
                self._client.query(
                    self._index_name,
                    query,
                    options=QueryOptions(top_k=top_k, alpha=alpha, **option_kwargs),
                )
            )
            for doc in result.docs:
                passages.append(
                    _DotDict(
                        long_text=doc.text,
                        id=doc.id,
                        score=doc.score,
                        metadata=doc.metadata or {},
                    )
                )
            logger.debug("Moss query '%s' returned %d docs", query, len(result.docs))

        return passages

    # ------------------------------------------------------------------
    # Mutable RM helpers (optional — for agents that write to the index)
    # ------------------------------------------------------------------

    def get_objects(self, num_samples: int = 5) -> list[dict[str, Any]]:
        """Fetch up to ``num_samples`` documents from the index.

        Args:
            num_samples: Maximum number of documents to return.

        Returns:
            List of dicts with ``id``, ``text``, and ``metadata`` keys.
        """
        docs = self._run(self._client.get_docs(self._index_name))
        return [
            {"id": d.id, "text": d.text, "metadata": d.metadata or {}}
            for d in docs[:num_samples]
        ]

    def insert(self, new_objects: dict[str, Any] | list[dict[str, Any]]) -> None:
        """Add or upsert documents into the index.

        Args:
            new_objects: A single document dict or a list of dicts.
                Each dict must have an ``id`` and ``text`` key; ``metadata``
                is optional.
        """
        if isinstance(new_objects, dict):
            new_objects = [new_objects]

        moss_docs = [
            DocumentInfo(
                id=obj["id"],
                text=obj["text"],
                metadata={str(k): str(v) for k, v in obj.get("metadata", {}).items()} or None,
            )
            for obj in new_objects
        ]
        self._run(
            self._client.add_docs(
                self._index_name, moss_docs, options=MutationOptions(upsert=True)
            )
        )
        logger.info("Inserted %d documents into Moss index '%s'", len(moss_docs), self._index_name)
