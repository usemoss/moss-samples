#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Moss retrieval service implementation.

Provides functionality for retrieval and vector-store services that augment
LLM context with relevant documents retrieved from memory or vector databases.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from loguru import logger

from pipecat.frames.frames import ErrorFrame, Frame, LLMContextFrame, LLMMessagesFrame, MetricsFrame
from pipecat.metrics.metrics import ProcessingMetricsData
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from client import MossClient, SearchResult

from pipecat.processors.aggregators.openai_llm_context import (
    OpenAILLMContextFrame,
)

__all__ = ["MossRetrievalService"]


class MossRetrievalService(FrameProcessor):
    """Retrieval service backed by InferEdge Moss vector indexes.

    Intercepts LLM context frames to augment them with relevant documents
    retrieved from a Moss vector index based on the user's latest query.
    """

    def __init__(
        self,
        *,
        index_name: str,
        client: Optional[MossClient] = None,
        project_id: Optional[str] = None,
        project_key: Optional[str] = None,
        top_k: int = 5,
        system_prompt: str = "Here is additional context retrieved from database:\n\n",
        **kwargs,
    ):
        """Initialize the Moss retrieval service.
        
        Args:
            index_name: Name of the Moss index.
            client: Existing MossClient (optional).
            project_id: Moss project ID (optional).
            project_key: Moss project key (optional).
            top_k: Max results (default: 5).
            system_prompt: Context prefix.
            **kwargs: Additional options (deduplicate_queries, max_documents, etc).
        """
        super().__init__(name=kwargs.get("name"))
        if not index_name:
            raise ValueError("index_name must be provided")

        self._index_name = index_name
        self._top_k = max(1, top_k)
        self._system_prompt = system_prompt
        
        # Configurable options with defaults
        self._auto_load_index = kwargs.get("auto_load_index", True)
        self._add_as_system_message = kwargs.get("add_as_system_message", True)
        self._deduplicate_queries = kwargs.get("deduplicate_queries", True)
        self._max_documents = max(1, kwargs.get("max_documents", 5))
        self._max_document_chars = kwargs.get("max_document_chars", 2000)

        self._client = client or MossClient(project_id=project_id, project_key=project_key)
        self._last_query: Optional[str] = None

    def can_generate_metrics(self) -> bool:
        """Check if the processor can generate metrics.

        Returns:
            True, as this processor generates retrieval latency metrics.
        """
        return True

    async def retrieve_documents(
        self, query: str, *, limit: int
    ) -> SearchResult:
        """Retrieve documents for a given query.

        Args:
            query: The search query string.
            limit: Maximum number of documents to return.

        Returns:
            A SearchResult object containing the matching documents and metadata.
        """
        top_k = min(self._top_k, limit)
        result = await self._client.query(
            self._index_name,
            query,
            top_k=top_k,
            auto_load=self._auto_load_index,
        )

        if self.metrics_enabled:
            time_taken = getattr(result, "time_taken_ms", None)
            if time_taken is None and isinstance(result, dict):
                time_taken = result.get("time_taken_ms")

            if time_taken is not None:
                logger.info(f"{self}: Retrieval latency: {time_taken}ms")
                await self.push_frame(
                    MetricsFrame(
                        data=[
                            ProcessingMetricsData(
                                processor=self.name,
                                value=time_taken / 1000.0,
                            )
                        ]
                    )
                )

        return result

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames to extract queries and augment LLM context with retrieved documents.

        Args:
            frame: The frame to process.
            direction: The direction of the frame flow.
        """
        await super().process_frame(frame, direction)

        context = None
        messages = None

        if isinstance(frame, (LLMContextFrame, OpenAILLMContextFrame)):
            context = frame.context
        elif isinstance(frame, LLMMessagesFrame):
            messages = frame.messages
            context = LLMContext(messages)

        if not context:
            await self.push_frame(frame, direction)
            return

        try:
            context_messages = context.get_messages()
            latest_user_message = self._get_latest_user_text(context_messages)

            if (
                latest_user_message
                and not (self._deduplicate_queries and self._last_query == latest_user_message)
            ):
                search_result = await self.retrieve_documents(
                    latest_user_message, limit=self._max_documents
                )

                if self._deduplicate_queries:
                    self._last_query = latest_user_message

                documents = getattr(search_result, "docs", []) or []
                if documents:
                    content = self._format_documents(documents)
                    role = "system" if self._add_as_system_message else "user"
                    context.add_message({"role": role, "content": content})

            if messages is not None:
                await self.push_frame(LLMMessagesFrame(context.get_messages()))
            elif isinstance(frame, (LLMContextFrame, OpenAILLMContextFrame)):
                await self.push_frame(type(frame)(context=context))  # type: ignore[arg-type]
            else:
                await self.push_frame(frame)

        except Exception as exc:
            logger.exception(f"{self}: error while running retrieval: {exc}")
            await self.push_error(ErrorFrame(error=f"{self} retrieval error: {exc}"))

    @staticmethod
    def _get_latest_user_text(messages: Sequence[Dict[str, Any]]) -> Optional[str]:
        """Extract the text content from the latest user message.

        Args:
            messages: A sequence of message dictionaries.

        Returns:
            The text content of the last user message, or None if not found.
        """
        for m in reversed(messages):
            if m.get("role") == "user":
                content = m.get("content")
                if isinstance(content, str):
                    return content.strip()
                # Simplified list handling (assumes standard structure)
                if isinstance(content, list):
                    return "\n".join(
                        c["text"] for c in content if c.get("type") == "text"
                    ).strip()
        return None

    def _format_documents(self, documents: Sequence[Any]) -> str:
        """Format retrieved documents into a single context string.

        Args:
            documents: Sequence of retrieved documents.

        Returns:
            A formatted string containing the system prompt and document contents.
        """
        lines = [self._system_prompt.rstrip(), ""]
        for idx, doc in enumerate(documents, start=1):
            # Trust the object structure from our own library
            meta = doc.metadata or {}
            extras = []
            
            if source := meta.get("source"):
                extras.append(f"source={source}")
            
            if (score := getattr(doc, "score", None)) is not None:
                extras.append(f"score={score}")

            suffix = f" ({', '.join(extras)})" if extras else ""
            
            text = doc.text
            if self._max_document_chars and len(text) > self._max_document_chars:
                text = f"{text[:self._max_document_chars].rstrip()}…"

            lines.append(f"{idx}. {text}{suffix}")
        return "\n".join(lines).strip()