"""
Mortgage Lending Voice Agent (multi-agent, with handoff)
========================================================

Two agents share one LiveKit session:

  1. MortgageRetrievalAgent
     - Answers retrieval-heavy mortgage questions (down payment, credit score,
       loan types, DTI, PMI, closing costs, documents needed, ...).
     - Grounded in a Moss index that lives in-process for sub-10ms search.
     - Hands off to PaymentFlowAgent when the customer is ready to pay.

  2. PaymentFlowAgent
     - Walks the customer through a structured payment flow (confirm loan,
       collect amount, choose method, confirm).
     - Reads/writes `MortgageSessionData` (shared via session.userdata) so
       facts the retrieval agent already gathered (loan number, last 4 of
       SSN, etc.) are not asked again.

The handoff is a single line: a function_tool returns the next Agent.
LiveKit preserves chat history so the conversation feels continuous.
"""

import logging
import os
from dataclasses import dataclass, field

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

INDEX_NAME = os.getenv("MOSS_INDEX_NAME", "mortgage-lending-kb")


def _require_env(name: str) -> str:
    """Read a required env var or fail fast with a friendly message.

    Module-level usage of ``os.getenv`` returns ``Optional[str]``; passing
    ``None`` into ``MossClient(...)`` later would surface as an opaque
    error from inside the SDK. Validate at the call site instead.
    """
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"See .env.example for the full list of keys this agent needs."
        )
    return value

logging.getLogger("livekit").setLevel(logging.WARNING)
logging.getLogger("livekit.agents").setLevel(logging.WARNING)
logger = logging.getLogger("moss-mortgage")
logger.setLevel(logging.INFO)

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"


# ---------------------------------------------------------------------------
# Shared session state (passed between agents via session.userdata)
# ---------------------------------------------------------------------------


@dataclass
class MortgageSessionData:
    """Facts gathered during the call, shared across agent handoffs.

    `moss_client` carries the already-loaded MossClient so handoffs can
    reuse the warm in-process index instead of constructing a fresh client
    (which would silently fall back to the slow cloud query API).
    """

    loan_number: str | None = None
    customer_name: str | None = None
    last_four_ssn: str | None = None
    payment_amount: float | None = None
    payment_method: str | None = None
    questions_answered: list[str] = field(default_factory=list)
    moss_client: MossClient | None = None


# ---------------------------------------------------------------------------
# Agent 1: retrieval-heavy mortgage Q&A, backed by Moss
# ---------------------------------------------------------------------------


