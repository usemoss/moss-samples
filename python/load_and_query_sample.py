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
    print("Moss SDK - Load Index & Query Sample")
    print("=" * 40)

    # Load configuration from environment variables
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")
    index_name = os.getenv("MOSS_INDEX_NAME")

    # Validate required environment variables
    if not all([project_id, project_key, index_name]):
        print("Error: Missing required environment variables!")
        print("Please set MOSS_PROJECT_ID, MOSS_PROJECT_KEY, and MOSS_INDEX_NAME in .env file")
        return

    print(f"Using index: {index_name}")

    # Initialize Moss client
    client = MossClient(project_id, project_key)

    try:
        # Load the index for querying
        print(f"\nLoading index...")
        await client.load_index(index_name)
        print(f"Index loaded successfully")

        # Perform sample searches
        print(f"\nPerforming sample searches...")
        
        queries = [
            "how to return damaged item",
            "return shipping label process",
            "refund processing time and policy"
        ]

        for i, query in enumerate(queries, 1):
            print(f"\nQuery {i}: '{query}'")
            try:
                results = await client.query(index_name, query, 3)
                print(f"Found {len(results.docs)} results in {results.time_taken_ms}ms")
                
                for j, result in enumerate(results.docs, 1):
                    preview = result.text[:80] + "..." if len(result.text) > 80 else result.text
                    print(f"  {j}. [{result.id}] Score: {result.score:.3f}")
                    print(f"     {preview}")
                    
            except Exception as e:
                print(f"  Query failed: {str(e)}")

        print(f"\nSample completed successfully!")

    except Exception as error:
        print(f"Error: {error}")
        print("Check your credentials and index name in .env file")


# Export main function
__all__ = ["load_and_query_sample"]


# Run the sample
if __name__ == "__main__":
    asyncio.run(load_and_query_sample())