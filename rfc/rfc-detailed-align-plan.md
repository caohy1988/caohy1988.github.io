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
| detailed rendered / folds-open words | 5,247 / 6,958 | _tbd_ |
| first 800 rendered words contain the five tokens | no (`Knowledge Publications`, `2026-09-19` absent) | _tbd_ |
| landing rendered / folds-open | 943 / 1,706 | unchanged |
