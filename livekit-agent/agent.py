"""
LiveKit Voice Agent - Quick Start
==================================
The simplest possible LiveKit voice agent to get you started.
Requires only OpenAI and Deepgram API keys.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from inferedge_moss import MossClient
from livekit import agents
from livekit import rtc  # <--- ADD THIS LINE
from livekit.agents import Agent, AgentSession, RunContext, metrics, MetricsCollectedEvent
from livekit.agents.llm import function_tool
from livekit.plugins import cartesia, deepgram, openai, silero
# DataPacketKind import is correctly removed.

from settings import get_settings

# Load environment variables
load_dotenv(".env")

# Get configuration settings
settings = get_settings()

logger = logging.getLogger("livekit.agent_logger")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

async def verify_components_ready():
    """Verify all voice pipeline components are loaded and ready."""
    try:
        logger.info("Verifying all voice pipeline components...")

        # Initialize STT
        logger.info("Initializing STT (Deepgram)...")
        stt = deepgram.STT(
            model=settings.stt.model,
            language=settings.stt.language
        )
        logger.info("✓ STT component ready")

        # Initialize LLM
        logger.info("Initializing LLM (OpenAI)...")
        llm = openai.LLM(
            model=settings.llm.model,
            temperature=settings.llm.temperature
        )
        logger.info("✓ LLM component ready")

        # Initialize TTS
        logger.info("Initializing TTS (Cartesia)...")
        tts = cartesia.TTS(
            model=settings.tts.model,
            voice=settings.tts.voice,
            speed=settings.tts.speed
        )
        logger.info("✓ TTS component ready")

        # Initialize VAD
        logger.info("Initializing VAD (Silero)...")
        vad = silero.VAD.load()
        logger.info("✓ VAD component ready")

        # Initialize Moss client AND load index
        logger.info("Initializing Moss client and loading index...")
        moss_client = MossClient(
            os.environ["MOSS_PROJECT_ID"],
            os.environ["MOSS_PROJECT_KEY"]
        )
        await moss_client.load_index(settings.moss.index_name)
        logger.info("✓ Moss client and index ready")

        logger.info("All components verified and ready")
        return {
            'stt': stt,
            'llm': llm,
            'tts': tts,
            'vad': vad,
            'moss_client': moss_client
        }

    except Exception as e:
        logger.error(f"Component verification failed: {e}")
        return None


async def create_readiness_marker():
    """Create readiness marker only after all components are verified."""
    components = await verify_components_ready()
    if components:
        Path("/tmp/agent_ready").touch()
        logger.info("Agent fully ready - all components loaded and verified")
        return components
    else:
        logger.error("Agent not ready - component loading failed")
        # Remove readiness marker if it exists
        ready_path = Path("/tmp/agent_ready")
        if ready_path.exists():
            ready_path.unlink()
            logger.info("Removed readiness marker due to component failure")
        return None


class Assistant(Agent):
    """Customer support voice agent powered by the Moss FAQ index."""

    # --- START OF CHANGE 1 ---
    def __init__(self, moss_client, room: rtc.Room):
        super().__init__(
            instructions=settings.instructions
        )

        self._moss_config = settings.moss
        self._moss_client = moss_client
        self._room = room  # Store the room object
        self._moss_index_loaded = True
    # --- END OF CHANGE 1 ---

    @function_tool
    async def search_support_faqs(self, context: RunContext, question: str) -> str:
        """Retrieve relevant FAQ answers using Moss semantic search."""

        query = question.strip()
        if not query:
            return "No question provided for FAQ search."

        logger.info("Received support query: %s", query)

        results = await self._moss_client.query(
            self._moss_config.index_name,
            query,
            self._moss_config.top_k_results
        )

        time_taken_ms = getattr(results, "time_taken_ms", 0)
        logger.info(
            "Moss query completed in %sms", time_taken_ms
        )

        docs = list(getattr(results, "docs", []) or [])

# --- BEGIN MOSS METRICS ---
        try:
            # Create payload for our new metric type
            payload = {
                "type": "moss",
                "data": {
                    "time_taken_ms": time_taken_ms,
                    "query": query,
                    "num_matches": len(docs)
                }
            }

            # Send payload over data channel
            json_payload = json.dumps(payload).encode("utf-8")

            # Use the stored self._room object
            await self._room.local_participant.publish_data(
                payload=json_payload,
                reliable=True,
            )
        except Exception as e:
            logger.error(f"Failed to send Moss metrics: {e}")
        # --- END MOSS METRICS ---

        if not docs:
            logger.info("No FAQ matches returned for query: %s", query)
            summary = "No FAQ matches found."
        else:
            match_texts = [
                (doc.text or "").strip()
                for doc in docs
            ]

            full_text = "\n\n".join(match_texts)

            logger.info(
                "Top Moss matches for %r:\n%s",
                query,
                full_text,
            )
            summary = full_text

        context.session.history.add_message(
            role="system",
            content="FAQ search context for the current user request:\n" + summary,
            created_at=datetime.utcnow().timestamp(),
        )

        return summary

async def entrypoint(ctx: agents.JobContext):
    """Entry point for the agent."""

    # Create readiness marker after verifying all components
    components = await create_readiness_marker()
    if not components:
        logger.error("Failed to initialize components, cannot start agent")
        return

    # Configure the voice pipeline using pre-loaded components
    session = AgentSession(
        stt=components['stt'],
        llm=components['llm'],
        tts=components['tts'],
        vad=components['vad'],
    )

    # --- BEGIN METRICS INTEGRATION (MODIFIED) ---

    # 1. Define the async logic in its own function
    async def _send_metrics_task(ev: MetricsCollectedEvent):
        # --- START OF CHANGE ---
        payload = {"type": "", "data": {}}
        data = ev.metrics # ev.metrics is the metric object itself

        try:
            # Check the type of the metric object
            if isinstance(data, metrics.LLMMetrics):
                payload["type"] = "llm"
                payload["data"] = {
                    "duration": data.duration, "ttft": data.ttft,
                    "completion_tokens": data.completion_tokens, "prompt_tokens": data.prompt_tokens,
                    "tokens_per_second": data.tokens_per_second, "speech_id": data.speech_id,
                }
            elif isinstance(data, metrics.TTSMetrics):
                payload["type"] = "tts"
                payload["data"] = {
                    "duration": data.duration, "ttfb": data.ttfb,
                    "audio_duration": data.audio_duration, "characters_count": data.characters_count,
                    "speech_id": data.speech_id,
                }
            elif isinstance(data, metrics.STTMetrics):
                payload["type"] = "stt"
                payload["data"] = {
                    "duration": data.duration, "audio_duration": data.audio_duration,
                }
            elif isinstance(data, metrics.EOUMetrics):
                payload["type"] = "eou"
                payload["data"] = {
                    "end_of_utterance_delay": data.end_of_utterance_delay,
                    "transcription_delay": data.transcription_delay,
                    "speech_id": data.speech_id,
                }
            else:
                # Skip other metric types we don't handle (like VADMetrics)
                return

            # --- END OF CHANGE ---

            # Send payload over data channel to all participants in the room
            json_payload = json.dumps(payload).encode("utf-8")
            await ctx.room.local_participant.publish_data(
                payload=json_payload,
                reliable=True,
            )
            # logger.info(f"Sent metrics packet: {payload['type']}") # Optional: can be noisy

        except Exception as e:
            logger.error(f"Failed to process/send metrics data: {e}")

    # 2. Create a synchronous callback for the listener
    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        # This part is synchronous and runs immediately
        metrics.log_metrics(ev.metrics)

        # 3. Schedule the async task to run in the background
        asyncio.create_task(_send_metrics_task(ev))

    # --- END METRICS INTEGRATION ---

    try:
        # Start the session.
        # The agent will now wait for the user to speak.
        await session.start(
            room=ctx.room,
            # --- START OF CHANGE 3 ---
            agent=Assistant(components['moss_client'], ctx.room)
            # --- END OF CHANGE 3 ---
        )

        logger.info("Agent session finished successfully")

    except Exception as e:
        logger.error(f"Session error: {e}")
        raise
    finally:
        logger.info("Agent session ended, ready for next connection")


if __name__ == "__main__":
    # Run the agent
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
