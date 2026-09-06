# Intent — board pack after the two spike merges

Prepared by Astra for Fable 5.1, 2026-09-06 UTC / 2026-09-05 PT; implemented by Fable 5.1 on `feat/board-pack-post-spike` from `origin/main` `b05e278` the same day. Target: `caohy1988/caohy1988.github.io`, `/rfc/board-pack/`. Supersedes the earlier diagram-only intent (implemented 2026-09-05 on `feat/rfc-board-pack-diagram`).

## Reader outcome

A reader should understand Maya's near-miss, the three proposed runtime advantages, and exactly what the merged experiments now support. Preserve the short customer/runtime brief: story first, three paired comparisons, optional Technical design, a qualified punchline, and one Finance pilot ask.

Keep the invented Alder scenario intact: 8:55 a.m., Maya Chen, the $4 million existing-customer expansion proposal, the wrong 118% retention figure and corrected 96%. Keep the $10m / $9.6m / $2.2m arithmetic and the three unanswered questions. Missing access explanation is not proof of unauthorized access. Neither spike produced these retention figures: both use Acme gross-margin material, and neither ran this board-pack story.

## Position after the merges

**Opportunity: HIGH (scoped).** Carry JOINT's complete scope with the label: analytical agents whose relevant facts already live in BigQuery, using Enterprise or Enterprise Plus capacity, within customer-accepted latency, freshness, concurrency and cost budgets. This remains a conditional opportunity assessment; the spike has not established a customer-accepted operating envelope. The broader general Knowledge Catalog serving-tier opportunity is MODERATE+. Reassess the conditional HIGH at the existing 2026-09-19 evidence checkpoint; under JOINT's downgrade triggers the scoped opportunity falls to MODERATE+, and inconclusive measurements do not preserve it indefinitely.

**Combined delivery: LOW.** Two merged experiments do not constitute a connected runtime. Promotion requires KC discovery → pinned publication → governed retrieval → caller-delegated computation → result-bound receipt → enforced consumption, with publication consistency and negative authorization evidence.

**Receipt delivery: MODERATE for the demonstrated example only.** SDK PR 479 merged at `120da78`, reviewed head `6719eb5`. The report records a real caller-owned BigQuery job, result readback, fresh-process verification and consumer-enforced release, with substitutions and missing evidence handled separately. This is example code under `examples/okf_attested_computation/`, not a new SDK API, product release or independent service-principal attestation. Astra's final review says APPROVE; it discloses that Astra also authored the last fix.

**Graph evidence: a demonstrated retrieval slice, with substantial gaps.** Site PR 28 merged at `b05e278`, head `cf20d4a`. Its report assesses the passed gates G1–G5 (capacity, projection, retrieval, impact/stub backlog, and negative-fixture isolation cases) as supporting MODERATE for demonstrated graph retrieval only. Attribute that assessment to the report. G6 authorization and G7 publication consistency remain PARTIAL; distinct-principal graph tests remain BLOCKED; G8 benchmarks are INCOMPLETE, with 0/9 cells complete. The Enterprise reservation was torn down. Merging the artifacts is not production Graph-over-OKF or customer-envelope acceptance. *(2026-09-05 record at `b05e278`; the distinct-principal BLOCKED status is superseded on the relational fallback engine only by the PR 33 addendum below. GQL remains BLOCKED.)*

The two experiments followed **parallel-spike, receipts-gated** sequencing. The next connected pilot must preserve receipt progress independently of graph completion. A graph pass cannot compensate for a broken result-evidence boundary.

## Keep the three comparisons

1. **Replayable context:** KC discovers and OKF authors; a runtime selects linked context from a pinned projection with explicit, bounded semantics. The graph spike now supplies retrieval evidence, not evidence that the selected calculation ran.
2. **Explainable access:** current policy must gate retrieval and replay for an authenticated requester. The graph's partial governance results do not establish complete caller-specific authorization. Metadata visibility still does not grant source-file access.
3. **Verifiable execution:** a declared computation needs a job, authoritative result evidence and an enforcing consumer. The merged receipt example demonstrates a narrow version of this boundary. Full-RFC/demo computation attesters remain stubs and the full demo's receipts remain UNVERIFIABLE.

BigQuery's case is authority over its own execution and an integration opportunity. Other retrievers can call BigQuery and consume the same evidence; receipt construction is not an exclusive capability.

## Editorial and delivery boundary

Put short evidence links beside the relevant comparisons and fuller boundaries inside the existing Technical design disclosure. The closed skim must show the scoped opportunity, receipt-only advance and LOW combined delivery. Keep the illustrative diagram as a proposed design; identify Enterprise/Plus for GQL and make clear its arrows have not been exercised as one connected path. Preserve native keyboard behavior, mobile layouts, print inclusion and the removed footer.

