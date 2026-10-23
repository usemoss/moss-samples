from __future__ import annotations

import ast
import time
import unittest
from pathlib import Path

from tests.test_t3_token_endpoint import decode_jwt, run_route_call


ROOT = Path(__file__).resolve().parents[1]
AGENT_MAIN = ROOT / "agent" / "main.py"
VOICE_CLIENT = ROOT / "app" / "voice-test" / "VoiceTestClient.tsx"


def assigns_agent_name(node: ast.AST) -> bool:
    if not isinstance(node, ast.Assign):
        return False

    return any(
        isinstance(target, ast.Name) and target.id == "AGENT_NAME"
        for target in node.targets
    )


def agent_name_from_source() -> str:
    tree = ast.parse(AGENT_MAIN.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue

        if (
            assigns_agent_name(node)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    raise AssertionError("AGENT_NAME constant not found")


class T5EndToEndWiringTest(unittest.TestCase):
    def test_token_route_mints_short_lived_room_join_token_that_dispatches_retrieval_agent(
        self,
    ) -> None:
        room_name = "partsline-e2e-room"
        participant_identity = "browser-e2e-caller"
        api_secret = "test-livekit-api-secret"

        before = int(time.time())
        result = run_route_call(
            {
                "room_name": room_name,
                "participant_identity": participant_identity,
            },
            env={
                "LIVEKIT_URL": "wss://partsline-test.livekit.cloud",
                "LIVEKIT_API_KEY": "test-livekit-api-key",
                "LIVEKIT_API_SECRET": api_secret,
            },
        )
        after = int(time.time())

        self.assertEqual(result["status"], 201)
        payload = result["payload"]
        self.assertEqual(payload["server_url"], "wss://partsline-test.livekit.cloud")

        token = payload["participant_token"]
        self.assertIsInstance(token, str)

        _, claims, _ = decode_jwt(token)

        self.assertEqual(claims["video"]["room"], room_name)
        self.assertEqual(claims["sub"], participant_identity)

        video_grant = claims["video"]
        self.assertEqual(video_grant["room"], room_name)
        self.assertTrue(video_grant["roomJoin"])
        self.assertTrue(video_grant["canPublish"])
        self.assertTrue(video_grant["canPublishData"])
        self.assertTrue(video_grant["canSubscribe"])

        self.assertLessEqual(claims["nbf"], after)
        self.assertGreater(claims["exp"], before)
        self.assertLessEqual(claims["exp"] - claims["nbf"], 600)

        self.assertEqual(
            claims["roomConfig"],
            {"agents": [{"agentName": agent_name_from_source()}]},
        )

    def test_browser_requests_dispatch_token_for_fresh_room(self) -> None:
        # Static wiring check only. The actual browser -> LiveKit -> agent path is
        # validated by the manual voice test.
        source = VOICE_CLIENT.read_text(encoding="utf-8")

        self.assertIn('uniqueName("partsline-voice-test")', source)
        self.assertIn("room_name", source)
        self.assertIn("participant_identity", source)
        self.assertIn('fetch("/api/token"', source)
