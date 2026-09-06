---
title: Board pack after spike merges - Plan
type: docs
date: 2026-09-05
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: user-request-and-joint-alignment
execution: code
---

# Board pack after spike merges - Plan

Prepared by Astra for Fable 5.1; implemented by Fable 5.1 on 2026-09-06 UTC (2026-09-05 PT). Evidence date: 2026-09-06 UTC. Target repo: `caohy1988/caohy1988.github.io`. Read with sibling `intent.md` and `spec.md`. Supersedes the earlier diagram-only plan, whose 2026-09-05 validation record is historical and not reused here.

## Goal Capsule

- **Objective:** Board-pack readers understand what the two merged spikes establish and what still requires a connected Finance pilot.
- **Means:** A bounded editorial update using the current story, comparisons and Technical design (KTD1–KTD3).
- **Authority:** This user request and JOINT's promotion rules govern; pinned spike evidence supports present-tense claims; prior board-pack docs supply retained presentation constraints. The obsolete diagram-only branch/review instructions are superseded.
- **Execution profile:** One documentation/static-page PR. No cloud workload, runtime implementation, SDK modification or spike rerun.
- **Tail ownership:** Fable implements and records fresh static QA. EM receives the PR/session handoff. Haiyuan alone decides merge. Astra's present turn stops with reviewed plans, session record and vault note.

---

## Product Contract

### Summary and problem frame

The live page treats the runtime uniformly as unbuilt and calls its demo receipts UNVERIFIABLE without naming the full-demo boundary. It also makes existing data placement irrelevant to the opportunity case. Two merged examples and JOINT's scoped alignment make those statements insufficient. Replacing them with a whole-product success claim would be equally inaccurate.

### Requirements

The normative R1–R11 and AE1–AE4 are in sibling `spec.md`; preserve their IDs when copying the handoff into the repository.

- R1–R2: retain the story, three comparisons and compact reader flow.
- R3–R7: carry scoped opportunity, distinct receipt/graph evidence, full-demo limitations and the connected promotion gate.
- R8–R10: carry GQL capacity and Preview boundaries through prose/diagram without changing disclosure or print behavior.
- R11: preserve canonical/redirect routing and make all four board-pack Markdown companions consistent.

**Success signal:** A reader can distinguish proposed Alder behavior from recorded Acme evidence without opening another page. Evidence links then permit inspection of each narrow claim.

### Scope boundaries

Edit `rfc/board-pack/index.html`, `STORY.md`, `intent.md`, `spec.md`, `plan.md`; allow `styles.css` only for wrapping, focus, spacing or print adjustments required by the new text. No move/rename, RFC root rewrite, new graph landing page, cloud operation or runtime change. Preserve full-demo and both merged spikes byte-for-byte.

Deferred to follow-up work: connected retrieval-to-result pilot, graph G6/G7 live negatives, G8 benchmarks and customer budget acceptance. These are evidence gates, not tasks to implement in this PR.

---

## Planning Contract

### Key technical decisions

- KTD1. **Revise claims in place.** Put the compact assessment in `.runtime-heading`, short evidence in existing comparison notes and technical details in the existing disclosure. This keeps the page's story order and avoids reviving a footer dump (R1–R7).
- KTD2. **Use immutable GitHub evidence links.** E1–E5 map directly to both merged PRs, their reviewed artifacts and the approval comment. The graph Pages directory is currently 404; it must not become the evidence destination (R4–R5, R11).
- KTD3. **Keep the diagram hypothetical.** Update shared labels, both accessible descriptions and visible notes together. Preserve the native details/adjacent-body CSS arrangement because it makes closed-state print work across engines (R8–R10).
- KTD4. **Replace stale companion docs together.** Copy the handoff's three documents into the implementation branch and reconcile `STORY.md`; remove old branch names, old review gates and apparent current QA successes from the former diagram plan. Retain history only when explicitly dated (R11).

### Baseline and branch

Inspection baseline: latest fetched `origin/main` was `b05e278b0c459f3dc035d7cae48841c75d6fa89f`, containing PR 28. Board-pack files and redirect matched the local tracked versions; live `index.html` matched as well. Receipt worktree was exactly `6719eb535667963fa640dd4535e508b550eb6cb1`. GitHub confirmed both merges and heads.

Implementation branch: `feat/board-pack-post-spike`, created by Fable in a separate worktree from fetched `origin/main` at `b05e278b0c459f3dc035d7cae48841c75d6fa89f` (no prior branch of that name existed locally or on origin). The shared checkout and its untracked files were not touched.

### Decisions resolved from evidence

Receipt MODERATE is supported by E2 and the final-head review; it covers the trusted consumer boundary, not an arbitrary verifier return value or a product API. Graph's report offers a separate retrieval-only MODERATE assessment, which the page must attribute to that report. Governance/publication consistency and customer operating budgets remain unproven. A new real-data or cloud run is unnecessary for this editorial change.

