# Acceptance results — PLAN_v2 §8 (PR4)

- **Recorded:** 2026-09-14 PT by Opus (`claude-opus-5`), standing in for the quota-held Fable seat.
- **Page:** `index.html` on branch `research/mcp-apps-matrix-pm-readable-pr4` (base `main` `ec5d03b`, live page bytes equal to that main before PR4). After the PR4 CSS fix below, `index.html` SHA-256 is `5953e49c…`.
- **Reproduce:** `node tools/matrix_skim_check.mjs --check --engine all [--json FILE] [--shots DIR]`. It serves the repo on loopback and runs headless Chromium and WebKit through the gstack Playwright install. Exit 1 means a gate failed; exit 3 means no browser was found.
- **Scope:** these are automated gates only. No MCP Apps UI was run for this record, and it adds no evidence to any cell. The human Safari Reader pass and the PM/UTL test have not been run; see `acceptance-checklist.md`.

## Summary

| Gate | Result | Measured value |
|---|---|---|
| S1 reading load | **FAIL** (residual; threshold unchanged) | 1,547–1,631 words, 6.73–7.09 min at 230 wpm, against a limit of ≤ 900 words / ≤ 4.0 min |
| S2 first-screen geometry | PASS | bottom edge (px) of banner / judgment / action: 1280×720 → 564 / 391 / 446; 375×667 → 560 / 330 / 416 (Chromium) |
| S3 first-screen tokens | PASS | all 4 tokens visible at 1280×720 and 375×667 in both engines |
| S4 preservation | PASS | layer D: 6 block hashes, 81 links in order, `#matrix` / `#notes` / `#takeaways` present; loading `#takeaways` opens the fold at every viewport |
| S5 derivation | PASS | judgments schema, counterexample fixtures and sentence derivations; compact freshness, with a stale `cell_sha256` correctly failing; host TLDR parser |
| S6 mobile and interaction | PASS | overflowX 0 at 320 and 375; Enter/Space/Escape work at all 4 viewports; tap works at 320 and 375; print emulation opens the fold |
| S7 forbidden strings | PASS (one note) | static checks plus rendered check; see the host TLDR label note below |
| S8 drift | PASS for this page | `build_mcp_apps_matrix.mjs --check` in sync; `check_site_nav.mjs` has 2 pre-existing failures on `research/usage/` only |

Test suite: `node --test tools/matrix_judgments.test.mjs tools/matrix_preserve.test.mjs tools/matrix_compact.test.mjs tools/matrix_host_tldr.test.mjs tools/matrix_skim_check.test.mjs` gives 36 tests: 35 pass, 0 fail, and 1 todo. The todo is S1; it still asserts the 900-word limit and prints the failing values.

## S1 — reading load, folds closed

Words are counted in `<main>` `innerText` as whitespace tokens containing a letter or digit. At every viewport the evidence fold is closed and 0 compact panels are open. Chromium and WebKit give identical counts.

| Viewport | Words | Minutes |
|---|---|---|
| 320×568 | 1,631 | 7.09 |
| 375×667 | 1,631 | 7.09 |
| 820×1180 | 1,547 | 6.73 |
| 1280×720 | 1,575 | 6.85 |

Words per section, compared with the PLAN_v2 §3 layer budgets:

| Section | 375×667 | 1280×720 | PLAN budget |
|---|---|---|---|
| Layer A: kicker, h1, meta, short version, banner, by product | 380 | 408 | ≤ 450 ✓ |
| Host status at a glance (`#host-tldr`, PR73, additive) | 298 | 309 | not in PLAN_v2 budget |
| Layer B: status by product (`#status-by-product`) | 741 (cards) | 646 (table) | ≤ 300 ✗ |
| Layer C: what would change this page | 179 | 179 | ≤ 150 ✗ |
| Generator-inputs line + evidence fold summary | 33 | 33 | — |

