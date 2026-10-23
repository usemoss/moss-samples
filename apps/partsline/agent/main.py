from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
from collections.abc import Awaitable
from time import perf_counter
from typing import cast

from livekit.agents import Agent, RunContext, function_tool, llm
from livekit.plugins import cartesia, deepgram, openai, silero

from agent.prompts import PARTSLINE_SYSTEM_PROMPT
from agent import session_limits
from agent.db import save_call
from agent.outcome import CallOutcome
from agent.process_lock import AgentProcessLock, AgentProcessLockError
from agent.tools.lookup_part import (
    AmbiguousResult,
    SingleMatchResult,
    SupersededResult,
    lookup_part,
    part_index,
    warm_moss_client_cache,
)
from agent.tools.set_aside import SetAsideResult, set_aside
from agent.tools.transfer import TransferResult, transfer_to_human


LOGGER = logging.getLogger(__name__)
AGENT_NAME = "partsline-retrieval"
GREETING = "Parts counter, go ahead."
ENDPOINTING_MIN_DELAY_SECONDS = 1.0
ENDPOINTING_MAX_DELAY_SECONDS = 3.0
CLOSING_LINE_TIMEOUT_SECONDS = 5.0
SESSION_LIMIT_SHUTDOWN_REASON = "session limits reached"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "llama-3.3-70b-versatile"
TOOL_TIMING_LOG_EVENT = "partsline_tool_timing"
SessionLimits = session_limits.SessionLimits


class PartsLineSessionState:
    def __init__(self) -> None:
        self.captured_vehicle: dict[str, str] = {}
        self.call_outcome = CallOutcome()


def part_name(part_number: str) -> str:
    """Look up the human-readable name for a part number from the catalog."""
    try:
        record = part_index()[part_number]
    except KeyError:
        return part_number
    return record["metadata"].get("name", part_number)


async def lookup_part_for_session(
    ctx: RunContext[PartsLineSessionState],
    part: str,
    year: str,
    make: str,
    model: str,
    engine: str | None = None,
    trim: str | None = None,
) -> object:
    total_start = perf_counter()
    stages: dict[str, float] = {}

    stage_start = perf_counter()
    result = await lookup_part(
        part=part, year=year, make=make, model=model, engine=engine, trim=trim
    )
    stages["lookup_part_seconds"] = _elapsed_since(stage_start)

    stage_start = perf_counter()
    outcome = ctx.userdata.call_outcome
    outcome.record_vehicle(year=year, make=make, model=model, engine=engine, trim=trim)

    status = result.get("status")

    if status == "single_match":
        single = cast("SingleMatchResult", result)
        outcome.record_quoted_part(
            part_number=single["part_number"],
            name=part_name(single["part_number"]),
            price=single["price"],
            stock=single["stock"],
            resolution="quoted",
        )
    elif status == "superseded":
        superseded = cast("SupersededResult", result)
        replacement = superseded["replacement_part_number"]
        outcome.record_quoted_part(
            part_number=replacement,
            name=part_name(replacement),
            price=superseded["price"],
            stock=superseded["stock"],
            resolution="superseded_quoted",
        )
    elif status == "no_match":
        outcome.set_final_outcome("no_match")
    stages["outcome_recording_seconds"] = _elapsed_since(stage_start)

    stage_start = perf_counter()
    await emit_lookup_chip(
        ctx,
        result=result,
        year=year,
        make=make,
        model=model,
        engine=engine,
        trim=trim,
    )
    stages["lookup_chip_emit_seconds"] = _elapsed_since(stage_start)
    _log_tool_timing(
        tool_name="lookup_part",
        total_start=total_start,
        stages=stages,
        result_status=status if isinstance(status, str) else None,
    )

    return result


def parse_quantity(value: object, available_stock: int) -> int:
    """Coerce an LLM-supplied quantity into an int.

    Handles ints, numeric strings, number words, and the common
    "both"/"all"/"them all" phrasing that a caller uses to mean
    "everything you have in stock".
    """
    if isinstance(value, bool):
        # bool is a subclass of int; treat it as unset
        return 1
    if isinstance(value, int):
        return value

    text = str(value).strip().lower()
    if not text:
        return 1

    # "both", "all", "all of them", "them all" -> all available stock
    if any(word in text for word in ("both", "all", "them all", "every")):
        return max(available_stock, 1)

    number_words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "a": 1,
        "an": 1,
        "a couple": 2,
        "couple": 2,
        "a few": 3,
        "few": 3,
    }
    if text in number_words:
        return number_words[text]

    # pull the first integer out of the string ("2", "2 of them")
    match = re.search(r"\d+", text)
    if match:
        return int(match.group())

    return 1


