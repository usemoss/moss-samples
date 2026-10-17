from __future__ import annotations

import asyncio
import os
from typing import Any

from dotenv import load_dotenv
from moss import DocumentInfo, MossClient
from moss_smolagents import MossSearchTool
from smolagents import CodeAgent


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

    print(f"Creating demo index '{index_name}'...")
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
    print("Demo index created successfully.")


def _initialize_model() -> Any:
    """Initialize a model for smolagents based on available environment variables."""
    # 1. Hugging Face Inference API
    if hf_token := os.getenv("HUGGING_FACE_HUB_TOKEN"):
        from smolagents import HfApiModel

        print("Using Hugging Face HfApiModel...")
        return HfApiModel(token=hf_token)

    # 2. OpenAI API
    if openai_key := os.getenv("OPENAI_API_KEY"):
        from smolagents import OpenAIServerModel

        print("Using OpenAI OpenAIServerModel (gpt-4o-mini)...")
        return OpenAIServerModel(model_id="gpt-4o-mini", api_key=openai_key)

    # 3. Gemini API (using OpenAI compatibility layer or LiteLLM if available)
    if gemini_key := os.getenv("GEMINI_API_KEY"):
        try:
            from smolagents import LiteLLMModel

            print("Using Gemini LiteLLMModel (gemini/gemini-2.5-flash)...")
            return LiteLLMModel(
                model_id="gemini/gemini-2.5-flash", api_key=gemini_key
            )
        except ImportError:
            from smolagents import OpenAIServerModel

            print("Using Gemini OpenAIServerModel (gemini-2.5-flash)...")
            return OpenAIServerModel(
                model_id="gemini-2.5-flash",
                api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=gemini_key,
            )

    raise RuntimeError(
        "No model credentials found. Please define one of the following in your .env file:\n"
        "  - HUGGING_FACE_HUB_TOKEN\n"
        "  - OPENAI_API_KEY\n"
        "  - GEMINI_API_KEY"
    )


async def main() -> None:
    """Run the cookbook demo."""
    load_dotenv()

    # Initialize Moss Client and ensure demo index exists
    client = MossClient(
        _require_env("MOSS_PROJECT_ID"),
        _require_env("MOSS_PROJECT_KEY"),
    )
    index_name = _require_env("MOSS_INDEX_NAME")

    await _ensure_demo_index(client, index_name)

    # Initialize the Moss search tool and pre-load index
    moss_tool = MossSearchTool(client=client, index_name=index_name)

    print(f"Pre-loading Moss index '{index_name}' into memory...")
    await moss_tool.load_index()
    print("Moss index pre-loaded successfully.")

    # Initialize model and agent
    model = _initialize_model()
    agent = CodeAgent(
        tools=[moss_tool],
        model=model,
    )

    # Execute a query
    prompt = os.getenv(
        "SMOLAGENTS_PROMPT",
        "How do I reset my password? Summarize the steps.",
    )
    print(f"\nRunning task: '{prompt}'\n")

    result = agent.run(prompt)
    print("\n--- Agent Result ---")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
