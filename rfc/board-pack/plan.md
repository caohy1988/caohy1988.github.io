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

## Validation record — tone pass (Fable, 2026-09-06 UTC, `feat/board-pack-human-tone`)

Scope: `rfc/board-pack/{index.html,STORY.md,intent.md,spec.md,plan.md}` only. `styles.css`, the `.hero`, `rfc/bq-vp/index.html`, `rfc/index.html`, `rfc/full-demo/` and `rfc/spikes/` are unchanged. No authored JavaScript, external assets or build steps.

- **Content audit.** Visible prose contains none of: HIGH, MODERATE, LOW, PARTIAL, BLOCKED, INCOMPLETE, INCONCLUSIVE, UNVERIFIABLE, UNPROVEN, JOINT, spike, PR 479, PR 28, G1–G8, SDK, HMAC, worktree, commit hashes or reviewer names (grep over `index.html` and `STORY.md` excluding `href` values). The E2, E5 and E6 URLs are unchanged behind plain link text; E1, E3 and E4 remain linked inside the expanded design. The substantive limits are all still stated in plain words: no agreed customer budget, recorded examples only, connected path still to prove, wider-demo receipts not yet verifiable, graph access checks unfinished, benchmarks 0 of 9.
- **Engines.** Chromium, Firefox and WebKit pass at 1280, 768, 375 and 320 px, closed and open: no overflow, one visible diagram when open, pairs together on narrow widths, no duplicate IDs, all `use` references resolve, no SVG label (including the renamed `NOT PROVEN · WITHHELD` and `SQL / bounded graph walk`) exceeds its rect, both SVG descriptions still name the proposed connected design, Enterprise capacity, consumer enforcement and the illustrative outcome. No console, page or request errors. Native Enter/Space toggle with a visible focus ring; comparison-note links focus with the `#e2c493` ring.
- **Closed state.** 700 visible words (identical in all three engines), 2,007 px tall at 1280 × 720 in Chromium (1,986 WebKit); open state 3,814 px. Two evidence links reachable without expanding: the recorded graph walk and the recorded receipt check.
- **Print.** Closed-state print media in all three engines shows the design body, wide diagram, evidence section and pilot; narrow diagram hidden; monochrome fills. Chromium A4 PDF saved.
- **Navigation.** `/rfc/bq-vp/` still redirects to `/rfc/board-pack/`; `rfc/index.html` still labels the page **Board-pack near-miss →**.
- **Artifacts.** `/tmp/okf-boardpack-tone/qa/` (`check.cjs`, `results.json`, Chromium PNGs per viewport/state, crops of the assessment block, diagram and evidence section, `chromium-closed-print.pdf`).

Not done: no cloud run, no experiment rerun, no merge. Haiyuan retains the merge gate.

## Later questions slice (Fable 5.1, 2026-09-06 PT, `feat/board-pack-ask-later` from `origin/main` `9182405`)

**Scope:** Astra's Slice 1 ("Three later questions in the board pack"), chosen first by Haiyuan over the full-RFC §07 table. Files: `rfc/board-pack/{index.html,STORY.md,intent.md,spec.md,plan.md}`. Unchanged: `styles.css`, SVGs, `rfc/index.html`, `rfc/bq-vp/`, `rfc/full-demo/`, `rfc/spikes/`. No authored JavaScript, external assets, build steps, cloud runs or experiment reruns.

**Change:** one `section#later-questions` after `.comparison` closes and before the capacity line, built from the existing `.runtime-rule` and `.comparison-note` classes: a lead line, three question/answer lines in the order of the three comparisons, and one boundary sentence (105 words). Companion docs carry the dated scope (`intent.md`), R12–R14 and acceptance (`spec.md`) and the later-audit beat (`STORY.md`).

### Validation record

Static checks served from the worktree with Playwright-managed Chromium, Firefox and WebKit; artifacts under `/tmp/okf-boardpack-later/qa/` (`check.cjs`, `results.json`, Chromium PNGs per viewport/state, panel crops, `chromium-closed-print.pdf`, print-media screenshot).

