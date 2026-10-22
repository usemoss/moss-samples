import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime

from dotenv import load_dotenv
from openai import AsyncOpenAI
from livekit import rtc
from livekit.plugins import openai, deepgram, silero, cartesia
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.agents import (
    JobContext,
    WorkerOptions,
    cli,
    ChatContext,
    ChatMessage,
    Agent,
    AgentSession,
)

from moss import MossClient, DocumentInfo, QueryOptions

load_dotenv()

MOSS_PROJECT_ID = os.getenv("MOSS_PROJECT_ID")
MOSS_PROJECT_KEY = os.getenv("MOSS_PROJECT_KEY")
# Long-term, pre-loaded knowledge shared across every call.
CATALOG_INDEX = os.getenv("TRAVEL_CATALOG_INDEX", "demo-travel-catalog")

# Turns the traveler's raw speech into clean, standalone facts before we store them.
# Questions, recall requests, and small talk yield no facts, so they never hit the session.
FACT_EXTRACT_PROMPT = """You pull durable traveler preferences out of one thing the traveler just said on a trip-planning call.

Return JSON: {"facts": ["...", "..."]}.

A fact is a short, standalone statement of something true about the traveler or their trip:
party size, budget, dates, interests, must-haves, or destinations they like or dislike.

Rules:
- Only include preferences actually stated in this utterance.
- Split multiple preferences into separate facts.
- Drop filler and normalize (e.g. "our budget's around, uh, twenty five hundred a person" -> "Budget is about $2,500 per person").
- Keep each fact under about 8 words.
- Return {"facts": []} for questions, recall requests, or small talk (e.g. "what did I say my budget was?", "so where should we go?")."""

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("moss-travel")


def _docs(result):
    return [
        {"id": getattr(d, "id", None), "text": d.text, "score": float(getattr(d, "score", 0.0))}
        for d in (result.docs if result and result.docs else [])
    ]


