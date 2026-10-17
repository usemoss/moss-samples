import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.documents import Document
from moss_langchain import MossRetriever, get_moss_tool


class TestMossRetriever(unittest.IsolatedAsyncioTestCase):
    """Behavioral tests for MossRetriever."""

    @patch('moss_langchain.MossClient')
    async def test_aget_relevant_documents_maps_results(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.load_index = AsyncMock()
        mock_client.query = AsyncMock(return_value=MagicMock(
            docs=[
                MagicMock(text="hello world", score=0.9, id="d1"),
                MagicMock(text="foo bar", score=0.7, id="d2"),
            ]
        ))

        retriever = MossRetriever(
            project_id="p", project_key="k", index_name="idx"
        )
        docs = await retriever._aget_relevant_documents("test query")

        self.assertEqual(len(docs), 2)
        self.assertIsInstance(docs[0], Document)
        self.assertEqual(docs[0].page_content, "hello world")
        self.assertEqual(docs[0].metadata, {"score": 0.9, "id": "d1"})
        self.assertEqual(docs[1].page_content, "foo bar")

    @patch('moss_langchain.MossClient')
    async def test_aget_relevant_documents_empty_results(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.load_index = AsyncMock()
        mock_client.query = AsyncMock(return_value=MagicMock(docs=[]))

        retriever = MossRetriever(
            project_id="p", project_key="k", index_name="idx"
        )
        docs = await retriever._aget_relevant_documents("empty query")

        self.assertEqual(docs, [])

    @patch('moss_langchain.MossClient')
    async def test_load_index_called_once(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.load_index = AsyncMock()
        mock_client.query = AsyncMock(return_value=MagicMock(docs=[]))

        retriever = MossRetriever(
            project_id="p", project_key="k", index_name="idx"
        )

        await retriever._aget_relevant_documents("q1")
        await retriever._aget_relevant_documents("q2")

        mock_client.load_index.assert_awaited_once_with("idx")


class TestGetMossTool(unittest.IsolatedAsyncioTestCase):
    """Behavioral tests for get_moss_tool."""

    @patch('moss_langchain.MossClient')
    async def test_coroutine_formats_output(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.load_index = AsyncMock()
        mock_client.query = AsyncMock(return_value=MagicMock(
            docs=[
                MagicMock(text="first result", score=0.9, id="d1"),
                MagicMock(text="second result", score=0.8, id="d2"),
            ]
        ))

        tool = get_moss_tool("p", "k", "idx")
        result = await tool.coroutine("search query")

        self.assertIn("Result 1:\nfirst result", result)
        self.assertIn("Result 2:\nsecond result", result)

    @patch('moss_langchain.MossClient')
    async def test_coroutine_empty_results(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.load_index = AsyncMock()
        mock_client.query = AsyncMock(return_value=MagicMock(docs=[]))

        tool = get_moss_tool("p", "k", "idx")
        result = await tool.coroutine("no results query")

        self.assertEqual(result, "No relevant information found.")


if __name__ == '__main__':
    unittest.main()
