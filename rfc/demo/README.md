# BQAA → derived OKF prototype (`/rfc/demo/`)

Clickable four-beat demo for the OKF runtime context projection RFC:
**Observe → Adapt → Project → Consume**. Live at
<https://caohy1988.github.io/rfc/demo/> once merged. Static files, no build,
no live GCP.

## Honesty labels

| Thing | Status |
|---|---|
| `fixture/bundle/`, `fixture/golden/` | **Authored** Phase 0 fixture, copied byte-for-byte from `okf-phase0-mvp/`. Display-only. Never modified by the adapter. |
| `traces/bqaa-germany.json` | **Synthetic** BQAA observer trace (15 events shaped like `agent_events` rows). Never written to a table. `user_id` null; no SQL, parameter values, bundle paths or `concept_version_id`. |
| `derived/bundle/`, `derived/identities.json` | **Derived / demo.** Emitted by the adapter from the trace. `bundle_key = bqaa-derived-cymbal-demo`, its own observation / snapshot / publication triple. Not canonical authoring. |
| Beat 3 Catalog pane | Projection **view**. No live `kcmd` write. |
| Beat 3 BigQuery pane | Client-side rows in the RFC projection shape (`publications`, `deployment_heads`, `nodes_current`, `edges_current`). No DML. |
| Beat 4 ADK transcript | Fixture **replay** of an ADK agent on `gemini-3.8-flash`. The page runs no Python and calls no model. |
| Receipt | Phase 0 golden specimen: `UNVERIFIABLE`, reason `phase0_no_execution_or_integrity_proof`. Nothing was executed or attested. Phase 4 `ATTESTED` shape shown beside it, non-normative. |

## Never-emit (agent-facing payloads)

`concept_version_id`, bundle-relative paths, principal / `user_id`, SQL or
query text, parameter values, raw destination table names. Beat 4 asserts at
render time that the tool-result JSON keys ∩ never-emit list = ∅. Beat 1 runs
the same scan over every trace event key. The bundle inspector in beat 2 shows
authored-style paths because that is source, not telemetry.

## ADK model

The consuming agent is `google.adk.agents.Agent` with
`Gemini(model="gemini-3.8-flash")`. `DEMO_MODEL_ID` may override; the
checked-in default is `gemini-3.8-flash`. Never `gemini-2.5-flash`.

## Identity chain

`hash.js` is a vanilla-JS port of the PROFILE.md rules (canonical CBOR,
domain-separated SHA-256, canon:v1 text normalization). It is checked three
ways:

```
node tools/check-authored-identities.mjs   # reproduces the authored golden triple + 9 concept versions
node tools/build-derived.mjs               # regenerates derived/bundle + derived/identities.json
python3 tools/derived_vectors.py           # independent stdlib re-derivation; exit 0 on match
```

The page recomputes the derived triple in the browser on load and shows
"JS = pinned = Python ✓" only when it matches `derived/identities.json`.
`tools/derived_vectors.py` is adapted from `okf-phase0-mvp/golden/vectors_gen.py`
and is read-only with respect to `okf-phase0-mvp/`.

## Run locally

```
python3 -m http.server 8000      # from the repo root
open http://localhost:8000/rfc/demo/
```

`file://` does not work: the page fetches its fixtures with `fetch()`.

Deep links: `#beat=1` … `#beat=4`. Keys: → / N next, ← / P back, 1–4 jump.

## Manual checklist (static gate)

- [ ] Open each of the four beats; no console errors.
- [ ] Identity strip shows the authored triple (pinned) and the derived triple with "JS = pinned = Python ✓ · distinct from authored".
- [ ] Beat 1 never-emit scan: every key absent, `user_id` null on all events.
- [ ] Beat 2 inspector: every stub starts "Derived from BQAA observation, not authored."
- [ ] Beat 3 seam note reads "same publication on both stores ✓".
- [ ] Beat 4 model badge reads `gemini-3.8-flash`; assertion tile reads `keys ∩ never-emit = ∅ ✓`; verdict `UNVERIFIABLE`.

## Not in this PR

No `okf-bqaa-e2e.mp4` and no recording. Per Haiyuan (2026-09-02): record only
after Claude, Codex and Kimi align (dual LGTM on the PR). No live Catalog
writes, no BigQuery DML, no attester, no change to PROFILE.md hashing.
