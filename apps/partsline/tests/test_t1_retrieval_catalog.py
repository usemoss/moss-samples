from __future__ import annotations

import asyncio
from collections.abc import Callable
from collections.abc import Coroutine
from dataclasses import dataclass
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, ClassVar, cast
import unittest


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "catalog" / "demo_catalog.json"
SEED_PATH = ROOT / "seed.py"

JsonObject = dict[str, Any]


def load_catalog() -> list[JsonObject]:
    with CATALOG_PATH.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise AssertionError("catalog must be a JSON object")

    documents = payload.get("documents")
    if not isinstance(documents, list):
        raise AssertionError("catalog must contain a documents list")

    for document in documents:
        if not isinstance(document, dict):
            raise AssertionError("catalog documents must be JSON objects")

    return cast(list[JsonObject], documents)


def metadata(document: JsonObject) -> dict[str, str]:
    raw_metadata = document.get("metadata")
    if not isinstance(raw_metadata, dict):
        raise AssertionError("catalog document metadata must be an object")

    return cast(dict[str, str], raw_metadata)


def matching(documents: list[JsonObject], **expected: str) -> list[JsonObject]:
    return [
        document
        for document in documents
        if all(metadata(document).get(key) == value for key, value in expected.items())
    ]


@dataclass
class FakeDocumentInfo:
    id: str
    text: str
    metadata: dict[str, str]


class FakeMossClient:
    instances: ClassVar[list["FakeMossClient"]] = []
    created_indexes: ClassVar[list[tuple[str, list[FakeDocumentInfo], str]]] = []

    def __init__(self, project_id: str, project_key: str) -> None:
        self.project_id = project_id
        self.project_key = project_key
        self.instances.append(self)

    async def create_index(
        self, index_name: str, docs: list[FakeDocumentInfo], model: str
    ) -> None:
        self.created_indexes.append((index_name, docs, model))


