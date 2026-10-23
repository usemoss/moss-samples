"""Copy chunks into a Moss index."""

from __future__ import annotations

from collections.abc import Iterable

from moss import (
    DocumentInfo,
    GetDocumentsOptions,
    MossClient,
    MutationOptions,
    MutationResult,
)

from .chunk import MAX_CHUNK_INDEX, chunk_id

#: How many candidate IDs to look up at once when hunting for a source's leftover
#: chunks. One round trip covers a document that shrank by up to this many chunks,
#: which is nearly all of them.
_PROBE_WINDOW = 256


async def ingest(
    documents: Iterable[DocumentInfo],
    project_id: str,
    project_key: str,
    index_name: str,
    model_id: str | None = None,
) -> MutationResult | None:
    """Create a Moss index holding exactly these chunks.

    This is the create path only: it builds a fresh index every time, so it is
    not what you reach for to refresh one document inside an existing one — use
    `refresh_source` for that.

    Deliberately without the connector template's `auto_id` option: random UUIDs
    would make every chunk look new on the way back in, where the contract's
    stable IDs let an unchanged document reproduce exactly the IDs it had.
    """
    docs = list(documents)
    if not docs:
        return None
    client = MossClient(project_id, project_key)
    return await client.create_index(index_name, docs, model_id=model_id)


async def refresh_source(
    client: MossClient,
    index_name: str,
    source: str,
    documents: Iterable[DocumentInfo],
) -> MutationResult | None:
    """Replace everything `index_name` holds for `source` with `documents`.

    Stable IDs make re-chunking an unchanged document a no-op and a rewritten one
    an overwrite — but only for the chunks that still exist. `add_docs` upserts,
    it does not reconcile: if `notes.md` used to cut into 21 chunks and now cuts
    into 6, `#chunk-0006` through `#chunk-0020` stay in the index, still
    searchable, holding text that is no longer in the document. Nothing errors,
    and the stale hits look exactly like real ones.

    So the tail is deleted before the new chunks go in. What makes finding it
    cheap is the contract itself: `chunk_document` guarantees indices run
    `0, 1, 2, …`, so anything left over sits in a contiguous run above the new
    chunk count, and looking up one window of candidate IDs past the end is
    enough to find it or prove it is not there.

    That contiguity is the one assumption here, so it is also maintained here:
    deletions run highest ID first and each one is waited on, which keeps what
    survives a failure an unbroken run that the next refresh will find. A source
    whose IDs were punched full of holes by something other than this package is
    outside the guarantee — reconciling that would mean scanning the whole
    `MAX_CHUNK_INDEX` space on every refresh, tens of round trips per document,
    to defend against a writer that is not honouring the contract anyway.

    Raises whatever `wait_for_job` raises if a deletion fails, rather than
    returning a result that implies a replacement which did not happen. Returns
    the add's `MutationResult`, which the caller can wait on in turn — or `None`
    when there was nothing to add.

    `documents` must be `source`'s entire cut, in order — `chunk_document`'s
    output for that source and nothing else. A mismatched ID raises before
    anything is deleted, since the whole reconciliation is arithmetic on
    `len(documents)` and the wrong list would delete live chunks.

    **Not atomic, and one source at a time.** Two refreshes of the same source
    running concurrently can interleave — a short cut deletes the tail, a long
    cut adds it back, and the short cut's add lands last, leaving chunks from a
    document that no longer exists. Serialize refreshes per source; the index is
    the shared resource and nothing client-side can make probe/delete/add one
    operation. What the ordering above does guarantee is that the wreckage is
    ordinary stale tail, contiguous above the surviving cut, so the next refresh
    of that source clears it.

    Passing no documents deletes every chunk for `source`, which is how a deleted
    file is removed from the index.

    `upsert` is set explicitly rather than left to the server's default, since
    replacing a chunk in place is the entire premise of the ID contract.
    """
    docs = list(documents)

    # Everything below reads `len(docs)` as "the first index this source no
    # longer uses", which is only true if these documents really are this
    # source's whole cut. Handed another source's documents, or a filtered slice
    # of this one's, that arithmetic would delete live chunks and then add
    # documents that do not belong to `source` — a destructive way to discover a
    # mistaken argument. `chunk_document` output passes this by construction.
    for position, doc in enumerate(docs):
        expected = chunk_id(source, position)
        if doc.id != expected:
            raise ValueError(
                f"documents[{position}] has id {doc.id!r}, expected {expected!r}: "
                f"refresh_source replaces everything under {source!r}, so it needs "
                "that source's chunks, all of them, in cut order"
            )

    stale: list[str] = []
    start = len(docs)
    while start <= MAX_CHUNK_INDEX:
        window = [
            chunk_id(source, index)
            for index in range(start, min(start + _PROBE_WINDOW, MAX_CHUNK_INDEX + 1))
        ]
        found = await client.get_docs(index_name, GetDocumentsOptions(doc_ids=window))
        if not found:
            break
        stale.extend(doc.id for doc in found)
        start += len(window)

    # `get_docs` does not promise an order, and the deletion below depends on
    # one. Sorting the IDs is sorting by index, which is what the zero-padding
    # in `chunk_id` is for.
    stale.sort()

    # Batched, because the stale run can be thousands of IDs long and one
    # request carrying all of them is one request that can fail all of them.
    #
    # Highest IDs first, which is what makes a failed batch recoverable. The
    # survivors of a partial delete are then still one unbroken run from
    # `len(docs)` upward — the shape the probe above relies on — so the next
    # refresh finds them and finishes the job. Deleting lowest-first would punch
    # a hole underneath them instead: the next probe would read the emptied low
    # window as proof that nothing was left and stop, stranding every ID above
    # it in the index, searchable, with no run that will ever reach them.
    for end in range(len(stale), 0, -_PROBE_WINDOW):
        batch = stale[max(end - _PROBE_WINDOW, 0) : end]
        deletion = await client.delete_docs(index_name, batch)
        # `delete_docs` returns when the job is accepted, not when it has run,
        # so an unwaited deletion that fails afterwards is invisible: this
        # function would return successfully with the stale chunks still
        # searchable. The add below is handed back to the caller, who can wait
        # on it; nobody outside this function ever sees these job IDs.
        await client.wait_for_job(deletion.job_id)

    if not docs:
        return None
    return await client.add_docs(index_name, docs, MutationOptions(upsert=True))
