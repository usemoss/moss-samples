"""
Moss SDK Session Sample

A SessionIndex is a local, in-process index you read and write in real time with no
cloud round trip, then push to the cloud so another agent or device can resume it.
This is how Moss indexes a live conversation (e.g. voice/chat transcript turns).

Required Environment Variables:
- MOSS_PROJECT_ID: Your Moss project ID
- MOSS_PROJECT_KEY: Your Moss project key
- MOSS_INDEX_NAME: Name for the session index (created or resumed). Defaults to "session-demo".
"""

import asyncio
import os

from dotenv import load_dotenv
from moss import DocumentInfo, MossClient, QueryOptions

# Load environment variables
load_dotenv()


async def session_sample():
    """Open a session, index documents locally, query in-memory, then push to the cloud."""
    print("=" * 40)
    print("Moss SDK - Session Sample")
    print("=" * 40)

    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")
    index_name = os.getenv("MOSS_INDEX_NAME", "session-demo")

    if not project_id or not project_key:
        print("Error: Missing required environment variables!")
        print("Please set MOSS_PROJECT_ID and MOSS_PROJECT_KEY in .env file")
        return

    client = MossClient(project_id, project_key)

    try:
        # Open a session by name. If a cloud index with this name already exists it
        # auto-loads; otherwise the session starts empty. No cloud round trip on add/query.
        print(f"\nOpening session '{index_name}'...")
        session = await client.session(index_name=index_name)
        print(f"Session open ({session.doc_count} existing docs)")

        # Add documents as they arrive (e.g. transcript turns). Embedded locally.
        print("\nAdding documents locally...")
        added, updated = await session.add_docs([
            DocumentInfo(id="turn-1", text="Customer was charged twice for the March renewal."),
            DocumentInfo(id="turn-2", text="Agent confirmed a refund for the duplicate charge."),
            DocumentInfo(id="turn-3", text="Customer also asked to cancel auto-renew."),
        ])
        print(f"{added} added, {updated} updated ({session.doc_count} total)")

        # Query the in-memory session (~1-10 ms, no network).
        print("\nQuerying the session...")
        results = await session.query("what did the customer want refunded", QueryOptions(top_k=3))
        for doc in results.docs:
            print(f"  [{doc.id}] {doc.score:.3f}  {doc.text}")

        # Push the session to the cloud so another agent or device can resume it.
        print("\nPushing session to the cloud...")
        pushed = await session.push_index()
        print(f"Pushed {pushed.doc_count} docs (job {pushed.job_id})")

        print("\nSample completed successfully!")

    except Exception as error:
        print(f"Error: {error}")
        print("Check your credentials in .env file")


# Export main function
__all__ = ["session_sample"]


# Run the sample
if __name__ == "__main__":
    asyncio.run(session_sample())
