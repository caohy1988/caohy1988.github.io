# Acceptance results — PLAN_v2 §8 (S1 residual fix, after PR4)

- **Recorded:** 2026-09-14 PT by Opus (`claude-opus-5`), standing in for the quota-held Fable seat.
- **Page:** `index.html` on branch `research/mcp-apps-matrix-pm-readable-s1`, base `main` `d0e7ec6` (PR74 merged as `b0c4b43`). `index.html` SHA-256 after this change: `f9253d95…`.
- **Reproduce:** `node tools/matrix_skim_check.mjs --check --engine all [--json FILE] [--shots DIR]`. It serves the repo on loopback and runs headless Chromium and WebKit through the gstack Playwright install. Exit 1 means a gate failed; exit 3 means no browser was found.
- **Scope:** these are automated gates only. No MCP Apps UI was run for this record, and it adds no evidence to any cell. The human Safari Reader pass and the PM/UTL test have not been run; see `acceptance-checklist.md`.
- **Thresholds were not raised.** `S1_MAX_WORDS = 900` and `S1_MAX_MINUTES = 4.0` are unchanged, and the test asserts both values.

## Summary

| Gate | Result | Measured value |
|---|---|---|
| S1 reading load | **PASS** | 863–890 readable words, 3.75–3.87 min at 230 wpm (limit ≤ 900 / ≤ 4.0), both engines, all four viewports |
| S2 first-screen geometry | PASS | bottom edge (px) of banner / judgment / action: 1280×720 → 541 / 368 / 424; 375×667 → 560 / 330 / 416 (Chromium) |
| S3 first-screen tokens | PASS | all 4 tokens visible at 1280×720 and 375×667 in both engines |
| S4 preservation | PASS | layer D: 6 block hashes, 81 links in order, `#matrix` / `#notes` / `#takeaways`; the whole `#full-evidence` fold is byte-identical to `main` (SHA-256 `3c449cd6…` on both); `#takeaways` opens the fold at every viewport |
| S5 derivation | PASS | judgments schema, counterexample fixtures, sentence derivations; compact freshness (stale `cell_sha256` fails); host TLDR parser, now including the official-vs-ours comparison |
| S6 mobile and interaction | PASS | overflowX 0 at all four sizes; status fold opens on Enter (all) and tap (phones); compact trigger Enter/Space/Escape (all) and tap (phones); print opens both folds |
| S7 forbidden strings | PASS | host TLDR chips are only Full / Partial / Unknown; no Documented chip in `#host-tldr`; no Yes/No/Supported/Unsupported; no private path |
| S8 drift | PASS for this page | builder `--check` in sync; `check_site_nav.mjs` still has the same 2 pre-existing failures on `research/usage/index.html` only |

Test suite (`node --test tools/matrix_judgments.test.mjs tools/matrix_preserve.test.mjs tools/matrix_compact.test.mjs tools/matrix_host_tldr.test.mjs tools/matrix_skim_check.test.mjs`): **39 tests, 39 pass, 0 fail, 0 todo.** The S1 `todo` from PR4 is gone; S1 is an ordinary asserted test.

## What changed

