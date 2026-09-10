# Site navigation — plan

1. **Generator.** `tools/site_nav.mjs`: IA + page list, `render(pagePath)`, sync and `--check` modes, page-relative asset hrefs.
2. **Assets.** `assets/site-nav.css` (bar, folders, mobile collapse, no-JS fallback, print) and `assets/site-nav.js` (folder state, keyboard, toggle, outside click, aria-current reconcile).
3. **Migration (one-off, not committed).** Replace each page's old topbar block with the markers, add the two head tags, strip the page-local `.topbar/.brand/.nav-links/.site-topbar` rules (also from `rfc/demo/styles.css`, `rfc/full-demo/styles.css`, `rfc/styles.css`), then run the generator.
4. **Tests.** `tools/check_site_nav.mjs` (Playwright, desktop + mobile per page, `--shots` for screenshots); update `test_both_demos_carry_the_detailed_rfc_nav_item` to read the generated block; run `check_rfc_routes.mjs`, `rfc_word_count.mjs`, and the spike suite.
5. **Generators outside the repo.** `agent-analytics-research/usage-dashboard/collect_and_build.py` rewrites `research/usage/index.html` on every refresh: its template gets the same block and head tags so the next refresh does not revert the chrome. Guard: `node tools/site_nav.mjs --check`.
6. **Ship.** Docs beside the hub (`research/site-nav-{intent,spec,plan}.md`), branch `feat/site-nav-layout`, PR against `main`, vault note under `Ship/builds/`. Astra reviews on GitHub.

Follow-ups (not in this PR): move the brief publisher's two-link strip (`research/briefs/*.html`) onto the shared block; consider running `check_site_nav.mjs` from the pytest suite.
