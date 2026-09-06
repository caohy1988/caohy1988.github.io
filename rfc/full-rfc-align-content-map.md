# Content map — full RFC alignment and human tone

Date: 2026-09-05 PT. Baseline: `rfc/index.html` at `d3f66f437977d6fa18e695477c849d06444f7781`. Use text anchors and IDs; line numbers below are navigation hints for that baseline only. [Spec](full-rfc-align-spec.md) requirements and preservation rules govern every row.

## Section-by-section implementation map

This is a revision of the existing complete RFC. Replace contradictory sentences in place; do not leave the old claim followed by a corrective disclaimer. C01–C09 below are proposed reader copy, not additional page sections. E1–E9 refer to the spec's full pinned URLs.

| Location / baseline hint | Exact action | Preserve / acceptance |
| --- | --- | --- |
| Head, masthead `.thesis`, `.status-note`, `.badges` (248–260) | Keep formal title and optional-profile subtitle. Use C01 for thesis/status; change “Design proposal · implementation gated” to “Proposed integration · early examples.” | Canonical URL, fonts/chrome, board-pack link and portability; R2–R5/R14 |
| Service-role strip `.credo` (262–267) | Keep existing four roles. It already separates OKF authoring, KC discovery, proposed runtime and BQAA observation. | No fifth authority, second benefit grid or new service |
| `#summary` lede/intro (276–278) | Change “This optional profile connects…” to “This optional profile proposes to connect…”; insert C02 after the two opening paragraphs and before the comparison. | Existing definition of authored source and separate policy/telemetry owners |
| `#runtime-guarantees` (280–302) | Keep all three paired comparisons and proposed caption. In the first note append E4 and “The recorded walk retrieves linked rules; access and publication checks remain unfinished.” In the access note add that the current examples do not prove per-node authorization. Replace third note's demo-only verdict sentence with C03. | Deterministic vector caveat, custom-entry scope, metadata/file distinction and no data-quality guarantee |
| Summary comparison ending (303) | Replace its final sentence with C04's distinctive-contribution paragraph. | Other retrievers can use the same BQ evidence; no exclusivity claim |
| `#summary` first-workload paragraph (313) | Replace whole paragraph with C04's first-workload paragraph; link edition wording. | No missing-data retrieval, no assumption about Alder's warehouse |
| `#summary` final two package paragraphs (314–315) | Keep a short human bridge: “The source bundle stays authoritative. Catalog points a request to a publication; the runtime must serve that authorized version or explain why it cannot. Agent Analytics observes the request.” Retain their unique package/type/ledger/publication/lag/observer details in a new technical paragraph appended to `#baseline-body`; consolidate only text already present there or in the six decisions. | Do not lose the sample-as-delta relationship, `toolbox/okf-context`, `kcmd`, no silent latest-head substitution, push-only/relational-first contract or BQAA ownership |
| Summary navigation | Preserve current links; optionally add `#current-evidence` as “Recorded examples.” | Existing IDs/hrefs unchanged; no new numbered section |
| `#motivation` (319–340) | No changes. | Entire section byte-stable: story, arithmetic, Germany distinction, existing links |
| `#architecture` prose, plane table, `#arch-crosswalk` (344–360) | Keep architecture and authority detail. Add a short proposed-connected-path status beside the diagram, using C05. | Before-disclosure current access, distinct identities, all planes and serving authority |
| Main architecture SVG (363–561) | Replace visible “core keys consumed · #195 / #183 / #253 keys tolerated” with “core keys consumed · adopted extensions tolerated.” Replace “reviewed source PR” with “reviewed source change.” Adjust the attester line per C06. Add “The connected path has not yet been demonstrated” to accessible description/caption, while retaining the existing detailed description. | All boxes/arrows and identity rail; exact protocol names remain technical. Avoid shrinking type. No topology implying the two examples are already connected |
| Optional Graph SVG box (483–486) | Keep “Optional Property Graph” and “Phase 5 · GQL ≡ SQL paths”; replace “no gate may require it” with “optional; separate acceptance.” Explain Enterprise/Plus and optional promotion in adjacent prose/caption. | Technical labels stay readable; relational and receipt paths independent |
| `#decision` introduction and closing (564–598) | Keep all six recommendations and technical source-convention provenance. Replace “small PRs in phase order” with C07's sequencing paragraph. | Package, placement, frozen-source distinction, convention order, separate aspects, delete-only-owned ledger discipline |
| `#baseline` / `#baseline-body` (576–584) | Keep existing summary and historical paragraphs; append the retained unique summary implementation detail as mapped above. | Do not edit existing historical claims or duplicate their entire content; technical provenance may keep tracker references |
| `#statemachine` (588–636) | Keep states, SVG, exact transitions, historical API observations and links. Add one plain sentence to the introduction: “The graph example's publication pointer is narrower than this cross-service protocol and does not demonstrate Catalog pinning.” Link E4. | SVG byte-stable; no prototype `active_publication` substituted for full `deployment_heads`; no false governed commit |
| `#details` heading / seven summaries | Preserve topics and default open/closed state. Optional heading polish: “The proposed model.” | All seven disclosures remain; headings/summaries are skim prose |
| Identity and Relationships disclosures (644–703) | No body changes. | Byte-stable formulas, reserved-file handling, manifests, generic links, assertions, resource nodes, unresolved references |
| Runtime schema disclosure (707–715) | Replace the overbroad “No correctness gate…in any phase…” sentence with “The relational baseline and receipt delivery do not depend on Property Graph. Enabling the optional Graph implementation requires its own equivalence, authorization and operating-budget checks.” Replace the “Product API availability…” sentence with C05's schema-status paragraph. Append the concise capacity/GA/Preview/GRAPH_EXPAND boundary from the spec. | Relational authority, table/view model and graph naming; do not copy prototype ID or schema semantics |
| Retrieval disclosure (718–756) | Keep all existing selection, policy, lifecycle, instruction and privacy requirements. Insert a short human status paragraph after the current-policy discussion: “The recorded graph walk does not yet establish these access guarantees. Tests with two different requesters could not run, and protection against hidden-identifier disclosure and mixed publications remains unproven live.” Link E4. | Code blocks byte-stable; no data in public telemetry; current access still overrides retained publications |
| Execution disclosure (760–785) | Apply C06 to identity/evidence prose and status paragraph. Make the complete-verdict list require authoritative result binding as well as output permission. Separately require the consumer to validate the matching successful verdict before releasing the result. Keep exact verdict meanings, named parameters, two receipt artifacts and threat model. | Separate identity remains target; metadata-only cannot bind result; example `VERIFIED` is not full-profile `ATTESTED`; no new data grant or changed public receipt schema |
| BQAA and Catalog ownership disclosures (789–817) | No body changes. | Both bodies and `context_ref` bytes unchanged; no imported graph/receipt payloads into telemetry |
| `#repro` (821–833) | Keep six levels and their explanations. Replace bold score-like “guaranteed/conditional” headings with C08; add one line that these are proposed contracts, not demonstrated by the two examples as a whole. | Fixed inputs, current access, retained artifacts/fact versions; no identical-LLM promise |
| `#accept` (839–853) | Keep existing ten items. In Verifiable execution add trusted result evidence and enforced consumer release per C06. Replace First workload with the scoped C04 meaning. Add two items: connected-evidence promotion (R11) and parallel receipt work/customer-budget checkpoint (R10/R12). | A “yes” accepts design and gates, never completed implementation; pending sign-offs remain pending |
| `#phases` introduction / at-a-glance table (859–871) | Add C07. Update overview rows together with cards as listed below. Keep six numeric phases. | Germany baseline and Phase A distinction; no example-based phase-completion labels |
| Phase 0 historical off-site note (874) | Keep the dated historical report and pending work. Add nothing claiming a fresh validator/vector rerun. | Existing evidence qualifications and exact fixture identity |
| Historical demo evidence note (876–883) | Retain the recorded Germany/full-demo material and every link. Make the introductory label “What the earlier demos show.” Scope every negative claim to those captures; use “their computation checks are placeholders” in assessment prose and exact raw verdicts only when explaining captures. End with a link to new `#current-evidence`. | Actual operator SELECT evidence is not metric attestation; existing probes remain historical |
| New evidence group inside `#phases`, after historical note and before cards | Add `id="current-evidence"`, “What the recorded examples show,” C03/C05 evidence descriptions and connected-path limit. Use E1/E2/E4/E5/E6/E7; code links E3/E8 may sit in technical provenance. Do not add an eleventh numbered section or copy report tables. | Four scopes: earlier Germany demos, receipt example, graph example, proposed combined runtime |
| Risk table (936–949) | Keep all risks. Clarify optional-Graph row as above; extend attester row with unresolved trustworthy result binding. Add customer envelope/capacity/alternative-comparison risk and one-example-to-product overclaim risk. | Give each a checkpoint or existing phase owner; do not delete existing security/identity risks |
| `#closing` and footer (952–965) | Use C01 for conditional punchline and C09 for pilot/decision text. Preserve historical provenance; append “Evidence and assessment language aligned 2026-09-06; the connected profile remains proposed.” | Full RFC footer retained; no implied new approval, production completion or PR-number narrative |