async def set_aside_for_session(
    ctx: RunContext[PartsLineSessionState],
    first_name: str,
    part_number: str,
    quantity: object = 1,
) -> SetAsideResult:
    total_start = perf_counter()
    stages: dict[str, float] = {}

    stage_start = perf_counter()
    outcome = ctx.userdata.call_outcome
    quoted = next(
        (
            p
            for p in outcome.parts
            if p["part_number"].upper() == part_number.strip().upper()
        ),
        None,
    )
    available = quoted["stock"] if quoted else 0
    stages["quote_lookup_seconds"] = _elapsed_since(stage_start)

    stage_start = perf_counter()
    parsed_quantity = parse_quantity(quantity, available)
    stages["quantity_parse_seconds"] = _elapsed_since(stage_start)

    stage_start = perf_counter()
    result = set_aside(outcome, first_name, part_number, parsed_quantity)
    stages["set_aside_seconds"] = _elapsed_since(stage_start)
    status = result.get("status")
    _log_tool_timing(
        tool_name="set_aside",
        total_start=total_start,
        stages=stages,
        result_status=status if isinstance(status, str) else None,
    )
    return result


async def transfer_to_human_for_session(
    ctx: RunContext[PartsLineSessionState], reason: str
) -> TransferResult:
    total_start = perf_counter()
    stages: dict[str, float] = {}

    stage_start = perf_counter()
    outcome = ctx.userdata.call_outcome
    stages["outcome_access_seconds"] = _elapsed_since(stage_start)

    stage_start = perf_counter()
    result = transfer_to_human(outcome, reason)
    stages["transfer_seconds"] = _elapsed_since(stage_start)
    status = result.get("status")
    _log_tool_timing(
        tool_name="transfer_to_human",
        total_start=total_start,
        stages=stages,
        result_status=status if isinstance(status, str) else None,
    )
    return result


LOOKUP_PART_TOOL = function_tool(
    lookup_part_for_session,
    name="lookup_part",
    description=(
        "Look up an auto part using mandatory year, make, and model metadata "
        "filters. Returns single_match, ambiguous, superseded, or no_match."
    ),
)

SET_ASIDE_TOOL = function_tool(
    set_aside_for_session,
    name="set_aside",
    description=(
        "Hold a quoted, in-stock part under the caller's first name. "
        "Rejects parts not quoted this call or parts with no stock."
    ),
)

TRANSFER_TO_HUMAN_TOOL = function_tool(
    transfer_to_human_for_session,
    name="transfer_to_human",
    description=(
        "Simulate a warm transfer to a human and return a transfer event "
        "with the captured vehicle and part context."
    ),
)


TURN_METRICS_LOG_EVENT = "partsline_turn_metrics"


def _elapsed_since(start: float) -> float:
    return perf_counter() - start


def _log_tool_timing(
    *,
    tool_name: str,
    total_start: float,
    stages: dict[str, float],
    result_status: str | None,
) -> None:
    payload: dict[str, object] = {
        "event": TOOL_TIMING_LOG_EVENT,
        "tool_name": tool_name,
        "total_seconds": _elapsed_since(total_start),
        "stages": stages,
    }
    if result_status is not None:
        payload["result_status"] = result_status

    LOGGER.info(
        "%s %s",
        TOOL_TIMING_LOG_EVENT,
        json.dumps(payload, separators=(",", ":"), sort_keys=True),
    )


def _numeric_metric(metrics: object, key: str) -> float | None:
    if not isinstance(metrics, dict):
        return None
    value = metrics.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _chat_item_type(item: object) -> object:
    return getattr(item, "type", None)


def _is_assistant_message(item: object) -> bool:
    return (
        _chat_item_type(item) == "message"
        and getattr(item, "role", None) == "assistant"
    )


def _assistant_message_for_turn(chat_items: list[object]) -> object | None:
    for item in reversed(chat_items):
        if _is_assistant_message(item):
            return item
    return None


def _log_turn_metrics(
    speech_handle: object, llm_generation_times: dict[str, float]
) -> None:
    chat_items = list(getattr(speech_handle, "chat_items", []))
    assistant_message = _assistant_message_for_turn(chat_items)
    if assistant_message is None:
        return

    metrics = getattr(assistant_message, "metrics", {})
    speech_id = getattr(speech_handle, "id", None)
    llm_generation_time = (
        llm_generation_times.pop(speech_id, None)
        if isinstance(speech_id, str)
        else None
    )
    payload = {
        "event": TURN_METRICS_LOG_EVENT,
        "llm_time_to_first_token_seconds": _numeric_metric(metrics, "llm_node_ttft"),
        "llm_total_generation_seconds": llm_generation_time,
        "tool_call_happened": any(
            _chat_item_type(item) == "function_call" for item in chat_items
        ),
        "tts_time_to_first_byte_seconds": _numeric_metric(metrics, "tts_node_ttfb"),
        "turn_latency_to_first_audio_seconds": _numeric_metric(metrics, "e2e_latency"),
    }
    LOGGER.info(
        "%s %s",
        TURN_METRICS_LOG_EVENT,
        json.dumps(payload, separators=(",", ":"), sort_keys=True),
    )


