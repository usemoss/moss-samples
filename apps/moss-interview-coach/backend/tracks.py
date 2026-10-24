"""Interview tracks: prompts, Moss index names, and knowledge sources.

Single source of truth for backend ingest + server (+ grader persona).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"

# Each track has its own Moss index so retrieval/grading stay on-topic.
INTERVIEW_TRACKS: dict[str, dict[str, Any]] = {
    "system-design": {
        "label": "System Design",
        "blurb": "Distributed systems, APIs, scale, and reliability.",
        "fallback_tips": [
            "State assumptions out loud before diving into components.",
            "Compare at least two design alternatives with trade-offs.",
            "Call out bottlenecks and how you would scale them.",
        ],
        "index_name": "system-design-rubric",
        "knowledge_file": str(KNOWLEDGE_DIR / "system_design_rubrics.json"),
        "sample_query": "How would you design rate limiting for a public API?",
        "grader_persona": "strict system design interview grader",
        "focus": (
            "You are an expert System Design Interview Coach. "
            "Stay focused on distributed systems, APIs, scalability, reliability, and storage. "
            "Common deep-dives include WhatsApp, rate limiting, sharding, CDNs, and the CAP theorem."
        ),
        "welcome": (
            "Welcome to your system design interview. "
            "What would you like to design first—WhatsApp, rate limiting, sharding, CDNs, "
            "or the CAP theorem?"
        ),
    },
    "agent-native-infrastructure": {
        "label": "Agent-Native Infrastructure",
        "blurb": "Agent runtimes, tools, memory, orchestration, and evals.",
        "fallback_tips": [
            "Say which agent boundary you are designing: runtime, tools, or memory.",
            "Explain how the agent recovers when a tool call fails or times out.",
            "Describe how you would evaluate the change, not just ship it.",
        ],
        "index_name": "agent-native-infrastructure-rubric",
        "knowledge_file": str(KNOWLEDGE_DIR / "agent_native_rubrics.json"),
        "sample_query": "How would you design tool calling and memory for a production agent?",
        "grader_persona": "strict agent-native infrastructure interview grader",
        "focus": (
            "You are an expert Agent-Native Infrastructure Interview Coach. "
            "Stay focused on agent runtimes, tool calling, memory, orchestration, evals, "
            "and production reliability for AI agents."
        ),
        "welcome": (
            "Welcome to your agent-native infrastructure interview. "
            "Where should we start—agent runtimes, tool calling, memory, orchestration, or evals?"
        ),
    },
    "machine-learning-concepts": {
        "label": "Machine Learning Concepts",
        "blurb": "ML fundamentals, evaluation, training, and model systems.",
        "fallback_tips": [
            "Name the metric you are optimizing and why it fits the problem.",
            "Separate training-time choices from inference-time constraints.",
            "Say how you would detect the model degrading in production.",
        ],
        "index_name": "machine-learning-concepts-rubric",
        "knowledge_file": str(KNOWLEDGE_DIR / "ml_concepts_rubrics.json"),
        "sample_query": "How do you choose evaluation metrics for a classification model?",
        "grader_persona": "strict machine learning concepts interview grader",
        "focus": (
            "You are an expert Machine Learning Concepts Interview Coach. "
            "Stay focused on ML fundamentals, training vs inference, evaluation, "
            "feature pipelines, and model systems trade-offs."
        ),
        "welcome": (
            "Welcome to your machine learning concepts interview. "
            "Where should we begin—supervised learning basics, evaluation metrics, "
            "training versus inference, or feature pipelines?"
        ),
    },
}

DEFAULT_TRACK_ID = "system-design"


def _canonical_track_key(raw: str | None) -> str | None:
    if raw is None:
        return None
    key = raw.strip().lower().replace("_", "-")
    return key or None


def normalize_track_id(raw: str | None) -> str:
    """Lenient normalization: missing/empty/unknown → default track."""
    key = _canonical_track_key(raw)
    if key is None or key not in INTERVIEW_TRACKS:
        return DEFAULT_TRACK_ID
    return key


def resolve_track_id_for_offer(raw: str | None) -> str:
    """Strict resolution for /api/offer: missing/empty → default; unknown → error."""
    key = _canonical_track_key(raw)
    if key is None:
        return DEFAULT_TRACK_ID
    if key not in INTERVIEW_TRACKS:
        raise ValueError(f"Unknown interview track: {key}")
    return key


def track_index_name(track_id: str) -> str:
    return INTERVIEW_TRACKS[normalize_track_id(track_id)]["index_name"]


def all_index_names() -> list[str]:
    return [meta["index_name"] for meta in INTERVIEW_TRACKS.values()]