def load_seed_module(env: dict[str, str] | None = None) -> ModuleType:
    moss_module = ModuleType("moss")
    setattr(moss_module, "MossClient", FakeMossClient)
    setattr(moss_module, "DocumentInfo", FakeDocumentInfo)

    dotenv_module = ModuleType("dotenv")
    setattr(dotenv_module, "load_dotenv", lambda: None)

    previous_moss = sys.modules.get("moss")
    previous_dotenv = sys.modules.get("dotenv")
    env_keys = [
        "MOSS_PROJECT",
        "MOSS_API_KEY",
        "MOSS_PROJECT_ID",
        "MOSS_PROJECT_KEY",
    ]
    previous_env = {key: os.environ.get(key) for key in env_keys}

    sys.modules["moss"] = moss_module
    sys.modules["dotenv"] = dotenv_module
    for key in env_keys:
        os.environ.pop(key, None)
    os.environ.update(
        env
        or {
            "MOSS_PROJECT": "test-project-id",
            "MOSS_API_KEY": "test-project-key",
        }
    )

    try:
        spec = importlib.util.spec_from_file_location("partsline_seed", SEED_PATH)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous_moss is None:
            sys.modules.pop("moss", None)
        else:
            sys.modules["moss"] = previous_moss

        if previous_dotenv is None:
            sys.modules.pop("dotenv", None)
        else:
            sys.modules["dotenv"] = previous_dotenv

        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def with_moss_env(env: dict[str, str], callback: Callable[[], None]) -> None:
    env_keys = [
        "MOSS_PROJECT",
        "MOSS_API_KEY",
        "MOSS_PROJECT_ID",
        "MOSS_PROJECT_KEY",
    ]
    previous_env = {key: os.environ.get(key) for key in env_keys}
    for key in env_keys:
        os.environ.pop(key, None)
    os.environ.update(env)

    try:
        callback()
    finally:
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class T1RetrievalCatalogTest(unittest.TestCase):
    def test_catalog_json_contains_required_traps_without_midyear_splits(self) -> None:
        self.assertTrue(CATALOG_PATH.exists())

        documents = load_catalog()
        self.assertGreaterEqual(len(documents), 8)

        for document in documents:
            self.assertIsInstance(document.get("id"), str)
            self.assertIsInstance(document.get("text"), str)
            for value in metadata(document).values():
                self.assertIsInstance(value, str)

            lowered_text = str(document.get("text", "")).lower()
            self.assertNotIn("prod_cutoff", metadata(document))
            self.assertNotIn("production_date", metadata(document))
            self.assertNotIn("before march", lowered_text)
            self.assertNotIn("from march", lowered_text)

        outback_belts = matching(
            documents,
            category="belts",
            make="Subaru",
            model="Outback",
            year="2014",
        )
        self.assertEqual(
            {metadata(document)["engine"] for document in outback_belts},
            {"2.5", "3.6"},
        )
        self.assertEqual(
            len({metadata(document)["part_number"] for document in outback_belts}), 2
        )

        docs_by_part = {
            metadata(document)["part_number"]: document
            for document in documents
            if "part_number" in metadata(document)
        }
        old_filter = metadata(docs_by_part["A-100"])
        replacement_filter = metadata(docs_by_part["A-100B"])
        self.assertEqual(old_filter["stock"], "0")
        self.assertEqual(old_filter["superseded_by"], "A-100B")
        self.assertGreater(int(replacement_filter["stock"]), 0)
        self.assertNotIn("superseded_by", replacement_filter)

        self.assertTrue(
            [
                document
                for document in documents
                if metadata(document).get("universal") == "true"
            ]
        )

        camry_brakes = matching(
            documents,
            category="brakes",
            make="Toyota",
            model="Camry",
            year="2015",
            engine="2.5",
        )
        self.assertEqual(len(camry_brakes), 1)
        self.assertEqual(metadata(camry_brakes[0])["part_number"], "BP-2201")

        self.assertFalse(matching(documents, make="Toyota", model="RAV4"))

    def test_seed_builds_moss_documents_from_catalog_json_only_when_run(self) -> None:
        FakeMossClient.instances.clear()
        FakeMossClient.created_indexes.clear()

        seed = load_seed_module()

        self.assertEqual(FakeMossClient.created_indexes, [])
        self.assertEqual(getattr(seed, "CATALOG_PATH"), CATALOG_PATH)

        build_documents_obj = getattr(seed, "build_documents", None)
        self.assertTrue(callable(build_documents_obj))
        build_documents = cast(
            Callable[[], list[FakeDocumentInfo]], build_documents_obj
        )

        catalog = load_catalog()
        docs = build_documents()

        self.assertEqual(len(docs), len(catalog))
        self.assertEqual([doc.id for doc in docs], [str(doc["id"]) for doc in catalog])
        self.assertEqual(
            [doc.text for doc in docs], [str(doc["text"]) for doc in catalog]
        )
        self.assertEqual(
            [doc.metadata for doc in docs], [metadata(doc) for doc in catalog]
        )

    def test_seed_uses_committed_moss_env_names_when_creating_client(self) -> None:
        FakeMossClient.instances.clear()
        FakeMossClient.created_indexes.clear()
        seed = load_seed_module(
            {
                "MOSS_PROJECT": "project-from-env-template",
                "MOSS_API_KEY": "key-from-env-template",
            }
        )

        main_obj = getattr(seed, "main", None)
        self.assertTrue(callable(main_obj))
        main = cast(Callable[[], Coroutine[Any, Any, None]], main_obj)

        with_moss_env(
            {
                "MOSS_PROJECT": "project-from-env-template",
                "MOSS_API_KEY": "key-from-env-template",
            },
            lambda: asyncio.run(main()),
        )

        self.assertEqual(
            [
                (client.project_id, client.project_key)
                for client in FakeMossClient.instances
            ],
            [("project-from-env-template", "key-from-env-template")],
        )
        self.assertEqual(len(FakeMossClient.created_indexes), 1)
