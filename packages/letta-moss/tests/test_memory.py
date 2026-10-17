"""Unit tests for MossLettaMemory."""

import pytest


class FakeQueryResultDoc:
    def __init__(self, id, text, metadata=None, score=None):
        self.id = id
        self.text = text
        self.metadata = metadata
        self.score = score


class FakeQueryResult:
    def __init__(self, docs):
        self.docs = docs


class FakeClient:
    def __init__(self, *, project_id=None, project_key=None):
        self.project_id = project_id
        self.project_key = project_key
        self.create_index_calls = []
        self.add_docs_calls = []
        self.delete_docs_calls = []
        self.get_docs_calls = []
        self.query_calls = []
        self._get_docs_return = []
        self._query_return = FakeQueryResult(docs=[])
        self._create_index_error = None
        self._load_index_error = None
        self._add_docs_error = None
        self.load_index_calls = []

    async def load_index(self, index_name, auto_refresh=False, polling_interval_in_seconds=600):
        self.load_index_calls.append((index_name, auto_refresh, polling_interval_in_seconds))
        if self._load_index_error is not None:
            raise self._load_index_error

    async def create_index(self, name, docs, model_id=None):
        self.create_index_calls.append((name, docs, model_id))
        if self._create_index_error is not None:
            raise self._create_index_error

    async def add_docs(self, name, docs, options=None):
        self.add_docs_calls.append((name, docs, options))
        if self._add_docs_error is not None:
            raise self._add_docs_error

    async def delete_docs(self, name, doc_ids):
        self.delete_docs_calls.append((name, doc_ids))

    async def get_docs(self, name, options=None):
        self.get_docs_calls.append((name, options))
        return self._get_docs_return

    async def query(self, name, query, *, options=None):
        self.query_calls.append((name, query, options))
        return self._query_return


