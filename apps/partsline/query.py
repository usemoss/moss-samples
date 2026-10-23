"""
query.py - interactive fitment-question tester.
Run:  python query.py
Type a search, optionally add filters like:  make=Subaru model=Outback year=2014 engine=2.5
Example:  serpentine belt | make=Subaru model=Outback year=2014
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from dotenv import load_dotenv
from moss import MossClient, QueryOptions


load_dotenv()
INDEX_NAME = "parts-catalog-test"


def moss_credentials() -> tuple[str, str]:
    project_id = os.environ.get("MOSS_PROJECT") or os.environ.get("MOSS_PROJECT_ID")
    project_key = os.environ.get("MOSS_API_KEY") or os.environ.get("MOSS_PROJECT_KEY")
    if not project_id or not project_key:
        raise RuntimeError("Moss environment is not configured")
    return project_id, project_key


def parse(line: str) -> tuple[str, dict[str, Any] | None]:
    if "|" not in line:
        return line.strip(), None

    text, filt = line.split("|", 1)
    conds = []
    for pair in filt.strip().split():
        key, value = pair.split("=", 1)
        conds.append({"field": key, "condition": {"$eq": value}})

    filters = conds[0] if len(conds) == 1 else {"$and": conds}
    return text.strip(), filters


async def main() -> None:
    client = MossClient(*moss_credentials())
    print("Loading index...")
    await client.load_index(INDEX_NAME)
    print("Ready. Type queries ('quit' to exit).")
    print("Format:  <search text> | key=val key=val   (filters optional)\n")
    while True:
        line = input("query> ").strip()
        if line.lower() in ("quit", "exit"):
            break
        if not line:
            continue
        text, filters = parse(line)
        opts = (
            QueryOptions(top_k=5, alpha=0.8, filter=filters)
            if filters
            else QueryOptions(top_k=5, alpha=0.8)
        )
        result = await client.query(INDEX_NAME, text, opts)
        time_taken = (
            result.time_taken_in_ms if hasattr(result, "time_taken_in_ms") else "?"
        )
        print(f"  ({time_taken} ms)")
        for doc in result.docs:
            print(f"  [{doc.score:.3f}] {doc.id}  ::  {doc.text[:70]}")
            print(f"          {doc.metadata}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
