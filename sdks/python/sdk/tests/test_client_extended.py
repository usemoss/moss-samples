"""Extended unit tests for MossClient covering edge cases and additional functionality."""

from __future__ import annotations

from importlib.metadata import version
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from moss import MossClient, __version__
from moss.client.moss_client import _get_manage_url, _get_query_url


class TestUnloadIndex:
    """Tests for unload_index method."""

    @pytest.mark.asyncio
    async def test_unload_delegates_to_index_manager(self, client):
        client._manager.unload_index = MagicMock(return_value=None)

        await client.unload_index("idx")

        client._manager.unload_index.assert_called_once_with("idx")

    @pytest.mark.asyncio
    async def test_unload_wraps_runtime_error(self, client):
        client._manager.unload_index = MagicMock(
            side_effect=RuntimeError("index not found")
        )

        with pytest.raises(RuntimeError, match="Failed to unload index 'idx'"):
            await client.unload_index("idx")

    @pytest.mark.asyncio
    async def test_unload_returns_none(self, client):
        client._manager.unload_index = MagicMock(return_value=None)

        result = await client.unload_index("idx")

        assert result is None


class TestCloudFallbackErrors:
    """Tests for cloud fallback error handling."""

    @pytest.mark.asyncio
    async def test_cloud_fallback_http_error(self, unloaded_client):
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 500

        with patch("moss.client.moss_client.httpx.AsyncClient") as mock_httpx:
            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_httpx.return_value.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(Exception, match="HTTP error! status: 500"):
                await unloaded_client.query("idx", "test query")

    @pytest.mark.asyncio
    async def test_cloud_fallback_network_error(self, unloaded_client):
        with patch("moss.client.moss_client.httpx.AsyncClient") as mock_httpx:
            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(
                side_effect=httpx.RequestError("Connection refused")
            )
            mock_httpx.return_value.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(Exception, match="Cloud query request failed"):
                await unloaded_client.query("idx", "test query")

    @pytest.mark.asyncio
    async def test_cloud_fallback_with_custom_embedding(self, unloaded_client):
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {
            "docs": [{"id": "d1", "text": "test", "score": 0.9}],
            "query": "test",
            "indexName": "idx",
            "timeTakenMs": 10,
        }

        with patch("moss.client.moss_client.httpx.AsyncClient") as mock_httpx:
            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_httpx.return_value.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

            opts = MagicMock()
            opts.top_k = 5
            opts.embedding = [0.1, 0.2, 0.3]
            opts.filter = None

            result = await unloaded_client.query("idx", "test query", opts)

            assert len(result.docs) == 1
            call_args = mock_client_instance.post.call_args
            request_body = call_args[1]["json"]
            assert "queryEmbedding" in request_body


class TestDictToSearchResult:
    """Tests for _dict_to_search_result helper method."""

    def test_basic_conversion(self):
        data = {
            "docs": [
                {"id": "d1", "text": "hello", "score": 0.9},
                {"id": "d2", "text": "world", "score": 0.5},
            ],
            "query": "test query",
            "indexName": "my-index",
            "timeTakenMs": 42,
        }

        result = MossClient._dict_to_search_result(data)

        assert len(result.docs) == 2
        assert result.docs[0].id == "d1"
        assert result.docs[0].text == "hello"
        assert result.docs[0].score == pytest.approx(0.9, abs=1e-6)
        assert result.docs[1].id == "d2"
        assert result.docs[1].score == pytest.approx(0.5, abs=1e-6)
        assert result.query == "test query"
        assert result.index_name == "my-index"
        assert result.time_taken_ms == 42

    def test_empty_docs(self):
        data = {"docs": [], "query": "", "indexName": "idx", "timeTakenMs": 0}

        result = MossClient._dict_to_search_result(data)

        assert len(result.docs) == 0

    def test_missing_doc_fields(self):
        data = {
            "docs": [{"id": "d1"}, {"text": "hello"}, {"score": 0.5}],
            "query": "q",
            "indexName": "idx",
        }

        result = MossClient._dict_to_search_result(data)

        assert result.docs[0].id == "d1"
        assert result.docs[0].text == ""
        assert result.docs[0].score == 0.0
        assert result.docs[1].text == "hello"
        assert result.docs[1].score == 0.0
        assert result.docs[2].score == 0.5

    def test_docs_with_metadata(self):
        data = {
            "docs": [
                {
                    "id": "d1",
                    "text": "test",
                    "score": 0.9,
                    "metadata": {"city": "NYC"},
                }
            ],
            "query": "q",
            "indexName": "idx",
        }

        result = MossClient._dict_to_search_result(data)

        assert result.docs[0].metadata == {"city": "NYC"}

    def test_score_type_coercion(self):
        data = {
            "docs": [
                {"id": "d1", "text": "test", "score": "0.95"},
                {"id": "d2", "text": "test", "score": 1},
            ],
            "query": "q",
            "indexName": "idx",
        }

        result = MossClient._dict_to_search_result(data)

        assert result.docs[0].score == pytest.approx(0.95, abs=1e-6)
        assert result.docs[1].score == pytest.approx(1.0, abs=1e-6)

    def test_missing_top_level_fields(self):
        data = {}

        result = MossClient._dict_to_search_result(data)

        assert len(result.docs) == 0
        assert result.query == ""
        assert result.index_name is None
        assert result.time_taken_ms is None


