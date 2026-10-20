#
# Copyright (c) 2024-2025, Daily
# Copyright (c) 2026, Moss Team
#
# SPDX-License-Identifier: BSD-2-Clause
#

"""Retrieval service manager for Moss vector indexes."""

from __future__ import annotations

from loguru import logger
from moss import MossClient

from .moss_index_processor import MossIndexProcessor

__all__ = ["MossRetrievalService"]


class MossRetrievalService:
    """Retrieval service manager for Moss vector indexes."""

    def __init__(
        self,
        *,
        project_id: str | None = None,
        project_key: str | None = None,
        system_prompt: str = "Here is additional context retrieved from database:\n\n",
    ):
        """Store shared client and default retrieval settings."""
        self._client = MossClient(project_id=project_id, project_key=project_key)
        self._system_prompt = system_prompt
        logger.debug("Initialized MossRetrievalService for project")

    async def load_index(self, index_name: str):
        """Explicitly load an index before using the pipeline."""
        try:
            logger.debug(f"Loading index: {index_name}")
            await self._client.load_index(index_name)
            logger.debug(f"Index loaded: {index_name}")
        except Exception as exc:  # pragma: no cover - pass-through
            logger.error(f"Failed to load index {index_name}: {exc}")
            raise exc

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
