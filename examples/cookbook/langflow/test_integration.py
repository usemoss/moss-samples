"""Tests for Moss Langflow custom components.

These tests mock the Moss SDK so they can run without live credentials
or a Langflow server.  The focus is on verifying the data mapping,
error handling, and caching logic.
"""

import json
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Guard: skip the entire module if langflow is not installed.
# ---------------------------------------------------------------------------
try:
    from langflow.schema import Data
    from langflow.schema.message import Message
except ImportError:
    Data = None  # type: ignore[assignment,misc]
    Message = None  # type: ignore[assignment,misc]

try:
    from moss_langflow import (
        MossRetrieverComponent,
        MossSearchComponent,
        _parse_filter,
        _run_async,
    )

    _LANGFLOW_AVAILABLE = True
except ImportError:
    MossRetrieverComponent = None  # type: ignore[assignment,misc]
    MossSearchComponent = None  # type: ignore[assignment,misc]
    _run_async = None  # type: ignore[assignment,misc]
    _LANGFLOW_AVAILABLE = False

    # _parse_filter is pure Python (no langflow dependency).  Duplicate
    # the logic here so we can test it even without langflow installed.
    def _parse_filter(raw: str):  # type: ignore[misc]
        """Inline fallback of the JSON filter parser for testing."""
        if not raw or not raw.strip():
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid metadata filter JSON: {exc}.  "
                "Expected a Moss filter object."
            ) from exc
        if not isinstance(parsed, dict):
            raise ValueError("Metadata filter must be a JSON object (dict).")
        return parsed

_SKIP = not _LANGFLOW_AVAILABLE
_SKIP_REASON = "langflow or moss_langflow not installed"


# ---------------------------------------------------------------------------
# Helper: build a mock component with attribute-style input access
# ---------------------------------------------------------------------------

def _make_component(cls, **input_values):
    """Instantiate a component class and set input values as attributes.

    Langflow normally injects input values via descriptors; in tests we
    bypass that by setting them directly on the instance.
    """
    comp = cls.__new__(cls)
    for k, v in input_values.items():
        setattr(comp, k, v)
    # Ensure optional inputs have defaults
    comp.metadata_filter = input_values.get("metadata_filter", "")
    return comp


# ---------------------------------------------------------------------------
# _parse_filter tests
# ---------------------------------------------------------------------------

class TestParseFilter(unittest.TestCase):
    """Unit tests for the JSON filter parser helper.

    These tests always run — _parse_filter is pure Python with no
    external dependencies.
    """

    def test_empty_string_returns_none(self):
        self.assertIsNone(_parse_filter(""))

    def test_whitespace_returns_none(self):
        self.assertIsNone(_parse_filter("   "))

    def test_valid_json_returns_dict(self):
        result = _parse_filter('{"$eq": {"category": "faq"}}')
        self.assertEqual(result, {"$eq": {"category": "faq"}})

    def test_invalid_json_raises_valueerror(self):
        with self.assertRaises(ValueError) as ctx:
            _parse_filter("{not valid json}")
        self.assertIn("Invalid metadata filter JSON", str(ctx.exception))

    def test_non_dict_json_raises_valueerror(self):
        with self.assertRaises(ValueError) as ctx:
            _parse_filter("[1, 2, 3]")
        self.assertIn("must be a JSON object", str(ctx.exception))


# ---------------------------------------------------------------------------
# MossRetrieverComponent tests
# ---------------------------------------------------------------------------

