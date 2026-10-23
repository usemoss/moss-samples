# PartsLine — Voice Agent for Auto Parts Counters

## What it is
A browser-based voice agent that answers the highest-volume call an auto
parts counter gets: "do you have [part] for [vehicle]?" It searches a
parts catalog with vehicle details as metadata filters, checks stock,
quotes price, sets parts aside by name, and transfers anything complex
to a human — with the vehicle/part context already captured.

Built on Moss because the problem is retrieval-shaped: catalogs are too
large to prompt-stuff, one question triggers multiple lookups
(part → fitment → stock), and on a live call those lookups must resolve
mid-sentence (~5-15ms in-process vs ~200-600ms over a cloud DB round trip).

## Who it's for
Demo audience now (incl. as an open-source reference app); architecture
kept honest so a real shop's catalog/POS data could swap in later.

## Guardrails (the "trained new employee" rules)
- Exact-match-or-ask: never quote fitment on an ambiguous vehicle spec;
  ask the disambiguating question ("2.5 or 3.6?")
- Grounded-only: every fitment/price/stock claim comes from a retrieval
  result; no answers from LLM world-knowledge
- Hedged stock language ("we're showing 2 in stock")
- Immediate cheerful transfer for: modifications, interchange questions,
  returns/warranty, fleet/commercial pricing

## MVP scope
Caller: part lookup w/ disambiguation → price + stock quote →
set-aside by first name → or transfer-with-context.
Shop: minimal call-log screen (time, vehicle, part, outcome).

## Explicitly NOT building (v1)
Ordering/payments · order status · returns handling · multi-part calls ·
phone telephony (browser voice only) · callback-number capture ·
real catalog/POS integration · CRM/analytics · auth/multi-tenancy ·
public deployment (laptop-demoed)

## Data model
- PART (part_number, name, category, brand, description, price)
- VEHICLE (year, make, model, engine, trim?)
- FITMENT (part↔vehicle join + condition notes; THE core domain)
- STOCK (separate from PART by design — the future POS-sync seam)
- CALL_LOG (append-only: time, vehicle, parts, outcome, set-aside name)

Implementation note: FITMENT is flattened into one Moss document per
(part × vehicle) combination, with vehicle attributes (make/model/year/
engine) as string metadata fields on each document. Confirmed working
via live test (see Retrieval Findings below).

Synthetic catalog: 3-4 categories (belts, brakes, filters, batteries),
~200-500 parts, ~50-100 vehicles, deliberately messy fitment: dual-engine
vehicles, mid-year splits, superseded part numbers, universal-fit parts,
vehicles absent from catalog.

## Retrieval Findings (from live Moss test — moss-test/seed.py + query.py)

A 12-document trap-laden mini-catalog was pushed to a real Moss index
and queried live. Results, and what they mean for the build:

**CONFIRMED WORKING — dual-engine disambiguation.**
Unfiltered query ("serpentine belt" for 2014 Outback) returned BOTH the
2.5L and 3.6L belts with close scores (1.000 / 0.969) — this is the
visible-ambiguity signal the agent needs to trigger "2.5 or 3.6?".
Adding `engine=2.5` to the filter cleanly isolated the correct part.
→ Build implication: when a filtered-by-known-attributes query returns
  >1 result, the agent must ask a disambiguating question before
  answering. This is a hard rule, not a nicety.

**CRITICAL FINDING — semantic score is NOT a safe "we don't carry this"
signal.** An unfiltered query for "brake pads for a 2019 RAV4" (a vehicle
NOT in the catalog at all) returned Civic/Camry brake pads scoring
0.909-0.994 — indistinguishable from genuine matches. There is no score
threshold that separates a real match from a confidently-wrong one.
By contrast, the SAME query WITH a vehicle filter (`model=RAV4`)
correctly returned zero results.
→ Build implication (HARD REQUIREMENT): the agent must NEVER accept a
  fitment answer from an unfiltered/semantic-only query. Vehicle
  identity (make/model/year/engine) must always be applied as a metadata
  filter before a part is quoted to a caller. An empty filtered result
  is the ONLY trustworthy "we don't carry that" signal. This changes the
  guardrail from "prefer filtering" to "filtering is mandatory before
  any fitment claim."

**FINDING — discontinued parts can outrank their replacement.**
A discontinued part (A-100, 0 stock, superseded_by="A-100B") scored
HIGHER (0.994) than its current replacement (A-100B, 0.975) on a plain
semantic query. Text similarity has no concept of "this part is dead."
→ Build implication: retrieval logic must explicitly exclude or
  deprioritize documents where `superseded_by` is set or `stock="0"`,
  rather than trusting raw top-result ranking. Options to evaluate in
  build: (a) filter out `stock=0` at query time when alternatives exist,
  (b) always chase `superseded_by` chains before presenting a result,
  (c) surface both with the agent explicitly saying "that one's been
  replaced by X." Needs a decision during Phase 2 build, not left to
  the LLM's judgment.

