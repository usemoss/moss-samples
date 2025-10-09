"""
FAQ Query Example using Moss Python SDK

This example demonstrates how to create a searchable FAQ system using the Moss API.
It loads FAQ data from faqs.json and performs semantic search operations.
"""

import asyncio
import os
import json
from typing import List
from dotenv import load_dotenv
from datetime import datetime
from inferedge_moss import MossClient, DocumentInfo, AddDocumentsOptions, GetDocumentsOptions

# Load environment variables
load_dotenv()

async def example_usage():
    """Complete example demonstrating FAQ search with Moss API."""
    print("⭐ FAQ Search System using Moss API ⭐")

    # Initialize client with project credentials from environment
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")

    if not project_id or not project_key:
        print("❌ Please set MOSS_TEST_PROJECT_ID and MOSS_TEST_PROJECT_KEY in .env file")
        print("Copy .env.template to .env and fill in your credentials")
        return

    client = MossClient(project_id, project_key)

    # Load FAQ documents from JSON file
    print("Loading FAQ data from faqs.json...")
    try:
        with open('faqs.json', 'r') as f:
            faq_data = json.load(f)
        
        # Convert FAQ data to DocumentInfo objects
        documents: List[DocumentInfo] = [
            DocumentInfo(
                id=faq["id"],
                text=faq["text"],
                metadata=faq["metadata"]
            )
            for faq in faq_data
        ]
        
        print(f"✅ Loaded {len(documents)} FAQ documents")
        
    except FileNotFoundError:
        print("❌ Error: faqs.json file not found!")
        return
    except json.JSONDecodeError:
        print("❌ Error: Invalid JSON format in faqs.json!")
        return

    # Use timestamp to create unique index name
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    index_name = f"faq-index-{timestamp}"

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

        print("\n4. Adding additional FAQ documents...")
        new_docs: List[DocumentInfo] = [
            DocumentInfo(
                id="doc-additional-1",
                text="How do I create a custom product? Custom product requests can be submitted through our 'Custom Orders' form. Include specifications, quantity needed, and timeline. Our team will provide a custom quote within 3 business days.",
                metadata={"category": "orders", "topic": "custom_products", "difficulty": "advanced"}
            ),
            DocumentInfo(
                id="doc-additional-2", 
                text="What are your bulk order policies? We offer volume discounts starting at 10+ items. Bulk orders receive priority processing and dedicated support. Contact our sales team for enterprise pricing.",
                metadata={"category": "orders", "topic": "bulk_orders", "difficulty": "intermediate"}
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
            GetDocumentsOptions(doc_ids=["doc-1", "doc-2", "doc-additional-1"])
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
            "how to track my order and shipping information",
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
        delete_result = await client.delete_docs(index_name, ["doc-additional-1", "doc-additional-2"])
        print(f"✅ Documents deleted: {delete_result['deleted']}")

        print("\n10. Verifying document count after deletion...")
        remaining_docs = await client.get_docs(index_name)
        print(f"✅ Remaining documents: {len(remaining_docs)}")

        print("\n11. Final search to verify everything works...")
        final_results = await client.query(
            index_name,
            "return policy and refund information",
            4
        )

        print("✅ Final search results:")
        print(f"Time taken: {final_results.time_taken_ms} ms")
        for i, item in enumerate(final_results.docs, 1):
            print(f"{i}. [{item.id}] Score: {item.score:.3f}")

        # print("\n12. Cleaning up - deleting the test index...")
        # deleted = await client.delete_index(index_name)
        # print(f"✅ Index deleted: {deleted}")

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