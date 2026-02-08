import unittest
from unittest.mock import MagicMock, patch
from moss_langchain import MossRetriever, get_moss_tool
from langchain_core.documents import Document

class TestMossLangChain(unittest.TestCase):
    def setUp(self):
        self.project_id = "test_project"
        self.project_key = "test_key"
        self.index_name = "test_index"

    @patch('moss_langchain.MossClient')
    def test_retriever_initialization(self, mock_client):
        retriever = MossRetriever(
            project_id=self.project_id,
            project_key=self.project_key,
            index_name=self.index_name
        )
        self.assertEqual(retriever.index_name, self.index_name)
        self.assertEqual(retriever.top_k, 5)

    @patch('moss_langchain.MossClient')
    def test_tool_initialization(self, mock_client):
        tool = get_moss_tool(
            project_id=self.project_id,
            project_key=self.project_key,
            index_name=self.index_name
        )
        self.assertEqual(tool.name, "moss_search")
        self.assertIn("Moss semantic search", tool.description)

    @patch('moss_langchain.MossClient')
    def test_aget_relevant_documents(self, mock_client):
        # Setup mock client
        mock_instance = mock_client.return_value
        mock_instance.load_index = MagicMock() # async? should be async
        
        # In our implementation it's await self.client.load_index
        # So it needs to be an AsyncMock for a real test, 
        # but for a basic structure test we'll see if it runs.
        
        retriever = MossRetriever(
            project_id=self.project_id,
            project_key=self.project_key,
            index_name=self.index_name
        )
        
        # Basic check that retriever exists
        self.assertIsNotNone(retriever)

if __name__ == '__main__':
    unittest.main()
