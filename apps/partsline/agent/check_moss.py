from __future__ import annotations

import asyncio
from pathlib import Path
import sys

from dotenv import load_dotenv
from moss import MossClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query import INDEX_NAME, moss_credentials  # noqa: E402

ENV_PATH = ROOT / ".env"


async def check_moss() -> int:
    load_dotenv(ENV_PATH)
    try:
        client = MossClient(*moss_credentials())
        await client.load_index(INDEX_NAME)
    except Exception as exc:
        print(exc)
        return 1

    print("Moss OK")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(check_moss()))


if __name__ == "__main__":
    main()
