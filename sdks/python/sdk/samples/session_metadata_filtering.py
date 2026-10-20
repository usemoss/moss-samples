"""
Example: Metadata Filtering in a Session Index

Demonstrates querying a local session index with metadata filters.
All operations run in-memory — no cloud round trips during the session.

Filter operators shown:
  $eq, $ne, $gt, $in, $and, $or, $near
"""

import asyncio
import os
import time
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from moss import DocumentInfo, MossClient, QueryOptions


def _ms(start: float) -> str:
    return f"{(time.perf_counter() - start) * 1000:.1f}ms"


# -- Sample data: support call transcript with rich metadata ------------------

TRANSCRIPT = [
    DocumentInfo(
        id="t1",
        text="Customer opened the call about an incorrect charge on their March invoice.",
        metadata={"speaker": "agent", "topic": "billing", "priority": "3", "location": "40.7580,-73.9855"},
    ),
    DocumentInfo(
        id="t2",
        text="The account was billed twice for the same subscription renewal on March 5th.",
        metadata={"speaker": "agent", "topic": "billing", "priority": "5", "location": "40.7580,-73.9855"},
    ),
    DocumentInfo(
        id="t3",
        text="I need a full refund for the duplicate charge of $49.99 immediately.",
        metadata={"speaker": "customer", "topic": "refund", "priority": "5", "location": "40.6892,-74.0445"},
    ),
    DocumentInfo(
        id="t4",
        text="The refund will be processed within 3 to 5 business days to your original payment method.",
        metadata={"speaker": "agent", "topic": "refund", "priority": "4", "location": "40.7580,-73.9855"},
    ),
    DocumentInfo(
        id="t5",
        text="Can you also tell me what is included in the Business plan upgrade?",
        metadata={"speaker": "customer", "topic": "upgrade", "priority": "2", "location": "40.6892,-74.0445"},
    ),
    DocumentInfo(
        id="t6",
        text="The Business plan includes 1TB storage, priority support, and team collaboration at $79.99 per month.",
        metadata={"speaker": "agent", "topic": "upgrade", "priority": "2", "location": "40.7580,-73.9855"},
    ),
    DocumentInfo(
        id="t7",
        text="That sounds good, I would like to upgrade my plan right now.",
        metadata={"speaker": "customer", "topic": "upgrade", "priority": "3", "location": "40.6892,-74.0445"},
    ),
    DocumentInfo(
        id="t8",
        text="I have processed the plan upgrade and sent a confirmation email to your address.",
        metadata={"speaker": "agent", "topic": "upgrade", "priority": "3", "location": "40.7580,-73.9855"},
    ),
]


