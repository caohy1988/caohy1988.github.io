# Walkthrough capture plan (live page)

The `okf-bqaa-e2e.mp4` currently embedded on `/rfc/demo/` is a **prior
fixture clip, recorded before the live run, not live-GCP proof**. This file
lists the four beats to capture once a recording of the live page is made.
Do not replace the clip until every beat below is shown against the committed
`live/` snapshot.

Run: `okf_rfc_consume_agent` on `gemini-3.8-flash` (Vertex `global`), session
`04fa3d56-f2f1-413e-8c2b-ec116835af84`, dataset
`test-project-0728-467323.okf_rfc_demo.agent_events`, Knowledge Catalog entry
`okf-derived-germany`. Label throughout: derived / demo, observer-only, not
ATTESTED.

## Before recording

- Serve from the repo root: `python3 -m http.server 8000`, open
  `http://localhost:8000/rfc/demo/`.
- `python3 rfc/demo/tools/check_live_trace.py` exits 0.
- `python3 rfc/demo/tools/derived_vectors.py` exits 0.
- Live strip reads "snapshot verified in-browser ✓ · 14 rows".
- Identity strip reads "JS = pinned = Python ✓ · distinct from authored".

## Beat 1 · Observe

- Show the live strip: dataset, agent, model chip `gemini-3.8-flash`, session
  id, full `ran_at`.
- Open the BigQuery console link; show `okf_rfc_demo.agent_events` filtered
  to the session id; return to the page.
- Show the 14 committed rows and the event-type histogram.
- Show the never-emit scan: every key absent across all rows.

## Beat 2 · Adapt

- Show the synthetic adapter input (`traces/bqaa-germany.json`), labelled
  synthetic.
- Show the derived bundle and the derived triple recomputed in-browser.
- Open the inspector; every stub starts "Derived from BQAA observation, not
  authored."

## Beat 3 · Project

- Open the Dataplex console link; show entry `okf-derived-germany` in group
  `okf-rfc-demo`; return to the page.
- Show the Catalog pane and the BigQuery pane side by side; seam note reads
  "same publication on both stores ✓".
- Point at `context_ref = okf:env-demo#a25e1c0ccbca` and the matching
  `publication_id`.

## Beat 4 · Consume

- Show the live transcript: user question, `function_call` with
  `{context_ref}` only, `TOOL_COMPLETED` result, final answer citing the
  `context_ref`.
- Show the model badge `gemini-3.8-flash` and the `LLM_RESPONSE` token
  usage on each model turn.
- Show the assertion tile `keys ∩ never-emit = ∅ ✓`.
- Show the receipt tile "NO RECEIPT · nothing executed, nothing attested",
  then the collapsed fixture replay beneath it, labelled as a replay.

## After recording

- Save as `rfc/demo/okf-bqaa-live.mp4` (new name; keep the old fixture clip
  name distinct).
- Update the `<video>` source and the label in `index.html`, and the mp4 row
  in `README.md`.
