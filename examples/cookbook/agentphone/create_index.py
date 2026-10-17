"""One-time setup: create the Moss demo index this cookbook uses.

Run before starting the webhook server::

    uv run python create_index.py

Reads ``MOSS_PROJECT_ID``, ``MOSS_PROJECT_KEY``, and ``MOSS_INDEX_NAME`` from
``.env``. If the index already exists, the script exits without changes.
"""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from moss import DocumentInfo, MossClient

DEMO_DOCS = [
    DocumentInfo(
        id="refunds",
        text="Refunds are processed within 3-5 business days after approval.",
    ),
    DocumentInfo(
        id="support-hours",
        text="Customer support is available Monday to Friday, 9am to 6pm IST.",
    ),
    DocumentInfo(
        id="reset-password",
        text=(
            "To reset your password, go to Settings, then Security, choose "
            "Reset Password, and follow the email verification link."
        ),
    ),
    DocumentInfo(
        id="shipping",
        text="Free shipping on orders over $50 in the contiguous US.",
    ),
    DocumentInfo(
        id="returns",
        text="Returns are accepted within 30 days of purchase with original packaging.",
    ),
]


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


async def main() -> None:
    load_dotenv()
    client = MossClient(
        _require_env("MOSS_PROJECT_ID"),
        _require_env("MOSS_PROJECT_KEY"),
    )
    index_name = _require_env("MOSS_INDEX_NAME")

    existing = await client.list_indexes()
    if any(index.name == index_name for index in existing):
        print(f"Index '{index_name}' already exists. Nothing to do.")
        return

    await client.create_index(index_name, DEMO_DOCS)
    print(f"Created index '{index_name}' with {len(DEMO_DOCS)} demo docs.")


if __name__ == "__main__":
    asyncio.run(main())
