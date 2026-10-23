"""Slack and Discord event adapters for the shared Q&A engine."""

from __future__ import annotations

import re

from .qa_engine import AnswerEngine


def extract_slack_question(text: str) -> str:
    """Remove the leading bot mention from an app mention event."""
    return re.sub(r"^\s*<@[^>]+>\s*", "", text).strip()


def extract_discord_question(
    content: str, bot_user_id: int | None, prefix: str
) -> str | None:
    """Return a question only when a Discord message mentions the bot or uses the prefix."""
    question = content.strip()
    prefix_lower = prefix.lower()
    if question.lower().startswith(prefix_lower):
        return question[len(prefix) :].strip()

    if bot_user_id is None:
        return None

    mention_patterns = (f"<@{bot_user_id}>", f"<@!{bot_user_id}>")
    for mention in mention_patterns:
        if mention in question:
            return question.replace(mention, "", 1).strip()
    return None


async def run_slack(engine: AnswerEngine, bot_token: str, app_token: str) -> None:
    """Run a Slack Socket Mode adapter that answers app mentions in threads."""
    from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
    from slack_bolt.async_app import AsyncApp

    app = AsyncApp(token=bot_token)

    @app.event("app_mention")
    async def handle_app_mention(body, say, logger) -> None:
        event = body.get("event", {})
        question = extract_slack_question(event.get("text", ""))
        thread_ts = event.get("thread_ts") or event.get("ts")
        if not question:
            await say(
                "Please include a question after mentioning me.", thread_ts=thread_ts
            )
            return

        try:
            answer = await engine.answer(question)
        except Exception:
            logger.exception("Failed to answer Slack question")
            answer = "I couldn't answer that right now. Please try again."
        await say(answer, thread_ts=thread_ts)

    handler = AsyncSocketModeHandler(app, app_token)
    await handler.start_async()


async def run_discord(engine: AnswerEngine, token: str, prefix: str) -> None:
    """Run a Discord adapter that answers mentions and prefixed questions."""
    import discord

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return

        bot_user_id = client.user.id if client.user else None
        question = extract_discord_question(message.content, bot_user_id, prefix)
        if question is None:
            return
        if not question:
            await message.reply(
                "Please include a question after mentioning me.", mention_author=False
            )
            return

        async with message.channel.typing():
            try:
                answer = await engine.answer(question)
            except Exception:
                answer = "I couldn't answer that right now. Please try again."
        await message.reply(answer, mention_author=False)

    await client.start(token)