- **Acceptance 1 (story intact).** `.hero` is byte-identical to `origin/main`. Three `.comparison-point` sections; the punchline, pilot ask, illustrative label, 118%/96% and $4 million are unchanged. No experiment is said to have produced Alder's number.
- **Acceptance 2 (mapping, self-contained).** Lines 1–3 correspond to `#context-point` / `#design-context`, `#access-point` / `#design-access`, `#execution-point` / `#design-execution`. The panel adds no links, so no fragment navigation into the closed design body. `aria-labelledby` resolves; no duplicate IDs in any engine.
- **Acceptance 3 (conditional wording).** "could ask" / "would identify"; "goals for the connected pilot"; "holds only while that evidence is retained and the reader is permitted to see it now"; "none explains the model's private reasoning". Grep over `index.html` and `STORY.md` (excluding `href` values) finds none of: Semantica, Palantir, causal, decision graph, guaranteed, forever, always, six-month, or the scoreboard labels HIGH / LOW / MODERATE / PARTIAL / BLOCKED / INCOMPLETE / UNVERIFIABLE.
- **Acceptance 4 (QA).** 1280 px and 320 px, disclosure closed and open, in all three engines: no horizontal overflow; the panel sits between the comparison block and the capacity line; no page or console errors. Native Enter opens and Space closes the disclosure with `.technical-design[open] + .design-body` intact. Print media with the disclosure closed: panel `display: block`, text `#333`, border `#aaa`, 8pt; the design body still prints. Closed state: 805 visible words (all engines), 2,163 px tall at 1280 × 720 in Chromium (2,165 Firefox, 2,142 WebKit); open state 3,970 px. The closed skim is 105 words over the tone pass's 700; Astra's plan accepts about 100 words for this panel, so the copy was not shortened further.
- **Acceptance 5 (diff).** `git diff --name-only` lists only the five files; `git diff --check` passes.

Not done: no cloud run, no experiment rerun, no merge. Haiyuan retains the merge gate. Full-RFC evidence map (Slice 2) and auditor acceptance cases (Slice 3) are separate later work.

## PR 33 honesty slice (Fable 5.1, 2026-09-06 PT, `feat/board-pack-pr33-honesty` from `origin/main` `bb88df4`)

**Why:** PR 33 (merge `bb88df4`, head `114e81a`) was a fresh live pass: five distinct-principal negatives MEASURED under the impersonated `sa:okf-receipt-restricted` on the relational fallback engine, teardown VERIFIED. The board pack and three full-RFC sentences still said the two-requester tests "could not run". Spec R5 forbids treating merge status as a live pass; this was a live pass, so the pack was wrong, not merely incomplete. JOINT (Fable + Astra, 2026-09-06 ~13:43 PT) ranked this correction first, ahead of the connected graph→receipt chain.

**Scope:** `rfc/board-pack/{index.html,STORY.md,intent.md,spec.md,plan.md}` plus the three short handoff notes `intent-pr33-honesty.md`, `spec-pr33-honesty.md`, `plan-pr33-honesty.md`, and in `rfc/index.html` only the two-requester sentences: the explainable-access "Where the evidence stands" paragraph, the current-evidence note's access paragraph, and the Phase 3 "Still required as evidence" cells in the phase table and the phase drill (the table cell was included so the two Phase 3 cells agree); after review, also the comparison-table caution note and the current-evidence graph-walk link (re-pinned so a reader does not land on the pre-addendum report). Unchanged: `styles.css`, SVGs, `#later-questions`, `.hero`, capacity line, `.punchline`, `.ask`, 2026-09-19 checkpoint text, `rfc/bq-vp/`, `rfc/full-demo/`, `rfc/spikes/`, and every other full-RFC paragraph (its remaining `b05e278` report links in untouched paragraphs are dated history). No cloud run, no experiment rerun, no styling.

### Claim-to-source map

| Reader-facing claim (this branch) | Source at `bb88df4` |
| --- | --- |
| "A separate restricted identity passed five denial checks on the SQL path, not yet inside graph queries" (`#access-point` note); "speed benchmarks and graph-query access checks are still to come" (`#context-point` note) | `evidence/authz_cases.json` line 4 `engine: fallback`, line 540 summary (five MEASURED), line 501 `gql_variant` BLOCKED; `evidence/summary.json` 0/9 |
| `#design-access`: five named checks (hidden intermediate stayed hidden; denied bundle returned no denied node or section identifiers in reply or error text; output withheld while the seed store stayed readable by a plain row count with search denied; no owner-credential fallback; revocation before cached replay failed closed); graded behind an allowed request; temporary grants removed and read back | `authz_cases.json` cases `hidden_intermediate` ENFORCED, `denied_bundle` DENIED_NO_LEAK (`leaked_id_count` 0 against the denied content-id set; `scope.bundle_id` / `publication_id` and the project/dataset/table in `api_error_redacted` are retained, so the claim is scoped to denied node/section ids), `output_denied_seed_visible` (`seed_visibility_evidence`: row count of `section_vectors`, not `VECTOR_SEARCH`; probe 19 vectors / 0 nodes / 0 edges; forced seed NO_SEED, `natural_seed` DENIED with 0 hits), `owner_fallback_negative` NO_FALLBACK, `revocation_before_cached_replay` FAIL_CLOSED; `allowed_control` line 522; `teardown` line 458, VERIFIED line 494; README "Second principal (2026-09-06)" |
| "have not yet run inside graph queries, which need an Enterprise capacity window this run could not open" | `gql_variant.reason` (bounded window lifecycle for both clients not wired; window gate refuses on unreconciled legacy job journal); README lines 55–58 |
| "Under the operator's own identity we still could not confirm that no hidden identifiers leak" | `evidence/report.md` G6 rows: authorized-views and RLS no-leak INCONCLUSIVE (substring detector, payload not retained, no re-run) |
| "protection across mixed publications is not proven live" | `evidence/report.md` G7 PARTIAL |
| "cover three of those tests in isolation, not yet as part of one chain" (`#design-evidence`) | connected chain not run (`comparison.md` row 1, BigQuery Graph: second principal MEASURED on relational fallback; row 2, KC + ordinary SQL/vector: fixture-driven discovery, connected KC evidence unproven); promotion rule unchanged |
| "temporary grants on one fixture, removed and read back… a narrower cleanup record than the reservation teardown" | `teardown.steps` remove_dataset_reader / restore_policies ok; `reservation_changes.json` unchanged since `b05e278` |
| Historical: "run on a measured Enterprise reservation on 5 September 2026" (STORY) | `evidence/report.md` 2026-09-05 rows kept above the line-159 addendum |

