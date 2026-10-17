"""
E2E tests for MossClient with large datasets.

Tests validate the full pipeline (init -> upload -> build -> poll)
at realistic data sizes.

Requires:
    - MOSS_TEST_PROJECT_ID and MOSS_TEST_PROJECT_KEY env vars
    - A running API server (or the production endpoint)

Usage:
    pytest tests/test_e2e.py -v -s -m e2e
"""

from __future__ import annotations

import random
import time
from typing import List

import pytest
from moss_core import DocumentInfo

from moss import GetDocumentsOptions, MossClient

from .constants import (
    TEST_MODEL_ID,
    TEST_PROJECT_ID,
    TEST_PROJECT_KEY,
    generate_unique_index_name,
)

# -- Data generation ---------------------------------------------------

DOC_TOPICS = [
    "Machine learning algorithms and optimization techniques for large-scale data processing",
    "Natural language processing and text classification using transformer architectures",
    "Computer vision and image recognition with convolutional neural networks",
    "Reinforcement learning agents for autonomous decision making in complex environments",
    "Distributed systems and fault-tolerant architectures for cloud computing",
    "Database indexing strategies and query optimization for high-throughput workloads",
    "Cryptographic protocols and secure communication in distributed networks",
    "Real-time stream processing and event-driven architectures at scale",
]


def generate_docs(count: int, seed: int = 42) -> List[DocumentInfo]:
    rng = random.Random(seed)
    docs = []
    for i in range(count):
        topic = rng.choice(DOC_TOPICS)
        docs.append(
            DocumentInfo(
                id=f"doc-{i}",
                text=f"{topic} (variation {i}, seed {rng.randint(0, 100000)})",
            )
        )
    return docs


def generate_docs_with_embeddings(
    count: int,
    dimension: int,
    seed: int = 42,
) -> List[DocumentInfo]:
    rng = random.Random(seed)
    docs = []
    for i in range(count):
        topic = rng.choice(DOC_TOPICS)
        embedding = [rng.gauss(0, 1) for _ in range(dimension)]
        magnitude = sum(x * x for x in embedding) ** 0.5
        if magnitude > 0:
            embedding = [x / magnitude for x in embedding]
        docs.append(
            DocumentInfo(
                id=f"doc-{i}",
                text=f"{topic} (variation {i})",
                embedding=embedding,
            )
        )
    return docs


# -- Fixtures ----------------------------------------------------------


@pytest.fixture
def client():
    return MossClient(TEST_PROJECT_ID, TEST_PROJECT_KEY)


# -- Tests -------------------------------------------------------------


@pytest.mark.e2e
class TestBulkCreateIndex:
    """Test create_index with large doc counts."""

    @pytest.mark.asyncio
    async def test_create_1k_docs(self, client):
        """1K docs — baseline for bulk pipeline correctness."""
        index_name = generate_unique_index_name("e2e-1k")
        docs = generate_docs(1_000)

        try:
            t0 = time.perf_counter()
            result = await client.create_index(index_name, docs, TEST_MODEL_ID)
            elapsed = time.perf_counter() - t0

            assert result.job_id
            assert result.index_name == index_name
            assert result.doc_count == 1_000

            info = await client.get_index(index_name)
            assert info.doc_count == 1_000
            print(f"\n  1K create: {elapsed:.1f}s, job={result.job_id}")
        finally:
            await client.delete_index(index_name)

    @pytest.mark.asyncio
    async def test_create_10k_docs(self, client):
        """10K docs — validates upload + build at moderate scale."""
        index_name = generate_unique_index_name("e2e-10k")
        docs = generate_docs(10_000)

        try:
            t0 = time.perf_counter()
            result = await client.create_index(index_name, docs, TEST_MODEL_ID)
            elapsed = time.perf_counter() - t0

            assert result.job_id
            assert result.doc_count == 10_000

            info = await client.get_index(index_name)
            assert info.doc_count == 10_000
            print(f"\n  10K create: {elapsed:.1f}s, job={result.job_id}")
        finally:
            await client.delete_index(index_name)

    @pytest.mark.asyncio
    async def test_create_10k_custom_embeddings(self, client):
        """10K docs with pre-computed 384-dim embeddings."""
        index_name = generate_unique_index_name("e2e-10k-custom")
        docs = generate_docs_with_embeddings(10_000, dimension=384)

        try:
            t0 = time.perf_counter()
            result = await client.create_index(index_name, docs, "custom")
            elapsed = time.perf_counter() - t0

            assert result.doc_count == 10_000
            print(f"\n  10K custom embeddings create: {elapsed:.1f}s")
        finally:
            await client.delete_index(index_name)

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_create_50k_docs(self, client):
        """50K docs — stress test for upload size + build time."""
        index_name = generate_unique_index_name("e2e-50k")
        docs = generate_docs(50_000)

        try:
            t0 = time.perf_counter()
            result = await client.create_index(index_name, docs, TEST_MODEL_ID)
            elapsed = time.perf_counter() - t0

            assert result.doc_count == 50_000

            info = await client.get_index(index_name)
            assert info.doc_count == 50_000
            print(f"\n  50K create: {elapsed:.1f}s, job={result.job_id}")
        finally:
            await client.delete_index(index_name)


