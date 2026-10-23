# Demo Script — Metadata Filtering (region-scoped answers)

~90s. Shows the **same question** returning **different, correct answers** by region,
because Moss filters retrieval on `metadata.region` — one shared index, scoped per line.

## Before you record
- [ ] **Re-seed** (metadata changed): delete the old `demo-customer_faqs` index in the Moss
      portal, then `python seed_index.py`.
- [ ] `python agent.py dev` · `livekit-server --dev` · web UI at localhost:3000
- [ ] Region is chosen with the **US / EU picker** in the panel (starts on US) — no restart.

## 1 · Frame it (0:00–0:12)
> "Same knowledge base, one index. This support panel has a region picker — right now it's
> set to the US, and Moss only retrieves policies that apply to that region. Watch."

**[Connect. Panel shows the picker on US and `filter · region ∈ [US, all]`.]**

## 2 · US answer (0:12–0:35)
> "What's your return window?"

**[Point at panel: the filter line + the retrieved US chunk.]**
> "Thirty days. The panel shows the filter — region is US or global — and it pulled the
> US returns policy. The EU policy is in the same index, but it was filtered out."

## 3 · Switch region (0:35–1:05)
**[Click EU in the picker — the filter line flips to `region ∈ [EU, all]` instantly.]**
> "Now I switch the same agent to the EU — no restart, just the filter. Same question."

> "What's your return window?"

> "Fourteen days — the EU right of withdrawal. Same index, same question, different answer,
> because the metadata filter scoped retrieval to the right region."

## 4 · Why it matters (1:05–1:25)
> "That's one line of filter in the query. It's how you serve region-specific policies,
> or isolate tenants, or gate content by plan — all from a single Moss index, evaluated
> locally in milliseconds. Open source at github.com/usemoss/moss."

---

## The filter (for reference)
```python
QueryOptions(top_k=5, alpha=0.8,
    filter={"field": "region", "condition": {"$in": ["EU", "all"]}})
```

## Try these too
- "How much is shipping?" → US quotes dollars, EU quotes euros (with VAT).
- A global question ("I forgot my password") → same answer in both regions (region = `all`).
