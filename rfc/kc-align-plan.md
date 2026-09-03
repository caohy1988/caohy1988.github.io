# Plan — file-level edits for the Knowledge Catalog alignment

Implement from this file. Worktree `/Users/haiyuancao/caohy1988.github.io-okf-kc-align`,
branch `feat/rfc-kc-blog-align` off `main` `cc38d7a`. PR against
`caohy1988/caohy1988.github.io` `main`. Do not merge. Do not touch SDK PR 474.

## Decisions taken (fixed for this slice)

- **Adopt `okf-bundle`.** No fork. Every `okf-concept` in `rfc/index.html`
  becomes `okf-bundle`, with one sentence in §04 saying it is the shipped type.
- **Pins in a profile-owned `okf-context-runtime` aspect** (`publication_id`,
  `published_snapshot_id`, `managed_by_*` stamps, top-level strings). The
  shipped 13-field `okf` aspect is not extended. Revised 2026-09-03 after Codex
  P1 on PR 13: a stock sample repush replaces `okf` whole. Never in `extra`.
- **`okf-computation` is runtime-derived only.** Authored §10 fields stay on
  shipped `okf` fields 8 to 12.
- **Reserved-file rule.** `index.md` and `log.md` are bundle content for
  `source_manifest_hash`, not concepts. Index entries and the root `log.md`
  entry are projected, owned, pinned, and reconciled as non-concept entries for
  Documents-Layout parity, with `parentEntry`; `log.md` keeps the sample's
  `overview` + `okf` (`okf_type: Log`) shape.

## Commit 1 — docs (this file and its siblings)

- `rfc/kc-align-intent.md`, `rfc/kc-align-spec.md`, `rfc/kc-align-plan.md`,
  and the accepted analysis `rfc/kc-blog-analysis.md`.

## Commit 2 — `rfc/index.html`

Edits by region (line numbers at `cc38d7a`):

1. **Header, Sources note (L193).** Rewrite the "Sources:" clause: frozen
   snapshot kept; add the default-push caveat (`okf.ts` `DEFAULT_BUNDLE`), the
   `sql_equality.py` difference, and "bundle root from either repository".
   Add a second note, "Shipped baseline", holding the Section E paragraph with
   the post linked.
2. **Summary (L206).** Add the clause that the Catalog leg is a delta on the
   shipped `toolbox/mdcode/demo/okf/` sample.
3. **§03 diagram (L318 to L320).** `okf-bundle entries (shipped type, v1)`;
   `okf aspect: shipped 13 fields + pins (14, 15)`;
   `okf-computation aspect: runtime-derived, on §10 concepts`.
4. **§04 Scope (L438).** Add the "strengthened by the post" sentence; mark
   `okf-rfc-roadmap.md` off-site.
5. **§04 Placement (L439).** Add the sample's location beside
   `toolbox/okf-context/`; Discussions availability stays unverified.
6. **§04 Implementation (L440).** Replace the false `push.ts` sentence with the
   verified description; add "delta on a shipped mechanism".
7. **§04 Catalog types (L451).** Adopt `okf-bundle`; shipped `okf` aspect plus
   `okf-context-runtime` pin aspect; `okf-computation` runtime-derived; reworded Phase 2b
   `semantic-*` rule citing kcmd's prefix ownership, `--force-remove`, and
   one-model-per-EntryGroup.
8. **§05 bullets (L497, L498).** Lag SLO per entry count; pin read via
   `entries.get` with `view=ALL` (post claim on LookupContext labeled), runtime
   enforces pin-or-fail-stale, search predicates filter only.
9. **§06 identity (after L514) and membership (L530).** Reserved-file bullet;
   membership sentence that reserved files are recorded as non-concept files.
10. **§06 retrieval (L585, L586).** Scope #209 granularity to the BigQuery
    runtime; add the Catalog enforcement unit (EntryGroup, full bodies in
    `overview`, mixed-policy fail closed at projection).
11. **§06 Catalog ownership (L657, L658).** Mapping uses `okf-bundle`, shipped
    aspect plus pins, runtime-derived `okf-computation`, index entries with
    `parentEntry`; ownership paragraph cites the post's no-delete upsert and
    names both adversaries; cite the post.
12. **§09 phase table (L705) and Phase 2 (L733 to L735).** `okf-bundle`; gate
    adds index/log ownership, the Documents-Layout adversary, and the
    `entries.get` pin wording; Out reworded for 2b.
13. **§09 Phase 0 MVP note (L711).** Mark `PROFILE.md` and
    `okf-rfc-roadmap.md` as off-site working files.
14. **§09 risk table (L764).** Two-pushers row names both adversaries and the
    IAM fact that `catalogEditor` grants delete across the EntryGroup.
15. **Footer.** Add "Aligned 2026-09-03 with the Knowledge Catalog post".

## Commit 2 (same or separate) — `rfc/demo/app.js`

Only the badge string `okf-concept · derived view` becomes
`okf-bundle · derived view` so the demo does not contradict the RFC. No other
demo change. Run `python3 rfc/demo/tools/check_cli_viewer.py` after.

## Verify

- `grep -c okf-concept rfc/index.html rfc/demo/app.js` is 0 for both.
- Post URL present in `rfc/index.html`.
- `python3 -c "import html.parser"`-level sanity: open the page locally with
  `python3 -m http.server` and confirm the header notes and §04 render.
- `git diff --stat` touches only `rfc/index.html`, `rfc/demo/app.js`, and the
  four `rfc/kc-*.md` files.

## Ship

```
git add rfc/kc-blog-analysis.md rfc/kc-align-intent.md rfc/kc-align-spec.md rfc/kc-align-plan.md
git commit -m "docs(rfc): intent/spec/plan for aligning the Catalog leg with the shipped OKF post"
# ... HTML edits ...
git add rfc/index.html rfc/demo/app.js
git commit -m "rfc: align Catalog projection with shipped OKF Knowledge Catalog post"
git push -u origin HEAD
gh pr create --repo caohy1988/caohy1988.github.io --base main
```

Do not merge. Codex and Kimi review next.
