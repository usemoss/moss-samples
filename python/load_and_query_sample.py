"""
Simple Moss SDK Load Index and Query Sample

This sample shows how to load an existing FAQ index and perform search queries.
Includes sample returns-related questions for demonstration.

Required Environment Variables:
- MOSS_PROJECT_ID: Your Moss project ID  
- MOSS_PROJECT_KEY: Your Moss project key
- MOSS_INDEX_NAME: Name of existing FAQ index to query
"""

import asyncio
import os
from dotenv import load_dotenv
from inferedge_moss import MossClient

# Load environment variables
load_dotenv()

async def load_and_query_sample():
    """Simple sample showing how to load an existing index and perform queries."""
    print("=" * 40)
    print("Moss SDK - Load Index & Query Sample")
    print("=" * 40)

    # Load configuration from environment variables
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")
    index_name = os.getenv("MOSS_INDEX_NAME")

    print(f"Using index: {index_name}")

    # Initialize Moss client
    client = MossClient(project_id, project_key)

    try:
        # Load the index for querying
        print("\nLoading index...")
        await client.load_index(index_name)
        print("Index loaded successfully")
        print("=" * 40)

        print("\nPerforming sample search...\n")
        query = "refund processing time and policy"
        results = await client.query(index_name, query, top_k=6)

        print(f"Found {len(results.docs)} results in {results.time_taken_ms}ms\n")
        for j, result in enumerate(results.docs, 1):
            print(f"[{result.id}] Score: {result.score:.3f}")
            print(f"     {result.text}\n")

        print("\nSample completed successfully!")

    except Exception as error:
        print(f"Error: {error}")
        print("Check your credentials and index name in .env file")


# Export main function
__all__ = ["load_and_query_sample"]


# Run the sample
if __name__ == "__main__":
    asyncio.run(load_and_query_sample())