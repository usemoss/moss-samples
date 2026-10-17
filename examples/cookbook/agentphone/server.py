"""AgentPhone voice webhook server backed by Moss + Claude tool calling.

Thin FastAPI shell. The reusable pieces (tool schema, tool-call loop,
signature verification, NDJSON helpers, Moss log block) live in
``moss_agentphone``. This file wires concrete clients and env vars to
them and exposes the ``/webhook`` route.

Run::

    uv run python create_index.py    # one-time
    uv run python server.py
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from moss import MossClient, QueryOptions
from moss_agentphone import (
    log_moss_search,
    ndjson,
    run_tool_call,
    to_anthropic_history,
    verify_webhook_signature,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
logger = logging.getLogger("moss_agentphone.server")


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


load_dotenv()

WEBHOOK_SECRET = _require_env("AGENTPHONE_WEBHOOK_SECRET")
INDEX_NAME = _require_env("MOSS_INDEX_NAME")
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

moss_client = MossClient(
    _require_env("MOSS_PROJECT_ID"),
    _require_env("MOSS_PROJECT_KEY"),
)
anthropic_client = AsyncAnthropic(api_key=_require_env("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = (
    "You are a friendly customer-support agent on a phone call. "
    "When the caller asks about company policies, orders, refunds, "
    "shipping, returns, account help, or product facts, call the "
    "moss_search tool first and answer using ONLY what it returns. "
    "If the search returns nothing relevant, say so honestly. Keep "
    "replies short and conversational, two to three sentences."
)


async def _moss_search(args: dict[str, Any]) -> str:
    """Tool handler: run a Moss query and return numbered excerpts."""
    query = (args or {}).get("query", "").strip()
    if not query:
        return "moss_search requires a non-empty query string."

    result = await moss_client.query(
        INDEX_NAME, query, QueryOptions(top_k=5, alpha=0.8)
    )
    log_moss_search(query, result.docs, result.time_taken_ms)

    if not result.docs:
        return "No relevant excerpts found."
    return "\n".join(
        f"{i}. {getattr(d, 'text', '')}"
        for i, d in enumerate(result.docs, start=1)
    )


TOOL_HANDLERS = {"moss_search": _moss_search}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await moss_client.load_index(INDEX_NAME)
    logger.info("Index loaded, listening for AgentPhone webhooks")
    yield


app = FastAPI(title="Moss + AgentPhone webhook", lifespan=lifespan)


@app.post("/webhook")
async def webhook(
    request: Request,
    x_webhook_signature: str = Header(...),
    x_webhook_timestamp: str = Header(...),
    x_webhook_id: str = Header(...),
    x_webhook_event: str = Header(...),
):
    body = await request.body()
    if not verify_webhook_signature(
        secret=WEBHOOK_SECRET,
        timestamp=x_webhook_timestamp,
        body=body,
        signature=x_webhook_signature,
    ):
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    event = await request.json()
    logger.info(
        "delivery=%s event=%s channel=%s",
        x_webhook_id,
        event.get("event"),
        event.get("channel"),
    )

    if event.get("event") != "agent.message" or event.get("channel") != "voice":
        return {"ok": True}

    data = event.get("data") or {}
    transcript = data.get("transcript", "")
    history = to_anthropic_history(event.get("recentHistory"))

    async def generate() -> AsyncIterator[bytes]:
        yield ndjson({"text": "Let me check that for you.", "interim": True})
        try:
            answer = await run_tool_call(
                user_message=transcript,
                history=history,
                anthropic_client=anthropic_client,
                tool_handlers=TOOL_HANDLERS,
                model=MODEL,
                system_prompt=SYSTEM_PROMPT,
            )
        except Exception:
            logger.exception("tool-call loop failed")
            answer = "Sorry, I ran into a problem. Could you try again?"
        yield ndjson({"text": answer})

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
