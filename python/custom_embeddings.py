#!/usr/bin/env python3
"""
Test custom embeddings workflow:
0. Create a new index with 10 initial documents
1. Add 3 more documents with custom OpenAI embeddings using add_docs
2. Query via hotpath (cloud query without loading index locally)
3. Load index locally
4. Query locally
"""

import asyncio
import os
import sys
import time
from typing import List

from dotenv import load_dotenv
from openai import OpenAI

from inferedge_moss import (
    AddDocumentsOptions,
    DocumentInfo,
    MossClient,
    QueryOptions,
)

# Load environment variables from .env file
load_dotenv()

# Get credentials from environment variables
MOSS_PROJECT_ID = os.getenv("MOSS_PROJECT_ID")
MOSS_PROJECT_KEY = os.getenv("MOSS_PROJECT_KEY")
MOSS_INDEX_NAME = f"cust-hot-{int(time.time() * 1000)}"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize clients
moss_client = MossClient(MOSS_PROJECT_ID, MOSS_PROJECT_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Initial documents to create index with
INITIAL_DOCUMENTS = [
    {
        "id": "init-doc-1",
        "text": "React is a popular JavaScript library for building user interfaces",
    },
    {
        "id": "init-doc-2",
        "text": "Python is a versatile programming language used for web development",
    },
    {
        "id": "init-doc-3",
        "text": "Machine learning enables computers to learn from data",
    },
    {
        "id": "init-doc-4",
        "text": "Docker containers help package applications with their dependencies",
    },
    {
        "id": "init-doc-5",
        "text": "TypeScript adds static typing to JavaScript for safer code",
    },
    {
        "id": "init-doc-6",
        "text": "Kubernetes orchestrates containerized applications at scale",
    },
    {
        "id": "init-doc-7",
        "text": "GraphQL provides a flexible query language for APIs",
    },
    {
        "id": "init-doc-8",
        "text": "Redis is an in-memory data store used for caching",
    },
    {
        "id": "init-doc-9",
        "text": "PostgreSQL is a powerful open-source relational database",
    },
    {
        "id": "init-doc-10",
        "text": "Git is a distributed version control system for tracking code changes",
    },
]

# Test documents to add later
NEW_DOCUMENTS = [
    {
        "id": f"test-doc-{int(time.time() * 1000)}-1",
        "text": "David loves playing john butler oscean songs on his guitar",
    },
    {
        "id": f"test-doc-{int(time.time() * 1000)}-2",
        "text": "David enjoys hiking in the mountains during weekends",
    },
    {
        "id": f"test-doc-{int(time.time() * 1000)}-3",
        "text": "David loves playing games on ps5",
    },
]

# Query to test retrieval
TEST_QUERY = "what song does David like to play on guitar?"


def generate_embedding(text: str) -> List[float]:
    """Generate OpenAI embedding for text."""
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding


async def main():
    """Main test workflow."""
    print("=" * 80)
    print("🧪 Testing Custom Embeddings Workflow")
    print("=" * 80)
    print(f"Index: {MOSS_INDEX_NAME}")
    print(f"Initial documents: {len(INITIAL_DOCUMENTS)}")
    print(f"Documents to add later: {len(NEW_DOCUMENTS)}")
    print()

    try:
        # Step 0: Create index with initial documents
        print("🏗️  Step 0: Creating index with 10 initial documents...")
        print("   Generating embeddings for initial documents...")

        initial_docs_with_embeddings = []
        for doc in INITIAL_DOCUMENTS:
            embedding = generate_embedding(doc["text"])
            initial_docs_with_embeddings.append(
                DocumentInfo(
                    id=doc["id"],
                    text=doc["text"],
                    embedding=embedding,
                )
            )

        print(f"   ✓ Generated {len(initial_docs_with_embeddings)} embeddings")

        print("   Creating index with custom embeddings...")
        await moss_client.create_index(
            MOSS_INDEX_NAME,
            initial_docs_with_embeddings,
        )
        print(f"   ✅ Index \"{MOSS_INDEX_NAME}\" created successfully with custom embeddings")
        print("   ⏳ Waiting 3 seconds for index to initialize...")
        await asyncio.sleep(3)
        print()

        # Step 1: Generate embeddings for new documents
        print("📝 Step 1: Generating OpenAI embeddings for new documents...")
        docs_with_embeddings = []
        for doc in NEW_DOCUMENTS:
            embedding = generate_embedding(doc["text"])
            print(f"   ✓ Generated embedding for \"{doc['id']}\" (dim: {len(embedding)})")
            docs_with_embeddings.append(
                DocumentInfo(
                    id=doc["id"],
                    text=doc["text"],
                    embedding=embedding,
                )
            )
        print(f"   ✅ Generated {len(docs_with_embeddings)} embeddings")
        print()

        # Step 2: Add documents to index using add_docs
        print("📤 Step 2: Adding documents with custom embeddings to index...")
        add_result = await moss_client.add_docs(
            MOSS_INDEX_NAME,
            docs_with_embeddings,
            AddDocumentsOptions(upsert=True),
        )
        print(f"   ✅ Added: {add_result['added']}, Updated: {add_result['updated']}")
        print("   ⏳ Waiting 2 seconds for index to update...")
        await asyncio.sleep(2)
        print()

        # Step 3: Query via hotpath (cloud query without loading locally)
        print("🔍 Step 3: Querying via hotpath (cloud query without loading index)...")
        query_embedding = generate_embedding(TEST_QUERY)
        print(f"   Generated query embedding (dim: {len(query_embedding)})")

        hotpath_results = await moss_client.query(
            MOSS_INDEX_NAME,
            TEST_QUERY,
            QueryOptions(embedding=query_embedding, top_k=5),
        )

        print(f"   ✅ Hotpath query returned {len(hotpath_results.docs)} results")
        print(f"   Time taken: {hotpath_results.time_taken_ms}ms")
        print()
        print("   Top 3 results:")
        for i, doc in enumerate(hotpath_results.docs[:3]):
            print(f"   {i + 1}. {doc.id}")
            print(f"      Score: {doc.score:.4f}")
            print(f"      Text: {doc.text[:60]}...")

        # Verify that newly added documents appear in results
        new_doc_ids = [d["id"] for d in NEW_DOCUMENTS]
        found_new_docs = [
            doc for doc in hotpath_results.docs
            if any(doc.id.startswith("-".join(id.split("-")[:3])) for id in new_doc_ids)
        ]
        print(f"   📊 Found {len(found_new_docs)} of {len(NEW_DOCUMENTS)} newly added docs in results")
        print()

        # Step 4: Load index locally
        print("💾 Step 4: Loading index locally...")
        loaded_index_name = await moss_client.load_index(MOSS_INDEX_NAME)
        print(f"   ✅ Index \"{loaded_index_name}\" loaded successfully")
        print()

        # Step 5: Query locally (should use loaded index)
        print("🔎 Step 5: Querying locally (using loaded index)...")
        local_results = await moss_client.query(
            MOSS_INDEX_NAME,
            TEST_QUERY,
            QueryOptions(embedding=query_embedding, top_k=5),
        )

        print(f"   ✅ Local query returned {len(local_results.docs)} results")
        print(f"   Time taken: {local_results.time_taken_ms}ms")
        print()
        print("   Top 3 results:")
        for i, doc in enumerate(local_results.docs[:3]):
            print(f"   {i + 1}. {doc.id}")
            print(f"      Score: {doc.score:.4f}")
            print(f"      Text: {doc.text[:60]}...")

        # Verify that newly added documents appear in local results
        found_new_docs_local = [
            doc for doc in local_results.docs
            if any(doc.id.startswith("-".join(id.split("-")[:3])) for id in new_doc_ids)
        ]
        print(f"   📊 Found {len(found_new_docs_local)} of {len(NEW_DOCUMENTS)} newly added docs in local results")
        print()

        # Step 6: Compare results
        print("📊 Step 6: Comparing hotpath vs local results...")
        print(f"   Hotpath results: {len(hotpath_results.docs)}")
        print(f"   Local results: {len(local_results.docs)}")
        print(f"   Hotpath time: {hotpath_results.time_taken_ms}ms")
        print(f"   Local time: {local_results.time_taken_ms}ms")

        # Check if top results match
        if hotpath_results.docs and local_results.docs:
            top_hotpath = hotpath_results.docs[0]
            top_local = local_results.docs[0]
            top_results_match = top_hotpath.id == top_local.id
            print(f"   Top result match: {'✅ Yes' if top_results_match else '❌ No'}")
            if not top_results_match:
                print(f"      Hotpath top: {top_hotpath.id}")
                print(f"      Local top: {top_local.id}")
        print()

        # Summary
        print("=" * 80)
        print("✅ TEST SUMMARY")
        print("=" * 80)
        print(f"✓ Created new index with {len(INITIAL_DOCUMENTS)} initial documents")
        print(f"✓ Successfully added {add_result['added'] + add_result['updated']} more documents with custom embeddings")
        print(f"✓ Total documents in index: {len(INITIAL_DOCUMENTS) + add_result['added'] + add_result['updated']}")
        print(f"✓ Hotpath query returned {len(hotpath_results.docs)} results")
        print(f"✓ Local query returned {len(local_results.docs)} results")
        print(f"✓ Newly added documents found in hotpath: {len(found_new_docs)}/{len(NEW_DOCUMENTS)}")
        print(f"✓ Newly added documents found in local: {len(found_new_docs_local)}/{len(NEW_DOCUMENTS)}")
        print()
        print("🎉 All tests completed successfully!")
        print("=" * 80)

    except Exception as error:
        print()
        print("=" * 80)
        print("❌ TEST FAILED")
        print("=" * 80)
        print(f"Error: {error}")
        import traceback
        print()
        print("Stack trace:")
        traceback.print_exc()
        print("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())