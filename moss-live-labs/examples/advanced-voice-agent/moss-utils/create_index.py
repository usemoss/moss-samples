"""Create a searchable index from a PDF using the Moss parse pipeline."""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

from moss import MossClient, ParseFileInput  # noqa: E402

PROJECT_ID = os.getenv("MOSS_PROJECT_ID")
PROJECT_KEY = os.getenv("MOSS_PROJECT_KEY")
PDF_PATH = "Harry-Potter-Resume.pdf"
INDEX_NAME = "Harry-Potter-Persona"



async def main():
    client = MossClient(PROJECT_ID, PROJECT_KEY)

    result = await client.create_index_from_files(
        INDEX_NAME,
        [ParseFileInput(name=os.path.basename(PDF_PATH), content_type="application/pdf", path=PDF_PATH)],
    )
    print(f"Index created: {result.index_name} ({result.doc_count} chunks)")


if __name__ == "__main__":
    asyncio.run(main())
