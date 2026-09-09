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
