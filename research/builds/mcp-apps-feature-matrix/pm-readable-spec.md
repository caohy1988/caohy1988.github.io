# Spec — copy contract and field definitions (PR1)

Authoritative detail: Haiyuan-approved PLAN_v2 §3–§4 and §7 PR1. This file is the in-repo copy contract summary.

## Inputs (ownership)
| Input | Owns |
|---|---|
| `judgments.json` | every product sentence and every compact phrase (36 rows = 9 products × 4 questions) |
| `brief.md` | banner, aggregate judgment, shipping action, next-steps, headings (**added in PR2**) |
| `source.md` | layer D (v7 matrix, legend, columns, footnotes, takeaways, history) — **byte-stable in PR1–4** |
| `v7-preservation-baseline.json` | pinned hashes of evidence blocks + 81-link inventory |
| `copy-map.json` | verbatim sentences/phrases that must survive into later slices |

## Field definitions (layer B questions)

| Question id | Label | Answers permitted | Source rows in v7 |
|---|---|---|---|
| `vendor_docs` | Vendor documents Apps rendering? | Documented · Unknown | *Iframe / UI mount* VD clauses; *Extension advertised* VD clauses |
| `rendering_evidence` | Rendering evidence | Reported · Source pinned · Code found · Unknown | *Iframe / UI mount* HR, SS, LI clauses |
| `apps_control` | Apps control | User setting · Reported · Internal gate found · Unknown | *Apps switch / flag* |
| `without_apps` | Without Apps, what shows? | Reported · Source pinned · Code found · Unknown (phrase names trigger when source separates them) | *Fallback* |

Rows *Negotiated Apps version*, *Published capability checklist*, and *App-only visibility* stay in layer D. Visibility is one sentence in the shipping action.

## Derivation rule (P1-1)
Each compact field is a question with a fixed answer set. A human writes the answer from the exact clause(s) that address that question, records evidence kind + qualifier. **No first-token / strongest-token selection over a whole cell.**

Derivation row schema: see `judgments.json` `compact_rows[]` (`product`, `question`, `source_row`, `supporting_clauses`, `non_supporting_clauses_noted`, `evidence_kind`, `qualifier`, `phrase`, `cell_sha256`, reviewers).

## Counterexample fixtures (must pass schema tests)
1. **Cursor fallback** — cell starts `[VD generic]`; `without_apps` answer is **Reported** (HR plain text, 3.10.20, Jul 2026).
2. **VS Code mount** — cell starts `[VD inline]`; `rendering_evidence` answer is **Source pinned** (SS inline-only; not a release run).

## Forbidden on the page
- Status chips: Yes / No / supported / unsupported / Partial (as capability claims)
- Private receipt directory or file paths; “links to a receipt”
- Invented runs; upgrading Unknown to a positive claim

## Product label
Always spell **GitHub Copilot in VS Code** in row/card labels (source column remains `GitHub Copilot`).

## PR1 visual rule
No live rendered HTML layout change in PR1 beyond wiring files. Generator still builds from `source.md` only until PR2.
