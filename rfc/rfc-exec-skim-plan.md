# Plan — `rfc-exec-skim`

1. **Copy-map first** (spec §1): list every test-pinned string and id; confirm the fact-data paragraph moves into the thresholds fold verbatim.
2. **Rewrite `rfc/index.html`** in the spec §2 order: decision block, hero (one-sentence scene), four roles, three question cards, later-questions paragraph, three evidence rows, three-line envelope + thresholds fold, technical-design fold (unchanged), punchline, risks strip, asks with four roles. Keep every id; add only the new ids listed in the spec.
3. **Styles** in `rfc/styles.css`: `.decision`, `.roles`, `.evidence`, `.thresholds` (same open-body pattern as the technical fold so print shows it), `.risks`, `.ask-roles`; mobile and print rules.
4. **Detailed backlink label** in `rfc/detailed-rfc/index.html`: `Illustrative · 3–4 minutes.` → `Illustrative · 5-minute decision brief.` (label only; href unchanged).
5. **Gate tooling**: `rfc/tools/rfc_skim_check.mjs` (rendered count, first-450-words tokens, minutes) and `rfc/spikes/bq-graph/tests/test_rfc_exec_skim.py` wrapping it.
6. **Verify**: word counter; skim check; `check_rfc_routes.mjs`; `tools/site_nav.mjs --check`; `tools/check_site_nav.mjs` (the bar is untouched but the page changed); pytest link + fact-select + ceilings + skim tests; full spike suite; desktop and mobile screenshots of the first screen.
7. **Ship**: record the measured counts in this plan; push `feat/rfc-exec-skim`; PR against `main`; vault note under `Ship/rfc/`; Astra review. No merge.

## Result (filled in at delivery)

| Measure | Before | After |
|---|---|---|
| rendered words | 1,117 | _tbd_ |
| folds-open words | 1,670 | _tbd_ |
| first 450 words contain the five tokens | no (`2026-09-19` and `pilot` absent above the fold) | _tbd_ |
| read time at 230 wpm | 4.9 min | _tbd_ |
