"""Unit tests for query metrics and tracing hooks in MossClient."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from moss import (
    MossClient,
    QueryMetrics,
    QueryOptions,
    QueryResultDocumentInfo,
    SearchResult,
)


class TestQueryMetricsDataclass:
    """Tests for the QueryMetrics dataclass."""

    def test_success_metrics_properties(self):
        metrics = QueryMetrics(
            index_name="products",
            query="wireless headphones",
            duration_ms=12.5,
            result_count=3,
            is_local=True,
            top_k=5,
            alpha=0.8,
            engine_time_ms=2,
            error=None,
        )

        assert metrics.index_name == "products"
        assert metrics.query == "wireless headphones"
        assert metrics.duration_ms == 12.5
        assert metrics.result_count == 3
        assert metrics.is_local is True
        assert metrics.top_k == 5
        assert metrics.alpha == 0.8
        assert metrics.engine_time_ms == 2
        assert metrics.error is None
        assert metrics.is_success is True

    def test_error_metrics_properties(self):
        err = RuntimeError("network failure")
        metrics = QueryMetrics(
            index_name="products",
            query="test",
            duration_ms=5.0,
            result_count=0,
            is_local=False,
            error=err,
        )

        assert metrics.is_success is False
        assert metrics.error == err
        assert metrics.result_count == 0

    def test_as_dict_serialization(self):
        metrics = QueryMetrics(
            index_name="docs",
            query="search query",
            duration_ms=8.4,
            result_count=2,
            is_local=True,
            top_k=10,
            alpha=0.5,
            engine_time_ms=1,
            error=None,
        )

        d = metrics.as_dict()
        assert d == {
            "index_name": "docs",
            "query": "search query",
            "duration_ms": 8.4,
            "result_count": 2,
            "is_local": True,
            "top_k": 10,
            "alpha": 0.5,
            "engine_time_ms": 1,
            "is_success": True,
            "error": None,
        }

    def test_as_dict_with_error(self):
        err = ValueError("bad query")
        metrics = QueryMetrics(
            index_name="docs",
            query="bad",
            duration_ms=1.2,
            result_count=0,
            is_local=True,
            error=err,
        )

        d = metrics.as_dict()
        assert d["is_success"] is False
        assert d["error"] == "bad query"


class TestMossClientHookConfiguration:
    """Tests for configuring hooks on MossClient."""

    def test_init_without_hook_defaults_to_none(self):
        with (
            patch("moss.client.moss_client.ManageClient"),
            patch("moss.client.moss_client.IndexManager"),
        ):
            client = MossClient("pid", "pkey")
            assert client.on_query is None

    def test_init_with_single_hook(self):
        hook = MagicMock()
        with (
            patch("moss.client.moss_client.ManageClient"),
            patch("moss.client.moss_client.IndexManager"),
        ):
            client = MossClient("pid", "pkey", on_query=hook)
            assert client.on_query == hook

    def test_on_query_setter(self):
        hook1 = MagicMock()
        hook2 = MagicMock()
        with (
            patch("moss.client.moss_client.ManageClient"),
            patch("moss.client.moss_client.IndexManager"),
        ):
            client = MossClient("pid", "pkey", on_query=hook1)
            assert client.on_query == hook1

            client.on_query = hook2
            assert client.on_query == hook2

            client.on_query = None
            assert client.on_query is None


class TestMetricsEmission:
    """Tests for metrics emission on query execution."""

    @pytest.mark.asyncio
    async def test_sync_hook_called_on_successful_local_query(self, client):
        captured: list[QueryMetrics] = []

        def hook(m: QueryMetrics):
            captured.append(m)

        client.on_query = hook

        mock_search_result = SearchResult(
            docs=[
                QueryResultDocumentInfo(id="d1", text="text1", score=0.9),
                QueryResultDocumentInfo(id="d2", text="text2", score=0.8),
            ],
            query="hello world",
            index_name="idx",
            time_taken_ms=3,
        )
        client._manager.query_text = MagicMock(return_value=mock_search_result)

        opts = QueryOptions(top_k=5, alpha=0.8)
        result = await client.query("idx", "hello world", opts)

        assert result == mock_search_result
        assert len(captured) == 1
        m = captured[0]
        assert m.index_name == "idx"
        assert m.query == "hello world"
        assert m.duration_ms > 0
        assert m.result_count == 2
        assert m.is_local is True
        assert m.top_k == 5
        assert m.alpha == pytest.approx(0.8)
        assert m.engine_time_ms == 3
        assert m.is_success is True
        assert m.error is None

    @pytest.mark.asyncio
    async def test_async_hook_called_and_awaited(self, client):
        captured: list[QueryMetrics] = []

        async def async_hook(m: QueryMetrics):
            await asyncio.sleep(0.001)
            captured.append(m)

        client.on_query = async_hook

        mock_search_result = SearchResult(
            docs=[QueryResultDocumentInfo(id="d1", text="text1", score=0.95)],
            query="async test",
            index_name="my-index",
            time_taken_ms=1,
        )
        client._manager.query_text = MagicMock(return_value=mock_search_result)

        await client.query("my-index", "async test")

        assert len(captured) == 1
        assert captured[0].index_name == "my-index"
        assert captured[0].result_count == 1
        assert captured[0].is_success is True

    @pytest.mark.asyncio
    async def test_multiple_hooks_sequence(self, client):
        hook1_events = []
        hook2_events = []

        def hook1(m: QueryMetrics):
            hook1_events.append(m)

        def hook2(m: QueryMetrics):
            hook2_events.append(m)

        client.on_query = [hook1, hook2]

        mock_search_result = SearchResult(docs=[], query="q", index_name="idx")
        client._manager.query_text = MagicMock(return_value=mock_search_result)

        await client.query("idx", "q")

        assert len(hook1_events) == 1
        assert len(hook2_events) == 1

    @pytest.mark.asyncio
    async def test_per_query_hook_parameter(self, client):
        client_hook_events = []
        query_hook_events = []

        def client_hook(m: QueryMetrics):
            client_hook_events.append(m)

        def query_hook(m: QueryMetrics):
            query_hook_events.append(m)

        client.on_query = client_hook

        mock_search_result = SearchResult(docs=[], query="q", index_name="idx")
        client._manager.query_text = MagicMock(return_value=mock_search_result)

        await client.query("idx", "q", on_query=query_hook)

        assert len(client_hook_events) == 1
        assert len(query_hook_events) == 1

    @pytest.mark.asyncio
    async def test_cloud_fallback_metrics_emission(self, unloaded_client):
        captured: list[QueryMetrics] = []

        unloaded_client.on_query = lambda m: captured.append(m)

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {
            "docs": [{"id": "cloud-doc-1", "text": "cloud content", "score": 0.88}],
            "query": "cloud search",
            "indexName": "remote-idx",
            "timeTakenMs": 150,
        }

        with patch("moss.client.moss_client.httpx.AsyncClient") as mock_httpx:
            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_httpx.return_value.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await unloaded_client.query("remote-idx", "cloud search")

        assert len(result.docs) == 1
        assert len(captured) == 1
        m = captured[0]
        assert m.index_name == "remote-idx"
        assert m.query == "cloud search"
        assert m.is_local is False
        assert m.result_count == 1
        assert m.engine_time_ms == 150
        assert m.is_success is True

    @pytest.mark.asyncio
    async def test_query_error_emits_failure_metrics(self, client):
        captured: list[QueryMetrics] = []

        client.on_query = lambda m: captured.append(m)
        client._manager.query_text = MagicMock(
            side_effect=RuntimeError("Index corrupt")
        )

        with pytest.raises(RuntimeError, match="Index corrupt"):
            await client.query("idx", "failing query")

        assert len(captured) == 1
        m = captured[0]
        assert m.index_name == "idx"
        assert m.query == "failing query"
        assert m.duration_ms > 0
        assert m.result_count == 0
        assert m.is_success is False
        assert isinstance(m.error, RuntimeError)
        assert str(m.error) == "Index corrupt"

    @pytest.mark.asyncio
    async def test_hook_exception_does_not_break_query(self, client, caplog):
        def faulty_hook(m: QueryMetrics):
            raise Exception("StatsD sink down!")

        client.on_query = faulty_hook

        mock_search_result = SearchResult(
            docs=[QueryResultDocumentInfo(id="d1", text="ok", score=1.0)],
            query="resilient test",
            index_name="idx",
        )
        client._manager.query_text = MagicMock(return_value=mock_search_result)

        result = await client.query("idx", "resilient test")

        assert len(result.docs) == 1
        assert "Error executing query metrics hook" in caplog.text
        assert "StatsD sink down!" in caplog.text

    @pytest.mark.asyncio
    async def test_async_hook_exception_does_not_break_query(self, client, caplog):
        async def faulty_async_hook(m: QueryMetrics):
            await asyncio.sleep(0.001)
            raise ConnectionError("Remote telemetry timeout")

        client.on_query = faulty_async_hook

        mock_search_result = SearchResult(
            docs=[QueryResultDocumentInfo(id="d1", text="ok", score=1.0)],
            query="async resilient test",
            index_name="idx",
        )
        client._manager.query_text = MagicMock(return_value=mock_search_result)

        result = await client.query("idx", "async resilient test")

        assert len(result.docs) == 1
        assert "Error executing query metrics hook" in caplog.text
        assert "Remote telemetry timeout" in caplog.text

    @pytest.mark.asyncio
    async def test_faulty_hook_does_not_prevent_other_hooks(self, client):
        second_hook_captured = []

        def bad_hook(m: QueryMetrics):
            raise ValueError("bad hook")

        def good_hook(m: QueryMetrics):
            second_hook_captured.append(m)

        client.on_query = [bad_hook, good_hook]

        mock_search_result = SearchResult(docs=[], query="q", index_name="idx")
        client._manager.query_text = MagicMock(return_value=mock_search_result)

        await client.query("idx", "q")

        assert len(second_hook_captured) == 1
