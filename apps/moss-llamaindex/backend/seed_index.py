"""
seed_index.py — Pre-index a PDF into Moss so the index can be reused in main.py.

Usage:
  python seed_index.py /path/to/file.pdf [index-name]

Example:
  python seed_index.py ~/Downloads/1706.03762v7.pdf transformer-paper

The printed index name can be injected into main.py's session cache via the
SEED_INDEX env var (see bottom of this file).
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from liteparse import LiteParse
from moss import DocumentInfo, MossClient
from nltk.tokenize import sent_tokenize

load_dotenv()

MOSS_PROJECT_ID = os.getenv("MOSS_PROJECT_ID", "")
MOSS_PROJECT_KEY = os.getenv("MOSS_PROJECT_KEY", "")

_parser = LiteParse()


def chunk_text(text: str, chunk_size_words: int = 400, overlap_sentences: int = 2) -> list[str]:
    """
    Chunk text by accumulating sentences until reaching ~chunk_size_words.
    Overlap by carrying the last overlap_sentences from the previous chunk.

    Args:
        text: The text to chunk
        chunk_size_words: Target word count per chunk (default 400)
        overlap_sentences: Number of sentences to carry forward for overlap (default 2).
                          Must be >= 0. Clamped to max(1, chunk_size_words // 100) to prevent
                          excessive overlap that reduces chunking progress.

    Returns:
        List of text chunks (each containing complete sentences only)
    """
    if chunk_size_words < 1:
        raise ValueError(f"chunk_size_words must be >= 1, got {chunk_size_words}")
    if overlap_sentences < 0:
        raise ValueError(f"overlap_sentences must be >= 0, got {overlap_sentences}")

    # Clamp overlap to sensible maximum (avoid excessive overlap reducing progress)
    overlap_sentences = min(overlap_sentences, max(1, chunk_size_words // 100))

    sentences = sent_tokenize(text)
    # Strip and filter out empty sentences
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return []

    chunks = []
    i = 0

    while i < len(sentences):
        chunk_sentences = []
        word_count = 0
        start_idx = i

        # Accumulate sentences until we exceed chunk_size_words
        while i < len(sentences):
            sentence = sentences[i]
            sentence_word_count = len(sentence.split())

            # Always add the first sentence in a chunk
            if not chunk_sentences:
                chunk_sentences.append(sentence)
                word_count += sentence_word_count
                i += 1
            # If adding this sentence would exceed the limit, stop
            elif word_count + sentence_word_count > chunk_size_words:
                break
            # Otherwise, add it
            else:
                chunk_sentences.append(sentence)
                word_count += sentence_word_count
                i += 1

        # Join sentences into a chunk (all sentences are guaranteed complete)
        chunk_text_str = " ".join(chunk_sentences)
        chunks.append(chunk_text_str)

        # For the next chunk, back up to create overlap
        if i < len(sentences):
            i = max(i - overlap_sentences, start_idx + 1)

    return chunks


async def seed(pdf_path: str, index_name: str) -> str:
    filename = Path(pdf_path).name

    print(f"Parsing {filename} ...")
    result = _parser.parse(pdf_path, ocr_enabled=False)
    pages = [
        {"page": page.pageNum, "text": page.text.strip()}
        for page in result.pages
        if page.text.strip()
    ]
    print(f"  Pages: {len(pages)}")

    docs: list[DocumentInfo] = []
    for p in pages:
        for idx, chunk in enumerate(chunk_text(p["text"])):
            docs.append(DocumentInfo(
                id=f"{filename}-p{p['page']}-c{idx}",
                text=chunk,
                metadata={"source": filename, "page": str(p["page"])},
            ))
    print(f"  Chunks: {len(docs)}")

    print(f"Creating Moss index '{index_name}' ...")
    client = MossClient(MOSS_PROJECT_ID, MOSS_PROJECT_KEY)
    await client.create_index(index_name, docs)
    await client.load_index(index_name)

    print("\nDone!")
    print(f"  Index name : {index_name}")
    print(f"  Chunk count: {len(docs)}")
    print("\nTo use this as a cached session in main.py, set:")
    print(f"  SEED_INDEX_NAME={index_name}")
    return index_name


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python seed_index.py /path/to/file.pdf [index-name]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not Path(pdf_path).exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    default_name = Path(pdf_path).stem.lower().replace(".", "-").replace("_", "-")[:32]
    index_name = sys.argv[2] if len(sys.argv) > 2 else f"seed-{default_name}"

    asyncio.run(seed(pdf_path, index_name))
