from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from moss import MossClient, QueryOptions, QueryResultDocumentInfo, SearchResult


@pytest.fixture(autouse=True)
def clear_cross_encoder_cache():
    MossClient._cross_encoder_cache.clear()
    MossClient._cross_encoder_locks.clear()
    yield
    MossClient._cross_encoder_cache.clear()
    MossClient._cross_encoder_locks.clear()


def test_query_options_validation():
    # Test valid options
    opts = QueryOptions(
        top_k=5, alpha=0.5, embedding=[0.1, 0.2], rerank=True, rerank_top_k=10
    )
    assert opts.top_k == 5
    assert opts.alpha == 0.5
    assert opts.embedding == [0.1, 0.2]
    assert opts.rerank is True
    assert opts.rerank_top_k == 10

    # Test default values
    default_opts = QueryOptions()
    assert default_opts.top_k is None
    assert default_opts.alpha is None
    assert default_opts.embedding is None
    assert default_opts.rerank is False
    assert default_opts.rerank_top_k is None
    assert default_opts.rerank_model is None

    # Test invalid top_k
    with pytest.raises(ValueError, match="top_k must be an integer >= 1"):
        QueryOptions(top_k=-1)

    with pytest.raises(ValueError, match="top_k must be an integer >= 1"):
        QueryOptions(top_k=0)

    # Test invalid alpha
    with pytest.raises(ValueError, match="alpha must be a float between 0.0 and 1.0"):
        QueryOptions(alpha=2.0)

    with pytest.raises(ValueError, match="alpha must be a float between 0.0 and 1.0"):
        QueryOptions(alpha=-0.1)

    # Test invalid embedding
    with pytest.raises(ValueError, match="embedding must be a sequence of numbers"):
        QueryOptions(embedding=["invalid"])  # type: ignore

    # Test invalid rerank_top_k
    with pytest.raises(ValueError, match="rerank_top_k must be an integer >= 1"):
        QueryOptions(rerank_top_k=0)

    with pytest.raises(ValueError, match="rerank_top_k must be an integer >= 1"):
        QueryOptions(rerank_top_k=-5)

    # Test rerank_top_k < top_k
    with pytest.raises(ValueError, match="rerank_top_k must be >= top_k"):
        QueryOptions(top_k=10, rerank_top_k=5)


@pytest.mark.asyncio
async def test_rerank_results():
    client = MossClient("test", "key")

    # Create fake docs
    doc1 = QueryResultDocumentInfo(id="1", text="Bad match", score=0.9)
    doc2 = QueryResultDocumentInfo(id="2", text="Good match", score=0.8)
    doc3 = QueryResultDocumentInfo(id="3", text="Okay match", score=0.85)

    search_result = SearchResult(
        docs=[doc1, doc2, doc3],
        query="test query",
        index_name="idx",
        time_taken_ms=10,
    )

    opts = QueryOptions(top_k=2, rerank=True, rerank_model="mock-model")

    mock_model = MagicMock()
    # Let's say the cross encoder scores doc2 the highest, then doc3, then doc1
    mock_model.predict.return_value = [0.1, 0.99, 0.5]

    with patch.dict(
        "sys.modules",
        {
            "sentence_transformers": MagicMock(
                CrossEncoder=MagicMock(return_value=mock_model)
            )
        },
    ):
        result = await client._rerank_results("test query", search_result, opts)

        # It should slice to top_k=2, so doc1 should be dropped
        assert len(result.docs) == 2

        # First should be doc2
        assert result.docs[0].id == "2"
        assert result.docs[0].score == pytest.approx(0.99, abs=1e-5)

        # Second should be doc3
        assert result.docs[1].id == "3"
        assert result.docs[1].score == pytest.approx(0.5, abs=1e-5)

        # Ensure predict was called with pairs
        mock_model.predict.assert_called_once_with(
            [
                ["test query", "Bad match"],
                ["test query", "Good match"],
                ["test query", "Okay match"],
            ]
        )


@pytest.mark.asyncio
async def test_rerank_results_empty_docs():
    client = MossClient("test", "key")
    search_result = SearchResult(docs=[], query="test", index_name="idx")
    opts = QueryOptions(rerank=True)

    result = await client._rerank_results("test", search_result, opts)
    assert result.docs == []


