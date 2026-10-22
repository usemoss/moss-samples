import json
import logging
import os
import time
from dotenv import load_dotenv
from livekit import rtc
from livekit.plugins import openai, deepgram, silero, cartesia
from livekit.agents import (
    JobContext,
    WorkerOptions,
    cli,
    ChatContext,
    ChatMessage,
    Agent,
    AgentSession,
    StopResponse,
)


# Moss Import
from moss import MossClient, QueryOptions

load_dotenv()

# Configuration
MOSS_PROJECT_ID = os.getenv("MOSS_PROJECT_ID")
MOSS_PROJECT_KEY = os.getenv("MOSS_PROJECT_KEY")
INDEX_NAME = os.getenv("MOSS_INDEX_NAME", "demo-customer_faqs")
# Default region for console / no-UI runs. The web picker is authoritative when
# the browser is connected and overrides this on moss.region.
ALLOWED_REGIONS = {"US", "EU"}
_region_env = os.getenv("MOSS_REGION", "US")
if _region_env not in ALLOWED_REGIONS:
    raise SystemExit(
        f"Invalid MOSS_REGION={_region_env!r}. Allowed values: {sorted(ALLOWED_REGIONS)}."
    )
REGION = _region_env

NO_MATCH_CONTEXT = (
    "No relevant information was found. Say you don't have that detail "
    "and offer to help with something else. Do not make up specifics."
)

# LiveKit reliable data packets are capped around 15 KiB; stay under that.
_MAX_RETRIEVAL_BYTES = 14 * 1024

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("moss-agent")

