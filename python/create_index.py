"""
Simple Moss SDK Sample - Index Creation

This example demonstrates creating a Moss index from a JSON file:
- Loading documents from lightberry.json
- Creating an index with the documents
- Basic error handling

The sample uses a dynamic index name based on current timestamp.
"""

import asyncio
import os
from typing import List, Dict, Any
from dotenv import load_dotenv
from datetime import datetime
import json

# Load environment variables
load_dotenv()

from inferedge_moss import MossClient, DocumentInfo


async def comprehensive_moss_example():
    """
    Simple example demonstrating Moss SDK index creation from JSON file.
    
    This sample covers:
    1. Client initialization
    2. Loading documents from lightberry.json
    3. Index creation with documents
    """
    print("Moss SDK Index Creation Sample")
    print("=" * 60)

    # Initialize client with project credentials from environment
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")

    if not project_id or not project_key:
        print("❌ Error: Missing environment variables!")
        print("Please set MOSS_PROJECT_ID and MOSS_PROJECT_KEY in .env file")
        print("Copy .env.template to .env and fill in your credentials")
        return

    client = MossClient(project_id, project_key)

    # Load documents from lightberry.json
    json_file_path = os.path.join(os.path.dirname(__file__), "lightberry.json")
    
    try:
        with open(json_file_path, 'r') as f:
            json_data = json.load(f)
        
        # Convert JSON data to DocumentInfo objects
        documents: List[DocumentInfo] = []
        for item in json_data:
            documents.append(DocumentInfo(
                id=item["id"],
                text=item["text"],
                metadata=item.get("metadata", {})
            ))
        
        print(f"\nLoaded {len(documents)} documents from lightberry.json")
        
    except FileNotFoundError:
        print(f"❌ Error: Could not find lightberry.json at {json_file_path}")
        return
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON format in lightberry.json: {e}")
        return

    # Create dynamic index name with timestamp
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    index_name = f"lightberry-demo-{timestamp}"

    try:
        print(f"\nCreating index '{index_name}' with {len(documents)} documents...")
        created = await client.create_index(index_name, documents, "moss-minilm")
        print(f"✅ Index created successfully: {created}")

        print(f"\nIndex creation completed successfully!")
        print("=" * 60)

    except Exception as error:
        print(f"❌ Error occurred: {error}")
        if hasattr(error, 'message'):
            print(f"   Error message: {error.message}")
        if hasattr(error, 'status_code'):
            print(f"   Status code: {error.status_code}")


# Export for use in tests or other modules
__all__ = ["comprehensive_moss_example"]


# Run the example
if __name__ == "__main__":
    asyncio.run(comprehensive_moss_example())