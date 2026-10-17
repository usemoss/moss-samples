"""Unit tests for the AgentPhone voice cookbook (no live API calls).

Covers:
- HMAC + replay-window signature verification.
- ``to_anthropic_history`` direction -> role mapping.
- ``run_tool_call`` loop with and without a tool, plus history threading.
- FastAPI ``/webhook`` route: valid voice event, invalid signature,
  ignored non-voice event.

Run with::

    uv run python test_integration.py
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from moss_agentphone import (
    run_tool_call,
    to_anthropic_history,
    verify_webhook_signature,
)

# server.py reads env on import, so set placeholders before importing it.
os.environ.setdefault("MOSS_PROJECT_ID", "test")
os.environ.setdefault("MOSS_PROJECT_KEY", "test")
os.environ.setdefault("MOSS_INDEX_NAME", "test-index")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("AGENTPHONE_WEBHOOK_SECRET", "whsec_test")


# -- helpers ----------------------------------------------------------------


def _text_block(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _tool_use_block(
    tool_id: str, name: str, args: dict[str, Any]
) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = args
    return block


def _claude_response(stop_reason: str, content: list[Any]) -> MagicMock:
    response = MagicMock()
    response.stop_reason = stop_reason
    response.content = content
    return response


def _anthropic_client(responses: list[MagicMock]) -> MagicMock:
    client = MagicMock()
    client.messages.create = AsyncMock(side_effect=responses)
    return client


def _sign(secret: str, timestamp: str, body: bytes) -> str:
    digest = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    return f"sha256={digest}"


# -- signature -------------------------------------------------------------


class WebhookSignatureTests(unittest.TestCase):
    SECRET = "whsec_test"
    TS = "1715760000"

    def test_accepts_valid_signature(self) -> None:
        body = b'{"event":"agent.message"}'
        self.assertTrue(
            verify_webhook_signature(
                secret=self.SECRET,
                timestamp=self.TS,
                body=body,
                signature=_sign(self.SECRET, self.TS, body),
            )
        )

    def test_rejects_tampered_body(self) -> None:
        body = b'{"event":"agent.message"}'
        self.assertFalse(
            verify_webhook_signature(
                secret=self.SECRET,
                timestamp=self.TS,
                body=b'{"event":"tampered"}',
                signature=_sign(self.SECRET, self.TS, body),
            )
        )

    def test_rejects_garbage_signature(self) -> None:
        self.assertFalse(
            verify_webhook_signature(
                secret=self.SECRET,
                timestamp=self.TS,
                body=b"{}",
                signature="sha256=deadbeef",
            )
        )


# -- history mapping -------------------------------------------------------


class HistoryMappingTests(unittest.TestCase):
    def test_maps_directions_to_roles(self) -> None:
        history = to_anthropic_history(
            [
                {"content": "Hi", "direction": "inbound"},
                {"content": "Hello, how can I help?", "direction": "outbound"},
            ]
        )
        self.assertEqual(
            history,
            [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello, how can I help?"},
            ],
        )

    def test_skips_empty_entries(self) -> None:
        history = to_anthropic_history(
            [
                {"content": "", "direction": "inbound"},
                {"content": "real", "direction": "outbound"},
            ]
        )
        self.assertEqual(
            history, [{"role": "assistant", "content": "real"}]
        )

    def test_empty_input_returns_empty_list(self) -> None:
        self.assertEqual(to_anthropic_history(None), [])
        self.assertEqual(to_anthropic_history([]), [])


# -- tool-call loop --------------------------------------------------------


class RunToolCallTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_call_then_final_answer(self) -> None:
        async def moss_search(args: dict[str, Any]) -> str:
            return f"1. excerpt about {args['query']}"

        anthropic = _anthropic_client(
            [
                _claude_response(
                    "tool_use",
                    [_tool_use_block("tu_1", "moss_search", {"query": "refunds"})],
                ),
                _claude_response(
                    "end_turn",
                    [_text_block("Refunds take three to five business days.")],
                ),
            ]
        )

        answer = await run_tool_call(
            user_message="how long do refunds take?",
            history=[],
            anthropic_client=anthropic,
            tool_handlers={"moss_search": moss_search},
            model="claude-haiku-4-5-20251001",
            system_prompt="You are a test agent.",
        )

        self.assertEqual(answer, "Refunds take three to five business days.")
        second_messages = anthropic.messages.create.await_args_list[1].kwargs[
            "messages"
        ]
        self.assertEqual(second_messages[-1]["role"], "user")
        self.assertEqual(second_messages[-1]["content"][0]["type"], "tool_result")
        self.assertIn(
            "excerpt about refunds",
            second_messages[-1]["content"][0]["content"],
        )

    async def test_model_can_answer_without_tool(self) -> None:
        called = False

        async def moss_search(args: dict[str, Any]) -> str:
            nonlocal called
            called = True
            return ""

        anthropic = _anthropic_client(
            [_claude_response("end_turn", [_text_block("Hi! How can I help?")])]
        )

        answer = await run_tool_call(
            user_message="hello",
            history=[],
            anthropic_client=anthropic,
            tool_handlers={"moss_search": moss_search},
            model="claude-haiku-4-5-20251001",
            system_prompt="You are a test agent.",
        )

        self.assertEqual(answer, "Hi! How can I help?")
        self.assertFalse(called)

    async def test_history_is_prepended_to_messages(self) -> None:
        anthropic = _anthropic_client(
            [_claude_response("end_turn", [_text_block("ok")])]
        )
        history = [
            {"role": "user", "content": "earlier turn"},
            {"role": "assistant", "content": "earlier reply"},
        ]

        await run_tool_call(
            user_message="new turn",
            history=history,
            anthropic_client=anthropic,
            tool_handlers={},
            model="claude-haiku-4-5-20251001",
            system_prompt="You are a test agent.",
        )

        sent = anthropic.messages.create.await_args.kwargs["messages"]
        self.assertEqual(sent[0], {"role": "user", "content": "earlier turn"})
        self.assertEqual(sent[1], {"role": "assistant", "content": "earlier reply"})
        self.assertEqual(sent[2], {"role": "user", "content": "new turn"})


# -- FastAPI /webhook route -------------------------------------------------


class WebhookRouteTests(unittest.TestCase):
    """Smoke tests for the FastAPI route via TestClient."""

    @classmethod
    def setUpClass(cls) -> None:
        # Import server only inside the test scope so env defaults above
        # are guaranteed to be set first.
        import server  # noqa: WPS433
        from fastapi.testclient import TestClient

        cls.server = server
        cls.client = TestClient(server.app)
        cls._patches = [
            patch.object(server.moss_client, "load_index", AsyncMock()),
            patch.object(
                server.moss_client,
                "query",
                AsyncMock(
                    return_value=MagicMock(
                        docs=[MagicMock(text="Refunds 3-5 days.")],
                        time_taken_ms=2,
                    )
                ),
            ),
            patch.object(
                server.anthropic_client.messages,
                "create",
                AsyncMock(
                    side_effect=[
                        _claude_response(
                            "end_turn",
                            [_text_block("Refunds take three to five days.")],
                        ),
                    ]
                ),
            ),
        ]
        for p in cls._patches:
            p.start()

    @classmethod
    def tearDownClass(cls) -> None:
        for p in cls._patches:
            p.stop()

    def _post_webhook(
        self,
        body: dict[str, Any] | None = None,
        *,
        signature: str | None = None,
        timestamp: str | None = None,
    ) -> Any:
        import time as _time

        body = body or {
            "event": "agent.message",
            "channel": "voice",
            "data": {"transcript": "how long do refunds take?"},
            "recentHistory": [],
        }
        raw = json.dumps(body).encode()
        ts = timestamp or str(int(_time.time()))
        sig = signature or _sign("whsec_test", ts, raw)
        return self.client.post(
            "/webhook",
            content=raw,
            headers={
                "X-Webhook-Signature": sig,
                "X-Webhook-Timestamp": ts,
                "X-Webhook-Id": "del_test",
                "X-Webhook-Event": body.get("event", ""),
                "Content-Type": "application/json",
            },
        )

    def test_voice_event_returns_ndjson_stream(self) -> None:
        response = self._post_webhook()
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/x-ndjson", response.headers["content-type"])
        lines = [
            json.loads(line)
            for line in response.text.strip().splitlines()
            if line.strip()
        ]
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].get("interim"))
        self.assertNotIn("interim", lines[1])
        self.assertEqual(
            lines[1]["text"], "Refunds take three to five days."
        )

    def test_invalid_signature_returns_401(self) -> None:
        response = self._post_webhook(signature="sha256=deadbeef")
        self.assertEqual(response.status_code, 401)

    def test_non_voice_event_is_acked(self) -> None:
        response = self._post_webhook(
            {
                "event": "agent.call_ended",
                "channel": "voice",
                "data": {"callId": "c_1"},
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})


if __name__ == "__main__":
    unittest.main()
