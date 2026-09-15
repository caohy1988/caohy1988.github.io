# Plan — implementation slices (in-repo pointer)

Full dual-aligned plan: `/tmp/mcp-apps-matrix-pm/impl/PLAN_v2.md` (Haiyuan-approved 2026-09-14). Do not re-litigate v7 wording in PRs 1–4.

## Publishable slices
| PR | Contents | Checks in same PR | v7 text edited? |
|---|---|---|---|
| **1. Copy contract (this PR)** | `pm-readable-{intent,spec,plan}.md`; field defs; `judgments.json` (9 sentences + 36 rows + fixtures); `v7-preservation-baseline.json`; `copy-map.json`; schema/fixture tests | schema validation; Cursor/VS Code counterexamples | no |
| **2. First reader-facing page** | `brief.md` + generator: banner, aggregate judgment, shipping action, product sentences; layer D in `<details>` with ids + fragment-open; no compact grid yet | preservation parity (blocks + 81 links); private-path/forbidden-word; `--check` drift; site-nav; viewport S2 | no |
| **3. Compact comparison** | layer B grid from `judgments.json`; cards under ~700px; disclosure buttons | mapping/staleness hash gate; keyboard/touch; print/fragment | no |
| **3b. Host TLDR (additive)** | above-fold `#host-tldr` from `host-tldr.md`: plain summary, official-matrix paragraph, Host \| Status \| Why (Documented/Partial/Unknown chips, linked evidence) | 9 rows; allowed chips only; https link per Why; private-path guard; `--check` drift | no |
| **4. Acceptance / handoff** | Chromium viewports as PR70; Safari Reader; PM+UTL reader session; Astra at exact HEAD; vault | §8 gates recorded | no |

PR4 records: measured §8 values (Chromium + WebKit) in `acceptance-results.md`, reproducible with `tools/matrix_skim_check.mjs`; the deferred human steps (Safari Reader View pass, PM + UTL five-question test) and their templates in `acceptance-checklist.md`. S1 fails at HEAD and is recorded as a residual, threshold unchanged.

## Order rule
No fold-only intermediate publish. Judgment + shipping action land in PR2 with preservation checks.

## Same URL
Canonical path stays `/research/builds/mcp-apps-feature-matrix/`.
