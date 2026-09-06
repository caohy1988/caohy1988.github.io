# Spec — full RFC alignment and human tone

Date: 2026-09-05 PT. Baseline: `d3f66f437977d6fa18e695477c849d06444f7781`; evidence cutoff: supplied 2026-09-06 UTC status. [Intent](full-rfc-align-intent.md) · [Plan](full-rfc-align-plan.md) · [Content map and copy](full-rfc-align-content-map.md).

## Requirements

### Scope and argument

- R1. This pass produces only the four `full-rfc-align-*.md` files in the EM directory and `rfc/`, committed and pushed on `feat/full-rfc-align-human`. Fable's subsequent implementation changes `rfc/index.html`; PR creation is not authorized by this planning pass and merge remains Haiyuan's gate.
- R2. Preserve all ten numbered sections, the six decisions, seven model disclosures, six reproducibility levels, Phase 0–5 overview and cards, risks, source evidence and public anchors. The board pack remains the short brief; no long-form contract is deleted merely to shorten the skim.
- R3. Keep the three outcomes and paired KC + OKF / + BQ runtime comparison. State the proposed runtime's strongest opportunity beside the customer and capacity conditions, explicitly adding that no customer operating budget has been accepted yet.
- R4. Preserve the first-workload route as a distinct adoption possibility after the projection and necessary facts are loaded. Qualify GQL with Enterprise or Enterprise Plus; ordinary relational SQL/vector retrieval can use on-demand. Do not apply GQL's capacity requirement to all receipts or all BigQuery retrieval.
- R5. Preserve Germany's Phase 0 fixture and historical evidence, Alder's illustrative story/arithmetic and Acme's separate experimental identity. Do not claim Alder keeps its facts in BigQuery, executed a job or produced a verified 96% result.

### Evidence and promotion

- R6. Replace global “unbuilt/unproven” or “all receipts unverifiable” wording with scoped descriptions of the wider demos, the receipt example, the graph example and the proposed connected path. Cite the recorded examples beside their claims using the full pinned URLs below.
- R7. Describe graph results as retrieval only: Enterprise reservation, retired anchor through two links to declared SQL, impact comparison and awkward-bundle cases. State that the SQL was found, not run; per-requester authorization, leak prevention and publication consistency remain unfinished.
- R8. Describe the receipt result as one consumer-enforced example with caller-delegated execution, authoritative job/result reads and fresh-process verification. Preserve its same-requester credentials, local HMAC custody, limited live cases and lack of a separate verifier principal or portable signature.
- R9. Every general benchmark-status sentence says **“speed benchmarks are not finished yet (0 of 9 cells complete)”** or the same wording with the count as linked text. Do not say “never run,” “have not run,” “no benchmarks were run,” or imply zero attempts; the record contains 20 warmups and 28 of 100 measured requests in one incomplete cell.
- R10. Keep receipt and graph work parallel, with receipts the first deliverable and no dependency on graph results. Retain Phase 0–5 as the full-profile implementation sequence; isolated examples do not complete those phases.
- R11. Require the complete connected path before upgrading the combined delivery claim: KC discovery → pinned publication → governed retrieval → caller-delegated computation → result-bound receipt → consumer-enforced verdict. Also require publication consistency and negative tests for denied intermediate nodes, revoked access before cached replay, unauthorized output access and a shared service account mislabeled as the requester.
- R12. Carry the 2026-09-19 evidence checkpoint and opportunity downgrade conditions. The scoped case cannot be carried indefinitely without credible progress across retrieval, caller authorization and result-bound execution plus a customer-accepted operating envelope.

### Technical honesty and presentation

- R13. Preserve the exact normative contracts below, including independent attestation as a future target. Make its unresolved trusted result-evidence path explicit; metadata-only access cannot authenticate the displayed value, and a same-credential fresh process does not satisfy the separate-principal target.
- R14. Apply the defined skim blacklist and plain-language replacements to prose, headings, labels, diagram descriptions and assessments. Technical states, APIs and source references remain precise where they define a contract; a technical section's status paragraph is still an assessment and must use human language.
- R15. Keep the light layout, native disclosures, accessible diagrams and no-JavaScript behavior. Verify the whole page at desktop/mobile sizes and in print; use narrowly scoped CSS only if changed text requires it.
- R16. Verify immutable surfaces byte-for-byte and changed prose against the story, evidence and no-overclaim examples below. Report document checks separately from runtime experiments; this task does not run or complete any cloud, conformance or product benchmark gate.

