from __future__ import annotations

import ast
import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
AGENT_MAIN = ROOT / "agent" / "main.py"
AGENT_PROMPTS = ROOT / "agent" / "prompts.py"
AGENT_REQUIREMENTS = ROOT / "agent" / "requirements.txt"
ENV_EXAMPLE = ROOT / ".env.example"


class FakeOpenAILLM:
    calls: list[dict[str, object]] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.calls.append(kwargs)


def agent_source() -> str:
    return AGENT_MAIN.read_text(encoding="utf-8")


def agent_tree() -> ast.AST:
    return ast.parse(agent_source())


def load_agent_module():
    spec = importlib.util.spec_from_file_location("partsline_agent_main", AGENT_MAIN)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def call_keyword_values(call_name: str, keyword: str) -> list[ast.AST]:
    values: list[ast.AST] = []
    for node in ast.walk(agent_tree()):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == call_name:
            values.extend(
                keyword_node.value
                for keyword_node in node.keywords
                if keyword_node.arg == keyword
            )
    return values


class T3RetrievalAgentTest(unittest.TestCase):
    def test_requirements_declares_livekit_openai_plugin_extra(self) -> None:
        requirements = AGENT_REQUIREMENTS.read_text(encoding="utf-8").splitlines()

        self.assertIn(
            "livekit-agents[deepgram,cartesia,silero,openai]>=1.6.1,<2",
            requirements,
        )

    def test_prompt_encodes_grounded_lookup_rules(self) -> None:
        self.assertTrue(AGENT_PROMPTS.exists())
        prompt_source = AGENT_PROMPTS.read_text(encoding="utf-8")

        for required_text in [
            "lookup_part",
            "only retrieval tool",
            "year, make, and model",
            "read the vehicle back",
            "never state a part, price, stock level, or fitment",
            "We're showing",
            "We don't carry a match for that vehicle.",
            "2.5 or the 3.6",
            "superseded",
        ]:
            self.assertIn(required_text, prompt_source)

    def test_env_template_uses_groq_and_keeps_dartmouth_chat_fallback(self) -> None:
        env_template = ENV_EXAMPLE.read_text(encoding="utf-8")

        self.assertIn("GROQ_API_KEY=", env_template)
        self.assertIn("DARTMOUTH_CHAT_API_KEY=", env_template)
        self.assertIn("DARTMOUTH_CHAT_BASE_URL=", env_template)
        self.assertIn("DARTMOUTH_CHAT_MODEL=", env_template)
        self.assertNotIn("OPENAI_API_KEY", env_template)

    def test_agent_session_wires_openai_llm_and_tools(self) -> None:
        source = agent_source()

        self.assertIn(
            "from livekit.plugins import cartesia, deepgram, openai, silero", source
        )
        self.assertIn("lookup_part", source)
        self.assertIn(
            "from agent.tools.set_aside import SetAsideResult, set_aside", source
        )
        self.assertIn(
            "from agent.tools.transfer import TransferResult, transfer_to_human",
            source,
        )
        self.assertIn("from agent.prompts import PARTSLINE_SYSTEM_PROMPT", source)
        self.assertIn("function_tool(", source)
        self.assertIn("lookup_part,", source)
        self.assertIn("set_aside_for_session,", source)
        self.assertIn("transfer_to_human_for_session,", source)
        self.assertIn("build_llm", source)
        self.assertIn("build_dartmouth_chat_llm", source)
        self.assertIn("llm=build_llm()", source)
        self.assertNotIn("llm=build_dartmouth_chat_llm()", source)
        self.assertIn(
            "tools=[LOOKUP_PART_TOOL, SET_ASIDE_TOOL, TRANSFER_TO_HUMAN_TOOL]",
            source,
        )
        self.assertNotIn("api.openai.com", source)
        self.assertNotIn("OPENAI_API_KEY", source)
        self.assertNotIn("VoicePipelineAgent", source)
        self.assertNotIn("MultimodalAgent", source)

    def test_dartmouth_chat_llm_uses_required_base_url_key_and_model(self) -> None:
        agent = load_agent_module()
        FakeOpenAILLM.calls.clear()

        with (
            patch.object(agent.openai, "LLM", FakeOpenAILLM),
            patch.dict(
                os.environ,
                {
                    "DARTMOUTH_CHAT_API_KEY": "dartmouth-key",
                    "DARTMOUTH_CHAT_BASE_URL": "https://chat.dartmouth.example/v1",
                    "DARTMOUTH_CHAT_MODEL": "dartmouth-gpt-4o-class",
                    "OPENAI_API_KEY": "must-not-be-used",
                },
                clear=True,
            ),
        ):
            llm = agent.build_dartmouth_chat_llm()

        self.assertIsInstance(llm, FakeOpenAILLM)
        self.assertEqual(
            FakeOpenAILLM.calls,
            [
                {
                    "model": "dartmouth-gpt-4o-class",
                    "api_key": "dartmouth-key",
                    "base_url": "https://chat.dartmouth.example/v1",
                }
            ],
        )

    def test_dartmouth_chat_llm_refuses_missing_config(self) -> None:
        agent = load_agent_module()

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                agent.build_dartmouth_chat_llm()

    def test_build_llm_uses_groq_base_url_key_and_model(self) -> None:
        agent = load_agent_module()
        FakeOpenAILLM.calls.clear()

        with (
            patch.object(agent.openai, "LLM", FakeOpenAILLM),
            patch.dict(
                os.environ,
                {
                    "GROQ_API_KEY": "groq-key",
                    "DARTMOUTH_CHAT_API_KEY": "must-not-be-used",
                    "DARTMOUTH_CHAT_BASE_URL": "https://chat.dartmouth.example/v1",
                    "DARTMOUTH_CHAT_MODEL": "dartmouth-gpt-4o-class",
                    "OPENAI_API_KEY": "must-not-be-used",
                },
                clear=True,
            ),
        ):
            llm = agent.build_llm()

        self.assertIsInstance(llm, FakeOpenAILLM)
        self.assertEqual(
            FakeOpenAILLM.calls,
            [
                {
                    "model": "llama-3.3-70b-versatile",
                    "api_key": "groq-key",
                    "base_url": "https://api.groq.com/openai/v1",
                }
            ],
        )

    def test_build_llm_refuses_missing_groq_api_key(self) -> None:
        agent = load_agent_module()

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                agent.build_llm()

    def test_retrieval_agent_uses_prompt_and_session_state(self) -> None:
        source = agent_source()
        tree = agent_tree()
        class_names = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        }

        self.assertIn("PartsLineAgent", class_names)
        self.assertIn("PartsLineSessionState", class_names)
        self.assertIn("captured_vehicle", source)
        self.assertIn("instructions=PARTSLINE_SYSTEM_PROMPT", source)

    def test_agent_start_uses_partsline_agent_not_echo_agent(self) -> None:
        source = agent_source()

        self.assertIn("run_retrieval_session", source)
        self.assertIn("build_agent() -> PartsLineAgent", source)
        self.assertNotIn("class EchoAgent", source)
        self.assertNotIn("format_echo_response", source)

        self.assertIn("agent = build_agent()", source)
        self.assertIn("await session.start(room=ctx.room, agent=agent)", source)
