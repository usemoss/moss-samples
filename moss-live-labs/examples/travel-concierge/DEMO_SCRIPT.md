# Demo Script — Travel Concierge (cloud catalog + live session)

~90s. Shows Moss answering from **two indexes in one call**: a pre-loaded catalog and a
live session that remembers trip preferences you mention. Watch both panels on the right.

## Before you record
- [ ] `uv run python agent.py download-files` (once) · `uv run python seed_index.py` · `uv run python agent.py dev` · `livekit-server --dev` · web at localhost:3000

## 1 · Frame it (0:00–0:12)
> "This concierge knows a catalog of trips — that's loaded ahead of time. But it also
> remembers the trip preferences I mention on the call. Two Moss indexes, live, side by side. Watch."

**[Click Start planning. The agent greets you.]**

## 2 · Tell it about the trip (0:12–0:40)
> "We're a family of four, our budget's around two thousand five hundred dollars a person,
> we love beaches, and we want to travel the first week of December."

**[Point at the "This call · live session" panel filling up as you talk.]**
> "Watch the live session. It's pulling the facts out of what I say — a family of four,
> the budget, the dates — and storing each one in an in-memory session."

## 3 · Recall (0:40–0:58)
> "Wait, what did I say my budget was?"

**[The session panel lights up; the agent answers from what you said.]**
> "It pulled that straight from this conversation — not the catalog. And notice the question
> itself doesn't get stored, only the facts do."

## 4 · Recommend (0:58–1:20)
> "So where should we go?"

**[Both panels light: catalog hits + your session prefs.]**
> "Now it's using both — my preferences from the session *and* the catalog it already had —
> to recommend somewhere that actually fits. Beach, family, December, in budget."

## 5 · Why it matters (1:20–1:35)
> "That's long-term knowledge and short-term memory in the same call — one pre-loaded index,
> one live session, both queried in milliseconds, on-device. Open source at
> github.com/usemoss/moss."

---

## Say-these preferences (each is distilled to a fact in the session)
- "Family of four, budget about $2,500 per person."
- "We love beaches and warm weather."
- "Traveling the first week of December."

> Only facts land in the session. Questions like "what did I say my budget was?" and
> "where should we go?" are recalled against, but never stored.

## Recall / recommend prompts
- "What did I say my budget was?" → session
- "Which destinations do you have?" → catalog
- "Where should we go?" → both (expect Tulum or Costa Rica for beach + family + Dec)
