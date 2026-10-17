"""Create the hackathon FAQ index in Moss from data/hackathon_faq.json.

    python build_index.py     # run once before voice_agent.py
"""
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from moss import DocumentInfo, MossClient

load_dotenv()
INDEX = os.getenv("MOSS_INDEX_NAME", "hackathon")


async def main():
    client = MossClient(os.environ["MOSS_PROJECT_ID"], os.environ["MOSS_PROJECT_KEY"])
    entries = json.loads(Path("data/hackathon_faq.json").read_text())
    docs = [DocumentInfo(id=e["id"], text=e["text"]) for e in entries]

    print(f"indexing {len(docs)} entries into '{INDEX}'...")
    await client.create_index(INDEX, docs, model_id="moss-minilm")
    print("done. now run: python voice_agent.py console")


if __name__ == "__main__":
    asyncio.run(main())
