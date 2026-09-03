# BQAA → derived OKF prototype (`/rfc/demo/`)

Clickable four-beat demo for the OKF runtime context projection RFC:
**Observe → Adapt → Project → Consume**. Live at
<https://caohy1988.github.io/rfc/demo/> once merged. Static files, no build.
The page itself never calls GCP from the browser; it renders a committed
snapshot of one **live GCP run** plus console deep links.

## The live run

| Item | Value |
|---|---|
| Dataset / table | `test-project-0728-467323.okf_rfc_demo.agent_events` (location `US`) |
| ADK agent | `okf_rfc_consume_agent` (`live/run_okf_agent.py`) |
| Model | `gemini-3.8-flash`, Vertex location `global` |
| Session | `04fa3d56-f2f1-413e-8c2b-ec116835af84` |
| Trace | `0294f653a4f141ae960865e438538d2e` |
| Knowledge Catalog entry | `okf-derived-germany` in entry group `okf-rfc-demo` (`us-central1`) |
| `context_ref` | `okf:env-demo#a25e1c0ccbca` (12 hex chars of the derived `publication_id`) |
| Ran at | `2026-09-02T23:05:12Z` |
| Label | **derived / demo, observer-only, not canonical authoring, not ATTESTED** |

All of the above is pinned in `live/live.json`, which also carries the
BigQuery and Dataplex console links the page shows. `live/agent_events.json`
is the committed read-back of the 14 `agent_events` rows the ADK
`BigQueryAgentAnalyticsPlugin` appended during that session.

## Honesty labels

| Thing | Status |
|---|---|
| `live/agent_events.json`, `live/live.json` | **Live, committed snapshot.** Real rows from a real `okf_rfc_demo.agent_events` run of `okf_rfc_consume_agent` on `gemini-3.8-flash`. Exported once; not re-queried by the page. |
| `fixture/bundle/`, `fixture/golden/` | **Authored** Phase 0 fixture, copied byte-for-byte from `okf-phase0-mvp/`. Display-only. Never modified by the adapter. |
| `traces/bqaa-germany.json` | **Synthetic** adapter input (15 events shaped like `agent_events` rows). Used by beat 2 to derive the bundle; never written to a table. `user_id` null; no SQL, parameter values, bundle paths or `concept_version_id`. |
| `derived/bundle/`, `derived/identities.json` | **Derived / demo.** Emitted by the adapter from the trace. `bundle_key = bqaa-derived-cymbal-demo`, its own observation / snapshot / publication triple. Not canonical authoring. |
| Beat 1 Observe | Live `agent_events` rows, observer-only. Never-emit scan runs over every row's `attributes` and `content` keys in the browser. |
| Beat 3 Catalog pane | Live Dataplex entry `okf-derived-germany` (console link). The projection table shown is a client-side view; no `kcmd` write happens from the page. |
| Beat 3 BigQuery pane | Live dataset link. Client-side rows in the RFC projection shape (`publications`, `deployment_heads`, `nodes_current`, `edges_current`). No DML from the page. |
| Beat 4 ADK transcript | **Live** session reconstructed from the committed rows. The agent declared one tool, called it with `context_ref` only, and the tool result names the derived `publication_id` and nothing from the never-emit list. The earlier fixture replay is kept collapsed below it for comparison and is labelled as a replay. |
| Receipt | This live run minted **no receipt**. Nothing was executed as a sanctioned computation and nothing is ATTESTED. The model's own "verified" wording overstates. The only receipt on the page is the Phase 0 golden specimen: `UNVERIFIABLE`, reason `phase0_no_execution_or_integrity_proof`. The Phase 4 `ATTESTED` shape is shown beside it, non-normative. |
| `okf-bqaa-e2e.mp4` | **Prior fixture clip**, recorded before the live run. Not live-GCP proof. See `WALKTHROUGH.md` for the live-page capture plan. |

## Never-emit (agent-facing payloads)

`concept_version_id`, bundle-relative paths, principal / `user_id`, SQL or
query text, parameter values, raw destination table names. Beat 4 asserts at
render time that the live tool-args and tool-result JSON keys ∩ never-emit
list = ∅. Beat 1 runs the same scan over every live row. The bundle inspector
in beat 2 shows authored-style paths because that is source, not telemetry.

## ADK model

The consuming agent is `google.adk.agents.Agent` with
`Gemini(model="gemini-3.8-flash")` on Vertex, location `global`. Every
`LLM_RESPONSE` row in the live snapshot carries
`model_version = gemini-3.8-flash`; the page checks this on load. Never
`gemini-2.5-flash`.

## Identity chain

`hash.js` is a vanilla-JS port of the PROFILE.md rules (canonical CBOR,
domain-separated SHA-256, canon:v1 text normalization). It is checked three
ways:

```
node rfc/demo/tools/check-authored-identities.mjs   # reproduces the authored golden triple + 9 concept versions
node rfc/demo/tools/build-derived.mjs               # regenerates derived/bundle + derived/identities.json
python3 rfc/demo/tools/derived_vectors.py           # independent stdlib re-derivation; exit 0 on match
```

The page recomputes the derived triple in the browser on load and shows
"JS = pinned = Python ✓" only when it matches `derived/identities.json`.
The live `context_ref` and the tool result's `publication_id` must match that
derived triple; the live strip reports "snapshot verified in-browser ✓" only
when they do.

## Check the live snapshot

```
python3 rfc/demo/tools/check_live_trace.py          # exit 0: rows, session, model, context_ref, never-emit all OK
```

This is a read-only check of the committed `live/` files. It does not query
BigQuery. To open the real resources use the console links in
`live/live.json` (`bq_console`, `kc_console`).

## Run locally

```
python3 -m http.server 8000      # from the repo root
open http://localhost:8000/rfc/demo/
```

`file://` does not work: the page fetches its fixtures and the live snapshot
with `fetch()`.

Deep links: `#beat=1` … `#beat=4`. Keys: → / N next, ← / P back, 1–4 jump.

## Manual checklist (static gate)

- [ ] Open each of the four beats; no console errors.
- [ ] Live strip reads "snapshot verified in-browser ✓ · 14 rows".
- [ ] Identity strip shows the authored triple (pinned) and the derived triple with "JS = pinned = Python ✓ · distinct from authored".
- [ ] Beat 1 never-emit scan: every key absent on all live rows.
- [ ] Beat 2 inspector: every stub starts "Derived from BQAA observation, not authored."
- [ ] Beat 3 seam note reads "same publication on both stores ✓"; Dataplex and BigQuery links resolve.
- [ ] Beat 4 model badge reads `gemini-3.8-flash`; tool args are `{context_ref}` only; assertion tile reads `keys ∩ never-emit = ∅ ✓`; receipt tile reads "NO RECEIPT".
- [ ] Walkthrough: the live-run summary card comes first; the video below it is labelled as the prior fixture clip.

## Not in this PR

No live-page recording yet (`WALKTHROUGH.md` lists the beats to capture). No
Catalog writes or BigQuery DML from the page, no attester, no receipt for the
live session, no change to PROFILE.md hashing.
