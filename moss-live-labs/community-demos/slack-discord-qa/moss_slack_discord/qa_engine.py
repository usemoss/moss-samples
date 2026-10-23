"""Shared retrieval and answer-generation logic for both chat adapters."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


NO_RESULTS_MESSAGE = (
    "I couldn't find anything relevant in the workspace knowledge base."
)


@dataclass(frozen=True)
class RetrievedDocument:
    """The small part of a Moss result needed by the answer engine."""

    text: str
    score: float | None = None


class Retriever(Protocol):
    async def retrieve(
        self, question: str, top_k: int
    ) -> Sequence[RetrievedDocument]: ...


class Responder(Protocol):
    async def respond(self, question: str, context: str) -> str: ...


def build_context(
    documents: Sequence[RetrievedDocument], max_chars: int = 12_000
) -> str:
    """Format retrieved documents into a bounded context for the LLM."""
    sections: list[str] = []
    remaining = max_chars

    for index, document in enumerate(documents, start=1):
        text = document.text.strip()
        if not text or remaining <= 0:
            continue

        score = f" (score: {document.score:.3f})" if document.score is not None else ""
        section = f"[{index}]{score}\n{text}"
        section = section[:remaining]
        sections.append(section)
        remaining -= len(section) + 2

    return "\n\n".join(sections)


@dataclass
class AnswerEngine:
    """Answer questions using retrieved Moss documents as the source of truth."""

    retriever: Retriever
    responder: Responder
    top_k: int = 5

    async def answer(self, question: str) -> str:
        question = question.strip()
        if not question:
            return "Please include a question after mentioning me."

        documents = await self.retriever.retrieve(question, self.top_k)
        context = build_context(documents)
        if not context:
            return NO_RESULTS_MESSAGE

        answer = (await self.responder.respond(question, context)).strip()
        return (
            answer or "I couldn't generate an answer from the workspace knowledge base."
        )