def register_turn_metrics_logging(session: object) -> None:
    llm_generation_times: dict[str, float] = {}

    def on_metrics_collected(event: object) -> None:
        metrics = getattr(event, "metrics", None)
        if getattr(metrics, "type", None) != "llm_metrics":
            return

        speech_id = getattr(metrics, "speech_id", None)
        duration = getattr(metrics, "duration", None)
        if (
            isinstance(speech_id, str)
            and not isinstance(duration, bool)
            and isinstance(duration, int | float)
        ):
            llm_generation_times[speech_id] = float(duration)

    def on_speech_created(event: object) -> None:
        if getattr(event, "source", None) != "generate_reply":
            return

        speech_handle = getattr(event, "speech_handle", None)
        add_done_callback = getattr(speech_handle, "add_done_callback", None)
        if not callable(add_done_callback):
            return

        def on_speech_done(done_handle: object) -> None:
            _log_turn_metrics(done_handle, llm_generation_times)

        add_done_callback(on_speech_done)

    on = getattr(session, "on")
    on("metrics_collected", on_metrics_collected)
    on("speech_created", on_speech_created)


def required_env(name: str, config_name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for {config_name}")
    return value


def build_llm():
    return openai.LLM(
        model=GROQ_MODEL,
        api_key=required_env("GROQ_API_KEY", "Groq LLM config"),
        base_url=GROQ_BASE_URL,
    )


def build_dartmouth_chat_llm():
    return openai.LLM(
        model=required_env("DARTMOUTH_CHAT_MODEL", "Dartmouth Chat LLM config"),
        api_key=required_env("DARTMOUTH_CHAT_API_KEY", "Dartmouth Chat LLM config"),
        base_url=required_env("DARTMOUTH_CHAT_BASE_URL", "Dartmouth Chat LLM config"),
    )


class PartsLineAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=PARTSLINE_SYSTEM_PROMPT)
        self.session_limits: session_limits.SessionLimits | None = None

    async def on_user_turn_completed(
        self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ) -> None:
        if self.session_limits is not None:
            self.session_limits.record_user_activity()


def build_session():
    from livekit.agents import AgentSession, TurnHandlingOptions, inference

    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="en"),
        llm=build_llm(),
        tts=cartesia.TTS(model="sonic-3"),
        vad=silero.VAD.load(),
        tools=[LOOKUP_PART_TOOL, SET_ASIDE_TOOL, TRANSFER_TO_HUMAN_TOOL],
        userdata=PartsLineSessionState(),
        turn_handling=TurnHandlingOptions(
            turn_detection=inference.TurnDetector(),
            endpointing={
                "mode": "fixed",
                "min_delay": ENDPOINTING_MIN_DELAY_SECONDS,
                "max_delay": ENDPOINTING_MAX_DELAY_SECONDS,
            },
            interruption={"enabled": True, "mode": "adaptive"},
        ),
    )
    register_turn_metrics_logging(session)
    return session


def build_agent() -> PartsLineAgent:
    return PartsLineAgent()


async def _await_if_needed(result: object) -> None:
    if inspect.isawaitable(result):
        await cast(Awaitable[object], result)


def lookup_chip_filter(
    *,
    year: str,
    make: str,
    model: str,
    engine: str | None,
    trim: str | None,
) -> dict[str, str]:
    filters = {"year": year, "make": make, "model": model}
    if engine:
        filters["engine"] = engine
    if trim:
        filters["trim"] = trim
    return filters


def lookup_chip_parts(result: object) -> list[dict[str, object]]:
    status = result.get("status") if isinstance(result, dict) else None
    if status == "single_match":
        single = cast("SingleMatchResult", result)
        return [
            {
                "part_number": single["part_number"],
                "name": part_name(single["part_number"]),
                "price": single["price"],
                "stock": single["stock"],
            }
        ]
    if status == "superseded":
        superseded = cast("SupersededResult", result)
        old_part_number = superseded["old_part_number"]
        replacement = superseded["replacement_part_number"]
        return [
            {"part_number": old_part_number, "name": part_name(old_part_number)},
            {
                "part_number": replacement,
                "name": part_name(replacement),
                "price": superseded["price"],
                "stock": superseded["stock"],
            },
        ]
    return []


