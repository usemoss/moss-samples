from __future__ import annotations

import json
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
AGENT_MAIN = ROOT / "agent" / "main.py"


def load_agent_module():
    spec = importlib.util.spec_from_file_location("partsline_agent_main", AGENT_MAIN)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeAgentSession:
    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}

    def on(self, event: str, callback: object) -> object:
        self.handlers[event] = callback
        return callback

    def emit(self, event: str, payload: object) -> None:
        callback = self.handlers[event]
        assert callable(callback)
        callback(payload)


class FakeSpeechHandle:
    def __init__(self, chat_items: list[object]) -> None:
        self.id = "speech_observability_1"
        self.chat_items = chat_items
        self._done_callbacks: list[object] = []

    def add_done_callback(self, callback: object) -> None:
        self._done_callbacks.append(callback)

    def finish(self) -> None:
        for callback in self._done_callbacks:
            assert callable(callback)
            callback(self)


class LiveKitObservabilityWiringTest(unittest.TestCase):
    def test_turn_metrics_listener_logs_completed_turn_with_tool_call(self) -> None:
        agent = load_agent_module()
        source = AGENT_MAIN.read_text(encoding="utf-8")
        session = FakeAgentSession()
        assistant_message = SimpleNamespace(
            type="message",
            role="assistant",
            metrics={
                "llm_node_ttft": 0.123,
                "tts_node_ttfb": 0.045,
                "e2e_latency": 0.678,
            },
        )
        speech_handle = FakeSpeechHandle(
            [
                SimpleNamespace(type="function_call"),
                SimpleNamespace(type="function_call_output"),
                assistant_message,
            ]
        )

        agent.register_turn_metrics_logging(session)

        self.assertIn("register_turn_metrics_logging(session)", source)
        self.assertIn("speech_created", session.handlers)
        self.assertIn("metrics_collected", session.handlers)

        session.emit(
            "metrics_collected",
            SimpleNamespace(
                metrics=SimpleNamespace(
                    type="llm_metrics",
                    speech_id=speech_handle.id,
                    duration=0.456,
                )
            ),
        )

        with self.assertLogs(agent.LOGGER, level="INFO") as captured:
            session.emit(
                "speech_created",
                SimpleNamespace(source="generate_reply", speech_handle=speech_handle),
            )
            speech_handle.finish()

        self.assertEqual(len(captured.records), 1)
        message = captured.records[0].getMessage()
        self.assertTrue(message.startswith("partsline_turn_metrics "))
        payload = json.loads(message.removeprefix("partsline_turn_metrics "))
        self.assertEqual(
            payload,
            {
                "event": "partsline_turn_metrics",
                "llm_time_to_first_token_seconds": 0.123,
                "llm_total_generation_seconds": 0.456,
                "tool_call_happened": True,
                "tts_time_to_first_byte_seconds": 0.045,
                "turn_latency_to_first_audio_seconds": 0.678,
            },
        )