## Source precedence and stale instructions

The user request is the authority for scope and output. The supplied `JOINT_final.md` controls opportunity, parallel sequencing, promotion and downgrade policy; `SPIKE_STATUS.md` updates its historical delivery claims. Their directory is `/tmp/okf-full-rfc/`. Detailed pinned reports qualify the summary; the current board-pack source supplies the tone. Existing main-RFC contracts remain authoritative except for the explicit clarification in R13 and the optional-Graph gate clarification in the content map.

Do not apply the previous `full-update-*` packet mechanically. Its introduction/story work is already in the baseline. Its unqualified “graph can be the first workload,” present-tense punchline, blanket demo language, instruction to preserve metadata-only attestation prose without qualification, and blanket prohibition on all Graph gates need the deltas here. Preserve the previous packet on disk; this packet is the new handoff.

## Evidence register

Use friendly link text. The keys E1–E9 below are planning references, not labels to display in the skim. Full URLs must retain their commit pins; never replace a report link with a branch, directory URL, local `/tmp` path or PR landing page.

| Key | Pinned artifact and suggested visible label | Supports | Does not support |
| --- | --- | --- | --- |
| E1 | [Recorded receipt check](https://github.com/GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK/blob/6719eb535667963fa640dd4535e508b550eb6cb1/examples/okf_attested_computation/evidence/receipt/report.md) | Caller-owned job; authoritative `jobs.get` and `jobs.getQueryResults`; fresh-process check; enforced release; example scope and limitations | Separate constrained verifier principal, portable signature, library/API release, broad accounting correctness, full profile `ATTESTED` |
| E2 | [Receipt case records](https://github.com/GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK/blob/6719eb535667963fa640dd4535e508b550eb6cb1/examples/okf_attested_computation/evidence/receipt/live_cases.json) | Approved, wrong query, wrong period, display substitution, missing job/result, receipt tampering/replay, job-owner mismatch and grant revocation cases, within the report's live scope | Every field mutation, key-lifecycle, expiry and concurrency case having run live |
| E3 | [Receipt example code and notes](https://github.com/GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK/tree/6719eb535667963fa640dd4535e508b550eb6cb1/examples/okf_attested_computation) | Example location and documented topology | New SDK core behavior or supported product integration |
| E4 | [Recorded graph walk](https://github.com/caohy1988/caohy1988.github.io/blob/b05e278b0c459f3dc035d7cae48841c75d6fa89f/rfc/spikes/bq-graph/evidence/report.md) | Narrow retrieval, impact/backlog, scope/ambiguity handling, Enterprise route; historical access/publication gaps | Execution of returned SQL; leak-free per-node authorization; connected KC discovery; full RFC publication protocol |
| E5 | [Benchmark completion record](https://github.com/caohy1988/caohy1988.github.io/blob/b05e278b0c459f3dc035d7cae48841c75d6fa89f/rfc/spikes/bq-graph/evidence/summary.json) | 0 of 9 complete; incomplete sampled cell | Representative latency/cost or an accepted customer SLO |
| E6 | [Recorded capacity teardown](https://github.com/caohy1988/caohy1988.github.io/blob/b05e278b0c459f3dc035d7cae48841c75d6fa89f/rfc/spikes/bq-graph/evidence/reservation_changes.json) | Recorded Enterprise reservation CREATE/DELETE history | Every pending job cancelled, all fixture resources deleted, billing fully reconciled |
| E7 | [Comparison evidence and limits](https://github.com/caohy1988/caohy1988.github.io/blob/b05e278b0c459f3dc035d7cae48841c75d6fa89f/rfc/spikes/bq-graph/evidence/comparison.md) | Differentiates measured BQ requests, Lyon's recorded Neo4j semantics, documented Spanner placement and missing matched runs | Four-way benchmark winner; ordinary KC/SQL fallback having called a live KC discovery endpoint |
| E8 | [Graph example code and notes](https://github.com/caohy1988/caohy1988.github.io/tree/b05e278b0c459f3dc035d7cae48841c75d6fa89f/rfc/spikes/bq-graph) | Scoped prototype, published code and evidence | Full reference implementation or matching full-profile identity formulas |
| E9 | [Receipt review note](https://github.com/GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK/pull/479#issuecomment-5556160003) | Review provenance; reviewer discloses writing the final fix | Independent authorship review, new implementation approval or merge authority |

The receipt pin is the reviewed example head `6719eb535667963fa640dd4535e508b550eb6cb1`; its merge commit is `120da786c6f47122ac48ebeef5c8dfa9c7cd95b1`. The graph pin is merge commit `b05e278b0c459f3dc035d7cae48841c75d6fa89f`. Keep these distinctions in technical provenance only. The source status and board pack record both examples as merged/reviewed; that does not endorse the forthcoming HTML revision. E9 is optional if the page does not narrate review provenance.

Technical evidence detail may attribute the graph report's G1–G5 retrieval scope and retain its G6/G7 PARTIAL, distinct-principal BLOCKED and G8 incomplete labels as quoted source terminology. Prefer explanatory prose instead. The `NOT_EXECUTED` graph result and the receipt example's `VERIFIED` verdict are distinct from the full profile's `ATTESTED` contract. Prototype publication IDs and `active_publication` are not the full RFC's publication hash formula and `deployment_heads` protocol.

Evidence validation produces a verdict before consumption. A consumer must validate that matching verdict and the current release conditions before disclosing the result; a completed release is never a prerequisite for issuing the verdict.

The receipt attack example used a product-cost-only gross-margin substitution, not Alder's total-ARR substitution. Its success must never be described as having executed the retention scenario. Later code fixes and hermetic regressions did not retroactively complete missing live graph tests.

## Product boundaries and evidence still needed

Google's [edition matrix](https://docs.cloud.google.com/bigquery/docs/editions-intro) limits GQL queries to Enterprise/Enterprise Plus; creating a graph on-demand is not evidence of on-demand GQL support. [GRAPH_EXPAND restrictions](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/graph-sql-queries#graph_expand) do not supply a general OKF link-graph substitute: the schema relationship graph must be single-root acyclic, with ambiguous and many-to-many relationships omitted from that schema graph. This does not rule out ordinary relational SQL/vector retrieval on-demand.

The recorded path used generally available vector search plus GQL. [Graph-native semantic search](https://docs.cloud.google.com/bigquery/docs/graph-search) is separately marked Preview; never claim it was the tested route or call all of BigQuery Graph Preview. A customer unable to accept Preview needs a supported generally available route that preserves the required semantics. Product availability is not combined delivery evidence.

[Google's graph placement guidance](https://docs.cloud.google.com/bigquery/docs/graph-compare) distinguishes analytical work from online neighborhood retrieval. Keep the broad serving-tier opportunity more tentative than the facts-already-in-BigQuery case. BigQuery contributes authority over its own execution and a supported integration opportunity; other retrievers can call BigQuery and consume the same evidence. Co-location alone does not align Catalog, source, traversal and output policy.

At the checkpoint, require a stated corpus and concurrency, seed-plus-two-hop p50/p95, freshness/publication upkeep, per-request and capacity cost, and the customer's agreed budgets. Compare equivalent behavior against ordinary KC/SQL retrieval, Neo4j and Spanner Graph. Do not import the example's provisional target as an accepted customer budget or publish sampled timings as a benchmark result.

Narrow the opportunity if measurements miss customer budgets while an alternative plus BigQuery execution meets them; Enterprise cost cannot be justified; simpler retrieval supplies comparable governed answers with less operating work; required semantics, authorization or publication consistency cannot be retained; a supported route cannot meet a customer's Preview restriction; or trustworthy result evidence cannot be bound and enforced. A successful graph example cannot compensate for a failed receipt boundary.

## Human-tone contract

### Skim boundary

The mandatory prose scan covers `header`, `#summary`, `#motivation`, `#closing`, all numbered-section introductory prose, all headings, native disclosure summaries, comparison cells/notes, overview assessments, new evidence notes, phase-card titles, captions and footer. Include accessible names/descriptions and visible SVG narrative labels. Keep prose-led assessments human even when placed inside `#details` or a new evidence disclosure.

Technical bodies in `#decision`, `#statemachine`, `#details`, detailed phase gates and risks can retain exact API/field names, normative verdicts and source references. Exempt an exact state such as `BQ_COMMITTED` or `UNVERIFIABLE` only where its protocol behavior or historical raw capture is being explained, never because it is wrapped in `code`. The source-convention references in Decision 6 and `#baseline-body` are technical provenance, not a scorecard. Existing hash/config/code blocks and state-machine labels are technical contracts.

For repeatable checks, Fable should mark the prose regions being audited with `data-rfc-skim` on existing containers (or record an equivalent explicit selector list). Do not create wrappers that change layout, and do not mark technical code blocks as skim. The selector list must cover the minimum boundary above; it may not shrink to make the check pass.

### Blacklist

Run text-aware checks on rendered skim text, link labels and accessible descriptions after HTML entity decoding. Do not scan raw HTML as the sole tone check: `href` paths containing `spikes` are valid evidence links. The following are forbidden as skim wording:

- Case-insensitive whole words `spike`, `spikes`, `post-spike`, `JOINT`, `G1` through `G8` (including ranges), and PR narration such as `PR #30`, `pull request 479`, `#195`, or exposed commit hashes.
- Score labels `HIGH`, `LOW`, `MODERATE`, `MODERATE+`, `PARTIAL`, `BLOCKED`, including title/lowercase uses when presented as ratings. Do not flag ordinary words such as “low-entropy” inside protected technical detail as a score.
- Internal progress shorthand used as assessments: `UNVERIFIABLE`, `NOT_RUN`, `INCONCLUSIVE`, `receipts-gated`, “implementation gated,” “promotion to MODERATE.” Preserve exact verdicts only at the technical boundary described above.
- Benchmark zero-attempt assertions identified by R9. Future tests may say “still to prove”; never rewrite the recorded unfinished benchmark as unattempted.

An all-page pass additionally reviews every new status sentence and link label. Opening disclosures must not reveal a second scorecard. Exact attributed source labels, if retained, belong only in technical evidence provenance with a nearby plain-language explanation. Do not censor source files or the contents of linked reports.

| Old assessment or shorthand | Plain-language replacement | Qualification that must travel with it |
| --- | --- | --- |
| HIGH (scoped) opportunity | “Especially strong when the facts an analytical agent needs already live in BigQuery…” | Enterprise/Plus and customer-accepted latency, freshness, concurrency and cost budgets; none accepted yet |
| LOW combined delivery | “The connected path still needs to be proven.” | Two isolated examples exist; no live catalog-to-result integration |
| MODERATE receipt slice | “One worked example checks a caller-owned query and releases its result only after verification.” | Same requester delegation, local key, example/tests only |
| MODERATE graph slice | “The graph walk retrieves the linked rules in the tested cases.” | SQL found, not run; unfinished access/publication/benchmark evidence |
| PARTIAL governance | “Access and publication checks are unfinished.” | Two-requester tests could not run; hidden-identifier and mixed-publication protections not proven live |
| BLOCKED second principal | “Tests with two different requesters could not run.” | Not a claim that every IAM test was absent or that they passed |
| UNVERIFIABLE demo receipts | “The wider demo's computation checks are placeholders, so its receipts cannot yet be verified.” | Scope this to the wider demo; retain exact verdict in historical/technical detail |
| parallel-spike / receipts-gated | “Continue receipt and graph work in parallel. Receipt work must not wait for graph results.” | First deliverable is receipt enforcement; no production promise in a fortnight |
| G8 incomplete / NOT_RUN | “Speed benchmarks are not finished yet (0 of 9 cells complete).” | Partial attempts exist; no representative comparison claim |
| merged PR number as proof | “The recorded examples are merged and reviewed.” | Friendly pinned evidence links; merge is not combined readiness |

## Preservation contract

Compare against the baseline commit, not an already edited working copy. Byte-stable means exact source bytes, including code whitespace; meaning-stable prose may be edited only as mapped.

| Surface | Required preservation |
| --- | --- |
| This planning pass | Entire tracked repository remains byte-stable except the four newly added planning files. In particular `rfc/index.html` remains unchanged. |
| Fable's implementation scope | All pre-existing files except `rfc/index.html` remain byte-stable, including previous planning files, `rfc/demo/`, `rfc/full-demo/`, `rfc/board-pack/`, `rfc/bq-vp/index.html`, `rfc/spikes/` and every fixture/capture. Clarifications to this packet must be explicit in Fable's review, not silent changes to old evidence. |
| Story | Entire existing `#motivation` section is byte-stable. Its narrative, arithmetic, link and Germany fixture boundary already satisfy the target. |
| Code and identities | All existing `pre > code` blocks are byte-stable. Preserve snapshot/publication formulas, computation-version formula, relationship keys, domain separators, HMAC inputs, envelope serialization examples and `context_ref` fields. No copied prototype hash protocol. |
| Core model disclosures | Existing Identity, Relationships, BQAA seam and Catalog ownership disclosure bodies are byte-stable. Evidence additions go in other mapped sections; no schema or ownership changes. |
| Publication diagram | Entire SVG in `#statemachine` stays byte-stable. Existing protocol state spellings, atomic head swap, history, lag and pin-or-fail-stale semantics remain unchanged. |
| Anchors and evidence destinations | Preserve all existing `id` values and href destinations, including fragments and capture links. New anchors may be added uniquely. No pin substitutions or normalized `spikes` paths. |
| Detailed contracts | Preserve optional OKF core/producer syntax, one-domain default, no LLM-inferred typed edges, current authorization before every disclosure, privileged-only denied details, retention/purge/revocation limits and source-native reviewed changes. |
| Attestation | Preserve caller-delegated execution and the separate constrained attester target, exact `ATTESTED`/`UNVERIFIABLE`/`REJECTED` semantics, named parameters, threat model, key lifecycle, fail-closed evidence and consumer enforcement. Apply R13's explicit gap clarification; never silently grant row access or adopt same-credential verification as the final design. |
| Phase structure | Keep phases 0, 1, 2, 3, 4, 5, their ownership and deliverables, plus conditional 2b type reuse. Keep pending validator, regenerated-vector rerun and owner sign-offs pending. Graph equivalence applies when promoting the optional Graph implementation, not to receipt or relational baseline completion. |

## Acceptance examples and checks

| Check | Given / reading action | Pass condition |
| --- | --- | --- |
| A1 — scoped opportunity | Read only masthead/summary | Customer facts already in BQ, Enterprise/Plus, all four budgets and no accepted customer envelope are visible; first-workload possibility is separately scoped. |
| A2 — evidence | Follow each example claim | E1/E4 support it; receipt has consumer enforcement; graph has retrieved but unexecuted SQL; neither proves Alder or the combined path. |
| A3 — benchmark history | Search status prose and check E4/E5 | “Not finished yet (0 of 9 cells complete)”; no zero-attempt implication or sampled benchmark winner. |
| A4 — promotions | Follow summary → acceptance → phases → closing | Full chain and negative tests remain required; examples do not complete phases; receipts need not wait for optional Graph. |
| A5 — attester boundary | Compare architecture SVG, §06 execution and Phase 4 overview/card | All preserve the independent target and state the unresolved authoritative result path; metadata-only is insufficient; same requester/fresh process is only the example. |
| A6 — story integrity | Read motivation and inspect protected bytes | Alder arithmetic/stakes and unexplained-access framing unchanged; Germany fixture distinct; Acme evidence never becomes an Alder result. |
| A7 — full argument | Walk ten anchors and open seven model disclosures | No missing contract; comparison still has all three pairs; reproducibility, six phases and risk table intact. |
| A8 — tone | Scan specified skim, expanded assessments and accessible descriptions | No blacklist hits outside the explicit technical exemption; human limitations replace scores without implying completion. |
| A9 — byte stability | Compare baseline and final HTML/files | Every preservation row passes; additions do not rewrite evidence, code formulas or public IDs. |
| A10 — document behavior | Desktop/mobile, keyboard and print review | No document overflow at 1280/900/768/375/320; native disclosures focus/toggle; diagrams have readable descriptions; folded content is available in print, with named browser evidence. |

Document verification is sufficient for this editorial implementation. Do not add runtime tests that merely restate the prose, run new cloud experiments, or mark the existing runtime acceptance gates passed.
