import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(__file__))

from example_usage import (
    _load_index_before_graph_runs,
    _parse_filter_eq,
    run_langgraph_agent,
)
from moss_langgraph import (
    ask_question,
    build_moss_graph,
)


class TestLangGraphHelpers(unittest.TestCase):
    def test_parse_filter_eq_builds_moss_filter(self):
        self.assertEqual(
            _parse_filter_eq("category=returns"),
            {"field": "category", "condition": {"$eq": "returns"}},
        )

    def test_parse_filter_eq_rejects_invalid_input(self):
        with self.assertRaises(ValueError):
            _parse_filter_eq("category")


class TestLangGraphIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_load_index_before_graph_runs_calls_client(self):
        client = MagicMock()
        client.load_index = AsyncMock()

        await _load_index_before_graph_runs(client, "idx")

        client.load_index.assert_awaited_once_with("idx")

    async def test_ask_question_returns_retrieval_and_answer(self):
        client = MagicMock()
        client.query = AsyncMock(
            return_value=MagicMock(
                docs=[
                    MagicMock(
                        id="faq-returns-1",
                        text="Refunds take 3 to 5 business days.",
                        score=0.99,
                        metadata={"category": "returns"},
                    )
                ],
                time_taken_ms=7,
            )
        )
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=MagicMock(content="Grounded answer"))

        graph = build_moss_graph(client, "idx", llm)
        result = await ask_question(
            graph,
            user_question="What is the refund policy?",
            metadata_filter={"field": "category", "condition": {"$eq": "returns"}},
            top_k=2,
            alpha=0.6,
        )

        self.assertEqual(result["answer"], "Grounded answer")
        self.assertEqual(result["retrieval_time_ms"], 7)
        self.assertEqual(len(result["retrieval_results"].docs), 1)
        self.assertEqual(result["retrieval_results"].docs[0].id, "faq-returns-1")
        self.assertIn("Refunds take 3 to 5 business days.", result["retrieval_context"])

        client.query.assert_awaited_once()
        call_args = client.query.await_args.args
        self.assertEqual(call_args[0], "idx")
        self.assertEqual(call_args[1], "What is the refund policy?")
        self.assertEqual(call_args[2].top_k, 2)
        self.assertAlmostEqual(call_args[2].alpha, 0.6)
        self.assertEqual(
            call_args[2].filter,
            {"field": "category", "condition": {"$eq": "returns"}},
        )

    @patch.dict(
        os.environ,
        {
            "MOSS_PROJECT_ID": "project-id",
            "MOSS_PROJECT_KEY": "project-key",
            "MOSS_INDEX_NAME": "demo-index",
            "GROQ_API_KEY": "groq-key",
            "GROQ_MODEL": "llama-3.3-70b-versatile",
        },
        clear=False,
    )
    @patch("example_usage._print_response")
    @patch("example_usage.ChatGroq")
    @patch("example_usage.MossClient")
    async def test_run_langgraph_agent_single_shot(self, mock_client_cls, mock_groq_cls, mock_print):
        mock_client = mock_client_cls.return_value
        mock_client.load_index = AsyncMock()
        mock_client.query = AsyncMock(
            return_value=MagicMock(
                docs=[
                    MagicMock(
                        id="faq-returns-1",
                        text="Refunds take 3 to 5 business days.",
                        score=1.0,
                        metadata={"category": "returns"},
                    )
                ],
                time_taken_ms=3,
            )
        )

        mock_llm = mock_groq_cls.return_value
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="Grounded answer"))

        await run_langgraph_agent(
            question="What is the refund policy?",
            filter_eq="category=returns",
            top_k=1,
            alpha=0.7,
        )

        mock_client.load_index.assert_awaited_once_with("demo-index")
        mock_client.query.assert_awaited_once()
        self.assertAlmostEqual(mock_client.query.await_args.args[2].alpha, 0.7)
        mock_groq_cls.assert_called_once_with(
            model="llama-3.3-70b-versatile",
            api_key="groq-key",
            temperature=0,
        )
        mock_print.assert_called_once()


if __name__ == "__main__":
    unittest.main()
