# Spec — static viewer of the SDK CLI path

## Source of truth (do not invert)

| Item | Value |
|---|---|
| SDK | `GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK` PR 474 HEAD `476d37dc9d4210a335c2f77e78003f6a5ebe2878` |
| Adapter | `okf-bqaa-adapter:v0` · `python examples/okf_bqaa_adapter/run.py` |
| Observe agent | `okf_rfc_observe_agent` |
| Session | `f21ee192-d989-4c38-894f-66b6b82eaf18` |
| Trace | `e-c7214361-4017-43d7-af4e-cddfe51b09a4` |
| Events | **180** (histogram in `live/observe/snapshot.json`) |
| Table | `test-project-0728-467323.okf_rfc_demo.agent_events` |
| Model | `gemini-3.8-flash` · Vertex `global` |
| context_ref | `okf:env-observe#674153c572f6` |
| observation_id | `sha256:85ea62a96e5076a292572a996f0408865c4c56aac696bbeb79a73bbc5eda8af6` |
| snapshot_id | `sha256:f18befd010ff7e3d1fe140303626a82dc985c986846093f73643e7d0eea92b75` |
| publication_id | `sha256:53bd1651c43f69d53f591e4f91e3ccdda4640d8b36cb1dce1ac97328ffa39a77` |
| Receipt | `UNVERIFIABLE` `rcpt-observe-noexec` · nothing ATTESTED |

## Inputs (committed, static)

| File | Role |
|---|---|
| `live/observe/live.json` | Observe-run metadata copied from SDK `fixtures/live.json`. |
| `live/observe/live_identities.json` | Derived identity chain copied from SDK `fixtures/live_identities.json`. |
| `live/observe/mapping.json` | Fail-closed lookup table from the CLI `out/mapping.json`. |
| `live/observe/snapshot.json` | **Trimmed** viewer snapshot (histogram + sample events). Not the 180-row dump. Full export: PR 474. |
| `cli/okf-bqaa-cli-transcript.txt` | Committed plaintext of the stdlib CLI run (durable proof). |
| `cli/okf-bqaa-cli.cast` | asciinema v2 of the same commands. |
| `cli/okf-bqaa-cli.gif` | agg render of the cast. |
| `okf-bqaa-cli.mp4` | Terminal clip of THIS CLI path, labelled live-adapter proof. |
| `okf-bqaa-e2e.mp4` | **Prior fixture clip** only. Must stay labelled as such. |
| `live/live.json`, `live/agent_events.json`, `live/run_okf_agent.py` | **Prior live-GCP consume experiment** (`okf_rfc_consume_agent` / `04fa3d56-…` / `lookup_okf_context`). Keep, but label as NOT adapter input and NOT Observe. |
| `traces/bqaa-germany.json` | **SYNTHETIC hashing-only**. `sess-4c1f9a2e7b3d`. Never the demo source of truth. |
| `fixture/`, `derived/` (germany hashes) | Authored golden + previous germany-derived identities. Germany derived triple may remain as a labelled hashing check; identity strip **derived row** must show the live CLI triple (`53bd1651…`), not `a25e1c0c…`. |
| `adapter.js` / `hash.js` | May remain for the labelled SYNTHETIC hashing check. Must not drive Adapt. Must not claim "computed in-browser" for the live identities. |

## Page structure (top to bottom)

1. Masthead. Kicker: SDK CLI path / live observe snapshot. Badges: derived/demo; authored untouched; ADK `gemini-3.8-flash`; 180 live observe rows; CLI adapter `okf-bqaa-adapter:v0`; browser makes no GCP calls.
2. Banner: derived/demo, observer-only, nothing attested.
3. **Live observe strip**: agent `okf_rfc_observe_agent`, session `f21ee192-…`, trace `e-c7214361-…`, 180 events, table, model, `context_ref okf:env-observe#674153c572f6`, publication `sha256:53bd1651…`, link to SDK PR 474.
4. Identity strip: authored golden unchanged. Derived row = committed `live_identities.json` (NOT "computed in-browser"). Status: "pinned from CLI · okf-bqaa-adapter:v0".
5. Stepper + stage, four beats.
6. Walkthrough: CLI recording first (`okf-bqaa-cli.mp4` + transcript + `.cast`), labelled **live-adapter proof**. Prior `okf-bqaa-e2e.mp4` only if labelled **prior fixture clip, not this run**.
7. Honesty card / "What is real here" rewritten. Live snapshot card rewritten.
8. Footer. `rfc/index.html` Prototype callout updated to observe agent + CLI adapt.

