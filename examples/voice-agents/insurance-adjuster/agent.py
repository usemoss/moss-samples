"""
Insurance Claims Adjuster Voice Agent

Startup: prewarm_fnc loads ALL indexes simultaneously via asyncio.gather +
moss.session() before the first call arrives. Zero per-call loading delay.

Per call: entrypoint picks the right pre-warmed session from WorkerState.

Three ambient queries per turn (SessionIndex.query, all in-process):
  1. kb_session      - shared HO-3 policy language, exclusions, state rules
  2. policy_session  - this policyholder's declarations, limits, deductibles
  3. claim_session   - live findings for this inspection (grows as adjuster talks)

Three write tools: load_policy, log_finding, submit_report.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    ChatContext,
    ChatMessage,
    JobContext,
    JobProcess,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
)
from livekit.plugins import cartesia, deepgram, openai
from moss import DocumentInfo, MossClient, QueryOptions, SessionIndex

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s"
)
logger = logging.getLogger("insurance-adjuster")

CLAIMS_KB = "claims-kb"
POLICY_INDEXES = [
    "policy-fl-ho3-001",
    "policy-ca-ho3-002",
    "policy-tx-ho3-003",
]
REPORT_DIR = Path(os.getenv("CLAIM_REPORT_DIR", "./claim-reports"))


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing env var: {name}. Check your .env file.")
    return value


# ---------------------------------------------------------------------------
# Worker-level pre-warmed state (shared across all jobs in this process)
# ---------------------------------------------------------------------------


@dataclass
class WorkerState:
    moss: MossClient
    kb_session: SessionIndex
    policy_sessions: dict[str, SessionIndex]  # index_name -> session


# ---------------------------------------------------------------------------
# Per-call session state
# ---------------------------------------------------------------------------


@dataclass
class SessionData:
    worker: WorkerState
    kb_session: SessionIndex  # alias to worker.kb_session
    policy: str | None = None
    policy_session: SessionIndex | None = None
    claim_session: SessionIndex | None = None
    findings: list[dict] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    room: object = None


async def _start_claim_session(data: SessionData) -> None:
    if data.claim_session or not data.policy:
        return
    name = f"claim-{data.policy.lower()}-{int(data.started_at)}"
    data.claim_session = await data.worker.moss.session(name)
    logger.info("claim session created: %s", name)


async def _publish_moss_event(
    data: SessionData, query: str, index_name: str, result, timestamp: float
) -> None:
    """Publish a moss_context data message so the frontend retrieval strip updates."""
    if not data.room:
        return
    payload = json.dumps(
        {
            "type": "moss_context",
            "data": {
                "query": query,
                "index_name": index_name,
                "matches": [
                    {"text": d.text, "score": getattr(d, "score", None)}
                    for d in result.docs[:3]
                ],
                "time_taken_ms": result.time_taken_ms,
                "timestamp": timestamp,
            },
        }
    ).encode()
    try:
        await data.room.local_participant.publish_data(payload, reliable=False)
    except Exception as e:
        logger.warning("moss_context publish failed: %s", e)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

INSTRUCTIONS = """You are a voice assistant for field insurance claims adjusters.
You help adjusters on-site answer coverage questions and document damage, hands-free.

Context is automatically retrieved and injected before each of your responses:
  - "Policy context": this policy's specific limits, deductibles, endorsements
  - "Claims KB context": HO-3 coverage rules, exclusions, state guidelines
  - "Findings logged so far": damage items already recorded this inspection

Use the findings context to answer questions like "what have I logged?",
"what is my total covered?", or "have I documented the roof yet?" without
asking the adjuster to repeat themselves.

Answer directly from the injected context. Never invent coverage amounts or policy language.
If the context does not cover the question, say so and offer to escalate.

Flow: ask for the policy number, call load_policy, answer coverage questions,
call log_finding for each damage item, call submit_report at the end.

