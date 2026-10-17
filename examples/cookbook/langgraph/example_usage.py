"""Runnable LangGraph + Moss cookbook example."""

from __future__ import annotations

import argparse
import asyncio
import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from moss import MossClient
from moss_langgraph import (
    LangGraphMossState,
    ask_question,
    build_moss_graph,
)

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _parse_filter_eq(raw: str | None) -> dict[str, object] | None:
    """Parse a simple equality filter in the form: field=value."""
    if not raw:
        return None

    if "=" not in raw:
        raise ValueError(
            "--filter-eq must be in the form field=value (e.g. category=returns)."
        )

    field, value = raw.split("=", 1)
    field = field.strip()
    value = value.strip()

    if not field or not value:
        raise ValueError(
            "--filter-eq must be in the form field=value (e.g. category=returns)."
        )

    return {"field": field, "condition": {"$eq": value}}


async def _load_index_before_graph_runs(client: MossClient, index_name: str) -> None:
    """Explicitly load the Moss index before the graph starts."""
    print(f"Loading Moss index '{index_name}' locally before the graph runs...")

    # Local load keeps query() on the in-memory hot path and enables filters.
    await client.load_index(index_name)

    print(
        "Local load complete. Retrieval now stays in-memory "
        "(~1-10ms) instead of cloud fallback (~100-500ms).\n"
    )


def _print_response(result: LangGraphMossState) -> None:
    search_result = result.get("retrieval_results")
    docs = search_result.docs if search_result is not None else []
    time_taken_ms = result.get("retrieval_time_ms")
    latency = f"{time_taken_ms}ms" if time_taken_ms is not None else "unknown time"

    print(f"\n[Moss returned {len(docs)} docs in {latency}]")
    if docs:
        for doc in docs:
            print(f"- {doc.id} (score={doc.score:.3f})")
    print(f"\nAssistant: {result.get('answer', 'No answer generated.')}\n")


async def run_langgraph_agent(
    question: str | None = None,
    filter_eq: str | None = None,
    top_k: int = 4,
    alpha: float | None = None,
) -> None:
    """Run the LangGraph example in single-shot or interactive mode."""
    project_id = _require_env("MOSS_PROJECT_ID")
    project_key = _require_env("MOSS_PROJECT_KEY")
    index_name = _require_env("MOSS_INDEX_NAME")
    groq_api_key = _require_env("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    client = MossClient(project_id, project_key)
    await _load_index_before_graph_runs(client, index_name)

    llm = ChatGroq(model=model, api_key=groq_api_key, temperature=0)
    graph = build_moss_graph(client, index_name, llm)

    if question:
        metadata_filter = _parse_filter_eq(filter_eq)
        result = await ask_question(
            graph,
            user_question=question,
            metadata_filter=metadata_filter,
            top_k=top_k,
            alpha=alpha,
        )
        _print_response(result)
        return

    print("=== Moss + LangGraph Grounded Agent ===")
    print("Each turn runs: question -> retrieve node -> generate node")
    print("Type 'quit' to exit.\n")

    while True:
        try:
            user_question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_question:
            continue
        if user_question.lower() in {"quit", "exit", "q"}:
            print("Goodbye!")
            break

        try:
            raw_filter = input("Metadata filter (optional, field=value): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        try:
            metadata_filter = _parse_filter_eq(raw_filter or None)
            result = await ask_question(
                graph,
                user_question=user_question,
                metadata_filter=metadata_filter,
                top_k=top_k,
                alpha=alpha,
            )
            _print_response(result)
        except Exception as exc:
            print(f"\nError: {exc}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LangGraph cookbook example using Moss as a retrieval node."
    )
    parser.add_argument(
        "--question",
        help="Single question to answer. Omit for interactive mode.",
    )
    parser.add_argument(
        "--filter-eq",
        help="Optional convenience filter in the form field=value (e.g. category=returns).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=4,
        help="Number of Moss results to retrieve per question.",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=None,
        help=(
            "Optional Moss hybrid search blend from 0.0 keyword-only to "
            "1.0 semantic-only. Omit to use the SDK default."
        ),
    )
    args = parser.parse_args()

    asyncio.run(
        run_langgraph_agent(
            question=args.question,
            filter_eq=args.filter_eq,
            top_k=args.top_k,
            alpha=args.alpha,
        )
    )


if __name__ == "__main__":
    main()
