# Spec — `rfc-exec-skim`: `/rfc/` as a five-minute decision brief

Source of truth for the slice: the joint EM recommendation of 2026-09-09 (Fable + Astra consults). Page: `rfc/index.html` (static, hand-authored; no generator). Companion: `rfc/styles.css`. Optional: the backlink label in `rfc/detailed-rfc/index.html`.

## 1. Copy-map of pinned strings (read before any edit; PR 64 lesson)

Every string below is asserted by a test in `rfc/spikes/bq-graph/tests/` and must survive byte-for-byte in `rfc/index.html` unless marked otherwise.

| # | Pinned by | String or rule | Where it lives after this slice |
|---|---|---|---|
| P1 | `test_fact_select_surfaces::test_no_surface_says_a_count_check_verifies_the_digest` | `match the rows and columns to their own digest, not the script’s` and `no live run has done this yet` | fact-data row inside the thresholds fold, verbatim paragraph |
| P2 | `…::test_the_readback_target_is_the_content_digest_not_the_script_digest` | `a digest of the rows and columns themselves` | same paragraph |
| P3 | `…::test_every_surface_says_synthetic_and_keeps_alder_unselected` | the word `synthetic` (any case); `Alder’s cohort has never been selected`; `not customer data` | same paragraph (also the Still-to-validate row repeats "Alder’s cohort has never been selected") |
| P4 | `…::test_no_current_tense_surface_still_says_the_version_is_unchosen` | none of the STALE patterns (`has no runner`, `no selected fact version`, `Not yet chosen`, `nobody has picked one`, `UNSELECTED / INCOMPLETE`, `checks the live tables against that digest`, …) | forbidden anywhere on the page |
| P5 | `…::test_reader_facing_prose_carries_no_digest_job_id_or_pr_number` | no hex run of 12+ characters outside `<a …>` tags and URLs; no `bqjob_`; no `FACTS_UNSELECTED`; no `PR <number>` | forbidden anywhere in prose |
| P6 | `…::test_the_readback_target…` | no `match it/them to that digest` | forbidden |
| P7 | `test_board_pack_links::test_the_baseline_card_is_one_of_them` | `href="spikes/bq-graph/evidence/sql-baseline/baseline.md"` | fact-data row and cost row in the fold; the Measured-retrieval evidence row |
| P8 | `…::test_the_landing_page_and_the_detailed_rfc_link_each_other` | `href="detailed-rfc/"` on the landing; `href="../"` and the generated nav item `<a href="/rfc/detailed-rfc/" aria-current="page">Detailed RFC</a>` on the detailed page | masthead kicker link; risks strip link; unchanged on the detailed page |
| P9 | `…::test_the_moved_pages_declare_their_new_canonical_addresses` | `<link rel="canonical" href="https://caohy1988.github.io/rfc/">`; `href="styles.css"` | head, unchanged |
| P10 | `…::test_the_landing_page_forwards_every_old_technical_bookmark_and_none_of_its_own` | the `var legacy = […]` list stays equal to (detailed ids − landing ids); `sep19-envelope` defined on the landing and absent from the list | head script unchanged; **every existing landing id kept** (see §2); new ids must not exist on the detailed page (`summary`, `decision`, `details`, `accept`, `phases`, `closing`, `baseline`, `motivation`, `architecture`, `repro`, `current-evidence`, `statemachine`, `runtime-guarantees`, `arch-crosswalk`, `baseline-body`, `repro-ask-later` are taken) |
| P11 | `…::test_every_pinned_blob_link_exists_at_its_revision` | at least one pinned GitHub blob link; each existing pinned link keeps its revision and path | the five existing links stay: graph-walk report, receipt report, catalog-chain summary, restricted-pass README anchor, Slice B run E |
| P12 | `…::test_every_relative_link_resolves_on_disk` | every relative href resolves; at least one relative href | `board-pack/intent-knowledge-publications.md`, `spikes/bq-graph/evidence/sql-baseline/baseline.md`, `detailed-rfc/`, `styles.css` |
| P13 | `rfc/tools/check_rfc_routes.mjs` (via `test_routes_in_a_real_browser`) | `/rfc/#sep19-envelope` stays on `/rfc/` and scrolls (the section is below the first screen); `/rfc/#story-title` stays | both ids kept |
| P14 | `test_rfc_word_ceilings` | folds-open count ≤ 1,800 | measured before merge |

Audited label: the masthead kicker `3–4 MIN READ` and the detailed page's backlink `Illustrative · 3–4 minutes.` are not test-pinned. Both change **only through this copy-map** to `5-MINUTE DECISION BRIEF` / `Illustrative · 5-minute decision brief.`

### Ids on the landing page (all kept)
`main`, `story-title`, `runtime-title`, `context-point`, `access-point`, `execution-point`, `later-questions`, `later-questions-title`, `sep19-envelope`, `sep19-envelope-title`, `technical-design-body`, `plot-caption`, `plot-arrowhead`, `plot-graph`, `plot-query`, `plot-context`, `plot-identity`, `plot-policy`, `plot-access`, `plot-declaration`, `plot-job`, `plot-outcome`, `plot-title-wide`, `plot-desc-wide`, `plot-title-narrow`, `plot-desc-narrow`, `design-context`, `design-access`, `design-execution`, `design-chain`, `design-evidence`, `ask-title`, plus the generated nav ids. New ids: `decision-request`, `decision-request-title`, `service-roles`, `evidence-status`, `evidence-status-title`, `thresholds-body`, `risk-strip`, `risk-strip-title`.

