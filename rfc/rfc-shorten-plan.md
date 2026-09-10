# Plan — shorten both RFC surfaces

Branch `feat/rfc-shorten-both` from `21b87e5` (origin/main), worktree `caohy1988.github.io-rfc-shorten`. Offline; no merge.

1. Baseline: count both pages with the Chromium counter (3,281 / 14,102 all open); run the link tests, the fact-select tests, both demo checkers.
2. Add `rfc/tools/rfc_word_count.mjs` and `test_rfc_word_ceilings.py` (skips without Playwright).
3. Landing page, section by section (keep / shrink / cut):
   - keep: head script, masthead, hero title and figure, comparison cells, envelope row set, design figure, punchline
   - shrink: opening, runtime assessment (5 → 3 paragraphs), comparison notes, later questions, every envelope row, design intro and Shown/Limits items, the benchmark bullet, the two asks
   - cut: the fourth assessment paragraph (invented data, untried refusal) — folded into the "shown" paragraph as one clause; the Enterprise rule's second and third sentences; per-row measurement history in the envelope
4. Detailed RFC, section by section:
   - keep: every id, both diagrams, every code block, plane table, guarantee table, keys table, ladder, auditor table, at-a-glance table, risks table, jump nav, badges, credo, board-pack link, `../demo/` and `../full-demo/` links, all pinned evidence links in the recorded-examples note
   - shrink: status note, summary prose and table notes, motivation, system-design prose, all six decisions, baseline fold, protocol bullets, every fold in 06, ladder and table cells, acceptance checks, phase intro, phase cards, closing, footer
   - cut: the summary's examples paragraph (→ pointer), motivation's fixture note (→ one sentence), the Alder-consequence paragraphs in 06, the three "where the evidence stands" paragraphs in 06 (→ one sentence each), the Phase 0 MVP inventory (→ three sentences), the earlier-demos bullet list (→ one sentence with its links), the phase intro's third paragraph (→ two sentences), footer history (→ one line)
   - names removed: the VP, the post's authors, the reviewing agents
5. Verify: counter under both ceilings; link tests, fact-select tests, new ceiling test; full suite to a log file; `check_full_demo.py` exit 0; `check_cli_viewer.py` at 3 baseline FAILs; browser route check.
6. Commit, push, open PR with before/after counts. Vault note under `Ship/rfc/`.

## Result (2026-09-09)

| Page | Before (all open / closed) | After (all open / closed) | Ceiling |
|---|---|---|---|
| `rfc/index.html` | 3,281 / 2,172 | 1,797 / 1,156 | 1,800 |
| `rfc/detailed-rfc/index.html` | 14,102 / 10,132 | 7,493 / 5,721 | 7,500 |

Counted by `node rfc/tools/rfc_word_count.mjs`. The architecture diagram's rendered labels alone are about 600 words of the detailed page and the landing diagram about 120; both are unchanged.

Verified offline: link tests, fact-select tests and the new ceiling test (33 passed); full spike suite 1,013 passed after rebasing onto origin/main `c37056a` (PR 63 merged mid-slice; its FS-1 wording — hermetic-only runner, never run live; “no live run has done this yet” — is re-applied on both shortened pages); `check_full_demo.py` exit 0; `check_cli_viewer.py` at its three baseline Prototype-callout failures (the callout was already absent before this slice); `check_rfc_routes.mjs` all routes behave. No section id was removed on either page; the landing forwarder list is unchanged. Links dropped from the detailed page: the demo walkthrough anchor, five full-demo capture files that the earlier-demos note no longer itemises, the graph-overview doc page and one README anchor; none is asserted by a test and every remaining relative link resolves.

## Limitation-evidence cut (2026-09-09, second pass on Haiyuan's ask)

| Page | Before (all open / closed) | After (all open / closed) | Ceiling |
|---|---|---|---|
| `rfc/index.html` | 1,797 / 1,156 | 1,650 / 1,112 | 1,800 |
| `rfc/detailed-rfc/index.html` | 7,493 / 5,721 | 6,942 / 5,231 | 7,500 |

Cut: the repeated dumps of what was not measured, not proven, hermetic-only, cost-cell-empty or 0-of-9. Each limit now appears once, as a clause beside the claim it qualifies. Landing: the "still open" list collapses to one sentence; the cost and latency rows keep the proposed number and one "not yet measured / sampled" clause; the design fold keeps one Limits line per part, drops the Preview aside, the reviewer-wrote-the-fix bullet and the hermetic-runner narration (the locked fact-data sentence in the envelope still carries it). Detailed: the status note, table notes, architecture status, figcaption, decision scope, baseline fold, captured-API bullet, Property Graph, access, verdict and phase paragraphs lose their "does not establish / not completion / still to prove" tails; the Phase 0 off-site inventory note and the motivation fixture note are deleted; the recorded-examples note keeps one limit per run and the FS-1 sentence the tests lock; the footer keeps its single dated honesty line. No section id removed; dropped links are unasserted (two session captures, `comparison.md`, the graph-search doc).

Verified offline: link, fact-select and ceiling tests 33 passed; full spike suite 1,013 passed; `check_full_demo.py` exit 0; `check_cli_viewer.py` at its 3 baseline failures; `check_rfc_routes.mjs` all routes behave; no digest, job id, PR number or personal name in prose.

### Review fix (Astra P2 at 0ba489a)

Both chain summaries carry one added clause: "The restricted-identity and graph-query runs began from hand-pinned seeds; the restricted run used plain SQL." Landing 1,665 / detailed 6,957 words with every fold open; 33 page tests passed.
