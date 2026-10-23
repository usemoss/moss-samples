from dataclasses import dataclass

import pytest

from moss_slack_discord.qa_engine import (
    AnswerEngine,
    NO_RESULTS_MESSAGE,
    RetrievedDocument,
    build_context,
)


@dataclass
class FakeRetriever:
    documents: list[RetrievedDocument]
    last_question: str | None = None
    last_top_k: int | None = None

    async def retrieve(self, question: str, top_k: int) -> list[RetrievedDocument]:
        self.last_question = question
        self.last_top_k = top_k
        return self.documents


@dataclass
class FakeResponder:
    answer: str = "The answer is in the workspace."
    last_question: str | None = None
    last_context: str | None = None

    async def respond(self, question: str, context: str) -> str:
        self.last_question = question
        self.last_context = context
        return self.answer


@pytest.mark.asyncio
async def test_answer_uses_retrieved_context() -> None:
    retriever = FakeRetriever(
        [RetrievedDocument("Refunds take five business days.", 0.92)]
    )
    responder = FakeResponder()
    engine = AnswerEngine(retriever, responder, top_k=3)

    answer = await engine.answer("  How long do refunds take? ")

    assert answer == "The answer is in the workspace."
    assert retriever.last_question == "How long do refunds take?"
    assert retriever.last_top_k == 3
    assert responder.last_question == "How long do refunds take?"
    assert (
        responder.last_context == "[1] (score: 0.920)\nRefunds take five business days."
    )


@pytest.mark.asyncio
async def test_answer_returns_fallback_without_documents() -> None:
    engine = AnswerEngine(FakeRetriever([]), FakeResponder())

    assert await engine.answer("Where is the policy?") == NO_RESULTS_MESSAGE


@pytest.mark.asyncio
async def test_answer_handles_empty_question() -> None:
    engine = AnswerEngine(FakeRetriever([]), FakeResponder())

    assert (
        await engine.answer("   ") == "Please include a question after mentioning me."
    )


def test_context_is_bounded() -> None:
    context = build_context([RetrievedDocument("abcdefghij")], max_chars=5)

    assert len(context) <= 5
    assert context.startswith("[1]")
