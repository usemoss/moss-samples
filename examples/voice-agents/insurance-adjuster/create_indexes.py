"""Build Moss indexes for the Insurance Claims Adjuster voice agent.

Two index types:

  1. Per-policy index  — ``policy-<policy_number_lower>``
     One index per policyholder. Contains declarations, coverage limits,
     endorsements, prior claims, and property details for that specific policy.

  2. Shared claims-kb  — ``claims-kb``
     One shared index containing HO-3 standard policy language, coverage rules,
     state guidelines, and optionally crawled public insurance documentation.
     All adjusters query this index on every turn; per-policy indexes are loaded
     on demand when a specific policy is identified.

Run (build everything):

    uv run python create_indexes.py

Build a single policy index:

    uv run python create_indexes.py --policy FL-HO3-001

Build only the shared KB (useful after running ingest/crawl.py):

    uv run python create_indexes.py --kb-only

Rebuild the shared KB including crawled docs:

    uv run python create_indexes.py --kb-only --include-crawled data/crawled_kb.json

List available policy fixtures:

    uv run python create_indexes.py --list
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from moss import DocumentInfo, MossClient

load_dotenv()

POLICY_DIR = Path(__file__).parent / "data" / "policies"
CLAIMS_KB_PATH = Path(__file__).parent / "data" / "claims_kb.json"

CLAIMS_KB_INDEX = "claims-kb"


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Copy .env.example to .env and fill in your credentials."
        )
    return value


# ---------------------------------------------------------------------------
# Policy fixture discovery
# ---------------------------------------------------------------------------


def _discover_policies() -> dict[str, Path]:
    """Map policy_number (uppercase) to its fixture JSON path."""
    out: dict[str, Path] = {}
    for path in sorted(POLICY_DIR.glob("policy_*.json")):
        # filename pattern: policy_HO3_FL001.json → key "FL-HO3-001" not enforced;
        # policy_number is read from the summary doc inside the fixture
        docs = json.loads(path.read_text())
        summary = next((d for d in docs if d["id"] == "policy-summary"), None)
        if summary:
            # Extract policy number from the summary text: "Policy number FL-HO3-001."
            text = summary["text"]
            import re

            m = re.search(r"Policy number\s+([\w\-]+)", text, re.IGNORECASE)
            if m:
                policy_num = m.group(1).strip().upper()
                out[policy_num] = path
    return out


def _index_name_for(policy_number: str) -> str:
    return f"policy-{policy_number.lower()}"


def _load_json_docs(path: Path) -> list[DocumentInfo]:
    raw = json.loads(path.read_text())
    return [
        DocumentInfo(
            id=doc["id"],
            text=doc["text"],
            metadata={k: str(v) for k, v in doc.get("metadata", {}).items()},
        )
        for doc in raw
    ]


def _load_raw_dicts(path: Path) -> list[dict]:
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Index builders
# ---------------------------------------------------------------------------


async def build_policy_index(client: MossClient, policy_number: str, path: Path) -> str:
    index = _index_name_for(policy_number)
    docs = _load_json_docs(path)
    print(f"  building {index} ({len(docs)} docs from {path.name})...")
    await client.create_index(index, docs)
    return index


async def build_claims_kb(
    client: MossClient,
    extra_paths: list[Path] | None = None,
) -> str:
    """Build the shared claims-kb index from the hand-authored KB and optional crawled docs."""
    all_raw: list[dict] = _load_raw_dicts(CLAIMS_KB_PATH)
    print(f"  hand-authored KB: {len(all_raw)} docs from {CLAIMS_KB_PATH.name}")

    if extra_paths:
        for ep in extra_paths:
            if not ep.exists():
                print(f"  WARNING: crawled file not found: {ep} — skipping")
                continue
            crawled = _load_raw_dicts(ep)
            print(f"  crawled KB: {len(crawled)} docs from {ep.name}")
            # Deduplicate by ID
            existing_ids = {d["id"] for d in all_raw}
            new_docs = [d for d in crawled if d["id"] not in existing_ids]
            print(f"    → {len(new_docs)} new docs after dedup")
            all_raw.extend(new_docs)

    docs = [
        DocumentInfo(
            id=d["id"],
            text=d["text"],
            metadata={k: str(v) for k, v in d.get("metadata", {}).items()},
        )
        for d in all_raw
    ]

    print(f"  building {CLAIMS_KB_INDEX} ({len(docs)} total docs)...")
    await client.create_index(CLAIMS_KB_INDEX, docs)
    return CLAIMS_KB_INDEX


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run(
    only_policy: str | None = None,
    kb_only: bool = False,
    skip_kb: bool = False,
    extra_crawled: list[Path] | None = None,
) -> None:
    project_id = _require_env("MOSS_PROJECT_ID")
    project_key = _require_env("MOSS_PROJECT_KEY")
    client = MossClient(project_id, project_key)

    policies = _discover_policies()

    if not kb_only:
        if only_policy:
            key = only_policy.upper()
            if key not in policies:
                raise SystemExit(
                    f"Policy {key} not found. Available: {', '.join(sorted(policies))}"
                )
            policies = {key: policies[key]}

        print(f"Building {len(policies)} policy index(es)...")
        for policy_num, path in policies.items():
            await build_policy_index(client, policy_num, path)

    if not skip_kb:
        print("\nBuilding shared claims-kb index...")
        await build_claims_kb(client, extra_paths=extra_crawled)

    print("\nAll indexes ready.")
    print(f"  Policy indexes : {[_index_name_for(p) for p in policies]}")
    print(f"  Shared KB index: {CLAIMS_KB_INDEX}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build per-policy and shared claims-kb Moss indexes."
    )
    parser.add_argument(
        "--policy", help="Build a single policy index (e.g. FL-HO3-001)."
    )
    parser.add_argument(
        "--kb-only",
        action="store_true",
        help="Build only the shared claims-kb index (skip per-policy indexes).",
    )
    parser.add_argument(
        "--skip-kb",
        action="store_true",
        help="Skip the shared claims-kb index (build only policy indexes).",
    )
    parser.add_argument(
        "--include-crawled",
        metavar="PATH",
        action="append",
        default=[],
        help="Include a crawled JSON file in the claims-kb (can be specified multiple times).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available policy fixtures and exit.",
    )
    args = parser.parse_args()

    if args.list:
        policies = _discover_policies()
        print("Available policy fixtures:")
        for num, path in sorted(policies.items()):
            print(f"  {num:20} → {path.name}  (index: {_index_name_for(num)})")
        return

    extra = [Path(p) for p in args.include_crawled]
    asyncio.run(
        run(
            only_policy=args.policy,
            kb_only=args.kb_only,
            skip_kb=args.skip_kb,
            extra_crawled=extra if extra else None,
        )
    )


if __name__ == "__main__":
    main()