class MortgageRetrievalAgent(Agent):
    """Answers mortgage questions from a Moss-backed knowledge base."""

    def __init__(self, moss_client: MossClient):
        self._moss = moss_client

        super().__init__(
            instructions="""
                You are Moss, a friendly mortgage lending voice assistant.

                Phase 1 of the call is information gathering. Customers will ask
                detailed mortgage questions: down payment requirements, credit
                score thresholds, loan types (conventional, FHA, VA, jumbo),
                debt-to-income ratios, PMI rules, closing costs, required
                documents, pre-approval vs pre-qualification.

                Rules:
                - ALWAYS call `search_mortgage_kb` before answering a factual
                  question. Never invent figures.
                - Keep answers short and conversational. This is voice — no
                  bullet points, no markdown.
                - When the customer signals they want to make a payment
                  ("I'd like to pay", "make my payment", "schedule a payment",
                  "pay my bill"), call `transfer_to_payment_flow`. Do not try
                  to handle payment yourself.
                - Capture the customer's loan number if they give it; pass it
                  to the payment flow.
            """,
        )

    async def on_enter(self) -> None:
        await self.session.say(
            "Hi, this is Moss from mortgage services. I can help with questions "
            "about your loan, payment options, or rates. What can I help you with?"
        )

    @function_tool
    async def search_mortgage_kb(self, context: RunContext, question: str) -> str:
        """Search the mortgage lending knowledge base.

        Use this for ANY factual question about loan products, rates, eligibility,
        documentation, closing process, payment options, escrow, or fees.

        Args:
            question: The customer's question, rephrased as a search query.
        """
        logger.info(f"{CYAN}Moss query:{RESET} {question}")
        try:
            results = await self._moss.query(
                INDEX_NAME,
                question,
                QueryOptions(top_k=4, alpha=0.75),
            )
            if not results.docs:
                return "No relevant information found. Tell the customer you'll need a specialist to follow up."

            logger.info(
                f"{GREEN}Moss returned {len(results.docs)} docs in "
                f"{results.time_taken_ms}ms{RESET}"
            )
            for i, doc in enumerate(results.docs, 1):
                preview = doc.text[:140] + "..." if len(doc.text) > 140 else doc.text
                logger.info(f"{GREEN}  [{i}] {preview}{RESET}")

            # Track what's been asked so the payment agent can skip re-asking
            data: MortgageSessionData = self.session.userdata
            data.questions_answered.append(question)

            return "\n".join(f"- {d.text}" for d in results.docs)
        except Exception as e:
            logger.error(f"Moss search failed: {e}", exc_info=True)
            return "Knowledge base search failed. Ask the customer to rephrase."

    @function_tool
    async def capture_loan_number(self, context: RunContext, loan_number: str) -> str:
        """Save the customer's loan number to session state.

        Call this whenever the customer provides their loan or account number
        so it can be reused if they switch to the payment flow.
        """
        data: MortgageSessionData = self.session.userdata
        data.loan_number = loan_number.strip()
        logger.info(f"{YELLOW}Captured loan number: {data.loan_number}{RESET}")
        return f"Saved loan number {data.loan_number}."

    @function_tool
    async def transfer_to_payment_flow(self, context: RunContext) -> tuple[Agent, str]:
        """Hand the conversation off to the payment flow agent.

        Call this when the customer asks to make a payment, schedule a payment,
        or pay their bill. The next agent inherits all session state.
        """
        logger.info(f"{YELLOW}Handoff -> PaymentFlowAgent{RESET}")
        data: MortgageSessionData = self.session.userdata
        greeting = (
            "Got it, let me hand you over to our payment flow."
            if not data.loan_number
            else "Got it. I have your loan number on file — connecting you to payments now."
        )
        return PaymentFlowAgent(), greeting


# ---------------------------------------------------------------------------
# Agent 2: structured payment flow
# ---------------------------------------------------------------------------