Link pins: every graph link inside the touched paragraphs now points at merge `bb88df4` (tree identical to head `114e81a` for `rfc/spikes/bq-graph`; `summary.json` and `reservation_changes.json` are byte-identical to `b05e278`, so no history is lost). New links: `evidence/authz_cases.json` and `README.md#second-principal-2026-09-06`. Receipt links stay at `6719eb5`. Spec E4/E5 keep their dated `b05e278` pins; E7 records the new pin.

Earlier validation records above (2026-09-06 UTC post-spike, tone pass, later-questions slice) are historical for this branch; their "distinct-principal BLOCKED" content audit lines describe the page as it was at those commits and are not restated as current.

### Validation record (Fable 5.1, 2026-09-06 PT)

Static checks served from the worktree with Playwright-managed Chromium, Firefox and WebKit (Playwright 1.58.2); artifacts under `/tmp/okf-bp-pr33/qa/` (`check.cjs`, `results.json`, `run.log`, Chromium PNGs at 1280/320 closed/open, `chromium-closed-print.pdf`, print-media screenshot).

- **Claims.** No unqualified current claim that the two-requester tests could not run survives in the five board-pack files or `rfc/index.html`. A grep for "could not run" / "two different requesters" still matches five lines on purpose: the `spec.md` tone-map row marked historical, and self-describing sentences in `spec.md` (R15 acceptance), `intent.md` (PR 33 addendum) and `plan.md` (this section) that quote the wording being replaced. Those are kept as dated history, not deleted to make the grep pass. Visible prose of `index.html` and `STORY.md` (href values and Markdown link targets stripped) contains none of: HIGH, MODERATE, LOW, PARTIAL, BLOCKED, INCOMPLETE, INCONCLUSIVE, MEASURED, VERIFIED, UNVERIFIABLE, PR numbers, spike, JOINT, gate codes, SDK, HMAC, service-account names or commit hashes. Remaining gaps stated in plain words: graph-query checks still to come, operator-identity hidden-identifier check unconfirmed, mixed publications unproven, 0 of 9 benchmark cells, no agreed budget, connected path unproven, three checks in isolation not as one chain.
- **Protected content.** `.hero`, `#later-questions`, the capacity line, `.punchline` and `.ask` are byte-identical to `bb88df4`. Page order unchanged; no new section, ID or class; `styles.css` and SVGs untouched.
- **Links.** All seven distinct new/re-pinned GitHub URLs (report, comparison, summary, reservation changes, authz cases, README, spike tree at `bb88df4`) returned HTTP 200 on 2026-09-06; every target path exists in the `bb88df4` tree (`git cat-file -e`); the README heading `## Second principal (2026-09-06)` exists at that pin, giving the `#second-principal-2026-09-06` fragment.
- **Engines.** Chromium, Firefox and WebKit at 1280 and 320 px, disclosure closed and open: no horizontal overflow (scroll width equals viewport), no duplicate IDs, panel order intact between the comparison block and the capacity line, no page or console errors. Native Enter opens and Space closes the disclosure (`#technical-design-body` display block → none). Print media with the disclosure closed: later-questions panel `display: block`, text and strong `#333`, border `#aaa`, design body still printed; Chromium A4 PDF saved.
- **Closed state.** 813 visible words in all three engines (805 + 8 from the two comparison-note swaps); 2,181 px tall at 1280 × 720 in Chromium (2,183 Firefox, 2,160 WebKit); open state 4,134 px Chromium. The word ceiling is amended to 820 in `spec.md` with this slice.
- **Diff.** `git diff --check` passes; changed tracked files are the five board-pack files and `rfc/index.html`; the three `*-pr33-honesty.md` handoff notes are added.

