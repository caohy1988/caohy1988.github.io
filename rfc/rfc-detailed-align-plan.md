# Plan — `rfc-detailed-align`

1. **Copy-map first** (spec §1): footer and recorded-examples sentences, hrefs, ids, Prototype callouts. No id is added or removed, so the landing's legacy forwarder list stays valid without touching `rfc/index.html`.
2. **Masthead**: thesis sentence (A1); decision block after the status note (A2); link-row label (A3); service roles (A4). Styles: `.decision-brief` (three-column definition list, one column under 760px).
3. **Summary**: naming bridge (A5) and the three-row evidence status (A6) between the lede and the guarantees table. Styles: `.evidence-status`.
4. **Closing**: blockquote, pilot paragraph, two asks and four roles (A7).
5. **Gate tooling**: `rfc/tools/rfc_skim_check.mjs` gains `--window`, `--tokens`, `--max-rendered`, `--max-minutes` flags (defaults keep the landing gate identical); new `tests/test_rfc_detailed_align.py` (G2, G3).
6. **Verify**: word counter; skim check for both pages; routes; site-nav sync and browser check; demo checkers; targeted pytest (links, fact-select, ceilings, exec-skim, detailed-align); full suite; screenshots of the detailed first screen at 1280 and 375.
7. **Ship**: results below; push `feat/rfc-detailed-align`; PR against `main`; vault note under `Ship/rfc/`; Astra review. No merge.

## Result (filled in at delivery)

| Measure | Before | After |
|---|---|---|
| detailed rendered / folds-open words | 5,247 / 6,958 | 5,643 / 7,354 (ceiling 7,500) |
| first 800 rendered words contain the five tokens | no (`Knowledge Publications`, `2026-09-19` absent) | yes |
| landing rendered / folds-open | 943 / 1,706 | unchanged |

Checks at delivery: `check_rfc_routes.mjs` all routes behave; `site_nav.mjs --check` 13 pages in sync; `check_site_nav.mjs` all pages pass; link + fact-select + ceiling + exec-skim + detailed-align tests 37 passed; full spike suite 1,017 passed. `check_cli_viewer.py` shows the three known baseline Prototype-callout FAILs; `check_full_demo.py` shows five audit-register FAILs (INV-1, SCAN_FILES, INV-6, INV-5) that are byte-identical on main at 3855b91 and name no detailed-page text, so they are pre-existing and out of this slice.
