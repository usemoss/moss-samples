from __future__ import annotations

import base64
import hashlib
import hmac
import json
import subprocess
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOKEN_ROUTE = ROOT / "app" / "api" / "token" / "route.ts"


def base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


JsonObject = dict[str, Any]


def decode_jwt(token: str) -> tuple[JsonObject, JsonObject, bytes]:
    header_segment, payload_segment, signature_segment = token.split(".")
    header = json.loads(base64url_decode(header_segment))
    payload = json.loads(base64url_decode(payload_segment))
    signature = base64url_decode(signature_segment)
    return header, payload, signature


def expected_signature(token: str, secret: str) -> bytes:
    signed_part = ".".join(token.split(".")[:2]).encode("ascii")
    return hmac.new(secret.encode("utf-8"), signed_part, hashlib.sha256).digest()


def run_route_call(
    body: dict[str, str],
    env: dict[str, str] | None = None,
) -> JsonObject:
    script = textwrap.dedent(
        f"""
        import {{ POST }} from {json.dumps(TOKEN_ROUTE.as_uri())};

        const request = new Request("http://localhost/api/token", {{
          method: "POST",
          headers: {{ "content-type": "application/json" }},
          body: JSON.stringify({json.dumps(body)}),
        }});

        const response = await POST(request);
        const payload = await response.json();

        console.log(JSON.stringify({{
          status: response.status,
          payload,
        }}));
        """
    )
    with tempfile.NamedTemporaryFile(
        "w", suffix=".mjs", delete=False, encoding="utf-8"
    ) as handle:
        handle.write(script)
        script_path = Path(handle.name)

    try:
        result = subprocess.run(
            ["node", str(script_path)],
            cwd=ROOT,
            env={**(env or {})},
            text=True,
            capture_output=True,
            check=True,
        )
    finally:
        script_path.unlink(missing_ok=True)

    return json.loads(result.stdout)


class T3TokenEndpointTest(unittest.TestCase):
    def test_token_endpoint_returns_signed_short_lived_room_join_token(self) -> None:
        room_name = "room-from-request"
        participant_identity = "caller-from-request"
        api_key = "test-livekit-api-key"
        api_secret = "test-livekit-api-secret"

        before = int(time.time())
        result = run_route_call(
            {
                "room_name": room_name,
                "participant_identity": participant_identity,
            },
            env={
                "LIVEKIT_URL": "wss://partsline-test.livekit.cloud",
                "LIVEKIT_API_KEY": api_key,
                "LIVEKIT_API_SECRET": api_secret,
            },
        )
        after = int(time.time())

        self.assertEqual(result["status"], 201)
        payload = result["payload"]
        self.assertEqual(payload["server_url"], "wss://partsline-test.livekit.cloud")

        token = payload["participant_token"]
        self.assertIsInstance(token, str)

        header, claims, signature = decode_jwt(token)
        self.assertEqual(header, {"alg": "HS256", "typ": "JWT"})
        self.assertTrue(
            hmac.compare_digest(signature, expected_signature(token, api_secret))
        )
        self.assertEqual(claims["iss"], api_key)
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

    def test_token_endpoint_reports_missing_livekit_config_without_leaking_names(
        self,
    ) -> None:
        result = run_route_call(
            {"room_name": "room", "participant_identity": "identity"},
            env={},
        )

        self.assertEqual(result["status"], 500)
        self.assertEqual(
            result["payload"],
            {"error": "LiveKit environment is not configured"},
        )
