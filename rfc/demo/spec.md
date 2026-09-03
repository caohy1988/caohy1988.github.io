# Spec — why-slice rewrite of `/rfc/demo/`

Same committed run as PR 11. Same files under `live/observe/` and the same
SDK CLI. This spec is the editorial + tape rewrite.

## Source of truth (do not invert)

| Item | Value |
|---|---|
| SDK | `GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK` PR 474 HEAD `476d37dc9d4210a335c2f77e78003f6a5ebe2878` |
| Adapter | `okf-bqaa-adapter:v0` · `python examples/okf_bqaa_adapter/run.py` |
| Observe agent | `okf_rfc_observe_agent` |
| Session | `f21ee192-d989-4c38-894f-66b6b82eaf18` |
| Trace | `e-c7214361-4017-43d7-af4e-cddfe51b09a4` |
| Events | **180** (histogram only in collapsed IDs / How this was built) |
| Table | `test-project-0728-467323.okf_rfc_demo.agent_events` |
| Model | `gemini-3.8-flash` · Vertex `global` |
| context_ref | `okf:env-observe#674153c572f6` |
| observation_id | `sha256:85ea62a96e5076a292572a996f0408865c4c56aac696bbeb79a73bbc5eda8af6` |
| snapshot_id | `sha256:f18befd010ff7e3d1fe140303626a82dc985c986846093f73643e7d0eea92b75` |
| publication_id | `sha256:53bd1651c43f69d53f591e4f91e3ccdda4640d8b36cb1dce1ac97328ffa39a77` |
| Receipt | `UNVERIFIABLE` `rcpt-observe-noexec` · nothing ATTESTED |
| KC write this path | **none**. No real KC pin for publication `53bd1651`. Dataplex `okf-derived-germany` is a leftover of the prior consume experiment. |

## Locked copy

### Hero title

What was active-customer revenue in Germany last quarter — and can I trust the number?

### Hero subtitle (exactly, ~3 sentences)

Without this path a finance agent can pick the superseded Customer revenue (legacy) metric, or talk as if the number is verified. A live BQAA trace ranked Active-customer revenue first, excluded the legacy metric, and recorded the receipt as unproven. Derived OKF in Knowledge Catalog is how the next agent finds that — uses the current metric, skips legacy, and reports the number as unproven.

Do **not** put a wall of SHAs, adapter version, event counts, or `Object.hasOwn` in the hero or the live strip. A short derived/demo badge is fine. Session / SHA / PR 474 live in **How this was built / IDs**.

### Four beat titles (human language; keep `#beat=1..4`)

| # | Short title (stepper `.t`) | Subtitle (stepper `.s`) | Stage story |
|---|---|---|---|
| 1 | Ask | The question and the trap | One human sentence: the agent is asked for Germany last-quarter revenue and whether to trust it. Two traps: (a) **Customer revenue (legacy)**, superseded; (b) talking as if the number is verified. Contrast with current **Active-customer revenue**. |
| 2 | Observe | What the live trace saw | Session `f21ee192-…`, agent `okf_rfc_observe_agent` / `gemini-3.8-flash`. Rank 1 **Active-customer revenue**. **Customer revenue (legacy)** excluded (superseded; out of force since 2026-06-20). Receipt UNVERIFIABLE / nothing attested. Show a couple of observer-visible titles (rank 1 metric, the exclusion, maybe rank 2 computation). Not a 180-row dump, not the histogram as the hero of the beat. |
| 3 | Publish | Derived OKF, a Catalog handle | `python examples/okf_bqaa_adapter/run.py` emits 8 derived stubs (metric, computation, policy, tables, log) with their own identity chain. Titles the next agent can use. KC is where a later agent finds that publication by `context_ref` `okf:env-observe#674153c572f6` → publication `sha256:53bd1651…`. **Honesty, on this beat, in human language:** this CLI path did not DML Catalog; “this is the handle a Knowledge Catalog entry would expose.” The Dataplex leftover `okf-derived-germany` stays collapsed and labelled prior consume experiment. Do not fake a write. |
| 4 | Next agent | Lookup and the payoff | `lookup(context_ref)` returns the derived publication. Agent uses Active-customer revenue, skips legacy, reports the number as unproven. Junk refs fail closed (labelled expected, not a crash). That is the payoff. |

Walkthrough captions (one sentence per beat, matching the tape):

1. The agent is asked for Germany last-quarter revenue — and whether the number can be trusted.
2. The live trace ranked Active-customer revenue first and excluded the superseded legacy metric; the receipt is unproven.
3. One command turns that telemetry into derived OKF, the handle a Catalog entry would expose.
4. The next agent looks up that handle, uses the current metric, skips legacy, and reports the number as unproven.

## Page structure (top to bottom)

