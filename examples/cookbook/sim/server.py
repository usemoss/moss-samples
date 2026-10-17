#
# Copyright (c) 2025, InferEdge Inc.
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""FastAPI webhook server — exposes Moss search to sim.ai as an external tool.

Run with:
    uvicorn server:app --host 0.0.0.0 --port 8000

Later you can run ngrok to expose your local server to the internet:
    ngrok http 8000

Then in your sim.ai workflow, add an HTTP tool node:
    POST https://your-server/search
    Body: {"query": "{{user_message}}"}
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sim_moss import MossSimSearch

load_dotenv()

search = MossSimSearch(
    project_id=os.environ["MOSS_PROJECT_ID"],
    project_key=os.environ["MOSS_PROJECT_KEY"],
    index_name=os.environ.get("MOSS_INDEX_NAME", "sim-docs"),
    top_k=5,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the Moss index once at startup so every request hits a warm index."""
    await search.load_index()
    yield


app = FastAPI(
    title="Moss Knowledge Base for sim.ai",
    description="Webhook server that serves Moss semantic search results to sim.ai workflows.",
    lifespan=lifespan,
)


class SearchRequest(BaseModel):
    """Request body for the /search endpoint."""

    query: str


@app.post("/search")
async def handle_search(req: SearchRequest):
    """Handle a knowledge base query from a sim.ai workflow tool node.

    Returns documents in sim.ai's expected shape:
        {"results": [{"content": "...", "score": 0.94, "source": "..."}], "time_taken_ms": 4}
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    result = await search.search(req.query)
    return {"results": result.results, "time_taken_ms": result.time_taken_ms}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "index_loaded": search._index_loaded}
