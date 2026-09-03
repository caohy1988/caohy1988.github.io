# BQAA → derived OKF: static viewer of the SDK CLI path (`/rfc/demo/`)

Clickable four-beat page for the OKF runtime context projection RFC:
**Observe → Adapt → Project → Consume**. Live at
<https://caohy1988.github.io/rfc/demo/> once merged. Static files, no build.

The page is a **viewer of one recorded CLI run**, not an adapter. It renders a
committed snapshot of a live ADK observe session, the identities the SDK CLI
derived from it, and the CLI transcript. The browser hashes nothing, adapts
nothing, resolves nothing for the live identities, and never calls GCP.

## The run on record

```
python examples/okf_bqaa_adapter/run.py
python examples/okf_bqaa_adapter/run.py --lookup 'okf:env-observe#674153c572f6'
python examples/okf_bqaa_adapter/run.py --lookup 'okf:env-junk#deadbeef'   # FAIL_CLOSED, exit 2
```

| Item | Value |
|---|---|
| SDK | `GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK` [PR 474](https://github.com/GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK/pull/474) HEAD `476d37dc9d4210a335c2f77e78003f6a5ebe2878`, `examples/okf_bqaa_adapter` (**do not merge**) |
| Adapter | `okf-bqaa-adapter:v0`, stdlib only, no GCP on the default path |
| Observe agent | `okf_rfc_observe_agent`, google-adk, `gemini-3.8-flash`, Vertex `global` |
| Table | `test-project-0728-467323.okf_rfc_demo.agent_events` |
| Session | `f21ee192-d989-4c38-894f-66b6b82eaf18` |
| Trace | `e-c7214361-4017-43d7-af4e-cddfe51b09a4` (first of 12 invocations) |
| Events | **180** rows, multi-turn, one session; not padded |
| `context_ref` | `okf:env-observe#674153c572f6` |
| observation_id | `sha256:85ea62a96e5076a292572a996f0408865c4c56aac696bbeb79a73bbc5eda8af6` |
| snapshot_id | `sha256:f18befd010ff7e3d1fe140303626a82dc985c986846093f73643e7d0eea92b75` |
| publication_id | `sha256:53bd1651c43f69d53f591e4f91e3ccdda4640d8b36cb1dce1ac97328ffa39a77` |
| Receipt | `UNVERIFIABLE` `rcpt-observe-noexec`; nothing ATTESTED |
| Ran at | `2026-09-03T04:10:36Z` |
| Label | **derived / demo, observer-only, nothing attested, not canonical authoring** |

## Files

| File | Role |
|---|---|
| `live/observe/live.json` | Observe-run metadata (copy of SDK `fixtures/live.json`). |
| `live/observe/live_identities.json` | Derived identity chain (copy of SDK `fixtures/live_identities.json`): 8 file hashes, 7 concept versions, the triple above. |
| `live/observe/mapping.json` | The CLI's `out/mapping.json`: exactly one binding, `okf:env-observe#674153c572f6` → publication. |
| `live/observe/snapshot.json` | **Trimmed** viewer snapshot: event-type histogram (Σ 180), identities, six sample rows, never-emit list. Not the export. The 494 KB 180-row export is on PR 474 only. |
| `cli/okf-bqaa-cli-transcript.txt` | Plaintext of the CLI run (durable proof). |
| `cli/okf-bqaa-cli.cast` · `cli/okf-bqaa-cli.gif` · `okf-bqaa-cli.mp4` | asciinema v2 cast, gif render and terminal clip of the same commands, labelled **live-adapter proof**. |
| `fixture/bundle/`, `fixture/golden/` | **Authored** Phase 0 fixture (`cymbal-finance-core`), display-only, never touched by the adapter. |
| `okf-bqaa-e2e.mp4` | **Prior fixture clip**, recorded before the observe run. Collapsed on the page and labelled as not this run. |
| `live/live.json`, `live/agent_events.json`, `live/run_okf_agent.py` | **Prior live-GCP consume experiment** (`okf_rfc_consume_agent`, session `04fa3d56-…`, stub `lookup_okf_context`, 14 rows). Kept, collapsed under beats 1 and 4, labelled prior. Not the Observe input; the SDK CLI fails closed on that session (not retrieve-shaped). |
| `traces/bqaa-germany.json`, `derived/` | **SYNTHETIC hashing-only** (`sess-4c1f9a2e7b3d`). Regression input for `adapter.js` + `hash.js`; collapsed under beat 1; never the source of truth. |
| `adapter.js`, `hash.js` | Loaded only for that synthetic hashing check. They do not drive Adapt and produce none of the live identities. |

## Beats

1. **Observe.** Histogram of the 180 rows, six sample rows, run facts, PR 474 link for the full export. Never-emit scan over the sample content keys. Collapsed: the prior consume experiment and the synthetic Germany trace, both labelled.
2. **Adapt.** The committed CLI transcript with the pinned identities highlighted, links to the cast / gif / mp4, and the 8 derived files (names, sha256, store-only concept versions) described as the CLI `out/bundle/`. Cross-checks: transcript = `live_identities.json` = identity strip; `FILES 8`; one mapping binding; distinct from the authored bundle.
3. **Project.** Identity chips from `live_identities.json`. Catalog pane is a derived view with an honesty label (no entry created on this path; the prior Dataplex entry `okf-derived-germany` is a labelled leftover). BigQuery pane shows the live source table (read-only) above the RFC projection shape rendered from the pinned identities. No DML.
4. **Consume.** Tape 1: `--lookup okf:env-observe#674153c572f6` → `{context_ref, publication_id, label: derived/demo}`. Tape 2: `--lookup okf:env-junk#deadbeef` → `FAIL_CLOSED`, exit 2. A "try a ref" box resolves against the committed `mapping.json` with the same rule (static file, no store, no network). Receipt tile `UNVERIFIABLE · rcpt-observe-noexec`; Phase 4 ATTESTED shape non-normative. Collapsed: the prior stub-tool consume transcript, labelled prior.

## Honesty

- Browser never calls GCP. Same-origin static files and Google Fonts only.
- Observe input is the 180-row observe session. Not the prior consume session, not the Germany fixture.
- Adapt is the Python CLI on SDK PR 474. Not `adapter.js`. No identity on this page was computed in the browser.
- Catalog / BigQuery projection tables are derived views. No Catalog write and no DML on this path.
- Receipt is `UNVERIFIABLE`. Nothing is ATTESTED.
- Never emitted on agent-facing payloads: `concept_version_id`, bundle paths, principal, SQL / query text, parameter values, raw destination table names.
- Model is `gemini-3.8-flash` throughout. Never `2.5`.

## Checks

```
python3 rfc/demo/tools/check_cli_viewer.py    # exit 0: snapshot, identities, mapping, transcript, page strings, no forbidden claims
```

Read-only over the committed files. It asserts the observe session, `event_count` 180, the `context_ref`, the publication, the transcript lines (`SESSION`, `PUBLICATION_ID`, `FAIL_CLOSED`), that the hero / live strip names `okf_rfc_observe_agent` and `okf:env-observe#674153c572f6`, that the prior consume session and the Germany fixture are never presented as source of truth, and that no "computed in-browser" claim remains.

The older germany hashing checks still run as labelled extras and are **not** retargeted at the live identities (different `bundle_key` inputs, different files):

```
node rfc/demo/tools/check-authored-identities.mjs   # authored golden triple + 9 concept versions
python3 rfc/demo/tools/derived_vectors.py           # synthetic germany re-derivation
python3 rfc/demo/tools/check_live_trace.py          # prior consume-experiment snapshot (labelled prior)
```

## Reproduce the CLI run

```
git clone https://github.com/GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK
git checkout 476d37dc9d4210a335c2f77e78003f6a5ebe2878      # PR 474 HEAD; do not merge
python examples/okf_bqaa_adapter/run.py
python examples/okf_bqaa_adapter/run.py --lookup 'okf:env-observe#674153c572f6'
```

Do not run `--live`: the observe agent is not to be re-run and the export is not to be padded.

## Run the page locally

```
python3 -m http.server 8000      # from the repo root
open http://localhost:8000/rfc/demo/
```

`file://` does not work: the page fetches its snapshot and transcript with `fetch()`.
Deep links: `#beat=1` … `#beat=4`. Keys: → / N next, ← / P back, 1–4 jump.

## Manual checklist (static gate)

- [ ] Open each of the four beats; no console errors.
- [ ] Live strip reads "snapshot loaded ✓ · 180 events · transcript agrees".
- [ ] Identity strip: authored triple pinned; derived row reads "pinned from CLI · okf-bqaa-adapter:v0 · = transcript ✓ · distinct from authored".
- [ ] Beat 1 histogram sums to 180; never-emit scan all ✓; prior consume and Germany sections collapsed and labelled.
- [ ] Beat 2 transcript shows `PUBLICATION_ID sha256:53bd1651…` highlighted; all cross-checks ✓.
- [ ] Beat 3 seam note reads "one publication everywhere on this page ✓"; Catalog card says no write on this path.
- [ ] Beat 4 tape 1 resolves, tape 2 reads `FAIL_CLOSED … # exit 2`; receipt tile reads `UNVERIFIABLE · rcpt-observe-noexec`.
- [ ] Walkthrough: `okf-bqaa-cli.mp4` first, labelled live-adapter proof; the e2e clip collapsed and labelled prior fixture clip.

## Not in this PR

No re-run of the observe agent, no new BigQuery DML, no Catalog writes, no attester, no receipt beyond the no-execution specimen, no change to OKF v0.2 core or PROFILE.md, no merge of SDK PR 474, nothing from #435.