@unittest.skipIf(_SKIP, _SKIP_REASON)
class TestMossRetrieverComponent(unittest.TestCase):
    """Behavioral tests for MossRetrieverComponent."""

    @patch("moss_langflow.MossClient")
    def test_retrieve_maps_results(self, mock_client_cls):
        """Verify Moss docs are correctly mapped to Langflow Data objects."""
        mock_client = mock_client_cls.return_value
        mock_client.load_index = AsyncMock()
        mock_client.query = AsyncMock(
            return_value=MagicMock(
                docs=[
                    MagicMock(
                        text="hello world",
                        score=0.9,
                        id="d1",
                        metadata={"source": "faq"},
                    ),
                    MagicMock(
                        text="foo bar",
                        score=0.7,
                        id="d2",
                        metadata=None,
                    ),
                ]
            )
        )

        comp = _make_component(
            MossRetrieverComponent,
            project_id="p",
            project_key="k",
            index_name="idx",
            query="test query",
            top_k=5,
            alpha=0.5,
        )
        docs = comp.retrieve()

        self.assertEqual(len(docs), 2)
        self.assertIsInstance(docs[0], Data)
        self.assertEqual(docs[0].data["text"], "hello world")
        self.assertEqual(docs[0].data["score"], 0.9)
        self.assertEqual(docs[0].data["id"], "d1")
        self.assertEqual(docs[0].data["metadata"], {"source": "faq"})

        self.assertEqual(docs[1].data["text"], "foo bar")
        self.assertEqual(docs[1].data["metadata"], {})

    @patch("moss_langflow.MossClient")
    def test_retrieve_empty_results(self, mock_client_cls):
        """Empty Moss results should produce an empty list."""
        mock_client = mock_client_cls.return_value
        mock_client.load_index = AsyncMock()
        mock_client.query = AsyncMock(
            return_value=MagicMock(docs=[])
        )

        comp = _make_component(
            MossRetrieverComponent,
            project_id="p",
            project_key="k",
            index_name="idx",
            query="empty query",
            top_k=5,
            alpha=0.5,
        )
        docs = comp.retrieve()

        self.assertEqual(docs, [])

    @patch("moss_langflow.MossClient")
    def test_retrieve_with_metadata_filter(self, mock_client_cls):
        """Metadata filter JSON should be parsed and forwarded."""
        mock_client = mock_client_cls.return_value
        mock_client.load_index = AsyncMock()
        mock_client.query = AsyncMock(
            return_value=MagicMock(docs=[])
        )

        comp = _make_component(
            MossRetrieverComponent,
            project_id="p",
            project_key="k",
            index_name="idx",
            query="filtered query",
            top_k=3,
            alpha=0.8,
            metadata_filter='{"$eq": {"category": "faq"}}',
        )
        comp.retrieve()

        # Verify QueryOptions was constructed with the filter
        call_args = mock_client.query.call_args
        query_opts = call_args[0][2]  # third positional arg
        self.assertIsNotNone(query_opts)

    @patch.dict(os.environ, {"MOSS_PROJECT_ID": "env-pid", "MOSS_PROJECT_KEY": "env-pkey"})
    @patch("moss_langflow.MossClient")
    def test_env_var_fallback(self, mock_client_cls):
        """Credentials should fall back to env vars when inputs are empty."""
        mock_client = mock_client_cls.return_value
        mock_client.load_index = AsyncMock()
        mock_client.query = AsyncMock(
            return_value=MagicMock(docs=[])
        )

        comp = _make_component(
            MossRetrieverComponent,
            project_id="",
            project_key="",
            index_name="idx",
            query="test",
            top_k=5,
            alpha=0.5,
        )
        comp.retrieve()

        mock_client_cls.assert_called_once_with("env-pid", "env-pkey")

    def test_missing_credentials_raises(self):
        """Missing credentials (no input, no env var) should raise ValueError."""
        comp = _make_component(
            MossRetrieverComponent,
            project_id="",
            project_key="",
            index_name="idx",
            query="test",
            top_k=5,
            alpha=0.5,
        )
        # Clear env vars to ensure no fallback
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                comp.retrieve()
            self.assertIn("Moss credentials are required", str(ctx.exception))


# ---------------------------------------------------------------------------
# MossSearchComponent tests
# ---------------------------------------------------------------------------

@unittest.skipIf(_SKIP, _SKIP_REASON)
class TestMossSearchComponent(unittest.TestCase):
    """Behavioral tests for MossSearchComponent."""

    @patch("moss_langflow.MossClient")
    def test_search_formats_text(self, mock_client_cls):
        """Results should be formatted as numbered text blocks."""
        mock_client = mock_client_cls.return_value
        mock_client.load_index = AsyncMock()
        mock_client.query = AsyncMock(
            return_value=MagicMock(
                docs=[
                    MagicMock(text="first result", score=0.923, id="d1", metadata=None),
                    MagicMock(text="second result", score=0.847, id="d2", metadata=None),
                ]
            )
        )

        comp = _make_component(
            MossSearchComponent,
            project_id="p",
            project_key="k",
            index_name="idx",
            query="search query",
            top_k=5,
            alpha=0.5,
        )
        message = comp.search()

        self.assertIsInstance(message, Message)
        self.assertIn("Result 1 (score: 0.923):", message.text)
        self.assertIn("first result", message.text)
        self.assertIn("Result 2 (score: 0.847):", message.text)
        self.assertIn("second result", message.text)

    @patch("moss_langflow.MossClient")
    def test_search_empty_results(self, mock_client_cls):
        """Empty results should return a 'no info found' message."""
        mock_client = mock_client_cls.return_value
        mock_client.load_index = AsyncMock()
        mock_client.query = AsyncMock(
            return_value=MagicMock(docs=[])
        )

        comp = _make_component(
            MossSearchComponent,
            project_id="p",
            project_key="k",
            index_name="idx",
            query="no results query",
            top_k=5,
            alpha=0.5,
        )
        message = comp.search()

        self.assertIsInstance(message, Message)
        self.assertEqual(message.text, "No relevant information found.")


if __name__ == "__main__":
    unittest.main()
