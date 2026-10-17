from __future__ import annotations

import os
import warnings

import pytest
import pytest_asyncio

from moss import (
    DocumentInfo,
    MossClient,
    QueryOptions,
)
from tests.constants import (
    TEST_DOCUMENTS,
    TEST_MODEL_ID,
    TEST_PROJECT_ID,
    TEST_PROJECT_KEY,
    generate_unique_index_name,
)


@pytest.fixture(scope="module")
def moss_client():
    if not os.getenv("MOSS_TEST_PROJECT_ID") or not os.getenv("MOSS_TEST_PROJECT_KEY"):
        warnings.warn(
            "Warning: Using default test credentials. Set MOSS_TEST_PROJECT_ID and "
            "MOSS_TEST_PROJECT_KEY env vars for actual testing."
        )
    return MossClient(TEST_PROJECT_ID, TEST_PROJECT_KEY)


class TestHotReloadE2E:

    class TestLoadIndexWithAutoRefresh:

        @pytest_asyncio.fixture
        async def test_index(self, moss_client):
            """Create a test index for auto-refresh tests."""
            index_name = generate_unique_index_name("test-auto-refresh")

            docs = [
                DocumentInfo(id=doc["id"], text=doc["text"]) for doc in TEST_DOCUMENTS
            ]
            await moss_client.create_index(index_name, docs, TEST_MODEL_ID)

            yield index_name

            try:
                await moss_client.delete_index(index_name)
            except Exception:
                pass

        @pytest.mark.asyncio
        async def test_load_index_without_auto_refresh_by_default(
            self, moss_client, test_index
        ):
            """Should load index without auto-refresh by default."""
            loaded_name = await moss_client.load_index(test_index)
            assert loaded_name == test_index

        @pytest.mark.asyncio
        async def test_load_index_with_auto_refresh_enabled(
            self, moss_client, test_index
        ):
            """Should load index with auto-refresh enabled."""
            loaded_name = await moss_client.load_index(
                test_index,
                auto_refresh=True,
                polling_interval_in_seconds=600,
            )
            assert loaded_name == test_index

        @pytest.mark.asyncio
        async def test_accept_custom_polling_interval(self, moss_client, test_index):
            """Should accept custom polling interval."""
            # Load with a custom polling interval (5 minutes)
            loaded_name = await moss_client.load_index(
                test_index,
                auto_refresh=True,
                polling_interval_in_seconds=300,
            )
            assert loaded_name == test_index

            # Clean up
            await moss_client.load_index(test_index)

        @pytest.mark.asyncio
        async def test_allow_reloading_already_loaded_index(
            self, moss_client, test_index
        ):
            """Should allow reloading an already loaded index."""
            # First load
            await moss_client.load_index(test_index)

            # Second load should not throw (reloads the index)
            loaded_name = await moss_client.load_index(test_index)
            assert loaded_name == test_index

        @pytest.mark.asyncio
        async def test_stop_auto_refresh_when_reloading_without_option(
            self, moss_client, test_index
        ):
            """Should stop auto-refresh when reloading without the option."""
            # Load with auto-refresh
            await moss_client.load_index(
                test_index,
                auto_refresh=True,
                polling_interval_in_seconds=600,
            )

            # Reload without auto-refresh (stops polling)
            loaded_name = await moss_client.load_index(test_index)
            assert loaded_name == test_index

        @pytest.mark.asyncio
        async def test_replace_auto_refresh_settings_when_reloading(
            self, moss_client, test_index
        ):
            """Should replace auto-refresh settings when reloading with different interval."""
            # Load with 10 minute interval
            await moss_client.load_index(
                test_index,
                auto_refresh=True,
                polling_interval_in_seconds=600,
            )

            # Reload with 5 minute interval (should replace)
            loaded_name = await moss_client.load_index(
                test_index,
                auto_refresh=True,
                polling_interval_in_seconds=300,
            )
            assert loaded_name == test_index

            # Clean up
            await moss_client.load_index(test_index)

        @pytest.mark.asyncio
        async def test_query_after_loading_with_auto_refresh(
            self, moss_client, test_index
        ):
            """Should be able to query after loading with auto-refresh."""
            await moss_client.load_index(
                test_index,
                auto_refresh=True,
                polling_interval_in_seconds=600,
            )

            results = await moss_client.query(
                test_index,
                "machine learning",
                QueryOptions(top_k=3),
            )

            assert hasattr(results, "docs")
            assert isinstance(results.docs, list)
            assert len(results.docs) > 0

            # Clean up by reloading without auto-refresh
            await moss_client.load_index(test_index)

    class TestQueryBehavior:
        """Test query behavior with loaded and unloaded indexes."""

        @pytest_asyncio.fixture
        async def test_index(self, moss_client):
            """Create a test index for query behavior tests."""
            index_name = generate_unique_index_name("test-query-behavior")

            docs = [
                DocumentInfo(id=doc["id"], text=doc["text"]) for doc in TEST_DOCUMENTS
            ]
            await moss_client.create_index(index_name, docs, TEST_MODEL_ID)

            yield index_name

            try:
                await moss_client.delete_index(index_name)
            except Exception:
                pass

        @pytest.mark.asyncio
        async def test_query_cloud_when_index_not_loaded(self, moss_client, test_index):
            """Should query cloud when index is not loaded locally."""
            # Query without loading - should fall back to cloud
            results = await moss_client.query(
                test_index,
                "machine learning",
                QueryOptions(top_k=3),
            )

            assert hasattr(results, "docs")
            assert isinstance(results.docs, list)
            assert len(results.docs) > 0

        @pytest.mark.asyncio
        async def test_query_locally_after_loading_index(self, moss_client, test_index):
            """Should query locally after loading index."""
            # Load index locally
            await moss_client.load_index(test_index)

            # Query should use local index (faster)
            results = await moss_client.query(
                test_index,
                "neural networks",
                QueryOptions(top_k=3),
            )

            assert hasattr(results, "docs")
            assert isinstance(results.docs, list)
            assert len(results.docs) > 0

    class TestMultipleIndexes:
        """Test handling multiple indexes with different settings."""

        @pytest_asyncio.fixture
        async def test_indexes(self, moss_client):
            """Create two test indexes."""
            index_name1 = generate_unique_index_name("test-multi-1")
            index_name2 = generate_unique_index_name("test-multi-2")

            docs = [
                DocumentInfo(id=doc["id"], text=doc["text"]) for doc in TEST_DOCUMENTS
            ]
            await moss_client.create_index(index_name1, docs, TEST_MODEL_ID)
            await moss_client.create_index(index_name2, docs, TEST_MODEL_ID)

            yield index_name1, index_name2

            try:
                await moss_client.delete_index(index_name1)
            except Exception:
                pass
            try:
                await moss_client.delete_index(index_name2)
            except Exception:
                pass

        @pytest.mark.asyncio
        async def test_multiple_indexes_with_different_auto_refresh_settings(
            self, moss_client, test_indexes
        ):
            """Should handle multiple indexes with different auto-refresh settings."""
            index_name1, index_name2 = test_indexes

            # Load first index with auto-refresh
            loaded1 = await moss_client.load_index(
                index_name1,
                auto_refresh=True,
                polling_interval_in_seconds=600,
            )
            assert loaded1 == index_name1

            # Load second index without auto-refresh
            loaded2 = await moss_client.load_index(index_name2)
            assert loaded2 == index_name2

            # Both should be queryable
            results1 = await moss_client.query(
                index_name1,
                "machine learning",
                QueryOptions(top_k=2),
            )
            assert len(results1.docs) > 0

            results2 = await moss_client.query(
                index_name2,
                "neural networks",
                QueryOptions(top_k=2),
            )
            assert len(results2.docs) > 0

            # Clean up
            await moss_client.load_index(index_name1)

    class TestErrorHandling:
        """Test error handling for hot reload operations."""

        @pytest.mark.asyncio
        async def test_fail_to_load_non_existent_index(self, moss_client):
            """Should fail to load a non-existent index."""
            non_existent_index_name = "non-existent-index-for-test"

            with pytest.raises(Exception):
                await moss_client.load_index(non_existent_index_name)

        @pytest.mark.asyncio
        async def test_fail_to_query_non_existent_index(self, moss_client):
            """Should fail to query a non-existent index."""
            non_existent_index_name = "non-existent-index-for-test"

            with pytest.raises(Exception):
                await moss_client.query(
                    non_existent_index_name,
                    "test query",
                    QueryOptions(top_k=3),
                )
