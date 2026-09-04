# Spec — VP punchline strip v4 (customer story + value)

## Goal
Rewrite the strip so a VP of BQ gets **customer story → value we add** first. Mechanism (SQL, Graph, IAM details) is supporting evidence, not the lead.

## Required narrative (order fixed)

1. **Headline (value):** BigQuery is the runtime of Knowledge Catalog + OKF — so agents answer Germany revenue from pinned, governed context instead of a Catalog shelf alone.
2. **Customer story (the moment):** Leadership asks: what was active-customer revenue in Germany, and can I trust it?
   - Catalog-only path (`04fa3d56`): agent said **“verified”** from `ok: true` — **no computation ran**.
   - BigQuery runtime path (`f21ee192`): agent said **“No. The number is unproven.”** (12/12) with `verdict: UNVERIFIABLE`.
3. **Value we add (3 short bullets max):**
   - **Trust you can defend** — a verdict (or honest unproven), not a word from lookup.
   - **One answer, not EntryGroup roulette** — deterministic pin of OKF-in-KC to a publication / receipt.
   - **IAM you can explain** — deployment-scoped grants vs cascading EntryGroup read of the whole policy body (label Phase A / RFC where not live).
4. **Optional one-liner (not a card):** BigQuery Graph can walk the OKF chain (observation → snapshot → publication) the easy way — honesty: relational evidence on this page today; Graph optional per RFC.

## UI
- Lead with story + value; demote API jargon (`LookupContext`, `FAIL_STALE`, table names) into beat citations under the cards.
- Keep honesty labels. Checker exit 0. No invented Graph job / Phase A completion / ATTESTED.

## Out of scope
Scanner hardening. New captures.
