"""`refresh_source` tests.

Upsert alone cannot reconcile: a document that cuts into fewer chunks than it
used to leaves the old tail behind, still searchable, holding text that is no
longer in the document. These tests are about that tail — that it is found, that
it is deleted before the new chunks land, and that a document which did not
shrink pays one lookup for the privilege and nothing more.

The client is a fake. Everything under test is which calls get made and in what
order, which is exactly what a fake can answer and a live index cannot cheaply.
"""

from __future__ import annotations

import pytest
from moss import DocumentInfo
from moss_chunking import CharSplitter, chunk_document, chunk_id, refresh_source

PROSE = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi"


class FakeResult:
    """`MutationResult` is a native type; only its `job_id` is used here."""

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id


class FakeClient:
    """Enough of `MossClient` for the refresh path, recording what it was asked.

    `fail_delete_after` fails the nth deletion the way the SDK does — after the
    job has been accepted, when it is waited on — which is the case that decides
    whether a half-finished refresh can be recovered by the next one.
    """

    def __init__(
        self,
        existing: list[str] | None = None,
        fail_delete_after: int | None = None,
        shuffled: bool = False,
    ) -> None:
        self.existing = set(existing or [])
        self.calls: list[tuple[str, object]] = []
        self.fail_delete_after = fail_delete_after
        self.shuffled = shuffled
        self.deletions = 0

    async def get_docs(self, name, options=None):
        self.calls.append(("get_docs", list(options.doc_ids)))
        found = [doc_id for doc_id in options.doc_ids if doc_id in self.existing]
        if self.shuffled:
            found.reverse()
        return [DocumentInfo(id=doc_id, text="stale") for doc_id in found]

    async def delete_docs(self, name, doc_ids):
        self.calls.append(("delete_docs", list(doc_ids)))
        self.deletions += 1
        if self.fail_delete_after is not None and self.deletions > self.fail_delete_after:
            # Accepted, but the job will fail; the documents stay put.
            return FakeResult(f"delete-{self.deletions}-doomed")
        self.existing -= set(doc_ids)
        return FakeResult(f"delete-{self.deletions}")

    async def wait_for_job(self, job_id, **kwargs):
        self.calls.append(("wait_for_job", job_id))
        if job_id.endswith("doomed"):
            raise RuntimeError(f"job {job_id} failed")
        return None

    async def add_docs(self, name, docs, options=None):
        self.calls.append(("add_docs", [d.id for d in docs]))
        self.existing |= {d.id for d in docs}
        return "added"


def ids_for(source: str, count: int) -> list[str]:
    return [chunk_id(source, index) for index in range(count)]


def deleted(client: FakeClient) -> list[str]:
    return [doc_id for kind, arg in client.calls if kind == "delete_docs" for doc_id in arg]


async def test_a_shrunken_document_loses_its_stale_tail():
    """The case upsert cannot handle: 21 chunks re-cut into 6."""
    client = FakeClient(existing=ids_for("notes.md", 21))
    docs = [DocumentInfo(id=doc_id, text="fresh") for doc_id in ids_for("notes.md", 6)]

    await refresh_source(client, "idx", "notes.md", docs)

    assert deleted(client) == ids_for("notes.md", 21)[6:]
    assert client.existing == set(ids_for("notes.md", 6))


async def test_the_tail_is_deleted_before_the_new_chunks_land():
    """Ordering matters: an add that fails must not leave the stale tail behind."""
    client = FakeClient(existing=ids_for("notes.md", 9))
    docs = [DocumentInfo(id=doc_id, text="fresh") for doc_id in ids_for("notes.md", 2)]

    await refresh_source(client, "idx", "notes.md", docs)

    kinds = [kind for kind, _ in client.calls]
    assert kinds.index("delete_docs") < kinds.index("add_docs")


async def test_a_document_that_did_not_shrink_deletes_nothing():
    client = FakeClient(existing=ids_for("notes.md", 4))
    docs = [DocumentInfo(id=doc_id, text="fresh") for doc_id in ids_for("notes.md", 4)]

    result = await refresh_source(client, "idx", "notes.md", docs)

    assert result == "added"
    assert [kind for kind, _ in client.calls] == ["get_docs", "add_docs"]


async def test_a_grown_document_costs_a_single_lookup():
    """One probe past the end proves there is no tail; no scan of the index."""
    client = FakeClient(existing=ids_for("notes.md", 2))
    docs = [DocumentInfo(id=doc_id, text="fresh") for doc_id in ids_for("notes.md", 5)]

    await refresh_source(client, "idx", "notes.md", docs)

    assert [kind for kind, _ in client.calls].count("get_docs") == 1


async def test_passing_no_documents_removes_the_source_entirely():
    """How a deleted file leaves the index."""
    client = FakeClient(existing=ids_for("notes.md", 3) + ids_for("other.md", 2))

    result = await refresh_source(client, "idx", "notes.md", [])

    assert result is None
    assert client.existing == set(ids_for("other.md", 2))


async def test_another_sources_chunks_are_never_touched():
    client = FakeClient(existing=ids_for("notes.md", 8) + ids_for("other.md", 8))
    docs = [DocumentInfo(id=doc_id, text="fresh") for doc_id in ids_for("notes.md", 1)]

    await refresh_source(client, "idx", "notes.md", docs)

    assert set(ids_for("other.md", 8)) <= client.existing
    assert not any(doc_id.startswith("other.md") for doc_id in deleted(client))


