"""Moss custom components for Langflow.

Drop-in retriever and search tool components that connect Langflow's
visual builder to Moss semantic search.  Users can drag-and-drop these
components onto the canvas, configure credentials and index name, and
wire them into any Langflow flow — no code required.

Two components are provided:

* **MossRetrieverComponent** – returns ``list[Data]`` for downstream
  pipeline consumption (e.g. feeding a vector store or prompt builder).
* **MossSearchComponent** – returns a ``Message`` with formatted text,
  ideal for plugging directly into an LLM prompt.

Both components lazy-load the Moss index on first query and cache it
for subsequent calls within the same flow execution.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from langflow.custom import Component
from langflow.io import (
    FloatInput,
    IntInput,
    MessageTextInput,
    Output,
    SecretStrInput,
)
from langflow.schema import Data
from langflow.schema.message import Message
from moss import MossClient, QueryOptions

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_async(coro: Any) -> Any:
    """Run an async coroutine synchronously.

    Langflow component methods are synchronous, but the Moss SDK is
    async-only.  This helper bridges the gap, with a clear error message
    when called inside an already-running event loop (e.g. Jupyter).
    """
    try:
        return asyncio.run(coro)
    except RuntimeError as exc:
        if "cannot be called from a running event loop" in str(exc):
            raise RuntimeError(
                "MossClient requires an event loop.  If you are running "
                "inside Jupyter or another async context, use "
                "nest_asyncio.apply() before importing this module."
            ) from exc
        raise


def _parse_filter(raw: str) -> dict | None:
    """Parse an optional JSON filter string into a dict.

    Returns ``None`` when *raw* is empty or whitespace-only.

    Raises ``ValueError`` with a user-friendly message on invalid JSON.
    """
    if not raw or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid metadata filter JSON: {exc}.  "
            "Expected a Moss filter object, e.g. "
            '{\"$eq\": {\"category\": \"faq\"}}'
        ) from exc
    if not isinstance(parsed, dict):
        raise ValueError("Metadata filter must be a JSON object (dict).")
    return parsed


# ---------------------------------------------------------------------------
# MossRetrieverComponent
# ---------------------------------------------------------------------------

class MossRetrieverComponent(Component):
    """Retrieve documents from a Moss semantic search index.

    This component loads a Moss index and returns matching documents as
    Langflow ``Data`` objects.  Wire the *Retrieved Documents* output
    into any downstream component that accepts structured data.
    """

    display_name = "Moss Retriever"
    description = (
        "Retrieve documents from a Moss semantic search index.  "
        "Returns structured Data objects with text, score, and metadata."
    )
    icon = "search"
    name = "MossRetriever"

    inputs = [
        SecretStrInput(
            name="project_key",
            display_name="Moss Project Key",
            info=(
                "Your Moss project key.  "
                "Leave blank to read from the MOSS_PROJECT_KEY env var."
            ),
            required=False,
        ),
        MessageTextInput(
            name="project_id",
            display_name="Moss Project ID",
            info=(
                "Your Moss project ID.  "
                "Leave blank to read from the MOSS_PROJECT_ID env var."
            ),
            required=False,
        ),
        MessageTextInput(
            name="index_name",
            display_name="Index Name",
            info="Name of the Moss index to query.",
            required=True,
        ),
        MessageTextInput(
            name="query",
            display_name="Search Query",
            info="The text to search for.",
            required=True,
        ),
        IntInput(
            name="top_k",
            display_name="Top K",
            info="Number of results to return.",
            value=5,
        ),
        FloatInput(
            name="alpha",
            display_name="Alpha (Hybrid Search)",
            info=(
                "Blending factor: 0.0 = pure keyword, "
                "1.0 = pure semantic, 0.5 = balanced hybrid."
            ),
            value=0.5,
        ),
        MessageTextInput(
            name="metadata_filter",
            display_name="Metadata Filter (JSON)",
            info=(
                'Optional Moss filter as JSON, e.g. {"$eq": {"category": "faq"}}.  '
                "Leave blank for no filtering."
            ),
            advanced=True,
            required=False,
        ),
    ]

    outputs = [
        Output(
            display_name="Retrieved Documents",
            name="documents",
            method="retrieve",
        ),
    ]

    def _resolve_credentials(self) -> tuple[str, str]:
        """Resolve project_id and project_key from inputs or env vars."""
        pid = self.project_id or os.getenv("MOSS_PROJECT_ID", "")
        pkey = self.project_key or os.getenv("MOSS_PROJECT_KEY", "")
        if not pid or not pkey:
            raise ValueError(
                "Moss credentials are required.  Provide project_id and "
                "project_key in the component inputs or set the "
                "MOSS_PROJECT_ID / MOSS_PROJECT_KEY environment variables."
            )
        return pid, pkey

    def retrieve(self) -> list[Data]:
        """Execute a Moss semantic search and return Data objects."""
        pid, pkey = self._resolve_credentials()

        # Cache the client + loaded index for repeated calls on the same component instance.
        if getattr(self, "_moss_creds", None) != (pid, pkey):
            self._moss_client = MossClient(pid, pkey)
            self._moss_loaded_index = None
            self._moss_creds = (pid, pkey)

        client = self._moss_client

        filter_dict = _parse_filter(self.metadata_filter or "")

        async def _search() -> list[Data]:
            if getattr(self, "_moss_loaded_index", None) != self.index_name:
                await client.load_index(self.index_name)
                self._moss_loaded_index = self.index_name
            opts = QueryOptions(
                top_k=self.top_k,
                alpha=self.alpha,
                filter=filter_dict,
            )
            results = await client.query(self.index_name, self.query, opts)

            data_list: list[Data] = []
            for doc in results.docs:
                data_list.append(
                    Data(
                        data={
                            "text": doc.text,
                            "score": doc.score,
                            "id": doc.id,
                            "metadata": doc.metadata or {},
                        }
                    )
                )
            return data_list

        docs = _run_async(_search())
        self.status = docs
        return docs


# ---------------------------------------------------------------------------
# MossSearchComponent
# ---------------------------------------------------------------------------

class MossSearchComponent(Component):
    """Search a Moss index and return formatted text.

    This component is designed to be wired directly into an LLM prompt.
    It returns a ``Message`` with numbered search results that an LLM
    can consume as context.
    """

    display_name = "Moss Search"
    description = (
        "Search a Moss index and return results as formatted text, "
        "ready for LLM prompt injection."
    )
    icon = "search"
    name = "MossSearch"

    inputs = [
        SecretStrInput(
            name="project_key",
            display_name="Moss Project Key",
            info=(
                "Your Moss project key.  "
                "Leave blank to read from the MOSS_PROJECT_KEY env var."
            ),
            required=False,
        ),
        MessageTextInput(
            name="project_id",
            display_name="Moss Project ID",
            info=(
                "Your Moss project ID.  "
                "Leave blank to read from the MOSS_PROJECT_ID env var."
            ),
            required=False,
        ),
        MessageTextInput(
            name="index_name",
            display_name="Index Name",
            info="Name of the Moss index to query.",
            required=True,
        ),
        MessageTextInput(
            name="query",
            display_name="Search Query",
            info="The text to search for.",
            required=True,
        ),
        IntInput(
            name="top_k",
            display_name="Top K",
            info="Number of results to return.",
            value=5,
        ),
        FloatInput(
            name="alpha",
            display_name="Alpha (Hybrid Search)",
            info=(
                "Blending factor: 0.0 = pure keyword, "
                "1.0 = pure semantic, 0.5 = balanced hybrid."
            ),
            value=0.5,
        ),
        MessageTextInput(
            name="metadata_filter",
            display_name="Metadata Filter (JSON)",
            info=(
                'Optional Moss filter as JSON, e.g. {"$eq": {"category": "faq"}}.  '
                "Leave blank for no filtering."
            ),
            advanced=True,
            required=False,
        ),
    ]

    outputs = [
        Output(
            display_name="Search Results",
            name="search_results",
            method="search",
        ),
    ]

    def _resolve_credentials(self) -> tuple[str, str]:
        """Resolve project_id and project_key from inputs or env vars."""
        pid = self.project_id or os.getenv("MOSS_PROJECT_ID", "")
        pkey = self.project_key or os.getenv("MOSS_PROJECT_KEY", "")
        if not pid or not pkey:
            raise ValueError(
                "Moss credentials are required.  Provide project_id and "
                "project_key in the component inputs or set the "
                "MOSS_PROJECT_ID / MOSS_PROJECT_KEY environment variables."
            )
        return pid, pkey

    def search(self) -> Message:
        """Execute a Moss search and return formatted text."""
        pid, pkey = self._resolve_credentials()
        client = MossClient(pid, pkey)

        filter_dict = _parse_filter(self.metadata_filter or "")

        async def _search() -> str:
            await client.load_index(self.index_name)
            opts = QueryOptions(
                top_k=self.top_k,
                alpha=self.alpha,
                filter=filter_dict,
            )
            results = await client.query(self.index_name, self.query, opts)

            if not results.docs:
                return "No relevant information found."

            formatted = []
            for i, doc in enumerate(results.docs, 1):
                formatted.append(
                    f"Result {i} (score: {doc.score:.3f}):\n{doc.text}"
                )
            return "\n\n".join(formatted)

        text = _run_async(_search())
        message = Message(text=text)
        self.status = message
        return message
