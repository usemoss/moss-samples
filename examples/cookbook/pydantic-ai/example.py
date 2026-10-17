from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from moss import DocumentInfo, MossClient
from moss_pydantic_ai import MossSearchTool
from pydantic_ai import Agent


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


async def _ensure_demo_index(client: MossClient, index_name: str) -> None:
    """Create a small demo index if it does not already exist."""
    existing_indexes = await client.list_indexes()
    if any(index.name == index_name for index in existing_indexes):
        return

    docs = [
        DocumentInfo(
            id="reset-password",
            text=(
                "To reset your password, go to Settings > Security, choose Reset "
                "Password, and follow the email verification link."
            ),
        ),
        DocumentInfo(
            id="refund-policy",
            text="Refunds are processed within 3-5 business days after approval.",
        ),
        DocumentInfo(
            id="support-hours",
            text="Customer support is available Monday to Friday, 9 AM to 6 PM IST.",
        ),
    ]
    await client.create_index(index_name, docs)


async def main() -> None:
    """Run the cookbook example using the Moss-backed search tool."""
    load_dotenv()

    client = MossClient(
        _require_env("MOSS_PROJECT_ID"),
        _require_env("MOSS_PROJECT_KEY"),
    )
    index_name = _require_env("MOSS_INDEX_NAME")
    await _ensure_demo_index(client, index_name)
    moss = MossSearchTool(
        client=client,
        index_name=index_name,
    )
    await moss.load_index()

    agent = Agent(
        _require_env("PYDANTIC_AI_MODEL"),
        system_prompt=(
            "Answer user questions with the help of Moss search when "
            "factual lookup from the knowledge base is needed."
        ),
        tools=[moss.tool],
    )

    question = os.getenv(
        "PYDANTIC_AI_PROMPT",
        "How to reset password?",
    )
    result = await agent.run(question)
    print(result.output)


if __name__ == "__main__":
    asyncio.run(main())
