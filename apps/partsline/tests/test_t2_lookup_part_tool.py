from __future__ import annotations

import asyncio
from dataclasses import dataclass
import importlib
import os
from types import SimpleNamespace
from typing import Any, ClassVar
import unittest
from unittest.mock import patch

import seed


JsonObject = dict[str, Any]


@dataclass
class FakeMossDoc:
    id: str
    text: str
    metadata: dict[str, str]
    score: float = 1.0


class FakeMossClient:
    docs: ClassVar[list[FakeMossDoc]] = []
    instances: ClassVar[list["FakeMossClient"]] = []

    def __init__(self, project_id: str, project_key: str) -> None:
        self.project_id = project_id
        self.project_key = project_key
        self.loaded_indexes: list[str] = []
        self.queries: list[tuple[str, str, object]] = []
        self.instances.append(self)

    async def load_index(self, index_name: str) -> None:
        self.loaded_indexes.append(index_name)

    async def query(self, index_name: str, text: str, options: object) -> object:
        self.queries.append((index_name, text, options))
        filter_obj = getattr(options, "filter")
        matching_docs = [
            doc
            for doc in self.docs
            if filter_matches(filter_obj, doc.metadata)
            and text_matches_part_query(text, doc)
        ]
        return SimpleNamespace(docs=matching_docs)


def catalog_doc(document_id: str) -> FakeMossDoc:
    for entry in seed.load_catalog_entries():
        if entry["id"] == document_id:
            return FakeMossDoc(
                id=entry["id"], text=entry["text"], metadata=entry["metadata"]
            )

    raise AssertionError(f"missing catalog fixture {document_id}")


def text_matches_part_query(query: str, doc: FakeMossDoc) -> bool:
    normalized_query = query.lower()
    metadata = doc.metadata
    searchable_values = [
        metadata.get("category", ""),
        metadata.get("part_number", ""),
        doc.text,
    ]
    return any(
        value.lower() in normalized_query or normalized_query in value.lower()
        for value in searchable_values
    )


def filter_matches(filter_obj: JsonObject, metadata: dict[str, str]) -> bool:
    if "$and" in filter_obj:
        conditions = filter_obj["$and"]
    else:
        conditions = [filter_obj]

    for condition in conditions:
        field = condition["field"]
        expected = condition["condition"]["$eq"]
        if metadata.get(field) != expected:
            return False

    return True


def flatten_filter(filter_obj: JsonObject) -> dict[str, str]:
    if "$and" in filter_obj:
        conditions = filter_obj["$and"]
    else:
        conditions = [filter_obj]

    return {
        condition["field"]: condition["condition"]["$eq"] for condition in conditions
    }


def run_lookup(**kwargs: str) -> tuple[dict[str, object], FakeMossClient]:
    lookup_part_module = importlib.import_module("agent.tools.lookup_part")
    lookup_part_module.reset_moss_client_cache()
    FakeMossClient.instances.clear()

    with (
        patch.object(lookup_part_module, "MossClient", FakeMossClient),
        patch.dict(
            os.environ,
            {
                "MOSS_PROJECT": "test-project",
                "MOSS_API_KEY": "test-key",
            },
        ),
    ):
        result = asyncio.run(lookup_part_module.lookup_part(**kwargs))

    return result, FakeMossClient.instances[0]