async def main() -> None:
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")

    if not project_id or not project_key:
        print("Please set MOSS_PROJECT_ID and MOSS_PROJECT_KEY in samples/.env")
        print("Copy samples/.env.template to samples/.env and fill in your credentials.")
        return

    client = MossClient(project_id, project_key)
    call_id = f"filter-sample-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    print(f"\n--- Session: {call_id} ---\n")

    # -- Open session and index the transcript ---------------------------------
    t = time.perf_counter()
    session = await client.session(index_name=call_id)
    await session.add_docs(TRANSCRIPT)
    print(f"Session ready: {session.doc_count} turns indexed  [{_ms(t)}]\n")

    # -- 1. $eq: customer turns only ------------------------------------------
    print("1. $eq  — customer turns only")
    t = time.perf_counter()
    results = await session.query(
        "what did the customer say",
        QueryOptions(top_k=5, filter={"field": "speaker", "condition": {"$eq": "customer"}}),
    )
    print(f"   [{_ms(t)}]  {len(results.docs)} result(s)")
    for doc in results.docs:
        print(f"   [{doc.id}] score={doc.score:.3f}  {doc.text[:70]}...")

    # -- 2. $ne: exclude agent turns ------------------------------------------
    print("\n2. $ne  — exclude agent turns")
    t = time.perf_counter()
    results = await session.query(
        "what was discussed",
        QueryOptions(top_k=5, filter={"field": "speaker", "condition": {"$ne": "agent"}}),
    )
    print(f"   [{_ms(t)}]  {len(results.docs)} result(s)")
    for doc in results.docs:
        print(f"   [{doc.id}] score={doc.score:.3f}  speaker={doc.metadata['speaker']}  {doc.text[:60]}...")

    # -- 3. $gt: high-priority turns ------------------------------------------
    print("\n3. $gt  — priority > 3")
    t = time.perf_counter()
    results = await session.query(
        "urgent issues",
        QueryOptions(top_k=5, filter={"field": "priority", "condition": {"$gt": "3"}}),
    )
    print(f"   [{_ms(t)}]  {len(results.docs)} result(s)")
    for doc in results.docs:
        print(f"   [{doc.id}] score={doc.score:.3f}  priority={doc.metadata['priority']}  {doc.text[:60]}...")

    # -- 4. $in: billing or refund turns --------------------------------------
    print("\n4. $in  — topic in [billing, refund]")
    t = time.perf_counter()
    results = await session.query(
        "payment and charges",
        QueryOptions(top_k=5, filter={"field": "topic", "condition": {"$in": ["billing", "refund"]}}),
    )
    print(f"   [{_ms(t)}]  {len(results.docs)} result(s)")
    for doc in results.docs:
        print(f"   [{doc.id}] score={doc.score:.3f}  topic={doc.metadata['topic']}  {doc.text[:60]}...")

    # -- 5. $and: agent turns about billing -----------------------------------
    print("\n5. $and  — agent + billing")
    t = time.perf_counter()
    results = await session.query(
        "billing explanation",
        QueryOptions(
            top_k=5,
            filter={"$and": [
                {"field": "speaker", "condition": {"$eq": "agent"}},
                {"field": "topic",   "condition": {"$eq": "billing"}},
            ]},
        ),
    )
    print(f"   [{_ms(t)}]  {len(results.docs)} result(s)")
    for doc in results.docs:
        print(f"   [{doc.id}] score={doc.score:.3f}  {doc.text[:70]}...")

    # -- 6. $or: refund or upgrade topics -------------------------------------
    print("\n6. $or  — refund or upgrade")
    t = time.perf_counter()
    results = await session.query(
        "account changes",
        QueryOptions(
            top_k=5,
            filter={"$or": [
                {"field": "topic", "condition": {"$eq": "refund"}},
                {"field": "topic", "condition": {"$eq": "upgrade"}},
            ]},
        ),
    )
    print(f"   [{_ms(t)}]  {len(results.docs)} result(s)")
    for doc in results.docs:
        print(f"   [{doc.id}] score={doc.score:.3f}  topic={doc.metadata['topic']}  {doc.text[:60]}...")

    # -- 7. $near: turns from the Times Square office (within 1km) ------------
    print("\n7. $near  — within 1km of Times Square (agent location)")
    t = time.perf_counter()
    results = await session.query(
        "agent response",
        QueryOptions(
            top_k=5,
            filter={"field": "location", "condition": {"$near": "40.7580,-73.9855,1000"}},
        ),
    )
    print(f"   [{_ms(t)}]  {len(results.docs)} result(s)")
    for doc in results.docs:
        print(f"   [{doc.id}] score={doc.score:.3f}  speaker={doc.metadata['speaker']}  {doc.text[:60]}...")

    # -- Push session index to cloud ------------------------------------------
    print(f"\nPushing session index to cloud as {call_id!r}...")
    t = time.perf_counter()
    push_result = await session.push_index()
    print(f"  job_id:    {push_result.job_id}  [{_ms(t)}]")
    print(f"  index:     {push_result.index_name}")
    print(f"  doc_count: {push_result.doc_count}")
    print(f"  status:    {push_result.status}")
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
