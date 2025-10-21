"""
LiveKit Voice Agent - Quick Start
==================================
The simplest possible LiveKit voice agent to get you started.
Requires only OpenAI and Deepgram API keys.
"""

import logging
import os
from datetime import datetime
from typing import List

from dotenv import load_dotenv
from inferedge_moss import MossClient
from livekit import agents
from livekit.agents import Agent, AgentSession, RunContext
from livekit.agents.llm import function_tool
from livekit.plugins import deepgram, openai, silero, cartesia

from settings import get_settings

# Load environment variables
load_dotenv(".env")

# Get configuration settings
settings = get_settings()


logger = logging.getLogger("livekit_agent.moss")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


class Assistant(Agent):
    """Customer support voice agent powered by the Moss FAQ index."""

    def __init__(self):
        super().__init__(
            instructions=settings.instructions
        )

        self._moss_config = settings.moss
        self._moss_client = MossClient(
            os.environ["MOSS_PROJECT_ID"],
            os.environ["MOSS_PROJECT_KEY"]
        )
        self._moss_index_loaded = False

    @function_tool
    async def search_support_faqs(self, context: RunContext, question: str) -> str:
        """Retrieve relevant FAQ answers using Moss semantic search."""

        query = question.strip()
        if not query:
            return "No question provided for FAQ search."

        logger.info("Received support query: %s", query)

        if not self._moss_index_loaded:
            logger.info("Loading Moss index '%s'", self._moss_config.index_name)
            await self._moss_client.load_index(self._moss_config.index_name)
            self._moss_index_loaded = True

        results = await self._moss_client.query(
            self._moss_config.index_name,
            query,
            self._moss_config.top_k_results
        )
        logger.info(
            "Moss query completed in %sms", getattr(results, "time_taken_ms", "?")
        )

        docs = list(getattr(results, "docs", []) or [])
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

    # Configure the voice pipeline using settings
    session = AgentSession(
        stt=deepgram.STT(
            model=settings.stt.model,
            language=settings.stt.language
        ),
        llm=openai.LLM(
            model=settings.llm.model,
            temperature=settings.llm.temperature
        ),
        tts=cartesia.TTS(
            model=settings.tts.model,
            voice=settings.tts.voice,
            speed=settings.tts.speed
        ),
        vad=silero.VAD.load(),
    )

    # Start the session
    await session.start(
        room=ctx.room,
        agent=Assistant()
    )

    # Generate initial greeting
    await session.generate_reply(
        instructions=settings.initial_greeting_instructions
    )

if __name__ == "__main__":
    # Run the agent
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))