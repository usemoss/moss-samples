"""Create or refresh a MOSS index from a directory of documents.

Each subdirectory under the docs root maps to one index.  The index name
is taken from --index-name so it can reflect the agent persona, e.g.
"customer_support", "product_faq", "hr_policies".

Usage:
    python create_index.py --index-name customer_support --docs-dir ./docs/customer_support
    python create_index.py --index-name product_faq --docs-dir ./docs/product_faq
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from moss import DocumentInfo, MossClient

load_dotenv(".env")

SUPPORTED_EXTENSIONS = {".txt", ".md"}
DEFAULT_MODEL_ID = "moss-minilm"


def load_docs_from_dir(docs_dir: Path) -> list[DocumentInfo]:
    """Read all supported text files from *docs_dir* recursively."""
    if not docs_dir.exists():
        raise FileNotFoundError(f"Docs directory not found: {docs_dir}")

    documents: list[DocumentInfo] = []
    for path in sorted(docs_dir.rglob("*")):
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        doc_id = str(path.relative_to(docs_dir))
        documents.append(
            DocumentInfo(
                id=doc_id,
                text=text,
                metadata={"source": doc_id, "filename": path.name},
            )
        )

    if not documents:
        raise ValueError(
            f"No .txt or .md documents found in {docs_dir}. "
            "Add your documents and re-run."
        )

    return documents


async def create_index(index_name: str, docs_dir: Path) -> None:
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")
    model_id = os.getenv("MOSS_MODEL_ID", DEFAULT_MODEL_ID)

    missing = [
        name
        for name, val in {
            "MOSS_PROJECT_ID": project_id,
            "MOSS_PROJECT_KEY": project_key,
        }.items()
        if not val
    ]
    if missing:
        raise OSError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    assert project_id is not None
    assert project_key is not None

    documents = load_docs_from_dir(docs_dir)
    client = MossClient(project_id, project_key)

    print(
        f"Creating index '{index_name}' with {len(documents)} documents "
        f"using model '{model_id}'..."
    )
    result = await client.create_index(index_name, documents, model_id)
    print(
        f"Done — job: {result.job_id} | index: {result.index_name} | "
        f"docs: {result.doc_count}"
    )
    print(f"Index '{index_name}' is ready. The voice agent can now search it.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create a MOSS index from a directory of .txt/.md documents."
    )
    parser.add_argument(
        "--index-name",
        required=True,
        help="Name for the index (e.g. customer_support, product_faq). "
        "This name identifies the knowledge base to the voice agent.",
    )
    parser.add_argument(
        "--docs-dir",
        required=True,
        type=Path,
        help="Path to directory containing .txt or .md documents.",
    )
    args = parser.parse_args()

    asyncio.run(create_index(args.index_name, args.docs_dir))