## Phase overview and card parity

Apply each delta to both the overview row and the detailed card, without rewriting the other gate requirements.

| Phase | Required delta | Explicit non-completion statement |
| --- | --- | --- |
| 0 — Contract + fixture | Add the trustworthy result-evidence path to future capability-probe/design questions. Preserve all Germany hash/validator requirements. | Example-specific IDs and tests do not close the full-profile contract or sign-offs. |
| 1 — Compiler + BQ core | Call its first workload a relational projection; distinguish optional Enterprise/Plus GQL. | Acme's prototype publication scheme is not implementation of these identity/head-history contracts. |
| 2 — Catalog projection | Preserve full-entry runtime pins, coexistence and reconciliation requirements. | A pinned source file is not live KC discovery or pin-or-fail-stale integration. |
| 3 — Retrieval + access | Retain every-hop negatives; add the unfinished distinct-requester, hidden-identifier and live mixed-publication checks as evidence still required. | Receipt job-owner/dataset-grant tests do not establish graph node/edge authorization. |
| 4 — Execution evidence | Retain independent attester identity and no broad source-row read. Require the trusted authoritative result-evidence path and enforced release; exact mechanism and least-privilege grants remain to prove. Preserve key/privacy/telemetry tests. | The same-requester receipt example is useful evidence, not Phase 4 completion. Receipt development can proceed without Graph results. |
| 5 — Hardening + pilot | Make GQL equivalence conditional on enabling optional Graph. Add Enterprise/Plus capacity, stated corpus/concurrency, representative latency/cost/freshness and upkeep measurements, alternate-retriever comparison and customer acceptance. | Speed benchmarks are not finished yet (0 of 9 cells complete); no live connected pilot or customer budget is established. |