**Residual.** S1 fails because of the page content, not a layout bug. Layer B, which shows 36 visible phrases, is more than twice its budget. The PR73 host TLDR adds about 300 words the plan never budgeted. Layer C is slightly over. Getting under 900 would mean cutting or folding reviewed copy: collapsing layer B by default, trimming the host TLDR, or shortening the next steps. That is a copy and IA decision for Haiyuan and Astra, not a PR4 acceptance fix, so PR4 changes no copy and keeps the threshold.

## S2 / S3 — first screen

`scrollY` is 0 and folds are closed. A target passes when `top ≥ 0` and `bottom ≤ innerHeight`. S3 text consists of the words whose own box sits inside the viewport and inside every clipping ancestor.

| Engine | Viewport | Gated | Banner bottom | Judgment bottom | Action bottom | S3 tokens | First-screen words |
|---|---|---|---|---|---|---|---|
| Chromium | 1280×720 | yes | 564 | 391 | 446 | 4/4 | 248 |
| Chromium | 375×667 | yes | 560 | 330 | 416 | 4/4 | 170 |
| Chromium | 820×1180 | no | 360 | 220 | 267 | 4/4 | 453 |
| Chromium | 320×568 | no | **615 (below fold)** | 349 | 455 | 2/4 | 137 |
| WebKit | 1280×720 | yes | 556 | 386 | 440 | 4/4 | 248 |
| WebKit | 375×667 | yes | 545 | 323 | 407 | 4/4 | 177 |
| WebKit | 820×1180 | no | 352 | 216 | 262 | 4/4 | 465 |
| WebKit | 320×568 | no | **599 (below fold)** | 342 | 445 | 3/4 | 145 |

The page puts the judgment and action before the banner. At 320×568 the banner ends below the first screen, and there the Unknown-definition token is not visible without scrolling. PLAN_v2 gates S2/S3 at 1280×720 and 375×667 only, so this is recorded, not failed. It is the margin to watch if a later PR adds anything above the banner.

Font sensitivity: with Google Fonts blocked (`--offline`, 0 web fonts loaded), Chromium 1280×720 bottoms are 607 / 434 / 490 and S2/S3 still pass. The 375×667 values are unchanged.

## S4 / S5 / S7 / S8 — existing gates

- **S4** `tools/matrix_preserve.test.mjs`: `--check` in sync; the ordered 81-link inventory and the `#matrix` / `#notes` / `#takeaways` ids; the `html_intro`, `html_matrix_region`, `html_callout`, `html_notes`, `html_takeaways` and `html_rendered_from` blocks match the pinned baseline hashes and byte lengths; deleting a takeaway fails parity. In the browser, loading `#takeaways` opens `#full-evidence` and shows the target at all 4 viewports in both engines.
- **S5** `tools/matrix_judgments.test.mjs`, `tools/matrix_compact.test.mjs`, `tools/matrix_host_tldr.test.mjs`: schema and counterexample fixtures (Cursor fallback, VS Code mount), sentence derivations, exact 9×4 coverage, stale `cited_blocks` / `cell_sha256` rejection, 72 unique disclosure ids, host TLDR allowed chips and a linked Why per row.
- **S7** static: private-path guard (including an ordinary temp-directory inspection path in the brief), no receipt-link phrasing, no Yes/No-supported status word, no Unsupported chip, and the parser rejects `Unsupported`. Rendered (both engines, all viewports):
  - chips are only Documented / Partial / Unknown;
  - compact words are Documented, Reported, Unknown, Code found, Internal gate found, Source pinned and User setting;
  - no private path appears in `<main>`;
  - compact table rows and cards read "GitHub Copilot in VS Code".
  - **Note:** the PR73 host TLDR row label is the shorter "GitHub Copilot". Its summary sentence and Why links name VS Code. PLAN_v2 S7 was written for the compact rows and cards before PR73 existed. The label comes from reviewed `host-tldr.md` copy, so it is recorded here and not changed.
