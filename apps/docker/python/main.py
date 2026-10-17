"""
Moss Python SDK - Docker Example

Demonstrates how to use the Moss Python SDK inside a container
(as you would in AWS ECS, Kubernetes, etc.).

Env vars (set via docker-compose or your container runtime):
  MOSS_PROJECT_ID   - Your Moss project ID
  MOSS_PROJECT_KEY  - Your Moss project key
  MOSS_INDEX_NAME   - Name of the index to query
"""

import asyncio
import os

from dotenv import load_dotenv
from moss import MossClient, QueryOptions

load_dotenv()


async def main():
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")
    index_name = os.getenv("MOSS_INDEX_NAME")

    if not project_id or not project_key or not index_name:
        print("Error: MOSS_PROJECT_ID, MOSS_PROJECT_KEY, and MOSS_INDEX_NAME must be set.")
        return

    client = MossClient(project_id, project_key)

    print(f"Loading index '{index_name}'...")
    await client.load_index(index_name)
    print("Index loaded.")

    query = "what is your return policy"
    print(f"\nQuerying: '{query}'")
    results = await client.query(index_name, query, QueryOptions(top_k=3))

    print(f"Found {len(results.docs)} results in {results.time_taken_ms}ms\n")
    for result in results.docs:
        print(f"  [{result.id}] score={result.score:.3f}")
        print(f"  {result.text}\n")


if __name__ == "__main__":
    asyncio.run(main())