## 2. Required structure (top to bottom)

| # | Block | Content rule |
|---|---|---|
| 1 | Masthead kicker | `BIGQUERY / 5-MINUTE DECISION BRIEF / Detailed RFC →` (label change via this copy-map) |
| 2 | **Decision block** (`#decision-request`, before the hero) | eyebrow names *proposed* BigQuery Knowledge Publications; one-sentence problem; the proposal in two sentences (Knowledge Publications first, SQL first, receipt as follow-on, both proposals); **Decision requested** (owner + Knowledge Catalog counterpart to scope a managed Preview; one Finance retention pilot with agreed data and budget); **Status** (feasibility on invented data only, each run a different part, nothing committed); **Checkpoint 2026-09-19: continue, narrow or stop** |
| 3 | Hero (`#story-title`) | headline kept; one sentence of the 8:55 scene; reconciliation figure kept verbatim; near-miss paragraph kept |
| 4 | Four roles (`#service-roles`) | Open Knowledge Format · Knowledge Catalog · BigQuery Knowledge Publications **(proposed)** · BigQuery Agent Analytics **(observes use and does not grant access or certify results)**; the "especially strong when" sentence kept |
| 5 | Three cards (`#context-point`, `#access-point`, `#execution-point`) | headers become Finance's questions; eyebrow keeps `01 Replayable context` etc.; cells `Today · KC + OKF` vs `Proposed · Knowledge Publications`; two lines each; no per-card evidence notes (evidence lives once in block 7 and the technical fold) |
| 6 | Later questions (`#later-questions`) | one paragraph: the three records and the "only while retained and the reader may see it" condition |
| 7 | **Evidence** (`#evidence-status`) | exactly three rows, `Recorded feasibility` / `Measured retrieval` / `Still to validate`, each with a scope sentence; no "working" badge; the concurrency shortfall (under five seconds single, over at five concurrent) and the unmeasured full-path cost/time are **visible** here |
| 8 | Decision envelope (`#sep19-envelope`) | three visible lines (task; success rule; decision with SQL-must-justify-graph) + a fold "Proposed thresholds (none accepted)" holding the eight items; the fact-data paragraph verbatim (P1–P3, P7) |
| 9 | Technical-design fold | unchanged content; the fold stays closed by default |
| 10 | Punchline | kept |
| 11 | **Risks** (`#risk-strip`) | four rows: Catalog lag / stale pins; ordinary SQL may suffice; access inside graph queries unproven; a demonstration mistaken for readiness — each with its gate; link to the detailed phases/risks section |
| 12 | Asks (`#ask-title`) | product ask and customer ask kept; add the four **roles** (BigQuery owner, Knowledge Catalog counterpart, Finance pilot owner, BigQuery Agent Analytics integration counterpart), no names; staffing, budget, real-data selection pending |

## 3. Honesty beats (verbatim in meaning, each present on the page)

1. Invented data only (Alder, Acme, the fourteen-row fixture); Alder’s cohort has never been selected; not customer data.
2. Feasibility, not the feature: Knowledge Publications and the verified receipt are proposed; neither is committed; every threshold is proposed and none accepted.
3. Each run reached a different part; single identity; hand-pinned seeds; the graph-query run tried only the case expected to succeed.
4. Access inside graph queries is unproven (the restricted identity was denied on plain SQL only).
5. Fact rows pinned by a digest of the rows and columns themselves; no live run has read every table back and matched them.
6. Ordinary SQL under five seconds one request at a time and over it at five at once; full time from question to released number and cost per answered question not measured.
7. Replayable context does not promise identical LLM answers.
8. Checkpoint 2026-09-19 = continue, narrow or stop against thresholds the owner accepts; demonstrations are not pilot validation.
9. Knowledge Publications first, receipt as follow-on, SQL as the first engine; graph must justify its extra cost.
10. BigQuery Agent Analytics observes use; it does not grant access or certify results.

## 4. Acceptance gates (all hermetic)

| Gate | Tool | Threshold |
|---|---|---|
| G1 rendered words | `rfc/tools/rfc_word_count.mjs` (`rendered`) | ≤ 950 |
| G2 folds-open words | same (`open`) | ≤ 1,800 (existing `test_rfc_word_ceilings`) |
| G3 decision above the fold | new `rfc/tools/rfc_skim_check.mjs` | first 450 rendered words contain `proposed`, `invented`, `Knowledge Publications`, `pilot`, `2026-09-19` |
| G4 read time | same | rendered ÷ 230 ≤ 5.0 minutes |
| G5 pinned strings | `test_fact_select_surfaces`, `test_board_pack_links` | green |
| G6 routes | `rfc/tools/check_rfc_routes.mjs` | all routes behave (`#sep19-envelope`, `#story-title`, legacy fragments `#architecture`, `#current-evidence`, `#repro`, `#summary` forward) |
| G7 spike suite | `pytest` in `rfc/spikes/bq-graph` (Homebrew python3.13) | all passed |
| G8 no id added to or removed from the detailed page; no landing id removed | `_section_ids` in `test_board_pack_links` | green |
| G9 site nav | `node tools/site_nav.mjs --check` | in sync (the generated block is not touched) |

G1, G3 and G4 are gated by the new `tests/test_rfc_exec_skim.py`, which skips (not passes) when node or Playwright is unavailable, like the ceiling test.

## 5. Out of scope

No `/rfc/exec/` route; no receipt-first reopen; no live cloud run; no detailed-RFC body change; no cut of a scope clause to hit 850 rendered words.