class TestConstructor:
    def test_uses_explicit_args(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        assert m._client.project_id == "p"
        assert m._client.project_key == "k"
        assert m._index_name == "idx"
        assert m._index_loaded is False

    def test_falls_back_to_env_vars(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        monkeypatch.setenv("MOSS_PROJECT_ID", "env-p")
        monkeypatch.setenv("MOSS_PROJECT_KEY", "env-k")
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(index_name="idx")
        assert m._client.project_id == "env-p"
        assert m._client.project_key == "env-k"

    def test_raises_without_credentials(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        monkeypatch.delenv("MOSS_PROJECT_ID", raising=False)
        monkeypatch.delenv("MOSS_PROJECT_KEY", raising=False)
        from letta_moss.memory import MossLettaMemory

        with pytest.raises(ValueError, match="Moss credentials required"):
            MossLettaMemory(index_name="idx")


class TestLoadIndex:
    async def test_delegates_and_marks_loaded(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        assert m._index_loaded is False
        await m.load_index()
        assert m._index_loaded is True

    async def test_forwards_auto_refresh_settings_to_client(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(
            project_id="p",
            project_key="k",
            index_name="idx",
            auto_refresh=True,
            refresh_interval_seconds=45,
        )
        await m.load_index()
        assert m._client.load_index_calls == [("idx", True, 45)]

    async def test_marks_index_created_on_successful_load(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        assert m._index_created is False
        await m.load_index()
        assert m._index_created is True

    async def test_is_idempotent(self, monkeypatch):
        import letta_moss.memory as memory_mod

        load_calls = []

        class TrackingClient(FakeClient):
            async def load_index(
                self, index_name, auto_refresh=False, polling_interval_in_seconds=600
            ):
                load_calls.append(index_name)

        monkeypatch.setattr(memory_mod, "MossClient", TrackingClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        await m.load_index()
        await m.load_index()
        assert load_calls == ["idx"]

    async def test_swallows_index_not_found(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        m._client._load_index_error = RuntimeError("Failed to load index 'idx': index not found")

        await m.load_index()  # must not raise
        assert m._index_loaded is False

    async def test_clears_stale_index_created_flag_when_index_not_found(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        # Simulate a previous successful load/create having cached "it exists".
        m._index_created = True
        m._client._load_index_error = RuntimeError("index not found")

        await m.load_index()

        assert m._index_created is False

    async def test_reraises_other_errors(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        m._client._load_index_error = RuntimeError("unauthorized")

        with pytest.raises(RuntimeError, match="unauthorized"):
            await m.load_index()

    async def test_mutation_during_load_prevents_stale_loaded_flag(self, monkeypatch):
        """A load in flight during a mutation must not mark a stale snapshot loaded."""
        import asyncio

        import letta_moss.memory as memory_mod

        release_load = asyncio.Event()

        class SlowClient(FakeClient):
            async def load_index(
                self, index_name, auto_refresh=False, polling_interval_in_seconds=600
            ):
                await release_load.wait()
                await super().load_index(index_name, auto_refresh, polling_interval_in_seconds)

        monkeypatch.setattr(memory_mod, "MossClient", SlowClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")

        load_task = asyncio.create_task(m.load_index())
        await asyncio.sleep(0)  # let load_index() capture generation_at_start and block

        await m.insert_memory("mutated while load was in flight")
        assert m._index_loaded is False

        release_load.set()
        await load_task

        # The load that was already in flight must not mark this stale snapshot loaded.
        assert m._index_loaded is False
        assert m._index_created is True


class TestInsertMemory:
    async def test_creates_index_on_first_insert(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        memory_id = await m.insert_memory("hello world", tags=["a", "b"], metadata={"n": 1})

        assert isinstance(memory_id, str) and len(memory_id) > 0
        assert m._client.add_docs_calls == []
        [(name, docs, _model_id)] = m._client.create_index_calls
        assert name == "idx"
        [doc] = docs
        assert doc.id == memory_id
        assert doc.text == "hello world"
        # Non-string metadata values are JSON-encoded with the typed prefix.
        assert doc.metadata["n"] == "__moss_typed__:1"
        assert doc.metadata["tags"] == '__moss_typed__:["a", "b"]'
        assert m._index_created is True

    async def test_falls_through_to_add_docs_if_index_already_exists(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        m._client._create_index_error = RuntimeError("index 'idx' already exists")

        memory_id = await m.insert_memory("hello world")

        assert len(m._client.create_index_calls) == 1
        [(name, docs, options)] = m._client.add_docs_calls
        assert name == "idx"
        assert options.upsert is True
        [doc] = docs
        assert doc.id == memory_id
        assert m._index_created is True

    async def test_recreates_index_if_deleted_externally_before_add_docs(self, monkeypatch):
        """A stale ``_index_created`` should trigger a create_index() retry, not an error.

        Simulates the index having been deleted by another process/user after
        this instance last confirmed it existed: add_docs() fails with "not
        found", which should trigger a one-shot create_index() retry rather
        than propagating the error.
        """
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        m._index_created = True  # process-local cache, now stale
        m._client._add_docs_error = RuntimeError("index 'idx' not found")

        memory_id = await m.insert_memory("hello world")

        assert len(m._client.add_docs_calls) == 1
        [(name, docs, _model_id)] = m._client.create_index_calls
        assert name == "idx"
        [doc] = docs
        assert doc.id == memory_id
        assert m._index_created is True

    async def test_add_docs_invalidates_loaded_index(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        await m.load_index()
        assert m._index_loaded is True

        await m.insert_memory("hello world")

        assert m._index_loaded is False

    async def test_second_insert_skips_create_index(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        await m.insert_memory("first")
        await m.insert_memory("second")

        assert len(m._client.create_index_calls) == 1
        assert len(m._client.add_docs_calls) == 1

    async def test_raises_on_other_create_index_errors(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        m._client._create_index_error = RuntimeError("unauthorized")

        with pytest.raises(RuntimeError, match="unauthorized"):
            await m.insert_memory("hello world")

    async def test_rejects_metadata_with_reserved_tags_key(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        with pytest.raises(ValueError, match="'tags' key"):
            await m.insert_memory("hello", metadata={"tags": "should not be allowed"})


class TestSearchMemory:
    async def test_returns_empty_list_if_index_does_not_exist_yet(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        m._client._load_index_error = RuntimeError("index not found")

        assert await m.search_memory("q") == []
        assert m._client.query_calls == []

    async def test_lazily_loads_index_before_querying(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        assert m._index_loaded is False
        await m.search_memory("q")
        assert m._index_loaded is True

    async def test_delegates_and_decodes_metadata(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx", top_k=3, alpha=0.5)
        await m.load_index()
        m._client._query_return = FakeQueryResult(
            docs=[
                FakeQueryResultDoc(
                    id="1",
                    text="hit",
                    metadata={"tags": '__moss_typed__:["x"]', "note": "plain"},
                    score=0.9,
                )
            ]
        )

        results = await m.search_memory("what is moss")

        [(name, query, options)] = m._client.query_calls
        assert name == "idx"
        assert query == "what is moss"
        # No tags filter requested, so top_k is passed through unscaled.
        assert options.top_k == 3
        assert options.alpha == 0.5

        [item] = results
        assert item.id == "1"
        assert item.content == "hit"
        assert item.tags == ["x"]
        assert item.metadata == {"note": "plain"}
        assert item.score == 0.9

    async def test_tags_post_filter(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        await m.load_index()
        m._client._query_return = FakeQueryResult(
            docs=[
                FakeQueryResultDoc(id="1", text="a", metadata={"tags": '__moss_typed__:["x"]'}),
                FakeQueryResultDoc(id="2", text="b", metadata={"tags": '__moss_typed__:["y"]'}),
            ]
        )

        results = await m.search_memory("q", tags=["y"])
        assert [r.id for r in results] == ["2"]

    async def test_oversamples_top_k_when_tags_given(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        await m.load_index()

        await m.search_memory("q", top_k=5, tags=["y"])

        [(_name, _query, options)] = m._client.query_calls
        assert options.top_k == 5 * memory_mod._TAGS_OVERSAMPLE_FACTOR

    async def test_truncates_to_requested_top_k_after_tag_filter(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        await m.load_index()
        m._client._query_return = FakeQueryResult(
            docs=[
                FakeQueryResultDoc(id=str(i), text="x", metadata={"tags": '__moss_typed__:["y"]'})
                for i in range(10)
            ]
        )

        results = await m.search_memory("q", top_k=2, tags=["y"])
        assert len(results) == 2


class TestDeleteMemory:
    async def test_delegates_to_delete_docs(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        await m.delete_memory("mem-1")
        assert m._client.delete_docs_calls == [("idx", ["mem-1"])]

    async def test_invalidates_loaded_index(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        await m.load_index()
        assert m._index_loaded is True

        await m.delete_memory("mem-1")

        assert m._index_loaded is False


class TestGetMemory:
    async def test_returns_item_when_found(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        m._client._get_docs_return = [FakeQueryResultDoc(id="1", text="hi", metadata=None)]

        item = await m.get_memory("1")
        assert item is not None
        assert item.id == "1"
        [(name, options)] = m._client.get_docs_calls
        assert name == "idx"
        assert options.doc_ids == ["1"]

    async def test_returns_none_when_not_found(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        m._client._get_docs_return = []

        assert await m.get_memory("missing") is None


class TestListMemories:
    async def test_lists_all_docs_with_no_options(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        m._client._get_docs_return = [
            FakeQueryResultDoc(id="1", text="a"),
            FakeQueryResultDoc(id="2", text="b"),
        ]

        items = await m.list_memories()
        assert [i.id for i in items] == ["1", "2"]
        [(name, options)] = m._client.get_docs_calls
        assert name == "idx"
        assert options is None

    async def test_applies_limit(self, monkeypatch):
        import letta_moss.memory as memory_mod

        monkeypatch.setattr(memory_mod, "MossClient", FakeClient)
        from letta_moss.memory import MossLettaMemory

        m = MossLettaMemory(project_id="p", project_key="k", index_name="idx")
        m._client._get_docs_return = [
            FakeQueryResultDoc(id="1", text="a"),
            FakeQueryResultDoc(id="2", text="b"),
        ]

        items = await m.list_memories(limit=1)
        assert [i.id for i in items] == ["1"]


class TestMetadataRoundTrip:
    def test_serialize_then_deserialize_restores_original(self):
        from letta_moss.memory import _deserialize_metadata, _serialize_metadata

        original = {"note": "plain string", "count": 3, "tags": ["a", "b"], "nested": {"x": 1}}
        serialized = _serialize_metadata(original)
        assert all(isinstance(v, str) for v in serialized.values())
        assert _deserialize_metadata(serialized) == original

    def test_handles_none(self):
        from letta_moss.memory import _deserialize_metadata, _serialize_metadata

        assert _serialize_metadata(None) is None
        assert _deserialize_metadata(None) == {}

    def test_escapes_plain_string_colliding_with_sentinel_prefix(self):
        from letta_moss.memory import _deserialize_metadata, _serialize_metadata

        original = {"label": "__moss_typed__:42", "note": '__moss_typed__:"quoted"'}
        serialized = _serialize_metadata(original)
        # The stored value must not be the bare original string, or it would
        # be mistaken for a genuinely-encoded value on read-back.
        assert serialized["label"] != original["label"]
        assert _deserialize_metadata(serialized) == original