@pytest.mark.e2e
class TestBulkAddDocs:
    """Test add_docs at scale — incremental bulk mutations."""

    @pytest.mark.asyncio
    async def test_add_5k_docs_to_existing_index(self, client):
        index_name = generate_unique_index_name("e2e-add-5k")
        initial_docs = generate_docs(1_000, seed=1)

        try:
            await client.create_index(index_name, initial_docs, TEST_MODEL_ID)

            new_docs = generate_docs(5_000, seed=2)
            # Ensure no ID overlap
            for i, doc in enumerate(new_docs):
                doc.id = f"new-doc-{i}"

            t0 = time.perf_counter()
            result = await client.add_docs(index_name, new_docs)
            elapsed = time.perf_counter() - t0

            assert result.doc_count == 5_000

            info = await client.get_index(index_name)
            assert info.doc_count == 6_000
            print(f"\n  Add 5K to 1K index: {elapsed:.1f}s")
        finally:
            await client.delete_index(index_name)

    @pytest.mark.asyncio
    async def test_add_docs_multiple_batches(self, client):
        """Add docs in 3 sequential batches to verify incremental builds."""
        index_name = generate_unique_index_name("e2e-add-batches")
        batch_size = 2_000

        try:
            initial = generate_docs(batch_size, seed=0)
            await client.create_index(index_name, initial, TEST_MODEL_ID)

            for batch_num in range(1, 3):
                batch = generate_docs(batch_size, seed=batch_num * 1000)
                for i, doc in enumerate(batch):
                    doc.id = f"batch{batch_num}-doc-{i}"

                result = await client.add_docs(index_name, batch)
                assert result.doc_count == batch_size

            info = await client.get_index(index_name)
            assert info.doc_count == batch_size * 3
            print(f"\n  3 batches of {batch_size}: total {info.doc_count} docs")
        finally:
            await client.delete_index(index_name)


@pytest.mark.e2e
class TestBulkDeleteDocs:
    """Test delete_docs at scale."""

    @pytest.mark.asyncio
    async def test_delete_half_of_10k(self, client):
        index_name = generate_unique_index_name("e2e-del-5k")
        docs = generate_docs(10_000)

        try:
            await client.create_index(index_name, docs, TEST_MODEL_ID)

            delete_ids = [f"doc-{i}" for i in range(5_000)]

            t0 = time.perf_counter()
            result = await client.delete_docs(index_name, delete_ids)
            elapsed = time.perf_counter() - t0

            assert result.doc_count == 5_000

            info = await client.get_index(index_name)
            assert info.doc_count == 5_000
            print(f"\n  Delete 5K from 10K: {elapsed:.1f}s")
        finally:
            await client.delete_index(index_name)


@pytest.mark.e2e
class TestJobStatus:
    """Test get_job_status after bulk operations."""

    @pytest.mark.asyncio
    async def test_completed_job_status(self, client):
        index_name = generate_unique_index_name("e2e-status")
        docs = generate_docs(1_000)

        try:
            result = await client.create_index(index_name, docs, TEST_MODEL_ID)

            status = await client.get_job_status(result.job_id)
            assert status.job_id == result.job_id
            assert status.status.value == "completed"
            assert status.progress == 1.0 or status.progress == 100.0
            assert status.error is None
        finally:
            await client.delete_index(index_name)


@pytest.mark.e2e
class TestReadOps:
    """Test read operations against a large index."""

    @pytest.mark.asyncio
    async def test_get_docs_from_large_index(self, client):
        index_name = generate_unique_index_name("e2e-read")
        docs = generate_docs(5_000)

        try:
            await client.create_index(index_name, docs, TEST_MODEL_ID)

            all_docs = await client.get_docs(index_name)
            assert len(all_docs) == 5_000

            specific = await client.get_docs(
                index_name, GetDocumentsOptions(doc_ids=["doc-0", "doc-100", "doc-999"])
            )
            assert len(specific) == 3
            ids = {d.id for d in specific}
            assert ids == {"doc-0", "doc-100", "doc-999"}
        finally:
            await client.delete_index(index_name)

    @pytest.mark.asyncio
    async def test_list_indexes(self, client):
        indexes = await client.list_indexes()
        assert isinstance(indexes, list)