class TestURLHelpers:
    """Tests for URL helper functions."""

    def test_get_manage_url_default(self):
        with patch.dict("os.environ", {}, clear=True):
            url = _get_manage_url()
            assert "/v1/manage" in url

    def test_get_manage_url_from_env(self):
        with patch.dict(
            "os.environ",
            {"MOSS_CLOUD_API_MANAGE_URL": "https://custom.example.com/v1/manage"},
        ):
            url = _get_manage_url()
            assert url == "https://custom.example.com/v1/manage"

    def test_get_query_url_derived(self):
        with patch.dict(
            "os.environ",
            {"MOSS_CLOUD_API_MANAGE_URL": "https://api.example.com/v1/manage"},
        ):
            url = _get_query_url()
            assert url == "https://api.example.com/query"

    def test_get_query_url_explicit(self):
        with patch.dict(
            "os.environ",
            {
                "MOSS_CLOUD_API_MANAGE_URL": "https://api.example.com/v1/manage",
                "MOSS_CLOUD_QUERY_URL": "https://query.example.com/search",
            },
        ):
            url = _get_query_url()
            assert url == "https://query.example.com/search"


class TestVersionExport:
    """Tests for version export."""

    def test_version_is_defined(self):
        assert __version__ is not None
        assert isinstance(__version__, str)
        assert len(__version__) > 0

    def test_version_format(self):
        assert __version__ == version("moss")


class TestQueryOptionsBehavior:
    """Tests for QueryOptions behavior in query operations."""

    @pytest.mark.asyncio
    async def test_query_with_only_top_k(self, client):
        mock_result = MagicMock()
        client._manager.query_text = MagicMock(return_value=mock_result)

        opts = MagicMock()
        opts.top_k = 10
        opts.alpha = None
        opts.embedding = None
        opts.filter = None

        await client.query("idx", "test", opts)

        client._manager.query_text.assert_called_once_with("idx", "test", 10, 0.8, None)

    @pytest.mark.asyncio
    async def test_query_with_only_alpha(self, client):
        mock_result = MagicMock()
        client._manager.query_text = MagicMock(return_value=mock_result)

        opts = MagicMock()
        opts.top_k = None
        opts.alpha = 0.5
        opts.embedding = None
        opts.filter = None

        await client.query("idx", "test", opts)

        client._manager.query_text.assert_called_once_with("idx", "test", 5, 0.5, None)

    @pytest.mark.asyncio
    async def test_query_alpha_zero_keyword_only(self, client):
        mock_result = MagicMock()
        client._manager.query_text = MagicMock(return_value=mock_result)

        opts = MagicMock()
        opts.top_k = 5
        opts.alpha = 0
        opts.embedding = None
        opts.filter = None

        await client.query("idx", "test", opts)

        client._manager.query_text.assert_called_once_with("idx", "test", 5, 0, None)

    @pytest.mark.asyncio
    async def test_query_alpha_one_semantic_only(self, client):
        mock_result = MagicMock()
        client._manager.query_text = MagicMock(return_value=mock_result)

        opts = MagicMock()
        opts.top_k = 5
        opts.alpha = 1
        opts.embedding = None
        opts.filter = None

        await client.query("idx", "test", opts)

        client._manager.query_text.assert_called_once_with("idx", "test", 5, 1, None)


class TestMetadataFilterWarning:
    """Tests for metadata filter warning when index is not loaded."""

    @pytest.mark.asyncio
    async def test_filter_warning_logged_when_unloaded(self, unloaded_client, caplog):
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {"docs": [], "query": "q"}

        with patch("moss.client.moss_client.httpx.AsyncClient") as mock_httpx:
            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_httpx.return_value.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

            opts = MagicMock()
            opts.filter = {"field": "city", "condition": {"$eq": "NYC"}}

            with caplog.at_level("WARNING"):
                await unloaded_client.query("idx", "test", opts)

            assert "Metadata filter ignored" in caplog.text
            assert "idx" in caplog.text


class TestClientIdGeneration:
    """Tests for client ID generation."""

    def test_client_id_is_uuid(self, client):
        assert client._client_id is not None
        assert len(client._client_id) == 36
        assert client._client_id.count("-") == 4

    def test_client_id_is_unique(self):
        with (
            patch("moss.client.moss_client.ManageClient"),
            patch("moss.client.moss_client.IndexManager"),
        ):
            c1 = MossClient("pid", "pkey")
            c2 = MossClient("pid", "pkey")
            assert c1._client_id != c2._client_id


class TestProjectCredentials:
    """Tests for project credential handling."""

    def test_credentials_stored(self, client):
        assert client._project_id == "test-project"
        assert client._project_key == "test-key"

    def test_credentials_passed_to_manage_client(self):
        with (
            patch("moss.client.moss_client.ManageClient") as mock_manage,
            patch("moss.client.moss_client.IndexManager"),
        ):
            MossClient("my-project-id", "my-secret-key")

            args = mock_manage.call_args[0]
            assert args[0] == "my-project-id"
            assert args[1] == "my-secret-key"

    def test_credentials_passed_to_index_manager(self):
        with (
            patch("moss.client.moss_client.ManageClient"),
            patch("moss.client.moss_client.IndexManager") as mock_mgr,
        ):
            MossClient("pid", "pkey")

            args = mock_mgr.call_args[0]
            assert args[0] == "pid"
            assert args[1] == "pkey"
