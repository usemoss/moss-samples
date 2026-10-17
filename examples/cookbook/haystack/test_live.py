import asyncio
import os

import pytest
from dotenv import load_dotenv
from haystack import Document
from haystack.document_stores.types import DuplicatePolicy
from moss import MossClient
from moss_haystack import MossDocumentStore, MossRetriever

load_dotenv()

PROJECT_ID = os.getenv("MOSS_PROJECT_ID")
PROJECT_KEY = os.getenv("MOSS_PROJECT_KEY")
TEST_INDEX = "haystack-live-test"

skip_no_creds = pytest.mark.skipif(
    not PROJECT_ID or not PROJECT_KEY,
    reason="MOSS_PROJECT_ID and MOSS_PROJECT_KEY must be set",
)


@skip_no_creds
class TestHaystackLive:
    """Live integration tests against the Moss platform."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Create client, store, and clean up index after tests."""
        self.client = MossClient(PROJECT_ID, PROJECT_KEY)
        self.store = MossDocumentStore(
            project_id=PROJECT_ID, project_key=PROJECT_KEY, index_name=TEST_INDEX
        )
        self.docs = [
            Document(id="doc-1", content="Moss delivers sub-10ms semantic search."),
            Document(
                id="doc-2",
                content="CrewAI is a multi-agent orchestration framework.",
            ),
            Document(id="doc-3", content="Python is a popular programming language."),
            Document(
                id="doc-4",
                content="Vector databases store embeddings for similarity search.",
            ),
            Document(
                id="doc-5",
                content="Hybrid search combines semantic and keyword matching.",
            ),
        ]
        yield
        # Cleanup: delete the test index
        try:
            asyncio.run(self.client.delete_index(TEST_INDEX))
        except Exception:
            pass

    def test_write_documents_creates_index(self):
        count = self.store.write_documents(self.docs, policy=DuplicatePolicy.OVERWRITE)
        assert count == 5

    def test_count_documents(self):
        self.store.write_documents(self.docs, policy=DuplicatePolicy.OVERWRITE)
        count = self.store.count_documents()
        assert count == 5

    def test_write_documents_upsert(self):
        self.store.write_documents(self.docs, policy=DuplicatePolicy.OVERWRITE)
        extra = [Document(id="doc-6", content="Reranking improves search quality.")]
        count = self.store.write_documents(extra, policy=DuplicatePolicy.OVERWRITE)
        assert count == 1

    def test_filter_documents_returns_all_when_no_filters(self):
        self.store.write_documents(self.docs, policy=DuplicatePolicy.OVERWRITE)
        all_docs = self.store.filter_documents()
        assert len(all_docs) == len(self.docs)
        ids = {d.id for d in all_docs}
        assert ids == {d.id for d in self.docs}

    def test_retriever_run(self):
        self.store.write_documents(self.docs, policy=DuplicatePolicy.OVERWRITE)
        self.store.load_index()
        retriever = MossRetriever(document_store=self.store, top_k=3)
        result = retriever.run(query="semantic search latency")
        assert len(result["documents"]) > 0
        assert result["documents"][0].score > 0

    def test_delete_documents(self):
        self.store.write_documents(self.docs, policy=DuplicatePolicy.OVERWRITE)
        self.store.delete_documents(["doc-5"])
        count = self.store.count_documents()
        assert count == 4

    def test_delete_index(self):
        self.store.write_documents(self.docs, policy=DuplicatePolicy.OVERWRITE)
        asyncio.run(self.client.delete_index(TEST_INDEX))
        indexes = asyncio.run(self.client.list_indexes())
        names = [idx.name for idx in indexes]
        assert TEST_INDEX not in names