**UNRESOLVED — production-date / mid-year-split filtering not actually
tested.** The test used discrete string tags (`prod_cutoff:
"before-2014-03"` / `"from-2014-03"`) rather than a real date value with
$lte/$gte comparison. Filtering on year=2014 alone correctly returned
BOTH pad versions (expected, since prod_cutoff wasn't filtered on) — but
this does NOT confirm whether Moss's `$lte`/`$gte` operators work
cleanly against real date metadata for mid-year splits.
→ Build implication: re-test with an actual date field before assuming
  this pattern works. If date-range filtering proves awkward, fallback
  is precomputing the split into a boolean/enum field like `prod_cutoff`
  (as tested) and having the agent ask "was this bought before or after
  March 2014?" — a viable path either way, but confirm which.

## Evaluation discipline
15-25 held-out caller scenarios written before build, kept OUT of the
repo (and away from coding agents) during development; run manually
against the finished agent; added to the repo as documented evals after
v1. MUST include explicit cases for: dual-engine disambiguation,
superseded-part handling, and an absent-vehicle call (RAV4-style) to
confirm the agent refuses to guess rather than offering a wrong part.

## Presentation
- Demo page: one "talk" button, live transcript, inline lookup-chips
  showing each retrieval as it fires (the proof layer)
- Call-log page: single newest-first list
- Open source (MIT), README-first, reproducible via seed script

## Stack
- Voice/transport: LiveKit Agents (Python) — browser WebRTC native;
  Moss's own reference integration path
- Retrieval: Moss — catalog index (semantic + $eq/$and metadata
  filters), retrieval exposed as LLM function tools; per-call session
  optional. Confirmed live: `create_index`, `load_index`, filtered and
  unfiltered `query` all work as documented against a real project.
- STT: Deepgram · LLM: GPT-4o (Groq as TTFT upgrade) · TTS: Cartesia
- Frontend: Next.js (demo page + /calls log route)
- DB: SQLite (CALL_LOG only); catalog source-of-truth = JSON in repo,
  seeded to Moss via script (see moss-test/seed.py as the working
  reference implementation)
- Deploy: none for v1 (local); later Vercel + LiveKit Cloud/Fly.io

## Architecture sketch
Browser (Next.js, LiveKit client)
  ⇄ LiveKit room ⇄ Agent worker (Python: Deepgram → GPT-4o ⇄ Moss
    function tools → Cartesia) → SQLite CALL_LOG → /calls page

Moss function-tool logic (per the findings above) MUST:
1. Always resolve vehicle identity (make/model/year/engine) before
   querying for a part — never answer from an unfiltered query.
2. If a filtered query returns >1 result, ask a disambiguating question
   instead of picking one.
3. If a filtered query returns 0 results, tell the caller "we don't
   carry a match for that vehicle" — do not fall back to unfiltered
   semantic search to find a "close enough" answer.
4. Exclude/deprioritize discontinued (`stock=0` or `superseded_by`-set)
   parts rather than trusting raw ranking; resolve to the current
   replacement when one exists.

## Security-sensitive areas
- All keys in .env (gitignored) + committed .env.example; clean from
  first commit (repo is public from day one)
- Spend caps + alerts on all provider accounts (Moss, LiveKit, Deepgram,
  OpenAI/Groq, Cartesia), day one
- Post-v1 public deploy adds: rate limiting on the agent endpoint,
  abuse pass (strangers can burn LLM/TTS credits via the talk button)

## Build sequencing (mock-first)
1. ~~Next.js page + fake transcript (clickable skeleton)~~
2. ~~Catalog seed script + Moss index + a CLI that answers text
   queries~~ — DONE: moss-test/seed.py + query.py, findings above
   incorporated. Re-test production-date filtering ($lte/$gte) before
   moving on if mid-year-split parts matter for the demo story.
3. LiveKit voice loop with a dumb echo agent (voice proven separately)
4. Wire 2+3: function tools enforcing the four hard rules above,
   disambiguation loop, superseded-part handling
5. Lookup-chips in transcript; CALL_LOG + /calls page LAST
6. Run held-out evals (incl. RAV4-style absent-vehicle case); fix;
   publish repo

## Open questions carried forward
1. Real-world validation: has anyone confirmed with an actual parts
   counter that this is the call volume/pain they'd want solved?
   (Deliberately parked, not resolved.)
2. STT disambiguation tolerance: how many "sorry, which one was that?"
   re-asks is acceptable before it feels broken? (Resolved as: graceful
   re-asking is acceptable, expected behavior — not a defect to eliminate.)
3. Production-date filtering: does Moss's $lte/$gte work cleanly on a
   real date field, or does the mid-year-split need to stay a
   precomputed boolean tag? RE-TEST BEFORE BUILDING THE FEATURE.
4. Superseded-part resolution strategy: pick (a), (b), or (c) from the
   Retrieval Findings section above during Phase 2 build — do not leave
   this to implicit LLM judgment, it's a guardrail decision.