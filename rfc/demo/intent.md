# Intent — why BQAA trace → derived OKF in Knowledge Catalog helps the next agent

Status: accepted from Haiyuan (2026-09-02 ~10:18 PM PT): rewrite
https://caohy1988.github.io/rfc/demo/ so a reader immediately gets **WHY**
this path helps an agent do better. The live page (PR 11 / `47575a4`) is too
technically feature-oriented (hashes, adapter version, 180 events,
fail-closed `Object.hasOwn`).

Locked scenario — do not invent a different story.

A finance agent is asked: **“What was active-customer revenue in Germany last
quarter — and can I trust the number?”**

Without this path the agent can (a) use **Customer revenue (legacy)**,
superseded, or (b) talk as if the number is verified.

With BQAA observe → derived OKF in Knowledge Catalog:

1. **Ask / the trap** — one human sentence. Legacy metric vs current
   `Active-customer revenue`.
2. **Observe** — session `f21ee192-d989-4c38-894f-66b6b82eaf18`, 180 rows,
   `okf_rfc_observe_agent` / `gemini-3.8-flash`. Rank 1 Active-customer
   revenue; Customer revenue (legacy) excluded (superseded); receipt
   UNVERIFIABLE / nothing attested. A couple of observer-visible titles, not
   a 180-row dump.
3. **Publish** — `python examples/okf_bqaa_adapter/run.py` emits 8 derived
   stubs (metric, computation, policy, tables, log) with their own identity
   chain. KC is where a later agent finds that publication by `context_ref`
   `okf:env-observe#674153c572f6` → publication `sha256:53bd1651…`. The
   Dataplex leftover `okf-derived-germany` is the prior consume experiment —
   do not pretend this CLI path wrote KC. Honesty: this slice’s CLI did not
   DML Catalog; say “this is the handle a KC entry would expose”. Do not
   fake a write. There is no real KC pin for publication `53bd1651`.
4. **Next agent** — `lookup(context_ref)` returns the derived publication.
   Agent uses the current metric, skips legacy, reports the number as
   unproven. Junk refs fail closed. That is the payoff.

## What the page is

A **why-slice** static viewer of the same committed CLI run as PR 11. Same
observe session, same adapter, same identities. The rewrite is editorial:
hero = the question and the payoff in ~3 sentences; four beats in human
language; technical proof (CLI, SHA triple, 180-event histogram, SDK PR 474,
`Object.hasOwn`) lives in a collapsed **How this was built / IDs** panel.

Source of truth remains SDK PR 474 HEAD
`476d37dc9d4210a335c2f77e78003f6a5ebe2878`. **Do not merge PR 474. Do not
re-run the live ADK observe agent. Do not pad events. Off #435.**

## Why

A visitor who is not the RFC author should leave the page knowing: without
this path the agent can pick a dead metric or over-claim trust; with it the
next agent looks up a Catalog handle, uses Active-customer revenue, skips
legacy, and says the number is unproven.

## Constraints (do not break)

- Hero is the question and the payoff. No wall of SHAs on the hero.
- Four beats retitled Ask → Observe → Publish → Next agent. Keep
  `#beat=1` … `#beat=4`.
- Recut walkthrough 20–40s, 1280×720 H.264. Last-frame poster = the payoff
  (lookup JSON + “use Active-customer revenue, not legacy; number unproven”),
  not FAIL_CLOSED, not empty header. On-screen comments in plain English.
  Still run the real `python3 examples/okf_bqaa_adapter/run.py`.
- Caption: one sentence per beat matching the tape.
- Honesty that must stay: derived/demo, observer-only, nothing ATTESTED,
  authored `cymbal-finance-core` untouched, browser does not call GCP,
  germany is SYNTHETIC hashing-only, consume session `04fa3d56` is prior
  experiment not Observe input, do not merge 474, this CLI path did not
  write Knowledge Catalog.
- `context_ref` on the page (beats / IDs, not a hero SHA wall) is
  `okf:env-observe#674153c572f6`. Hero agent, if named, is
  `okf_rfc_observe_agent`.
- Do not dump the giant 180-event JSON onto GitHub Pages.

## Out of scope

- Re-running the observe agent, new BQ DML, new Catalog writes, attester work.
- Changing OKF v0.2 core or PROFILE.md.
- Implementing or merging the SDK adapter (already on PR 474).
- Inventing a different finance story.

## Success

Visitor opens `/rfc/demo/`, reads the question, understands the trap, sees
what the live trace observed, sees that telemetry become a KC handle, and
sees the next agent do better. PR against `caohy1988/caohy1988.github.io`
`main`; Haiyuan merges to flip Pages.
