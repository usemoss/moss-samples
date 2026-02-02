"""
LiveKit Voice Agent - Quick Start
==================================
The simplest possible LiveKit voice agent to get you started.
Requires only OpenAI and Deepgram API keys.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from inferedge_moss import MossClient
from livekit import agents, rtc
from livekit.agents import Agent, AgentSession, ChatMessage, ChatRole, RunContext
from livekit.agents.llm import ChatChunk, function_tool
from livekit.plugins import cartesia, deepgram, openai, silero  # type: ignore

# Load environment variables
load_dotenv(".env.local")


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

    def __init__(self, room: Optional[rtc.Room] = None):
        super().__init__(
            instructions="""You are a warm, professional customer support agent for our ecommerce help desk.
            Call `search_support_faqs` BEFORE crafting your answer so your reply is grounded.
            Use retrieved FAQ snippets to produce concise, empathetic, action-oriented responses, not bullet points; acknowledge when information isn't available."""
        )

        project_id = os.environ["MOSS_PROJECT_ID"]
        project_key = os.environ["MOSS_PROJECT_KEY"]
        self._moss_index_name = os.environ["MOSS_INDEX_NAME"]
        self._moss_client = MossClient(project_id, project_key)
        self._moss_index_loaded = False
        self._room = room

    async def on_enter(self) -> None:
        await super().on_enter()
        if self._moss_index_loaded:
            return

        try:
            logger.info("Preloading Moss index '%s' during session start", self._moss_index_name)
            await self._moss_client.load_index(self._moss_index_name)
            self._moss_index_loaded = True
            logger.info("Moss index '%s' ready", self._moss_index_name)
        except Exception:
            logger.exception("Failed to preload Moss index '%s'", self._moss_index_name)
            # Leave `_moss_index_loaded` as-is; the tool method will attempt again on demand.

    def llm_node(
        self,
        chat_ctx,
        tools,
        model_settings,
    ):
        async def _generator():
            collected_parts: list[str] = []
            usage_details = None
            async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
                if isinstance(chunk, str):
                    collected_parts.append(chunk)
                    yield chunk
                    continue

                if isinstance(chunk, ChatChunk):
                    delta = getattr(chunk, "delta", None)
                    if delta and getattr(delta, "content", None):
                        collected_parts.append(delta.content)
                    usage = getattr(chunk, "usage", None)
                    if usage:
                        usage_details = usage

                yield chunk

            full_text = "".join(collected_parts).strip()
            if full_text:
                logger.info("LLM response: %s", full_text)

            if usage_details:
                usage_source = usage_details
                for attr_name in ("model_dump", "dict", "to_dict"):
                    method = getattr(usage_source, attr_name, None)
                    if callable(method):
                        try:
                            usage_source = method()
                            break
                        except TypeError:
                            continue

                if hasattr(usage_source, "__dict__") and not isinstance(usage_source, dict):
                    usage_source = usage_source.__dict__

                def _extract(keys: tuple[str, ...]) -> int | None:
                    for key in keys:
                        if isinstance(usage_source, dict) and key in usage_source:
                            try:
                                return int(usage_source[key])
                            except (TypeError, ValueError):
                                continue
                        if hasattr(usage_source, key):
                            try:
                                return int(getattr(usage_source, key))
                            except (TypeError, ValueError):
                                continue
                    return None

                prompt_tokens = _extract(("prompt_tokens", "input_tokens", "prompt"))
                completion_tokens = _extract(("completion_tokens", "output_tokens", "completion"))
                total_tokens = _extract(("total_tokens", "total"))

                if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
                    total_tokens = prompt_tokens + completion_tokens

                if any(value is not None for value in (prompt_tokens, completion_tokens, total_tokens)):
                    try:
                        logger.info(
                            "LLM usage tokens — prompt: %s, completion: %s, total: %s",
                            prompt_tokens,
                            completion_tokens,
                            total_tokens,
                        )
                    except Exception:
                        logger.debug("Unable to log LLM usage tokens", exc_info=True)

                    if self._room:
                        try:
                            model_name = None
                            for attr in ("model", "name", "id"):
                                if hasattr(model_settings, attr):
                                    model_name = getattr(model_settings, attr)
                                    if model_name:
                                        break

                            timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                            payload = {
                                "type": "llm_usage",
                                "data": {
                                    "model": model_name,
                                    "prompt_tokens": prompt_tokens,
                                    "completion_tokens": completion_tokens,
                                    "total_tokens": total_tokens,
                                    "timestamp": timestamp_ms,
                                },
                            }
                            encoded = json.dumps(payload, default=str).encode("utf-8")
                            await self._room.local_participant.publish_data(
                                payload=encoded,
                                reliable=True,
                            )
                        except Exception:
                            logger.exception("Failed to publish LLM usage data")

        return _generator()

    @function_tool
    async def search_support_faqs(self, context: RunContext, question: str) -> str:
        """Retrieve relevant FAQ answers using Moss semantic search."""

        query = question.strip()
        if not query:
            return "No question provided for FAQ search."

        logger.info("Received support query: %s", query)

        # --- Early history-based skip: ensure at least one real user message exists ---
        # If there is no prior user message, we treat this as an initial assistant self-prompt or greeting classification.
        history = getattr(context.session, "history", None)
        chat_items = list(getattr(history, "items", [])) if history else []
        user_role: ChatRole = "user"

        def _message_text(message: ChatMessage) -> str:
            if message.text_content:
                return message.text_content
            parts = [part for part in getattr(message, "content", []) if isinstance(part, str)]
            return "\n".join(parts)

        has_user_message = False
        for item in reversed(chat_items):
            if isinstance(item, ChatMessage) and item.role == user_role:
                if _message_text(item).strip():
                    has_user_message = True
                break

        if not has_user_message:
            summary = "(No user query yet – skipped FAQ search.)"
            logger.info("Skipping Moss search: no prior user message present.")
            if history:
                history.add_message(
                    role="system",
                    content="FAQ search context for the current user request:\n" + summary,
                    created_at=datetime.now(timezone.utc).timestamp(),
                )
            return summary

        results = await self._moss_client.query(self._moss_index_name, query, top_k=3)
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

        if history:
            history.add_message(
                role="system",
                content="FAQ search context for the current user request:\n" + summary,
                created_at=datetime.now(timezone.utc).timestamp(),
            )

        if self._room:
            try:
                matches = []
                for doc in docs:
                    text = (doc.text or "").strip()
                    match_entry = {"text": text}
                    score = getattr(doc, "score", None)
                    if score is None:
                        score = getattr(doc, "similarity", None)
                    if score is not None:
                        try:
                            match_entry["score"] = float(score)
                        except (TypeError, ValueError):
                            pass
                    metadata = getattr(doc, "metadata", None)
                    if metadata:
                        match_entry["metadata"] = metadata
                    matches.append(match_entry)

                payload = {
                    "type": "moss_context",
                    "data": {
                        "query": query,
                        "matches": matches,
                        "time_taken_ms": getattr(results, "time_taken_ms", None),
                        "timestamp": datetime.now(timezone.utc).timestamp(),
                    },
                }
                encoded = json.dumps(payload, default=str).encode("utf-8")
                await self._room.local_participant.publish_data(payload=encoded, reliable=True)
            except Exception:
                logger.exception("Failed to publish Moss context data")

        return summary

async def entrypoint(ctx: agents.JobContext):
    """Entry point for the agent."""

    # Configure the voice pipeline with the essentials
    # You can adjust the STT, LLM and TTS settings as needed
    session: AgentSession = AgentSession(
        stt=deepgram.STT(model="nova-2"),
        llm=openai.LLM(
            model="gpt-5",
        ),
        tts=cartesia.TTS(
            model="sonic-2",
            voice="f786b574-daa5-4673-aa0c-cbe3e8534c02",
        ),
        vad=silero.VAD.load(),
    )

    # Start the session
    room = getattr(ctx, "room", None)

    await session.start(
        room=room,  # type: ignore
        agent=Assistant(room=room)  # type: ignore
    )

    # Generate initial greeting
    await session.generate_reply(
        instructions="Greet the user warmly and ask how you can help."
    )

if __name__ == "__main__":
    # Run the agent
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