## Replacement copy

Convert Markdown links to existing HTML anchors using the full URLs in the spec. Copy may be tightened for fit only if all qualifications remain. Block IDs and editorial instructions are not page text.

### C01 — thesis and near-hero status

**Thesis, also closing punchline:** The proposed BigQuery runtime would turn the OKF graph into replayable context for agents—with explainable access and evidence that the declared computation ran.

**Status:** Proposed integration, with two separate worked examples. One retrieves linked rules; another checks a caller-owned query and releases its result only after verification. The connected path still needs to be proven. OKF v0.2 stays unchanged and usable without this runtime.

Use E4 on “retrieves linked rules” and E1 on “checks a caller-owned query.”

### C02 — opportunity and delivery, before the comparison

**Especially strong when** the facts an analytical agent needs already live in BigQuery on Enterprise or Enterprise Plus capacity, within latency, freshness, concurrency and cost budgets the customer has agreed to. No customer has agreed that operating budget yet. A broader Catalog serving layer needs a separate case against simpler retrieval options.

**What the examples show:** a graph walk can find linked rules, and a separate receipt check can tie a caller-owned query to its result. **What remains to prove:** catalog discovery, governed retrieval, caller-delegated computation and checked result release working as one connected path. One example supports the part it exercised; it does not establish the combined product.

