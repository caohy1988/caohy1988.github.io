# Intent — live GCP full demo page (`/rfc/demo/`)

Status: accepted from Haiyuan (2026-09-02): "update the full demo page". Not a badge-only patch.

## What

Every beat on https://caohy1988.github.io/rfc/demo/ shows the live GCP run that already happened:

- Dataset `test-project-0728-467323.okf_rfc_demo.agent_events` (US). Not `adk_logs`.
- Agent `okf_rfc_consume_agent` on `gemini-3.8-flash` (Vertex location `global`).
- Session `04fa3d56-f2f1-413e-8c2b-ec116835af84`, trace `0294f653a4f141ae960865e438538d2e`.
- One tool, `lookup_okf_context`, called with `context_ref=okf:env-demo#a25e1c0ccbca` only.
- Knowledge Catalog entry `projects/test-project-0728-467323/locations/us-central1/entryGroups/okf-rfc-demo/entries/okf-derived-germany`.

The 14 real BQAA rows are committed as `live/agent_events.json` and are the primary trace on the page. Console deep links go to the BigQuery table and the Dataplex search for the entry.

## Why

The previous page was fixture-only ("no live GCP"). Leadership needs to see that the observer → derived → project → consume path ran against real BigQuery Agent Analytics, a real Dataplex entry, and a real Gemini call, and that the agent still only saw `context_ref`.

## Constraints (do not break)

- BQAA is observer-only. One-way adapter. Authored `cymbal-finance-core` fixture is never read or written by the adapter.
- Everything derived is labelled derived/demo. Nothing is claimed ATTESTED. The live run minted no receipt; the model's own "verified" wording is shown verbatim and flagged.
- Agent-facing payloads never carry `concept_version_id`, paths, principal, SQL. Asserted at render time against the live tool args and result.
- Model stays `gemini-3.8-flash`. Four beats stay Observe → Adapt → Project → Consume.
- Static Pages. Snapshots + console deep links. The browser never calls BigQuery, Dataplex or a model.
- `okf-bqaa-e2e.mp4` is a prior fixture clip. Live evidence is shown first; the clip is labelled as not live-GCP proof.

## Out of scope

- Re-running the agent, new BigQuery DML, new Catalog writes, attester work.
- Changing OKF v0.2 core, PROFILE.md hashing, or the derived vector tests.
- Other repos.

## Success

A visitor sees the live IDs and console links before anything else, walks the four beats and finds the live session in each, the derived identity chain still verifies in-browser, and `python3 tools/check_live_trace.py` plus the existing derived vector checks exit 0. PR open against `main`, not merged.
