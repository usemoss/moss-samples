"""
Ecommerce Support Voice Agent
=============================

Showcase for the ``moss-agent`` SDK's process-wide ``MossAgent`` + per-room
``attach(ctx)`` pattern.

How it's wired:

  prewarm() (runs ONCE per worker process)
    |
    +-- MossAgent(project_id, project_key)
    +-- agent.load_indexes(["ecommerce_products",
                            "ecommerce_faq",
                            "ecommerce_policies"])
    +-- proc.userdata["moss_agent"] = agent

  handle_visit(ctx) (runs PER LiveKit room)
    |
    +-- await ctx.connect()
    +-- call = agent.attach(ctx)         <-- one line, scoped to this room
    +-- AgentSession(...).start(...)
    +-- Tool calls route every query through `call.query_multi_index(...)`
        so per-call telemetry (call_id, durationMs) attaches automatically.

Why this matters:

  The indexes are loaded once at boot. Every concurrent room queries the
  same warm in-process cache. There is no per-call cold start, no
  duplicated state, and search latency stays in the sub-10ms band even
  with hundreds of simultaneous calls.

  ``attach(ctx)`` is idempotent on ``ctx.room.name`` and registers a
  shutdown callback so the call scope closes automatically when the room
  tears down - no manual lifecycle code in your handler.

Run::

    # 1. Build the indexes once
    uv run python create_indexes.py

    # 2A. Talk in your terminal (no LiveKit server needed)
    uv run python agent.py console

    # 2B. Or register as a worker and dispatch from a browser
    uv run python agent.py dev
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    cli,
    function_tool,
)
from livekit.plugins import cartesia, deepgram, openai, silero
from moss_agent import MossAgent, MossCall, QueryOptions

load_dotenv()

PRODUCT_INDEX = "ecommerce_products"
FAQ_INDEX = "ecommerce_faq"
POLICY_INDEX = "ecommerce_policies"
ALL_INDEXES = [PRODUCT_INDEX, FAQ_INDEX, POLICY_INDEX]

logging.getLogger("livekit").setLevel(logging.WARNING)
logging.getLogger("livekit.agents").setLevel(logging.WARNING)
logger = logging.getLogger("moss-ecommerce-support")
logger.setLevel(logging.INFO)

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"See .env.example for the full list of keys this example needs."
        )
    return value


# ---------------------------------------------------------------------------
# Process-wide setup: build MossAgent, warm indexes. Runs ONCE per worker.
# ---------------------------------------------------------------------------

server = AgentServer(num_idle_processes=1)


def prewarm(proc: JobProcess) -> None:
    """Construct the process-wide ``MossAgent`` and warm its indexes.

    Everything in here runs exactly once per worker process. The agent and
    its loaded indexes are then shared by every room this worker handles -
    no per-call cold start, no duplicated state.
    """
    import asyncio

    agent = MossAgent(
        project_id=_require_env("MOSS_PROJECT_ID"),
        project_key=_require_env("MOSS_PROJECT_KEY"),
    )
    asyncio.run(agent.load_indexes(ALL_INDEXES))
    logger.info(
        f"{GREEN}Prewarmed MossAgent (client_id={agent.client_id}) "
        f"with {len(ALL_INDEXES)} indexes: {', '.join(ALL_INDEXES)}{RESET}"
    )
    proc.userdata["moss_agent"] = agent


server.setup_fnc = prewarm


# ---------------------------------------------------------------------------
# The voice agent. Owns a `MossCall` scoped to the current room.
# ---------------------------------------------------------------------------


class SupportAgent(Agent):
    """A single retrieval-grounded support agent.

    Every factual question routes through ``self._call`` - the
    :class:`MossCall` that ``attach(ctx)`` returned. That object tags every
    query with the LiveKit room's ``call_id`` so per-call telemetry
    (durationMs, query count) lands in Moss's event log without any extra
    work on our side.
    """

    def __init__(self, call: MossCall):
        self._call = call

        super().__init__(
            instructions="""
                You are an ecommerce support voice agent for a small online store.

                You can answer questions about:
                  - Specific products (price, features, availability, colors)
                  - Shipping, payment, and account questions
                  - Return, warranty, price-match, and privacy policies

                Rules:
                  - ALWAYS call `search_store` before answering a factual
                    question. Never invent prices, SKUs, shipping times, or
                    policy terms.
                  - If the question is clearly product-specific (a model name,
                    a SKU, "do you have X"), call `search_products` to scope
                    the search to the product catalog.
                  - Keep answers short and conversational. This is voice -
                    no bullet points, no markdown, no SKUs read aloud unless
                    the customer asks for one.
                  - If the search returns nothing useful, say you'll have a
                    human follow up - do not guess.
            """,
        )

    async def on_enter(self) -> None:
        await self.session.say(
            "Hi, this is the support line. I can help with our products, "
            "shipping, returns, anything store-related. What's going on?"
        )

    @function_tool
    async def search_store(self, context: RunContext, question: str) -> str:
        """Search the store knowledge base across products, FAQ, and policies.

        Use this for any factual question that isn't obviously scoped to one
        of those three categories - the multi-index search lets the embedding
        model pick the right docs across all of them.

        Args:
            question: The customer's question, rephrased as a search query.
        """
        logger.info(f"{CYAN}Moss multi-index query [{self._call.call_id[:8]}]:{RESET} {question}")
        try:
            results = await self._call.query_multi_index(
                ALL_INDEXES,
                question,
                QueryOptions(top_k=4),
            )
        except Exception as e:
            logger.error(f"Moss search failed: {e}", exc_info=True)
            return "Knowledge base search failed. Tell the customer you'll have a teammate follow up."

        if not results.docs:
            return "No relevant information found. Tell the customer you'll have a human follow up."

        logger.info(
            f"{GREEN}  returned {len(results.docs)} docs in {results.time_taken_ms}ms{RESET}"
        )
        for i, doc in enumerate(results.docs, 1):
            preview = doc.text[:120] + "..." if len(doc.text) > 120 else doc.text
            logger.info(f"{GREEN}  [{i}] {preview}{RESET}")

        return "\n".join(f"- {d.text}" for d in results.docs)

    @function_tool
    async def search_products(self, context: RunContext, question: str) -> str:
        """Search only the product catalog.

        Call this when the customer is clearly asking about a specific
        product or product category - "do you sell X", "how much is the Y",
        "what colors does Z come in". For broader questions
        (shipping, returns, payment) use `search_store` instead.
        """
        logger.info(f"{CYAN}Moss product query [{self._call.call_id[:8]}]:{RESET} {question}")
        try:
            results = await self._call.query(
                PRODUCT_INDEX,
                question,
                QueryOptions(top_k=4, alpha=0.75),
            )
        except Exception as e:
            logger.error(f"Moss product search failed: {e}", exc_info=True)
            return "Product search failed. Ask the customer to rephrase."

        if not results.docs:
            return "No matching products found. Offer to search the broader store."

        logger.info(
            f"{GREEN}  returned {len(results.docs)} docs in {results.time_taken_ms}ms{RESET}"
        )
        return "\n".join(f"- {d.text}" for d in results.docs)


# ---------------------------------------------------------------------------
# Per-room handler. Runs once per LiveKit room.
# ---------------------------------------------------------------------------


@server.rtc_session(agent_name="moss-ecommerce-support")
async def handle_visit(ctx: JobContext) -> None:
    """Bind a Moss call scope to this room and run the voice pipeline."""
    await ctx.connect()

    # Grab the process-wide agent and bind a call scope to this room.
    # `attach` is idempotent and registers its own shutdown callback.
    moss_agent: MossAgent = ctx.proc.userdata["moss_agent"]
    call = moss_agent.attach(ctx)
    logger.info(
        f"{YELLOW}Attached Moss call_id={call.call_id} "
        f"to room={call.livekit_room_id}{RESET}"
    )

    session = AgentSession(
        stt=deepgram.STT(model="nova-2"),
        llm=openai.LLM(model="gpt-4o"),
        tts=cartesia.TTS(model="sonic-3-2026-01-12"),
        vad=silero.VAD.load(),
        turn_handling={"interruption": {"mode": "vad"}},
    )

    await session.start(
        agent=SupportAgent(call),
        room=ctx.room,
    )


if __name__ == "__main__":
    cli.run_app(server)