Not done: no cloud run, no experiment rerun, no merge. Reviewers: Astra (mandatory, claim review against `report.md` / `authz_cases.json`) and Opus; Haiyuan retains the merge gate.

### Review fix pass (Fable 5.1, 2026-09-06 PT, same branch)

Astra (4 P2) and Opus (APPROVE, 4 P2) reviewed `9a95197`; both found no P0/P1. All eight P2s applied as wording and link corrections, no spike rerun:

- **Seed visibility** (`#design-access`, `STORY.md`, full-RFC access paragraph, claim map): "starting point was visible" became "the seed store stayed readable to that identity by a plain row count (search itself was denied)", matching `seed_visibility_evidence` (row count of `section_vectors`, not `VECTOR_SEARCH`; forced seed NO_SEED, natural-language seed DENIED with 0 hits).
- **Identifier scope** (same loci plus `intent.md`): "no identifiers" became "no denied node or section identifiers"; the judge checks the denied content-id set, and `scope.bundle_id` / `publication_id` plus the project/dataset/table in the redacted API error are retained. Wording correction only; no new leak was found.
- **Artifact provenance** (`intent.md`): dropped "on failure paths only"; the merged harness also merges per-observation fields on successful returns and records `restore_policy_<table>` steps unconditionally. Retained boundary: live artifact from `0d07e47`; later passes hermetic-only, no new live measurements.
- **Validation grep** (above, and the PR body): restated as "no unqualified current claim survives", with the historical and self-describing matches listed rather than deleted. URL count corrected from eight to seven.
- **Claim map**: `comparison.md` row 1 (second principal MEASURED) split from row 2 (connected KC evidence unproven).
- **Full RFC**: the `#current-evidence` graph-walk link and the comparison-table caution note re-pinned to `bb88df4` so a reader no longer lands on the pre-addendum report one paragraph before the corrected text; the caution note now says "access checks inside graph queries and publication checks remain unfinished". Other `b05e278` report links (untouched paragraphs) remain dated history.

Re-verification after the fixes: three-engine Playwright at 1280/320 closed/open passed again (813 closed-state words in all engines, 2,181 px Chromium; open 4,134 px; no overflow, duplicate IDs or console errors; Enter/Space toggle and closed-state print intact). Visible-prose banned-label grep: zero hits. Seven distinct `bb88df4` URLs across the changed pages. `git diff --check` clean. Protected blocks unchanged. Not done: no cloud run, no merge; Haiyuan retains the merge gate.

## PR 35 chain honesty slice (Fable 5.1, 2026-09-06 PT, `feat/board-pack-chain-honesty` from `origin/main` `157ec6d`)

**Why:** PR 35 (merge `157ec6d`, head `59fada0`) ran the graph → receipt chain as one path on Acme: fixture seed → pinned publication → governed retrieval (declaration + SQL) → bind by data files → SDK receipt CLI under the caller → consumer, with two substitutions refused; live `CHAIN_CONNECTED` on the relational fallback engine, same requester. The board pack still said "nothing has yet run as one connected path" and "no part of it has run as one connected path". Those were true at `bb88df4` and are stale now. JOINT ordered this correction next after (B).

**Scope:** `rfc/board-pack/{index.html,STORY.md,intent.md,spec.md,plan.md}` plus the three handoff notes `intent-chain-honesty.md`, `spec-chain-honesty.md`, `plan-chain-honesty.md`. In `index.html`: `.runtime-assessment`, the `#execution-point` note, both SVG `<desc>` elements, `.plot-note`, `.design-intro`, the `#design-context` limits sentence, the `#design-access` closing sentence, one new `#design-chain` section ("Run the three as one chain") between execution and evidence, and two sentences in `#design-evidence`. Unchanged: `styles.css`, SVG geometry, `#later-questions`, `.hero`, capacity line, `.punchline`, `.ask`, checkpoint text, `rfc/index.html` (full-RFC chain wording is JOINT item C), `rfc/bq-vp/`, `rfc/full-demo/`, `rfc/spikes/`. No cloud run, no experiment rerun, no styling.

### Claim-to-source map

