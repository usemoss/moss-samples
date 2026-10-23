from __future__ import annotations

import asyncio
from contextlib import redirect_stdout
from io import StringIO
import importlib.util
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CHECK_MOSS = ROOT / "agent" / "check_moss.py"


def load_check_moss_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_moss_module", CHECK_MOSS)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeMossClient:
    instances: list["FakeMossClient"] = []

    def __init__(self, project_id: str, project_key: str) -> None:
        self.project_id = project_id
        self.project_key = project_key
        self.load_calls: list[str] = []
        self.instances.append(self)

    async def load_index(self, index_name: str) -> None:
        self.load_calls.append(index_name)


class FailingMossClient(FakeMossClient):
    async def load_index(self, index_name: str) -> None:
        self.load_calls.append(index_name)
        raise RuntimeError("Cloud error: Authentication failed: invalid credentials")


class CheckMossTest(unittest.TestCase):
    def setUp(self) -> None:
        FakeMossClient.instances.clear()

    def test_check_moss_loads_env_and_index_once_then_prints_ok(self) -> None:
        module = load_check_moss_module()
        dotenv_paths: list[Path] = []
        output = StringIO()

        module.load_dotenv = dotenv_paths.append
        module.MossClient = FakeMossClient
        module.moss_credentials = lambda: ("project-id", "project-key")

        with redirect_stdout(output):
            exit_code = asyncio.run(module.check_moss())

        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue(), "Moss OK\n")
        self.assertEqual(dotenv_paths, [ROOT / ".env"])
        self.assertEqual(len(FakeMossClient.instances), 1)
        self.assertEqual(FakeMossClient.instances[0].load_calls, [module.INDEX_NAME])

    def test_check_moss_prints_actual_error_and_returns_nonzero(self) -> None:
        module = load_check_moss_module()
        output = StringIO()

        module.load_dotenv = lambda _: None
        module.MossClient = FailingMossClient
        module.moss_credentials = lambda: ("project-id", "project-key")

        with redirect_stdout(output):
            exit_code = asyncio.run(module.check_moss())

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            output.getvalue(),
            "Cloud error: Authentication failed: invalid credentials\n",
        )
        self.assertEqual(FakeMossClient.instances[0].load_calls, [module.INDEX_NAME])