class T2LookupPartToolTest(unittest.TestCase):
    def setUp(self) -> None:
        lookup_part_module = importlib.import_module("agent.tools.lookup_part")
        lookup_part_module.reset_moss_client_cache()
        FakeMossClient.instances.clear()

    def test_dual_engine_vehicle_returns_ambiguous_and_uses_vehicle_filter(
        self,
    ) -> None:
        FakeMossClient.docs = [
            catalog_doc("belt-2.5-outback"),
            catalog_doc("belt-3.6-outback"),
            catalog_doc("belt-f150"),
        ]

        result, client = run_lookup(
            part="  SERPENTINE   BELT  ",
            year="2014",
            make=" subaru ",
            model="outback",
        )

        self.assertEqual(
            result,
            {
                "status": "ambiguous",
                "attribute": "engine",
                "candidates": ["2.5", "3.6"],
            },
        )
        self.assertEqual(client.loaded_indexes, ["parts-catalog-test"])
        self.assertEqual(len(client.queries), 1)

        index_name, text, options = client.queries[0]
        self.assertEqual(index_name, "parts-catalog-test")
        self.assertEqual(text, "SERPENTINE BELT")
        self.assertEqual(
            flatten_filter(getattr(options, "filter")),
            {
                "year": "2014",
                "make": "Subaru",
                "model": "Outback",
                "category": "belts",
            },
        )

    def test_absent_vehicle_returns_no_match_from_filtered_query(self) -> None:
        FakeMossClient.docs = [
            catalog_doc("pads-camry"),
            catalog_doc("pads-civic-2013"),
        ]

        result, client = run_lookup(
            part="front brake pads",
            year="2019",
            make="Toyota",
            model="RAV4",
        )

        self.assertEqual(result, {"status": "no_match"})
        self.assertEqual(len(client.queries), 1)
        self.assertEqual(
            flatten_filter(getattr(client.queries[0][2], "filter")),
            {
                "year": "2019",
                "make": "Toyota",
                "model": "RAV4",
                "category": "brakes",
            },
        )

    def test_superseded_part_returns_replacement_price_and_stock(self) -> None:
        FakeMossClient.docs = [
            catalog_doc("filter-a100"),
            catalog_doc("filter-a100b"),
        ]

        result, _client = run_lookup(
            part="A-100",
            year="2015",
            make="Toyota",
            model="Camry",
            engine="2.5",
        )

        self.assertEqual(
            result,
            {
                "status": "superseded",
                "old_part_number": "A-100",
                "replacement_part_number": "A-100B",
                "price": "8.49",
                "stock": 11,
            },
        )

    def test_normal_part_returns_single_match_with_price_and_stock(self) -> None:
        FakeMossClient.docs = [catalog_doc("pads-camry")]

        result, _client = run_lookup(
            part="front brake pads",
            year="2015",
            make="Toyota",
            model="Camry",
            engine="2.5",
        )

        self.assertEqual(
            result,
            {
                "status": "single_match",
                "part_number": "BP-2201",
                "price": "36.75",
                "stock": 6,
            },
        )

    def test_sequential_lookups_reuse_loaded_moss_client(self) -> None:
        FakeMossClient.docs = [catalog_doc("pads-camry")]
        lookup_part_module = importlib.import_module("agent.tools.lookup_part")
        FakeMossClient.instances.clear()

        async def run_two_lookups() -> tuple[object, object]:
            first = await lookup_part_module.lookup_part(
                part="front brake pads",
                year="2015",
                make="Toyota",
                model="Camry",
                engine="2.5",
            )
            second = await lookup_part_module.lookup_part(
                part="front brake pads",
                year="2015",
                make="Toyota",
                model="Camry",
                engine="2.5",
            )
            return first, second

        with (
            patch.object(lookup_part_module, "MossClient", FakeMossClient),
            patch.dict(
                os.environ,
                {
                    "MOSS_PROJECT": "test-project",
                    "MOSS_API_KEY": "test-key",
                },
            ),
        ):
            first, second = asyncio.run(run_two_lookups())

        self.assertEqual(first, second)
        self.assertEqual(len(FakeMossClient.instances), 1)
        client = FakeMossClient.instances[0]
        self.assertEqual(client.loaded_indexes, ["parts-catalog-test"])
        self.assertEqual(len(client.queries), 2)

    def test_missing_required_vehicle_attribute_refuses_before_querying(self) -> None:
        FakeMossClient.docs = [catalog_doc("pads-camry")]

        lookup_part_module = importlib.import_module("agent.tools.lookup_part")
        FakeMossClient.instances.clear()

        with (
            patch.object(lookup_part_module, "MossClient", FakeMossClient),
            patch.dict(
                os.environ,
                {
                    "MOSS_PROJECT": "test-project",
                    "MOSS_API_KEY": "test-key",
                },
            ),
        ):
            with self.assertRaises(ValueError):
                asyncio.run(
                    lookup_part_module.lookup_part(
                        part="front brake pads",
                        year="2015",
                        make="Toyota",
                        model="",
                    )
                )

        self.assertEqual(FakeMossClient.instances, [])
