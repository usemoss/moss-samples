import json
import logging
import os
import time
from dotenv import load_dotenv
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


# Moss Import
from moss import MossClient, QueryOptions

load_dotenv()

# Configuration
MOSS_PROJECT_ID = os.getenv("MOSS_PROJECT_ID")
MOSS_PROJECT_KEY = os.getenv("MOSS_PROJECT_KEY")
INDEX_NAME = os.getenv("MOSS_INDEX_NAME", "demo-customer_faqs")
# This support line serves one region. Metadata filtering scopes retrieval to
# region-specific policies + global ("all") docs. Set MOSS_REGION=EU to compare.
ALLOWED_REGIONS = {"US", "EU"}
REGION = os.getenv("MOSS_REGION", "US")
if REGION not in ALLOWED_REGIONS:
    REGION = "US"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("moss-agent")

class MossSemanticRetrievalAgent(Agent):

    def __init__(self, moss_client: MossClient, room: rtc.Room):
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
        self.region = REGION  # live-updated from the UI region picker

    async def _publish_retrieval(self, query: str, results, fallback_ms: float) -> None:
        """Send the retrieved chunks to the web UI over a LiveKit data channel."""
        # Use Moss's own server-reported search time; fall back to wall-clock.
        server_ms = getattr(results, "time_taken_ms", None)
        took_ms = float(server_ms) if server_ms is not None else fallback_ms
        payload = {
            "query": query,
            "docs": [
                {
                    "id": getattr(d, "id", None),
                    "text": d.text,
                    "score": float(getattr(d, "score", 0.0)),
                }
                for d in (results.docs if results and results.docs else [])
            ],
            "took_ms": round(took_ms, 2),
            "region": self.region,
        }
        try:
            await self.room.local_participant.publish_data(
                payload=json.dumps(payload).encode("utf-8"),
                reliable=True,
                topic="moss.retrieval",
            )
        except Exception as e:
            logger.warning(f"Failed to publish retrieval data: {e}")

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        """
        Intercept user message -> Search Moss -> Inject Context -> Continue
        """
        user_query = new_message.text_content
        if not user_query or not user_query.strip():
            # ignore empty/interim transcription artifacts
            await super().on_user_turn_completed(turn_ctx, new_message)
            return
        logger.info(f"User asked: {user_query}")

        try:
            # 1. Automatic Search — metadata-filtered to this region + global docs
            region_filter = {"field": "region", "condition": {"$in": [self.region, "all"]}}
            t0 = time.perf_counter()
            results = await self.moss.query(
                INDEX_NAME,
                user_query,
                QueryOptions(top_k=5, alpha=0.8, filter=region_filter),
            )
            took_ms = (time.perf_counter() - t0) * 1000.0

            # 2. Stream the retrieval to the web UI (the Moss knowledge-base panel)
            await self._publish_retrieval(user_query, results, took_ms)

            # 3. Context Injection
            if results.docs:
                context_str = "\n".join([f"- {d.text}" for d in results.docs])
                injection = (
                    f"Relevant information:\n{context_str}\n\n"
                    "Answer using only this. Do not mention these notes or where they came from."
                )
                turn_ctx.add_message(role="system", content=injection)
                logger.info(f"Injected context ({took_ms:.1f}ms): {context_str[:100]}...")
            else:
                # No match: keep the agent from inventing an answer.
                turn_ctx.add_message(
                    role="system",
                    content="No relevant information was found. Say you don't have that detail "
                    "and offer to connect them with a person. Do not make up specifics.",
                )
                logger.info("No relevant context found in Moss index")

        except Exception as e:
            logger.error(f"Moss search failed: {e}", exc_info=True)

        # 3. Proceed with standard generation
        await super().on_user_turn_completed(turn_ctx, new_message)


async def entrypoint(ctx: JobContext):
    if not MOSS_PROJECT_ID or not MOSS_PROJECT_KEY:
        raise SystemExit(
            "Missing MOSS_PROJECT_ID / MOSS_PROJECT_KEY. Copy .env.example to .env and fill them in."
        )
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

    # Create Session
    session = AgentSession(
        stt=deepgram.STT(model="nova-2", language="en-US"),
        llm=openai.LLM(model="gpt-4o-mini"),
        # sonic-turbo = Cartesia's lowest-latency model; "Jacqueline" voice.
        # Swap the id for any voice from play.cartesia.ai.
        tts=cartesia.TTS(model="sonic-turbo", voice="9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"),
        # activation_threshold above the 0.5 default + a short silence window
        # cuts false triggers so the agent doesn't talk over the caller.
        vad=silero.VAD.load(min_silence_duration=0.5, activation_threshold=0.6),
        # A real turn-detection model + endpointing delays make turn-taking
        # feel crisp instead of guessing on raw VAD.
        turn_handling={
            "turn_detection": MultilingualModel(),
            "endpointing": {"min_delay": 0.5, "max_delay": 1.5},
        },
    )

    agent = MossSemanticRetrievalAgent(moss_client, ctx.room)

    # The UI region picker publishes { "region": "US" | "EU" } on this topic.
    @ctx.room.on("data_received")
    def _on_data(pkt: rtc.DataPacket):
        if pkt.topic == "moss.region":
            try:
                r = json.loads(bytes(pkt.data).decode("utf-8")).get("region")
                if r in ALLOWED_REGIONS:
                    agent.region = r
                    logger.info(f"Region filter set to {r}")
                else:
                    logger.warning(f"Ignoring unknown region {r!r} (allowed: {sorted(ALLOWED_REGIONS)})")
            except Exception as e:
                logger.warning(f"Bad region packet: {e}")

    # Start the session with our custom MossSemanticRetrievalAgent
    await session.start(agent=agent, room=ctx.room)

    # Speak first, instantly — a fixed opener via say() skips the LLM round-trip.
    await session.say(
        "Thanks for calling Northwind support. How can I help you today?",
        allow_interruptions=True,
    )

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))