- **S8**: `node tools/build_mcp_apps_matrix.mjs --check` reports in sync. `node tools/check_site_nav.mjs` has 303 OK and 2 FAIL, both on `research/usage/index.html` (desktop IA links; End focuses the last item), with the same result before and after the PR4 change. The MCP Apps matrix page passes all of its site-nav checks. PR4 touches no `/rfc/` route.

## S6 — mobile and interaction

| Engine | Viewport | overflowX | Enter / Space / Escape | Tap | Print emulation |
|---|---|---|---|---|---|
| Chromium | 320×568 | 0 | pass | pass | pass |
| Chromium | 375×667 | 0 | pass | pass | pass |
| Chromium | 820×1180 | 0 (86 before the fix) | pass | — | pass |
| Chromium | 1280×720 | 0 | pass | — | pass |
| WebKit | 320×568 | 0 | pass | pass | pass |
| WebKit | 375×667 | 0 | pass | pass | pass |
| WebKit | 820×1180 | 0 (97 before the fix) | pass | — | pass |
| WebKit | 1280×720 | 0 | pass | — | pass |

- **Disclosure:** the first visible compact trigger ("Documented inline Claude Desktop, Vendor documents Apps rendering?: show evidence") gets focus. Enter sets `aria-expanded="true"` and shows the panel; Space closes it; Enter and then Escape closes it. On phones, tap opens and tap closes.
- **Print:** under `emulateMedia("print")`, `#full-evidence` opens through the page's `matchMedia("print")` listener, the summary is `display: none`, and hidden compact panels are `display: block`. The `@media print` CSS is present. The real print dialog was not exercised.
- **Fix in PR4 (CSS only; no copy and no layer D change).** At 820×1180 and 860 px, the document scrolled sideways by 86 px (Chromium) or 97 px (WebKit). The cause was the compact trigger's absolutely positioned `.visually-hidden` accessible-name span. Its containing block lay outside the `.compact-table-wrap` scroller, so it escaped the scroll clip. Adding `position: relative` to `.compact-trigger` in the generator removes the overflow; overflowX is now 0 at 820 and 860. This is outside the S6 gate (320/375), but it is a real viewport bug from PR3 at a PR70 viewport. The live page still shows the overflow until PR4 merges.

## Safari / WebKit

**Measured.** Headless WebKit (Playwright `webkit-2248`) rendered the same page at all 4 viewports and passed the same S2, S3, S4-fragment, S6 and S7 checks as Chromium; see the tables above. Reader-structure heuristics were identical in both engines:
- 1 `<main>`, 1 `<h1>`, `lang="en"`, canonical URL and meta description present;
- visible h2s with folds closed: The short version, Host status at a glance, By product, Status by product, What would change this page;
- 9 (phone) or 10 (desktop) visible paragraphs of at least 80 characters;
- evidence fold summary "Full evidence (v7, 2026-09-14): matrix, legend, columns, footnotes, takeaways, history";
- ids `aggregate-judgment`, `shipping-action`, `banner`, `host-tldr`, `by-product`, `status-by-product`, `what-would-change`, `full-evidence`, `matrix`, `notes` and `takeaways` all present.

**Not measured.** Safari Reader View is browser chrome. Its extraction is not exposed to Playwright WebKit, so neither what Reader keeps nor whether it expands the closed `<details>` is established here. **DEFERRED — human Safari Reader pass;** steps are in `acceptance-checklist.md` §1.

## Deferred human items

| Item | Status |
|---|---|
| Safari Reader View on the live URL | DEFERRED — requires a human in Safari |
| Outside-reader five-question test (one PM, one UTL) | DEFERRED — requires human PM + UTL, no coaching, folds closed, 5 minutes each. If either reader misses Q4 (what Unknown means), human acceptance cannot be called complete. |
| Astra review at exact PR4 HEAD | pending |

No reader answers, reader timings or Reader View observations have been recorded, and none may be filled in without a real session.
