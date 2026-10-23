"""Cross-agent handoff, built on Moss.

When a conversation moves between agents (chat -> voice), channels, or devices,
the context usually resets and the customer has to repeat themselves. With Moss,
every agent shares one *named session*. The first agent writes down what happened
and pushes it to the cloud; the next agent opens the same session by name, resumes
it (no re-embedding), and can immediately query context it never directly received.

This example simulates two independent agents in one process: agent A handles the
chat and hands off, then agent B (a fresh client, as if it were a different
service on voice) picks the session up and answers from the shared context.
"""

import asyncio
import os
import sys
import uuid

from dotenv import load_dotenv

from moss import MossClient, DocumentInfo, QueryOptions


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        sys.exit(f"Missing {name}. Copy .env.example to .env and fill in your keys.")
    return value


def _client() -> MossClient:
    return MossClient(
        project_id=_require("MOSS_PROJECT_ID"),
        project_key=_require("MOSS_PROJECT_KEY"),
    )


async def agent_a_handles_chat(session_name: str) -> None:
    """First agent: handles the chat turn, then hands the session off to the cloud."""
    moss = _client()
    session = await moss.session(index_name=session_name)

    # write the conversation as it happens (each turn is one document)
    await session.add_docs([
        DocumentInfo(id="t1", text="Customer reported a duplicate $49.99 charge on July 3."),
        DocumentInfo(id="t2", text="Agent confirmed a refund, arriving in 3-5 business days."),
        DocumentInfo(id="t3", text="Customer's order number is AC-77120."),
    ])

    # hand off: push to the cloud. push_index() queues a server-side indexing job,
    # so wait for it to finish before another agent tries to resume the session.
    result = await session.push_index()
    if result.job_id:
        await moss.wait_for_job(result.job_id)
    print("[agent A - chat]   wrote 3 turns and pushed the session to the cloud\n")


async def agent_b_picks_up(session_name: str) -> None:
    """Second agent (a different client/service, e.g. voice): resumes the same session."""
    moss = _client()

    # same name -> Moss auto-loads the pushed index from the cloud, no re-embedding
    session = await moss.session(index_name=session_name)

    # agent B was never told any of this; it queries the shared context
    for question in [
        "what is this call about?",
        "was a refund promised, and when?",
        "what is the order number?",
    ]:
        res = await session.query(question, QueryOptions(top_k=1))
        answer = res.docs[0].text if res.docs else "(nothing found)"
        print(f"[agent B - voice]  Q: {question}")
        print(f"                   A: {answer}\n")


async def main() -> None:
    load_dotenv()
    _require("MOSS_PROJECT_ID")
    _require("MOSS_PROJECT_KEY")

    # unique per run so the demo starts clean; in production use a stable id such
    # as the call / conversation id so the same session is resumable later.
    session_name = f"call-handoff-demo-{uuid.uuid4().hex[:8]}"
    print(f"shared session: {session_name}\n")

    try:
        await agent_a_handles_chat(session_name)
        print("--- customer is transferred from chat to voice ---\n")
        await agent_b_picks_up(session_name)
    finally:
        # demo cleanup: this run pushed a cloud index, so remove it. In production
        # you would keep the session (a stable, resumable id) instead of deleting it.
        await _client().delete_index(session_name)
        print(f"\ncleaned up demo session: {session_name}")


if __name__ == "__main__":
    asyncio.run(main())
