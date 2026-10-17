"""
Candidate Screening Voice Agent
===============================

A live voice screening interview that grounds every question in two Moss
indexes:

  * a job description index  (e.g. ``job-senior-backend-payments``)
  * a candidate resume index (e.g. ``candidate-strong-match``)

The agent runs a five-phase interview - intro/consent, background
verification, role-fit screening, candidate Q&A, and close - and emits
a structured scorecard at the end. Both retrievals stay in-process for
sub-10ms latency, which matters because each turn typically needs at
least one resume lookup AND one JD lookup before the LLM can ask a good
follow-up.

Design notes:
  - One agent, phased system prompt. Phases are content, not personas.
  - Two retrieval tools (`lookup_job_requirement`, `lookup_resume_fact`)
    so logs make the asymmetry visible.
  - Rubric scores are captured as the conversation happens, not
    reconstructed from a transcript at the end.
  - Bias-mitigation rules are baked into the system prompt and the
    set of available tools (no tool to capture protected attributes).
"""

from __future__ import annotations

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
    JobContext,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
)
from livekit.plugins import cartesia, deepgram, openai, silero
from moss import MossClient, QueryOptions

load_dotenv()

JOB_INDEX = os.getenv("MOSS_JOB_INDEX_NAME", "job-senior-backend-payments")
CANDIDATE_INDEX = os.getenv("MOSS_CANDIDATE_INDEX_NAME", "candidate-strong-match")
SCORECARD_DIR = Path(os.getenv("SCREENING_SCORECARD_DIR", "./scorecards"))

logging.getLogger("livekit").setLevel(logging.WARNING)
logging.getLogger("livekit.agents").setLevel(logging.WARNING)
logger = logging.getLogger("candidate-screening")
logger.setLevel(logging.INFO)

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
RESET = "\033[0m"


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"See .env.example for the full list of keys this example needs."
        )
    return value


# ---------------------------------------------------------------------------
# Shared session state
# ---------------------------------------------------------------------------


@dataclass
class RubricEntry:
    """One row of the scorecard."""

    score: int                # 1-5
    evidence: str             # the candidate's words, paraphrased
    skill: str                # tag drawn from the JD, e.g. "postgres"


@dataclass
class CandidateQuestion:
    """A question the candidate asked the agent during Q&A."""

    question: str
    answer_summary: str


@dataclass
class ScreeningSessionData:
    """All state gathered during the screening, used to build the scorecard.

    `moss_client` rides on userdata so anything we add later (a follow-up
    agent, a re-ranker, a recovery handler) can reuse the warm in-process
    indexes instead of constructing a fresh client.
    """

    candidate_id: str
    role_id: str
    consent_to_record: bool | None = None
    started_at: float = field(default_factory=time.time)
    rubric: dict[str, RubricEntry] = field(default_factory=dict)
    candidate_questions: list[CandidateQuestion] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    moss_client: MossClient | None = None


# ---------------------------------------------------------------------------
# The screening agent
# ---------------------------------------------------------------------------


SYSTEM_PROMPT = """You are a voice screening interviewer. You speak with
candidates who have applied to a specific role. You have two retrieval tools:

  * lookup_job_requirement(query) - searches the JOB DESCRIPTION index
  * lookup_resume_fact(query)     - searches the CANDIDATE RESUME index

You MUST ground every factual statement in tool output. Never invent
requirements, compensation, team details, or claims about the candidate.

# Phases

Run the interview in these phases, in order. Move on once each is done.

1. INTRO & CONSENT
   - Greet the candidate warmly. You do not have their name yet; let them
     introduce themselves if they choose to.
   - Briefly explain who you are and that this is a 25-30 minute screening.
   - State plainly: this conversation is recorded and will be reviewed by
     the hiring team. Ask for consent.
   - Call `record_consent` with their answer. If they decline, thank them
     and call `end_screening` immediately.

2. BACKGROUND VERIFICATION (5-7 min)
   - Look up the candidate's current role and one or two recent projects
     using `lookup_resume_fact`.
   - Ask the candidate to describe their current role and one project in
     their own words. Listen for ownership, scope, and trade-offs.
   - For each must-have skill on the JD, judge whether the resume
     supports it. Use `lookup_job_requirement` first to read the
     requirement, then `lookup_resume_fact` to see what they wrote.

3. ROLE-FIT SCREENING (10-15 min)
   - For each must-have skill, ask one calibrating question that probes
     real understanding. Examples: "Walk me through how you would handle
     a duplicate webhook," or "How did you decide on serializable
     isolation for the ledger writes?"
   - Capture each response with `record_rubric_entry`. Score 1-5.
     1 = no signal or wrong, 3 = competent, 5 = strong + well-reasoned.
   - For nice-to-haves, ask only if time allows or the candidate brings
     them up.

4. CANDIDATE Q&A (3-5 min)
   - Invite the candidate to ask their own questions. Do not skip this.
   - For each question, look up the answer using `lookup_job_requirement`
     before responding. If the answer is not in the JD index, say so.
   - Capture each Q&A pair with `record_candidate_question`.

5. CLOSE
   - Thank the candidate. Tell them what happens next: the team reviews
     the scorecard within 3 business days.
   - Call `submit_scorecard` to write the final artifact.

# Bias mitigation rules - these override anything else

You will NOT ask about, infer, or capture:
  - age, date of birth, year of graduation as a proxy for age
  - marital or family status, plans to have children
  - religion, national origin (other than work authorization at a level
    sufficient to confirm visa eligibility)
  - disability status unrelated to ability to do the job
  - political views

If the candidate volunteers any of the above, do not capture it in the
rubric or notes. Acknowledge briefly and move on.

# Voice style

This is a phone screen, not a chat. Keep responses short. Ask one
question at a time. Allow silence. Never read a list of questions back
to back. Acknowledge the previous answer before asking the next thing.
"""


