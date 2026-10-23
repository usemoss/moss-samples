"""Demo: mint an RTC token and start an Agora ConvoAI agent wired to our MCP server.

Usage:

    uv run python start_agent.py

Reads env vars listed in env.example. Prints the started agent's ID on success,
or the Agora REST response body on failure.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from typing import Any

import httpx
from agora_token_builder import RtcTokenBuilder
from dotenv import load_dotenv
from loguru import logger

MCP_SERVER_NAME = "moss"  # Agora rule: <= 48 chars, alphanumeric only.
AGORA_CONVOAI_BASE = "https://api.agora.io/api/conversational-ai-agent/v2/projects"
RTC_TOKEN_TTL_SECONDS = 3600  # 1 hour; ConvoAI REST max is 86400.


def mint_token(app_id: str, app_certificate: str, channel: str, uid: int) -> str:
    """Mint an Agora RTC token for the agent participant."""
    expire_ts = int(time.time()) + RTC_TOKEN_TTL_SECONDS
    # Role 1 = publisher; the ConvoAI agent publishes audio.
    return RtcTokenBuilder.buildTokenWithUid(app_id, app_certificate, channel, uid, 1, expire_ts)


def build_join_body(
    *,
    channel: str,
    agent_rtc_uid: int,
    agent_rtc_token: str,
    llm_url: str,
    llm_api_key: str,
    llm_model: str | None = None,
    mcp_public_url: str,
    mcp_auth_header: str | None,
    deepgram_key: str,
    cartesia_key: str,
    cartesia_voice_id: str,
) -> dict[str, Any]:
    """Construct the ConvoAI ``join`` request body with MCP + Deepgram + Cartesia."""
    mcp_entry: dict[str, Any] = {
        "name": MCP_SERVER_NAME,
        "endpoint": mcp_public_url,
        "transport": "streamable_http",
        "allowed_tools": ["search_knowledge_base"],
    }
    # Agora rule: server-entry name is <=48 chars, alphanumeric only.
    if not (mcp_entry["name"].isalnum() and 1 <= len(mcp_entry["name"]) <= 48):
        raise ValueError(f"MCP server name {mcp_entry['name']!r} must be 1-48 alphanumeric chars")
    if mcp_auth_header:
        mcp_entry["headers"] = {"Authorization": mcp_auth_header}

    llm_block: dict[str, Any] = {
        "vendor": "custom",
        "url": llm_url,
        "api_key": llm_api_key,
        "mcp_servers": [mcp_entry],
        "greeting_message": "Hi, I'm your Moss-powered support assistant. Ask me anything about the product.",
        "system_messages": [
            {
                "role": "system",
                "content": (
                    "You are a concise voice support assistant. Use the "
                    "search_knowledge_base tool to answer product questions, "
                    "then reply in one or two short sentences."
                ),
            }
        ],
    }
    if llm_model:
        llm_block["model"] = llm_model

    return {
        "name": f"moss-agora-{uuid.uuid4().hex[:8]}",
        "properties": {
            "channel": channel,
            "token": agent_rtc_token,
            "agent_rtc_uid": str(agent_rtc_uid),
            "remote_rtc_uids": os.environ.get("AGORA_REMOTE_RTC_UIDS", "2001").split(","),
            "llm": llm_block,
            "advanced_features": {"enable_tools": True},
            "asr": {
                "vendor": "deepgram",
                "params": {"key": deepgram_key, "model": "nova-3"},
            },
            "tts": {
                "vendor": "cartesia",
                "params": {
                    "api_key": cartesia_key,
                    "model_id": "sonic-3.6",
                    "voice": {"mode": "id", "id": cartesia_voice_id},
                    "output_format": {"container": "raw", "sample_rate": 16000},
                    "language": "en",
                },
            },
            "turn_detection": {"mode": "default"},
        },
    }


def _require_env(keys: tuple[str, ...]) -> dict[str, str]:
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        logger.error("Missing required env vars: {}", ", ".join(missing))
        sys.exit(1)
    return {k: os.environ[k] for k in keys}


def main() -> None:
    """Mint tokens and POST an Agora ConvoAI ``join`` body wiring in the MCP server."""
    load_dotenv()
    env = _require_env(
        (
            "AGORA_APP_ID",
            "AGORA_APP_CERTIFICATE",
            "AGORA_CUSTOMER_ID",
            "AGORA_CUSTOMER_SECRET",
            "AGORA_CHANNEL",
            "AGORA_MCP_PUBLIC_URL",
            "LLM_URL",
            "LLM_API_KEY",
            "DEEPGRAM_API_KEY",
            "CARTESIA_API_KEY",
            "CARTESIA_VOICE_ID",
        )
    )
    agent_rtc_uid = int(os.environ.get("AGORA_AGENT_RTC_UID", "1001"))
    rtc_token = mint_token(
        env["AGORA_APP_ID"],
        env["AGORA_APP_CERTIFICATE"],
        env["AGORA_CHANNEL"],
        agent_rtc_uid,
    )
    body = build_join_body(
        channel=env["AGORA_CHANNEL"],
        agent_rtc_uid=agent_rtc_uid,
        agent_rtc_token=rtc_token,
        llm_url=env["LLM_URL"],
        llm_api_key=env["LLM_API_KEY"],
        llm_model=os.environ.get("LLM_MODEL") or None,
        mcp_public_url=env["AGORA_MCP_PUBLIC_URL"],
        mcp_auth_header=os.environ.get("AGORA_MCP_AUTH_HEADER") or None,
        deepgram_key=env["DEEPGRAM_API_KEY"],
        cartesia_key=env["CARTESIA_API_KEY"],
        cartesia_voice_id=env["CARTESIA_VOICE_ID"],
    )
    url = f"{AGORA_CONVOAI_BASE}/{env['AGORA_APP_ID']}/join"
    auth = (env["AGORA_CUSTOMER_ID"], env["AGORA_CUSTOMER_SECRET"])
    with httpx.Client(timeout=30) as client:
        resp = client.post(url, auth=auth, json=body)
    if resp.status_code >= 300:
        logger.error("Agora REST {} {}", resp.status_code, resp.text)
        sys.exit(1)
    data = resp.json()
    logger.info("Agent started: {}", json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