class TravelConciergeAgent(Agent):
    """Answers from two Moss indexes at once: a pre-loaded catalog (long-term)
    and a live session that captures what the traveler says on THIS call."""

    def __init__(self, moss_client: MossClient, session_index, room: rtc.Room):
        super().__init__(
            instructions="""
                You are a warm, upbeat travel concierge on a voice call with one traveler.
                Each turn you're given two kinds of context:
                  1. Trip options from our catalog.
                  2. What the traveler has told you earlier in THIS call (their preferences).
                Use both: remember what they've said, and recommend trips from the catalog
                that fit. If they ask you to recall something they mentioned, answer from the
                facts in that context. Keep replies short and natural for voice. Never mention
                indexes, sessions, catalogs, or how you look things up.
            """
        )
        self.moss = moss_client
        self.session_index = session_index
        self.room = room
        self.turn = 0
        # background task that stores the current turn's facts; awaited next turn
        self._pending_remember = None
        # Small, fast model used only to distill the traveler's speech into facts.
        self._extractor = AsyncOpenAI()

    async def _publish(self, query, catalog, session, catalog_ms, session_ms):
        payload = {
            "query": query,
            "catalog": _docs(catalog),
            "session": _docs(session),
            "catalog_ms": round(catalog_ms, 2),
            "session_ms": round(session_ms, 2),
        }
        try:
            await self.room.local_participant.publish_data(
                json.dumps(payload).encode("utf-8"), reliable=True, topic="moss.retrieval"
            )
        except Exception as e:
            logger.warning(f"Failed to publish retrieval data: {e}")

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        query = new_message.text_content
        logger.info(f"Traveler: {query}")
        try:
            # 0. Make sure the previous turn's facts are stored before we recall,
            #    so an immediate follow-up question sees them.
            if self._pending_remember is not None:
                await self._pending_remember
                self._pending_remember = None

            # 1. Recall prior turns from the live session (short-term memory).
            t = time.perf_counter()
            session_results = await self.session_index.query(query, QueryOptions(top_k=3))
            session_ms = (time.perf_counter() - t) * 1000.0

            # 2. Look up matching trips in the pre-loaded catalog (long-term knowledge).
            t = time.perf_counter()
            catalog_results = await self.moss.query(CATALOG_INDEX, query, QueryOptions(top_k=3))
            catalog_ms = (time.perf_counter() - t) * 1000.0

            # 3. Show both in the UI.
            await self._publish(query, catalog_results, session_results, catalog_ms, session_ms)

            # 4. Inject both into the model's context, clearly labeled.
            blocks = []
            if catalog_results.docs:
                blocks.append("Trip options from our catalog:\n" + "\n".join(f"- {d.text}" for d in catalog_results.docs))
            if session_results.docs:
                blocks.append("Facts the traveler shared earlier in this call:\n" + "\n".join(f"- {d.text}" for d in session_results.docs))
            if blocks:
                turn_ctx.add_message(role="system", content="\n\n".join(blocks) + "\n\nUse this to help the traveler.")

            # 5. Distill this turn into facts and store only those in the live session, in the
            #    background so it never delays the reply. Awaited at the top of the next turn
            #    (step 0) so recall always sees it. Questions/recall add nothing.
            self._pending_remember = asyncio.create_task(self._remember_facts(query))
        except Exception as e:
            logger.error(f"Moss lookup failed: {e}", exc_info=True)

        await super().on_user_turn_completed(turn_ctx, new_message)

    async def _extract_facts(self, text: str) -> list[str]:
        """Pull clean, standalone facts out of one traveler utterance. [] if it states none."""
        try:
            resp = await self._extractor.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": FACT_EXTRACT_PROMPT},
                    {"role": "user", "content": text},
                ],
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            return [f.strip() for f in data.get("facts", []) if isinstance(f, str) and f.strip()]
        except Exception as e:
            logger.warning(f"Fact extraction failed: {e}")
            return []

    async def _remember_facts(self, text: str) -> None:
        for fact in await self._extract_facts(text):
            self.turn += 1
            try:
                await self.session_index.add_docs(
                    [DocumentInfo(id=f"fact-{self.turn}", text=fact, metadata={"role": "traveler"})]
                )
                logger.info(f"Remembered: {fact}")
            except Exception as e:
                logger.warning(f"Failed to store fact: {e}")


async def entrypoint(ctx: JobContext):
    if not MOSS_PROJECT_ID or not MOSS_PROJECT_KEY:
        raise SystemExit(
            "Missing MOSS_PROJECT_ID / MOSS_PROJECT_KEY. Copy .env.example to .env and fill them in."
        )
    await ctx.connect()

    client = MossClient(project_id=MOSS_PROJECT_ID, project_key=MOSS_PROJECT_KEY)

    # Long-term: the pre-loaded catalog, shared across all calls. Fatal if missing
    # so the worker doesn't keep taking calls with an empty catalog.
    try:
        await client.load_index(CATALOG_INDEX)
        logger.info(f"Loaded catalog index: {CATALOG_INDEX}")
    except Exception as e:
        raise SystemExit(f"Catalog index '{CATALOG_INDEX}' not available ({e}). Run seed_index.py first.")

    # Short-term: a fresh, empty session just for this call. The uuid suffix keeps
    # it unique even if two calls start in the same second.
    session_name = f"trip-session-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    session_index = await client.session(session_name)
    logger.info(f"Opened live session: {session_name}")

    agent = TravelConciergeAgent(client, session_index, ctx.room)

    session = AgentSession(
        stt=deepgram.STT(model="nova-2", language="en-US"),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=cartesia.TTS(model="sonic-turbo", voice="9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"),
        vad=silero.VAD.load(min_silence_duration=0.5, activation_threshold=0.6),
        turn_handling={
            "turn_detection": MultilingualModel(),
            "endpointing": {"min_delay": 0.5, "max_delay": 1.5},
        },
    )

    await session.start(agent=agent, room=ctx.room)
    await session.say(
        "Hi! I'm your travel concierge. Tell me about the trip you're dreaming of and I'll find something.",
        allow_interruptions=True,
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