1. Site topbar (unchanged).
2. **Masthead / hero.** Kicker can stay “Prototype · OKF runtime context projection”. Title = the locked question. Subtitle = the locked three sentences. Badges: derived/demo; authored untouched; static viewer / no GCP. **Not** a badge wall of 180 / adapter:v0 / PR 474 / SHA chips.
3. Optional one-line banner: derived/demo, observer-only, nothing attested. Keep it short.
4. **Do not** keep the three-row live SHA strip above the stepper. Move agent / session / table / SHA triple / context_ref / PR 474 into collapsed **How this was built / IDs**. Authored golden chips also live there (or a one-line “authored cymbal-finance-core untouched”).
5. Stepper + stage, four beats as the table above. Keep visual language (masthead fonts, stepper, stage, tiles). Rewrite beat bodies in `app.js` so the first screenful of each beat is the human story; technical cross-checks can stay but must not dominate.
6. Walkthrough: recut CLI tape first (`okf-bqaa-cli.mp4` + new poster). Caption = the four sentences above. Prior `okf-bqaa-e2e.mp4` stays collapsed, labelled prior fixture clip, not this run.
7. Collapsed extras:
   - **How this was built / IDs** — CLI commands, SHA triple, 180-event histogram, SDK PR 474, `Object.hasOwn` fail-closed, transcript / cast / gif links, live snapshot facts. This is where a reviewer verifies the run.
   - **What is real here, and what is not** — keep every honesty bullet from the current page (observe is live GCP from before the page was built; CLI is real stdlib; Catalog not written; germany SYNTHETIC; consume `04fa3d56` prior; receipt UNVERIFIABLE; browser same-origin only).
   - Run it locally.
8. Footer. `rfc/index.html` Prototype callout rewritten in why-language (2–4 sentences, question + payoff, not a feature list).

## Tape (recut, 20–40s, 1280×720 H.264)

Record from `/Users/haiyuancao/BigQuery-Agent-Analytics-SDK-okf-adapter` @ `476d37dc`. Stdlib, no GCP, nothing `--live`. Real `python3 examples/okf_bqaa_adapter/run.py`.

On-screen comments in **plain English** between commands. Beats on the tape match the page:

1. ASK — print the user question from the committed export (one line). Comment: the trap (legacy vs current).
2. OBSERVE — print session, 180 events, rank 1 title, excluded legacy title + reason, UNVERIFIABLE. Not 180 rows.
3. PUBLISH — run `python3 examples/okf_bqaa_adapter/run.py`, then show bundle titles (and optionally the active-customer-revenue frontmatter). Comment: 8 derived stubs; this is the handle a KC entry would expose; this CLI path did not write Catalog.
4. NEXT AGENT — `run.py --lookup 'okf:env-observe#674153c572f6'` → three-key JSON. Comment: **use Active-customer revenue, not legacy; the number is unproven.** Brief labelled junk-ref exit 2, then **hold the payoff comment as the last frames** so the poster is the lookup JSON + payoff, not FAIL_CLOSED, not empty header.

Assets: `cli/okf-bqaa-cli-transcript.txt`, `.cast` (asciinema v2, title names the why-story / live-adapter proof), `.gif` (agg), `okf-bqaa-cli.mp4` (H.264 1280×720 even dims, encoder comment `agg+ffmpeg`, not gif.ski), `okf-bqaa-cli-poster.png` = last-frame payoff.

## Honesty (must be true on the page)

- Browser never calls GCP.
- Observe input is the 180-row observe session, not consume, not germany.
- Adapt is the Python CLI, not `adapter.js`.
- Germany may remain only as SYNTHETIC hashing-only.
- Receipt is UNVERIFIABLE. Nothing ATTESTED.
- This CLI path did not write Knowledge Catalog. Do not fake a pin.
- Never emit `concept_version_id`, bundle paths, principal, SQL, parameter values, raw destination table names on agent-facing lookup payloads.
- Model is `gemini-3.8-flash`. Never `2.5`.

## Checks

Update `python3 rfc/demo/tools/check_cli_viewer.py`:

- Observe live.json session, event_count 180, context_ref, publication_id, model still hold.
- Transcript contains the ASK question, rank 1 `Active-customer revenue`, excluded `Customer revenue (legacy)`, `PUBLICATION_ID`, lookup JSON, payoff comment (`not legacy` / `unproven`), and labelled `FAIL_CLOSED`. Last-line / last-frame payoff: transcript must include the payoff comment **after** the junk-ref line (so the tape can end on payoff).
- `index.html` hero title is the locked question; hero subtitle contains the locked three-sentence payoff (legacy + unproven + next agent). Hero / masthead (html before `<main>`) does **not** contain the full 64-hex publication, `Object.hasOwn`, `okf-bqaa-adapter:v0` as a badge wall, or `180` as a hero badge. Those strings belong in the collapsed IDs / How this was built, walkthrough captions may mention 180 only as a secondary fact.
- Stepper titles: Ask, Observe, Publish, Next agent (`data-beat="1..4"` preserved).
- `poster="okf-bqaa-cli-poster.png"`; poster file exists; mp4 exists.
- Honesty: `index.html` + `app.js` still say derived/demo, observer-only, nothing attested, no Catalog write / “handle a KC entry would expose”, germany SYNTHETIC, consume `04fa3d56` only inside labelled prior, no `computed in-browser`, no `gemini-2.5`.
- Hero / live strip (pre-`<main>`) must not present `okf_rfc_consume_agent`, `04fa3d56`, `okf:env-demo#a25e1c0ccbca`, or `sess-4c1f9a2e7b3d`.
- Keep hermetic `Object.hasOwn` lookup tests (constructor / toString / `__proto__`) — they live in IDs, not the hero.
- Existing authored/derived vector checks still run as labelled extras.

## Inputs (committed, static) — reuse, do not re-export

Keep `live/observe/{live.json,live_identities.json,mapping.json,snapshot.json}`.
Replace tape assets (`cli/*`, `okf-bqaa-cli.mp4`, `okf-bqaa-cli-poster.png`).
Keep `okf-bqaa-e2e.mp4` labelled prior fixture clip.
Keep prior consume files and germany trace labelled as today.
`adapter.js` / `hash.js` stay for the labelled SYNTHETIC hashing check only.
