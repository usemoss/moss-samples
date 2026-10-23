"""Contract tests: IDs, validation, and the `DocumentInfo` rendering."""

from __future__ import annotations

import copy
import dataclasses
import pickle

import pytest
from moss_chunking import MAX_CHUNK_INDEX, Chunk, chunk_id


def test_chunk_id_is_zero_padded_so_it_sorts_in_cut_order():
    ids = [chunk_id("notes.md", i) for i in (0, 1, 9, 10, 100)]
    assert ids[0] == "notes.md#chunk-0000"
    assert ids[3] == "notes.md#chunk-0010"
    assert sorted(ids) == ids


def test_chunk_id_rejects_empty_source():
    with pytest.raises(ValueError, match="non-empty"):
        chunk_id("", 0)


def test_chunk_id_sorts_in_cut_order_across_the_whole_supported_range():
    ids = [chunk_id("notes.md", i) for i in (0, 1, 9, 10, 99, 100, 999, 1000, MAX_CHUNK_INDEX)]
    assert ids == sorted(ids)


def test_chunk_id_rejects_an_index_the_padding_cannot_hold():
    """Past 9999 the width stops being fixed and chunk-10000 sorts before -9999."""
    with pytest.raises(ValueError, match="sorting in cut order|<="):
        chunk_id("notes.md", MAX_CHUNK_INDEX + 1)


def test_chunk_id_rejects_negative_index():
    with pytest.raises(ValueError, match="index"):
        chunk_id("notes.md", -1)


def test_to_document_stringifies_every_metadata_value():
    doc = Chunk("body", 3, "char", 10, 20).to_document("notes.md")
    assert doc.id == "notes.md#chunk-0003"
    assert doc.text == "body"
    assert doc.metadata == {
        "source": "notes.md",
        "chunk_index": "3",
        "locator_type": "char",
        "locator_start": "10",
        "locator_end": "20",
    }
    assert all(isinstance(value, str) for value in doc.metadata.values())


def test_extra_metadata_is_merged():
    chunk = Chunk("body", 0, "page", 4, 4, extra={"page_label": "iv", "words": "12"})
    doc = chunk.to_document("paper.pdf")
    assert doc.metadata["page_label"] == "iv"
    assert doc.metadata["locator_type"] == "page"


def test_non_string_extra_values_are_stringified():
    """`{"page": 3}` is the natural thing to write, so accept and coerce it.

    Moss types metadata as `Dict[str, str]`; an int left in there fails at the
    SDK boundary, which is a worse place to find out than here.
    """
    chunk = Chunk("body", 0, "page", 4, 4, extra={"page": 3, "words": 12, "ok": True})
    metadata = chunk.to_document("paper.pdf").metadata
    assert metadata["page"] == "3"
    assert metadata["words"] == "12"
    assert metadata["ok"] == "True"
    assert all(isinstance(value, str) for value in metadata.values())


def test_non_string_extra_keys_are_rejected():
    """Keys are not coerced the way values are, and must fail in this package.

    `str(1)` and `"1"` are the same metadata key, so coercing would let one
    entry quietly overwrite another; left alone, a non-string key sails past the
    reserved-key check and fails at the SDK boundary instead.
    """
    with pytest.raises(TypeError, match="extra keys must be str"):
        Chunk("body", 0, "char", 0, 4, extra={1: "one"})


def test_extra_may_not_shadow_reserved_keys():
    with pytest.raises(ValueError, match="reserved"):
        Chunk("body", 0, "char", 0, 4, extra={"source": "elsewhere.md"})


def test_reserved_keys_win_at_render_even_if_validation_is_bypassed():
    """Belt and suspenders: the constructor check is not the last defence.

    Nothing should be able to get a reserved key into `extra` — the constructor
    rejects one and stores a copy the caller cannot reach. Forced past both, rendering
    still merges `extra` first so the contract's own keys overwrite it.
    """
    chunk = Chunk("body", 0, "char", 0, 4, extra={"extension": "md"})
    object.__setattr__(chunk, "extra", {"source": "elsewhere.md", "chunk_index": "99"})

    doc = chunk.to_document("notes.md")
    assert doc.metadata["source"] == "notes.md"
    assert doc.metadata["chunk_index"] == "0"


