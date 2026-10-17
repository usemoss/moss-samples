# Imports and setup
import logging
import os

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
    function_tool,
)
from livekit.plugins import cartesia, deepgram, google, silero
from moss import MossClient, QueryOptions

load_dotenv()

MOSS_PROJECT_ID = os.getenv("MOSS_PROJECT_ID")
MOSS_PROJECT_KEY = os.getenv("MOSS_PROJECT_KEY")
# PERSONA: update the default index name to match your knowledge base
INDEX_NAME = os.getenv("MOSS_INDEX_NAME", "Harry-Potter-Persona")


logging.getLogger("livekit").setLevel(logging.WARNING)
logging.getLogger("livekit.agents").setLevel(logging.WARNING)
logger = logging.getLogger("moss-agent")
logger.setLevel(logging.INFO)

CYAN  = "\033[96m"
GREEN = "\033[92m"
RESET = "\033[0m"

# Class definition for the agent. 
class HarryPotterAgent(Agent):

    def __init__(self, moss_client: MossClient):
        self.moss = moss_client

        @function_tool
        async def search_knowledge(query: str) -> str:
            """
            Search Harry Potter's personal knowledge base.
            Call this whenever the user asks about Harry Potter's background, experience,
            education, skills, adventures, contact info, or anything personal about him.

            Args:
                query: The question or topic to look up.
            """
            # PERSONA: update the docstring above to describe your new persona's knowledge base
            logger.info(f"{CYAN}Moss query:{RESET} {query}")
            try:
                results = await moss_client.query(
                    INDEX_NAME,
                    query,
                    QueryOptions(top_k=5, alpha=0.8),
                )
                if not results.docs:
                    return "No relevant information found in the knowledge base."
                logger.info(f"{GREEN}Moss returned {len(results.docs)} results in {results.time_taken_ms}ms{RESET}")
                for i, doc in enumerate(results.docs, 1):
                    preview = doc.text[:120] + "..." if len(doc.text) > 120 else doc.text
                    logger.info(f"{GREEN}  [{i}] {preview}{RESET}")
                return "\n".join([f"- {d.text}" for d in results.docs])
            except Exception as e:
                logger.error(f"Moss search failed: {e}", exc_info=True)
                return "Knowledge base search failed. Please try rephrasing your question."

        super().__init__(
            # PERSONA: replace the instructions and greeting below with your new persona
            instructions="""
                You are a voice assistant speaking on behalf of Harry Potter.
                Refer to Harry Potter in the third person — use "he", "him", and "Harry" when answering.

                You have a tool called search_knowledge. Use it to look up anything about
                Harry Potter before answering questions about his background, experience, skills,
                education, adventures, or contact details. Always call the tool first — never guess.

                Keep responses concise and conversational — this is a voice interface.
                If the knowledge base doesn't have enough information, say so honestly.
            """,
            tools=[search_knowledge],
        )

    async def on_enter(self):
        await self.session.say(
            "Hello! I am speaking on behalf of Harry Potter. He would have joined us himself, but apparently phone calls are not taught at Hogwarts. Ask me anything about him.")


async def entrypoint(ctx: JobContext):
    await ctx.connect()

# ===================== Moss client setup and index loading =====================
    moss_client = MossClient(project_id=MOSS_PROJECT_ID, project_key=MOSS_PROJECT_KEY)

    try:
        await moss_client.load_index(INDEX_NAME)
        logger.info(f"Loaded Moss index: {INDEX_NAME}")
    except Exception as e:
        logger.warning(f"Failed to load index '{INDEX_NAME}': {e}")
        logger.warning("Run create_index.py first to populate the index.")

# ===================== Agent session setup and start =====================

    session = AgentSession(
        stt=deepgram.STT(),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=cartesia.TTS(model="sonic-3-2026-01-12", voice="63ff761f-c1e8-414b-b969-d1833d1c870c"),
        vad=silero.VAD.load(),
        turn_handling={"interruption": {"mode": "vad"}},
    )

    await session.start(
        agent=HarryPotterAgent(moss_client),
        room=ctx.room,
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