The first-workload option remains architecturally possible on Enterprise/Plus after projection, but must be marked outside the HIGH-scoped facts-already-in-BigQuery case. No fact about fictional Alder's warehouse placement is inferred. The 700-word closed-state ceiling is an editorial allowance for the evidence delta, not a measured comprehension claim.

---

## Implementation Units

### U1. Align the visible brief and its source narrative

**Goal:** Make the closed page accurately describe the post-spike opportunity and delivery boundary.

**Requirements:** R1–R8, R11; AE1, AE4. **Dependencies:** None.

**Files:** `rfc/board-pack/index.html`, `rfc/board-pack/STORY.md`, `rfc/board-pack/intent.md`, `rfc/board-pack/spec.md`, `rfc/board-pack/plan.md`.

**Approach:** Apply `spec.md`'s copy map to the runtime introduction, comparison notes, capacity line, punchline and pilot. Update STORY's existing-data-placement and blanket-unbuilt passages. Copy the three handoff documents into their matching repo paths, correcting only implementation-specific details backed by the resulting diff. Keep the hero unchanged and the three advantages distinct.

**Verification:** Compare the hero bytes to the implementation base. Trace each present-tense claim to E1–E6 and check every rating's adjacent scope. Confirm existing-data-placement language no longer contradicts R3. Review AE1/AE4 from the closed page. No new unit test file: this is editorial content; claim review and rendered inspection are the relevant checks.

### U2. Align the expanded design and diagram

**Goal:** Keep the architecture useful without implying a connected deployed system.

**Requirements:** R4–R10; AE2. **Dependencies:** U1.

**Files:** `rfc/board-pack/index.html`; `rfc/board-pack/styles.css` only if needed.

**Approach:** Update `.design-status`, `.design-intro`, the three design sections, shared SVG nodes, both SVG descriptions and `.plot-note`. Add the short checkpoint/evidence prose within the existing design body. Preserve policy-before-disclosure, the distinction between selected SQL and executed results, and current authorization at replay. Follow the existing shared-node and monochrome print patterns.

**Verification:** Review AE2 in both diagram layouts and in print. The same scope must be conveyed visually and through accessible descriptions. No merged-evidence badge may attach to Alder's 96% or to the combined chain. Confirm G6/G7 and G8 do not acquire pass labels. No new runtime test: no runtime behavior changes.

### U3. Verify the static page and prepare the one-PR handoff

**Goal:** Deliver a reviewable update with working links and preserved reading behavior.

**Requirements:** R1–R11; AE1–AE4. **Dependencies:** U1, U2.

**Files:** The U1/U2 file set; QA and session evidence remain under `/tmp/okf-boardpack-update/`.

**Approach:** Run the Verification Contract, fix only issues in the allowed page scope, then prepare one PR against main. Record the base/head, PR URL, actual validation and remaining limits in the session handoff and a dated vault note. Do not treat old diagram QA or historical spike tests as fresh validation. Merge remains with Haiyuan.

**Verification:** The PR diff contains only the stated files; the redirect, RFC index, full-demo and spike artifacts are unchanged. All QA work finishes before reporting completion. Do not finish while tests or a required commit/push are pending.

---

## Verification Contract

Astra inspected source/evidence and links during planning. Fable ran the checks below on the implementation branch; results are in the Validation record.

| Check | Required evidence |
| --- | --- |
| Content audit | R1–R11 and AE1–AE4 checked; old “every receipt/unbuilt” claims properly scoped; no new production, connected, ATTESTED or accounting-correctness claim. No unqualified HIGH or MODERATE label. |
| Scope/diff | Hero unchanged from actual branch base; canonical and redirect preserved; allowed files only; `git diff --check` passes. Compare preserved paths to base. |
| Desktop/mobile | At 1280, 768, 375 and 320 px, details open/closed: no horizontal overflow or clipped SVG text, one visible diagram, each comparison pair stays together. Record closed word count/height and inspect representative screenshots. |
| Keyboard/accessibility | Skip link, visible focus, native Enter/Space disclosure, meaningful evidence link text; unique/resolving SVG IDs and title/description references. |
| Print | From a closed disclosure, the design, wide diagram, evidence qualifications and pilot print in monochrome. Check Chromium PDF visually plus Firefox/WebKit print-media visibility; record any unavailable engine rather than claiming a pass. |
| Navigation/evidence | Canonical direct visit, RFC index and legacy redirect work; E1–E5 resolve to the intended PR or pinned artifact. Do not link the known-404 graph directory. No console/network error caused by page changes. |
| Completion record | Record actual base/head, PR URL, QA results and vault note in `sessions.json`, preserving other agents' entries. No deployment or merge claim. |

