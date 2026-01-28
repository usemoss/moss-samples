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
class colors: # You may need to change color settings
    RED = '\033[31m'
    ENDC = '\033[m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'


async def load_and_query_sample():
    """Simple sample showing how to load an existing index and perform queries."""
    print(colors.BLUE + "=" * 40 + colors.ENDC)
    print(f"{colors.BLUE}Moss SDK - Load Index & Query Sample{colors.ENDC}")
    print(colors.BLUE + "=" * 40 + colors.ENDC)

    # Load configuration from environment variables
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")
    index_name = os.getenv("MOSS_INDEX_NAME")

    # Validate required environment variables
    if not all([project_id, project_key, index_name]):
        print("Error: Missing required environment variables!")
        print("Please set MOSS_PROJECT_ID, MOSS_PROJECT_KEY, and MOSS_INDEX_NAME in .env file")
        return

    print(f"{colors.BLUE}Using index: {index_name}{colors.ENDC}")

    # Initialize Moss client
    client = MossClient(project_id, project_key)

    try:
        # Load the index for querying
        print("\nLoading index...")
        await client.load_index(index_name)
        print(f"{colors.GREEN}Index loaded successfully{colors.ENDC}")
        print(colors.BLUE + "=" * 40 + colors.ENDC)

        print(f"\n{colors.BLUE}Performing sample search... {colors.ENDC}\n")
        query = "refund processing time and policy"
        results = await client.query(index_name, query, 6)

        print(f"{colors.GREEN}Found {len(results.docs)} results in {results.time_taken_ms}ms{colors.ENDC}\n")
        for j, result in enumerate(results.docs, 1):
            print(f"{colors.YELLOW}[{result.id}] Score: {result.score:.3f}{colors.ENDC}")
            print(f"     {result.text}\n")

        print(f"\n{colors.GREEN}Sample completed successfully!{colors.ENDC}")

    except Exception as error:
        print(f"Error: {error}")
        print("Check your credentials and index name in .env file")


# Export main function
__all__ = ["load_and_query_sample"]


# Run the sample
if __name__ == "__main__":
    asyncio.run(load_and_query_sample())