| Reader-facing claim (this branch) | Source at `157ec6d` |
| --- | --- |
| "one chain that joins governed retrieval to that receipt check on invented Acme data and refuses a swapped query" (`.runtime-assessment`); "that check was fed by retrieval rather than by hand" (`#execution-point` note) | `evidence/chain/chain_live.json` `verdict: CHAIN_CONNECTED`, `decisions` approved RELEASED / sql-substitution REFUSED / declaration-mismatch REFUSED; `bundle_id: acme_retail` |
| "began from a starting point we chose by hand, not from live catalog discovery" | `chain_live.json` `seed.mode: fixture`, `seed.query: forced:metrics/gross-margin.md`, note "live Knowledge Catalog discovery is out of scope"; README step 1 |
| "ran under one requester" / "the 14 retrieval and receipt jobs we checked shared one requester" | `chain_live.json` `requester.mode: same-requester`, `same_requester.jobs` 14 entries all `operator` (12 graph + 2 receipt), `graph_jobs: 12`. Not "every job": the live artifact is runner `chain/0.2.0`, whose identity set excludes the pointer-lookup job that precedes the provenance gate (README labels paragraph; report addendum "joined the identity set in runner `chain/0.3.0`, after this pass") |
| "checked that they matched the receipt example's pinned copy: same file hash, same SQL text, same parameters, same source pin" | `cases[approved].bind.checks` file_sha256 / sql_text / parameters / source_pin all `ok: true`, `status: BOUND` (ten checks) |
| "ran the job under the caller and verified it in its own process"; "released the number only after that check passed and the receipt's digest matched the bytes retrieval had handed over" | README steps 5–6 (subprocess CLI at `6719eb5`, independent verifier, `computation_digest` recomputed); report addendum "receipt job … VERIFIED / MATCH … consumer RELEASED `$400.00 USD`" |
| "a different formula executed in place of the declared one, caught by the verifier" | `sql-substitution`: `REJECTED sql_mismatch`, exit 2, acceptance `MET` |
| "a different calculation offered by the graph side, caught before anything ran" | `declaration-mismatch`: bind `MISMATCH` on file_sha256 / sql_text / path / parameters, CLI never invoked, acceptance `MET` |
| "ran twice: once with local stand-ins in place of BigQuery, and once live against BigQuery in 23 seconds" | `chain_hermetic.json` (`engine: oracle`, local graph oracle + SDK SYNTHETIC API emulation, runner `chain/0.4.0`, `CHAIN_CONNECTED`; nothing emulated BigQuery on the retrieval leg); `chain_live.json` `started_at` 21:52:18Z → `finished_at` 21:52:40Z; report addendum "23 s end to end" |
| "Retrieval used plain SQL on demand, not graph queries"; "joins governed retrieval to the receipt check", "used plain SQL retrieval rather than the graph walk", "not from this walk" (the GQL walk of PR 28 is not part of the chain; the chain reached the computation in one hop on the fallback engine) | `chain_live.json` `engine: fallback`; README "relational fallback engine … not BigQuery Graph; `--engine gql` needs an Enterprise window this module does not open" |
| "the formula swap was the receipt example's fixed case, not Maya's total-ARR query" | README: "The CLI has no free-form case, so a 'total ARR' swap is not what executes" |
| "This run does not change the assessment above"; "Neither clears that bar, and together they do not yet either" | report addendum: "the combined-delivery verdict in the outcome section is for the JOINT checkpoint to revise, not this addendum"; `comparison.md` row 2 "connected KC evidence is unproven" |
| "adds nothing to these access questions" (`#design-access`); "the retrieval and calculation steps above as one chain … under one requester asking for its own data, so the access step was not exercised against a second identity or a policy decision" (`#design-chain`) | README: "`sa:okf-receipt-restricted` is not exercised by this chain"; `chain_live.json` `requester.mode: same-requester`, no negative access case in `cases` |
| "Retrieval read Acme's publication in BigQuery; the receipt ran on the receipt example's own small fixture dataset; the declaration file's hash is what joined the two" | `chain_live.json` `publication` (Acme projection, pointer `pub_190192147fd7fd78`), `sdk.synthetic_fixture: true`, `bind.checks.file_sha256` graph = sdk_bytes = sdk_manifest `5e96ae11…` |
| "All three experiments are merged and were reviewed" | PR 35 merged `157ec6d`; vault `Ship/rfc/2026-09-06-pr35-{astra,opus}-rereview*.md` |

Link pins: the three new chain links point at merge `157ec6d` (`evidence/chain/chain_live.json`, `README.md#connected-chain-2026-09-06`, `evidence/report.md#addendum-2026-09-06-connected-chain-fixture-seed-same-requester`). Existing `bb88df4` graph links and `6719eb5` receipt links in untouched sentences stay as dated history; the `evidence/chain/` tree is byte-identical between `59fada0` and `157ec6d`.

### Validation record (Fable 5.1, 2026-09-06 PT)

Static checks served from the worktree with Playwright-managed Chromium, Firefox and WebKit (the PR 33 `check.cjs` re-pointed at this worktree); artifacts under `/tmp/okf-bp-chain/qa/`.