1. **Measurement fix (Astra PR74 P2).** PR4 counted `main.innerText`, which includes 36 fully clipped accessible-name spans (`.visually-hidden` on compact triggers, "… : show evidence") and the phone-clipped "The short version" heading. `readableTextInPage` now hides fully clipped boxes (`clip: rect(0,0,0,0)`, or `overflow: hidden` at ≤ 1×1 px, absolutely positioned) for the length of one read and restores them. The DOM and accessibility tree do not change. `rawWords` is still recorded. A browser regression fixture (`matrix_skim_check.test.mjs`) proves a 6-word clipped label and a clipped heading are excluded at 375 px, the heading counts at 1280 px, and closed-fold text never counts. The S1 gate now also requires every `<details>` in `<main>` to be closed.
2. **Skim IA.** Layer B `#status-by-product` sits inside a closed `<details id="status-by-product-fold">` whose summary is the h2 "Status by product" plus "four questions per host" (7 words). The grid, cards, 72 disclosures and their keyboard/touch behaviour are unchanged once the fold is open. A fragment inside any fold opens it, and print opens every fold in `<main>`. Layer C next steps are trimmed from 179 to 133 words, keeping each scoped step, its expected update and the proposed owner role. The generator-inputs line drops from 23 to 7 words. The desktop-only meta tail no longer repeats the banner.
3. **Official-vs-ours comparison (Haiyuan steer).** `#host-tldr` now leads its official-matrix block with **"Yes — this differs from the official MCP Apps matrix, intentionally."** It then gives a Question / Grain / Observed UI runs table: the official matrix asks whether a client implements `io.modelcontextprotocol/ui` (community CHECK); this page asks about the capability / registration-path / fallback gap on nine hosts (Full / Partial / Unknown with evidence links); observed UI runs: none. Both official links stay (overview, client matrix), plus the overlap line.
4. **Feature-parity chips (Haiyuan binding steer).** Host TLDR chips moved from Documented / Partial / Unknown (doc parity) to **Full / Partial / Unknown (feature parity)**, each Why citing dense-matrix capability evidence with links: **2 Full** (GitHub Copilot — docs plus pinned source for version, mount, off/error fallbacks, toggle; Cursor — docs plus dated reports of mount restored in 3.12, plain-text fallback, no toggle), **3 Partial** (Claude Desktop, Claude Cowork, OpenAI Codex Desktop), **4 Unknown** (Claude Code, OpenAI Codex CLI, Antigravity CLI, Antigravity Desktop). Full rows still say they are not observed runs; Unknown rows still say Unknown ≠ unsupported. Layer B keeps its own evidence words (Documented, Reported, …), which answer column questions, not host parity. No cell evidence was added and no UI was run.

## S1 — reading load, folds closed

Readable words in `<main>` (whitespace tokens containing a letter or digit; fully clipped accessibility-only text excluded). Chromium and WebKit give identical counts.

| Viewport | PR4 raw `innerText` | Counter fix only (PR4 page) | This branch, readable | This branch, raw | Minutes (readable) |
|---|---|---|---|---|---|
| 320×568 | 1,631 | 1,359 | **863** | 873 | 3.75 |
| 375×667 | 1,631 | 1,359 | **863** | 873 | 3.75 |
| 820×1180 | 1,547 | 1,276 | **881** | 884 | 3.83 |
| 1280×720 | 1,575 | 1,307 | **890** | 890 | 3.87 |

The counter-fix column runs the new counter against the unchanged `main` page. It shows the measurement fix alone leaves S1 failing (5.55–5.91 min), so the IA change was still needed.

Words per section, against the PLAN_v2 §3 budgets:

| Section | 375×667 | 1280×720 | PLAN budget |
|---|---|---|---|
| Layer A: kicker, h1, meta, short version, banner, by product | 377 | 386 | ≤ 450 ✓ |
| Host status at a glance (`#host-tldr`: summary, "Yes — this differs" comparison, Host/Status/Why) | 329 | 347 | not in PLAN_v2 budget (PR73 additive) |
| Layer B: status by product, folded (summary only) | 7 | 7 | ≤ 300 ✓ |
| Layer C: what would change this page | 133 | 133 | ≤ 150 ✓ |
| Generator-inputs line + evidence fold summary | 17 | 17 | — |

Margin: 10 words at 1280×720. The host TLDR is still outside the A+B+C=900 budget, and adding the comparison and feature-parity Why cells is what uses up most of the margin. A future host-TLDR addition should be measured before landing.

## S2 / S3 — first screen

`scrollY` is 0 and folds are closed. A target passes when `top ≥ 0` and `bottom ≤ innerHeight`.

| Engine | Viewport | Gated | Banner bottom | Judgment bottom | Action bottom | S3 tokens | First-screen words |
|---|---|---|---|---|---|---|---|
| Chromium | 1280×720 | yes | 541 | 368 | 424 | 4/4 | 235 |
| Chromium | 375×667 | yes | 560 | 330 | 416 | 4/4 | 170 |
| Chromium | 820×1180 | no | 360 | 220 | 267 | 4/4 | 417 |
| Chromium | 320×568 | no | **615 (below fold)** | 349 | 455 | 2/4 | 137 |
| WebKit | 1280×720 | yes | 534 | 364 | 418 | 4/4 | 235 |
| WebKit | 375×667 | yes | 545 | 323 | 407 | 4/4 | 175 |
| WebKit | 820×1180 | no | 352 | 216 | 262 | 4/4 | 437 |
| WebKit | 320×568 | no | **599 (below fold)** | 342 | 445 | 3/4 | 145 |