@pytest.mark.asyncio
async def test_rerank_missing_dependency():
    client = MossClient("test", "key")
    doc = QueryResultDocumentInfo(id="1", text="Doc", score=0.5)
    search_result = SearchResult(docs=[doc], query="test", index_name="idx")
    opts = QueryOptions(rerank=True)

    with patch.dict("sys.modules", {"sentence_transformers": None}):
        with pytest.raises(ImportError, match="sentence-transformers"):
            await client._rerank_results("test", search_result, opts)


@pytest.mark.asyncio
async def test_query_integration_with_rerank_local():
    with (
        patch("moss.client.moss_client.ManageClient"),
        patch("moss.client.moss_client.IndexManager") as mock_mgr_cls,
    ):
        client = MossClient("pid", "pkey")
        mock_mgr = mock_mgr_cls.return_value
        mock_mgr.has_index.return_value = True

        docs = [
            QueryResultDocumentInfo(id="1", text="Doc 1", score=0.9),
            QueryResultDocumentInfo(id="2", text="Doc 2", score=0.8),
            QueryResultDocumentInfo(id="3", text="Doc 3", score=0.7),
        ]
        mock_mgr.query_text.return_value = SearchResult(
            docs=docs, query="query", index_name="idx"
        )

        mock_cross_encoder = MagicMock()
        mock_cross_encoder.predict.return_value = [0.2, 0.9, 0.5]

        with patch.dict(
            "sys.modules",
            {
                "sentence_transformers": MagicMock(
                    CrossEncoder=MagicMock(return_value=mock_cross_encoder)
                )
            },
        ):
            opts = QueryOptions(top_k=2, rerank=True, rerank_top_k=3)
            result = await client.query("idx", "query", options=opts)

            # query_text should have received top_k=3 (the candidate pool)
            mock_mgr.query_text.assert_called_once_with("idx", "query", 3, 0.8, None)

            # Final returned results should be sliced to top_k=2 and sorted by reranker
            assert len(result.docs) == 2
            assert result.docs[0].id == "2"
            assert result.docs[1].id == "3"


@pytest.mark.asyncio
async def test_query_integration_with_rerank_cloud():
    with (
        patch("moss.client.moss_client.ManageClient"),
        patch("moss.client.moss_client.IndexManager") as mock_mgr_cls,
    ):
        client = MossClient("pid", "pkey")
        mock_mgr = mock_mgr_cls.return_value
        mock_mgr.has_index.return_value = False

        mock_cross_encoder = MagicMock()
        mock_cross_encoder.predict.return_value = [0.1, 0.85]

        with (
            patch.object(
                client,
                "_query_cloud",
                new_callable=AsyncMock,
                return_value=SearchResult(
                    docs=[
                        QueryResultDocumentInfo(id="c1", text="Cloud doc 1", score=0.9),
                        QueryResultDocumentInfo(id="c2", text="Cloud doc 2", score=0.6),
                    ],
                    query="query",
                    index_name="idx",
                ),
            ) as mock_query_cloud,
            patch.dict(
                "sys.modules",
                {
                    "sentence_transformers": MagicMock(
                        CrossEncoder=MagicMock(return_value=mock_cross_encoder)
                    )
                },
            ),
        ):
            opts = QueryOptions(top_k=1, rerank=True, rerank_top_k=10)
            result = await client.query("idx", "query", options=opts)

            mock_query_cloud.assert_called_once_with("idx", "query", opts, 10)
            assert len(result.docs) == 1
            assert result.docs[0].id == "c2"
            assert result.docs[0].score == pytest.approx(0.85, abs=1e-5)


@pytest.mark.asyncio
async def test_cross_encoder_caching():
    client = MossClient("test", "key")

    doc = QueryResultDocumentInfo(id="1", text="Doc", score=0.5)
    search_result = SearchResult(docs=[doc], query="test", index_name="idx")
    opts = QueryOptions(rerank=True, rerank_model="custom/test-model")

    mock_cross_encoder_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.predict.return_value = [0.9]
    mock_cross_encoder_cls.return_value = mock_instance

    with patch.dict(
        "sys.modules",
        {"sentence_transformers": MagicMock(CrossEncoder=mock_cross_encoder_cls)},
    ):
        await client._rerank_results("test 1", search_result, opts)
        await client._rerank_results("test 2", search_result, opts)

        # CrossEncoder constructor should be called only once due to cache
        mock_cross_encoder_cls.assert_called_once_with("custom/test-model")
        assert mock_instance.predict.call_count == 2
