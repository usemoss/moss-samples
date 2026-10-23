"""Built-in splitters. One class per strategy, all yielding `Chunk`.

Every splitter here reports `char` locators, because they all cut plain text and
character offsets are what plain text has. A splitter over paginated or line-
oriented content reports `page` or `line` instead — the contract does not care,
so long as the unit is declared.

The shared invariant, which the tests enforce: for a chunk produced from `text`,
`text[chunk.locator_start:chunk.locator_end] == chunk.text`. Offsets point into
the original string, never into a normalized or stripped copy of it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import replace
from typing import Protocol

from moss import DocumentInfo

from .chunk import Chunk

# A sentence ends at .!? — optionally followed by a closing quote or bracket —
# and is separated from the next by whitespace. Each lookbehind branch is a fixed
# width, which is what Python's `re` requires.
_SENTENCE_BOUNDARY = re.compile(r"(?:(?<=[.!?][\"'”’)\]])|(?<=[.!?]))\s+")

# A blank line, plus any whitespace padding around it. CRLF is matched too, or
# every paragraph in a Windows-authored file would run into the next one and
# `ParagraphSplitter` would silently emit a single oversized chunk.
_PARAGRAPH_BOUNDARY = re.compile(r"\r?\n[ \t]*\r?\n\s*")

Span = tuple[int, int]


class ChunkingStrategy(Protocol):
    """Cut `text` into ordered `Chunk`s.

    Implementations own only the cutting. IDs and metadata belong to the
    contract (see `chunk.py`), so a strategy never builds a `DocumentInfo`
    itself — that is precisely the freedom that let pikachu and llamaindex drift
    apart.
    """

    def split(self, text: str) -> Iterable[Chunk]: ...


def _trim(text: str, spans: Iterable[Span]) -> list[Span]:
    """Shrink each span past its surrounding whitespace, dropping blank ones."""
    trimmed: list[Span] = []
    for start, end in spans:
        raw = text[start:end]
        stripped = raw.strip()
        if not stripped:
            continue
        lead = len(raw) - len(raw.lstrip())
        trimmed.append((start + lead, start + lead + len(stripped)))
    return trimmed


def _separator_pattern(separator: str) -> re.Pattern[str]:
    """Boundary regex for `separator` that keeps its non-whitespace part.

    `_split_spans` discards whatever the boundary matches. That is right for
    `"\\n\\n"` or `" "` — whitespace between chunks is not content. It is wrong
    for `". "`, where the period belongs to the sentence it ends and only the
    space separates. So a separator's non-whitespace head goes into a lookbehind
    (fixed width, since it is a literal) and only its trailing whitespace is
    consumed, putting the cut after the punctuation rather than through it.
    """
    kept = separator.rstrip()
    if not kept:
        return re.compile(re.escape(separator))
    return re.compile(f"(?<={re.escape(kept)}){re.escape(separator[len(kept) :])}")


def _split_spans(text: str, boundary: re.Pattern[str]) -> list[Span]:
    """Spans of `text` between matches of `boundary`, whitespace trimmed."""
    spans: list[Span] = []
    pos = 0
    for match in boundary.finditer(text):
        spans.append((pos, match.start()))
        pos = match.end()
    spans.append((pos, len(text)))
    return _trim(text, spans)


def _hard_spans(text: str, max_chars: int) -> list[Span]:
    """Last resort: slice at `max_chars` when no separator gets a piece small."""
    windows = [
        (offset, min(offset + max_chars, len(text))) for offset in range(0, len(text), max_chars)
    ]
    return _trim(text, windows)


class CharSplitter:
    """Fixed-width character windows with a trailing overlap.

    The pikachu strategy: its 1800/300 settings are the defaults here.
    """

    def __init__(self, chunk_chars: int = 1800, overlap: int = 300) -> None:
        if chunk_chars < 1:
            raise ValueError(f"chunk_chars must be >= 1, got {chunk_chars}")
        if overlap < 0:
            raise ValueError(f"overlap must be >= 0, got {overlap}")
        if overlap >= chunk_chars:
            raise ValueError(
                f"overlap ({overlap}) must be < chunk_chars ({chunk_chars}), "
                "otherwise chunking never advances"
            )
        self.chunk_chars = chunk_chars
        self.overlap = overlap

    def split(self, text: str) -> Iterator[Chunk]:
        length = len(text)
        start = 0
        index = 0
        # Windows advance along the raw text, but what gets emitted is the
        # trimmed span inside them. On padded input two consecutive windows can
        # trim down to the same span, so track where the last chunk ended and
        # skip anything that adds no new content — otherwise the same text is
        # indexed twice under two IDs.
        last_end = -1
        while start < length:
            end = min(start + self.chunk_chars, length)
            for piece_start, piece_end in _trim(text, [(start, end)]):
                if piece_end <= last_end:
                    continue
                yield Chunk(
                    text=text[piece_start:piece_end],
                    index=index,
                    locator_type="char",
                    locator_start=piece_start,
                    locator_end=piece_end,
                )
                index += 1
                last_end = piece_end
            if end >= length:
                break
            start = max(end - self.overlap, start + 1)


class SentenceSplitter:
    """Whole sentences accumulated up to a word budget, overlapping by sentence.

    The llamaindex strategy: its 400-word / 2-sentence settings are the defaults.
    Sentence detection is regex-based rather than nltk-backed, so the package
    stays dependency-free apart from `moss` itself.
    """

    def __init__(self, max_words: int = 400, overlap_sentences: int = 2) -> None:
        if max_words < 1:
            raise ValueError(f"max_words must be >= 1, got {max_words}")
        if overlap_sentences < 0:
            raise ValueError(f"overlap_sentences must be >= 0, got {overlap_sentences}")
        self.max_words = max_words
        # Clamped as llamaindex clamps it, to keep the parity this splitter is
        # for. Not a safety net: progress is guaranteed by the `group_start + 1`
        # floor in `split`, which holds for any overlap.
        self.overlap_sentences = min(overlap_sentences, max(1, max_words // 100))

    def split(self, text: str) -> Iterator[Chunk]:
        sentences = _split_spans(text, _SENTENCE_BOUNDARY)
        if not sentences:
            return

        cursor = 0
        index = 0
        while cursor < len(sentences):
            group_start = cursor
            words = 0
            while cursor < len(sentences):
                start, end = sentences[cursor]
                sentence_words = len(text[start:end].split())
                # The first sentence always goes in, even if it blows the budget
                # on its own — otherwise nothing would ever be emitted for it.
                if cursor > group_start and words + sentence_words > self.max_words:
                    break
                words += sentence_words
                cursor += 1

            chunk_start = sentences[group_start][0]
            chunk_end = sentences[cursor - 1][1]
            yield Chunk(
                text=text[chunk_start:chunk_end],
                index=index,
                locator_type="char",
                locator_start=chunk_start,
                locator_end=chunk_end,
            )
            index += 1

            if cursor < len(sentences):
                cursor = max(cursor - self.overlap_sentences, group_start + 1)


class ParagraphSplitter:
    """Whole paragraphs packed up to a character budget.

    Paragraphs are never broken apart: one longer than `max_chars` is emitted on
    its own rather than cut, on the grounds that an author's paragraph break is
    better evidence of a topic boundary than an arbitrary offset. Use
    `RecursiveSplitter` when a hard ceiling matters more than that.
    """

    def __init__(self, max_chars: int = 1800) -> None:
        if max_chars < 1:
            raise ValueError(f"max_chars must be >= 1, got {max_chars}")
        self.max_chars = max_chars

    def split(self, text: str) -> Iterator[Chunk]:
        paragraphs = _split_spans(text, _PARAGRAPH_BOUNDARY)
        index = 0
        group: list[Span] = []
        for span in paragraphs:
            if group and span[1] - group[0][0] > self.max_chars:
                yield self._emit(text, group, index)
                index += 1
                group = []
            group.append(span)
        if group:
            yield self._emit(text, group, index)

    @staticmethod
    def _emit(text: str, group: Sequence[Span], index: int) -> Chunk:
        start, end = group[0][0], group[-1][1]
        return Chunk(
            text=text[start:end],
            index=index,
            locator_type="char",
            locator_start=start,
            locator_end=end,
        )


class RecursiveSplitter:
    """Split on the coarsest separator that fits, then merge back up.

    Tries each separator in turn — paragraphs, then lines, then sentences, then
    words — recursing into any piece still over budget, and finally coalescing
    adjacent pieces so chunks land near `max_chars` rather than far under it.
    Unlike `ParagraphSplitter` this always respects the ceiling, falling back to
    a hard character cut if no separator gets a piece small enough.
    """

    DEFAULT_SEPARATORS: tuple[str, ...] = ("\n\n", "\n", ". ", " ")

    def __init__(
        self,
        max_chars: int = 1800,
        separators: Sequence[str] | None = None,
    ) -> None:
        if max_chars < 1:
            raise ValueError(f"max_chars must be >= 1, got {max_chars}")
        self.max_chars = max_chars
        self.separators = tuple(separators) if separators is not None else self.DEFAULT_SEPARATORS

    def split(self, text: str) -> Iterator[Chunk]:
        spans = self._recurse(text, 0, self.separators)
        for index, (start, end) in enumerate(self._merge(spans)):
            yield Chunk(
                text=text[start:end],
                index=index,
                locator_type="char",
                locator_start=start,
                locator_end=end,
            )

    def _recurse(self, text: str, base: int, separators: Sequence[str]) -> list[Span]:
        if len(text) <= self.max_chars:
            return [(base + start, base + end) for start, end in _trim(text, [(0, len(text))])]
        if not separators:
            hard = _hard_spans(text, self.max_chars)
            return [(base + start, base + end) for start, end in hard]

        head, tail = separators[0], separators[1:]
        pieces = _split_spans(text, _separator_pattern(head))
        if len(pieces) <= 1:
            # This separator bought us nothing; try the next one.
            return self._recurse(text, base, tail)

        spans: list[Span] = []
        for start, end in pieces:
            piece = text[start:end]
            if len(piece) <= self.max_chars:
                spans.append((base + start, base + end))
            else:
                spans.extend(self._recurse(piece, base + start, tail))
        return spans

    def _merge(self, spans: Sequence[Span]) -> list[Span]:
        """Coalesce neighbours while the combined span stays within budget."""
        merged: list[Span] = []
        for span in spans:
            if merged and span[1] - merged[-1][0] <= self.max_chars:
                merged[-1] = (merged[-1][0], span[1])
            else:
                merged.append(span)
        return merged


def chunk_document(
    text: str,
    source: str,
    strategy: ChunkingStrategy,
    extra: Mapping[str, object] | None = None,
) -> list[DocumentInfo]:
    """Run `strategy` over `text` and render the chunks under the contract.

    `extra` is merged into every chunk's metadata — the place for source-level
    facts like `extension` or `modified_at` that the splitter cannot know.

    Where the two collide the chunk's own value wins. `extra` is by definition
    the same for every chunk, so letting it overwrite would mean a document-wide
    constant silently replacing the page or section number that only the
    splitter was in a position to know.

    A strategy that does not number its chunks `0, 1, 2, …` is rejected here.
    The index is what the ID is built from, so a repeat means two chunks render
    the same ID and the second overwrites the first on ingest — silent data
    loss, discovered later as a document with missing content. Renumbering them
    would paper over that just as quietly, and would rewrite the addressing of a
    splitter that meant something by its index, so the mismatch is raised
    instead.
    """
    documents: list[DocumentInfo] = []
    for position, chunk in enumerate(strategy.split(text)):
        if chunk.index != position:
            raise ValueError(
                f"{type(strategy).__name__} yielded chunk.index={chunk.index} at "
                f"position {position}: indices must run 0, 1, 2, … or chunk IDs "
                "collide and stop sorting in cut order"
            )
        if extra:
            chunk = replace(chunk, extra={**extra, **chunk.extra})
        documents.append(chunk.to_document(source))
    return documents
