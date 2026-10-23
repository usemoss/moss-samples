"""Grounded part lookup tool backed by vehicle-filtered Moss queries."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterable
from typing import Any, Literal, NotRequired, Protocol, TypedDict, cast

from moss import MossClient, QueryOptions

from query import INDEX_NAME, moss_credentials
from seed import load_catalog_entries


LookupStatus = Literal["single_match", "ambiguous", "superseded", "no_match"]
VehicleFilter = dict[str, str]
MossFilter = dict[str, Any]


# Maps a spoken part phrase to a catalog category. Keyed by the category value
# stored in the catalog metadata; values are substrings to look for in the
# caller's requested part text. First match wins.
PART_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "belts": ("belt",),
    "brakes": ("brake", "pad", "rotor", "caliper"),
    "filters": ("filter",),
    "batteries": ("battery", "batteries"),
    "wipers": ("wiper", "blade"),
}


class MossDoc(Protocol):
    id: str
    text: str
    metadata: dict[str, str]


class QueryResult(Protocol):
    docs: list[MossDoc]


class MossLookupClient(Protocol):
    async def load_index(self, index_name: str) -> object: ...

    async def query(
        self, index_name: str, text: str, options: QueryOptions
    ) -> object: ...


class SingleMatchResult(TypedDict):
    status: Literal["single_match"]
    part_number: str
    price: str
    stock: int


class AmbiguousResult(TypedDict):
    status: Literal["ambiguous"]
    attribute: str
    candidates: list[str]


class SupersededResult(TypedDict):
    status: Literal["superseded"]
    old_part_number: str
    replacement_part_number: str
    price: str
    stock: int


class NoMatchResult(TypedDict):
    status: Literal["no_match"]


LookupResult = SingleMatchResult | AmbiguousResult | SupersededResult | NoMatchResult


class CatalogEntry(TypedDict):
    id: str
    text: str
    metadata: dict[str, str]


class PartRecord(TypedDict):
    part_number: str
    price: str
    stock: int
    metadata: dict[str, str]
    superseded_by: NotRequired[str]


_moss_client_cache: MossLookupClient | None = None
_moss_client_cache_lock: asyncio.Lock | None = None


def reset_moss_client_cache() -> None:
    global _moss_client_cache, _moss_client_cache_lock
    _moss_client_cache = None
    _moss_client_cache_lock = None


def _moss_client_lock() -> asyncio.Lock:
    global _moss_client_cache_lock
    if _moss_client_cache_lock is None:
        _moss_client_cache_lock = asyncio.Lock()
    return _moss_client_cache_lock


async def _loaded_moss_client() -> MossLookupClient:
    global _moss_client_cache

    if _moss_client_cache is not None:
        return _moss_client_cache

    async with _moss_client_lock():
        if _moss_client_cache is None:
            client = MossClient(*moss_credentials())
            await client.load_index(INDEX_NAME)
            _moss_client_cache = client

    assert _moss_client_cache is not None
    return _moss_client_cache


async def warm_moss_client_cache() -> None:
    await _loaded_moss_client()


def normalize_part(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("part is required")
    return normalized


def infer_category(part: str) -> str | None:
    """Derive the catalog category from the requested part text.

    "serpentine belt" -> "belts", "oil filter" -> "filters",
    "brake pads" -> "brakes". Returns None when nothing matches, in which
    case the lookup falls back to vehicle-only filtering.
    """
    text = part.lower()
    for category, keywords in PART_CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category
    return None


def normalize_year(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("year is required")
    return normalized


def normalize_title(value: str, field: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError(f"{field} is required")
    return normalized.title()


def normalize_model(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("model is required")
    if any(character.isdigit() for character in normalized):
        return normalized.upper()
    return normalized.title()


def normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = " ".join(value.strip().split())
    # Strip engine unit noise: "2.5 liter", "2.5-liter", "2.5L" -> "2.5"
    # This handles the case where the LLM transcribes "two point five liter" from speech
    normalized = re.sub(
        r"[\s-]*(?:liter|litre|l)\b", "", normalized, flags=re.IGNORECASE
    )
    normalized = normalized.strip()
    return normalized or None


def vehicle_filter(
    *,
    year: str,
    make: str,
    model: str,
    engine: str | None = None,
    trim: str | None = None,
) -> VehicleFilter:
    filters = {
        "year": normalize_year(year),
        "make": normalize_title(make, "make"),
        "model": normalize_model(model),
    }

    normalized_engine = normalize_optional(engine)
    if normalized_engine is not None:
        filters["engine"] = normalized_engine

    normalized_trim = normalize_optional(trim)
    if normalized_trim is not None:
        filters["trim"] = normalized_trim

    return filters


def moss_filter(filters: VehicleFilter) -> MossFilter:
    conditions = [
        {"field": field, "condition": {"$eq": value}}
        for field, value in filters.items()
    ]
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


def part_index() -> dict[str, PartRecord]:
    records: dict[str, PartRecord] = {}
    for entry in load_catalog_entries():
        metadata = entry["metadata"]
        part_number = metadata.get("part_number")
        if not part_number:
            continue

        stock = int(metadata.get("stock", "0"))
        record: PartRecord = {
            "part_number": part_number,
            "price": metadata["price"],
            "stock": stock,
            "metadata": metadata,
        }
        superseded_by = metadata.get("superseded_by")
        if superseded_by:
            record["superseded_by"] = superseded_by
        records[part_number] = record

    return records


def get_stock(part_number: str) -> int:
    try:
        return part_index()[part_number]["stock"]
    except KeyError as exc:
        raise ValueError(f"unknown part number: {part_number}") from exc


def current_replacement(part_number: str) -> PartRecord:
    records = part_index()
    current = records[part_number]
    seen = {part_number}

    while "superseded_by" in current:
        next_part_number = current["superseded_by"]
        if next_part_number in seen:
            raise ValueError(f"supersession loop at part number: {next_part_number}")
        seen.add(next_part_number)
        current = records[next_part_number]

    return current


def matching_metadata(doc: MossDoc) -> dict[str, str]:
    return dict(doc.metadata)


def live_matches(docs: Iterable[MossDoc]) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    for doc in docs:
        metadata = matching_metadata(doc)
        if metadata.get("superseded_by"):
            matches.append(metadata)
            continue

        if int(metadata.get("stock", "0")) == 0:
            continue

        matches.append(metadata)

    return matches


def differing_attribute(matches: list[dict[str, str]]) -> tuple[str, list[str]]:
    for attribute in ("engine", "trim"):
        values = sorted(
            {
                metadata[attribute]
                for metadata in matches
                if metadata.get(attribute) is not None
            }
        )
        if len(values) > 1:
            return attribute, values

    part_numbers = sorted({metadata["part_number"] for metadata in matches})
    return "part_number", part_numbers


def format_single_match(metadata: dict[str, str]) -> SingleMatchResult:
    part_number = metadata["part_number"]
    return {
        "status": "single_match",
        "part_number": part_number,
        "price": metadata["price"],
        "stock": get_stock(part_number),
    }


def format_superseded(metadata: dict[str, str]) -> SupersededResult:
    old_part_number = metadata["part_number"]
    replacement = current_replacement(old_part_number)
    replacement_part_number = replacement["part_number"]
    return {
        "status": "superseded",
        "old_part_number": old_part_number,
        "replacement_part_number": replacement_part_number,
        "price": replacement["price"],
        "stock": get_stock(replacement_part_number),
    }


async def filtered_moss_query(part: str, filters: VehicleFilter) -> list[MossDoc]:
    client = await _loaded_moss_client()
    result = cast(
        QueryResult,
        await client.query(
            INDEX_NAME,
            part,
            QueryOptions(top_k=10, alpha=0.8, filter=moss_filter(filters)),
        ),
    )
    return result.docs


async def lookup_part(
    part: str,
    year: str,
    make: str,
    model: str,
    engine: str | None = None,
    trim: str | None = None,
) -> LookupResult:
    normalized_part = normalize_part(part)
    filters = vehicle_filter(
        year=year, make=make, model=model, engine=engine, trim=trim
    )

    # Constrain by part category so a vehicle that has parts of other
    # categories can never return the wrong part type. A belt request must
    # never come back as a filter.
    category = infer_category(normalized_part)
    if category is not None:
        filters["category"] = category

    docs = await filtered_moss_query(normalized_part, filters)

    if not docs:
        return {"status": "no_match"}

    matches = live_matches(docs)

    # Safety net: even if the category filter let something through, drop any
    # match whose category doesn't match what was asked for.
    if category is not None:
        matches = [
            metadata for metadata in matches if metadata.get("category") == category
        ]

    if not matches:
        return {"status": "no_match"}

    superseded_matches = [
        metadata for metadata in matches if metadata.get("superseded_by")
    ]
    if superseded_matches:
        return format_superseded(superseded_matches[0])

    if len(matches) > 1:
        attribute, candidates = differing_attribute(matches)
        return {
            "status": "ambiguous",
            "attribute": attribute,
            "candidates": candidates,
        }

    return format_single_match(matches[0])