Voice rules: keep every response under 25 words. State one fact at a time.
Repeat dollar amounts back to confirm."""


class AdjusterAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=INSTRUCTIONS)

    async def on_enter(self) -> None:
        data: SessionData = self.session.userdata
        if data.policy:
            await self.session.say(
                f"Claims assistant ready. Policy {data.policy} loaded. What would you like to check?"
            )
        else:
            await self.session.say("Claims assistant ready. What's the policy number?")

    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage
    ) -> None:
        """Ambient retrieval: query all three sessions in parallel before the LLM responds."""
        data: SessionData = self.session.userdata
        query = (new_message.text_content or "").strip()
        if not query:
            await super().on_user_turn_completed(turn_ctx, new_message)
            return

        # All queries run against local SessionIndex objects - no cloud round-trip
        tasks: list = [
            data.kb_session.query(query, QueryOptions(top_k=3, alpha=0.72)),
        ]
        if data.policy_session:
            tasks.append(
                data.policy_session.query(query, QueryOptions(top_k=3, alpha=0.75))
            )
        if data.claim_session and data.claim_session.doc_count > 0:
            tasks.append(
                data.claim_session.query(query, QueryOptions(top_k=3, alpha=0.7))
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        kb_result = results[0] if not isinstance(results[0], Exception) else None
        policy_result = (
            results[1]
            if len(results) > 1 and not isinstance(results[1], Exception)
            else None
        )
        findings_result = (
            results[2]
            if len(results) > 2 and not isinstance(results[2], Exception)
            else None
        )

        now = time.time()

        if policy_result and policy_result.docs:
            logger.info(
                "policy: %d docs in %dms",
                len(policy_result.docs),
                policy_result.time_taken_ms,
            )
            lines = "\n".join(f"- {d.text}" for d in policy_result.docs)
            turn_ctx.add_message(
                role="system",
                content=(f"Policy context for {data.policy}:\n---\n{lines}\n---"),
            )
            await _publish_moss_event(
                data, query, f"policy-{data.policy.lower()}", policy_result, now
            )

        if kb_result and kb_result.docs:
            logger.info(
                "claims-kb: %d docs in %dms",
                len(kb_result.docs),
                kb_result.time_taken_ms,
            )
            lines = "\n".join(f"- {d.text}" for d in kb_result.docs)
            turn_ctx.add_message(
                role="system",
                content=(
                    f"Claims KB context (HO-3 rules, exclusions, state guidelines):\n---\n{lines}\n---"
                ),
            )
            await _publish_moss_event(data, query, CLAIMS_KB, kb_result, now)

        if findings_result and findings_result.docs:
            logger.info(
                "findings session: %d docs in %dms",
                len(findings_result.docs),
                findings_result.time_taken_ms,
            )
            lines = "\n".join(f"- {d.text}" for d in findings_result.docs)
            turn_ctx.add_message(
                role="system",
                content=(f"Findings logged so far this inspection:\n---\n{lines}\n---"),
            )
            await _publish_moss_event(
                data, query, data.claim_session.name, findings_result, now
            )

        await super().on_user_turn_completed(turn_ctx, new_message)

    @function_tool
    async def load_policy(self, _context: RunContext, policy_number: str) -> str:
        """Load the per-policy session. Call as soon as the adjuster gives a policy number."""
        import re

        data: SessionData = self.session.userdata
        raw = policy_number.strip().upper().replace(" ", "").replace("-", "")
        m = re.match(r"^([A-Z]{2})(HO\d)(0{0,1}\d{3})$", raw)
        clean = (
            f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            if m
            else policy_number.strip().upper()
        )
        index = f"policy-{clean.lower()}"

        session = data.worker.policy_sessions.get(index)
        if not session:
            return f"Policy {clean} not found. Available: FL-HO3-001, CA-HO3-002, TX-HO3-003."

        data.policy = clean
        data.policy_session = session
        await _start_claim_session(data)
        logger.info("policy session activated: %s", index)
        return f"Policy {clean} ready. What would you like to check?"

    @function_tool
    async def log_finding(
        self,
        _context: RunContext,
        description: str,
        estimated_value: float,
        covered: bool,
        note: str,
    ) -> str:
        """Record a damage item and its coverage determination.

        description: what was damaged (e.g. "roof shingles, wind damage")
        estimated_value: repair/replacement cost in USD
        covered: True if covered under the policy, False if not
        note: the policy provision or exclusion that applies
        """
        data: SessionData = self.session.userdata
        idx = len(data.findings) + 1
        status = "COVERED" if covered else "NOT COVERED"

        data.findings.append(
            {
                "description": description,
                "estimated_value": estimated_value,
                "covered": covered,
                "note": note,
            }
        )

        if data.claim_session:
            await data.claim_session.add_docs(
                [
                    DocumentInfo(
                        id=f"finding-{idx}",
                        text=f"Finding {idx}: {description}. {status}. {note}",
                        metadata={
                            "covered": str(covered).lower(),
                            "estimated_value": str(estimated_value),
                            "finding_index": str(idx),
                        },
                    )
                ]
            )

        if data.room:
            try:
                await data.room.local_participant.publish_data(
                    json.dumps(
                        {
                            "type": "claim_update",
                            "policy": data.policy,
                            "findings": data.findings,
                        }
                    ).encode(),
                    reliable=True,
                )
            except Exception as e:
                logger.warning("publish_data failed: %s", e)

        logger.info(
            "finding %d: %s, $%.0f, %s", idx, description[:60], estimated_value, status
        )
        return f"Finding {idx} logged: {status}, ${estimated_value:,.0f}."

    @function_tool
    async def submit_report(self, _context: RunContext) -> str:
        """Finalise the inspection: push findings to cloud and write a local JSON report."""
        data: SessionData = self.session.userdata
        covered = [f for f in data.findings if f["covered"]]
        not_covered = [f for f in data.findings if not f["covered"]]

        session_ref: str | None = None
        if data.claim_session:
            try:
                result = await data.claim_session.push_index()
                session_ref = data.claim_session.name
                logger.info(
                    "claim session pushed: %s (job %s)", session_ref, result.job_id
                )
            except Exception as e:
                logger.warning("push_index failed: %s", e)

        report = {
            "policy": data.policy,
            "claim_session": session_ref,
            "duration_sec": int(time.time() - data.started_at),
            "findings": data.findings,
            "total_covered": sum(f["estimated_value"] for f in covered),
            "total_not_covered": sum(f["estimated_value"] for f in not_covered),
        }

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        path = (
            REPORT_DIR
            / f"{(data.policy or 'unknown').lower()}__{int(data.started_at)}.json"
        )
        path.write_text(json.dumps(report, indent=2))
        logger.info("report written: %s", path)

        if data.room:
            try:
                await data.room.local_participant.publish_data(
                    json.dumps({"type": "report_submitted", **report}).encode(),
                    reliable=True,
                )
            except Exception as e:
                logger.warning("publish_data failed: %s", e)

        return (
            f"Report saved. {len(covered)} covered items, ${report['total_covered']:,.0f}. "
            f"{len(not_covered)} not covered, ${report['total_not_covered']:,.0f}."
        )


# ---------------------------------------------------------------------------
# Worker pre-warm — runs once per process, before any job is accepted
# ---------------------------------------------------------------------------


async def _prewarm_async(proc: JobProcess) -> None:
    moss = MossClient(
        _require_env("MOSS_PROJECT_ID"),
        _require_env("MOSS_PROJECT_KEY"),
    )

    all_names = [CLAIMS_KB] + POLICY_INDEXES
    logger.info("pre-warming %d indexes in parallel: %s", len(all_names), all_names)

    sessions = await asyncio.gather(
        *(moss.session(name) for name in all_names),
        return_exceptions=True,
    )

    kb_session = None
    policy_sessions: dict[str, SessionIndex] = {}

    for name, result in zip(all_names, sessions):
        if isinstance(result, Exception):
            logger.error("failed to load '%s': %s", name, result)
        elif name == CLAIMS_KB:
            kb_session = result
            logger.info("  %s ready", name)
        else:
            policy_sessions[name] = result
            logger.info("  %s ready", name)

    if kb_session is None:
        raise RuntimeError("claims-kb failed to load — run create_indexes.py first")

    proc.userdata["worker"] = WorkerState(
        moss=moss,
        kb_session=kb_session,
        policy_sessions=policy_sessions,
    )
    logger.info("all indexes warm, worker ready")


def prewarm(proc: JobProcess) -> None:
    """Sync wrapper — livekit-agents calls prewarm_fnc without await."""
    load_dotenv()
    asyncio.run(_prewarm_async(proc))


# ---------------------------------------------------------------------------
# Entrypoint — runs per call
# ---------------------------------------------------------------------------


def _policy_from_participants(room) -> str | None:
    for p in room.remote_participants.values():
        if p.metadata and p.metadata.strip():
            return p.metadata.strip().upper()
    return None


async def entrypoint(ctx: JobContext) -> None:
    logger.info("job received: room=%s", ctx.room.name)
    await ctx.connect()

    worker: WorkerState = ctx.proc.userdata["worker"]
    userdata = SessionData(
        worker=worker,
        kb_session=worker.kb_session,
        room=ctx.room,
    )

    # Policy pre-selected on the welcome screen arrives via participant metadata
    policy = _policy_from_participants(ctx.room) or os.getenv("POLICY_NUMBER")
    if policy:
        import re

        raw = policy.upper().replace(" ", "").replace("-", "")
        m = re.match(r"^([A-Z]{2})(HO\d)(0{0,1}\d{3})$", raw)
        clean = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else policy
        index = f"policy-{clean.lower()}"
        session = worker.policy_sessions.get(index)
        if session:
            userdata.policy = clean
            userdata.policy_session = session
            await _start_claim_session(userdata)
            logger.info("policy %s activated from pre-warmed sessions", clean)
        else:
            logger.warning(
                "policy %s not in pre-warmed set, agent will ask verbally", clean
            )

    lk_session = AgentSession[SessionData](
        userdata=userdata,
        stt=deepgram.STT(model="nova-3"),
        llm=openai.LLM(model="gpt-4.1"),
        tts=cartesia.TTS(model="sonic-3.5-2026-05-04"),
    )

    await lk_session.start(agent=AdjusterAgent(), room=ctx.room)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        )
    )
