# Spec — `rfc-detailed-align`: the detailed RFC agrees with the decision brief

Page: `rfc/detailed-rfc/index.html` (static, hand-authored). Source of tone and structure: `rfc/index.html` after PR 66. `rfc/index.html` is not edited in this slice.

## 1. Copy-map of pinned strings and structure (read before any edit; PR 64 / PR 66 lesson)

| # | Pinned by | String or rule | Where it lives after this slice |
|---|---|---|---|
| D1 | `test_fact_select_surfaces::test_no_current_tense_surface_still_says_the_version_is_unchosen` | the footer sentence `Consolidated 2026-08-30 · evidence language updated 2026-09-09: the ordinary-SQL comparison’s fact-data version is a synthetic fixture, its consumer cells have a hermetic-only runner, never run live, customer (Alder) data remains unselected, and every threshold remains proposed · Prepared with Claude` — the test strips two historical clauses by exact text before scanning for stale patterns, so the footer stays byte-identical | footer, unchanged |
| D2 | `…::test_the_three_summaries_astra_named_now_say_synthetic_selected_and_alder_unselected` | `request-to-consumer cells have a hermetic-only runner, never run live (their fact data is a selected synthetic fixture, not customer data; the Alder cohort stays unselected)` | recorded-examples note (`#current-evidence`, Access and benchmarks), unchanged |
| D3 | `…::test_every_surface_says_synthetic_and_keeps_alder_unselected` | `synthetic`; `not customer data`; `customer (Alder) data remains unselected` | D1 and D2 carry them; the new evidence rows say "synthetic fact rows" and "the Alder cohort stays unselected" |
| D4 | `…::test_no_current_tense_surface…` (STALE list) | none of `has no runner` (without "yet"), `no selected fact version`, `no selected fact-data version` outside the stripped footer clauses, `Not yet chosen`, `nobody has picked one`, `UNSELECTED / INCOMPLETE`, `checks the live tables against that digest`, `match it/them to that digest` | forbidden in any new text |
| D5 | `test_board_pack_links::test_the_landing_page_and_the_detailed_rfc_link_each_other` | `href="../"` on the detailed page; the generated nav item `<a href="/rfc/detailed-rfc/" aria-current="page">Detailed RFC</a>`; `href="detailed-rfc/"` on the landing | masthead link row (label becomes "5-minute decision brief →"); nav block untouched; landing untouched |
| D6 | `…::test_the_moved_pages_declare_their_new_canonical_addresses` | `<link rel="canonical" href="https://caohy1988.github.io/rfc/detailed-rfc/">` | head, unchanged |
| D7 | `…::test_every_relative_link_resolves_on_disk` / `…::test_every_pinned_blob_link_exists_at_its_revision` | every relative href resolves; every pinned GitHub blob link keeps its revision and path | existing links untouched; the new evidence row links `../spikes/bq-graph/evidence/sql-baseline/baseline.md` (exists) |
| D8 | `…::test_the_landing_page_forwards_every_old_technical_bookmark_and_none_of_its_own` + `rfc/tools/check_rfc_routes.mjs` | the detailed page's set of ids is unchanged (`summary`, `runtime-guarantees`, `motivation`, `architecture`, `arch-crosswalk`, `decision`, `baseline`, `baseline-body`, `statemachine`, `details`, `repro`, `repro-ask-later`, `accept`, `phases`, `current-evidence`, `closing`, diagram ids); `/rfc/#architecture`, `#repro`, `#current-evidence`, `#summary` forward and scroll | **no id added or removed**; new blocks carry classes only |
| D9 | `rfc/demo/tools/check_cli_viewer.py`, `rfc/full-demo/tools/check_full_demo.py` | the Prototype callout (locked question, "legacy", "unproven", `href="../demo/"`, 2–6 sentences) and `href="../full-demo/"` | untouched |
| D10 | `test_rfc_word_ceilings` | detailed folds-open ≤ 7,500; landing ≤ 1,800 | measured before merge (baseline 6,958) |
| D11 | `tests/test_rfc_exec_skim.py` | landing rendered ≤ 950, tokens, minutes | landing untouched |

Data attributes `data-rfc-skim` on new masthead/summary blocks follow the existing skim-scan convention (comment above the header); no test reads them.

## 2. Required alignments

