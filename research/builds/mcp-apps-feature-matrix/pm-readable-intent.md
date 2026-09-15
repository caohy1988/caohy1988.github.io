# Intent — MCP Apps matrix, UTL/PM-readable edition

- **Page (unchanged URL):** https://caohy1988.github.io/research/builds/mcp-apps-feature-matrix/
- **Contract:** Haiyuan-approved `PLAN_v2.md` (2026-09-14), dual-aligned after Astra plan review.
- **This file:** why the redesign exists. Spec and plan siblings: `pm-readable-spec.md`, `pm-readable-plan.md`.

## Problem
The live v7 page is an engineer evidence ledger (~2.7k words, 72 cells, many `unk`, ~2360px-wide table). Judgments and shipping implications are buried. A UTL or PM cannot answer “what do we know / what do we ship anyway?” in five minutes.

## Intent
Keep the same URL and the same v7 evidence (layer D), and add a reader-facing front that:

1. States an honest aggregate judgment and a portable shipping action above the fold.
2. Gives nine short product sentences grouped by evidence kind.
3. Offers a compact question-first status grid (not Yes/No/supported chips).
4. Demotes the full v7 matrix, legends, footnotes, and takeaways into an on-demand evidence fold without editing v7 wording.

## Non-negotiable honesty
- No invented observed UI or fallback runs.
- Unknown means “this evidence does not establish the answer”; it is not “unsupported”.
- Do not upgrade `unk` cells.
- No private receipt paths or “links to a receipt” promises on the public page.
- Question-first chips: the evidence word answers the column’s question, not the strongest token in the cell.
- Keep v7 dates and qualifications in every phrase.

## Success (skim)
Outside PM + UTL, folds closed, under five minutes: which hosts document Apps UI; which stay unknown and why; what to ship regardless; one scoped evidence step that would change the page. Viewport: judgment + shipping action visible at 1280×720 and 375×667.