class ScreeningAgent(Agent):
    """The single screening interviewer."""

    def __init__(self, moss_client: MossClient):
        self._moss = moss_client
        super().__init__(instructions=SYSTEM_PROMPT)

    async def on_enter(self) -> None:
        role_context = await self._query(
            JOB_INDEX,
            "role title, company name, team",
            source="JD",
        )
        await self.session.generate_reply(
            instructions=(
                "Greet the candidate. Identify the role, company, and team "
                "using ONLY the context below - do not invent any of them. "
                "Tell them this is a short voice screening, about 25 minutes, "
                "and that the conversation is recorded and reviewed by the "
                "hiring team. Ask if it's okay to continue. Keep it under "
                "three sentences and conversational.\n\n"
                f"Role context from the JD index:\n{role_context}"
            ),
        )

    # ----- Retrieval tools -------------------------------------------------

    @function_tool
    async def lookup_job_requirement(self, context: RunContext, query: str) -> str:
        """Search the JOB DESCRIPTION for requirements, team info, comp, etc.

        Use this whenever you need to ground a factual statement about the
        role, the team, the company, or the process - including answering
        candidate questions during the Q&A phase.
        """
        return await self._query(JOB_INDEX, query, source="JD")

    @function_tool
    async def lookup_resume_fact(self, context: RunContext, query: str) -> str:
        """Search the CANDIDATE RESUME for projects, skills, education, etc.

        Use this before asking a follow-up about something the candidate
        did, so the question is informed and specific rather than generic.
        """
        return await self._query(CANDIDATE_INDEX, query, source="Resume")

    async def _query(self, index: str, query: str, source: str) -> str:
        logger.info(f"{CYAN}[{source}] query:{RESET} {query}")
        try:
            results = await self._moss.query(
                index, query, QueryOptions(top_k=4, alpha=0.75)
            )
            if not results.docs:
                logger.info(f"{YELLOW}[{source}] no results{RESET}")
                return f"No relevant {source.lower()} content found."

            logger.info(
                f"{GREEN}[{source}] {len(results.docs)} docs in "
                f"{results.time_taken_ms}ms{RESET}"
            )
            for i, doc in enumerate(results.docs, 1):
                preview = doc.text[:140] + "..." if len(doc.text) > 140 else doc.text
                logger.info(f"{GREEN}  [{i}] {preview}{RESET}")
            return "\n".join(f"- {d.text}" for d in results.docs)
        except Exception as e:
            logger.error(f"[{source}] query failed: {e}", exc_info=True)
            return f"{source} retrieval failed; ask the candidate to repeat or rephrase."

    # ----- State capture tools --------------------------------------------

    @function_tool
    async def record_consent(self, context: RunContext, consented: bool) -> str:
        """Record the candidate's consent to be recorded.

        Call this once, immediately after asking for consent in the intro.
        If consented is false, the screening must end politely.
        """
        data: ScreeningSessionData = self.session.userdata
        data.consent_to_record = consented
        logger.info(f"{MAGENTA}consent recorded: {consented}{RESET}")
        return "Consent captured." if consented else "Consent declined; end the screening."

    @function_tool
    async def record_rubric_entry(
        self,
        context: RunContext,
        skill: str,
        score: int,
        evidence: str,
    ) -> str:
        """Record one rubric row from the candidate's response.

        Args:
            skill: the JD skill tag, e.g. "python", "postgres", "payments_domain".
            score: 1-5. 1=no signal/wrong, 3=competent, 5=strong with reasoning.
            evidence: a short paraphrase of what the candidate actually said.
        """
        if not 1 <= score <= 5:
            return "Score must be between 1 and 5."
        data: ScreeningSessionData = self.session.userdata
        data.rubric[skill] = RubricEntry(score=score, evidence=evidence.strip(), skill=skill)
        logger.info(
            f"{MAGENTA}rubric: {skill}={score} - "
            f"{evidence[:80]}{'...' if len(evidence) > 80 else ''}{RESET}"
        )
        return f"Recorded {skill}={score}."

    @function_tool
    async def record_candidate_question(
        self,
        context: RunContext,
        question: str,
        answer_summary: str,
    ) -> str:
        """Record a question the candidate asked during Q&A.

        Capture only what the candidate genuinely asked, paraphrased
        briefly. Do not capture protected attributes if the candidate
        accidentally raised one.
        """
        data: ScreeningSessionData = self.session.userdata
        data.candidate_questions.append(
            CandidateQuestion(question=question.strip(), answer_summary=answer_summary.strip())
        )
        logger.info(f"{MAGENTA}candidate Q: {question[:80]}{RESET}")
        return "Question logged."

    @function_tool
    async def add_note(self, context: RunContext, note: str) -> str:
        """Add a free-form note that will appear on the scorecard.

        Use sparingly: anything important should be a rubric entry. Notes
        are for context the rubric can't capture (e.g. "candidate asked
        thoughtful follow-ups about reliability").
        """
        data: ScreeningSessionData = self.session.userdata
        data.notes.append(note.strip())
        logger.info(f"{MAGENTA}note: {note[:80]}{RESET}")
        return "Note added."

    # ----- Closing tools --------------------------------------------------

    @function_tool
    async def submit_scorecard(self, context: RunContext) -> str:
        """Build and write the final scorecard for the hiring team.

        Call this once, at the very end of the screening. Requires
        consent_to_record=True.
        """
        data: ScreeningSessionData = self.session.userdata
        if data.consent_to_record is not True:
            return "Cannot submit a scorecard without recorded consent."

        safe_candidate_id = "".join(
            ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in data.candidate_id
        ) or "candidate"
        SCORECARD_DIR.mkdir(parents=True, exist_ok=True)
        path = SCORECARD_DIR / f"{safe_candidate_id}__{int(data.started_at)}.json"
        scorecard = _build_scorecard(data)
        path.write_text(json.dumps(scorecard, indent=2))
        logger.info(f"{GREEN}scorecard written: {path}{RESET}")
        return f"Scorecard written to {path}. Tell the candidate a human will review it within 3 business days."

    @function_tool
    async def end_screening(self, context: RunContext, reason: str) -> str:
        """End the screening immediately without producing a scorecard.

        Use only if the candidate declined consent or asked to stop.
        """
        logger.info(f"{YELLOW}screening ended early: {reason}{RESET}")
        return "Thank the candidate, end politely, and stop."