| # | Block | Change |
|---|---|---|
| A1 | Masthead thesis | "The proposed BigQuery runtime would turn…" → "Proposed BigQuery Knowledge Publications would turn the OKF graph into replayable context for agents—with explainable access—and a later verified receipt would add evidence that the declared computation ran." (the brief's former punchline) |
| A2 | Masthead **decision block** (new, class `decision-brief`, after the status note) | eyebrow "Decision brief · proposed BigQuery Knowledge Publications · nothing committed"; Decision requested (BigQuery owner + Knowledge Catalog counterpart to scope a managed Preview, SQL first, receipt follow-on; one Finance retention pilot with agreed data and budget); Status (feasibility on invented data only, each recorded run a different part, access inside graph queries unproven, nothing committed); Checkpoint 2026-09-19 (continue, narrow or stop against thresholds the owner has accepted; every threshold proposed, none accepted); one sentence saying this page is the engineering companion of the 5-minute decision brief |
| A3 | Masthead link row | label "5-minute decision brief →" (href `../` unchanged); span "The pack says 118%. Retention is 96%. Illustrative scenario, invented company and numbers." |
| A4 | Service roles (`.credo`) | "BigQuery runtime · proposed" → "BigQuery Knowledge Publications · proposed — would serve the approved version and linked rules under current access; later, check calculation evidence"; "Agent Analytics — observes that use" → "BigQuery Agent Analytics — observes use; does not grant access or certify results" |
| A5 | Summary naming bridge (new paragraph after the lede) | this page's "BigQuery runtime" = the brief's BigQuery Knowledge Publications (proposed): managed, versioned retrieval, SQL first, verified receipt as the follow-on; neither committed |
| A6 | Summary **evidence status** (new block, class `evidence-status`) | three rows Recorded feasibility / Measured retrieval / Still to validate, each with a scope sentence; the concurrency shortfall (under five seconds single-request, over at five concurrent) and the unmeasured full-path time and cost are **visible** here; links to `#current-evidence` and the SQL comparison; no "working" badge |
| A7 | Closing | blockquote takes the A1 sentence; "One pilot" paragraph states the checkpoint outcome as continue, narrow or stop against thresholds the owner has accepted; new "Two asks" sentence (product ask to BigQuery; pilot ask to a Finance owner) and the four requested roles with no names: BigQuery owner · Knowledge Catalog counterpart · Finance pilot owner · BigQuery Agent Analytics integration counterpart; staffing, budget and real data pending |
| A8 | Everything else | unchanged: architecture, six agreements, state machine, design folds (including the BQAA seam fold, which already says BQAA neither grants access nor upgrades an unproven verdict), reproducibility, acceptance, phases, risk table, recorded-examples note, Prototype callouts, diagrams, footer |

## 3. Honesty beats (each present on the page, verbatim where pinned)

Invented data only; feasibility, not the feature; each run reached a different part; single identity, hand-pinned seeds, expected-success graph run; access inside graph queries unproven; fact rows are a synthetic fixture pinned by digest with no live read-back (D2 wording unchanged); ordinary SQL under five seconds single-request and over at five concurrent; full-path time and cost unmeasured; the graph benchmark unfinished; every threshold proposed, none accepted; Knowledge Publications first, receipt as the follow-on, SQL as the first engine; checkpoint 2026-09-19 = continue, narrow or stop; BigQuery Agent Analytics observes use, does not grant access or certify results.

## 4. Acceptance gates (hermetic)

| Gate | Tool | Threshold |
|---|---|---|
| G1 folds-open words | `rfc/tools/rfc_word_count.mjs` | detailed ≤ 7,500; landing ≤ 1,800 (unchanged) |
| G2 first-screen tokens | `rfc/tools/rfc_skim_check.mjs --window 800 --tokens …` (tool gains flags; landing defaults unchanged) | first 800 rendered words contain `proposed`, `invented`, `Knowledge Publications`, `BigQuery Agent Analytics`, `2026-09-19` (case-insensitive) |
| G3 cross-links | new `tests/test_rfc_detailed_align.py` | detailed has `href="../"` with the text "5-minute decision brief"; landing has `href="detailed-rfc/"` |
| G4 pins and ids | `test_fact_select_surfaces`, `test_board_pack_links` | green; detailed id set unchanged |
| G5 routes / nav | `rfc/tools/check_rfc_routes.mjs`; `node tools/site_nav.mjs --check`; `node tools/check_site_nav.mjs` | green |
| G6 demo checkers | `rfc/demo/tools/check_cli_viewer.py` (three known baseline FAILs only), `rfc/full-demo/tools/check_full_demo.py` | no new failure |
| G7 spike suite | `pytest` in `rfc/spikes/bq-graph` (Homebrew python3.13) | all passed |

## 5. Out of scope

No `/rfc/exec/`; no receipt-first reopen; no live cloud run; no landing edit; no rendered ceiling for the detailed page; no rename of "BigQuery runtime" through the technical sections.