## Beats

### 1 Observe
- Primary: compact snapshot of the 180-row observe session. Histogram, identities, sample events (from `live/observe/snapshot.json`). Facts pane: table, agent, model, session, trace, event_count=180, `ran_at`. Link PR 474 for the full export.
- Never-emit scan over the sample (and documented over the full export on PR 474).
- Collapsed `<details>`: prior consume experiment session `04fa3d56-…` (`okf_rfc_consume_agent`, 14 rows, stub tool) labelled **prior live-GCP consume experiment, NOT this adapter input**.
- Collapsed `<details>`: germany `traces/bqaa-germany.json` labelled **SYNTHETIC hashing-only**.

### 2 Adapt
- Show the committed CLI transcript (`cli/okf-bqaa-cli-transcript.txt`) as the proof. Commands + stdout: LABEL, ADAPTER, TABLE, SESSION, TRACE, MODEL, CONTEXT_REF, RECEIPT, OBSERVATION_ID, SNAPSHOT_ID, PUBLICATION_ID, FILES.
- Optional: embed/link `okf-bqaa-cli.mp4` / gif here too.
- Bundle inspector may still list the 8 derived files, but they must be described as CLI `out/bundle/` from `okf-bqaa-adapter:v0`, not as an in-browser adapter result from germany.
- Stop every "computed in-browser" string on the live derived row.

### 3 Project
- Identity chips from `live_identities.json` (`85ea62a9` / `f18befd0` / `53bd1651`).
- Catalog pane + BigQuery pane: **derived views / honesty labels, not extra DML**. Do not claim a live Catalog write for this CLI path. Prior Dataplex entry `okf-derived-germany` may remain as a labelled leftover of the consume experiment.
- Authored `cymbal-finance-core` untouched.

### 4 Consume
- Primary: fail-closed lookup of `okf:env-observe#674153c572f6` → publication `sha256:53bd1651…`, label `derived/demo`.
- Also show the junk-ref tape: `okf:env-junk#deadbeef` → `FAIL_CLOSED` exit 2.
- Receipt tile: `UNVERIFIABLE` / `rcpt-observe-noexec`. Nothing ATTESTED. Phase 4 ATTESTED shape stays non-normative.
- Collapsed: prior `lookup_okf_context` stub + session `04fa3d56-…` labelled prior live-GCP consume experiment.

## Honesty (must be true on the page)

- Browser never calls GCP.
- Observe input is the 180-row observe session, not consume, not germany.
- Adapt is the Python CLI, not `adapter.js`.
- Germany may remain only as SYNTHETIC hashing-only.
- Receipt is UNVERIFIABLE. Nothing ATTESTED.

## Checks

- `python3 rfc/demo/tools/check_cli_viewer.py` (new): asserts observe live.json session, event_count 180, context_ref, publication_id, transcript contains SESSION/PUBLICATION_ID/FAIL_CLOSED, index.html contains `okf_rfc_observe_agent` and `okf:env-observe#674153c572f6` and does **not** present consume session as Observe / germany as SoT (hero/live-strip).
- Existing authored/derived vector checks may still run against the labelled germany hashing fixtures; do not retarget them at the live CLI identities (different bundle_key / different files).
- Grep the demo HTML/JS for forbidden live claims: `computed in-browser` on the derived live row, hero `okf_rfc_consume_agent`, hero `okf:env-demo#a25e1c0ccbca`.