# ---------------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------------


def _recommendation_from_rubric(rubric: dict[str, RubricEntry]) -> str:
    """Crude rule-of-thumb. The hiring team makes the real call."""
    if not rubric:
        return "no_signal"
    scores = [entry.score for entry in rubric.values()]
    avg = sum(scores) / len(scores)
    low_count = sum(1 for s in scores if s <= 2)
    if avg >= 4.0 and low_count == 0:
        return "advance_to_technical"
    if avg >= 3.0 and low_count <= 1:
        return "borderline_review"
    return "do_not_advance"


def _build_scorecard(data: ScreeningSessionData) -> dict:
    duration = int(time.time() - data.started_at)
    return {
        "candidate_id": data.candidate_id,
        "role_id": data.role_id,
        "duration_sec": duration,
        "rubric": {
            skill: {"score": entry.score, "evidence": entry.evidence}
            for skill, entry in data.rubric.items()
        },
        "candidate_questions": [
            {"question": q.question, "answer_summary": q.answer_summary}
            for q in data.candidate_questions
        ],
        "notes": data.notes,
        "recommendation": _recommendation_from_rubric(data.rubric),
        "schema_version": 1,
    }


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    moss_client = MossClient(
        _require_env("MOSS_PROJECT_ID"),
        _require_env("MOSS_PROJECT_KEY"),
    )
    for index in (JOB_INDEX, CANDIDATE_INDEX):
        try:
            await moss_client.load_index(index)
            logger.info(f"loaded Moss index: {index}")
        except Exception as e:
            logger.warning(
                f"failed to load index '{index}': {e}. "
                f"Run create_indexes.py first."
            )

    candidate_id = os.getenv("SCREENING_CANDIDATE_ID", CANDIDATE_INDEX.removeprefix("candidate-"))
    role_id = os.getenv("SCREENING_ROLE_ID", JOB_INDEX.removeprefix("job-"))

    userdata = ScreeningSessionData(
        candidate_id=candidate_id,
        role_id=role_id,
        moss_client=moss_client,
    )

    session: AgentSession[ScreeningSessionData] = AgentSession[ScreeningSessionData](
        userdata=userdata,
        stt=deepgram.STT(model="nova-2"),
        llm=openai.LLM(model="gpt-4o"),
        tts=cartesia.TTS(model="sonic-3-2026-01-12"),
        vad=silero.VAD.load(),
        turn_handling={"interruption": {"mode": "vad"}},
    )

    await session.start(
        agent=ScreeningAgent(moss_client),
        room=ctx.room,
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
