# Spec — `/rfc/e2e/`

Companion to `intent.md`. Source of truth for every claim: `../spikes/bq-graph/evidence/report-publish-connected.md` and its run directory `evidence/publish-connected/kp-20260915t082018z-0387/`.

## 1. Files

| Path | What |
|---|---|
| `rfc/e2e/index.html` | The page. Static, with one small inline script (chapter seek and highlight) that degrades to static text. |
| `rfc/e2e/styles.css` | Page styles. Uses the `/rfc/demo/` tokens and fonts (Space Grotesk, Source Serif 4, IBM Plex Mono); scoped so the shared site bar is untouched. |
| `rfc/e2e/okf-publish-connected.en.vtt` | Caption track for the tape: human setup, stage labels, plain verdict. |
| `rfc/e2e/okf-publish-connected-poster.png` | Poster: frame at 0:01, with the question on screen. |
| `rfc/e2e/{intent,spec,plan}.md` | SDLC docs. |

## 2. Asset strategy

- **Tape.** `<video src="../demo/okf-publish-connected.mp4">` points at the one committed copy, the bytes reviewed and merged in PR #78. Copying 4.3 MB would create a second copy of the evidence that could drift. The page labels the source ("same recording as `/rfc/demo/`").
- **Captions and poster.** New files live under `rfc/e2e/`, so the page owns its narrative layer.
- **Links.** The report, raw transcript, cast and run JSON use relative links into `../spikes/bq-graph/evidence/` and `../demo/publish-connected/`.

## 3. Page structure (in order)

### 3.1 Above the fold (short scroll)

- **Kicker.** "End-to-end demo · one live run", with links back to the RFC and the Detailed RFC.
- **H1.** Plain-English claim of the path.
- **One-sentence problem.** An agent can find the right definition and still report a number nobody can defend.
- **Status badges.** Proposed feature · spike code · synthetic data · one live run · live GCP APIs.
- **Four-card "In 30 seconds" grid.**
  1. What breaks today.
  2. **Open Knowledge Format + Knowledge Catalog:** write it down, make it findable. Catalog is the directory, not the authority.
  3. **BigQuery Knowledge Publish:** make one version official. Readback, `READY`, one-step switch of the current version. BigQuery serves.
  4. **What the live run proved:** "One live run published in BigQuery, then the agent discovered, used, verified, and was revoked — successfully."
- **Still-open teaser plus the "Watch the 93-second tape" link.**

### 3.2 "Why all three" thesis (`#why`)

A table with four rows (paths) and three columns (RFC outcomes), plus a "Who says which version is current?" column.

| Path | Which version? (replayable context) | Who allowed it? (explainable access) | Did the query match? (verifiable execution) | Current version decided by |
|---|---|---|---|---|
| Ungoverned agent | Whatever it finds or writes | Whatever credential it runs with | Nothing checks | Nobody |
| OKF only | Files exist; nothing serves a fixed version | No access path | Declared, never checked | A file copy |
| Knowledge Catalog only | Similarity ranks candidates; no pin to the linked rule | Discovery alone does not explain the retrieval path | Finding the declaration does not prove it ran | A Catalog entry, which can drift from what is served |
| OKF + Knowledge Catalog + BigQuery Knowledge Publish | Pinned `READY` publication | Restricted requester checked on every step; revocation holds | Receipt ties job ↔ context ↔ result | BigQuery (serving authority) |

The last row is marked "shown once, on synthetic data". A one-line role statement follows the table: OKF authors, Knowledge Catalog discovers, BigQuery publishes and serves.

Wording is aligned with `/rfc/` ("Similarity ranks candidates; it does not pin the linked rule"; "discovery alone does not explain the agent's retrieval path"; "Finding the computation declaration does not prove the calculation ran") and with Detailed RFC §04 Authority.

### 3.3 The path, step by step (`#path`)

The lede bridges to the `/rfc/` landing:

- the 118% vs 96% retention slide is illustrative;
- this run puts the same checks (definition with its rule, access, receipt) live on Acme gross margin, the documented publish-connected path (intent, "Scenario").

Then seven numbered steps. Each has:

- a **plane tag**: A (OKF + Knowledge Catalog), B (BigQuery Knowledge Publish) or Consume;
- an **RFC outcome tag**;
- one plain sentence of what happens;
- one "In the live run" line in plain words, with numbers only where they help;
- a **tape timestamp button** that seeks the video.

| # | Step | Plane | Outcome | Tape |
|---|---|---|---|---|
| 1 | Author in Open Knowledge Format: Gross Margin metric (full cost, explicitly not the legacy formula), the policies it cites, the approved SQL calculation | A | replayable context | 0:04 |
| 2 | Publish in BigQuery: write rows, read every row back, `READY`, switch current version in one step | B | replayable context | 0:11 / 0:22 / 0:27 |
| 3 | Discover in Knowledge Catalog: entry written after the switch, pointing at that publication; the agent's restricted account reads it itself | A | replayable context | 0:30 / 0:40 |
| 4 | Agent retrieves under its own access: pinned publication, definition + linked rules + approved calculation | Consume | explainable access | 0:40 |
| 5 | Receipt verifies before release: $400.00 released; swapped query, hidden rule, unreadable output refused | Consume | verifiable execution | 0:49 / 0:58 |
| 6 | Revoke: fresh request stops at Catalog; cached shortcut and stored receipt refused | Consume | explainable access | 1:10 / 1:19 |
| 7 | Clean up; the agent gets only the answer and verdicts (no ids, SQL, accounts) | Consume | — | 1:24 / 1:30 |

