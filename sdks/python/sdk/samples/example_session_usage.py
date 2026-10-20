"""
Example: Live Call Session Indexing with moss

Demonstrates the full session workflow:
  1. Load a persistent FAQ index from cloud
  2. Start a local session for an active call
  3. Index call transcript turns locally during the call (~1-5ms each)
  4. Query both the session index and the cloud FAQ index for context
  5. Push the session index to cloud at call end
"""

import asyncio
import os
import time
from datetime import datetime
from moss import DocumentInfo, MossClient, QueryOptions
from dotenv import load_dotenv
load_dotenv()

def _ms(start: float) -> str:
    return f"{(time.perf_counter() - start) * 1000:.1f}ms"


async def main() -> None:
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")

    if not project_id or not project_key:
        print("Please set MOSS_PROJECT_ID and MOSS_PROJECT_KEY in samples/.env")
        print("Copy samples/.env.template to samples/.env and fill in your credentials.")
        return

    client = MossClient(project_id, project_key)

    # -- Simulated call data ---------------------------------------------------
    call_id = f"call-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    transcript = [
        ("turn-1", "Customer called about an incorrect charge on their March invoice."),
        ("turn-2", "The customer was billed twice for the same subscription renewal."),
        ("turn-3", "Customer requested a refund for the duplicate charge of $49.99."),
        ("turn-4", "Agent confirmed the refund would be processed in 3-5 business days."),
        ("turn-5", "Customer also asked about upgrading to the Business plan."),
        ("turn-6", "Agent explained Business plan includes 1TB storage at $79.99/month."),
        ("turn-7", "Customer decided to upgrade immediately after hearing the benefits."),
    ]

    print(f"\n--- Starting session: {call_id} ---\n")

    # -- Step 1: Open session — auto-loads from cloud if it exists, starts fresh if not
    t = time.perf_counter()
    session = await client.session(index_name=call_id)
    print(f"Session ready: {session.name!r}  ({session.doc_count} existing docs)  [{_ms(t)}]")

    # -- Step 2: Index transcript turns as they arrive -------------------------
    print("\nIndexing call transcript locally...")
    docs = [DocumentInfo(id=turn_id, text=text) for turn_id, text in transcript]
    t = time.perf_counter()
    added, updated = await session.add_docs(docs)
    print(f"  {added} turns added, {updated} updated  (total: {session.doc_count})  [{_ms(t)}]")

    # -- Step 3: Query the local session index for context ---------------------
    print("\nQuerying session index (local, no cloud)...")
    queries = [
        "billing issue and invoice dispute",
        "refund processing timeline",
        "plan upgrade storage",
    ]

    for query_text in queries:
        t = time.perf_counter()
        results = await session.query(query_text, QueryOptions(top_k=2))
        print(f"\n  Query: {query_text!r}  [{_ms(t)}]")
        for doc in results.docs:
            print(f"    [{doc.id}] score={doc.score:.3f}  {doc.text[:60]}...")

    # -- Step 4: Add more turns mid-call and query again -----------------------
    print("\nAdding follow-up turns...")
    follow_ups = [
        DocumentInfo(id="turn-8", text="Agent initiated the plan upgrade and sent confirmation email."),
        DocumentInfo(id="turn-9", text="Customer confirmed they received the email and were satisfied."),
    ]
    t = time.perf_counter()
    await session.add_docs(follow_ups)
    print(f"  Session now has {session.doc_count} documents  [{_ms(t)}]")

    t = time.perf_counter()
    result = await session.query("call resolution and next steps", QueryOptions(top_k=3))
    print(f"\n  Final context query results  [{_ms(t)}]:")
    for doc in result.docs:
        print(f"    [{doc.id}] score={doc.score:.3f}  {doc.text[:60]}...")

    # -- Step 5: End of call — push session index to cloud ---------------------
    print(f"\nPushing session index to cloud as {call_id!r}...")
    t = time.perf_counter()
    push_result = await session.push_index()
    print(f"  job_id:    {push_result.job_id}  [{_ms(t)}]")
    print(f"  index:     {push_result.index_name}")
    print(f"  doc_count: {push_result.doc_count}")
    print(f"  status:    {push_result.status}")

    print("\nDone! The session index is now available in the cloud for future retrieval.")
    print(f"Next run with index_name={call_id!r} will auto-load it.")


if __name__ == "__main__":
    asyncio.run(main())