As in PR4, at 320×568 the banner ends below the first screen, so the Unknown-definition token is not visible without scrolling there. PLAN_v2 gates S2/S3 at 1280×720 and 375×667 only, so this is recorded, not failed.

## S4 / S5 / S7 / S8

- **S4** `tools/matrix_preserve.test.mjs`: six pinned layer D block hashes and byte lengths, ordered 81-link inventory, the three ids, and the takeaway-deletion negative all pass. `source.md` is untouched. The extracted `#full-evidence` fold hashes identically on `main` and this branch.
- **S5** `matrix_judgments`, `matrix_compact`, `matrix_host_tldr`: the host TLDR parser now requires the Official matrix block to hold a lead containing "differs", a `| | Official … | This page |` table with Question / Grain / Observed UI runs rows, `io.modelcontextprotocol/ui` in the official question, and both official links. The negatives (no "differs", missing Grain row, wrong overview link, table removed) all throw.
- **S7** host TLDR tests enforce 9 hosts in order; chips exactly Partial, Partial, Unknown, Unknown, Partial, Full, Full, Unknown, Unknown; no `chip-documented` or Documented chip; an https link with a non-URL label in every Why; the parser rejects `Unsupported`. Rendered in both engines at all viewports, host chips are Full / Partial / Unknown. Compact words (read with the status fold open) are Documented, Reported, Unknown, Code found, Internal gate found, Source pinned and User setting. No private path appears in `<main>`, and compact rows/cards read "GitHub Copilot in VS Code". The host TLDR row label stays "GitHub Copilot", as recorded in PR4.
- **S8**: builder `--check` in sync. `node tools/check_site_nav.mjs` fails the same 2 checks as on `main`, both on `research/usage/index.html` (desktop IA links; End focuses the last item). The matrix page passes its site-nav checks.

## S6 — mobile and interaction

| Engine | Viewport | overflowX | Status fold Enter | Compact Enter / Space / Escape | Tap (fold + compact) | Print (both folds open, panels shown) |
|---|---|---|---|---|---|---|
| Chromium | 320×568 | 0 | pass | pass | pass | pass |
| Chromium | 375×667 | 0 | pass | pass | pass | pass |
| Chromium | 820×1180 | 0 | pass | pass | — | pass |
| Chromium | 1280×720 | 0 | pass | pass | — | pass |
| WebKit | 320×568 | 0 | pass | pass | pass | pass |
| WebKit | 375×667 | 0 | pass | pass | pass | pass |
| WebKit | 820×1180 | 0 | pass | pass | — | pass |
| WebKit | 1280×720 | 0 | pass | pass | — | pass |

- **Status fold:** closed at load. Focus on its summary, then Enter opens and Enter closes; on phones a tap opens it. With it open, the first visible compact trigger passes the PR4 Enter/Space/Escape and tap sequence.
- **Print:** the check first confirms the status fold is closed. Under `emulateMedia("print")` the page's `matchMedia("print")` listener opens `#full-evidence` and `#status-by-product-fold`; the evidence summary is `display: none` and hidden compact panels are `display: block`. The real print dialog was not exercised.
- **Comparison table on phones:** below 700 px the Question / Grain / Observed UI runs rows stack with "Official:" / "This page:" labels (CSS generated content; the clipped thead is excluded from S1).

## Safari / WebKit

**Measured.** Headless WebKit passes the same S1–S7 checks as Chromium (tables above). Visible h2s with folds closed are now The short version, Host status at a glance, By product, Status by product (inside the fold summary) and What would change this page.

**Not measured.** Safari Reader View extraction, including whether Reader expands the new closed status fold. **DEFERRED — human Safari Reader pass;** steps are in `acceptance-checklist.md` §1.

## Deferred human items

| Item | Status |
|---|---|
| Safari Reader View on the live URL | DEFERRED — requires a human in Safari |
| Outside-reader five-question test (one PM, one UTL) | DEFERRED — requires human PM + UTL, no coaching, folds closed, 5 minutes each. If either reader misses Q4 (what Unknown means), human acceptance cannot be called complete. |
| Astra review at this branch's exact HEAD | pending |

No reader answers, reader timings or Reader View observations have been recorded, and none may be filled in without a real session.
