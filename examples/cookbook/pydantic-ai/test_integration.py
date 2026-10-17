"""Tests for the Pydantic AI + Moss cookbook integration.

All tests use mocked MossClient - no Moss credentials required.
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from moss_pydantic_ai import MossSearchTool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_search_result(docs=None):
    """Create a mock SearchResult."""
    result = MagicMock()
    result.docs = docs or []
    result.time_taken_ms = 1.5
    return result


def _mock_doc(text="sample text", score=0.95, doc_id="d1", metadata=None):
    """Create a mock QueryResultDocumentInfo."""
    doc = MagicMock()
    doc.text = text
    doc.score = score
    doc.id = doc_id
    doc.metadata = metadata or {}
    return doc


# ---------------------------------------------------------------------------
# MossSearchTool - init
# ---------------------------------------------------------------------------


class TestMossSearchToolInit(unittest.TestCase):
    """Construction and default values."""

    @patch("moss_pydantic_ai.MossClient")
    def test_defaults(self, mock_client_cls):
        client = mock_client_cls.return_value
        tool = MossSearchTool(client=client, index_name="idx")
        self.assertEqual(tool._index_name, "idx")
        self.assertEqual(tool._top_k, 5)
        self.assertAlmostEqual(tool._alpha, 0.8)
        self.assertEqual(tool._tool_name, "moss_search")

    @patch("moss_pydantic_ai.MossClient")
    def test_custom_values(self, mock_client_cls):
        client = mock_client_cls.return_value
        tool = MossSearchTool(
            client=client,
            index_name="idx",
            tool_name="custom_search",
            top_k=10,
            alpha=0.5,
        )
        self.assertEqual(tool._tool_name, "custom_search")
        self.assertEqual(tool._top_k, 10)
        self.assertAlmostEqual(tool._alpha, 0.5)

    @patch("moss_pydantic_ai.MossClient")
    def test_tool_property_returns_pydantic_tool(self, mock_client_cls):
        client = mock_client_cls.return_value
        moss = MossSearchTool(client=client, index_name="idx")
        from pydantic_ai import Tool

        self.assertIsInstance(moss.tool, Tool)


# ---------------------------------------------------------------------------
# MossSearchTool - load_index
# ---------------------------------------------------------------------------


class TestLoadIndex(unittest.IsolatedAsyncioTestCase):
    """Tests for load_index()."""

    async def test_load_index_calls_client(self):
        client = MagicMock()
        client.load_index = AsyncMock()
        tool = MossSearchTool(client=client, index_name="idx")

        await tool.load_index()

        client.load_index.assert_awaited_once_with("idx")

    async def test_load_index_calls_client_each_time(self):
        client = MagicMock()
        client.load_index = AsyncMock()
        tool = MossSearchTool(client=client, index_name="idx")

        await tool.load_index()
        await tool.load_index()

        self.assertEqual(client.load_index.await_count, 2)


# ---------------------------------------------------------------------------
# MossSearchTool - search
# ---------------------------------------------------------------------------


class TestSearch(unittest.IsolatedAsyncioTestCase):
    """Tests for search()."""

    async def test_search_formats_results(self):
        client = MagicMock()
        client.load_index = AsyncMock()
        client.query = AsyncMock(
            return_value=_mock_search_result(
                [
                    _mock_doc("first result", 0.9, "d1"),
                    _mock_doc("second result", 0.7, "d2"),
                ]
            )
        )
        tool = MossSearchTool(client=client, index_name="idx")
        await tool.load_index()

        output = await tool.search("test query")

        self.assertIn("first result", output)
        self.assertIn("second result", output)
        self.assertIn("score=0.900", output)
        self.assertIn("score=0.700", output)

    async def test_search_empty_results(self):
        client = MagicMock()
        client.load_index = AsyncMock()
        client.query = AsyncMock(return_value=_mock_search_result([]))
        tool = MossSearchTool(client=client, index_name="idx")
        await tool.load_index()

        output = await tool.search("empty query")

        self.assertEqual(output, "No relevant results found.")

    async def test_search_queries_without_preload(self):
        client = MagicMock()
        client.query = AsyncMock(
            return_value=_mock_search_result([_mock_doc("fallback result", 0.88, "d1")])
        )
        tool = MossSearchTool(client=client, index_name="idx")

        output = await tool.search("test")

        client.query.assert_awaited_once()
        self.assertIn("fallback result", output)

    async def test_search_includes_metadata_source(self):
        client = MagicMock()
        client.load_index = AsyncMock()
        client.query = AsyncMock(
            return_value=_mock_search_result(
                [_mock_doc("doc text", 0.85, "d1", {"source": "faq.md"})]
            )
        )
        tool = MossSearchTool(client=client, index_name="idx")
        await tool.load_index()

        output = await tool.search("q")

        self.assertIn("source=faq.md", output)


# ---------------------------------------------------------------------------
# Format results - edge cases
# ---------------------------------------------------------------------------


class TestFormatResults(unittest.TestCase):
    """Tests for _format_results edge cases."""

    def test_empty_docs(self):
        result = MossSearchTool._format_results([])
        self.assertIn("No relevant results found", result)

    def test_numbered_results(self):
        docs = [
            _mock_doc("first", 0.9),
            _mock_doc("second", 0.8),
            _mock_doc("third", 0.7),
        ]
        result = MossSearchTool._format_results(docs)
        self.assertIn("1. first", result)
        self.assertIn("2. second", result)
        self.assertIn("3. third", result)

    def test_doc_with_no_metadata(self):
        doc = _mock_doc("plain text", 0.99, metadata={})
        result = MossSearchTool._format_results([doc])
        self.assertIn("1. plain text", result)
        self.assertIn("score=0.990", result)


if __name__ == "__main__":
    unittest.main()
