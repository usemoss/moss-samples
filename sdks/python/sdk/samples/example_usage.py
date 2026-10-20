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

from moss import (
    MossClient,
    DocumentInfo,
    MutationOptions,
    GetDocumentsOptions,
    QueryOptions,
)


async def example_usage():
    """Complete example demonstrating all Moss SDK functionality."""
    print("⭐ Moss API Complete Example ⭐")

    # Initialize client with project credentials from environment
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")

    if not project_id or not project_key:
        print(
            "❌ Please set MOSS_TEST_PROJECT_ID and MOSS_TEST_PROJECT_KEY in .env file"
        )
        print("Copy .env.template to .env and fill in your credentials")
        return

    client = MossClient(project_id, project_key)

    # Example documents following the API contract with metadata
    documents: List[DocumentInfo] = [
        DocumentInfo(
            id="doc1",
            text="Machine learning is a subset of artificial intelligence that enables computers to learn and improve from experience without being explicitly programmed.",
            metadata={
                "category": "ai",
                "topic": "machine_learning",
                "difficulty": "intermediate",
            },
        ),
        DocumentInfo(
            id="doc2",
            text="Deep learning uses neural networks with multiple layers to model and understand complex patterns in data.",
            metadata={
                "category": "ai",
                "topic": "deep_learning",
                "difficulty": "advanced",
            },
        ),
        DocumentInfo(
            id="doc3",
            text="Natural language processing enables computers to interpret and manipulate human language for various applications.",
            metadata={"category": "ai", "topic": "nlp", "difficulty": "intermediate"},
        ),
        DocumentInfo(
            id="doc4",
            text="Computer vision enables machines to interpret and understand visual information from the world around them.",
            metadata={
                "category": "ai",
                "topic": "computer_vision",
                "difficulty": "intermediate",
            },
        ),
        DocumentInfo(
            id="doc5",
            text="Reinforcement learning is a type of machine learning where an agent learns to make decisions by performing actions and receiving rewards.",
            metadata={
                "category": "ai",
                "topic": "reinforcement_learning",
                "difficulty": "advanced",
            },
        ),
    ]

    # Use timestamp to create unique index name
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    index_name = f"example-cloud-index-{timestamp}"

    try:
        print(f"\n[1/12] Creating index '{index_name}' with {len(documents)} documents...")
        created = await client.create_index(index_name, documents)
        print(f"✅ Created — {created.doc_count} docs indexed (job {created.job_id})")

        print("\n[2/12] Getting index information...")
        index_info = await client.get_index(index_name)
        print("✅ Index info")
        print(f"     Name:    {index_info.name}")
        print(f"     Docs:    {index_info.doc_count}")
        print(f"     Model:   {index_info.model.id}")
        print(f"     Status:  {index_info.status}")

        print("\n[3/12] Listing all indexes in this project...")
        indexes = await client.list_indexes()
        print(f"✅ Found {len(indexes)} index(es):")
        preview_limit = 5
        for idx in indexes[:preview_limit]:
            print(f"     - {idx.name}  ({idx.doc_count} docs, {idx.status})")
        if len(indexes) > preview_limit:
            print(f"     ... and {len(indexes) - preview_limit} more")

        print("\n[4/12] Adding more documents...")
        new_docs: List[DocumentInfo] = [
            DocumentInfo(
                id="doc6",
                text="Data science combines statistics, programming, and domain expertise to extract insights from data.",
                metadata={
                    "category": "data_science",
                    "topic": "analytics",
                    "difficulty": "intermediate",
                },
            ),
            DocumentInfo(
                id="doc7",
                text="Cloud computing provides on-demand access to computing resources over the internet.",
                metadata={
                    "category": "infrastructure",
                    "topic": "cloud",
                    "difficulty": "beginner",
                },
            ),
        ]
        add_result = await client.add_docs(
            index_name, new_docs, MutationOptions(upsert=True)
        )
        print(f"✅ Added {add_result.doc_count} docs (job {add_result.job_id})")

        print("\n[5/12] Getting all documents...")
        all_docs = await client.get_docs(index_name)
        print(f"✅ Total documents in index: {len(all_docs)}")

        print("\n[6/12] Getting specific documents by id...")
        specific_docs = await client.get_docs(
            index_name, GetDocumentsOptions(doc_ids=["doc1", "doc2", "doc6"])
        )
        print(f"✅ Fetched {len(specific_docs)} docs:")
        for doc in specific_docs:
            text_preview = doc.text[:60] + "..." if len(doc.text) > 60 else doc.text
            print(f"     [{doc.id}] {text_preview}")
            if doc.metadata:
                print(f"            metadata: {doc.metadata}")

        print("\n[7/12] Loading index for querying...")
        await client.load_index(index_name)
        print("✅ Index loaded and ready for queries")

        query_text = "artificial intelligence and neural networks"
        print(f"\n[8/12] Semantic search: \"{query_text}\"")
        search_results = await client.query(
            index_name,
            query_text,
            QueryOptions(top_k=3, alpha=0.6),
        )
        print(f"✅ {len(search_results.docs)} result(s):")
        for i, item in enumerate(search_results.docs, 1):
            text_preview = item.text[:80] + "..." if len(item.text) > 80 else item.text
            print(f"     {i}. [{item.id}]  score={item.score:.3f}")
            print(f"        {text_preview}")
            if item.metadata:
                print(f"        metadata: {item.metadata}")

        print("\n[9/12] Deleting some documents...")
        delete_result = await client.delete_docs(index_name, ["doc6", "doc7"])
        print(f"✅ Deleted {delete_result.doc_count} docs (job {delete_result.job_id})")

        print("\n[10/12] Verifying document count after deletion...")
        remaining_docs = await client.get_docs(index_name)
        print(f"✅ Remaining documents: {len(remaining_docs)}")

        final_query = "machine learning algorithms"
        print(f"\n[11/12] Final search: \"{final_query}\"")
        final_results = await client.query(
            index_name,
            final_query,
            QueryOptions(top_k=2),
        )
        print(f"✅ {len(final_results.docs)} result(s):")
        for i, item in enumerate(final_results.docs, 1):
            print(f"     {i}. [{item.id}]  score={item.score:.3f}")

        print(f"\n[12/12] Cleaning up — deleting index '{index_name}'...")
        await client.delete_index(index_name)
        print("✅ Index deleted")

        print("\n🎉 All operations completed successfully!")

    except Exception as error:
        print(f"❌ Error: {error}")
        if hasattr(error, "message"):
            print(f"Error message: {error.message}")


# Export for use in tests or other modules
__all__ = ["example_usage"]


# Run the example
if __name__ == "__main__":
    asyncio.run(example_usage())
