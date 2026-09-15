# Plan: publish in BigQuery, then consume (RFC-aligned full path)

Implements `spec-publish-author-bq.md`. Agent team: Opus implements and opens PRs. After the PR URLs exist, the parent
EM kicks Astra (primary review; APPROVE = overnight merge) and Kimi (second LGTM, quota permitting).

## Units

- **U1 Config and environment plumbing** (spike).
  - Add `dataset_stem` / `entry_stem` to `LifecycleConfig`.
  - Add `RestrictedBroker(graph_dataset=)`.
  - `LiveEnv` uses `cfg.runtime_dataset` for the broker, probe and revoke.
  - `HermeticEnv` gets optional Catalog pages/entries and head.
  - Gate: existing `test_connected.py`, `test_catalog_lifecycle.py` and `test_chain_restricted.py` stay green.
- **U2 `okf_bq_graph/publish_connected.py`.**
  - `HermeticCloud`, `run_publish_connected(...)`, `summary`, `main`, the §05 state trace, the consumed-publication
    check, author identity and the verdict.
  - Gate: new `tests/test_publish_connected.py` green (positive + five negatives).
- **U3 Full spike suite.** `python3.13 -m pytest -q` green, including the RFC word-ceiling tests.
  - Commit and push the site branch `rfc/publish-author-bq` **hermetic-first** (no-exit-while-waiting).
- **U4 Companion `okf-connected-e2e` 0.2.0** on branch `publish-author-bq`.
  - Default full path, `--consume-only`, banner, progress, payload `publication` block and the withheld rule.
  - `SPIKE_REF` points at the U3 commit.
  - Tests green; commit and push.
- **U5 Live.** On `test-project-0728-467323`, run `okf-e2e agent --live` under asciinema (tmux PTY, 160x50). The
  recording is the live run itself.
  - Pre-flight (read only): no leftover `okf_kp_publish_*` datasets or entries; group entry count under the page cap;
    ADC operator; SDK and Acme checkouts clean at their pins.
  - A failed live run is retained with its honest verdict and never relabelled; fix, then re-run.
- **U6 Evidence.**
  - Copy the run directory into the spike `evidence/publish-connected/`.
  - Write `evidence/report-publish-connected.md`: job table, `READY` row, head before/after, state trace, connected
    cases, identity, cleanup and residuals.
  - Scan for leaks (e-mail, tokens, home paths).
  - Tape: `agg` → `ffmpeg` mp4 (idle compressed, labelled), poster, cast, transcript → `rfc/demo/`.
- **U7 Site copy.**
  - `/rfc/demo/#connected-e2e` becomes the full path: Publish (BQ) → Discover → Pin/retrieve → Access/revoke →
    Receipt → Consumer. The earlier consume-only tape stays linked as history.
  - `/rfc/` "The three as one path" and "What is still open", and the detailed RFC §05 note and "Connected end-to-end
    run" paragraph, get word-neutral edits. Budgets: landing ~934/950 rendered, detailed ~7444/7500 open.
  - Re-run `rfc_word_count.mjs`.
- **U8 PRs.**
  - Site PR (base `main`) and code PR. Each body carries the job ids, run id, RFC coverage table, residuals and a
    "Review requested: @Astra (primary, overnight APPROVE = merge), Kimi (second LGTM)" line.
  - URLs go immediately to `/tmp/okf-publish-author/OPUS_PUBLISH_AUTHOR_NOTES.md` and `STATUS.md`
    (`STATUS=WAITING_REVIEW`).
- **U9 Vault.** `bin/vault-note Ship/builds` with learnings and pointers, no secrets.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Dataplex entry-group grant or revocation propagation (70–90 s) | existing `stable()` gates; `--wait-s 600` |
| Catalog list page cap (5 × 100) if the group accumulated entries | pre-flight count; cleanup of owned entries is exact |
| New dataset ACL propagation for the requester | broker `apply` waits on a dry-run probe of `<owned>.nodes`, then `stable()` |
| Operator lacks dataset create in US | Slice B2 created `okf_catalog_chain_*` live with the same operator |
| Dataset deleted before ACL restore reads back | connected teardown runs inside `run_connected`'s `finally`, before lifecycle cleanup |
| Content-addressed id equals the long-lived publication | disclosed; the consumed check also pins the owned dataset, not just the id |
| mp4 push size | `/usr/local/bin/git -c http.postBuffer=524288000 push` |
