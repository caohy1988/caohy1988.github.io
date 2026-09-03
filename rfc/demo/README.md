# Why a BQAA trace becomes derived OKF the next agent can look up (`/rfc/demo/`)

Live at <https://caohy1988.github.io/rfc/demo/> once merged. Static files, no build.

## The question

**What was active-customer revenue in Germany last quarter — and can I trust the number?**

Without this path a finance agent can pick the superseded **Customer revenue
(legacy)** metric, or talk as if the number is verified. A live BQAA trace
ranked **Active-customer revenue** first, excluded the legacy metric, and
recorded the receipt as unproven. Derived OKF in Knowledge Catalog is how the
next agent finds that: it uses the current metric, skips legacy, and reports
the number as unproven.

## What this demo is asking

Three readings are possible and only one is right. Are we trusting what is
in BQAA? Are we asking a human-in-the-loop or customer sentiment to decide
what to promote? Or are we adding context the agent obtained via the hard
path into OKF so it is available for easy discovery? **The third.**

- **Yes:** hard-path agent context (ranked `Active-customer revenue`, excluded
  the legacy metric, receipt unproven) was observed by BQAA; one adapter turn
  projects it into derived OKF so the next agent discovers it via `context_ref`
  instead of re-earning it or picking the dead metric.
- **Not** trusting BQAA as knowledge or truth. BQAA is observer-only; telemetry
  is not the authored bundle and not a truth score.
- **Not** human-in-the-loop promotion or customer-sentiment ranking of what to
  promote. This slice does not pick winners that way.
- Trust here means **process integrity of what was observed**: opaque IDs,
  fail-closed lookup, no overclaim. Not the number (the receipt stays
  `UNVERIFIABLE`), not BQAA as a second wiki.

## Four beats

1. **Ask.** The question, as recorded in the trace, and the two traps: the
   dead metric (`Customer revenue (legacy)`, superseded, out of force since
   2026-06-20) and over-claiming trust (no sanctioned computation ran). Beat 1
   also answers the three-way question above: hard-path context → derived OKF
   for discovery; not HITL or sentiment promotion; not BQAA as truth.
2. **Observe.** What the live trace saw: rank 1 `Active-customer revenue`;
   `Customer revenue (legacy)` excluded as superseded; receipt `UNVERIFIABLE`,
   nothing attested. A few observer-visible titles, not a 180-row dump.
3. **Publish.** `python examples/okf_bqaa_adapter/run.py` emits 8 derived
   stubs (metric, computation, concept, policy, two tables, the legacy metric
   marked deprecated, a log) with their own identity chain. The handle a
   Knowledge Catalog entry would expose is `context_ref`
   `okf:env-observe#674153c572f6` → publication `sha256:53bd1651…`.
   **This CLI path did not write Knowledge Catalog.** No entry, no DML, no
   real Catalog pin for that publication. The Dataplex entry
   `okf-derived-germany` is a leftover of the prior consume experiment and is
   labelled as such.
4. **Next agent.** `run.py --lookup 'okf:env-observe#674153c572f6'` returns
   `{context_ref, publication_id, label: derived/demo}`. The agent uses
   `Active-customer revenue`, skips legacy, reports the number as unproven.
   Junk refs fail closed (`FAIL_CLOSED`, exit 2, labelled expected). That is
   the payoff.

The page is a **viewer of one recorded CLI run**, not an adapter. It renders a
committed snapshot of the live ADK observe session, the identities the SDK
CLI derived from it, and the CLI transcript. The browser hashes nothing,
adapts nothing, resolves nothing for the live identities, and never calls
GCP. All IDs sit in the collapsed **How this was built / IDs** panel.

## The run on record

```
python examples/okf_bqaa_adapter/run.py
python examples/okf_bqaa_adapter/run.py --lookup 'okf:env-observe#674153c572f6'
python examples/okf_bqaa_adapter/run.py --lookup 'okf:env-junk#deadbeef'   # FAIL_CLOSED, exit 2
```