### 3.4 Tape (`#tape`)

- **Setup sentence above the video.**
- **Video:** `controls`, `preload="metadata"`, poster, and `<track kind="captions" default>`.
- **Chapter list** (buttons → `currentTime`; the active chapter is highlighted on `timeupdate`).
- **Plain verdict line below.**
- **Provenance note:** a real terminal recording of the live run; waits longer than 3 s are compressed (the run took about 12½ minutes).

### 3.5 What we proved / still open (`#proved`)

Two columns, plain English. Still open:

- the same access checks inside BigQuery Graph queries;
- an independent attester;
- repeated runs, cost and latency;
- real customer data;
- a new knowledge revision through publish;
- the full cross-service consistency protocol.

### 3.6 Evidence (`<details id="evidence">`, closed)

- **Run:** run id, verdict, project, window (UTC), model, runner and CLI versions.
- **Plane B:** `READY` publication id, row counts, source pin, 19 author jobs `BOUND`, merge job id, state trace, dataset (deleted).
- **Plane A:** Catalog entry name, readback `OK`, consumed-publication check `MATCH`.
- **Consume:** consume run id; the five cases and their decisions; access checks after revocation; receipt job ids; receipt `VERIFIED`.
- **Technical residuals** (verbatim-level precision):
  - relational fallback, not GQL;
  - SDK's own verifier with a requester-held key;
  - content-addressed id deployed fresh, not a new revision;
  - simplified §05 (no `sync_id` / `deployment_heads` / `*_current` / lag SLO);
  - harness-granted Catalog viewer and dataset reads;
  - injected denied-intermediate seed on the `_rls` copy;
  - n = 1, synthetic, no cost or latency benchmark.
- **Links:** report, run JSON, publish journal, transcript, cast, code repo, earlier runs.

## 4. Language rules

- **Full product names on first use in every card:** Open Knowledge Format, Knowledge Catalog, BigQuery, BigQuery Knowledge Publish.
- **Terms of art defined in place:**
  - "publication" (a fixed, read-only version of the knowledge in BigQuery);
  - "current version pointer" (the head);
  - "receipt" (a record tying the BigQuery job, the query, the context used and the result).
- **No job ids, hashes, state names or case slugs above the Evidence fold.** `READY` may appear once as a labelled status word.
- **Honesty wording:** "proposed", "spike code", "synthetic", "one run". Never "ready", "production" or "proven" without "once" / "on synthetic data".

## 5. Navigation and links

- **`tools/site_nav.mjs`:** `PAGES["/rfc/e2e/"] = "rfc/e2e/index.html"`, `CURRENT["/rfc/e2e/"] = "/rfc/"`, and add `/rfc/e2e/` to `STICKY`.
- **`/rfc/` landing:**
  - The "Recorded feasibility" row (rendered) names the publish-then-consume run and links `e2e/` ("the demo").
  - The "three as one path" bullet's tape link becomes `e2e/`.
  - "The bar, shown once." links `e2e/` alongside the report.
- **`/rfc/demo/#connected-e2e`:** a one-line pointer to `../e2e/` as the canonical end-to-end demo.

## 6. Gates (run before PR)

| Gate | Command | Pass |
|---|---|---|
| Nav in sync | `node tools/site_nav.mjs --check` | all pages in sync |
| Nav browser check | `node tools/check_site_nav.mjs` | all checks pass, including `/rfc/e2e/` desktop, mobile (no horizontal overflow), and short landscape sticky |
| Route check | `node rfc/tools/check_rfc_routes.mjs` | pass |
| Landing budget | `node rfc/tools/rfc_skim_check.mjs rfc/index.html` + `rfc_word_count.mjs rfc/index.html` | rendered ≤ 950, open ≤ 1800 |
| E2E page skim | `node rfc/tools/rfc_skim_check.mjs rfc/e2e/index.html --max-rendered 1150 --window 350 --tokens "Open Knowledge Format,Knowledge Catalog,BigQuery Knowledge Publish,synthetic,still open"` | ok (≤ 5 min at 230 wpm; five tokens in the first 350 rendered words, which include the ~25 nav-bar words and end at the still-open teaser) |
| Links | every relative `href`/`src` on the page resolves to a file in the repo | 0 missing |
| Captions | VTT parses (`WEBVTT` header, monotonic cues ≤ 92.75 s); the browser loads the track | ok |
| Honesty grep | the rendered page contains none of "production-ready", "readiness achieved", "hermetic" presented as live | 0 hits |
