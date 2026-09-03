# Intent — static viewer of the SDK CLI path (`/rfc/demo/`)

Status: accepted from Haiyuan (2026-09-02 9:34 PM PT): record the demo via the
code/CLI path that traces BQAA → OKF, then "update the full demo". Public
https://caohy1988.github.io/rfc/demo/ must become a **static viewer of the SDK
CLI path**, not an in-browser germany adapter and not the consume-agent page.

## What

The page is a committed snapshot of one stdlib CLI run:

```
python examples/okf_bqaa_adapter/run.py
python examples/okf_bqaa_adapter/run.py --lookup 'okf:env-observe#674153c572f6'
```

Source of truth: `GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK` PR 474 HEAD
`476d37dc9d4210a335c2f77e78003f6a5ebe2878` (`examples/okf_bqaa_adapter`).
**Do not merge PR 474. Do not re-run the live ADK observe agent. Do not pad
events. Off #435.**

Four honest beats:

1. **Observe** = live ADK observe agent `okf_rfc_observe_agent` writing **180**
   `agent_events` in session `f21ee192-d989-4c38-894f-66b6b82eaf18`
   (`gemini-3.8-flash`, Vertex `global`, table
   `test-project-0728-467323.okf_rfc_demo.agent_events`). Compact snapshot +
   `live.json` / `live_identities.json`; link PR 474 for the full export.
2. **Adapt** = Python `okf-bqaa-adapter:v0` via `python examples/okf_bqaa_adapter/run.py`.
   **Not** in-browser `adapter.js` on `traces/bqaa-germany.json`. Stop claiming
   "computed in-browser". Show the CLI transcript on this beat.
3. **Project** = committed identities from `live_identities.json`
   (observation `sha256:85ea62a9…`, snapshot `sha256:f18befd0…`, publication
   `sha256:53bd1651…`). Authored `cymbal-finance-core` untouched. Catalog/BQ
   tables on the page are derived views / honesty labels, not extra DML.
4. **Consume** = fail-closed lookup of `context_ref`
   `okf:env-observe#674153c572f6`. Old consume stub `lookup_okf_context` /
   session `04fa3d56-…` stay labelled as the **prior live-GCP consume
   experiment**, not this adapter input. Receipt remains **UNVERIFIABLE** /
   nothing ATTESTED. Browser still never calls GCP.

## Why

The live public page (f86689c / PR 9) still presents `okf_rfc_consume_agent`
session `04fa3d56-…` and `okf:env-demo#a25e1c0ccbca` as if they were Observe
input, and still adapts the germany fixture in-browser. Leadership asked for
the real BQAA → OKF code path that is already on PR 474.

## Constraints (do not break)

- `context_ref` on the page must be `okf:env-observe#674153c572f6`, never
  `okf:env-demo#a25e1c0ccbca`.
- Hero agent must be `okf_rfc_observe_agent`, not consume.
- NEVER use consume session `04fa3d56-…` as Observe input.
- NEVER use germany `sess-4c1f9a2e7b3d` as the demo source of truth (may remain
  labelled SYNTHETIC hashing-only).
- Do not dump the giant 180-event JSON onto GitHub Pages.
- Static Pages. Browser never calls GCP. No secrets.
- `okf-bqaa-e2e.mp4` is a **prior fixture clip**. New walkthrough media is the
  CLI tape (`cli/okf-bqaa-cli.cast` + `okf-bqaa-cli.mp4`), labelled live-adapter
  proof.
- Do not merge SDK PR 474. Do not start #435.

## Out of scope

- Re-running the observe agent, new BQ DML, new Catalog writes, attester work.
- Changing OKF v0.2 core or PROFILE.md.
- Implementing or merging the SDK adapter (already on PR 474).

## Success

Visitor opens `/rfc/demo/`, sees observe session `f21ee192-…`, 180 events,
CLI adapt to publication `sha256:53bd1651…`, fail-closed lookup of
`okf:env-observe#674153c572f6`, and a CLI walkthrough. PR against
`caohy1988/caohy1988.github.io` `main`; Haiyuan merges to flip Pages.
