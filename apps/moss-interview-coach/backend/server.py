#!/usr/bin/env python3
"""Interview Coach — FastAPI + Pipecat SmallWebRTC + Moss.

Only cloud credentials required: MOSS_PROJECT_ID / MOSS_PROJECT_KEY.
STT = local Whisper, TTS = local Piper, LLM = local Ollama.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from moss import MossClient, QueryOptions
from pydantic import BaseModel, Field
from pipecat.adapters.schemas.direct_function import tool_options
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    InterruptionFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TTSSpeakFrame,
    UserStartedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.ollama.llm import OLLamaLLMService
from pipecat.services.piper.tts import PiperTTSService
from pipecat.services.whisper.stt import Model as WhisperModel
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    IceCandidate,
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

from tracks import (
    DEFAULT_TRACK_ID,
    INTERVIEW_TRACKS,
    all_index_names,
    normalize_track_id,
    resolve_track_id_for_offer,
    track_index_name,
)

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
OLLAMA_GRADE_MODEL = os.getenv("OLLAMA_GRADE_MODEL", OLLAMA_MODEL)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "auto")
PIPER_VOICE = os.getenv("PIPER_VOICE", "en_US-lessac-medium")
GRADER_WORKER_PATH = Path(__file__).resolve().parent / "grader_worker.py"
GRADE_SUBPROCESS_TIMEOUT_SECS = float(os.getenv("GRADE_SUBPROCESS_TIMEOUT_SECS", "60"))
# Generous relative to the frontend's own 30s connect timeout, so a slow but
# genuine client is never cut off — this only catches offers that go nowhere.
SESSION_HANDSHAKE_TIMEOUT_SECS = float(os.getenv("SESSION_HANDSHAKE_TIMEOUT_SECS", "45"))
# Each session loads Whisper/Piper and drives Ollama, so concurrency is bounded.
MAX_ACTIVE_BOTS = int(os.getenv("MAX_ACTIVE_BOTS", "2"))

COACH_BEHAVIOR = (
    "Conduct a live voice interview. Ask probing follow-ups, push for trade-offs, "
    "and keep answers concise enough to speak aloud. "
    "Avoid markdown, bullets, and emojis. "
    "When the candidate finishes a substantive answer: speak your short follow-up question "
    "in the same turn, and also call grade_candidate_answer with their answer text. "
    "Skip the tool for greetings, topic picks, or one-word clarifications. "
    "Never speak scores, grades, or improvement tips aloud — the assist panel shows those."
)


def build_system_prompt(track_id: str) -> str:
    track = INTERVIEW_TRACKS[normalize_track_id(track_id)]
    return f"{track['focus']} {COACH_BEHAVIOR}"


moss_client: MossClient | None = None
# Track id → whether that track's Moss index is loaded locally.
moss_indexes_ready: dict[str, bool] = {tid: False for tid in INTERVIEW_TRACKS}
moss_ready = False
active_bots = 0
# Guards active_bots. The capacity check and the increment have to be one
# critical section: offer() runs concurrently, and the bot task that used to do
# the incrementing is spawned several awaits later, so checking there let any
# number of simultaneous offers pass the limit together.
active_bots_lock = asyncio.Lock()


async def reserve_bot_slot() -> bool:
    """Take a slot if one is free. Caller must release exactly once."""
    global active_bots
    async with active_bots_lock:
        if active_bots >= MAX_ACTIVE_BOTS:
            return False
        active_bots += 1
        return True


async def release_bot_slot() -> None:
    global active_bots
    async with active_bots_lock:
        active_bots = max(0, active_bots - 1)


class ActiveSession:
    """Handle for tearing down one in-flight interview.

    Uvicorn owns the process signals (see the WorkerRunner construction in
    run_interview_bot), so nothing cancels a running session on Ctrl-C unless
    shutdown reaches it explicitly — it would otherwise keep Whisper / Ollama /
    Piper and any grading subprocess alive until the server's shutdown timeout.
    """

    def __init__(self, worker: PipelineWorker, assist: InterviewAssistState) -> None:
        self.worker = worker
        self.assist = assist

    async def shutdown(self) -> None:
        """Cancel grading, then the pipeline worker. Idempotent enough to race."""
        grade_tasks = self.assist.cancel_grades()
        if grade_tasks:
            await asyncio.gather(*grade_tasks, return_exceptions=True)
        await self.worker.cancel()


active_sessions: set[ActiveSession] = set()

# Detached interview tasks (see webrtc_connection_callback for why they are not
# Starlette background tasks). Held so shutdown can cancel them.
bot_tasks: set[asyncio.Task[None]] = set()


def _on_bot_task_done(task: asyncio.Task[None]) -> None:
    bot_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.warning(f"Interview task ended with an error: {exc}")


ICE_SERVERS = [IceServer(urls="stun:stun.l.google.com:19302")]
small_webrtc_handler = SmallWebRTCRequestHandler(ice_servers=ICE_SERVERS)


class GradeResult(BaseModel):
    type: str = "grade_result"
    topic: str | None = None
    score: int = Field(ge=1, le=5)
    max_score: int = Field(default=5, ge=1)
    summary: str
    tips: list[str] = Field(default_factory=list)


# Cap on retained per-call snapshots; far above the handful ever in flight.
MAX_CALL_SNAPSHOTS = 32


class CallSnapshot(BaseModel):
    """What was true for the turn a tool call was issued for.

    Frozen deliberately: the point is to survive later turns mutating the
    shared state these values were read from.
    """

    model_config = {"frozen": True}

    answer: str | None = None
    question: str | None = None
    rubric_id: str | None = None
    rubric_text: str | None = None


class InterviewAssistState:
    """Shared question text for the Assist panel and grading tool."""

    def __init__(self) -> None:
        self.last_question: str | None = None
        self.bot_buf: list[str] = []
        self.bot_speaking: bool = False
        # Incremented each time the coach starts speaking. Lets a waiter tell
        # "has not started yet" apart from "already finished".
        self.bot_speech_turns: int = 0
        # Immutable per-tool-call snapshots of the turn a call was issued for,
        # keyed by tool_call_id. A grading call outlives its turn (the tool sets
        # cancel_on_interruption=False), so reading shared state when it finally
        # runs can bind it to a later turn. Recorded when the LLM announces the
        # call — i.e. while the originating turn is still current.
        self.call_snapshots: dict[str, CallSnapshot] = {}
        self._grade_generation: int = 0
        self._grade_tasks: set[asyncio.Task[None]] = set()
        self._grade_lock = asyncio.Lock()

    def record_call_snapshot(self, tool_call_id: str, snapshot: CallSnapshot) -> None:
        """Bind the current turn to a tool call before it can be rebound."""
        # Bounded: a call whose handler never runs would otherwise leak an entry.
        if len(self.call_snapshots) >= MAX_CALL_SNAPSHOTS:
            oldest = next(iter(self.call_snapshots))
            self.call_snapshots.pop(oldest, None)
        self.call_snapshots[tool_call_id] = snapshot

    def take_call_snapshot(self, tool_call_id: str) -> CallSnapshot | None:
        """Consume the snapshot for a call. Each call may only claim its own."""
        return self.call_snapshots.pop(tool_call_id, None)

    def cancel_grades(self) -> list[asyncio.Task[None]]:
        """Cancel in-flight grade tasks so subprocess workers are torn down."""
        tasks = list(self._grade_tasks)
        for task in tasks:
            task.cancel()
        return tasks

    def begin_grading(self) -> int:
        """Start a new grading turn; invalidates any in-flight grade."""
        self.cancel_grades()
        self._grade_generation += 1
        return self._grade_generation

    def invalidate_grading(self) -> None:
        """Discard in-flight grading (e.g. after barge-in)."""
        self.cancel_grades()
        self._grade_generation += 1

    def grading_still_current(self, turn_id: int) -> bool:
        return turn_id == self._grade_generation

    def track_grade_task(self, task: asyncio.Task[None]) -> None:
        self._grade_tasks.add(task)
        task.add_done_callback(self._grade_tasks.discard)


class MossContextInjector(FrameProcessor):
    """Query Moss on each user turn and inject rubric context into the LLM prompt."""

    def __init__(
        self,
        client: MossClient,
        *,
        system_prompt: str,
        index_name: str,
        assist_state: InterviewAssistState,
        top_k: int = 1,
        alpha: float = 0.6,
    ) -> None:
        super().__init__()
        self._client = client
        self._assist = assist_state
        self._system_prompt = system_prompt
        self._index_name = index_name
        self._top_k = top_k
        self._alpha = alpha
        self.last_moss_ms: float | None = None
        self.last_rubric_id: str | None = None
        self.last_rubric_text: str | None = None
        self.last_user_answer: str | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMContextFrame):
            await self._inject_rubric(frame)

        await self.push_frame(frame, direction)

    async def _inject_rubric(self, frame: LLMContextFrame) -> None:
        user_text = _last_user_text(frame.context)
        if not user_text:
            return

        self.last_user_answer = user_text
        started = time.perf_counter()
        try:
            results = await self._client.query(
                self._index_name,
                user_text,
                QueryOptions(top_k=self._top_k, alpha=self._alpha),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Moss query failed: {exc}")
            self.last_rubric_id = None
            self.last_rubric_text = None
            _upsert_system_message(frame.context, self._system_prompt)
            return

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        reported = getattr(results, "time_taken_ms", None)
        self.last_moss_ms = float(reported) if isinstance(reported, (int, float)) else elapsed_ms

        if not results.docs:
            logger.info(f"Moss returned no docs ({self.last_moss_ms:.2f} ms)")
            # Same reset as the failure path above: leaving the previous rubric
            # cached would let this turn — and the grader — score against a
            # topic the candidate is no longer being asked about.
            self.last_rubric_id = None
            self.last_rubric_text = None
            _upsert_system_message(frame.context, self._system_prompt)
            return

        top = results.docs[0]
        self.last_rubric_id = top.id
        self.last_rubric_text = top.text
        rubric_block = (
            f"Context/Rubric Guidelines:\n"
            f"Matched topic id={top.id} score={top.score:.3f}\n"
            f"{top.text}"
        )
        _upsert_system_message(frame.context, f"{self._system_prompt}\n\n{rubric_block}")
        logger.info(
            f"Moss retrieved '{top.id}' in {self.last_moss_ms:.2f} ms "
            f"(score={top.score:.3f})"
        )


class CoachQuestionEmitter(FrameProcessor):
    """Emit current_question only after a full coach utterance (no mid-turn flicker)."""

    def __init__(self, assist_state: InterviewAssistState) -> None:
        super().__init__()
        self._state = assist_state

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        # Welcome / queued speak frames may enter at the pipeline head.
        if isinstance(frame, TTSSpeakFrame) and frame.text.strip():
            self._state.bot_buf = [frame.text.strip() + " "]
            await self._maybe_emit_question(prefer_interrogative=False)

        if isinstance(frame, LLMFullResponseStartFrame):
            self._state.bot_buf = []

        if isinstance(frame, LLMTextFrame) and frame.text:
            self._state.bot_buf.append(frame.text)

        # Emit once when the LLM finishes — not on BotStoppedSpeaking (barge-in flicker).
        if isinstance(frame, LLMFullResponseEndFrame):
            await self._maybe_emit_question(prefer_interrogative=True)

        await self.push_frame(frame, direction)

    async def _maybe_emit_question(self, *, prefer_interrogative: bool) -> None:
        question = _extract_question(
            "".join(self._state.bot_buf),
            prefer_interrogative=prefer_interrogative,
        )
        if not question or question == self._state.last_question:
            return
        # Ignore tiny fragments that flash during tools / interruptions.
        if len(question) < 12:
            return
        self._state.last_question = question
        await self.push_frame(
            RTVIServerMessageFrame(
                data={"type": "current_question", "text": question}
            ),
            FrameDirection.DOWNSTREAM,
        )


class BotSpeechTracker(FrameProcessor):
    """Track whether the coach is currently speaking.

    Sits *downstream* of ``transport.output()``, which is what emits
    ``BotStartedSpeakingFrame`` / ``BotStoppedSpeakingFrame``. Keeping this
    separate from :class:`InterruptionBridge` matters: the bridge has to stay
    upstream of the output transport so its ``RTVIServerMessageFrame`` pushes
    reach the client, but that is the wrong place to *learn* about bot speech
    from. Pipecat currently broadcasts these frames upstream as well, so the
    bridge would happen to see them, but that is an implementation detail we
    should not depend on.
    """

    def __init__(self, assist_state: InterviewAssistState) -> None:
        super().__init__()
        self._assist = assist_state

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, BotStartedSpeakingFrame):
            self._assist.bot_speaking = True
            self._assist.bot_speech_turns += 1

        if isinstance(frame, BotStoppedSpeakingFrame):
            self._assist.bot_speaking = False

        await self.push_frame(frame, direction)


class InterruptionBridge(FrameProcessor):
    """Publish barge-in events to the client.

    Must stay upstream of ``transport.output()``: the ``RTVIServerMessageFrame``
    it pushes downstream only reaches the client by flowing into the output
    transport. Bot-speech state is owned by :class:`BotSpeechTracker`.
    """

    def __init__(self, assist_state: InterviewAssistState) -> None:
        super().__init__()
        self._assist = assist_state

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, UserStartedSpeakingFrame) and self._assist.bot_speaking:
            self._assist.invalidate_grading()
            await self._emit({"type": "interruption", "interrupted": True})

        if isinstance(frame, InterruptionFrame) and self._assist.bot_speaking:
            self._assist.invalidate_grading()
            await self._emit({"type": "interruption", "interrupted": True})

        await self.push_frame(frame, direction)

    async def _emit(self, payload: dict[str, Any]) -> None:
        await self.push_frame(
            RTVIServerMessageFrame(data=payload),
            FrameDirection.DOWNSTREAM,
        )


@tool_options(cancel_on_interruption=False, timeout_secs=90)
async def grade_candidate_answer(
    params: FunctionCallParams,
    answer: str,
    question: str | None = None,
) -> None:
    """Grade a candidate's substantive interview answer against the Moss rubric.

    Call this when the candidate finishes a substantive answer (not for
    greetings, topic picks, or one-word clarifications). Do not narrate the score
    or tips aloud — the assist panel shows feedback.

    Args:
        answer: The candidate's last substantive reply to grade.
        question: Optional interview question being answered; defaults to the last coach question.
    """
    resources = params.app_resources or {}
    moss: MossContextInjector | None = resources.get("moss")
    assist: InterviewAssistState | None = resources.get("assist")
    track_meta: dict[str, str] = resources.get("track") or INTERVIEW_TRACKS[DEFAULT_TRACK_ID]
    track_label = track_meta.get("label", "Interview")

    # These arguments are produced by the coach LLM *after* it has read the
    # candidate's own transcript, so they sit downstream of untrusted input: a
    # candidate can talk the model into grading a forged answer, and even with
    # no ill intent the model tends to paraphrase rather than quote. The server
    # already captured the real turn, so that is the source of truth; the tool
    # arguments are only a fallback for when nothing was captured.
    #
    # It has to be *this* call's transcript, though. The tool sets
    # cancel_on_interruption=False, so a call issued for one turn can run after
    # the candidate has spoken again — and shared state read at that point
    # describes the newer turn. The snapshot was frozen when the LLM announced
    # this call, keyed by its tool_call_id, so it cannot be rebound afterwards.
    snapshot = assist.take_call_snapshot(params.tool_call_id) if assist else None
    supplied_answer = (answer or "").strip()
    captured_answer = (snapshot.answer or "").strip() if snapshot else ""
    answer_text = captured_answer or supplied_answer
    if captured_answer and supplied_answer and supplied_answer != captured_answer:
        logger.info("Grading the captured transcript rather than the model-supplied answer.")
    elif snapshot is None and supplied_answer:
        # No snapshot: fall back to the arguments, which are themselves bound to
        # this invocation, rather than to shared state that may have moved on.
        logger.info("No turn snapshot for this call; grading its supplied answer.")
    if not answer_text:
        await params.result_callback(
            {
                "ok": False,
                "error": "empty_answer",
                "instruction": "Continue the spoken interview. Do not mention grading.",
            }
        )
        return

    # Same ordering for the question: assist.last_question is what the coach was
    # recorded as actually asking, so it outranks the model's restatement.
    captured_question = (snapshot.question or "").strip() if snapshot else ""
    question_text = (
        captured_question or (question or "").strip() or f"General {track_label} answer"
    )
    # From the same snapshot, so the rubric matches the graded turn.
    rubric_id = snapshot.rubric_id if snapshot else (moss.last_rubric_id if moss else None)
    rubric_text = snapshot.rubric_text if snapshot else (moss.last_rubric_text if moss else None)
    turn_id = assist.begin_grading() if assist else 0

    await _queue_rtvi(
        params,
        {"type": "user_answer", "text": answer_text, "turn_id": turn_id},
    )
    await _queue_rtvi(
        params,
        {"type": "grading_started", "topic": rubric_id, "turn_id": turn_id},
    )

    # Ack immediately so Pipecat does not block speech or reinject a long grade into the LLM.
    await params.result_callback(
        {
            "ok": True,
            "status": "queued",
            "instruction": "Continue speaking your follow-up. Never read scores or tips aloud.",
        }
    )

    if assist is None:
        return

    worker = params.pipeline_worker

    async def _background_grade() -> None:
        try:
            # Let the coach finish speaking / TTFT before competing for Ollama GPU.
            await _wait_until_coach_quiet(assist, timeout_secs=12.0)
            if not assist.grading_still_current(turn_id):
                return
            async with assist._grade_lock:
                if not assist.grading_still_current(turn_id):
                    return
                # Brief extra settle so Whisper/Piper aren't fighting inference.
                await asyncio.sleep(0.35)
                if not assist.grading_still_current(turn_id):
                    return
                try:
                    result = await _grade_in_subprocess(
                        question=question_text,
                        answer=answer_text,
                        rubric_id=rubric_id,
                        rubric_text=rubric_text,
                        track_label=track_label,
                        grader_persona=track_meta.get(
                            "grader_persona",
                            "strict technical interview grader",
                        ),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"Background grader subprocess failed: {exc}")
                    result = _fallback_grade_result(rubric_id, track_meta=track_meta)
            if not assist.grading_still_current(turn_id):
                return
            grade_payload = result.model_dump()
            grade_payload["turn_id"] = turn_id
            await worker.queue_frame(RTVIServerMessageFrame(data=grade_payload))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Background grade task crashed: {exc}")

    task = asyncio.create_task(_background_grade(), name=f"moss-grade-{turn_id}")
    assist.track_grade_task(task)


async def _queue_rtvi(params: FunctionCallParams, payload: dict[str, Any]) -> None:
    await params.pipeline_worker.queue_frame(RTVIServerMessageFrame(data=payload))


async def _wait_until_coach_quiet(
    assist: InterviewAssistState,
    *,
    timeout_secs: float,
    start_timeout_secs: float = 4.0,
) -> None:
    """Block until the coach's spoken follow-up is done.

    Grading is launched straight after the tool ack, while the follow-up is
    still being generated — so `bot_speaking` is False and the gap before
    speech starts looks identical to silence. Waiting on silence alone
    therefore returned after ~450ms and put the grader's Ollama request in
    competition with the coach's own response, which hurts on a single local
    GPU. Wait for speech to actually begin first, then for it to finish.
    """
    deadline = time.perf_counter() + timeout_secs
    start_deadline = min(deadline, time.perf_counter() + start_timeout_secs)
    turns_before = assist.bot_speech_turns

    # Wait for the follow-up to start. Bounded, because the coach may not speak
    # at all for this turn; the turn counter also covers an utterance that began
    # and ended between polls.
    while (
        not assist.bot_speaking
        and assist.bot_speech_turns == turns_before
        and time.perf_counter() < start_deadline
    ):
        await asyncio.sleep(0.12)

    # Then wait it out, plus a short quiet period so a multi-segment utterance
    # can finish before grading starts.
    quiet_for = 0.0
    while time.perf_counter() < deadline:
        if assist.bot_speaking:
            quiet_for = 0.0
        else:
            quiet_for += 0.12
            if quiet_for >= 0.45:
                return
        await asyncio.sleep(0.12)


def _extract_question(
    coach_text: str,
    *,
    prefer_interrogative: bool = True,
) -> str | None:
    text = re.sub(r"\s+", " ", coach_text).strip()
    if not text:
        return None
    parts = re.split(r"(?<=[.?!])\s+", text)
    questions = [p.strip() for p in parts if "?" in p]
    if questions:
        return questions[-1]
    if prefer_interrogative:
        # Avoid flashing non-questions mid interview when tools interleave text.
        return None
    return parts[-1] if parts else text


def _fallback_grade_result(
    rubric_id: str | None,
    *,
    track_meta: dict[str, Any] | None = None,
) -> GradeResult:
    """Grade shown when the grader subprocess fails.

    Tips come from the active track — the generic default below is only used
    when a track omits them, so an ML or agent-infra candidate is not handed
    system-design advice.
    """
    tips = (track_meta or {}).get("fallback_tips")
    return GradeResult(
        topic=rubric_id,
        score=3,
        summary="Could not grade this turn automatically. Keep covering trade-offs.",
        tips=list(tips)
        if tips
        else [
            "State your assumptions out loud before you go deeper.",
            "Compare at least two alternatives with explicit trade-offs.",
            "Name the main constraint and how you would address it.",
        ],
    )


def _grade_result_from_worker_payload(
    data: dict[str, Any],
    *,
    rubric_id: str | None,
) -> GradeResult:
    score = int(data.get("score", 3))
    score = max(1, min(5, score))
    tips_raw = data.get("tips") or []
    tips = [str(t).strip() for t in tips_raw if str(t).strip()][:4]
    topic = str(data["topic"]) if data.get("topic") else rubric_id
    return GradeResult(
        topic=topic,
        score=score,
        # Clamped like `score`: the payload is LLM-derived, and a negative
        # max_score would otherwise fail validation inside the grade task.
        max_score=max(1, int(data.get("max_score") or 5)),
        summary=str(
            data.get("summary") or "Review the rubric points for this topic."
        ).strip(),
        tips=tips
        or [
            "Call out concrete trade-offs.",
            "Name the bottleneck and how you scale it.",
        ],
    )


async def _terminate_grader(proc: asyncio.subprocess.Process) -> None:
    """Kill a grader subprocess and reap it. Best-effort; never raises.

    ``asyncio.shield`` keeps the reap alive when the caller is already being
    cancelled, so the process is collected rather than left as a zombie.
    """
    if proc.returncode is not None:
        return
    with suppress(ProcessLookupError, OSError):
        proc.kill()
    with suppress(asyncio.CancelledError, asyncio.TimeoutError, OSError):
        await asyncio.wait_for(asyncio.shield(proc.wait()), timeout=5.0)


async def _grade_in_subprocess(
    *,
    question: str,
    answer: str,
    rubric_id: str | None,
    rubric_text: str | None,
    track_label: str,
    grader_persona: str,
) -> GradeResult:
    """Run grading in a separate Python process so it never shares the coach loop."""
    if not GRADER_WORKER_PATH.is_file():
        raise FileNotFoundError(f"Grader worker missing: {GRADER_WORKER_PATH}")

    job = {
        "question": question,
        "answer": answer,
        "rubric_id": rubric_id,
        "rubric_text": rubric_text,
        "track_label": track_label,
        "grader_persona": grader_persona,
        "model": OLLAMA_GRADE_MODEL,
        "base_url": OLLAMA_BASE_URL,
    }
    # The grader only talks to local Ollama, and takes model/base_url from the
    # stdin job above — it reads no environment at all. Strip MOSS_* so the
    # cloud credentials load_dotenv() put in this process do not reach it.
    grader_env = {k: v for k, v in os.environ.items() if not k.startswith("MOSS_")}
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(GRADER_WORKER_PATH),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=grader_env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(json.dumps(job).encode("utf-8")),
            timeout=GRADE_SUBPROCESS_TIMEOUT_SECS,
        )
    except asyncio.TimeoutError as exc:
        await _terminate_grader(proc)
        raise TimeoutError(
            f"Grader subprocess timed out after {GRADE_SUBPROCESS_TIMEOUT_SECS:.0f}s"
        ) from exc
    except asyncio.CancelledError:
        # on_client_disconnected cancels every in-flight grade. Without this the
        # CancelledError would propagate straight out of communicate() and leave
        # grader_worker.py — and its Ollama request — running past the session.
        await _terminate_grader(proc)
        raise
    except BaseException:
        await _terminate_grader(proc)
        raise

    err_text = (stderr or b"").decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        raise RuntimeError(
            f"grader_worker exit={proc.returncode}"
            + (f": {err_text}" if err_text else "")
        )

    payload = json.loads((stdout or b"").decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("grader_worker returned non-object JSON")
    return _grade_result_from_worker_payload(payload, rubric_id=rubric_id)


def _last_user_text(context: LLMContext) -> str | None:
    for message in reversed(context.get_messages()):
        if not isinstance(message, dict):
            continue
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            chunks: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    chunks.append(str(part.get("text", "")))
                elif isinstance(part, str):
                    chunks.append(part)
            joined = " ".join(chunks).strip()
            if joined:
                return joined
    return None


def _upsert_system_message(context: LLMContext, content: str) -> None:
    messages = list(context.get_messages())
    system_msg = {"role": "system", "content": content}
    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        messages[0] = system_msg
    else:
        messages.insert(0, system_msg)
    context.set_messages(messages)


def _resolve_whisper_model(name: str) -> str | WhisperModel:
    key = name.strip().lower().replace("-", "_")
    mapping = {
        "tiny": WhisperModel.TINY,
        "base": WhisperModel.BASE,
        "small": WhisperModel.SMALL,
        "medium": WhisperModel.MEDIUM,
        "large": WhisperModel.LARGE,
        "large_v3": WhisperModel.LARGE,
    }
    return mapping.get(key, name)


async def run_interview_bot(
    webrtc_connection: SmallWebRTCConnection,
    track_id: str = DEFAULT_TRACK_ID,
) -> None:
    # The slot is reserved by offer() before this task is created, so every exit
    # path here — including the readiness check below — must release it.
    try:
        await _run_interview_bot(webrtc_connection, track_id)
    finally:
        await release_bot_slot()


async def _run_interview_bot(
    webrtc_connection: SmallWebRTCConnection,
    track_id: str = DEFAULT_TRACK_ID,
) -> None:
    track_id = normalize_track_id(track_id)
    if moss_client is None or not moss_indexes_ready.get(track_id):
        raise RuntimeError(
            f"Moss index for track '{track_id}' is not ready. "
            "Run ingest_knowledge.py first."
        )

    track = INTERVIEW_TRACKS[track_id]
    index_name = track["index_name"]
    system_prompt = build_system_prompt(track_id)

    session: ActiveSession | None = None
    try:
        transport = SmallWebRTCTransport(
            webrtc_connection=webrtc_connection,
            params=TransportParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
            ),
        )

        stt = WhisperSTTService(
            device=WHISPER_DEVICE,
            settings=WhisperSTTService.Settings(model=_resolve_whisper_model(WHISPER_MODEL)),
        )
        llm = OLLamaLLMService(
            base_url=OLLAMA_BASE_URL,
            settings=OLLamaLLMService.Settings(
                model=OLLAMA_MODEL,
                system_instruction=system_prompt,
            ),
        )
        tts = PiperTTSService(
            settings=PiperTTSService.Settings(voice=PIPER_VOICE),
        )

        assist_state = InterviewAssistState()
        moss_injector = MossContextInjector(
            moss_client,
            system_prompt=system_prompt,
            index_name=index_name,
            assist_state=assist_state,
        )

        # Bind each tool call to the turn it was issued for, while that turn is
        # still current. Fires when the LLM announces its calls, before the
        # runner executes them — so a call that later runs after the candidate
        # has spoken again still grades the right transcript.
        @llm.event_handler("on_function_calls_started")
        async def on_function_calls_started(service: Any, function_calls: Any) -> None:
            snapshot = CallSnapshot(
                answer=moss_injector.last_user_answer,
                question=assist_state.last_question,
                rubric_id=moss_injector.last_rubric_id,
                rubric_text=moss_injector.last_rubric_text,
            )
            for call in function_calls:
                assist_state.record_call_snapshot(call.tool_call_id, snapshot)

        context = LLMContext(
            messages=[{"role": "system", "content": system_prompt}],
            tools=[grade_candidate_answer],
        )
        user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
            context,
            user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
        )

        question_emitter = CoachQuestionEmitter(assist_state)
        interruption_bridge = InterruptionBridge(assist_state)
        bot_speech_tracker = BotSpeechTracker(assist_state)

        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                user_aggregator,
                moss_injector,
                llm,
                question_emitter,
                # Upstream of the output transport so its RTVI messages reach the client.
                interruption_bridge,
                tts,
                transport.output(),
                # Downstream of the output transport, which is what emits the
                # Bot{Started,Stopped}SpeakingFrame this reads.
                bot_speech_tracker,
                assistant_aggregator,
            ]
        )

        worker = PipelineWorker(
            pipeline,
            params=PipelineParams(
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
            app_resources={
                "moss": moss_injector,
                "assist": assist_state,
                "track": track,
            },
        )

        # Registered so the lifespan shutdown can reach this interview; Uvicorn
        # keeps the signal handlers, so nothing else would cancel it on Ctrl-C.
        session = ActiveSession(worker, assist_state)
        active_sessions.add(session)

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport: SmallWebRTCTransport, client: Any) -> None:
            logger.info(f"Client connected over SmallWebRTC (track={track_id})")

        # Greet on the RTVI ready handshake rather than a fixed sleep after the
        # WebRTC connect. A transport-level connection does not mean the RTVI
        # client is listening yet, so a slow connect could swallow the opening
        # question and its audio. `on_client_ready` is exactly that signal.
        # PipelineWorker enables RTVI by default and add_event_handler appends,
        # so this runs alongside pipecat's own set_bot_ready() handler.
        greeted = False
        client_ready = asyncio.Event()

        @worker.rtvi.event_handler("on_client_ready")
        async def on_client_ready(rtvi: Any) -> None:
            client_ready.set()
            # A client that re-sends ready (reconnect) must not replay the
            # welcome over an interview already in progress.
            nonlocal greeted
            if greeted:
                return
            greeted = True
            logger.info(f"RTVI client ready (track={track_id}); sending welcome")
            welcome = track["welcome"]
            assist_state.bot_buf = [welcome + " "]
            assist_state.last_question = _extract_question(
                welcome, prefer_interrogative=False
            )
            await worker.queue_frame(
                RTVIServerMessageFrame(
                    data={
                        "type": "interview_track",
                        "track_id": track_id,
                        "label": track["label"],
                    }
                )
            )
            if assist_state.last_question:
                await worker.queue_frame(
                    RTVIServerMessageFrame(
                        data={
                            "type": "current_question",
                            "text": assist_state.last_question,
                        }
                    )
                )
            await worker.queue_frame(TTSSpeakFrame(welcome))

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport: SmallWebRTCTransport, client: Any) -> None:
            logger.info("Client disconnected; ending pipeline.")
            await ActiveSession(worker, assist_state).shutdown()

        # This runner is per-session and lives inside Uvicorn, so it must not
        # own process signals. WorkerRunner defaults handle_sigint=True and
        # calls loop.add_signal_handler(SIGINT, ...) in run(), which *replaces*
        # Uvicorn's handler — and it never removes it, so Ctrl-C would stay
        # bound to a dead runner for the rest of the process. Uvicorn keeps
        # signal handling; the worker is still torn down from
        # on_client_disconnected above.
        runner = WorkerRunner(handle_sigint=False, handle_sigterm=False)

        async def _handshake_watchdog(current: ActiveSession) -> None:
            """Tear the session down if the client never finishes connecting.

            /api/offer accepts an SDP and starts the pipeline immediately, so a
            caller that never completes the WebRTC/RTVI handshake would leave
            Whisper, Piper and Ollama loaded until the transport happened to
            notice or the process exited.
            """
            try:
                await asyncio.wait_for(
                    client_ready.wait(), timeout=SESSION_HANDSHAKE_TIMEOUT_SECS
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"No client handshake within {SESSION_HANDSHAKE_TIMEOUT_SECS:.0f}s "
                    f"(track={track_id}); ending session."
                )
                await current.shutdown()

        watchdog = asyncio.create_task(_handshake_watchdog(session))
        try:
            await runner.add_workers(worker)
            await runner.run()
        finally:
            watchdog.cancel()
            with suppress(asyncio.CancelledError):
                await watchdog
    finally:
        if session is not None:
            # runner.run() can also end on a transport or LLM error, which
            # reaches none of the disconnect / watchdog / lifespan paths. Tear
            # the session down here before dropping the only handle to it, or a
            # spawned grader keeps its subprocess and Ollama request alive until
            # timeout and then queues a result into a dead worker.
            with suppress(Exception):
                await session.shutdown()
            active_sessions.discard(session)


async def ensure_moss_loaded() -> None:
    global moss_client, moss_ready, moss_indexes_ready
    project_id = os.getenv("MOSS_PROJECT_ID", "").strip()
    project_key = os.getenv("MOSS_PROJECT_KEY", "").strip()
    if not project_id or not project_key:
        logger.warning("Moss credentials missing; server will start but interviews will fail.")
        return

    moss_client = MossClient(project_id, project_key)
    ready: dict[str, bool] = {}
    for track_id, meta in INTERVIEW_TRACKS.items():
        index_name = meta["index_name"]
        try:
            await moss_client.load_index(index_name)
            ready[track_id] = True
            logger.info(f"Moss index '{index_name}' loaded (track={track_id}).")
        except Exception as exc:  # noqa: BLE001
            ready[track_id] = False
            logger.error(
                f"Failed to load Moss index '{index_name}' (track={track_id}): {exc}. "
                "Run `python ingest_knowledge.py` first."
            )
    moss_indexes_ready = ready
    moss_ready = any(ready.values())
    if moss_ready and not all(ready.values()):
        missing = [tid for tid, ok in ready.items() if not ok]
        logger.warning(f"Some interview tracks are unavailable until re-ingest: {missing}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_moss_loaded()
    try:
        yield
    finally:
        # Uvicorn owns SIGINT/SIGTERM, so on Ctrl-C it stops accepting requests
        # but nothing cancels an interview already in flight — it would hold
        # Whisper / Ollama / Piper and any grading subprocess until the shutdown
        # timeout. Cancel them here instead.
        sessions = list(active_sessions)
        active_sessions.clear()
        if sessions:
            logger.info(f"Shutting down {len(sessions)} active interview(s)")
            await asyncio.gather(
                *(s.shutdown() for s in sessions), return_exceptions=True
            )

        # Then the detached interview tasks themselves, so none outlive the app.
        tasks = [t for t in bot_tasks if not t.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        bot_tasks.clear()


app = FastAPI(title="Interview Coach", lifespan=lifespan)

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
if "*" in cors_origins:
    logger.warning(
        "CORS_ORIGINS contains '*'. /api/offer is unauthenticated — list explicit origins."
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    # No endpoint here reads cookies or an Authorization header, so credentialed
    # cross-origin requests are never needed. Leaving this on would make a
    # wildcard CORS_ORIGINS reflect the caller's origin.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _ollama_model_available(available: set[str], wanted: str) -> bool:
    """Ollama lists fully-qualified tags (`llama3.1:latest`); config omits `:latest`."""
    return wanted in available or (":" not in wanted and f"{wanted}:latest" in available)


@app.get("/health")
async def health() -> dict[str, Any]:
    ollama_ok = False
    ollama_error: str | None = None
    missing_models: list[str] = []
    try:
        base = OLLAMA_BASE_URL.removesuffix("/v1")
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{base}/api/tags")
        if resp.status_code != 200:
            ollama_error = f"status={resp.status_code}"
        else:
            payload = resp.json()
            entries = payload.get("models") or []
            available = {
                str(entry.get("name") or entry.get("model") or "")
                for entry in entries
                if isinstance(entry, dict)
            }
            available.discard("")
            # A responding daemon is not enough. An unpulled model would only
            # fail later, inside the background pipeline, after WebRTC is
            # already negotiated — so refuse the interview here instead.
            missing_models = sorted(
                {OLLAMA_MODEL, OLLAMA_GRADE_MODEL}
                - {m for m in {OLLAMA_MODEL, OLLAMA_GRADE_MODEL} if _ollama_model_available(available, m)}
            )
            if missing_models:
                ollama_error = "missing Ollama model(s): " + ", ".join(
                    f"{m} (ollama pull {m})" for m in missing_models
                )
            else:
                ollama_ok = True
    except Exception as exc:  # noqa: BLE001
        ollama_error = str(exc)

    return {
        "ok": moss_ready and ollama_ok,
        "moss_ready": moss_ready,
        "moss_indexes": {
            track_id: {
                "index_name": meta["index_name"],
                "ready": moss_indexes_ready.get(track_id, False),
            }
            for track_id, meta in INTERVIEW_TRACKS.items()
        },
        "moss_index_names": all_index_names(),
        "ollama_ok": ollama_ok,
        "ollama_error": ollama_error,
        "ollama_missing_models": missing_models,
        "ollama_model": OLLAMA_MODEL,
        "ollama_grade_model": OLLAMA_GRADE_MODEL,
        "whisper_model": WHISPER_MODEL,
        "piper_voice": PIPER_VOICE,
        "grader_worker": GRADER_WORKER_PATH.is_file(),
        "active_bots": active_bots,
    }


@app.get("/api/tracks")
async def list_tracks() -> dict[str, Any]:
    return {
        "tracks": [
            {
                "id": track_id,
                "label": meta["label"],
                "blurb": meta["blurb"],
                "index_name": meta["index_name"],
                "ready": moss_indexes_ready.get(track_id, False),
            }
            for track_id, meta in INTERVIEW_TRACKS.items()
        ],
        "default": DEFAULT_TRACK_ID,
    }


async def _json_object_body(request: Request) -> dict[str, Any]:
    """Parse a JSON object body, reporting bad input as 400 rather than 500."""
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail="Request body must be valid JSON"
        ) from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")
    return body


@app.post("/api/offer")
async def offer(request: Request) -> dict[str, Any]:
    try:
        track_id = resolve_track_id_for_offer(request.query_params.get("topic"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not moss_indexes_ready.get(track_id):
        index_name = track_index_name(track_id)
        raise HTTPException(
            status_code=503,
            detail=(
                f"Moss index '{index_name}' for track '{track_id}' is not loaded. "
                "Run ingest_knowledge.py and restart the server."
            ),
        )
    if not GRADER_WORKER_PATH.is_file():
        raise HTTPException(
            status_code=503,
            detail=f"Grader worker missing at {GRADER_WORKER_PATH.name}.",
        )
    # Parse and validate before reserving. A slot is scarce, and reading the
    # request body can stall on a slow client — holding capacity for an offer
    # that may never be well-formed enough to start a bot.
    body = await _json_object_body(request)
    try:
        offer_request = SmallWebRTCRequest.from_dict(body)
    except (KeyError, TypeError, ValueError) as exc:
        # A malformed offer is the caller's mistake, not a server fault.
        logger.warning(f"Malformed WebRTC offer: {exc}")
        raise HTTPException(
            status_code=422, detail=f"Malformed WebRTC offer: {exc}"
        ) from exc

    # Reserve immediately before handling: every session loads Whisper/Piper and
    # competes for the same local Ollama, so unbounded offers would degrade the
    # live ones. Taken here rather than inside the bot task — that runs several
    # awaits later, so concurrent offers would all pass a mere check and
    # overshoot the limit together.
    if not await reserve_bot_slot():
        raise HTTPException(
            status_code=503,
            detail=(
                f"At capacity: {MAX_ACTIVE_BOTS} interview(s) already running "
                f"(MAX_ACTIVE_BOTS={MAX_ACTIVE_BOTS}). Try again shortly."
            ),
        )
    # Ownership of the reserved slot moves to the bot task once it is created;
    # until then this request must hand it back on every failure path.
    slot_handed_over = False
    try:

        async def webrtc_connection_callback(connection: SmallWebRTCConnection) -> None:
            # Detached deliberately, not a Starlette background task. Those are
            # awaited as part of the request lifecycle, and uvicorn waits for
            # outstanding request tasks *before* running lifespan shutdown — with
            # timeout_graceful_shutdown defaulting to None, that wait is unbounded.
            # An interview attached to the request would therefore hang Ctrl-C
            # forever and the lifespan cleanup below would never get to cancel it.
            nonlocal slot_handed_over
            task = asyncio.create_task(
                run_interview_bot(connection, track_id),
                name=f"moss-interview-{track_id}",
            )
            # From here run_interview_bot's finally releases the slot, so this
            # request must not — even if handle_web_request fails afterwards.
            slot_handed_over = True
            bot_tasks.add(task)
            task.add_done_callback(_on_bot_task_done)

        try:
            answer = await small_webrtc_handler.handle_web_request(
                request=offer_request,
                webrtc_connection_callback=webrtc_connection_callback,
            )
        except HTTPException:
            # Already carries an intended status; do not flatten it to a 500.
            raise
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning(f"Malformed WebRTC offer: {exc}")
            raise HTTPException(
                status_code=422, detail=f"Malformed WebRTC offer: {exc}"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to handle WebRTC offer")
            raise HTTPException(
                status_code=500,
                detail="Failed to handle WebRTC offer",
            ) from exc
    finally:
        if not slot_handed_over:
            await release_bot_slot()

    return answer


@app.patch("/api/offer")
async def offer_patch(request: Request) -> dict[str, str]:
    body = await _json_object_body(request)

    pc_id = body.get("pc_id")
    if not isinstance(pc_id, str) or not pc_id:
        raise HTTPException(status_code=400, detail="pc_id is required and must be a string")

    raw_candidates = body.get("candidates", [])
    if not isinstance(raw_candidates, list):
        raise HTTPException(status_code=400, detail="candidates must be a list")
    try:
        candidates = [IceCandidate(**c) for c in raw_candidates]
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422, detail=f"Malformed ICE candidate: {exc}"
        ) from exc

    try:
        await small_webrtc_handler.handle_patch_request(
            SmallWebRTCPatchRequest(pc_id=pc_id, candidates=candidates)
        )
    except HTTPException:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning(f"Malformed ICE patch request: {exc}")
        raise HTTPException(
            status_code=422, detail=f"Malformed ICE patch request: {exc}"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to patch WebRTC ICE candidates")
        raise HTTPException(
            status_code=500,
            detail="Failed to patch WebRTC ICE candidates",
        ) from exc
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    # Loopback by default. /api/offer is unauthenticated and CORS does not stop
    # non-browser callers, so binding every interface would let anyone on the
    # network start Whisper/Ollama/Piper work and grader subprocesses on this
    # machine — and spend the project's Moss quota. Set BACKEND_HOST explicitly
    # (e.g. 0.0.0.0) to expose it on purpose.
    uvicorn.run(
        "server:app",
        host=os.getenv("BACKEND_HOST", "127.0.0.1"),
        port=int(os.getenv("BACKEND_PORT", "8000")),
        # Off by default: a reload mid-interview kills live WebRTC sessions and
        # can orphan grader subprocesses. Opt in with BACKEND_RELOAD=1.
        reload=os.getenv("BACKEND_RELOAD", "").strip().lower() in {"1", "true", "yes"},
    )
