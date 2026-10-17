"""
E2E tests for Cloud Fallback Query Feature

Tests that query() automatically falls back to cloud API when load_index()
has not been called first.

Note: Cloud fallback only supports standard models (moss-minilm, moss-mediumlm).
Custom embedding indexes must still call load_index() first.

Prerequisites:
- Set MOSS_TEST_PROJECT_ID environment variable
- Set MOSS_TEST_PROJECT_KEY environment variable
- Ensure cloud API is accessible
"""

from __future__ import annotations

import os
import warnings

import pytest
import pytest_asyncio

from moss import DocumentInfo, MossClient, QueryOptions
from tests.constants import (
    TEST_DOCUMENTS,
    TEST_MODEL_ID,
    TEST_PROJECT_ID,
    TEST_PROJECT_KEY,
    generate_unique_index_name,
)


@pytest.fixture(scope="module")
def moss_client():
    """Create a MossClient for the test module."""
    if not os.getenv("MOSS_TEST_PROJECT_ID") or not os.getenv("MOSS_TEST_PROJECT_KEY"):
        warnings.warn(
            "Warning: Using default test credentials. Set MOSS_TEST_PROJECT_ID and "
            "MOSS_TEST_PROJECT_KEY env vars for actual testing."
        )
    return MossClient(TEST_PROJECT_ID, TEST_PROJECT_KEY)


class TestCloudFallbackQuery:
    """Test cloud fallback query operations when index is not loaded locally."""

    @pytest_asyncio.fixture
    async def cloud_fallback_index(self, moss_client):
        """Create an index for cloud fallback tests and clean up after."""
        index_name = generate_unique_index_name("test-cloud-fallback")

        # Create the index with documents
        docs = [DocumentInfo(id=doc["id"], text=doc["text"]) for doc in TEST_DOCUMENTS]
        await moss_client.create_index(index_name, docs, TEST_MODEL_ID)

        yield index_name

        # Cleanup: delete the index
        try:
            await moss_client.delete_index(index_name)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_query_via_cloud_when_index_not_loaded(
        self, moss_client, cloud_fallback_index
    ):
        """Should query via cloud when index is not loaded locally."""
        # Query WITHOUT calling load_index() first - should fall back to cloud API
        results = await moss_client.query(
            cloud_fallback_index,
            "artificial intelligence",
            QueryOptions(top_k=5),
        )

        # Verify response structure
        assert hasattr(results, "docs")
        assert isinstance(results.docs, list)
        assert len(results.docs) > 0
        assert len(results.docs) <= 5

        # Verify each doc has required fields
        for doc in results.docs:
            assert hasattr(doc, "id")
            assert hasattr(doc, "text")
            assert hasattr(doc, "score")
            assert isinstance(doc.id, str)
            assert isinstance(doc.text, str)
            assert isinstance(doc.score, float)
            # Scores should be in range (0, 1]
            assert doc.score > 0
            assert doc.score <= 1

        # Verify scores are in descending order (sorted by relevance)
        for i in range(1, len(results.docs)):
            assert results.docs[i - 1].score >= results.docs[i].score

    @pytest.mark.asyncio
    async def test_respect_topk_parameter_in_cloud_fallback(
        self, moss_client, cloud_fallback_index
    ):
        """Should respect topK parameter in cloud fallback."""
        top_k = 2
        results = await moss_client.query(
            cloud_fallback_index,
            "machine learning",
            QueryOptions(top_k=top_k),
        )

        assert len(results.docs) <= top_k

    @pytest.mark.asyncio
    async def test_results_consistent_with_local_query_after_loading(
        self, moss_client, cloud_fallback_index
    ):
        """Should return results consistent with local query after loading."""
        # Step 1: Query via cloud (before load_index)
        cloud_results = await moss_client.query(
            cloud_fallback_index,
            "neural networks deep learning",
            QueryOptions(top_k=5),
        )

        # Step 2: Load the index locally
        await moss_client.load_index(cloud_fallback_index)

        # Step 3: Query via local (after load_index)
        local_results = await moss_client.query(
            cloud_fallback_index,
            "neural networks deep learning",
            QueryOptions(top_k=5),
        )

        # Both should return results
        assert len(cloud_results.docs) > 0
        assert len(local_results.docs) > 0

        # Top result (first doc ID) should match
        assert cloud_results.docs[0].id == local_results.docs[0].id

        # Significant overlap in result IDs (at least N-1 overlap)
        cloud_ids = [doc.id for doc in cloud_results.docs]
        local_ids = [doc.id for doc in local_results.docs]
        overlap = [id for id in cloud_ids if id in local_ids]
        min_overlap = min(len(cloud_ids), len(local_ids)) - 1
        assert len(overlap) >= min_overlap