class MossSemanticRetrievalAgent(Agent):

    def __init__(self, moss_client: MossClient, room: rtc.Room, region: str = REGION):
        super().__init__(
            instructions="""
                You are Northwind's customer support voice assistant, speaking directly to
                one customer on a call. Answer naturally and concisely using ONLY the
                knowledge-base context provided for the current question.

                - Present policies as simply "our policy" — the customer's own. Never mention
                  regions, "other regions", that policies vary by location, the knowledge
                  base, filters, or how you look answers up.
                - The context can change between questions; do not reuse facts or numbers from
                  earlier in the conversation if they are not in the current context.
                - If the current context doesn't answer the question, say you don't know and
                  offer to help with something else.

                Keep replies to a sentence or two, warm and clear for voice.
            """
        )
        self.moss = moss_client
        self.room = room
        self.region = region  # live-updated from the UI region picker
        # Region updates that arrive while a turn/reply is in flight are deferred so the
        # spoken answer stays aligned with the retrieval that already ran.
        self._pending_region: str | None = None
        self._turn_busy = False

    def apply_region(self, region: str) -> None:
        """Apply a UI region change, or queue it until the current reply finishes."""
        if region not in ALLOWED_REGIONS:
            return
        session = getattr(self, "_session", None)
        state = getattr(session, "agent_state", None) if session is not None else None
        if self._turn_busy or state in ("thinking", "speaking"):
            self._pending_region = region
            logger.info(
                "Region %s queued until current reply finishes (busy=%s state=%s)",
                region,
                self._turn_busy,
                state,
            )
            return
        self.region = region
        self._pending_region = None
        logger.info(f"Region filter set to {region}")

    def flush_pending_region(self) -> None:
        self._turn_busy = False
        if self._pending_region is None:
            return
        self.region = self._pending_region
        logger.info(f"Region filter set to {self.region} (applied after reply)")
        self._pending_region = None

    def _encode_retrieval_payload(self, query: str, docs: list, took_ms: float, region: str) -> bytes:
        """Build a moss.retrieval JSON payload that fits LiveKit's reliable size limit."""
        docs_out = [
            {
                "id": getattr(d, "id", None),
                "text": d.text,
                "score": float(getattr(d, "score", 0.0)),
            }
            for d in docs
        ]
        # Prefer highest-scoring docs if we must drop some for size.
        docs_out.sort(key=lambda d: d["score"], reverse=True)

        def encode(q: str, doc_list: list) -> bytes:
            return json.dumps(
                {
                    "query": q,
                    "docs": doc_list,
                    "took_ms": round(took_ms, 2),
                    "region": region,
                },
                ensure_ascii=False,
            ).encode("utf-8")

        q = query
        raw = encode(q, docs_out)
        while len(raw) > _MAX_RETRIEVAL_BYTES:
            if docs_out:
                last = docs_out[-1]
                text = last.get("text") or ""
                if len(text) > 120:
                    last["text"] = text[: max(40, len(text) // 2)].rstrip() + "…"
                else:
                    docs_out.pop()
                raw = encode(q, docs_out)
                continue
            if len(q) > 80:
                q = q[: max(40, len(q) // 2)].rstrip() + "…"
                raw = encode(q, docs_out)
                continue
            break

        if len(raw) > _MAX_RETRIEVAL_BYTES:
            logger.warning(
                "moss.retrieval payload still %s bytes after truncation; publishing empty docs",
                len(raw),
            )
            raw = encode(q[:80], [])
        return raw

    async def _publish_retrieval(
        self,
        query: str,
        results,
        fallback_ms: float,
        region: str,
    ) -> None:
        """Send the retrieved chunks to the web UI over a LiveKit data channel."""
        # Use Moss's own server-reported search time; fall back to wall-clock.
        server_ms = getattr(results, "time_taken_ms", None) if results is not None else None
        took_ms = float(server_ms) if server_ms is not None else fallback_ms
        docs = list(results.docs) if results and getattr(results, "docs", None) else []
        payload = self._encode_retrieval_payload(query, docs, took_ms, region)
        try:
            await self.room.local_participant.publish_data(
                payload=payload,
                reliable=True,
                topic="moss.retrieval",
            )
        except Exception as e:
            logger.warning(f"Failed to publish retrieval data: {e}")

    async def _query_moss(self, user_query: str, region: str):
        region_filter = {"field": "region", "condition": {"$in": [region, "all"]}}
        t0 = time.perf_counter()
        results = await self.moss.query(
            INDEX_NAME,
            user_query,
            QueryOptions(top_k=5, alpha=0.8, filter=region_filter),
        )
        took_ms = (time.perf_counter() - t0) * 1000.0
        return results, took_ms

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        """
        Intercept user message -> Search Moss -> Inject Context -> Continue
        """
        user_query = new_message.text_content
        if not user_query or not user_query.strip():
            # ignore empty/interim transcription artifacts
            raise StopResponse()

        logger.info(f"User asked: {user_query}")
        self._turn_busy = True
        region = self.region

        try:
            # Snapshot region for this turn. Mid-turn picker changes are deferred via
            # apply_region() until the reply finishes, so a single query/publish is enough.
            results, took_ms = await self._query_moss(user_query, region)
            await self._publish_retrieval(user_query, results, took_ms, region)

            if results and results.docs:
                context_str = "\n".join([f"- {d.text}" for d in results.docs])
                injection = (
                    f"Relevant information:\n{context_str}\n\n"
                    "Answer using only this. Do not mention these notes or where they came from."
                )
                turn_ctx.add_message(role="system", content=injection)
                logger.info(f"Injected context ({took_ms:.1f}ms): {context_str[:100]}...")
            else:
                # No match: keep the agent from inventing an answer.
                turn_ctx.add_message(role="system", content=NO_MATCH_CONTEXT)
                logger.info("No relevant context found in Moss index")

        except Exception as e:
            logger.error(f"Moss search failed: {e}", exc_info=True)
            # Clear stale panel docs and keep the reply grounded when retrieval fails.
            await self._publish_retrieval(user_query, None, 0.0, region)
            turn_ctx.add_message(role="system", content=NO_MATCH_CONTEXT)

        # Proceed with standard generation (_turn_busy cleared when agent returns to listening)
        await super().on_user_turn_completed(turn_ctx, new_message)


async def entrypoint(ctx: JobContext):
    if not MOSS_PROJECT_ID or not MOSS_PROJECT_KEY:
        raise SystemExit(
            "Missing MOSS_PROJECT_ID / MOSS_PROJECT_KEY. Copy .env.example to .env and fill them in."
        )

    # Register before connect so a UI region packet cannot arrive while we are offline
    # to the topic (browser often publishes as soon as the agent participant appears).
    pending_region = {"value": REGION}
    agent_holder: dict[str, MossSemanticRetrievalAgent | None] = {"agent": None}

    @ctx.room.on("data_received")
    def _on_data(pkt: rtc.DataPacket):
        if pkt.topic == "moss.region":
            try:
                r = json.loads(bytes(pkt.data).decode("utf-8")).get("region")
                if r in ALLOWED_REGIONS:
                    pending_region["value"] = r
                    agent = agent_holder["agent"]
                    if agent is not None:
                        agent.apply_region(r)
                    else:
                        logger.info(f"Region filter pending until agent ready: {r}")
                else:
                    logger.warning(f"Ignoring unknown region {r!r} (allowed: {sorted(ALLOWED_REGIONS)})")
            except Exception as e:
                logger.warning(f"Bad region packet: {e}")

    await ctx.connect()

    # Initialize Moss
    moss_client = MossClient(project_id=MOSS_PROJECT_ID, project_key=MOSS_PROJECT_KEY)

    # Pre-load the index locally. This is required: region metadata filtering is
    # only applied to locally loaded indexes (a cloud-fallback query silently
    # ignores the filter), so a failed load must be fatal rather than a warning.
    try:
        await moss_client.load_index(INDEX_NAME)
        logger.info(f"Successfully loaded index: {INDEX_NAME}")
    except Exception as e:
        raise SystemExit(
            f"Failed to load index '{INDEX_NAME}': {e}. Run seed_index.py first "
            "(region metadata filtering needs the index loaded locally)."
        )

    # Keep the voice pipeline identical to the base example; this PR only adds retrieval/UI.
    session = AgentSession(
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4o"),
        tts=cartesia.TTS(model="sonic-3-2026-01-12"),
        vad=silero.VAD.load(),
        turn_handling={"interruption": {"mode": "vad"}},
    )

    agent = MossSemanticRetrievalAgent(moss_client, ctx.room, region=pending_region["value"])
    agent._session = session  # used by apply_region to detect in-flight replies
    agent_holder["agent"] = agent

    @session.on("agent_state_changed")
    def _on_agent_state(ev):
        # Once the agent returns to listening, apply any region queued mid-reply.
        if ev.new_state in ("listening", "idle"):
            agent.flush_pending_region()

    # Start the session with our custom MossSemanticRetrievalAgent
    await session.start(agent=agent, room=ctx.room)

    # Speak first, instantly — a fixed opener via say() skips the LLM round-trip.
    await session.say(
        "Thanks for calling Northwind support. How can I help you today?",
        allow_interruptions=True,
    )

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
