"""Optional post-steps that rewrite a chunk's text after it is cut.

These are retrieval-quality tricks, not splitting tricks, so they live outside
`ChunkingStrategy` and compose with any of them. Keeping them separate is also
what makes them adoptable: pikachu already does the trick below by hand, and it
would keep its own copy if the only way to get it were to switch splitters.
"""

from __future__ import annotations

from collections.abc import Mapping

from moss import DocumentInfo


def prepend_context(doc: DocumentInfo, fields: Mapping[str, str]) -> DocumentInfo:
    """Return `doc` with `fields` written into the top of its text.

    Moss's hybrid search scores BM25 over chunk text, so facts that live only in
    metadata — the filename, the folder it sits in — are invisible to the keyword
    half of the query. Restating them in the text makes them matchable. This is
    pikachu's `enrich_chunk_body`, generalised: it prepends `Filename:` and
    `Path:` so a search for a file by name finds it.

    The ID and metadata are untouched, so an enriched chunk is still addressable
    exactly as the contract says it is.

    Any embedding is dropped. It was computed from the text this function just
    rewrote, so carrying it over would pair a vector with content it does not
    describe — and the mismatch is invisible, quietly skewing the dense half of
    every hybrid query. Dropping it forces a recompute downstream, which is the
    safe direction to fail; the alternative is a rule that enrichment must
    happen before embedding, which nothing can enforce.

    `payload` is carried through where the installed SDK has it. Unlike the
    embedding it has nothing to do with the text, so rebuilding the document
    without it would be silent data loss rather than a decision. It is passed
    conditionally because `moss`'s runtime `DocumentInfo` accepts it while the
    shipped `__init__.pyi` stub does not yet declare it — this keeps the package
    correct against both, and degrades to dropping it only on a build that has
    no such field to lose.
    """
    if not fields:
        return doc
    header = "\n".join(f"{key}: {value}" for key, value in fields.items())
    carried = {"payload": doc.payload} if hasattr(doc, "payload") else {}
    return DocumentInfo(
        id=doc.id,
        text=f"{header}\n\n{doc.text}",
        metadata=doc.metadata,
        embedding=None,
        **carried,
    )


def prepend_source_context(doc: DocumentInfo, filename: str, path: str) -> DocumentInfo:
    """`prepend_context` with pikachu's exact field set, for file-backed chunks."""
    return prepend_context(doc, {"Filename": filename, "Path": path})