| Item | Value |
|---|---|
| SDK | `GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK` [PR 474](https://github.com/GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK/pull/474) recording-time HEAD `476d37dc9d4210a335c2f77e78003f6a5ebe2878`, `examples/okf_bqaa_adapter`. **PR 474 merged 2026-09-03T16:54:58Z** (merge commit `4f54b5c0506d646f0fb785469701abbcc1ead79e`); the tape, cast, and transcript are a pre-merge recording of that HEAD |
| Adapter | `okf-bqaa-adapter:v0`, stdlib only, no GCP on the default path |
| Observe agent | `okf_rfc_observe_agent`, google-adk, `gemini-3.8-flash`, Vertex `global` |
| Table | `test-project-0728-467323.okf_rfc_demo.agent_events` |
| Session | `f21ee192-d989-4c38-894f-66b6b82eaf18` |
| Trace | `e-c7214361-4017-43d7-af4e-cddfe51b09a4` (first of 12 invocations) |
| Events | 180 rows, multi-turn, one session; not padded |
| `context_ref` | `okf:env-observe#674153c572f6` |
| observation_id | `sha256:85ea62a96e5076a292572a996f0408865c4c56aac696bbeb79a73bbc5eda8af6` |
| snapshot_id | `sha256:f18befd010ff7e3d1fe140303626a82dc985c986846093f73643e7d0eea92b75` |
| publication_id | `sha256:53bd1651c43f69d53f591e4f91e3ccdda4640d8b36cb1dce1ac97328ffa39a77` |
| Receipt | `UNVERIFIABLE` `rcpt-observe-noexec`; nothing ATTESTED |
| Catalog write on this path | none; no real Catalog pin for `53bd1651` |
| Ran at | `2026-09-03T04:10:36Z` |
| Label | **derived / demo, observer-only, nothing attested, not canonical authoring** |

## Files

| File | Role |
|---|---|
| `live/observe/live.json` | Observe-run metadata (copy of SDK `fixtures/live.json`). |
| `live/observe/live_identities.json` | Derived identity chain (copy of SDK `fixtures/live_identities.json`): 8 file hashes, 7 concept versions, the triple above. |
| `live/observe/mapping.json` | The CLI's `out/mapping.json`: exactly one binding, `okf:env-observe#674153c572f6` → publication. |
| `live/observe/snapshot.json` | **Trimmed** viewer snapshot: event-type histogram (Σ 180), identities, six sample rows (including the tool result with the ranked titles and the exclusion), never-emit list. Not the export. The 494 KB 180-row export is on PR 474 only. |
| `cli/okf-bqaa-cli-transcript.txt` | Plaintext of the four-beat tape (durable proof). |
| `cli/okf-bqaa-cli.cast` · `cli/okf-bqaa-cli.gif` · `okf-bqaa-cli.mp4` · `okf-bqaa-cli-poster.png` | asciinema v2 cast, gif (agg), H.264 1280×720 ~25s tape (agg + ffmpeg), poster = last frame: lookup JSON + “Payoff: use Active-customer revenue, not legacy; the number is unproven.” |
| `fixture/bundle/`, `fixture/golden/` | **Authored** Phase 0 fixture (`cymbal-finance-core`), display-only, never touched by the adapter. |
| `okf-bqaa-e2e.mp4` | **Prior fixture clip**, recorded before the observe run. Collapsed on the page and labelled as not this run. |
| `live/live.json`, `live/agent_events.json`, `live/run_okf_agent.py` | **Prior live-GCP consume experiment** (`okf_rfc_consume_agent`, session `04fa3d56-…`, stub `lookup_okf_context`, 14 rows). Kept, collapsed under beats 1 and 4, labelled prior. Not the Observe input; the SDK CLI fails closed on that session (not retrieve-shaped). |
| `traces/bqaa-germany.json`, `derived/` | **SYNTHETIC hashing-only** (`sess-4c1f9a2e7b3d`). Regression input for `adapter.js` + `hash.js`; collapsed under beat 1; never the source of truth. |
| `adapter.js`, `hash.js` | Loaded only for that synthetic hashing check. They do not drive Publish and produce none of the live identities. |

## Honesty

- Browser never calls GCP. Same-origin static files and Google Fonts only.
- Observe input is the 180-row observe session. Not the prior consume session, not the Germany fixture.
- Publish is the Python CLI on SDK PR 474. Not `adapter.js`. No identity on this page was computed in the browser.
- This CLI path did not write Knowledge Catalog and issued no DML. The handle on beat 3 is what a Catalog entry would expose, rendered from `mapping.json` and `live_identities.json`.
- Receipt is `UNVERIFIABLE`. Nothing is ATTESTED. The number is unproven and the page says so.
- Never emitted on agent-facing payloads: `concept_version_id`, bundle paths, principal, SQL / query text, parameter values, raw destination table names.
- Model is `gemini-3.8-flash` throughout. Never `2.5`.

## Checks

```
python3 rfc/demo/tools/check_cli_viewer.py    # exit 0: story + snapshot + identities + transcript + page strings
node --check rfc/demo/app.js
```

Read-only over the committed files. It asserts the locked hero question and
three-sentence payoff, that the hero carries no SHA wall (no full publication,
no `Object.hasOwn`, no adapter badge, no 180 badge), the stepper titles
Ask / Observe / Publish / Next agent, the tape beats (question, rank 1,
excluded legacy, `PUBLICATION_ID`, lookup JSON, payoff after the labelled
`FAIL_CLOSED`), the poster wiring, the honesty strings, and that the prior
consume session and the Germany fixture are never presented as source of
truth. Two hermetic node runs exercise the page's `Object.hasOwn` lookup
(constructor / toString / `__proto__` fail closed) and its transcript parser.

The older germany hashing checks still run as labelled extras and are **not**
retargeted at the live identities:

```
node rfc/demo/tools/check-authored-identities.mjs   # authored golden triple + 9 concept versions
python3 rfc/demo/tools/derived_vectors.py           # synthetic germany re-derivation
python3 rfc/demo/tools/check_live_trace.py          # prior consume-experiment snapshot (labelled prior)
```

## Reproduce the CLI run

```
git clone https://github.com/GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK
git checkout 476d37dc9d4210a335c2f77e78003f6a5ebe2878      # PR 474 pre-merge HEAD, the SHA the tape was recorded against
# PR 474 has merged (2026-09-03, 4f54b5c0506d); the same adapter is on main, but reproduce against the recording SHA
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

- [ ] Hero reads the question and the three-sentence payoff; only three short badges, no SHA wall.
- [ ] Open each of the four beats; no console errors.
- [ ] Beat 1: the question as recorded, the "What this demo is asking" block (third option; not HITL / sentiment; not BQAA as truth; number unproven), the two traps, the current metric; prior consume and Germany sections collapsed and labelled.
- [ ] Beat 2: rank 1 `Active-customer revenue`, excluded `Customer revenue (legacy)`, receipt UNVERIFIABLE; tape agrees, all ✓.
- [ ] Beat 3: 8 stubs with titles, legacy marked deprecated; the KC handle card says no Catalog write on this path; Dataplex leftover labelled prior.
- [ ] Beat 4: lookup JSON + payoff; “what the next agent does” (use / skip / unproven); junk-ref tape labelled expected; try-a-ref fails closed on anything else.
- [ ] Walkthrough: `okf-bqaa-cli.mp4` first, poster is the lookup JSON + payoff (not FAIL_CLOSED, not an empty header); four one-sentence captions; e2e clip collapsed and labelled prior.
- [ ] How this was built / IDs: live strip reads "snapshot loaded ✓ · 180 events · transcript agrees"; derived row reads "pinned from CLI · … = transcript ✓ · distinct from authored"; histogram Σ 180.

## Not in this PR

No re-run of the observe agent, no new BigQuery DML, no Catalog writes, no attester, no receipt beyond the no-execution specimen, no change to OKF v0.2 core or PROFILE.md, nothing from #435, no re-record of the tape after SDK PR 474 merged (it stays a labelled pre-merge recording), no different finance story.
