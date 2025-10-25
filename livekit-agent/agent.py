"""
LiveKit Voice Agent - Quick Start
==================================
A simple LiveKit voice agent using OpenAI, Deepgram, Cartesia, and Moss.
"""

# --- 1. Imports ---

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from dotenv import load_dotenv
from inferedge_moss import MossClient
from livekit import agents, rtc
from livekit.agents import (
    Agent,
    AgentSession,
    RunContext,
    MetricsCollectedEvent,
    metrics,
)
from livekit.agents.llm import function_tool
from livekit.plugins import cartesia, deepgram, openai, silero

from settings import get_settings

# --- 2. Configuration & Logging ---

# Load environment variables from .env file
load_dotenv(".env")

# Get configuration settings
try:
    settings = get_settings()
except Exception as e:
    print(f"Error loading settings: {e}")
    exit(1)

# Configure logger
logger = logging.getLogger("livekit.agent_logger")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


# --- 3. Component Verification ---

async def verify_components_ready() -> Optional[Dict[str, Any]]:
    """
    Initialize and verify all voice pipeline components.
    Returns a dictionary of components if successful, else None.
    """
    try:
        logger.info("Verifying all voice pipeline components...")

        logger.info("Initializing STT (Deepgram)...")
        stt = deepgram.STT(
            model=settings.stt.model, language=settings.stt.language
        )
        logger.info("✓ STT component ready")

        logger.info("Initializing LLM (OpenAI)...")
        llm = openai.LLM(
            model=settings.llm.model, temperature=settings.llm.temperature
        )
        logger.info("✓ LLM component ready")

        logger.info("Initializing TTS (Cartesia)...")
        tts = cartesia.TTS(
            model=settings.tts.model,
            voice=settings.tts.voice,
            speed=settings.tts.speed,
        )
        logger.info("✓ TTS component ready")

        logger.info("Initializing VAD (Silero)...")
        vad = silero.VAD.load()
        logger.info("✓ VAD component ready")

        logger.info("Initializing Moss client and loading index...")
        moss_client = MossClient(
            os.environ["MOSS_PROJECT_ID"], os.environ["MOSS_PROJECT_KEY"]
        )
        await moss_client.load_index(settings.moss.index_name)
        logger.info("✓ Moss client and index ready")

        logger.info("All components verified and ready")
        return {
            "stt": stt,
            "llm": llm,
            "tts": tts,
            "vad": vad,
            "moss_client": moss_client,
        }

    except Exception as e:
        logger.error(f"Component verification failed: {e}", exc_info=True)
        return None


async def create_readiness_marker() -> Optional[Dict[str, Any]]:
    """
    Create a readiness marker file *after* all components are verified.
    """
    components = await verify_components_ready()
    ready_path = Path("/tmp/agent_ready")

    if components:
        ready_path.touch()
        logger.info("Agent fully ready - all components loaded and verified")
        return components
    else:
        logger.error("Agent not ready - component loading failed")
        if ready_path.exists():
            ready_path.unlink()
            logger.info("Removed readiness marker due to component failure")
        return None


# --- 4. Agent Definition ---

