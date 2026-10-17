"""Tests for data types used in MossClient operations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestQueryOptionsUsage:
    """Tests for QueryOptions usage patterns in the client."""

    @pytest.mark.asyncio
    async def test_query_with_filter_option(self, client):
        mock_result = MagicMock()
        client._manager.query_text = MagicMock(return_value=mock_result)

        opts = MagicMock()
        opts.top_k = 5
        opts.alpha = 0.8
        opts.embedding = None
        opts.filter = {"field": "city", "condition": {"$eq": "NYC"}}

        await client.query("idx", "test", opts)

        client._manager.query_text.assert_called_once_with(
            "idx", "test", 5, 0.8, opts.filter
        )

    @pytest.mark.asyncio
    async def test_query_with_custom_embedding_option(self, client):
        mock_result = MagicMock()
        client._manager.query = MagicMock(return_value=mock_result)

        embedding = [0.1, 0.2, 0.3]
        opts = MagicMock()
        opts.top_k = 10
        opts.alpha = 0.5
        opts.embedding = embedding
        opts.filter = None

        await client.query("idx", "test", opts)

        call_args = client._manager.query.call_args
        assert call_args[0][0] == "idx"
        assert call_args[0][1] == "test"
        assert list(call_args[0][2]) == pytest.approx([0.1, 0.2, 0.3], abs=1e-6)
        assert call_args[0][3] == 10
        assert call_args[0][4] == 0.5


class TestGetDocumentsOptionsUsage:
    """Tests for GetDocumentsOptions usage patterns."""

    @pytest.mark.asyncio
    async def test_get_docs_with_doc_ids(self):
        with (
            patch("moss.client.moss_client.ManageClient") as mock_manage,
            patch("moss.client.moss_client.IndexManager") as _,
        ):
            from moss import GetDocumentsOptions, MossClient

            mock_manage_instance = mock_manage.return_value
            mock_manage_instance.get_docs = MagicMock(return_value=[])

            client = MossClient("test-project", "test-key")
            client._manage = mock_manage_instance

            opts = GetDocumentsOptions(doc_ids=["doc-1", "doc-2", "doc-3"])
            await client.get_docs("idx", opts)

            mock_manage_instance.get_docs.assert_called_once_with("idx", opts)


class TestMutationOptionsUsage:
    """Tests for MutationOptions usage patterns."""

    @pytest.mark.asyncio
    async def test_add_docs_with_upsert_option(self):
        with (
            patch("moss.client.moss_client.ManageClient") as mock_manage,
            patch("moss.client.moss_client.IndexManager") as _,
        ):
            from moss import MossClient, MutationOptions

            mock_manage_instance = mock_manage.return_value
            mock_result = MagicMock()
            mock_manage_instance.add_docs = MagicMock(return_value=mock_result)

            client = MossClient("test-project", "test-key")
            client._manage = mock_manage_instance

            opts = MutationOptions(upsert=True)
            docs = [MagicMock()]
            await client.add_docs("idx", docs, options=opts)

            mock_manage_instance.add_docs.assert_called_once_with("idx", docs, opts)

    @pytest.mark.asyncio
    async def test_add_docs_without_options(self):
        with (
            patch("moss.client.moss_client.ManageClient") as mock_manage,
            patch("moss.client.moss_client.IndexManager") as _,
        ):
            from moss import MossClient

            mock_manage_instance = mock_manage.return_value
            mock_result = MagicMock()
            mock_manage_instance.add_docs = MagicMock(return_value=mock_result)

            client = MossClient("test-project", "test-key")
            client._manage = mock_manage_instance

            docs = [MagicMock()]
            await client.add_docs("idx", docs)

            mock_manage_instance.add_docs.assert_called_once_with("idx", docs, None)


class TestDocumentInfoUsage:
    """Tests for DocumentInfo usage in client operations."""

    @pytest.mark.asyncio
    async def test_create_index_with_document_info(self):
        with (
            patch("moss.client.moss_client.ManageClient") as mock_manage,
            patch("moss.client.moss_client.IndexManager") as _,
        ):
            from moss import DocumentInfo, MossClient

            mock_manage_instance = mock_manage.return_value
            mock_result = MagicMock()
            mock_result.job_id = "j1"
            mock_result.index_name = "idx"
            mock_result.doc_count = 3
            mock_manage_instance.create_index = MagicMock(return_value=mock_result)

            client = MossClient("test-project", "test-key")
            client._manage = mock_manage_instance

            docs = [
                DocumentInfo(id="1", text="First document"),
                DocumentInfo(id="2", text="Second document"),
                DocumentInfo(id="3", text="Third document"),
            ]
            result = await client.create_index("idx", docs)

            assert result.job_id == "j1"
            mock_manage_instance.create_index.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_index_with_metadata(self):
        with (
            patch("moss.client.moss_client.ManageClient") as mock_manage,
            patch("moss.client.moss_client.IndexManager") as _,
        ):
            from moss import DocumentInfo, MossClient

            mock_manage_instance = mock_manage.return_value
            mock_result = MagicMock()
            mock_manage_instance.create_index = MagicMock(return_value=mock_result)

            client = MossClient("test-project", "test-key")
            client._manage = mock_manage_instance

            docs = [
                DocumentInfo(
                    id="1",
                    text="Document with metadata",
                    metadata={"category": "tech"},
                ),
                DocumentInfo(
                    id="2",
                    text="Another document",
                    metadata={"category": "science"},
                ),
            ]
            await client.create_index("idx", docs)

            call_args = mock_manage_instance.create_index.call_args
            passed_docs = call_args[0][1]
            assert len(passed_docs) == 2
            assert passed_docs[0].metadata == {"category": "tech"}

    @pytest.mark.asyncio
    async def test_create_index_with_embeddings(self):
        with (
            patch("moss.client.moss_client.ManageClient") as mock_manage,
            patch("moss.client.moss_client.IndexManager") as _,
        ):
            from moss import DocumentInfo, MossClient

            mock_manage_instance = mock_manage.return_value
            mock_result = MagicMock()
            mock_manage_instance.create_index = MagicMock(return_value=mock_result)

            client = MossClient("test-project", "test-key")
            client._manage = mock_manage_instance

            embedding = [0.1] * 384
            docs = [
                DocumentInfo(id="1", text="Doc with embedding", embedding=embedding),
            ]
            await client.create_index("idx", docs)

            call_args = mock_manage_instance.create_index.call_args
            assert call_args[0][2] == "custom"


class TestSearchResultUsage:
    """Tests for SearchResult handling."""

    def test_search_result_structure(self):
        from moss import QueryResultDocumentInfo, SearchResult

        doc1 = QueryResultDocumentInfo(id="d1", text="First", score=0.95)
        doc2 = QueryResultDocumentInfo(id="d2", text="Second", score=0.85)

        result = SearchResult(
            docs=[doc1, doc2],
            query="test query",
            index_name="test-index",
            time_taken_ms=5,
        )

        assert len(result.docs) == 2
        assert result.docs[0].id == "d1"
        assert result.docs[0].score == pytest.approx(0.95, abs=1e-6)
        assert result.docs[1].id == "d2"
        assert result.query == "test query"
        assert result.index_name == "test-index"
        assert result.time_taken_ms == 5

    def test_search_result_empty_docs(self):
        from moss import SearchResult

        result = SearchResult(docs=[], query="empty", index_name="idx")

        assert len(result.docs) == 0
        assert result.query == "empty"


class TestIndexInfoUsage:
    """Tests for IndexInfo handling."""

    @pytest.mark.asyncio
    async def test_get_index_returns_info(self):
        with (
            patch("moss.client.moss_client.ManageClient") as mock_manage,
            patch("moss.client.moss_client.IndexManager") as _,
        ):
            from moss import MossClient

            mock_manage_instance = mock_manage.return_value
            mock_info = MagicMock()
            mock_info.name = "my-index"
            mock_info.doc_count = 1000
            mock_manage_instance.get_index = MagicMock(return_value=mock_info)

            client = MossClient("test-project", "test-key")
            client._manage = mock_manage_instance

            result = await client.get_index("my-index")

            assert result.name == "my-index"
            assert result.doc_count == 1000
            mock_manage_instance.get_index.assert_called_once_with("my-index")


class TestJobStatusResponseUsage:
    """Tests for JobStatusResponse handling."""

    @pytest.mark.asyncio
    async def test_get_job_status_returns_response(self):
        with (
            patch("moss.client.moss_client.ManageClient") as mock_manage,
            patch("moss.client.moss_client.IndexManager") as _,
        ):
            from moss import MossClient

            mock_manage_instance = mock_manage.return_value
            mock_status = MagicMock()
            mock_status.job_id = "job-123"
            mock_manage_instance.get_job_status = MagicMock(return_value=mock_status)

            client = MossClient("test-project", "test-key")
            client._manage = mock_manage_instance

            result = await client.get_job_status("job-123")

            assert result.job_id == "job-123"
            mock_manage_instance.get_job_status.assert_called_once_with("job-123")
