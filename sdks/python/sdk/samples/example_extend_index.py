"""
Example: Resume an existing cloud index, extend it in-session, push the update.

session(index_name) automatically loads from cloud if the index exists,
or starts fresh if it doesn't — the workflow is identical in both cases.

  1. First run  — index doesn't exist yet, session starts empty
  2. Second run — index exists in cloud, session auto-loads it, new docs are appended
"""

import asyncio
import os
import time
from moss import DocumentInfo, MossClient, QueryOptions
from dotenv import load_dotenv

load_dotenv()

def _ms(start: float) -> str:
    return f"{(time.perf_counter() - start) * 1000:.1f}ms"


async def main() -> None:
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")
    index_name = os.getenv("MOSS_EXISTING_INDEX", "my-session-index")

    if not project_id or not project_key:
        print("Please set MOSS_PROJECT_ID and MOSS_PROJECT_KEY in samples/.env")
        return

    client = MossClient(project_id, project_key)

    # Auto-loads from cloud if the index exists, starts fresh if not
    print(f"Opening session for '{index_name}'...")
    t = time.perf_counter()
    session = await client.session(index_name=index_name)
    print(f"  Session ready — {session.doc_count} existing docs loaded  [{_ms(t)}]")

    # Add new docs — appended to whatever was already loaded
    new_docs = [
        DocumentInfo(id="follow-up-1", text="Customer called back to confirm refund was received."),
        DocumentInfo(id="follow-up-2", text="Refund of $49.99 appeared on statement within 3 days."),
        DocumentInfo(id="follow-up-3", text="Customer expressed satisfaction and closed the case."),
    ]
    print("\nAdding new docs...")
    t = time.perf_counter()
    added, updated = await session.add_docs(new_docs)
    print(f"  {added} added, {updated} updated  (total: {session.doc_count})  [{_ms(t)}]")

    # Query the combined index
    print("\nQuerying combined index...")
    t = time.perf_counter()
    results = await session.query("refund outcome and customer satisfaction", QueryOptions(top_k=3))
    print(f"  Query complete  [{_ms(t)}]")
    for doc in results.docs:
        print(f"    [{doc.id}] score={doc.score:.3f}  {doc.text[:60]}...")

    # Push back to cloud — creates or overwrites
    print(f"\nPushing to cloud as '{index_name}'...")
    t = time.perf_counter()
    push_result = await session.push_index()
    print(f"  job_id:    {push_result.job_id}  [{_ms(t)}]")
    print(f"  doc_count: {push_result.doc_count}")
    print(f"  status:    {push_result.status}")


if __name__ == "__main__":
    asyncio.run(main())