The graph may be a first workload on Enterprise capacity after projection, but an empty-project adoption route sits outside the HIGH-scoped facts-already-in-BigQuery case. Do not add a new data-placement claim to fictional Alder.

Fable implemented one PR from `origin/main` `b05e278` on `feat/board-pack-post-spike`, using `spec.md` for copy and acceptance requirements and `plan.md` for file scope and verification. The three handoff documents were copied into `rfc/board-pack/` in that PR and `STORY.md` was reconciled. `/rfc/bq-vp/` remains a redirect. Haiyuan retains the merge gate.

Evidence URLs and exact revisions are in `spec.md`.

## Tone pass (2026-09-06, Fable 5.1, `feat/board-pack-human-tone`)

Haiyuan asked for the board pack to read as a human brief: no scoreboard labels (HIGH / MODERATE / LOW, PARTIAL, BLOCKED, INCOMPLETE, UNVERIFIABLE) on the closed skim or comparison notes, no engineering shorthand (PR numbers, "spike", JOINT, gate codes, commit hashes, reviewer names, SDK, HMAC) in visible prose, and evidence links with friendly text. The **position above is unchanged in substance**: the opportunity is strongest for facts-already-in-BigQuery customers on Enterprise capacity within an agreed budget; the receipt check and graph walk are recorded examples; the connected path is still to prove and is the pilot's job. The page now says that in plain words. This addendum records the mapping; the sections above remain the dated source of the underlying assessment.

## Later questions slice (2026-09-06, Fable 5.1, `feat/board-pack-ask-later`)

Haiyuan chose Astra's board-pack-first order for the "what evidence lets us account for this number later?" idea. This slice adds one compact, visible panel after the three comparisons and before the capacity line: three questions Maya could ask later, one per comparison, each answered conditionally by evidence the proposed runtime would keep (saved context, protected access record, checked execution receipt), plus one boundary sentence. It is a reader-facing question, not a fourth outcome, a new product claim or a new score. The position, evidence and boundaries recorded above are unchanged; the closed skim, hero, arithmetic, three comparisons, Technical design, punchline and pilot ask are preserved. Retention and current permission are stated as conditions; nothing promises a retention horizon, and nothing claims the runtime explains the model's private reasoning. Full-RFC evidence mapping and auditor acceptance cases are later slices, not part of this PR.

## PR 33 honesty update (2026-09-06, Fable 5.1, `feat/board-pack-pr33-honesty`)

Site PR 33 (`spike/bq-graph-second-principal-20260906`) merged at `bb88df4`, head `114e81a`; the live artifact `evidence/authz_cases.json` was produced by the harness at `0d07e47` and later hermetic-only fix passes changed the evidence shape on failure paths only. It ran the distinct-principal negatives that the 2026-09-05 record left BLOCKED. Result: **5/5 MEASURED under the receipt spike's existing restricted service account (`sa:okf-receipt-restricted`, via impersonation, no new principal) on the relational fallback engine** over the same RLS tables, each case graded only behind a working allowed control under the same principal; teardown VERIFIED step by step. Cases: hidden intermediate ENFORCED, denied bundle DENIED_NO_LEAK (zero identifiers in the response and in the API error text), output denied with the seed visible, owner-credential fallback NO_FALLBACK, revocation before cached replay FAIL_CLOSED, plus an owner-stored cache entry replayed under the SA DENIED.

What did **not** change, and what this update must not imply:

- **The same five cases inside a GQL traversal remain BLOCKED.** GQL needs an Enterprise window; the bounded window lifecycle for both clients is not wired, and the window gate refuses while a legacy 2026-09-05 job journal is unreconciled. JOINT's flip trigger for authorization, which reads "inside GQL", is therefore still open.
- The operator-identity no-hidden-identifier claim stays INCONCLUSIVE (substring detector, payload not retained, never re-run). G7 mixed-publication protection stays PARTIAL. G8 benchmarks stay INCOMPLETE at 0/9.
- **No score moves.** Graph report: MODERATE for demonstrated retrieval only. Combined delivery: LOW. The connected chain (catalog discovery → pinned publication → governed retrieval → caller-delegated computation → result-bound receipt → enforced consumption) has still not run; the five negatives were run in isolation on one invented fixture with temporary grants, not as part of that chain. Live KC discovery, restricted-principal natural-language search (the remote embedding model is not usable by that principal), independent attestation and a customer-accepted budget are not established.

Reader-facing effect: the board pack no longer says the two-requester tests "could not run". It says a separate restricted identity passed five denial checks on the SQL path, not yet inside graph queries, and keeps the remaining gaps. The full RFC's matching sentences (§ explainable-access evidence paragraph, § current-evidence note, and the Phase 3 evidence cells) received the same correction and nothing else. Later-questions panel, hero, arithmetic, punchline, pilot ask, 2026-09-19 checkpoint and `styles.css` are unchanged.