Link the two example phrases to E4/E1. Keep both paragraphs visible. Do not move the budget caveat into a closed disclosure.

### C03 — receipt boundary

**Comparison note:** A retrieval record or job ID alone cannot substantiate a number. A recorded receipt example checks the query and result and enforces release at a consumer. The wider demo's computation checks are still placeholders, so its receipts cannot yet be verified. Attestation concerns process integrity, not the quality of the underlying data.

**Evidence paragraph:** The recorded receipt check ran on invented Acme gross-margin data. It used a BigQuery job owned by the caller, read the job and result back from BigQuery, verified them in a fresh process, and released the result only after the consumer's checks passed. Wrong query, wrong parameters, substituted display, tampering, replay and missing-evidence cases withheld the result. This is example code and tests, with no library change. Verification used the requester's delegation and a local signing mechanism; it does not establish a separate verifier principal, portable signatures or accounting correctness. It did not run Alder's retention calculation.

Link “recorded receipt check” to E1 and the cases to E2. In technical provenance describe local HMAC precisely rather than implying a portable digital signature. The report distinguishes live cases from broader hermetic tests; preserve that distinction if adding case detail.

### C04 — why BigQuery and the first workload

BigQuery brings authority over its own execution and a way to integrate retrieval with facts and job evidence already there. Other retrievers can call BigQuery and use the same evidence. Hosting the pieces together does not, by itself, make their access decisions consistent.

**A graph can be the first workload on Enterprise capacity.** Its authored inputs and any facts the query needs must first be loaded. That is a possible adoption route, separate from the stronger case where the relevant facts already live in BigQuery. GQL graph walks require Enterprise or Enterprise Plus; ordinary relational SQL and vector retrieval can also run on-demand. An empty project or an unprojected bundle supplies no retrieval evidence.

### C05 — graph evidence and architecture status

**Architecture status:** This diagram describes the proposed connected design. The recorded graph and receipt examples exercised separate pieces on Acme data; neither verifies the whole path or Alder's figures.

**Evidence paragraph:** The recorded graph walk ran on an Enterprise reservation. Starting from a retired Acme definition, it followed two links to the declared SQL and returned its status, derived trust, freshness and provenance. Its impact results matched a relational cross-check. Placeholder, ambiguous and out-of-scope cases were exercised on a separate test bundle; Acme's own backlog had no placeholders. This is retrieval evidence: the SQL was found, not run.

Access and publication checks are unfinished. Tests with two different requesters could not run, and the live evidence does not establish protection against hidden-identifier leaks or mixed publications. Speed benchmarks are not finished yet (0 of 9 cells complete). The Enterprise reservation was recorded as torn down; that record is not an audit of every pending job or fixture resource. No customer operating budget has been accepted.

**Schema-status paragraph:** The example demonstrates a scoped graph projection and retrieval path. It does not implement this RFC's complete identity, publication, access or receipt contracts. Relational serving remains authoritative, and the optional Graph implementation still needs its own equivalence and operating checks.

Use E4 for retrieval/access, E5 for the count, E6 for teardown and E7 for comparison limits. Add no percentile or price headline.

### C06 — independent attester and trustworthy result evidence

**Replace the identity paragraph's implied sufficiency, not its independence target:** Execution runs under the caller's BigQuery identity. The proposed attester runs under a separate constrained service identity. Job-metadata access can establish which query and parameters ran, but metadata alone cannot bind the reported value to the authoritative result. The full profile therefore also requires a stated, trusted path for result evidence and a consumer that enforces the verdict before release. The exact evidence mechanism and least-privilege grants remain design and validation work; broad source-row access remains excluded. Until the required result evidence is available, the verdict is `UNVERIFIABLE`.

