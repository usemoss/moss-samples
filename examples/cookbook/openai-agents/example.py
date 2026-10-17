import asyncio
import json
import os
from typing import Any

from agents import Agent, Runner, function_tool
from dotenv import load_dotenv
from moss import DocumentInfo, MossClient, QueryOptions

DEFAULT_TOP_K = 3
MAX_TOP_K = 20
REQUIRED_ENV_VARS = (
    "MOSS_PROJECT_ID",
    "MOSS_PROJECT_KEY",
    "MOSS_INDEX_NAME",
    "OPENAI_API_KEY",
)


def _require_env_vars(names: tuple[str, ...] = REQUIRED_ENV_VARS) -> dict[str, str]:
    """Return required environment variables or raise a clear setup error."""
    values = {name: os.getenv(name) for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing)
        )
    return {name: value for name, value in values.items() if value is not None}


def _validate_top_k(top_k: int) -> int:
    """Keep cookbook retrieval bounds simple and explicit."""
    if not isinstance(top_k, int) or isinstance(top_k, bool):
        raise ValueError("top_k must be an integer.")
    if top_k < 1 or top_k > MAX_TOP_K:
        raise ValueError(f"top_k must be between 1 and {MAX_TOP_K}.")
    return top_k


async def _ensure_demo_index(client: MossClient, index_name: str) -> None:
    """Create a small demo index if it does not already exist."""
    existing_indexes = await client.list_indexes()
    if any(index.name == index_name for index in existing_indexes):
        print(f"Index '{index_name}' already exists. Skipping creation.")
        return

    docs = [
        DocumentInfo(
            id="reset-password",
            text=(
                "To reset your password, go to Settings > Security, choose Reset "
                "Password, and follow the email verification link."
            ),
            metadata={"category": "account", "region": "global"},
        ),
        DocumentInfo(
            id="refund-policy",
            text="Refunds are processed within 3-5 business days after approval.",
            metadata={"category": "policy", "region": "global"},
        ),
        DocumentInfo(
            id="support-hours",
            text="Customer support is available Monday to Friday, 9 AM to 6 PM IST.",
            metadata={"category": "support", "region": "in"},
        ),
    ]
    await client.create_index(index_name, docs)


def _format_search_results(query: str, docs: list[Any]) -> str:
    """Return structured tool output that an agent can cite and reason over."""
    if not docs:
        return json.dumps(
            {
                "query": query,
                "message": "No relevant results found.",
                "results": [],
            },
            indent=2,
        )

    results = []
    for doc in docs:
        results.append(
            {
                "id": getattr(doc, "id", ""),
                "text": getattr(doc, "text", ""),
                "score": getattr(doc, "score", None),
                "metadata": getattr(doc, "metadata", None) or {},
            }
        )
    return json.dumps({"query": query, "results": results}, indent=2)


async def search_moss(
    client: MossClient,
    index_name: str,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    filter: dict[str, Any] | None = None,
) -> str:
    """Query Moss and format results for the OpenAI agent."""
    top_k = _validate_top_k(top_k)
    result = await client.query(
        index_name,
        query,
        options=QueryOptions(top_k=top_k, filter=filter),
    )
    return _format_search_results(query, result.docs)


def create_moss_search_tool(client: MossClient, index_name: str) -> Any:
    """Create the OpenAI Agents SDK function tool backed by Moss."""

    @function_tool
    async def moss_search(
        query: str,
        top_k: int = DEFAULT_TOP_K,
        filter: dict[str, Any] | None = None,
    ) -> str:
        """Search the knowledge base for answers to the user's question.

        Args:
            query: Natural-language search query.
            top_k: Number of Moss results to return. Use 1-20.
            filter: Optional Moss metadata filter, such as
                {"field": "category", "condition": {"$eq": "policy"}}.
        """
        print(f"[Tool Triggered] Searching Moss for: '{query}'")
        return await search_moss(client, index_name, query, top_k, filter)

    return moss_search


async def run_agent(client: MossClient, index_name: str, question: str) -> Any:
    """Load the local index, create the agent, and run the user question."""
    print(f"Pre-loading index '{index_name}' into Moss local runtime...")
    await client.load_index(index_name)

    moss_search = create_moss_search_tool(client, index_name)

    agent = Agent(
        name="Support Assistant",
        instructions=(
            "You are a helpful customer support assistant. "
            "Use the moss_search tool to look up information before answering. "
            "Ground your response in the retrieved documents and mention when "
            "the knowledge base has no relevant result."
        ),
        tools=[moss_search],
    )

    print("\nRunning agent query...")
    return await Runner.run(agent, question)


async def main() -> None:
    load_dotenv()
    env = _require_env_vars()

    # 1. Initialize Moss Client and Load Index
    client = MossClient(
        project_id=env["MOSS_PROJECT_ID"],
        project_key=env["MOSS_PROJECT_KEY"],
    )
    index_name = env["MOSS_INDEX_NAME"]  # e.g. "my-index"

    # Ensure the demo index exists in the cloud before pre-loading it
    await _ensure_demo_index(client, index_name)

    # 2. Load the index locally, create the agent, and run the question.
    result = await run_agent(client, index_name, "How long do refunds take to process?")
    print(f"\nFinal Agent Response:\n{result.final_output}")


if __name__ == "__main__":
    asyncio.run(main())