def test_a_key_added_after_construction_is_still_caught_at_render():
    """`extra` stays mutable, so the constructor's verdict has a shelf life.

    Keeping it a plain dict is what makes a chunk picklable and copyable; the
    cost is that validation has to be re-run where the metadata is actually
    built, rather than trusted from construction time.
    """
    chunk = Chunk("body", 0, "char", 0, 4)
    chunk.extra[1] = "one"

    with pytest.raises(TypeError, match="extra keys must be str"):
        chunk.to_document("notes.md")


def test_extra_is_copied_so_the_caller_cannot_mutate_validated_state():
    supplied = {"extension": "md"}
    chunk = Chunk("body", 0, "char", 0, 4, extra=supplied)
    supplied["source"] = "elsewhere.md"
    assert "source" not in chunk.extra
    assert chunk.to_document("notes.md").metadata["source"] == "notes.md"


def test_a_frozen_chunk_is_actually_hashable():
    """`frozen=True` advertises hashability; a dict field would break it."""
    chunk = Chunk("body", 0, "char", 0, 4, extra={"extension": "md"})
    assert hash(chunk) == hash(Chunk("body", 0, "char", 0, 4, extra={"other": "x"}))
    assert len({chunk, Chunk("body", 1, "char", 4, 8)}) == 2


def test_identity_is_text_and_position_not_metadata():
    """`extra` describes a chunk; it does not decide which chunk it is."""
    assert Chunk("b", 0, "char", 0, 1, extra={"a": "1"}) == Chunk("b", 0, "char", 0, 1)
    assert Chunk("b", 0, "char", 0, 1) != Chunk("b", 1, "char", 0, 1)


def test_a_chunk_in_a_set_stays_findable_however_extra_changes():
    """Equality cannot drift out from under a set, by rebinding or mutation."""
    chunk = Chunk("body", 0, "char", 0, 4, extra={"tags": ["a"]})
    members = {chunk}

    chunk.extra["tags"].append("b")  # type: ignore[attr-defined]
    chunk.extra["added"] = "later"
    assert chunk in members


def test_a_chunk_survives_pickle_deepcopy_and_asdict():
    """The obvious dataclass paths must keep working."""
    chunk = Chunk("body", 0, "char", 0, 4, extra={"page": 3})
    assert pickle.loads(pickle.dumps(chunk)) == chunk
    assert copy.deepcopy(chunk) == chunk
    assert dataclasses.asdict(chunk)["extra"] == {"page": 3}


def test_chunk_rejects_an_unsortable_index_at_construction():
    """Rejected where the index is set, not later inside `to_document`."""
    with pytest.raises(ValueError, match="sorting in cut order|<="):
        Chunk("body", MAX_CHUNK_INDEX + 1, "char", 0, 4)
    assert Chunk("body", MAX_CHUNK_INDEX, "char", 0, 4).index == MAX_CHUNK_INDEX


@pytest.mark.parametrize("bad", [1.5, True, False, "0", None])
def test_a_non_integer_index_is_rejected(bad):
    """`bool` subclasses `int`, so True would otherwise format as chunk-0001."""
    with pytest.raises(TypeError, match="index must be an int"):
        chunk_id("notes.md", bad)
    with pytest.raises(TypeError, match="index must be an int"):
        Chunk("body", bad, "char", 0, 4)


def test_chunk_id_rejects_a_non_string_source():
    """`chunk_id(123, 0)` would otherwise emit a non-string `source`."""
    with pytest.raises(TypeError, match="source must be a str"):
        chunk_id(123, 0)  # type: ignore[arg-type]


def test_unknown_locator_type_is_rejected():
    with pytest.raises(ValueError, match="locator_type"):
        Chunk("body", 0, "byte", 0, 4)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [1.5, True, False, "0", None])
@pytest.mark.parametrize("field", ["locator_start", "locator_end"])
def test_a_non_integer_locator_is_rejected(field, bad):
    """A locator is a position, so it gets the same treatment as the index.

    Left alone, `locator_start=1.5` renders as the metadata string `"1.5"` and
    `True` renders as `"True"` — neither distinguishable downstream from an
    offset the splitter meant.
    """
    kwargs = {"locator_start": 0, "locator_end": 4, field: bad}
    with pytest.raises(TypeError, match=f"{field} must be an int"):
        Chunk("body", 0, "char", **kwargs)


def test_backwards_locator_is_rejected():
    with pytest.raises(ValueError, match="locator_end"):
        Chunk("body", 0, "char", 20, 10)


def test_locator_may_be_a_single_point():
    """A page-located chunk starts and ends on the same page."""
    chunk = Chunk("body", 0, "page", 4, 4)
    assert chunk.to_document("paper.pdf").metadata["locator_start"] == "4"