Retain the existing exact job-metadata permission examples as probe candidates, not a proven sufficient grant. Preserve the separate-identity anti-subversion rationale and the exclusion of constrained-service-identity execution. Do not claim the example resolved those grants.

**Architecture SVG line:** “independent attester target · trusted result evidence still to prove” replaces “attester: independent constrained identity · job-metadata read · no data read.” Put the detailed no-broad-source-read boundary in adjacent prose; do not squeeze it into unreadable SVG text.

**Replace implementation-status paragraph:** The wider demo's computation checks remain placeholders. The separate Acme receipt example demonstrates checked result release under the requester's delegation, including verification in a fresh process. It does not establish the independent attester, portable receipt verification or complete connected profile described here.

Add authoritative result binding to the exact-verdict evidence requirements. Separately require the consumer to release a result only after validating a matching successful verdict; failed or unavailable checks withhold it. Include both requirements in the acceptance item, Phase 4 overview and card. Completed release is not a prerequisite for computing the verdict. Keep named parameters, literal template comparison, integrity proofs, key lifecycle and threat model. Leave exact receipt schemas and public fields unchanged; no permission change is part of this HTML task.

### C07 — parallel work and the promotion rule

Continue receipt and graph work in parallel. Receipt enforcement is the first deliverable to carry forward and must not wait for graph results or benchmark completion. The phases below describe the integrated profile's implementation dependencies; they do not make the independent receipt work wait for optional Graph support.

We will call the connected path proven only after one chain runs end to end: catalog discovery, a pinned publication, governed retrieval, computation delegated by the caller, a receipt bound to the result, and a consumer that enforces it. Publication consistency and tests for denied intermediate nodes, revocation before cached replay and unauthorized output must also pass. A shared service account with a user label is not caller delegation. Two successful examples do not clear that bar.

### C08 — reproducibility level headings

Keep each existing explanation and number; replace only the bold lead text. Level 5 deliberately has no terminal punctuation because its existing continuation completes the sentence:

1. What a snapshot and publication identify.
2. Reconstruct a retained snapshot.
3. Reconstruct a retained context package.
4. Repeat a selection with the same inputs and effective access.
5. Recover the computation contract while its artifacts are retained
6. Reproduce a result only while its required data versions remain available.

Retain the existing bounded-time-travel and changing-facts explanation. These headings are the proposed contract's distinctions, not experimental scores.

### C09 — checkpoint and Finance pilot

**One pilot.** Sponsor a Finance-owned retention pilot on real cohort data, with an agreed operating budget. Connect catalog discovery, pinned retrieval, current access checks, caller-delegated computation and result-bound consumption in one path. A substituted query or result, revoked access or missing evidence must withhold the claim. Alder's invented 96% is not a target for the pilot's data.

Reassess the opportunity at the 2026-09-19 evidence checkpoint. It narrows if customer budgets or Enterprise cost cannot be met, if simpler retrieval serves the need, if required semantics, authorization or publication guarantees fail, or if result evidence cannot be trusted and enforced. Customers who cannot accept Preview need a supported generally available route. The checkpoint is a decision about the evidence, not a promised production date.

## Consistency traps to remove

- Do not leave the present-tense “BigQuery turns…” in the masthead or closing after adding proposed status elsewhere.
- Do not leave a global “Graph-over-OKF is unbuilt” after adding E4. State which full-profile contract is still missing.
- Do not equate an Acme prototype publication pointer with the full cross-service protocol or declare Phase 1/2 complete.
- Do not relabel receipt `VERIFIED` as profile `ATTESTED`, or fresh-process checking as a separate trusted principal.
- Do not retain “metadata read · no data read” as a complete path to authenticated displayed results; C06 must reach the diagram and phase gates as well as §06.
- Do not leave unconditional GQL equivalence in the Phase 5 overview after making the card optional, or keep “no gate may require Graph” after specifying optional-feature acceptance.
- Do not hide unfinished access checks and the unaccepted budget behind the report links; the claim's limits belong on the page.
- Do not turn all uppercase protocol constants into human synonyms. Preserve machine-contract spelling in technical detail and scan the defined prose boundary separately.
