import logging
import os

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    ChatContext,
    ChatMessage,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.plugins import cartesia, deepgram, openai, silero

# Moss Import
from moss import MossClient, QueryOptions

load_dotenv()

# Configuration
MOSS_PROJECT_ID = os.getenv("MOSS_PROJECT_ID")
MOSS_PROJECT_KEY = os.getenv("MOSS_PROJECT_KEY")
INDEX_NAME = os.getenv("MOSS_INDEX_NAME", "demo-customer_faqs")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("moss-agent")

class MossSemanticRetrievalAgent(Agent):

    def __init__(self, moss_client: MossClient):
        super().__init__(
            instructions="""
                You are a helpful customer support voice assistant.
                You have access to a knowledge base which will be provided to you as context.
                Always answer the user's question based on the provided context.
                If the context doesn't contain the answer, politely say you don't know.
            """
        )
        self.moss = moss_client

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        """
        Intercept user message -> Search Moss -> Inject Context -> Continue
        """
        user_query = new_message.text_content
        logger.info(f"User asked: {user_query}")

        try:
            # 1. Automatic Search 
            results = await self.moss.query(
                INDEX_NAME,
                user_query,
                QueryOptions(top_k=5, alpha=0.8)
            )
            
            # 2. Context Injection
            if results.docs:
                context_str = "\n".join([f"- {d.text}" for d in results.docs])
                injection = f"Relevant context from knowledge base:\n{context_str}\n\nUse this to answer the user."
                
                # Insert into chat history as a system message
                turn_ctx.add_message(role="system", content=injection)
                logger.info(f"Injected context: {context_str[:100]}...")  # Log first 100 chars
            else:
                logger.info("No relevant context found in Moss index")
                
        except Exception as e:
            logger.error(f"Moss search failed: {e}", exc_info=True)

        # 3. Proceed with standard generation
        await super().on_user_turn_completed(turn_ctx, new_message)


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    # Initialize Moss
    moss_client = MossClient(project_id=MOSS_PROJECT_ID, project_key=MOSS_PROJECT_KEY)
    
    # Pre-load index
    try:
        await moss_client.load_index(INDEX_NAME)
        logger.info(f"Successfully loaded index: {INDEX_NAME}")
    except Exception as e:
        logger.warning(f"Index not found or failed to load: {e}")
        logger.warning("Moss queries will fail until the index is created. Run upload.py first.")

    # Create Session
    session = AgentSession(
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4o"),
        tts=cartesia.TTS(model="sonic-3-2026-01-12"),
        vad=silero.VAD.load(),
        turn_handling={"interruption": {"mode": "vad"}},
    )

    # Start the session with our custom MossSemanticRetrievalAgent
    await session.start(
        agent=MossSemanticRetrievalAgent(moss_client),
        room=ctx.room,
    )

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))