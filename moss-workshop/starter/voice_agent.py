"""Moss + LiveKit voice agent, using both Moss primitives.

    python build_index.py            # create the FAQ index (once)
    python voice_agent.py console    # talk to it in the terminal

  - MossClient: the FAQ cloud index (long-term knowledge), loaded into memory.
  - SessionIndex: a live session that indexes each turn so the agent can recall
    what was said earlier, then pushes to the cloud when the call ends.
Both query in-process, under 10 ms.
"""
import os

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    ChatContext,
    ChatMessage,
    JobContext,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
)
from livekit.plugins import deepgram, openai, silero
from moss import DocumentInfo, MossClient, QueryOptions

load_dotenv()
INDEX = os.getenv("MOSS_INDEX_NAME", "hackathon")


class HackathonAgent(Agent):
    def __init__(self, moss: MossClient, moss_session):
        super().__init__(instructions=(
            "You are the helper agent for Agents Hack Day at Bright Data (Moss is the "
            "official partner). Answer in at most two short sentences, conversationally. "
            "Call search_hackathon for facts about the event, and recall_conversation for "
            "what the user said earlier. If it is not covered, say so briefly and point "
            "them to the Moss table."
        ))
        self.moss = moss
        self.moss_session = moss_session  # SessionIndex: this call's live memory (Agent.session is reserved)
        self._turn = 0

    @function_tool
    async def search_hackathon(self, context: RunContext, query: str) -> str:
        """Search the hack-day knowledge base (schedule, what to build, logistics, how to use Moss)."""
        res = await self.moss.query(INDEX, query, QueryOptions(top_k=4))
        return "\n".join(f"- {d.text}" for d in res.docs) or "No matching info found."

    @function_tool
    async def recall_conversation(self, context: RunContext, query: str) -> str:
        """Recall something the user said earlier in this call."""
        res = await self.moss_session.query(query, QueryOptions(top_k=3))
        return "\n".join(f"- {d.text}" for d in res.docs) or "Nothing relevant earlier."

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        # Index each turn into the session locally (no network) so it can be recalled later.
        self._turn += 1
        await self.moss_session.add_docs([DocumentInfo(id=f"turn-{self._turn}", text=new_message.text_content)])
        await super().on_user_turn_completed(turn_ctx, new_message)


async def entrypoint(ctx: JobContext):
    await ctx.connect()
    moss = MossClient(os.environ["MOSS_PROJECT_ID"], os.environ["MOSS_PROJECT_KEY"])

    await moss.load_index(INDEX)                              # long-term: FAQ (run build_index.py first)
    session = await moss.session(index_name=f"call-{ctx.room.name}")  # short-term: live session
    ctx.add_shutdown_callback(lambda: session.push_index())   # persist for handoff at call end

    agent_session = AgentSession(
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=openai.TTS(),
        vad=silero.VAD.load(),
    )
    await agent_session.start(agent=HackathonAgent(moss, session), room=ctx.room)
    await agent_session.generate_reply(        # agent speaks first
        instructions="Greet the user in one sentence and invite a question about the hack day or building with Moss."
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
