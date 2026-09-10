# Site navigation — spec

## Information architecture

| Top level | Target | Folder items |
|---|---|---|
| Research | `/research/` | — |
| BQAA | `/research/stories/` | — |
| BigQuery ▾ | folder | Conversational Analytics `/research/conversational-analytics/` · BQ ML / AI Ops `/research/bqml-ai-operators/` · BQ Graph `/research/bigquery-graph/` · BQ Lakehouse `/research/bigquery-lakehouse/` · BQ Search `/research/bigquery-search/` |
| Usage | `/research/usage/` | — |
| Builds ▾ | folder | RFC `/rfc/` · Detailed RFC `/rfc/detailed-rfc/` · EvalBench `/evalbench/` |

Brand `HC / FIELD BRIEF` links to `/research/`. "CA in BigQuery" is relabelled "Conversational Analytics" inside the BigQuery folder (the folder already says BigQuery). The two demos under `/rfc/` mark RFC as current, as their old strips did.

## Single source of truth

- `tools/site_nav.mjs` holds the IA, the page list, the current-page map, and the sticky set. `node tools/site_nav.mjs` rewrites the block between `<!-- site-nav:start -->` and `<!-- site-nav:end -->` in every listed page and normalises the two `data-site-nav` head tags; `--check` exits 1 on drift.
- `assets/site-nav.css` and `assets/site-nav.js` are referenced with page-relative hrefs so `file://` previews and `rfc/tools/rfc_word_count.mjs` load them.
- Pages in scope (13): `research/index.html`, the seven `research/*/index.html`, `rfc/index.html`, `rfc/detailed-rfc/index.html`, `rfc/demo/index.html`, `rfc/full-demo/index.html`, `evalbench/index.html`. Per-page topbar/brand/nav CSS is removed; the board pack masthead loses its duplicate brand link and keeps its audited kicker line.

## Markup contract

`div.site-topbar[data-site-nav]` → `div.site-topbar-inner` → `a.site-brand`, `button.site-nav-toggle[aria-expanded][aria-controls=site-nav]`, `nav.nav-links.site-nav#site-nav[aria-label=Primary]`. Inside the nav: plain `a` for top-level links; `div.site-nav-folder` containing `button.site-nav-folder-button[aria-haspopup=true][aria-expanded][aria-controls]` and `div.site-nav-menu#…` of `a`. The class `nav-links` is kept so `rfc/tools/check_rfc_routes.mjs` keeps finding the links. The current page's link carries `aria-current="page"`; its folder carries `data-active="true"`. Long single-page documents (detailed RFC, both demos) carry `data-sticky`.

## Behaviour (`assets/site-nav.js`, progressive)

- Folder button click toggles its menu; opening one closes the others. `ArrowDown`/`ArrowUp` on the button opens and focuses the first/last item. Inside a menu `ArrowDown`/`ArrowUp`/`Home`/`End` move focus. `Escape` closes the open folder and returns focus to its button; tabbing out or clicking outside closes it.
- Handled keys (arrows, Home, End, Escape) are consumed with `stopPropagation` so page shortcuts (the demos' Home/End beat keys) do not fire. A panel that would run past the right edge of the viewport hangs from the button's right edge (`data-align="right"`; the last folder always does).
- Below 860px the nav collapses behind a `Menu` toggle (`aria-expanded`); folders expand inline; `Escape` with no folder open closes the menu and refocuses the toggle. Viewport changes reset state. On the sticky pages an expanded bar is capped at the viewport height and scrolls inside itself.
- Without the script the CSS shows folders on hover and `:focus-within` on desktop (an invisible 8px bridge above the panel keeps the pointer inside the folder while crossing the gap), lists everything on mobile (toggle hidden), and releases the sticky position on mobile so the list is ordinary page flow.
- The board pack's skip link (`rfc/styles.css`) sits above the bar (`z-index: 60` over the bar's 40) so the first Tab stop is visible.
- If a page ships without any `aria-current` (a generator drifted), the script marks the link whose href equals `location.pathname`.

## Visual

Dark navy bar (`#101828`), 58px tall, mono brand with orange `HC`, items muted `#b7c2d0` → white on hover, current item underlined in the accent, open folder is a raised panel; on mobile current items get a left accent bar. Hidden in print.

## Acceptance

1. `node tools/site_nav.mjs --check` → all 13 pages in sync.
2. `node tools/check_site_nav.mjs` → every page passes the desktop and mobile checks (IA links, single aria-current, each folder open inside the viewport, Escape focus return, ArrowDown/Home/End, tab-out and outside click close an open folder, toggle, no horizontal overflow), the no-JS hover path across the gap, the board pack's first-Tab skip link, Home/End on both demos keeping `#beat=3` at 1280 and 375px, and the sticky pages at 667×375 with and without the script.
3. `node rfc/tools/check_rfc_routes.mjs` → all routes behave; `rfc/spikes/bq-graph/tests` green (the demo nav test now reads the generated block).
4. `rfc/tools/rfc_word_count.mjs` stays under the ceilings (1,800 / 7,500 with folds open).
