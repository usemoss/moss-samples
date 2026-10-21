#
# Copyright (c) 2024-2025, Daily
# Copyright (c) 2026, Moss Team
#
# SPDX-License-Identifier: BSD-2-Clause
#

"""Retrieval service manager for Moss vector indexes."""

from __future__ import annotations

import asyncio
import os

from loguru import logger
from moss import MossClient

from .moss_index_processor import MossIndexProcessor

__all__ = ["MossRetrievalService"]


class MossRetrievalService:
    """Retrieval service manager for Moss vector indexes.

    Create one service per process and share it across bots.
    Its client holds the embedding model and every loaded index,
    so every bot reuses them instead of loading its own copy again.
    """

    def __init__(
        self,
        *,
        project_id: str | None = None,
        project_key: str | None = None,
        system_prompt: str = "Here is additional context retrieved from database:\n\n",
        cache_path: str | None = None,
    ):
        """Create the client that every processor from this service shares.

        Credentials default to `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY`.
        With `cache_path`, a load in a new process reads an unchanged index
        from disk instead of downloading it, and auto-refresh writes through to it.
        """
        project_id = project_id or os.getenv("MOSS_PROJECT_ID")
        project_key = project_key or os.getenv("MOSS_PROJECT_KEY")
        if not project_id or not project_key:
            raise ValueError(
                "Pass project_id and project_key, or set MOSS_PROJECT_ID and MOSS_PROJECT_KEY"
            )
        self._client = MossClient(project_id, project_key, cache_path=cache_path)
        self._system_prompt = system_prompt
        self._loads: dict[str, asyncio.Task[None]] = {}
        logger.debug("Initialized MossRetrievalService for project")

    async def load_index(self, index_name: str, *, auto_refresh: bool = False) -> None:
        """Load an index into memory once for this service.

        Later and concurrent calls wait for that same load.
        A failed load is retried by the next call, and the first call's options apply.
        With `auto_refresh`, the index follows new cloud versions while the process runs.
        """
        task = self._loads.get(index_name)
        if task is None or (task.done() and (task.cancelled() or task.exception() is not None)):
            task = asyncio.ensure_future(self._load(index_name, auto_refresh))
            # `_load` logs a failure and the next call retries, so no caller has to retrieve it.
            task.add_done_callback(lambda done: done.cancelled() or done.exception())
            self._loads[index_name] = task
        # A bot that disconnects mid-load must not cancel the load other bots share.
        await asyncio.shield(task)

    async def _load(self, index_name: str, auto_refresh: bool) -> None:
        try:
            logger.debug(f"Loading index: {index_name}")
            await self._client.load_index(index_name, auto_refresh=auto_refresh)
            logger.debug(f"Index loaded: {index_name}")
        except Exception as exc:  # pragma: no cover - pass-through
            logger.error(f"Failed to load index {index_name}: {exc}")
            raise

    def query(
        self,
        index_name: str,
        *,
        top_k: int = 5,
        alpha: float = 0.8,
    ) -> MossIndexProcessor:
        """Create a pipeline processor for a specific Moss index."""
        logger.debug(f"Creating MossIndexProcessor for index: {index_name}")
        return MossIndexProcessor(
            client=self._client,
            index_name=index_name,
            top_k=top_k,
            alpha=alpha,
            system_prompt=self._system_prompt,
        )
