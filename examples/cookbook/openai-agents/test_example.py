from __future__ import annotations

import importlib
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class QueryOptions:
    def __init__(self, top_k=None, filter=None):
        self.top_k = top_k
        self.filter = filter


class DocumentInfo:
    def __init__(self, id, text, metadata=None):
        self.id = id
        self.text = text
        self.metadata = metadata


class MossClient:
    pass


class Agent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class Runner:
    @staticmethod
    async def run(agent, question):
        return types.SimpleNamespace(
            agent=agent, question=question, final_output="done"
        )


def function_tool(func):
    func.is_function_tool = True
    return func


def load_dotenv():
    return None


def _import_example_with_stubs():
    cookbook_dir = Path(__file__).resolve().parent
    original_sys_path = sys.path[:]
    missing = object()
    original_modules = {
        name: sys.modules.get(name, missing)
        for name in ("moss", "agents", "dotenv", "example")
    }

    try:
        sys.path.insert(0, str(cookbook_dir))
        sys.modules["moss"] = types.SimpleNamespace(
            DocumentInfo=DocumentInfo,
            MossClient=MossClient,
            QueryOptions=QueryOptions,
        )
        sys.modules["agents"] = types.SimpleNamespace(
            Agent=Agent,
            Runner=Runner,
            function_tool=function_tool,
        )
        sys.modules["dotenv"] = types.SimpleNamespace(load_dotenv=load_dotenv)
        sys.modules.pop("example", None)

        return importlib.import_module("example")
    finally:
        for name, module in original_modules.items():
            if module is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        sys.path[:] = original_sys_path


example = _import_example_with_stubs()


def _doc(doc_id="d1", text="sample text", score=0.9, metadata=None):
    return types.SimpleNamespace(
        id=doc_id,
        text=text,
        score=score,
        metadata=metadata or {},
    )


def _search_result(docs):
    return types.SimpleNamespace(docs=docs)


class TestSearchMoss(unittest.IsolatedAsyncioTestCase):
    async def test_query_is_passed_to_client_query(self):
        client = MagicMock()
        client.query = AsyncMock(return_value=_search_result([_doc()]))

        await example.search_moss(client, "support-index", "refund status")

        client.query.assert_awaited_once()
        self.assertEqual(
            client.query.await_args.args[:2], ("support-index", "refund status")
        )

    async def test_top_k_is_forwarded_to_query_options(self):
        client = MagicMock()
        client.query = AsyncMock(return_value=_search_result([_doc()]))

        await example.search_moss(client, "idx", "refund", top_k=7)

        options = client.query.await_args.kwargs["options"]
        self.assertEqual(options.top_k, 7)

    async def test_metadata_filter_is_forwarded(self):
        client = MagicMock()
        client.query = AsyncMock(return_value=_search_result([_doc()]))
        metadata_filter = {"field": "category", "condition": {"$eq": "policy"}}

        await example.search_moss(
            client,
            "idx",
            "refund",
            top_k=5,
            filter=metadata_filter,
        )

        options = client.query.await_args.kwargs["options"]
        self.assertEqual(options.filter, metadata_filter)

    async def test_filter_none_is_allowed(self):
        client = MagicMock()
        client.query = AsyncMock(return_value=_search_result([_doc()]))

        await example.search_moss(client, "idx", "refund", filter=None)

        options = client.query.await_args.kwargs["options"]
        self.assertIsNone(options.filter)

    async def test_empty_results_produce_clear_response(self):
        client = MagicMock()
        client.query = AsyncMock(return_value=_search_result([]))

        output = await example.search_moss(client, "idx", "unknown")

        self.assertIn("No relevant results found.", output)
        self.assertIn('"results": []', output)

    async def test_invalid_top_k_is_handled_clearly(self):
        client = MagicMock()
        client.query = AsyncMock(return_value=_search_result([]))

        with self.assertRaisesRegex(ValueError, "top_k must be between 1 and 20"):
            await example.search_moss(client, "idx", "refund", top_k=0)

        client.query.assert_not_called()

    async def test_structured_results_include_grounding_fields(self):
        client = MagicMock()
        client.query = AsyncMock(
            return_value=_search_result(
                [
                    _doc(
                        doc_id="refund-policy",
                        text="Refunds take 3-5 business days.",
                        score=0.94,
                        metadata={"category": "policy"},
                    )
                ]
            )
        )

        output = await example.search_moss(client, "idx", "refund")

        self.assertIn('"id": "refund-policy"', output)
        self.assertIn('"text": "Refunds take 3-5 business days."', output)
        self.assertIn('"score": 0.94', output)
        self.assertIn('"metadata"', output)


class TestEnvironmentValidation(unittest.TestCase):
    def test_missing_env_vars_are_reported_together(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "MOSS_PROJECT_ID"):
                example._require_env_vars()

        try:
            with patch.dict(os.environ, {}, clear=True):
                example._require_env_vars()
        except RuntimeError as exc:
            message = str(exc)
        else:
            self.fail("_require_env_vars should have raised RuntimeError")

        self.assertIn("MOSS_PROJECT_KEY", message)
        self.assertIn("MOSS_INDEX_NAME", message)
        self.assertIn("OPENAI_API_KEY", message)


class TestAgentSetup(unittest.IsolatedAsyncioTestCase):
    async def test_load_index_happens_before_runner_run(self):
        events = []
        client = MagicMock()

        async def load_index(index_name):
            events.append(("load_index", index_name))

        class RecordingRunner:
            @staticmethod
            async def run(agent, question):
                events.append(
                    ("run", question, agent.kwargs["tools"][0].is_function_tool)
                )
                return types.SimpleNamespace(final_output="answer")

        client.load_index = AsyncMock(side_effect=load_index)

        with patch.object(example, "Runner", RecordingRunner):
            result = await example.run_agent(client, "idx", "How long do refunds take?")

        self.assertEqual(result.final_output, "answer")
        self.assertEqual(events[0], ("load_index", "idx"))
        self.assertEqual(events[1], ("run", "How long do refunds take?", True))


if __name__ == "__main__":
    unittest.main()