def lookup_chip_payload(
    result: object,
    *,
    year: str,
    make: str,
    model: str,
    engine: str | None,
    trim: str | None,
) -> dict[str, object]:
    status_value = result.get("status") if isinstance(result, dict) else None
    status = status_value if isinstance(status_value, str) else "no_match"
    result_label = {
        "single_match": "single",
        "ambiguous": "ambiguous",
        "superseded": "superseded",
        "no_match": "no_match",
    }.get(status, "no_match")
    payload: dict[str, object] = {
        "filter": lookup_chip_filter(
            year=year, make=make, model=model, engine=engine, trim=trim
        ),
        "result": result_label,
        "parts": lookup_chip_parts(result),
    }
    if status == "ambiguous":
        ambiguous = cast("AmbiguousResult", result)
        payload["candidates"] = {
            "attribute": ambiguous["attribute"],
            "values": ambiguous["candidates"],
        }
    return payload


def _room_from_tool_context(ctx: object) -> object | None:
    room = getattr(ctx, "room", None)
    if room is not None:
        return room

    session = getattr(ctx, "session", None)
    if session is None:
        return None
    try:
        room_io = getattr(session, "room_io", None)
    except RuntimeError:
        return None
    return getattr(room_io, "room", None)


async def publish_data_event(
    room: object | None, topic: str, payload: dict[str, object]
) -> None:
    if room is None:
        return

    participant = getattr(room, "local_participant", None)
    publish_data = getattr(participant, "publish_data", None)
    if publish_data is None:
        return

    data = json.dumps(payload, separators=(",", ":"))
    result = publish_data(data, reliable=True, topic=topic)
    await _await_if_needed(result)


async def emit_lookup_chip(
    ctx: object,
    result: object,
    *,
    year: str,
    make: str,
    model: str,
    engine: str | None,
    trim: str | None,
) -> None:
    await publish_data_event(
        _room_from_tool_context(ctx),
        "lookup_chip",
        lookup_chip_payload(
            result,
            year=year,
            make=make,
            model=model,
            engine=engine,
            trim=trim,
        ),
    )


def _call_outcome_for_session(session: object) -> CallOutcome | None:
    userdata = getattr(session, "userdata", None)
    outcome = getattr(userdata, "call_outcome", None)
    if isinstance(outcome, CallOutcome):
        return outcome
    return None


async def emit_call_ended(room: object, outcome: CallOutcome) -> None:
    await publish_data_event(
        room,
        "call_ended",
        {
            "call_id": outcome.call_id,
            "outcome": outcome.outcome,
        },
    )


async def _shutdown_for_session_limits(session, ctx) -> None:
    LOGGER.info("session limit reached; speaking closing line")
    closing_playout = session.say(
        session_limits.CLOSING_LINE, allow_interruptions=False
    )
    try:
        await asyncio.wait_for(closing_playout, timeout=CLOSING_LINE_TIMEOUT_SECONDS)
        LOGGER.info("closing line playout completed; closing session and room")
    except asyncio.TimeoutError:
        LOGGER.warning("closing line playout timed out; closing session and room")
    await _await_if_needed(session.aclose())
    await _await_if_needed(ctx.room.disconnect())
    await _await_if_needed(ctx.shutdown(SESSION_LIMIT_SHUTDOWN_REASON))


async def _warm_lookup_index_for_session() -> None:
    try:
        await warm_moss_client_cache()
    except Exception:
        LOGGER.warning("Moss cache warmup failed; lookup_part will retry on demand")


async def run_retrieval_session(ctx) -> None:
    session = build_session()
    agent = build_agent()
    await session.start(room=ctx.room, agent=agent)

    async def shutdown_for_session_limits() -> None:
        await _shutdown_for_session_limits(session, ctx)

    limits = SessionLimits(
        on_idle_timeout=shutdown_for_session_limits,
        on_max_duration=shutdown_for_session_limits,
    )
    agent.session_limits = limits
    limits.start()

    async def finish_call(_: str = "") -> None:
        await limits.stop()
        outcome = _call_outcome_for_session(session)
        if outcome is None:
            return
        save_call(outcome)
        await emit_call_ended(ctx.room, outcome)

    ctx.add_shutdown_callback(finish_call)
    await _warm_lookup_index_for_session()
    LOGGER.info("session started; speaking greeting", extra={"greeting": GREETING})
    await session.say(GREETING, allow_interruptions=True)
    LOGGER.info("greeting speak call completed")


def create_server():
    from livekit import agents
    from livekit.agents import AgentServer

    server = AgentServer()

    @server.rtc_session(agent_name=AGENT_NAME)
    async def partsline_retrieval(ctx: agents.JobContext) -> None:
        await run_retrieval_session(ctx)

    return server


def main() -> None:
    from dotenv import load_dotenv
    from livekit import agents

    load_dotenv()
    try:
        with AgentProcessLock():
            agents.cli.run_app(create_server())
    except AgentProcessLockError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
