# Walkthrough: the CLI tape (why the next agent does better)

The walkthrough media on `/rfc/demo/` is the recorded SDK CLI run, recut as
the same four beats as the page:

- `okf-bqaa-cli.mp4` (H.264 1280×720, ~25s, agg + ffmpeg; embedded first on the page)
- `okf-bqaa-cli-poster.png` (last frame: lookup JSON + the payoff comment)
- `cli/okf-bqaa-cli.cast` (asciinema v2, same commands)
- `cli/okf-bqaa-cli.gif` (agg render of the cast)
- `cli/okf-bqaa-cli-transcript.txt` (plaintext, the durable proof)

Recorded 2026-09-02 PT from a checkout of
`GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK` PR 474 at HEAD
`476d37dc9d4210a335c2f77e78003f6a5ebe2878`, `examples/okf_bqaa_adapter`.
Stdlib only, no GCP, nothing re-run: the CLI reads the committed export of
observe session `f21ee192-d989-4c38-894f-66b6b82eaf18` (180 rows,
`okf_rfc_observe_agent`, `gemini-3.8-flash`). Label throughout: derived / demo,
observer-only, nothing attested. Do not merge PR 474.

`okf-bqaa-e2e.mp4` is a **prior fixture clip**, recorded before the observe run
and before the CLI path existed. It stays on the page only inside a collapsed
section labelled "prior fixture clip, not this run".

## One sentence per beat (the captions on the page)

1. The agent is asked for Germany last-quarter revenue — and whether the number can be trusted.
2. The live trace ranked Active-customer revenue first and excluded the superseded legacy metric; the receipt is unproven.
3. One command turns that telemetry into derived OKF, the handle a Catalog entry would expose.
4. The next agent looks up that handle, uses the current metric, skips legacy, and reports the number as unproven.

## What the tape shows

### 1 · ASK

On-screen comment: a finance agent is asked for Germany last-quarter revenue
and whether to trust it; the trap is that `Customer revenue (legacy)` is
still on the shelf, superseded. Then a one-liner reads the question off the
committed export:

```
What was active-customer revenue in Germany last quarter — and can I trust the number?
```

On the page: beat 1, the question as recorded, the "What this demo is asking"
block, the two traps, the current metric. Say the answer out loud: this is the
third option. Context the first agent earned the hard way was observed by
BQAA and projected into derived OKF so the next agent can discover it. It is
not human-in-the-loop or customer-sentiment promotion, it is not trusting BQAA
as truth (observer-only, not the authored bundle, not a truth score), and
trust here means process integrity of what was observed. The number is still
unproven.

### 2 · OBSERVE

`python3 examples/okf_bqaa_adapter/_why_observe.py` prints what the trace saw,
not 180 rows:

```
180 events · okf_rfc_observe_agent
session f21ee192-d989-4c38-894f-66b6b82eaf18
rank 1: Active-customer revenue
excluded: Customer revenue (legacy) | superseded; out of force since 2026-06-20
receipt: UNVERIFIABLE · nothing attested
```

On the page: beat 2, the ranked titles, the exclusion, the receipt; the tape
pane says the same.

### 3 · PUBLISH

`python3 examples/okf_bqaa_adapter/run.py`, then `SESSION` / `CONTEXT_REF` /
`PUBLICATION_ID` / `FILES 8`, then the stub titles:

```
title: Active-customer revenue by region and quarter
title: Active customer
title: Active-customer revenue
title: Customer revenue (legacy)
title: Revenue recognition eligibility
title: Billing invoice lines
title: CRM customers
```

On-screen comment: 8 derived stubs with their own identity chain; this is the
handle a Knowledge Catalog entry would expose; this CLI path did not write
Catalog. On the page: beat 3, the handle card and the 8 stubs, legacy marked
deprecated.

### 4 · NEXT AGENT (poster frame)

`run.py --lookup 'okf:env-observe#674153c572f6'` → three-key JSON
(`context_ref`, `publication_id` `sha256:53bd1651…`, `label: derived/demo`),
then the comment **Payoff: use Active-customer revenue, not legacy; the number
is unproven.**

A brief junk-ref `run.py --lookup 'okf:env-junk#deadbeef'` → `FAIL_CLOSED`,
labelled `expected FAIL_CLOSED exit 2 — not a crashed demo`, then the lookup
and the payoff comment are held as the last frames, so the poster is the
payoff, not FAIL_CLOSED and not an empty header. On the page: beat 4.

## Beats on the page, if presenting live

1. **Ask.** Read the hero question and the three-sentence payoff aloud, then
   the ask callout under the badges. Beat 1: the question as recorded, the
   three-way answer (hard path → derived OKF; not HITL / sentiment; not BQAA
   as truth), the dead metric, the over-claim, the current metric. Expand the collapsed prior consume experiment and Germany sections
   only to show that they are labelled.
2. **Observe.** Beat 2: rank 1 `Active-customer revenue`, `Customer revenue
   (legacy)` excluded with its reason, receipt UNVERIFIABLE. The tape pane
   agrees, all ✓. The six sample rows and the never-emit scan are collapsed.
3. **Publish.** Beat 3: the handle card (`context_ref` → publication, no
   Catalog write on this path), the 8 stubs with titles, the tape. Identity
   chain and projection shape are collapsed.
4. **Next agent.** Beat 4: the lookup tape ending on the payoff; “what the next
   agent does” (use / skip / unproven); the junk-ref tape labelled expected;
   type any other ref into "try a ref" and see it fail closed against the
   committed `mapping.json`.
5. **How this was built / IDs** at the bottom: agent, session, table, SHA
   triple, `context_ref`, SDK PR 474, the 180-event histogram, the
   `Object.hasOwn` note. This is where a reviewer verifies the run.

## Before presenting

- `python3 rfc/demo/tools/check_cli_viewer.py` exits 0.
- Serve from the repo root: `python3 -m http.server 8000`, open
  `http://localhost:8000/rfc/demo/`; no console errors on any beat.
- Do not re-record. Do not run `--live`. Do not pad events.
