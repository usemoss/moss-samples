"""
Liteparse + Moss demo backend
------------------------------
PDF upload  → liteparse parses pages → chunk → single moss index (create + load)
Retrieval   → moss query, results streamed via SSE

Endpoints:
  POST /api/upload              – parse → chunk → index (single index, fastest)
  POST /api/chat/{session_id}   – SSE: query results streamed as they arrive
  GET  /api/stream/{session_id} – stub (no hydration)
"""

import asyncio
import json
import os
import tempfile
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from liteparse import LiteParse
from moss import DocumentInfo, MossClient, QueryOptions
from nltk.tokenize import sent_tokenize
from pydantic import BaseModel

load_dotenv()

MOSS_PROJECT_ID = os.getenv("MOSS_PROJECT_ID", "")
MOSS_PROJECT_KEY = os.getenv("MOSS_PROJECT_KEY", "")

_parser = LiteParse()
_seed             = os.getenv("SEED_INDEX_NAME", "")
_seed_chunk_count = int(os.getenv("SEED_CHUNK_COUNT", "0"))

sessions: dict[str, dict] = {}

if _seed:
    sessions["seed"] = {
        "index_name":  _seed,
        "client":      MossClient(MOSS_PROJECT_ID, MOSS_PROJECT_KEY),
        "chunk_count": _seed_chunk_count,
    }

# { session_id: { "index_name": str, "client": MossClient, "chunk_count": int } }


@asynccontextmanager
async def lifespan(app: FastAPI):
    if _seed and "seed" in sessions:
        try:
            print(f"[startup] Loading seed index '{_seed}' into memory…")
            await sessions["seed"]["client"].load_index(_seed)
            print("[startup] Seed index ready.")
        except Exception as e:
            print(f"[startup] Warning: could not load seed index '{_seed}': {e}")
            print("[startup] Sample PDF will be unavailable until the index is created.")
            sessions.pop("seed", None)
    yield


app = FastAPI(title="Liteparse + Moss Demo", lifespan=lifespan)


@app.middleware("http")
async def add_hsts_header(request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=30"
    return response


app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

router = APIRouter(prefix="/llamaindex")

# ── Helpers ────────────────────────────────────────────────────────────────────

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


def parse_pdf_with_liteparse(pdf_path: str) -> list[dict]:
    result = _parser.parse(pdf_path, ocr_enabled=False)
    return [
        {"page": page.pageNum, "text": page.text.strip()}
        for page in result.pages
        if page.text.strip()
    ]


def _create_and_load_sync(name: str, docs: list[DocumentInfo]) -> MossClient:
    """Runs in a thread — own event loop avoids blocking FastAPI's loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        client = MossClient(MOSS_PROJECT_ID, MOSS_PROJECT_KEY)
        loop.run_until_complete(client.create_index(name, docs))
        loop.run_until_complete(client.load_index(name))
        return client
    finally:
        loop.close()


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/api/sample")
async def load_sample():
    """Returns the pre-indexed sample PDF session instantly — no upload needed."""
    seed_session = sessions.get("seed")
    if seed_session is None:
        raise HTTPException(404, "No sample index available — set SEED_INDEX_NAME and restart.")
    return {
        "session_id": "seed",
        "index_name": seed_session["index_name"],
        "chunk_count": seed_session["chunk_count"],
        "files": ["1706.03762v7.pdf"],
    }


@router.post("/api/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(400, "No files provided")

    start      = time.time()
    session_id = uuid.uuid4().hex[:8]
    index_name = f"pdf-{session_id}"
    docs: list[DocumentInfo] = []
    file_names: list[str]    = []

    for file in files[:5]:
        pdf_bytes = await file.read()
        file_names.append(file.filename or "unknown.pdf")

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name
        try:
            pages = await asyncio.to_thread(parse_pdf_with_liteparse, tmp_path)
        finally:
            os.unlink(tmp_path)

        for p in pages:
            for idx, chunk in enumerate(chunk_text(p["text"])):
                docs.append(DocumentInfo(
                    id=f"{file.filename}-p{p['page']}-c{idx}",
                    text=chunk,
                    metadata={"source": file.filename or "unknown", "page": str(p["page"])},
                ))

    if not docs:
        raise HTTPException(422, "No text extracted from the PDFs.")

    print(f"[upload] {session_id} — {len(docs)} chunks, building index…")

    client = await asyncio.to_thread(_create_and_load_sync, index_name, docs)

    sessions[session_id] = {"index_name": index_name, "client": client, "chunk_count": len(docs)}

    elapsed = round(time.time() - start)
    print(f"[upload] done in {elapsed}s")

    return {"session_id": session_id, "chunk_count": len(docs), "elapsed_seconds": elapsed, "files": file_names}


class ChatRequest(BaseModel):
    question: str


@router.post("/api/chat/{session_id}")
async def chat(session_id: str, body: ChatRequest):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    async def generate() -> AsyncGenerator[str, None]:
        result = await session["client"].query(session["index_name"], body.question, QueryOptions(top_k=5, alpha=0.6))
        event = {
            "type":    "shard",
            "shard":   1,
            "total":   1,
            "time_ms": result.time_taken_ms,
            "index":   result.index_name,
            "docs": [
                {
                    "id":     d.id,
                    "text":   d.text,
                    "score":  round(d.score, 3),
                    "source": d.metadata.get("source", "?") if d.metadata else "?",
                    "page":   d.metadata.get("page", "?")   if d.metadata else "?",
                }
                for d in result.docs
            ],
        }
        yield f"data: {json.dumps(event)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/api/stream/{session_id}")
async def stream_noop(session_id: str):
    async def _() -> AsyncGenerator[str, None]:
        yield f"data: {json.dumps({'type': 'complete', 'stats': {'enriched_chunks': 0}})}\n\n"
    return StreamingResponse(_(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
