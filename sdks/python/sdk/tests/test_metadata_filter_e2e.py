"""
E2E tests for metadata filtering against the real cloud API.

Validates that metadata survives the cloud round-trip and that
client-side filtering works correctly on a loaded index.

Lifecycle: createIndex (with metadata docs) → loadIndex → query(filter) → deleteIndex

Prerequisites:
    - Set MOSS_TEST_PROJECT_ID and MOSS_TEST_PROJECT_KEY env vars

Run:
    pytest tests/test_metadata_filter_e2e.py -v
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from moss import DocumentInfo, MossClient, QueryOptions
from tests.constants import (
    TEST_MODEL_ID,
    TEST_PROJECT_ID,
    TEST_PROJECT_KEY,
    generate_unique_index_name,
)

FILTER_DOCS = [
    DocumentInfo(
        id="f1",
        text="Cheap coffee shop in downtown New York with great espresso",
        metadata={
            "city": "NYC",
            "price": "12",
            "category": "food",
            "location": "40.7580,-73.9855",
        },
    ),
    DocumentInfo(
        id="f2",
        text="High-end sushi restaurant in central Tokyo with omakase menu",
        metadata={
            "city": "Tokyo",
            "price": "45",
            "category": "food",
            "location": "35.6762,139.6503",
        },
    ),
    DocumentInfo(
        id="f3",
        text="Weekly tech meetup and hackathon event in New York coworking space",
        metadata={
            "city": "NYC",
            "price": "0",
            "category": "tech",
            "location": "40.6892,-74.0445",
        },
    ),
    DocumentInfo(
        id="f4",
        text="Art museum and cultural exhibition in the heart of Paris",
        metadata={
            "city": "Paris",
            "price": "20",
            "category": "culture",
            "location": "48.8566,2.3522",
        },
    ),
    DocumentInfo(
        id="f5",
        text="Popular street food market in Tokyo with yakitori and ramen stalls",
        metadata={
            "city": "Tokyo",
            "price": "8",
            "category": "food",
            "location": "35.6595,139.7004",
        },
    ),
    DocumentInfo(
        id="f6", text="General document with no metadata attached for edge case testing"
    ),
]


@pytest.fixture(scope="module")
def moss_client():
    return MossClient(TEST_PROJECT_ID, TEST_PROJECT_KEY)


async def query_ids(client, name, filt):
    result = await client.query(
        name, "food and restaurants", QueryOptions(top_k=10, filter=filt)
    )
    return sorted(d.id for d in result.docs)


class TestMetadataFilterE2E:

    @pytest_asyncio.fixture(scope="class")
    async def loaded_index(self, moss_client):
        index_name = generate_unique_index_name("test-filter-e2e")
        await moss_client.create_index(index_name, FILTER_DOCS, TEST_MODEL_ID)
        await moss_client.load_index(index_name)
        yield index_name
        try:
            await moss_client.delete_index(index_name)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_eq(self, moss_client, loaded_index):
        ids = await query_ids(
            moss_client, loaded_index, {"field": "city", "condition": {"$eq": "NYC"}}
        )
        assert ids == ["f1", "f3"]

    @pytest.mark.asyncio
    async def test_ne(self, moss_client, loaded_index):
        ids = await query_ids(
            moss_client, loaded_index, {"field": "city", "condition": {"$ne": "NYC"}}
        )
        assert ids == ["f2", "f4", "f5"]

    @pytest.mark.asyncio
    async def test_gt_numeric(self, moss_client, loaded_index):
        ids = await query_ids(
            moss_client, loaded_index, {"field": "price", "condition": {"$gt": "10"}}
        )
        assert ids == ["f1", "f2", "f4"]

    @pytest.mark.asyncio
    async def test_lt_int_coercion(self, moss_client, loaded_index):
        ids = await query_ids(
            moss_client, loaded_index, {"field": "price", "condition": {"$lt": 15}}
        )
        assert ids == ["f1", "f3", "f5"]

    @pytest.mark.asyncio
    async def test_gte(self, moss_client, loaded_index):
        ids = await query_ids(
            moss_client, loaded_index, {"field": "price", "condition": {"$gte": "20"}}
        )
        assert ids == ["f2", "f4"]

    @pytest.mark.asyncio
    async def test_lte(self, moss_client, loaded_index):
        ids = await query_ids(
            moss_client, loaded_index, {"field": "price", "condition": {"$lte": "8"}}
        )
        assert ids == ["f3", "f5"]

    @pytest.mark.asyncio
    async def test_in(self, moss_client, loaded_index):
        ids = await query_ids(
            moss_client,
            loaded_index,
            {"field": "city", "condition": {"$in": ["NYC", "Paris"]}},
        )
        assert ids == ["f1", "f3", "f4"]

    @pytest.mark.asyncio
    async def test_nin(self, moss_client, loaded_index):
        ids = await query_ids(
            moss_client, loaded_index, {"field": "city", "condition": {"$nin": ["NYC"]}}
        )
        assert ids == ["f2", "f4", "f5"]

    @pytest.mark.asyncio
    async def test_and(self, moss_client, loaded_index):
        filt = {
            "$and": [
                {"field": "city", "condition": {"$eq": "NYC"}},
                {"field": "category", "condition": {"$eq": "food"}},
            ]
        }
        ids = await query_ids(moss_client, loaded_index, filt)
        assert ids == ["f1"]

    @pytest.mark.asyncio
    async def test_or(self, moss_client, loaded_index):
        filt = {
            "$or": [
                {"field": "city", "condition": {"$eq": "Paris"}},
                {"field": "category", "condition": {"$eq": "tech"}},
            ]
        }
        ids = await query_ids(moss_client, loaded_index, filt)
        assert ids == ["f3", "f4"]

    @pytest.mark.asyncio
    async def test_nested_and_or(self, moss_client, loaded_index):
        filt = {
            "$and": [
                {
                    "$or": [
                        {"field": "city", "condition": {"$eq": "NYC"}},
                        {"field": "city", "condition": {"$eq": "Tokyo"}},
                    ]
                },
                {"field": "category", "condition": {"$eq": "food"}},
            ]
        }
        ids = await query_ids(moss_client, loaded_index, filt)
        assert ids == ["f1", "f2", "f5"]

    @pytest.mark.asyncio
    async def test_no_matches(self, moss_client, loaded_index):
        ids = await query_ids(
            moss_client, loaded_index, {"field": "city", "condition": {"$eq": "Berlin"}}
        )
        assert ids == []

    @pytest.mark.asyncio
    async def test_skips_docs_without_metadata(self, moss_client, loaded_index):
        ids = await query_ids(
            moss_client,
            loaded_index,
            {"field": "city", "condition": {"$ne": "nonexistent"}},
        )
        assert "f6" not in ids

    @pytest.mark.asyncio
    async def test_no_filter_returns_all(self, moss_client, loaded_index):
        result = await moss_client.query(
            loaded_index, "food and restaurants", QueryOptions(top_k=10)
        )
        assert len(result.docs) == 6

    @pytest.mark.asyncio
    async def test_near_within_range(self, moss_client, loaded_index):
        # 10km around Times Square — f1 (~0km) and f3 (~8.7km, Statue of Liberty area)
        ids = await query_ids(
            moss_client,
            loaded_index,
            {"field": "location", "condition": {"$near": "40.7580,-73.9855,10000"}},
        )
        assert "f1" in ids
        assert "f3" in ids
        assert "f2" not in ids  # Tokyo
        assert "f4" not in ids  # Paris

    @pytest.mark.asyncio
    async def test_near_excludes_far(self, moss_client, loaded_index):
        # 5km around Times Square — only f1 (~0km), not f3 (~8.7km)
        ids = await query_ids(
            moss_client,
            loaded_index,
            {"field": "location", "condition": {"$near": "40.7580,-73.9855,5000"}},
        )
        assert "f1" in ids
        assert "f3" not in ids

    @pytest.mark.asyncio
    async def test_near_skips_docs_without_location(self, moss_client, loaded_index):
        # f6 has no metadata at all — should not appear
        ids = await query_ids(
            moss_client,
            loaded_index,
            {"field": "location", "condition": {"$near": "40.7580,-73.9855,10000000"}},
        )
        assert "f6" not in ids
