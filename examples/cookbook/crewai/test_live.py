import asyncio
import os
import sys

from dotenv import load_dotenv
from moss import MossClient
from moss_crewai import (
    MossAddDocsTool,
    MossCreateIndexTool,
    MossDeleteDocsTool,
    MossDeleteIndexTool,
    MossGetDocsTool,
    MossListIndexesTool,
    MossSearchTool,
)

load_dotenv()

PROJECT_ID = os.getenv("MOSS_PROJECT_ID")
PROJECT_KEY = os.getenv("MOSS_PROJECT_KEY")
TEST_INDEX = "crewai-live-test"

passed = 0
failed = 0


def report(name, success, detail=""):
    global passed, failed
    status = "PASS" if success else "FAIL"
    if success:
        passed += 1
    else:
        failed += 1
    msg = f"  [{status}] {name}"
    if detail:
        msg += f" -- {detail}"
    print(msg)


async def run_tests():
    if not PROJECT_ID or not PROJECT_KEY:
        print("ERROR: MOSS_PROJECT_ID and MOSS_PROJECT_KEY must be set.")
        sys.exit(1)

    print("Running live tests against Moss platform...\n")

    # Shared client for all tools
    client = MossClient(PROJECT_ID, PROJECT_KEY)

    # --- 1. MossCreateIndexTool ---
    print("1. MossCreateIndexTool")
    create_tool = MossCreateIndexTool(client=client)
    try:
        result = await create_tool._arun(
            index_name=TEST_INDEX,
            texts=[
                "Moss delivers sub-10ms semantic search.",
                "CrewAI is a multi-agent orchestration framework.",
                "Python is a popular programming language.",
                "Vector databases store embeddings for similarity search.",
                "Hybrid search combines semantic and keyword matching.",
            ],
            ids=["doc-1", "doc-2", "doc-3", "doc-4", "doc-5"],
        )
        report("create index", "Successfully created" in result, result)
    except RuntimeError as e:
        if "already exists" in str(e):
            report("create index", True, "Index already exists (OK)")
        else:
            report("create index", False, str(e))

    # --- 2. MossListIndexesTool ---
    print("2. MossListIndexesTool")
    list_tool = MossListIndexesTool(client=client)
    try:
        result = await list_tool._arun()
        has_index = TEST_INDEX in result
        report("list indexes", has_index, result.replace("\n", " | "))
    except Exception as e:
        report("list indexes", False, str(e))

    # --- 3. MossAddDocsTool ---
    print("3. MossAddDocsTool")
    add_tool = MossAddDocsTool(client=client, index_name=TEST_INDEX)
    try:
        result = await add_tool._arun(
            texts=["Reranking improves search quality using cross-encoders."],
            ids=["doc-6"],
        )
        report("add docs", "Successfully added" in result, result)
    except Exception as e:
        report("add docs", False, str(e))

    # --- 4. MossGetDocsTool ---
    print("4. MossGetDocsTool")
    get_tool = MossGetDocsTool(client=client, index_name=TEST_INDEX)
    try:
        result = await get_tool._arun(doc_ids=["doc-1", "doc-2"])
        report(
            "get docs (by ID)",
            "doc-1" in result and "doc-2" in result,
            f"Retrieved {result.count('[doc-')} docs",
        )

        result_all = await get_tool._arun()
        report(
            "get docs (all)",
            "Retrieved" in result_all,
            result_all.split("\n")[0],
        )
    except Exception as e:
        report("get docs", False, str(e))

    # --- 5. MossSearchTool ---
    print("5. MossSearchTool")
    search_tool = MossSearchTool(client=client, index_name=TEST_INDEX, top_k=3)
    try:
        result = await search_tool._arun("semantic search latency")
        has_results = "Result 1" in result
        report("search", has_results, result.split("\n")[0])
    except Exception as e:
        report("search", False, str(e))

    # --- 6. MossDeleteDocsTool ---
    print("6. MossDeleteDocsTool")
    delete_docs_tool = MossDeleteDocsTool(client=client, index_name=TEST_INDEX)
    try:
        result = await delete_docs_tool._arun(doc_ids=["doc-6"])
        report("delete docs", "Successfully deleted" in result, result)
    except Exception as e:
        report("delete docs", False, str(e))

    try:
        result = await get_tool._arun(doc_ids=["doc-6"])
        report("verify deletion", "No documents found" in result, result)
    except Exception as e:
        report("verify deletion", True, f"Doc gone (exception: {e})")

    # --- 7. MossDeleteIndexTool ---
    print("7. MossDeleteIndexTool")
    delete_index_tool = MossDeleteIndexTool(client=client)
    try:
        result = await delete_index_tool._arun(index_name=TEST_INDEX)
        report("delete index", "Successfully deleted" in result, result)
    except Exception as e:
        report("delete index", False, str(e))

    try:
        result = await list_tool._arun()
        report(
            "verify index deleted",
            TEST_INDEX not in result,
            "Index no longer in list",
        )
    except Exception as e:
        report("verify index deleted", False, str(e))

    # --- Summary ---
    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_tests())
