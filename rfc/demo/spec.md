# Spec — live GCP full demo page

## Inputs (committed, static)

| File | Role |
|---|---|
| `live/live.json` | Run metadata: project, dataset, table, agent, model, session_id, trace_id, context_ref, publication_id, KC entry, console URLs, `ran_at`. |
| `live/agent_events.json` | 14 real rows exported from `okf_rfc_demo.agent_events` for the session. `attributes` and `content` are JSON strings (BQ export shape). |
| `live/run_okf_agent.py` | The ADK agent that produced the rows. No secrets; project id via env with default. |
| `traces/bqaa-germany.json` | Synthetic fixture trace. Still the adapter input for the derived bundle. Secondary on the page. |
| `derived/`, `fixture/` | Unchanged. |

## Identity binding

- Derived `publication_id` = `sha256:a25e1c0ccbcad270bf9e3b7a8f792167795381b6880bdc8a1ccde8df40ea52c5` (pinned, recomputed in-browser).
- Live `context_ref` = `okf:env-demo#a25e1c0ccbca` = `okf:env-demo#` + first 12 hex of the derived publication.
- Live `TOOL_COMPLETED.content.result.publication_id` must equal the derived publication. The page checks this at render time and shows ✓/✕.
- The fixture's `demo_envelope_id` (`env-a0578902fdf3dead`) is a different demo handle and is no longer used on the consume beat. It stays in `derived/identities.json` untouched.

## Page structure (top to bottom)

1. Masthead. Kicker: live GCP run. Badges: derived/demo; authored untouched; ADK `gemini-3.8-flash` live; live BQAA rows snapshot; browser makes no GCP calls.
2. Banner: derived/demo, observer-only.
3. **Live run strip** (new, before the identity strip): dataset, agent, model, session_id, trace_id, context_ref, KC entry, `ran_at`, and two console links (BigQuery table, Dataplex search).
4. Identity strip: unchanged (authored pinned; derived recomputed).
5. Stepper + stage, four beats.
6. Walkthrough: live-run summary card first (IDs + links), then the old mp4 labelled "prior fixture clip, recorded before the live run, not live-GCP proof".
7. "What is real here" rewritten. "Run it locally" adds the live check command.
8. Footer.

## Beats

### 1 Observe (live primary)
- Pane A: `agent_events · 04fa3d56…` list of the 14 live rows. Each row: timestamp, event_type, summary, click for the raw row (parsed `attributes`/`content`). TOOL_STARTING / TOOL_COMPLETED summaries show `context_ref`.
- Pane B facts: dataset (full path + location), agent, model, session_id, trace_id, event_type histogram, tool, `context_ref`, `ran_at`. Link to BQ console.
- Never-emit scan over the live tool payloads (`TOOL_STARTING.content.args`, `TOOL_COMPLETED.content.result`) and over every parsed row key: `concept_version_id`, `bundle_path`, `source_path`, `principal`, `query_text`, `sql`, `parameter_values`, `destination_table` absent. `user_id` is a BQAA row column and is the demo pseudonym `leadership-demo`; it is not on the tool payload. Say so.
- Collapsed `<details>`: the synthetic fixture trace (adapter input), with the previous event list and scan, labelled synthetic.

### 2 Adapt
- Unchanged mechanics. Lede and flow box say: adapter input is the fixture observation; the live session consumed the resulting publication. The live observation is the proof, the fixture is the adapter input.
- New checklist rows: live tool result `publication_id` == derived publication (✓/✕); live `context_ref` == `okf:env-demo#` + prefix12(derived publication) (✓/✕).

### 3 Project
- Catalog pane: first a **live entry card** for `okf-derived-germany` (entry group, location, full resource name, Dataplex link), then the in-browser derived projection cards labelled "derived view · in-browser".
- BigQuery pane: first a **live table card** for `okf_rfc_demo.agent_events` (location US, row count for the session, console link), then the in-browser RFC projection tables labelled "derived view · RFC projection shape · not a live table".
- Seam note unchanged.

### 4 Consume (live)
- Transcript from live rows: user text (USER_MESSAGE_RECEIVED), model call (LLM_RESPONSE "call: lookup_okf_context" + TOOL_STARTING args), tool result (TOOL_COMPLETED result, real JSON), model final text (AGENT_RESPONSE, parsed from `text: '…'`). Token usage from LLM_RESPONSE `usage`.
- Header: agent name, session, model badge `gemini-3.8-flash`, "live · Vertex global".
- Side tiles: agent construction (snippet mirroring `live/run_okf_agent.py`, link to file); never-emit assertion on live args + result; **no receipt** tile: this run minted no receipt, nothing is ATTESTED, model wording "verified" is the model's own and overstates; the Phase 0 golden `UNVERIFIABLE` specimen remains the only receipt (collapsed).
- Collapsed `<details>`: prior fixture replay transcript, labelled synthetic and superseded.

## Checks

- `node tools/check-authored-identities.mjs`, `node tools/build-derived.mjs` (no diff), `python3 tools/derived_vectors.py` still exit 0.
- New `python3 tools/check_live_trace.py`: parses `live/agent_events.json` and `live/live.json`; asserts all rows have session `04fa3d56-f2f1-413e-8c2b-ec116835af84` and trace `0294f653a4f141ae960865e438538d2e`; at least one TOOL_COMPLETED with `content.result.context_ref == okf:env-demo#a25e1c0ccbca`; TOOL_STARTING args carry the same `context_ref`; an AGENT_RESPONSE exists; LLM_REQUEST model is `gemini-3.8-flash`; tool payload keys ∩ never-emit = ∅; tool result `publication_id` == `derived/identities.json` publication_id; `live.json` fields agree. Exit 0 on pass.

## Non-goals

No browser fetches to GCP. No new BQ/Catalog writes. No ATTESTED claim. No change to hashing or the fixture.