class Assistant(Agent):
    """
    Customer support voice agent powered by the Moss FAQ index.
    """

    def __init__(self, moss_client: MossClient, room: rtc.Room):
        super().__init__(instructions=settings.instructions)
        self._moss_config = settings.moss
        self._moss_client = moss_client
        self._room = room  # Store the room object for data channel access
        self._moss_index_loaded = True
        logger.info("Assistant agent initialized with Moss client.")

    @function_tool
    async def search_support_faqs(self, context: RunContext, question: str) -> str:
        """
        Retrieve relevant FAQ answers using Moss semantic search.
        This tool is called by the LLM when it detects a support question.
        """
        query = question.strip()
        if not query:
            logger.warning("FAQ search called with an empty question.")
            return "No question provided for FAQ search."

        logger.info("Received support query: %s", query)

        try:
            results = await self._moss_client.query(
                self._moss_config.index_name,
                query,
                self._moss_config.top_k_results,
            )
        except Exception as e:
            logger.error(f"Moss query failed: {e}", exc_info=True)
            return "Sorry, I encountered an error trying to search our support articles."

        time_taken_ms = getattr(results, "time_taken_ms", 0)
        docs = list(getattr(results, "docs", []) or [])

        logger.info("Moss query completed in %sms, found %d matches", time_taken_ms, len(docs))

        # --- Send Moss Metrics ---
        await self._send_moss_metrics(query, time_taken_ms, len(docs))

        if not docs:
            logger.info("No FAQ matches returned for query: %s", query)
            summary = "No relevant FAQ matches were found for your question."
        else:
            match_texts = [(doc.text or "").strip() for doc in docs]
            summary = "\n\n".join(match_texts)
            logger.debug("Top Moss matches for %r:\n%s", query, summary)

        # Add the search result to context for the LLM
        context.session.history.add_message(
            role="system",
            content="FAQ search context for the current user request:\n" + summary,
            created_at=datetime.utcnow().timestamp(),
        )

        return summary

    async def _send_moss_metrics(
        self, query: str, time_taken_ms: float, num_matches: int
    ):
        """Helper to send Moss query metrics over the data channel."""
        try:
            payload = {
                "type": "moss",
                "data": {
                    "time_taken_ms": time_taken_ms,
                    "query": query,
                    "num_matches": num_matches,
                },
            }
            json_payload = json.dumps(payload).encode("utf-8")
            await self._room.local_participant.publish_data(
                payload=json_payload,
                reliable=True,
            )
        except Exception as e:
            logger.error(f"Failed to send Moss metrics: {e}")


# --- 5. Metrics Handling ---

async def _send_metrics_task(ev: MetricsCollectedEvent, room: rtc.Room):
    """
    Asynchronous task to process and send pipeline metrics
    over the data channel.
    """
    data = ev.metrics
    payload = {"type": "", "data": {}}

    try:
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
            return  # Skip other metric types (e.g., VADMetrics)

        # Send payload over data channel
        json_payload = json.dumps(payload).encode("utf-8")
        await room.local_participant.publish_data(
            payload=json_payload,
            reliable=True,
        )
        # logger.debug(f"Sent metrics packet: {payload['type']}")

    except Exception as e:
        logger.error(f"Failed to process/send metrics data: {e}")


# --- 6. Agent Entrypoint ---

async def entrypoint(ctx: agents.JobContext):
    """
    Main entry point for the agent worker.
    """
    logger.info("Agent entrypoint starting...")

    # Verify components and create readiness marker
    components = await create_readiness_marker()
    if not components:
        logger.critical("Failed to initialize components, agent cannot start")
        return

    # Configure the voice pipeline session
    session = AgentSession(
        stt=components["stt"],
        llm=components["llm"],
        tts=components["tts"],
        vad=components["vad"],
    )

    # --- Metrics Integration ---
    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        """Synchronous callback to log and schedule async sending."""
        # 1. Log metrics locally
        metrics.log_metrics(ev.metrics)
        # 2. Schedule the async task to send metrics over data channel
        asyncio.create_task(_send_metrics_task(ev, ctx.room))

    # --- Start Agent Session ---
    try:
        logger.info("Starting agent session...")
        await session.start(
            room=ctx.room,
            # Pass the Moss client and room object to the agent
            agent=Assistant(components["moss_client"], ctx.room),
        )
        logger.info("Agent session finished successfully")

    except Exception as e:
        logger.error(f"Agent session error: {e}", exc_info=True)
        raise
    finally:
        logger.info("Agent session ended, worker ready for next connection")


# --- 7. Main Execution ---

if __name__ == "__main__":
    logging.info("Starting LiveKit Agent worker...")
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))