No SDK/graph test suite, cloud benchmark, paid reservation or new unit test suite is required for this static editorial update.

---

## Definition of Done

The three comparisons and hypothetical story remain recognizable; the full-demo and spike evidence are clearly separated; opportunity/delivery labels follow JOINT; technical details and diagram agree; all Verification Contract checks pass or their concrete limitations are reported for review. The diff has no abandoned experiments or unrelated changes. One PR, its actual QA record and a vault note are available to EM/Haiyuan. The PR is unmerged.

Planning handoff sources: JOINT final at `/tmp/okf-bqgraph-debate/JOINT_final.md` (identical to `/tmp/okf-spikes/JOINT_final.md`); vault `Ship/rfc/2026-09-06-spike-*`, final receipt review at `6719eb5`, graph fix-pass-4 note, and `Ship/builds/2026-09-06-spike-graph-pr28-merged.md`. Public evidence URLs are indexed in `spec.md` E1–E6. The requested local paths are intentional EM handoff pointers; production page links use only public URLs.

---

## Validation record (Fable, 2026-09-06 UTC)

Static-page checks on the implementation branch, served locally from the worktree. These are page checks; historical spike test results are not restated as fresh validation.

- **Scope/diff.** Only `rfc/board-pack/{index.html,styles.css,STORY.md,intent.md,spec.md,plan.md}` changed. The `.hero` section is byte-identical to `b05e278`. `rfc/bq-vp/index.html`, `rfc/index.html`, `rfc/full-demo/` and `rfc/spikes/` are unchanged. `git diff --check` passes. No authored JavaScript, external assets or build steps were added.
- **Content audit.** R1–R11 traced: HIGH carries its scope and the unaccepted envelope in the runtime assessment; combined LOW and receipts MODERATE (one merged example) appear in the closed skim; G6/G7 PARTIAL, distinct-principal BLOCKED, G8 INCOMPLETE 0/9 and the recorded reservation teardown sit in the expanded design; full-demo stubs/UNVERIFIABLE are stated separately from the example; GQL Enterprise/Plus appears at the first-workload line, the plot note, `#plot-query` and both SVG descriptions; the punchline and pilot are qualified and do not use 96% as a real-data target.
- **Engines.** Chromium, Firefox and WebKit (Playwright-managed builds) pass at 1280, 768, 375 and 320 px with the disclosure closed and open: no horizontal overflow, one visible diagram layout when open, evidence links and the assessment block within the viewport, each KC + OKF / + BQ runtime pair stacked together on narrow widths, no duplicate IDs, all `use` references resolve, no SVG node label exceeds its rect, both SVG title/description pairs resolve and mention the proposed connected design, Enterprise capacity, consumer enforcement and the illustrative outcome. No console, page or request errors.
- **Closed state.** 639 visible words (Chromium; identical in Firefox and WebKit) and 1,968 px tall at 1280 × 720; open state 3,761 px. (Re-measured after the Opus nit pass; the first pass recorded 637 words and 3,697 px.) Three evidence links are reachable without expanding the design: graph spike report, receipt example report and merged SDK PR 479.
- **Keyboard.** Native Enter and Space toggle the disclosure with a visible focus ring; evidence links inside the dark section focus with a visible ring (`#e2c493`).
- **Print.** With the disclosure closed, print media in all three engines shows the design body, the wide diagram, the evidence-and-checkpoint section and the pilot; the narrow diagram is hidden; assessment text and node fills render in monochrome. Chromium A4 PDF and print-media screenshot saved under `/tmp/okf-boardpack-update/qa/`. The Safari app itself was not tested, only Playwright WebKit.
- **Navigation/evidence.** `/rfc/bq-vp/` redirects to `/rfc/board-pack/`; `rfc/index.html` still labels the page **Board-pack near-miss →**. All 13 external evidence URLs in the page (E1–E6 targets) returned HTTP 200 on 2026-09-06; the known-404 graph Pages directory is not linked.
- **Screenshots and results.** `/tmp/okf-boardpack-update/qa/` (`check.cjs`, `results.json`, Chromium PNGs per viewport/state, `chromium-closed-print.pdf`). Reviewed visually at 1280 closed, 320 closed/open and print media.

Opus review (2026-09-06): APPROVE with four non-blocking nits, all applied in the follow-up commit: meta description shortened to 164 characters; clear antecedent for the full demo's UNVERIFIABLE receipts; accurate gate wording in the retrieval design section instead of the G1–G5 shorthand; explicit MODERATE+ downgrade target for the scoped opportunity, kept distinct from the serving-tier MODERATE+. Three-engine QA re-run passed.

Not done: no cloud run, no spike rerun, no merge. Haiyuan retains the merge gate.