async def test_a_tail_longer_than_one_probe_window_is_still_cleared():
    """The window is a batch size, not a ceiling: probing continues while it hits."""
    client = FakeClient(existing=ids_for("notes.md", 600))
    docs = [DocumentInfo(id=doc_id, text="fresh") for doc_id in ids_for("notes.md", 1)]

    await refresh_source(client, "idx", "notes.md", docs)

    assert client.existing == set(ids_for("notes.md", 1))
    assert len(deleted(client)) == 599


async def test_documents_from_another_source_are_refused_before_anything_is_deleted():
    """The wrong argument would otherwise be discovered destructively."""
    client = FakeClient(existing=ids_for("notes.md", 5))
    docs = [DocumentInfo(id=doc_id, text="fresh") for doc_id in ids_for("other.md", 2)]

    with pytest.raises(ValueError, match="expected 'notes.md#chunk-0000'"):
        await refresh_source(client, "idx", "notes.md", docs)

    assert client.calls == []
    assert client.existing == set(ids_for("notes.md", 5))


async def test_a_gapped_document_list_is_refused():
    """A filtered list would make `len(docs)` mean the wrong index."""
    client = FakeClient(existing=ids_for("notes.md", 5))
    kept = [chunk_id("notes.md", 0), chunk_id("notes.md", 2)]
    docs = [DocumentInfo(id=doc_id, text="fresh") for doc_id in kept]

    with pytest.raises(ValueError, match=r"documents\[1\]"):
        await refresh_source(client, "idx", "notes.md", docs)

    assert client.calls == []


def test_the_client_surface_this_module_calls_actually_exists():
    """The fake client above cannot catch a method that the real one lacks.

    `wait_for_job` in particular is real on the declared floor (`moss==1.7.2`)
    but missing from both the checked-in stub and the in-tree SDK source, which
    is old enough to predate it — so reading either one suggests this module
    calls something that isn't there. This asserts against the installed SDK,
    which is the surface that decides.
    """
    from moss import MossClient

    missing = [
        name
        for name in ("get_docs", "delete_docs", "add_docs", "wait_for_job")
        if not hasattr(MossClient, name)
    ]
    assert not missing


async def test_the_tail_is_deleted_from_the_top_down():
    """Descending order is what makes a half-finished refresh recoverable."""
    client = FakeClient(existing=ids_for("notes.md", 600))
    docs = [DocumentInfo(id=doc_id, text="fresh") for doc_id in ids_for("notes.md", 1)]

    await refresh_source(client, "idx", "notes.md", docs)

    batches = [arg for kind, arg in client.calls if kind == "delete_docs"]
    assert len(batches) > 1
    assert [batch[0] for batch in batches] == sorted((b[0] for b in batches), reverse=True)


async def test_every_deletion_is_waited_on():
    """`delete_docs` returns when the job is accepted, not when it has run."""
    client = FakeClient(existing=ids_for("notes.md", 600))
    docs = [DocumentInfo(id=doc_id, text="fresh") for doc_id in ids_for("notes.md", 1)]

    await refresh_source(client, "idx", "notes.md", docs)

    kinds = [kind for kind, _ in client.calls]
    for position, kind in enumerate(kinds):
        if kind == "delete_docs":
            assert kinds[position + 1] == "wait_for_job"


async def test_a_failed_deletion_is_raised_rather_than_reported_as_a_refresh():
    """Returning normally here would claim a replacement that did not happen."""
    client = FakeClient(existing=ids_for("notes.md", 9), fail_delete_after=0)
    docs = [DocumentInfo(id=doc_id, text="fresh") for doc_id in ids_for("notes.md", 2)]

    with pytest.raises(RuntimeError, match="failed"):
        await refresh_source(client, "idx", "notes.md", docs)

    assert not any(kind == "add_docs" for kind, _ in client.calls)


async def test_a_refresh_after_a_failed_deletion_finishes_the_job():
    """The regression the delete order exists for.

    600 chunks re-cut to 1, with the deletion failing partway. Whatever survives
    has to stay reachable from a probe that starts at the new chunk count — if
    the surviving run had a hole punched under it, the retry would stop at the
    hole and strand everything above it forever.
    """
    existing = ids_for("notes.md", 600)
    docs = [DocumentInfo(id=doc_id, text="fresh") for doc_id in ids_for("notes.md", 1)]

    failing = FakeClient(existing=existing, fail_delete_after=1)
    with pytest.raises(RuntimeError):
        await refresh_source(failing, "idx", "notes.md", docs)
    assert len(failing.existing) > 1  # the refresh really did leave work behind

    retry = FakeClient(existing=sorted(failing.existing))
    await refresh_source(retry, "idx", "notes.md", docs)

    assert retry.existing == set(ids_for("notes.md", 1))


async def test_unordered_lookup_results_do_not_break_the_delete_order():
    """`get_docs` promises no order; the zero-padded IDs are sorted before use."""
    client = FakeClient(existing=ids_for("notes.md", 600), shuffled=True)
    docs = [DocumentInfo(id=doc_id, text="fresh") for doc_id in ids_for("notes.md", 1)]

    await refresh_source(client, "idx", "notes.md", docs)

    batches = [arg for kind, arg in client.calls if kind == "delete_docs"]
    assert [batch[0] for batch in batches] == sorted((b[0] for b in batches), reverse=True)
    assert client.existing == set(ids_for("notes.md", 1))


@pytest.mark.parametrize("cut", [40, 12])
async def test_refresh_is_idempotent_for_real_chunked_output(cut):
    """Twice through with the same text changes nothing the second time."""
    client = FakeClient()
    docs = chunk_document(PROSE, "notes.md", CharSplitter(chunk_chars=cut, overlap=5))

    await refresh_source(client, "idx", "notes.md", docs)
    after_first = set(client.existing)
    await refresh_source(client, "idx", "notes.md", docs)

    assert client.existing == after_first
    assert not deleted(client)
