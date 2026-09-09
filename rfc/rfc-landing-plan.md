# Plan — `/rfc/` landing restructure

Branch `feat/rfc-board-pack-landing` from `fb8c051` (origin/main), worktree `caohy1988.github.io-rfc-restructure`.

1. Baseline: run `check_full_demo.py` (exit 0), `check_cli_viewer.py` (3 pre-existing FAILs on the Prototype callout), `test_board_pack_links.py` (4 passed).
2. Moves: `git mv rfc/index.html rfc/detailed-rfc/index.html`; `cp rfc/board-pack/index.html rfc/index.html`; `git mv rfc/board-pack/styles.css rfc/styles.css`.
3. Link rewrites per spec; redirect stubs; demo kicker links; nav item on 66 pages.
4. Checkers repointed at `rfc/detailed-rfc/index.html` (`check_full_demo.py`, `mutation_fixture.py`, `check_cli_viewer.py`).
5. Test module rewritten to gate both pages and both stubs.
6. Verify offline: link tests, full spike suite, full-demo checker, headless-browser pass with a local `http.server`.
7. Commit, push, open PR. No merge.

## PR 61 overlap

PR 61 (`feat/sqlchain-fact-select`) edits three hunks in `rfc/board-pack/index.html` (lines 56, 123, 271) and three in `rfc/index.html` (lines 892, 960, 996). Whichever PR merges second re-applies the other's hunks:

- PR 61's `rfc/board-pack/index.html` hunks belong in `rfc/index.html` after this slice.
- PR 61's `rfc/index.html` hunks belong in `rfc/detailed-rfc/index.html` after this slice.

The content was copied, not git-mv'd through PR 61's files, so git will report plain conflicts rather than silent misapplied renames.

## Fix pass (Astra review 5157689974)

8. Fragment-preserving stubs, legacy-bookmark forwarder, demo nav + register row, browser route check. Rerun link tests, full suite, both demo checkers; push; reply on the PR.
