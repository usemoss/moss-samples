from __future__ import annotations

import asyncio
import ast
from collections.abc import Awaitable, Callable, Generator
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_MAIN = ROOT / "agent" / "main.py"
AGENT_REQUIREMENTS = ROOT / "agent" / "requirements.txt"


def load_agent_module():
    spec = importlib.util.spec_from_file_location("partsline_agent_main", AGENT_MAIN)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeSpeechHandle:
    def __init__(self, allow_interruptions: bool) -> None:
        self.id = "fake-speech-1"
        self.allow_interruptions = allow_interruptions
        self.awaited = False

    @property
    def interrupted(self) -> bool:
        return False

    @property
    def scheduled(self) -> bool:
        return self.awaited

    def done(self) -> bool:
        return self.awaited

    def __await__(self) -> Generator[None, None, "FakeSpeechHandle"]:
        async def wait_for_playout() -> FakeSpeechHandle:
            self.awaited = True
            return self

        return wait_for_playout().__await__()


class FakeAgentSession:
    def __init__(self) -> None:
        self.spoken: list[tuple[str, dict[str, object]]] = []
        self.handles: list[FakeSpeechHandle] = []
        self.started = False
        self.start_kwargs: dict[str, object] = {}

    def on(self, event: str) -> object:
        raise AssertionError(f"unexpected event handler registration: {event}")

    async def start(self, **kwargs: object) -> None:
        self.started = True
        self.start_kwargs = kwargs

    def say(self, text: str, **kwargs: object) -> FakeSpeechHandle:
        handle = FakeSpeechHandle(bool(kwargs.get("allow_interruptions", True)))
        self.spoken.append((text, kwargs))
        self.handles.append(handle)
        return handle


class FakeJobContext:
    def __init__(self) -> None:
        self.room = object()
        self.shutdown_callbacks: list[Callable[[str], Awaitable[None]]] = []

    def add_shutdown_callback(self, callback: Callable[[str], Awaitable[None]]) -> None:
        self.shutdown_callbacks.append(callback)


class T2AgentTest(unittest.TestCase):
    def test_agent_files_exist(self) -> None:
        self.assertTrue(AGENT_MAIN.exists())
        self.assertTrue(AGENT_REQUIREMENTS.exists())

    def test_requirements_match_retrieval_livekit_plugin_shape(self) -> None:
        requirements = AGENT_REQUIREMENTS.read_text(encoding="utf-8").splitlines()

        self.assertIn(
            "livekit-agents[deepgram,cartesia,silero,openai]>=1.6.1,<2",
            requirements,
        )
        self.assertIn("python-dotenv", requirements)
        self.assertFalse(any("pipecat" in line.lower() for line in requirements))
        self.assertFalse(any("vapi" in line.lower() for line in requirements))
        self.assertFalse(any("retell" in line.lower() for line in requirements))

    def test_session_state_starts_with_empty_captured_vehicle(self) -> None:
        agent = load_agent_module()

        state = agent.PartsLineSessionState()

        self.assertEqual(state.captured_vehicle, {})

    def test_run_retrieval_session_starts_partsline_agent_and_speaks_greeting(
        self,
    ) -> None:
        async def run_scenario() -> tuple[FakeAgentSession, list[str]]:
            agent = load_agent_module()
            session = FakeAgentSession()
            retrieval_agent = agent.PartsLineAgent()
            context = FakeJobContext()
            warmups: list[str] = []

            async def fake_warm_moss_client_cache() -> None:
                warmups.append("warmup")

            agent.build_session = lambda: session
            agent.build_agent = lambda: retrieval_agent
            agent.warm_moss_client_cache = fake_warm_moss_client_cache

            await agent.run_retrieval_session(context)
            await context.shutdown_callbacks[0]("test shutdown")
            return session, warmups

        session, warmups = asyncio.run(run_scenario())

        self.assertTrue(session.started)
        self.assertEqual(warmups, ["warmup"])
        self.assertEqual(
            session.start_kwargs["agent"].__class__.__name__, "PartsLineAgent"
        )
        self.assertEqual(
            session.spoken,
            [
                (
                    "Parts counter, go ahead.",
                    {"allow_interruptions": True},
                )
            ],
        )
        self.assertEqual([handle.awaited for handle in session.handles], [True])

    def test_agent_uses_agents_1_session_not_deprecated_voice_classes(self) -> None:
        source = AGENT_MAIN.read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attrs = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }

        self.assertIn("AgentSession", names)
        self.assertIn("AgentServer", names)
        self.assertIn("PartsLineAgent", names)
        self.assertIn("run_retrieval_session", source)
        self.assertNotIn("EchoAgent", source)
        self.assertNotIn("format_echo_response", source)
        self.assertNotIn("user_input_transcribed", source)
        self.assertNotIn("handle_user_transcript", source)
        self.assertNotIn("asyncio.create_task", source)
        self.assertNotIn("VoicePipelineAgent", source)
        self.assertNotIn("MultimodalAgent", source)
        self.assertNotIn("VoicePipelineAgent", names | attrs)
        self.assertNotIn("MultimodalAgent", names | attrs)

    def test_agent_configures_retrieval_voice_loop_components(self) -> None:
        source = AGENT_MAIN.read_text(encoding="utf-8")

        self.assertIn('deepgram.STT(model="nova-3"', source)
        self.assertIn('cartesia.TTS(model="sonic-3"', source)
        self.assertIn("silero.VAD.load()", source)
        self.assertIn("inference.TurnDetector()", source)
        self.assertIn("llm=build_llm()", source)
        self.assertNotIn("llm=build_dartmouth_chat_llm()", source)
        self.assertIn(
            "tools=[LOOKUP_PART_TOOL, SET_ASIDE_TOOL, TRANSFER_TO_HUMAN_TOOL]",
            source,
        )
        self.assertIn("userdata=PartsLineSessionState()", source)
        self.assertIn("session.say(GREETING, allow_interruptions=True)", source)
        self.assertIn("TurnHandlingOptions(", source)
        self.assertIn('"enabled": True', source)
