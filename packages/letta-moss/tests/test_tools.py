"""Unit tests for the plain-function custom tools."""

import asyncio
import dataclasses

import pytest


class FakeMemory:
    instances = []

    def __init__(self, *, index_name):
        self.index_name = index_name
        self.load_index_calls = 0
        self.insert_calls = []
        self.search_calls = []
        self.delete_calls = []
        FakeMemory.instances.append(self)

    async def load_index(self):
        # Yield control so concurrent _get_memory() callers can interleave,
        # exercising the lock guarding construction.
        await asyncio.sleep(0)
        self.load_index_calls += 1

    async def insert_memory(self, content, *, tags=None):
        self.insert_calls.append((content, tags))
        return "generated-id"

    async def search_memory(self, query, *, top_k=5, tags=None):
        self.search_calls.append((query, top_k, tags))
        from letta_moss.memory import ArchivalMemoryItem

        return [ArchivalMemoryItem(id="1", content="hit", tags=[], metadata={}, score=0.9)]

    async def delete_memory(self, memory_id):
        self.delete_calls.append(memory_id)


@pytest.fixture(autouse=True)
def _reset_singleton(monkeypatch):
    import letta_moss.tools as tools_mod

    FakeMemory.instances = []
    monkeypatch.setattr(tools_mod, "MossLettaMemory", FakeMemory)
    monkeypatch.setattr(tools_mod, "_memory", None)
    monkeypatch.setattr(tools_mod, "_memory_key", None)
    monkeypatch.setenv("MOSS_INDEX_NAME", "idx")
    yield
    monkeypatch.setattr(tools_mod, "_memory", None)
    monkeypatch.setattr(tools_mod, "_memory_key", None)


class TestLazySingleton:
    async def test_get_memory_constructs_once(self):
        from letta_moss.tools import _get_memory

        first = await _get_memory()
        second = await _get_memory()
        assert first is second
        assert len(FakeMemory.instances) == 1
        assert first.load_index_calls == 1
        assert first.index_name == "idx"

    async def test_concurrent_calls_construct_only_one_instance(self):
        from letta_moss.tools import _get_memory

        results = await asyncio.gather(*(_get_memory() for _ in range(10)))
        assert len(FakeMemory.instances) == 1
        assert all(r is results[0] for r in results)

    async def test_rebuilds_when_index_name_env_var_changes(self, monkeypatch):
        from letta_moss.tools import _get_memory

        first = await _get_memory()
        monkeypatch.setenv("MOSS_INDEX_NAME", "other-idx")
        second = await _get_memory()

        assert first is not second
        assert len(FakeMemory.instances) == 2
        assert second.index_name == "other-idx"

    async def test_rebuilds_when_project_credentials_env_vars_change(self, monkeypatch):
        from letta_moss.tools import _get_memory

        first = await _get_memory()
        monkeypatch.setenv("MOSS_PROJECT_ID", "new-project")
        second = await _get_memory()

        assert first is not second
        assert len(FakeMemory.instances) == 2


class TestMossMemoryInsert:
    async def test_delegates_to_memory(self):
        from letta_moss.tools import moss_memory_insert

        result = await moss_memory_insert("hello", tags=["a"])
        assert result == "generated-id"
        [memory] = FakeMemory.instances
        assert memory.insert_calls == [("hello", ["a"])]


class TestMossMemorySearch:
    async def test_returns_list_of_dicts(self):
        from letta_moss.memory import ArchivalMemoryItem
        from letta_moss.tools import moss_memory_search

        results = await moss_memory_search("query", top_k=2)
        [memory] = FakeMemory.instances
        assert memory.search_calls == [("query", 2, None)]
        expected_item = ArchivalMemoryItem(id="1", content="hit", tags=[], metadata={}, score=0.9)
        assert results == [dataclasses.asdict(expected_item)]


class TestMossMemoryDelete:
    async def test_delegates_to_memory(self):
        from letta_moss.tools import moss_memory_delete

        await moss_memory_delete("mem-1")
        [memory] = FakeMemory.instances
        assert memory.delete_calls == ["mem-1"]
