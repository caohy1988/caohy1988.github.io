# Spec — LT-friendly Technical design

## Target surface
Primary: `rfc/board-pack/index.html` → `#technical-design-body` (intros + design-context / access / execution / chain / evidence).
Mirror: `rfc/board-pack/STORY.md` matching sections.
SVG `<desc>` text if it still dumps lab chronology; keep diagram labels.

## Voice / length
- Each of the five design parts: roughly **half or less** of current prose.
- Prefer short paragraphs or tight bullets: **What it does** · **Shown** · **Not shown** (or equivalent).
- Lead with the support boundary; put attempt inventories, fixture names, dates, and runner plumbing behind evidence links.
- Keep leadership-story rules from PR53: no personal names in board pack; no lab calendar as the story; no per-case test inventories in the board surface.
- Do **not** weaken honesty: SQL-only vs graph, single identity, chosen-start, invented Acme, PROPOSED thresholds, combined proof bar, Finance pilot ask stay accurate.
- Full RFC (`rfc/index.html`) current-evidence mirror: only touch if it is byte-tied to board claims in this PR; prefer board + STORY. Do not expand RFC lab detail.

## Out of scope
Sep 19 Slice B driver/live; BQAA PRs; accepting envelope numbers; inventing fact versions; merge.