class PaymentFlowAgent(Agent):
    """Collects payment details and confirms the transaction."""

    def __init__(self):
        super().__init__(
            instructions="""
                You are the payment flow agent for mortgage services.

                Phase 2 of the call: collect payment details and confirm.

                Steps, in order:
                  1. If a loan number was already captured (check via
                     `read_session_state`), confirm it back to the customer
                     instead of re-asking.
                  2. Ask for the last four digits of their SSN to verify
                     identity. Save with `verify_identity`.
                  3. Ask the payment amount. Save with `set_payment_amount`.
                  4. Ask the payment method (bank transfer, debit card, or
                     scheduled autopay). Save with `set_payment_method`.
                  5. Read back all four facts and ask for confirmation.
                  6. On confirmation, call `submit_payment`.

                Rules:
                - Be concise — voice interface, no markdown.
                - Never ask for full SSN, full account numbers, or card
                  numbers. Last 4 only.
                - If the customer asks a mortgage question that isn't about
                  payment, call `return_to_advisor` to hand back.
            """,
        )

    async def on_enter(self) -> None:
        data: MortgageSessionData = self.session.userdata
        if data.loan_number:
            await self.session.say(
                f"Hi, I'll get your payment set up. I have loan number "
                f"{data.loan_number} on file — is that the one you want to pay?"
            )
        else:
            await self.session.say(
                "Hi, I'll get your payment set up. What's your loan number?"
            )

    @function_tool
    async def read_session_state(self, context: RunContext) -> str:
        """Return what's already known about the customer this call.

        Call this at the start to avoid asking for facts the previous agent
        already collected.
        """
        data: MortgageSessionData = self.session.userdata
        known = {
            "loan_number": data.loan_number,
            "customer_name": data.customer_name,
            "last_four_ssn": data.last_four_ssn,
            "payment_amount": data.payment_amount,
            "payment_method": data.payment_method,
        }
        return ", ".join(f"{k}={v}" for k, v in known.items() if v) or "nothing on file yet"

    @function_tool
    async def verify_identity(self, context: RunContext, last_four_ssn: str) -> str:
        """Save the last four digits of the customer's SSN for verification."""
        digits = "".join(c for c in last_four_ssn if c.isdigit())
        if len(digits) != 4:
            return "Please ask the customer to repeat the last four digits clearly."
        data: MortgageSessionData = self.session.userdata
        data.last_four_ssn = digits
        logger.info(f"{YELLOW}Verified identity (last 4) captured.{RESET}")
        return "Identity captured."

    @function_tool
    async def set_payment_amount(self, context: RunContext, amount: float) -> str:
        """Record the payment amount in dollars."""
        if amount <= 0:
            return "Amount must be positive. Ask the customer to repeat."
        data: MortgageSessionData = self.session.userdata
        data.payment_amount = amount
        logger.info(f"{YELLOW}Payment amount: ${amount:,.2f}{RESET}")
        return f"Recorded ${amount:,.2f}."

    @function_tool
    async def set_payment_method(self, context: RunContext, method: str) -> str:
        """Record the payment method (e.g., bank transfer, debit card, autopay)."""
        method_norm = method.strip().lower()
        valid = {"bank transfer", "debit card", "autopay", "scheduled autopay"}
        if method_norm not in valid:
            return f"Method must be one of: {', '.join(sorted(valid))}."
        data: MortgageSessionData = self.session.userdata
        data.payment_method = method_norm
        logger.info(f"{YELLOW}Payment method: {method_norm}{RESET}")
        return f"Recorded {method_norm}."

    @function_tool
    async def submit_payment(self, context: RunContext) -> str:
        """Submit the payment after the customer confirms.

        Requires loan_number, last_four_ssn, payment_amount, and payment_method
        to all be set. In a real system this would call your billing API.
        """
        data: MortgageSessionData = self.session.userdata
        missing = [
            name
            for name, value in [
                ("loan number", data.loan_number),
                ("last four SSN", data.last_four_ssn),
                ("payment amount", data.payment_amount),
                ("payment method", data.payment_method),
            ]
            if not value
        ]
        if missing:
            return f"Cannot submit — missing: {', '.join(missing)}."

        logger.info(
            f"{GREEN}Payment submitted: loan={data.loan_number} "
            f"amount=${data.payment_amount:,.2f} method={data.payment_method}{RESET}"
        )
        # Replace this stub with your real payment processor call.
        confirmation = f"MOSS-{abs(hash(data.loan_number)) % 10_000_000:07d}"
        return (
            f"Payment of ${data.payment_amount:,.2f} submitted via "
            f"{data.payment_method}. Confirmation number {confirmation}."
        )

    @function_tool
    async def return_to_advisor(self, context: RunContext) -> tuple[Agent, str]:
        """Hand the conversation back to the retrieval agent.

        Use this if the customer asks something off-topic for payment
        (e.g., a new mortgage question).
        """
        logger.info(f"{YELLOW}Handoff -> MortgageRetrievalAgent{RESET}")
        data: MortgageSessionData = self.session.userdata
        # Reuse the already-loaded MossClient so retrieval stays in-process.
        # Constructing a fresh client here would silently fall back to the
        # cloud query API on every search.
        return MortgageRetrievalAgent(data.moss_client), "Sure, let me get you back to the advisor."


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    moss_client = MossClient(
        _require_env("MOSS_PROJECT_ID"),
        _require_env("MOSS_PROJECT_KEY"),
    )
    try:
        await moss_client.load_index(INDEX_NAME)
        logger.info(f"Loaded Moss index: {INDEX_NAME}")
    except Exception as e:
        logger.warning(
            f"Failed to load index '{INDEX_NAME}': {e}. "
            "Run create_index.py first."
        )

    session: AgentSession[MortgageSessionData] = AgentSession[MortgageSessionData](
        userdata=MortgageSessionData(moss_client=moss_client),
        stt=deepgram.STT(model="nova-2"),
        llm=openai.LLM(model="gpt-4o"),
        tts=cartesia.TTS(model="sonic-3-2026-01-12"),
        vad=silero.VAD.load(),
        turn_handling={"interruption": {"mode": "vad"}},
    )

    await session.start(
        agent=MortgageRetrievalAgent(moss_client),
        room=ctx.room,
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
