"""Custom embeddings workflow sample."""

# ---------- Imports ----------
import asyncio
import os
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

# ---------- Configuration ----------
load_dotenv()
MOSS_PROJECT_ID = os.getenv("MOSS_PROJECT_ID")
MOSS_PROJECT_KEY = os.getenv("MOSS_PROJECT_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not all([MOSS_PROJECT_ID, MOSS_PROJECT_KEY, OPENAI_API_KEY]):
	raise ValueError(
		"Missing required environment variables. Please set MOSS_PROJECT_ID, "
		"MOSS_PROJECT_KEY, and OPENAI_API_KEY.",
	)

# Cast to str for mypy
PROJECT_ID = str(MOSS_PROJECT_ID)
PROJECT_KEY = str(MOSS_PROJECT_KEY)
API_KEY = str(OPENAI_API_KEY)

MOSS_INDEX_NAME = f"custom-embedding-index-{int(time.time() * 1000)}"
moss_client = MossClient(PROJECT_ID, PROJECT_KEY)
openai_client = OpenAI(api_key=API_KEY)


# ---------- Sample Data to create Index ----------

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

# ---------- Sample Data to add later ----------

NEW_DOCUMENTS = [
	{
		"id": f"step-doc-{int(time.time() * 1000)}-1",
		"text": "the Pine Grove gardening club meets every Saturday morning to plant herbs",
	},
	{
		"id": f"step-doc-{int(time.time() * 1000)}-2",
		"text": "club members water the raised beds and tidy the tool shed after the meeting",
	},
	{
		"id": f"step-doc-{int(time.time() * 1000)}-3",
		"text": "organizer Leo keeps a list of herbs to bring for next week",
	},
]

WORKFLOW_QUERY = "when does the Pine Grove gardening club meet?"


# ---------- Helper Functions ----------
def generate_embedding(text: str) -> List[float]:
	"""Generate an OpenAI embedding for the provided text."""

	response = openai_client.embeddings.create(
		model="text-embedding-3-small",
		input=text,
	)
	return response.data[0].embedding


async def delete_index(index_name: str) -> None:
	"""Delete the specified index if it exists."""

	print("🧹 Cleanup: Deleting index...")
	try:
		await moss_client.delete_index(index_name)
		print(f"   ✅ Index \"{index_name}\" deleted successfully")
	except Exception as cleanup_error:
		print(f"   ⚠️  Failed to delete index \"{index_name}\": {cleanup_error}")

# ---------- Main Workflow ----------
async def main() -> None:
	"""Exercise the custom embedding workflow steps end-to-end."""

	print("=" * 80)
	print("🧪 Running Custom Embeddings Workflow Steps")
	print("=" * 80)
	print(f"Index: {MOSS_INDEX_NAME}")
	print(f"Initial documents: {len(INITIAL_DOCUMENTS)}")
	print(f"Documents to add later: {len(NEW_DOCUMENTS)}")
	print()

	try:
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
		print(
			f"   ✅ Index \"{MOSS_INDEX_NAME}\" created successfully with custom embeddings"
		)
		print("   ⏳ Waiting 3 seconds for index to initialize...")
		await asyncio.sleep(3)
		print()

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

		print("🔍 Step 3: Querying via hotpath (cloud query without loading index)...")
		query_embedding = generate_embedding(WORKFLOW_QUERY)
		print(f"   Generated query embedding (dim: {len(query_embedding)})")

		hotpath_results = await moss_client.query(
			MOSS_INDEX_NAME,
			WORKFLOW_QUERY,
			QueryOptions(embedding=query_embedding, top_k=5),
		)

		print(f"   ✅ Hotpath query returned {len(hotpath_results.docs)} results")
		print(f"   Time taken: {hotpath_results.time_taken_ms}ms")
		print()
		print("   Top 3 results:")
		for i, result in enumerate(hotpath_results.docs[:3]):
			print(f"   {i + 1}. {result.id}")
			print(f"      Score: {result.score:.4f}")
			print(f"      Text: {result.text[:60]}...")

		new_doc_ids = [d["id"] for d in NEW_DOCUMENTS]
		found_new_docs = [
			res
			for res in hotpath_results.docs
			if any(res.id.startswith("-".join(id.split("-")[:3])) for id in new_doc_ids)
		]
		print(
			f"   📊 Found {len(found_new_docs)} of {len(NEW_DOCUMENTS)} newly added docs in results"
		)
		print()

		print("💾 Step 4: Loading index locally...")
		loaded_index_name = await moss_client.load_index(MOSS_INDEX_NAME)
		print(f"   ✅ Index \"{loaded_index_name}\" loaded successfully")
		print()

		print("🔎 Step 5: Querying locally (using loaded index)...")
		local_results = await moss_client.query(
			MOSS_INDEX_NAME,
			WORKFLOW_QUERY,
			QueryOptions(embedding=query_embedding, top_k=5),
		)

		print(f"   ✅ Local query returned {len(local_results.docs)} results")
		print(f"   Time taken: {local_results.time_taken_ms}ms")
		print()
		print("   Top 3 results:")
		for i, result_local in enumerate(local_results.docs[:3]):
			print(f"   {i + 1}. {result_local.id}")
			print(f"      Score: {result_local.score:.4f}")
			print(f"      Text: {result_local.text[:60]}...")

		found_new_docs_local = [
			res_local
			for res_local in local_results.docs
			if any(res_local.id.startswith("-".join(id.split("-")[:3])) for id in new_doc_ids)
		]
		print(
			"   📊 Found "
			f"{len(found_new_docs_local)} of {len(NEW_DOCUMENTS)} newly added docs in local results"
		)
		print()

		print("🎉 All steps completed successfully!")
		print("=" * 80)

	except Exception as error:
		print()
		print("=" * 80)
		print("❌ STEPS FAILED")
		print("=" * 80)
		print(f"Error: {error}")
		import traceback

		print()
		print("Stack trace:")
		traceback.print_exc()
		print("=" * 80)
		raise

	finally:
		print()
		await delete_index(MOSS_INDEX_NAME)


if __name__ == "__main__":
	asyncio.run(main())
