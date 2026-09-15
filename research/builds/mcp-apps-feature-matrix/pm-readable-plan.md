# Plan — implementation slices (in-repo pointer)

Full dual-aligned plan: `/tmp/mcp-apps-matrix-pm/impl/PLAN_v2.md` (Haiyuan-approved 2026-09-14). Do not re-litigate v7 wording in PRs 1–4.

## Publishable slices
| PR | Contents | Checks in same PR | v7 text edited? |
|---|---|---|---|
| **1. Copy contract (this PR)** | `pm-readable-{intent,spec,plan}.md`; field defs; `judgments.json` (9 sentences + 36 rows + fixtures); `v7-preservation-baseline.json`; `copy-map.json`; schema/fixture tests | schema validation; Cursor/VS Code counterexamples | no |
| **2. First reader-facing page** | `brief.md` + generator: banner, aggregate judgment, shipping action, product sentences; layer D in `<details>` with ids + fragment-open; no compact grid yet | preservation parity (blocks + 81 links); private-path/forbidden-word; `--check` drift; site-nav; viewport S2 | no |
| **3. Compact comparison** | layer B grid from `judgments.json`; cards under ~700px; disclosure buttons | mapping/staleness hash gate; keyboard/touch; print/fragment | no |
| **3b. Host TLDR (additive)** | above-fold `#host-tldr` from `host-tldr.md`: plain summary, official-vs-ours comparison, Host \| Status \| Why (Full/Partial/Unknown feature-parity chips since the S1 PR; Documented/Partial/Unknown at PR73; linked evidence) | 9 rows; allowed chips only; https link per Why; private-path guard; `--check` drift | no |
| **4. Acceptance / handoff** | Chromium viewports as PR70; Safari Reader; PM+UTL reader session; Astra at exact HEAD; vault | §8 gates recorded | no |

PR4 records: measured §8 values (Chromium + WebKit) in `acceptance-results.md`, reproducible with `tools/matrix_skim_check.mjs`; the deferred human steps (Safari Reader View pass, PM + UTL five-question test) and their templates in `acceptance-checklist.md`. S1 failed at PR4 HEAD and was recorded as a residual, threshold unchanged.

**S1 residual fix (branch `research/mcp-apps-matrix-pm-readable-s1`, after PR74):** (1) measurement: `matrix_skim_check.mjs` counts readable words, excluding fully clipped accessibility-only text that stays in the DOM (Astra PR74 P2); (2) IA: layer B `#status-by-product` moves behind a closed `<details>` ("Status by product — four questions per host"), layer C next steps trimmed to ≤150 words, generator-inputs line shortened, desktop meta tail no longer repeats the banner; (3) Haiyuan steers: `#host-tldr` gains a "Yes — this differs" official-vs-ours comparison table, and its chips become **Full / Partial / Unknown feature parity** (2 Full / 3 Partial / 4 Unknown), not documentation parity. Thresholds unchanged; values in `acceptance-results.md`.

## Order rule
No fold-only intermediate publish. Judgment + shipping action land in PR2 with preservation checks.

## Same URL
Canonical path stays `/research/builds/mcp-apps-feature-matrix/`.
