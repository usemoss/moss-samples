"""
Example usage of the Moss Python SDK

This example demonstrates the complete workflow.
"""

import asyncio
import os
from typing import List
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

from inferedge_moss import MossClient, DocumentInfo, AddDocumentsOptions, GetDocumentsOptions


async def example_usage():
    """Complete example demonstrating all Moss SDK functionality."""
    print("⭐ Moss API Complete Example ⭐")

    # Initialize client with project credentials from environment
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")

    if not project_id or not project_key:
        print("❌ Please set MOSS_TEST_PROJECT_ID and MOSS_TEST_PROJECT_KEY in .env file")
        print("Copy .env.template to .env and fill in your credentials")
        return

    client = MossClient(project_id, project_key)

    # Example documents following the API contract with metadata
    documents: List[DocumentInfo] = [
        DocumentInfo(
            id="doc1",
            text="Machine learning is a subset of artificial intelligence that enables computers to learn and improve from experience without being explicitly programmed.",
            metadata={"category": "ai", "topic": "machine_learning", "difficulty": "intermediate"}
        ),
        DocumentInfo(
            id="doc2",
            text="Deep learning uses neural networks with multiple layers to model and understand complex patterns in data.",
            metadata={"category": "ai", "topic": "deep_learning", "difficulty": "advanced"}
        ),
        DocumentInfo(
            id="doc3",
            text="Natural language processing enables computers to interpret and manipulate human language for various applications.",
            metadata={"category": "ai", "topic": "nlp", "difficulty": "intermediate"}
        ),
        DocumentInfo(
            id="doc4",
            text="Computer vision enables machines to interpret and understand visual information from the world around them.",
            metadata={"category": "ai", "topic": "computer_vision", "difficulty": "intermediate"}
        ),
        DocumentInfo(
            id="doc5",
            text="Reinforcement learning is a type of machine learning where an agent learns to make decisions by performing actions and receiving rewards.",
            metadata={"category": "ai", "topic": "reinforcement_learning", "difficulty": "advanced"}
        )
    ]

    # Use timestamp to create unique index name
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    index_name = f"example-cloud-index-{timestamp}"

    try:
        print("1. Creating index with documents...")
        created = await client.create_index(index_name, documents, "moss-minilm")
        print(f"✅ Index created: {created}")

        print("\n2. Getting index information...")
        index_info = await client.get_index(index_name)
        print(f"✅ Index info:")
        print(f"  Name: {index_info.name}")
        print(f"  Document Count: {index_info.doc_count}")
        print(f"  Model: {index_info.model.id}")
        print(f"  Status: {index_info.status}")

        print("\n3. Listing all indexes...")
        indexes = await client.list_indexes()
        print("✅ All indexes:")
        for idx in indexes:
            print(f"  - {idx.name}: {idx.doc_count} docs, status: {idx.status}")

        print("\n4. Adding more documents...")
        new_docs: List[DocumentInfo] = [
            DocumentInfo(
                id="doc6",
                text="Data science combines statistics, programming, and domain expertise to extract insights from data.",
                metadata={"category": "data_science", "topic": "analytics", "difficulty": "intermediate"}
            ),
            DocumentInfo(
                id="doc7",
                text="Cloud computing provides on-demand access to computing resources over the internet.",
                metadata={"category": "infrastructure", "topic": "cloud", "difficulty": "beginner"}
            )
        ]
        add_result = await client.add_docs(index_name, new_docs, AddDocumentsOptions(upsert=True))
        print(f"✅ Documents added: {add_result}")

        print("\n5. Getting all documents...")
        all_docs = await client.get_docs(index_name)
        print(f"✅ Total documents: {len(all_docs)}")

        print("\n6. Getting specific documents...")
        specific_docs = await client.get_docs(
            index_name, 
            GetDocumentsOptions(doc_ids=["doc1", "doc2", "doc6"])
        )
        print(f"✅ Specific documents:")
        for doc in specific_docs:
            text_preview = doc.text[:50] + "..." if len(doc.text) > 50 else doc.text
            print(f"  - {doc.id}: {text_preview}")
            if doc.metadata:
                print(f"    Metadata: {doc.metadata}")

        print("\n7. Loading index for querying...")
        loaded_index = await client.load_index(index_name)
        print(f"✅ Loaded index: {loaded_index}")

        print("\n8. Performing semantic search...")
        search_results = await client.query(
            index_name,
            "artificial intelligence and neural networks",
            3
        )

        print("✅ Search results:")
        print(f"Query: \"{search_results.query}\"")
        print(f"Found {len(search_results.docs)} results")
        print(f"Time taken: {search_results.time_taken_ms} ms")

        for i, item in enumerate(search_results.docs, 1):
            text_preview = item.text[:80] + "..." if len(item.text) > 80 else item.text
            print(f"{i}. [{item.id}] Score: {item.score:.3f}")
            print(f"   Text: {text_preview}")
            if item.metadata:
                print(f"   Metadata: {item.metadata}")

        print("\n9. Deleting some documents...")
        delete_result = await client.delete_docs(index_name, ["doc6", "doc7"])
        print(f"✅ Documents deleted: {delete_result['deleted']}")

        print("\n10. Verifying document count after deletion...")
        remaining_docs = await client.get_docs(index_name)
        print(f"✅ Remaining documents: {len(remaining_docs)}")

        print("\n11. Final search to verify everything works...")
        final_results = await client.query(
            index_name,
            "machine learning algorithms",
            4
        )

        print("✅ Final search results:")
        print(f"Time taken: {final_results.time_taken_ms} ms")
        for i, item in enumerate(final_results.docs, 1):
            print(f"{i}. [{item.id}] Score: {item.score:.3f}")

        print("\n12. Cleaning up - deleting the test index...")
        deleted = await client.delete_index(index_name)
        print(f"✅ Index deleted: {deleted}")

        print("\n🎉 All operations completed successfully!")

    except Exception as error:
        print(f"❌ Error: {error}")
        if hasattr(error, 'message'):
            print(f"Error message: {error.message}")


# Export for use in tests or other modules
__all__ = ["example_usage"]


# Run the example
if __name__ == "__main__":
    asyncio.run(example_usage())