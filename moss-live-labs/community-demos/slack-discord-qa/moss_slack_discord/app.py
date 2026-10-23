"""Application wiring for the Slack and Discord Moss Q&A demo."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from dotenv import load_dotenv

from .adapters import run_discord, run_slack
from .qa_engine import AnswerEngine, RetrievedDocument


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


class MossRetriever:
    """Adapt MossClient.query to the shared Retriever protocol."""

    def __init__(self, client: Any, index_name: str, query_options_type: Any) -> None:
        self.client = client
        self.index_name = index_name
        self.query_options_type = query_options_type

    async def retrieve(self, question: str, top_k: int) -> list[RetrievedDocument]:
        results = await self.client.query(
            self.index_name,
            question,
            self.query_options_type(top_k=top_k),
        )
        return [
            RetrievedDocument(text=document.text, score=document.score)
            for document in results.docs
            if document.text
        ]


class OpenAIResponder:
    """Generate a concise answer from the Moss context using OpenAI's async client."""

    def __init__(self, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    async def respond(self, question: str, context: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You answer workspace questions using only the supplied context. "
                        "If the context does not contain the answer, say that you do not know. "
                        "Keep the response concise and do not mention the retrieval process."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nQuestion: {question}",
                },
            ],
        )
        return response.choices[0].message.content or ""


async def build_answer_engine() -> AnswerEngine:
    """Load the configured Moss index and create the shared answer engine."""
    from moss import MossClient, QueryOptions
    from openai import AsyncOpenAI

    moss_client = MossClient(
        require_env("MOSS_PROJECT_ID"), require_env("MOSS_PROJECT_KEY")
    )
    index_name = require_env("MOSS_INDEX_NAME")
    await moss_client.load_index(index_name)

    return AnswerEngine(
        retriever=MossRetriever(moss_client, index_name, QueryOptions),
        responder=OpenAIResponder(
            AsyncOpenAI(api_key=require_env("OPENAI_API_KEY")),
            os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        ),
        top_k=int(os.getenv("MOSS_TOP_K", "5")),
    )


async def run() -> None:
    load_dotenv()
    engine = await build_answer_engine()
    tasks = []

    slack_bot_token = os.getenv("SLACK_BOT_TOKEN")
    slack_app_token = os.getenv("SLACK_APP_TOKEN")
    if slack_bot_token or slack_app_token:
        if not slack_bot_token or not slack_app_token:
            raise RuntimeError(
                "SLACK_BOT_TOKEN and SLACK_APP_TOKEN must be set together"
            )
        tasks.append(run_slack(engine, slack_bot_token, slack_app_token))

    discord_token = os.getenv("DISCORD_TOKEN")
    if discord_token:
        tasks.append(
            run_discord(engine, discord_token, os.getenv("DISCORD_PREFIX", "!ask"))
        )

    if not tasks:
        raise RuntimeError("Configure at least one adapter: Slack or Discord")
    await asyncio.gather(*tasks)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