- **Claims.** A grep for "nothing has (yet) run as one", "no part of it has run", "two separate/merged experiments" and "both experiments" over the five board-pack files matches only dated history and self-describing sentences: `intent.md` line 15 (the original 2026-09-06 UTC assessment, kept as the dated source) and the PR 35 addendum quoting the replaced wording, and `spec.md` R18 / its acceptance line. Visible prose of `index.html` and `STORY.md` (href values and Markdown link targets stripped) contains none of: HIGH, MODERATE, LOW, PARTIAL, BLOCKED, INCOMPLETE, INCONCLUSIVE, MEASURED, VERIFIED, UNVERIFIABLE, CHAIN_CONNECTED, MET, RELEASED, REFUSED, SDK, CLI, HMAC, JOINT, spike, PR numbers or commit hashes. R18 proximity was checked mechanically after the third fix pass (this record supersedes the narrower statements made after the first two passes, which are quoted in the fix-pass records below): every sentence in the visible prose of `index.html` and `STORY.md` (href values and Markdown link targets stripped) that contains the word "chain" or one of the paraphrases R18 lists ("narrower version", "exercised", "as one path", "joins governed retrieval", "end to end", "ran/run as one", "one path", "connected design") was printed with its neighbouring sentences and graded for fixture seed, one requester and plain SQL. All ten describing sites R18 lists pass within the same or next sentence. The complete list of hits that do not carry all three, each outside the rule for the reason R18 gives: the two bare cross-references "the connected chain below" (`#design-context`, `#design-access`); the "call it proven" bar text and its "that chain also needs tests" follow-on (index and STORY); the mid-narrative sentences inside `#design-chain` ("From there the chain read…", "The chain ran twice…", "What this chain does not show.") and inside the STORY chain bullet ("the chain read the pinned publication…") after their qualified openings; the `#design-access` sentence "A rule hidden in the middle of the chain stayed hidden" about the graph's links; the STORY sentence that the separate-identity checks ran "not as one chain"; and the protected pilot ask "Connect pinned retrieval, current authorization and result-bound consumption in one path", which describes the future pilot. The word-only audit of the second pass had missed the STORY diagram sentence, which carried fixture and requester but not plain SQL; the paraphrase scan found it and the third pass qualified it.
- **Protected content.** `.hero`, `#later-questions`, the capacity line (`p.runtime-rule`), `.punchline` and `.ask` are byte-identical to `157ec6d`. One new section ID `design-chain`; no other new ID or class; `styles.css` and SVG geometry untouched (only the two `<desc>` texts changed).
- **Links.** The three distinct new `157ec6d` URLs returned HTTP 200 on 2026-09-06; each target path exists in the `157ec6d` tree (`git cat-file -e`); the README heading `## Connected chain (2026-09-06)` (line 72) and the report heading `## Addendum 2026-09-06: connected chain (fixture seed, same requester)` (line 355) exist at that pin, giving both fragments.
- **Engines.** Chromium, Firefox and WebKit at 1280 and 320 px, disclosure closed and open: no horizontal overflow, no duplicate IDs, later-questions panel still between the comparison block and the capacity line, no page or console errors. Native Enter opens and Space closes the disclosure. Print media with the disclosure closed: panel `display: block`, text `#333`, border `#aaa`, design body printed.
- **Closed state.** 871 visible words in all three engines (813 + 58 from the runtime-assessment and execution-note edits); 2,223 px tall at 1280 × 720 in Chromium (2,224 Firefox, 2,200 WebKit); open state 4,675 px Chromium. The word ceiling is amended to 900 in `spec.md` with this slice.
- **Diff.** `git diff --check` passes; changed tracked files are the five board-pack files; the three `*-chain-honesty.md` handoff notes are added.

Not done: no cloud run, no experiment rerun, no merge, no `rfc/index.html` edit. Reviewers: Astra (claim review against `chain_live.json` / README / report addendum) and Opus; Haiyuan retains the merge gate.

### Review fix pass (Fable 5.1, 2026-09-06 PT, same branch)

Astra (CHANGES: 1 P1, 1 P2) and Opus (APPROVE: 4 P2, 3 P3) reviewed `8d1b74f`. All P1/P2 and two P3s applied as wording corrections, no spike rerun:

- **Every-job identity** (Astra P1, Opus P2 #3; `#design-chain`, `STORY.md`, claim map, PR body): "every job under one known identity" became "the 14 retrieval and receipt jobs we checked shared one requester". The live artifact is runner `chain/0.2.0`, whose identity set is the 14 case jobs; the pointer-lookup job before the provenance gate joined the set only in `chain/0.3.0`, and hermetic coverage cannot supply the missing live identity.
- **Local qualifiers on short mentions** (Astra P2; `#execution-point` note, `.plot-note`): both now carry the fixture seed, the single requester and the plain-SQL engine in the same sentence. R18 was tightened to name the short mentions and the checked identity set, and the validation "Claims" bullet above was corrected: the first pass had asserted R18 held when the two short mentions lacked the requester.
- **Graph walk is not part of the chain** (Opus P2 #1; `.runtime-assessment`, `.design-intro`, `#design-context` parenthetical, both SVG `<desc>`): "joins the two" became "joins governed retrieval to the receipt check"; every site now says retrieval used plain SQL rather than the graph walk (`engine: fallback`, `concept_hops: 1`), and "inside graph queries" is back on the closed-skim still-to-prove list.
- **Access step not exercised** (Opus P2 #2; `#design-chain`, `STORY.md`): "the three steps above as one chain" became "the retrieval and calculation steps above as one chain, under one requester asking for its own data, so the access step was not exercised against a second identity or a policy decision", agreeing with the `#design-access` closing sentence.
- **Copy-map drift** (Opus P2 #4; `spec.md`): the Combined-delivery and graph-score rows are marked historical with the R18/R19 wording that supersedes them; the `NOT_EXECUTED` row notes the current index wording.
- **Hermetic wording** (Opus P3 #5): "against an emulated BigQuery" became "with local stand-ins in place of BigQuery" (oracle graph engine + SDK SYNTHETIC API emulation; nothing emulated BigQuery on the retrieval leg). **SVG gap attribution** (Opus P3 #6): "the full design with live catalog discovery has not" now lists discovery, a second identity and graph queries as all unrun. Added Opus's non-finding as prose: retrieval read Acme's publication in BigQuery, the receipt ran on the receipt example's own fixture dataset, and the declaration file's hash joined the two.
- Not applied: Opus P3 #7 (`rfc/index.html` still says "two separate worked examples") stays JOINT item C, outside this slice.

Re-verification after the fixes: three-engine Playwright at 1280/320 closed/open passed again (900 closed-state words in all engines, 2,241 px Chromium; open 4,755 px; no overflow, duplicate IDs or console errors; Enter/Space toggle and closed-state print intact). Visible-prose banned-label grep: zero hits. A grep for "every job", "three steps", "joins the two", "emulated" and "with live discovery" over the five board-pack files matches only self-describing rows in `plan.md` / `spec.md` and the untouched graph-walk bullet in `STORY.md`. Protected blocks byte-identical to `157ec6d`. `git diff --check` clean. Word ceiling amended to 920 in `spec.md`. Not done: no cloud run, no merge; Haiyuan retains the merge gate.

### Review fix pass 2 (Fable 5.1, 2026-09-06 PT, same branch)

Astra re-review of `81eb7d1` (CHANGES: 0 P0 / 0 P1 / 1 P2) and Opus re-review (APPROVE, 2 cosmetic P3). The P2 was a requirement/validation mismatch, not an evidence finding: R18 as tightened in the first fix pass demanded fixture seed, one requester and plain SQL in the same or next sentence of every chain mention, and the validation record claimed that held, but the `#design-chain` opening and the `STORY.md` chain bullet placed plain SQL several sentences later. Applied, wording only, no spike rerun:

- **Prose now satisfies R18 at every describing site.** `#design-chain` opening: "A starting point we chose by hand stood in for catalog discovery, and retrieval used plain SQL on demand rather than the graph walk" is now the second sentence, directly after the one-requester sentence. `STORY.md` chain bullet: same clause in the same position. `#design-evidence` bar sentence and the STORY bar sentence: "with a fixture in place of discovery, one requester and plain SQL in place of graph queries". Both SVG `<desc>` openings: "seeded by a fixture, under one requester and on plain SQL". `.design-intro`: the qualifier sentence moved to directly follow the chain claim. Neither Astra nor Opus flagged the last three; they were caught by the mechanical audit below and fixed so the rule and the page agree.
- **R18 rewritten to name its sites and its carve-outs.** It lists the nine describing sites and states that bare cross-references to `#design-chain` ("the connected chain below" in `#design-context` and `#design-access`) and the unchanged "call it proven" bar text are pointers, not descriptions.
- **Validation claim replaced** with what was actually checked at that pass: every sentence containing "chain" in the visible prose of `index.html` and `STORY.md` was printed with its neighbours and graded for the three qualifiers. The sentences without all three were the two pointers, the bar text, mid-narrative sentences inside `#design-chain` and the STORY bullet after their qualified openings, the unrelated "a rule hidden in the middle of the chain" in `#design-access`, and the STORY sentence "not as one chain" about the separate-identity checks. (Superseded by fix pass 3: the word-only scan could not find a description that paraphrases the chain, and the main validation record above had still said "the only" residuals were the pointers and bar text; both are corrected there.)

Re-verification: three-engine Playwright at 1280/320 closed/open passed again (900 closed-state words in all engines, unchanged because the closed-skim edits were inside SVG `<desc>` text; 2,241 px Chromium; open 4,776 px; no overflow, duplicate IDs or console errors; Enter/Space toggle and closed-state print intact). Visible-prose banned-label grep: zero hits. Protected blocks (`.hero`, `#later-questions`, capacity line, `.punchline`, `.ask`, the "call it proven" bar sentence) byte-identical to `157ec6d`. `git diff --check` clean. Not done: no cloud run, no merge; `rfc/index.html` stays JOINT item C; Haiyuan retains the merge gate.

### Review fix pass 3 (Fable 5.1, 2026-09-06 PT, same branch)

Astra re-review 2 of `1ff8a93` (CHANGES: 0 P0 / 0 P1 / 1 P2) and Opus re-review 2 (APPROVE, 2 cosmetic P3). The P2 was again a coverage/validation mismatch: R18's site list omitted the `STORY.md` "Optional design detail" diagram sentence ("a narrower version of its arrows … has been exercised once on Acme"), which describes the recorded chain with fixture and requester but without plain SQL, and which the word-only audit could not find because it does not contain "chain"; and the main validation record still said the only unqualified sentences were the pointers and bar text while the fix-pass-2 record listed more. Applied, wording only, no spike rerun, `index.html` untouched:

- **STORY diagram sentence qualified:** "(pinned publication to enforcing consumer, fixture in place of discovery, one requester, plain SQL in place of graph queries)".
- **R18 inventory and method extended:** ten describing sites; the audit scans for "chain" and for the listed paraphrases; the carve-outs are enumerated (pointers, bar text, sentences after a qualified opening, the graph-links sentence, the "not as one chain" sentence, the protected pilot ask "in one path").
- **Main validation record reconciled** with the complete residual list and the actual method; the fix-pass-2 record is marked superseded rather than rewritten.

Re-verification: the paraphrase-plus-keyword audit over `index.html` and `STORY.md` returns no describing site without all three qualifiers and no residual outside the enumerated carve-outs. `index.html` is byte-identical to `1ff8a93`, so the three-engine result recorded for fix pass 2 (900 closed-state words, no overflow, no duplicate IDs, keyboard toggle and print) stands, and the protected blocks remain byte-identical to `157ec6d`. Visible-prose banned-label grep on `STORY.md`: zero hits. `git diff --check` clean. Not done: no cloud run, no merge; `rfc/index.html` stays JOINT item C; Haiyuan retains the merge gate.

### Leadership readability pass (Fable 5.1, 2026-09-06 PT, `feat/lead-human-readability` from `aeee7b7`)

Wording only, both pages, one PR. No spike rerun, no cloud, no `styles.css` or SVG geometry change. Applied by exact-match replacement (each old string asserted to occur once): 14 replacements in `rfc/board-pack/index.html`, 10 in `rfc/index.html`. The full before/after map is in `spec.md`.

- **Protected blocks.** Board pack `.hero`, `#later-questions`, capacity line, `.punchline`, `.ask`, the "call it proven" bar sentence and all SVG geometry (every `svg`/`use`/`path`/`rect`/`text`/`marker`/`g` line with `<desc>` text masked) hash identically before and after. Full RFC: the nine PR 38 regions (`context_ref`, identity formulas, all `pre` blocks, SVG formula text, §04 decisions, §08 checklist, §09 phase table, §09 phase cards, §02 motivation) hash identically to `aeee7b7`. Zero lines containing `2026-09-19` or `19 September` appear in the diff.
- **R18.** The paraphrase-plus-keyword scan over the board pack's visible text (including SVG `<desc>`) finds every describing site with all three qualifiers in the chain sentence or the next one. Residuals are the enumerated carve-outs plus one new bare pointer in `.design-intro` ("The chain section below has the detail.").
- **Banned words / labels.** Added lines contain none of the banned words and no scoreboard label; the only case-insensitive hits are the lowercase verbs "verified", "released" and "measured" carried on replaced lines. The single arrow on an added line is the required "Board-pack near-miss →" label on the read-time line.
- **Links.** Every external href on a changed line returns HTTP 200 (twelve distinct URLs, all pre-existing pins). The new in-page anchor `#design-chain` resolves; no in-page anchor on either page is dangling; no duplicate ids.
- **Engines, board pack.** Chromium, Firefox and WebKit at 1280 and 320 px, disclosure closed and open: 913 closed-state words in all three (900 before; ceiling 920), 2,241 px tall closed at 1280 in Chromium (open 4,797), document overflow 0 throughout, Enter opens and Space closes the disclosure, no page or console errors. Print media with the disclosure closed still renders the design body and the later-questions panel.
- **Engines, full RFC.** Chromium at 1280, 768 and 320 px: document overflow 0; `#repro-ask-later` measures 876/876, 724/724 and 276 wrapper / 443 table (scrolls inside the wrapper); print media 876/876; new column headers render; no console errors.
- **Diff.** `git diff --check` clean; changed tracked files are `rfc/index.html` and the five board-pack files.

Not done: no cloud run, no experiment rerun, no merge. Haiyuan retains the merge gate.
