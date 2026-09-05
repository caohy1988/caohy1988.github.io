# Draft copy — main RFC

Date: 2026-09-05. These blocks are for Fable's implementation of `rfc/index.html`. Follow the [content map](full-update-content-map.md) for placement and deletion of displaced prose. Markdown links in paste blocks are relative to the main RFC page. Block labels and editorial directions are not page copy.

## B01 — masthead and role line

**Document title:** OKF runtime context projection — replayable context for agents

**H1:** OKF runtime context projection

**Subtitle:** A proposed Knowledge Catalog + BigQuery runtime profile for OKF v0.2

**Lede:** BigQuery turns the OKF graph into replayable context for agents—with explainable access and evidence that the declared computation ran.

**Status:** RFC proposal. The profile defines the integration to build; the recorded demos do not yet implement these guarantees. OKF v0.2 stays unchanged and usable without this runtime.

**Short link:** [Board-pack near-miss →](./board-pack/) The pack says 118%. Retention is 96%. Illustrative · 2–3 minutes.

**Role line:** Open Knowledge Format (OKF) authors portable knowledge and its relations. Knowledge Catalog (KC) discovers and governs it. The proposed BigQuery runtime selects, authorizes and accounts for its use. BigQuery Agent Analytics (BQAA) observes that use.

Editorial: keep a compact optional-profile badge; replace the current review badge with “Design proposal · implementation gated.” Historical review credit belongs in the dated provenance note, not a current approval badge. Move the two long baseline notes per the content map.

## B02 — summary and three proposed guarantees

**H2:** Three things a definition lookup cannot establish

An agent can cite the right definition and still give the wrong number. This optional profile connects the knowledge it selected, the access that allowed it, and the computation that produced its answer. The authored OKF bundle remains the source; Catalog and BigQuery are derived projections with different jobs.

**Comparison caption:** KC + OKF, compared with the proposed BigQuery runtime

| Proposed guarantee | KC + OKF | + BQ runtime |
| --- | --- | --- |
| **01 Replayable context** | Catalog finds entries; OKF records linked definitions and rules. The retriever still chooses which linked context to assemble. | Pin a publication and use explicit SQL or bounded relational walks to select the definition, cohort rule and declared computation together. Fixed inputs and current authorization define the repeatable selection. |
| **02 Explainable access** | The custom-entry projection uses an EntryGroup access boundary. Discovery alone does not explain each asset decision made by the agent's separate retrieval path. | Bind the authenticated requester to the execution identity. Enforce current policy across the projected assets and retain a governed record of what was returned and why. |
| **03 Verifiable execution** | Discovering a computation declaration does not prove the calculation ran. | Validate a separate job ↔ context ↔ result receipt against the declared computation. Substituted SQL or missing evidence cannot substantiate the number. |

Place these short notes with their respective rows, not in a distant disclaimer:

- **01:** Vector search can be deterministic. The distinction is a pinned, inspectable selection contract—not identical LLM answers.
- **02:** The EntryGroup comparison is scoped to custom entries; other Catalog and source permissions still apply. Access metadata needs enforcement. Metadata visibility does not grant file access.
- **03:** A retrieval record or job ID alone is insufficient. Existing demo computation receipts remain `UNVERIFIABLE`.

These are the guarantees proposed by this profile, not claims that KC or OKF cannot be combined with another deterministic retriever. BigQuery brings the graph projection, related fact queries, authorization checks and job evidence into one runtime design.

## B03 — summary continuation and first workload

**The graph can be the first BigQuery workload.** Project the authored OKF bundle into versioned node, relationship and computation records, and version the facts a query needs. An existing revenue warehouse is not a prerequisite. If no projection enters BigQuery, retrieval does not run there; an empty project supplies no evidence by itself.

The proposed `toolbox/okf-context` package compiles the source bundle, publishes immutable runtime state and reconciles a Catalog discovery projection through `kcmd`. BigQuery relational state is the serving authority. A Catalog-discovered seed carries the publication it describes: the runtime serves that retained, authorized publication or fails stale. It never silently substitutes the latest head.

Catalog discovery can start a human or agent request. Runtime tools assemble the authorized context. BQAA observes their use through `context_ref`; it does not own authored definitions, access policy or attestation verdicts. The reference implementation remains push-only, relational-first and subject to the phase gates below.

## B04 — Alder motivation

**H2:** The board pack says 118%. Retention is 96%.

**Label:** Illustrative scenario · Alder and Maya are invented

At 8:55 a.m., Maya Chen, VP of Finance at subscription software company Alder, opens the pack for a 9 a.m. board meeting. A $4 million plan to expand sales to existing customers leans on her agent's “verified” 118% retention. An analyst spots the mistake: the query counted new customers. Revenue from the starting customers fell 4%.

All amounts are annual recurring revenue (ARR), measured at the start and end of one quarter:

| Calculation | What it counts | Result |
| --- | --- | --- |
| `($9.6m + $2.2m) ÷ $10.0m` | Closing ARR from the starting customers **plus new customers** | **118% — wrong for retention** |
| `$9.6m ÷ $10.0m` | Closing ARR from the **same starting customers only** | **96% — retention** |

Maya pulls the slide. The agent found Finance's definition but missed the accompanying rule: count only customers there at the start. It reused a total-ARR query; she cannot trace the policy allowing this agent to use that asset. No execution receipt connects the query, the retention calculation and the reported result. The access gap is an unexplained decision, not evidence that the agent broke a permission boundary.

The proposed runtime answers those questions separately: retrieve the linked definition and cohort rule with the declared computation; explain current access along that path; then validate the actual query and result against the declaration. A good context selection cannot, by itself, validate a different query. Missing evidence leaves the number unproven.

[Read the short board-pack story and system diagram →](./board-pack/)

**Existing fixture, separate from this illustration.** Germany active-customer revenue remains the Phase 0 fixture and the scenario in the recorded demos. Its identities and evidence are unchanged. Alder is a proposed acceptance example; no Alder query, receipt or attestation produced these figures.

## B05 — architecture, role descriptions and diagram text

**H2:** One authored source, three runtime checks

The source bundle is canonical for authored knowledge and computation declarations. The compiler records source observations, resolves the complete artifact closure and produces immutable snapshots and publications. Catalog exposes governed discovery; BigQuery serves the compiled graph and related runtime evidence. Policy and telemetry have separate authorities.

Use these replacements in the existing plane table:

| Plane | Primary responsibility | Authority |
| --- | --- | --- |
| Source OKF bundle | Definitions, authored relations, computation declarations and review history | Canonical authored source; no mandatory BigQuery dependency |
| Knowledge Catalog | Discovery, ownership, lifecycle and links to assets | Derived discovery projection; identifies the publication it describes |
| BigQuery runtime projection | Pinned retrieval, current-policy enforcement and computation evidence | Derived relational projection; serving authority for this profile |
| Agent Analytics | Observe tool use, correlation and evaluation | Observer; does not decide knowledge truth or runtime authorization |

Preserve the existing compiler/publication and identity-chain explanation, followed by:

**01 selects context. 02 controls disclosure. 03 validates execution.** The requester is authenticated before context is returned, and current access constrains every candidate and traversal hop. A retained selection manifest explains the context supplied to the agent. Only the separate computation path can establish that the declared retention calculation produced the reported result.

**Main SVG replacement labels:** “01 Replayable retrieval”; “Pinned publication · bounded SQL”; “02 Current access · every hop”; “03 Verifiable execution”; “Optional Property Graph · Phase 5.” Fit these to the existing diagram rather than shrinking type to force long prose into boxes.

**SVG accessible description / visible text equivalent:** Proposed architecture. An authored OKF bundle compiles to a BigQuery runtime projection and a reconciled Catalog discovery projection. Catalog may identify the starting concept and publication. Authenticated requester identity and current policy gate BigQuery's selection of linked context. A separate declared computation runs as a BigQuery job and requires validated execution evidence before an attested claim. BQAA observes opaque correlation IDs. The observation, snapshot, publication, envelope and receipt identities remain distinct.

**Figure caption:** Proposed runtime: replayable context, access enforced before disclosure, and separate computation evidence. Publication and receipt state names describe the design, not a completed deployment.

## B06 — decisions and baseline bridge

Keep the six existing decisions and their technical detail. Use **declared computation** for the authored contract; use **Attested Computation** for the proposed protocol and exact verdict terms for its outputs. Do not mechanically rename identifiers or quoted source language.

Replace the Placement sentence that says a runtime exists with:

The non-normative Discussion introduces the proposed runtime profile and the conventions it tracks; it does not imply an implemented runtime or change OKF conformance.

For the relocated baseline disclosure, retain the dated source/sample analysis and add this replacement ending:

The shipped Catalog sample establishes a distribution and discovery baseline. This profile proposes the additional runtime contracts: an immutable publication that a request can pin, authorized retrieval with a retained selection manifest, and independently validated computation evidence. It reuses the shipped authored-signal types. Publication pins and ownership stamps belong in the separate `okf-context-runtime` aspect; they never ride in the shared `okf` aspect or authored frontmatter. Catalog discovery and sample repush behavior do not establish that the runtime has been built.

In the BQAA disclosure add:

Retrieval and access evidence stay in the governed runtime records. “Retrieval receipt” is explanatory language for the selection record; it does not add principal, policy or graph-path fields to `context_ref`. BQAA may correlate permitted identifiers, but it neither grants access nor upgrades an unproven execution verdict.

## B07 — publication consistency and captured Catalog behavior

Replace the state-machine introduction with:

This is the proposed publication protocol. BigQuery and Catalog have no shared transaction: immutable rows first stage under a `sync_id`; `BQ_COMMITTED` means the atomic advance of a deployment head to a publication. Catalog reconciliation follows. A Catalog failure does not roll back a committed publication. The captured demos do not show this commit protocol running.

Keep the existing state names, arrows, head-history rules and lag requirements. Replace the publication-pinning bullet with:

**Publication pinning.** Every owned entry is to carry `publication_id` and `published_snapshot_id` on the profile-owned `okf-context-runtime` aspect. A Catalog-started request obtains those pins through the full-entry read path (`entries.get`, `view=ALL`, to be verified by the profile's compatibility gate), then presents them to the runtime. Serve the authorized retained publication or fail stale; a search predicate only filters and cannot enforce the pin.

**Captured API behavior, narrowly scoped.** In the September 3 captures, LookupContext returned overview content but omitted the `okf` fields for the tested shipped metric and computation entries; the corresponding full-entry `view=ALL` reads exposed those fields. These observations do not establish universal LookupContext behavior or demonstrate the proposed runtime pin aspect. See the [metric LookupContext response](./full-demo/live/lookup_context_shipped_metric.json), [computation response](./full-demo/live/lookup_context_shipped_computation.json), [full metric entry](./full-demo/live/catalog_shipped_entry_metric_viewALL.json) and [full computation entry](./full-demo/live/catalog_shipped_entry_computation_viewALL.json).

## B08 — identity, relationships and relational baseline

In the Identity list use:

- `snapshot_id` — deterministic identity of the complete compile-input closure under the compiler semantics version. It identifies the inputs and interpretation; a hash alone does not certify compiled output.
- `index_build_id` — an embedding/search-index build; `envelope_id` — one context package delivered; `receipt_id` — one execution-evidence record, which may carry an unproven or rejected verdict.

Preserve the existing formulas, membership and artifact-closure rules. Add to Relationships:

For Alder, selection follows Finance's authored links from the retention definition to the starting-cohort rule and computation declaration. Plain Markdown links remain generic links unless an authored producer extension supplies a stronger predicate. The compiler never invents a cohort relation from semantic similarity.

Replace the runtime schema's determinism/Graph paragraphs with:

**Relational is authoritative.** The OKF graph projection consists of versioned concepts, resources and relationship assertions with immutable snapshot membership. Seed lookup, bounded expansion and evidence paths work through relational queries. No baseline correctness gate requires Property Graph.

**Two kinds of determinism.** Compilation fixes the semantic input closure and reproduces its `snapshot_id`. Controlled retrieval fixes the publication and selection contract to reproduce selected context. Index builds, ranking, policy evaluation and packing are separate inputs; a deterministic compiler does not make every search or model decision deterministic.

**Property Graph is optional.** Current [BigQuery Graph documentation](https://docs.cloud.google.com/bigquery/docs/graph-overview) describes graph inputs from tables or views. This profile still must test its own versioned projections, key uniqueness, permissions and relational/GQL equivalence in Phase 5. Product API availability is not evidence that Graph-over-OKF is implemented. Preserve deployment-scoped graph naming and compiler-side key validation.

## B09 — replayable retrieval and selection evidence

**Disclosure summary:** Replayable retrieval, lifecycle modes and the Context Envelope

Discovery can start with keywords, vector similarity or a model-selected seed. Those techniques find candidates; they do not by themselves bind a definition, its linked rules and its computation into one repeatable selection. The proposed controlled path starts from a fixed selection and uses explicit SQL or bounded relational walks over a pinned publication.

**What must be fixed.** Record the publication; seed IDs; query or walk definition and bindings; versioned facts used by selection; traversal depth and result limits; lifecycle evaluation time/mode; ranker and index build if used; stable tie-breaking and ordering; output schema; tokenizer and packing budget. Exclude volatile functions and unversioned external inputs from the controlled guarantee. An explicit order, including tie-breakers, is part of the query contract, not something SQL supplies implicitly.

With those inputs fixed and equivalent effective access, the controlled path selects the same versioned items, paths, ordering and context shape. It need not reproduce request timestamps, opaque envelope IDs or the LLM's final answer. If a model picks a different seed, an index changes or a token budget changes, those are different inputs. Vector retrieval can be deterministic; the comparison is about explicit selection semantics, not an intrinsic defect in embeddings.

**Current authorization still applies.** Authenticate the requester and evaluate current policy before disclosure and throughout the path. A historical publication does not preserve permission to read it. Revocation, quarantine, purge or expired retention may prevent replay; the runtime must not restore historical privileges to manufacture identical output.

**Retrieval evidence.** Retain the selection inputs, returned version IDs and paths, policy/ranker versions, ordering and packing in the governed envelope manifest. Record the authoritative retrieval job/query evidence needed to explain the selection. This is the proposed “retrieval receipt”: a record of context selection, not proof that the business metric ran. Define its versioned serialization before implementation; do not change public identifiers or `context_ref` as an incidental documentation edit.

Keep the existing lifecycle-mode examples, instruction boundary, keyed equality formulas, random `envelope_id`, manifest IAM and disclosure limits. The retained manifest can reconstruct an authorized historical envelope without rerunning discovery; the next section distinguishes that from a controlled query rerun.

## B10 — explainable access without invented ACLs

Replace the policy-authority paragraph, preserving the surrounding every-hop enforcement requirement:

**Policy authority, v1.** OKF frontmatter is not an ACL. The initial profile supports one security domain per bundle/deployment, with caller-delegated BigQuery authorization as its policy source. Mixed-policy bundles fail closed unless an external policy resolver is configured. Per-node enforcement is proposed integration work; placing access relationships in graph metadata does not enforce them.

For this custom-entry Catalog projection, the EntryGroup is the access boundary for published concept bodies. This is not a claim that all Catalog permissions operate only at EntryGroup scope: source-system metadata permissions and entry/aspect operations have their own checks. A bundle with mixed body visibility must not be projected into one broadly readable EntryGroup. [Catalog IAM permissions](https://docs.cloud.google.com/dataplex/docs/iam-permissions).

**Who accessed which asset, under which policy?** Bind the authenticated user or agent requester to the execution identity at the trusted runtime boundary. Evaluate policy against the projected asset and, when fetching underlying data, its source permissions. Check intermediate nodes and evidence as well as returned nodes. A shared service account alone cannot identify Maya's agent; a node containing an access label cannot grant access to a file.

Retain the evaluated policy version/context and permitted asset decisions in privileged audit records linked to the request. Keep source permissions current and reevaluate cached or historical reads. User-visible explanations expose only authorized paths; full decisions and denied-asset details stay behind the audit boundary.

**Alder consequence:** Maya can trace why the agent was permitted to use the total-ARR asset. Permission to read that asset does not make its query the correct retention calculation.

In Catalog ownership, retain ledger discipline and editor-delete risk, but qualify its final “only IAM boundary” sentence to **the custom-entry body projection shared by those publishers**.

## B11 — verifiable execution

**Disclosure summary:** Verifiable execution: the Attested Computation protocol

Retrieval identifies the declared computation. Execution must separately demonstrate what actually ran. The proposed Attested Computation path binds the context publication and envelope, computation artifact, complete declared parameter bindings, caller-delegated BigQuery job and result path. Validation must also tie the reported result to that execution; matching a query while substituting its displayed answer is insufficient.

The agent may bind declared parameters; it may not improvise SQL or swap the computation while retaining this profile's attestation claim. The independent, constrained attester checks authoritative execution evidence under the existing threat model. A successful lookup, a self-reported “verified” label or a job ID alone cannot supply that evidence.

**Alder consequence:** If the job used total-ARR SQL instead of the declared starting-cohort calculation, the mismatch is rejected. If the required artifact, binding, job or output evidence is unavailable, the verdict is `UNVERIFIABLE`. Either way, 118% cannot be presented as an attested retention result. A retrieval receipt does not turn it into one.

Preserve the existing normative subsections for identity/grants, named parameters, exact verdicts, both receipt artifacts, authenticated proofs, keyed commitments, key lifecycle and threat model. Preserve the distinction between a trusted process-integrity claim and correctness of underlying data. Add near the verdict subsection:

**Implementation status:** These are acceptance requirements of the proposed profile. Existing demo computation attesters are stubs and their receipts remain `UNVERIFIABLE`; neither the Alder illustration nor the recorded probes satisfies this attestation contract.

## B12 — reproducibility ladder

**H2:** Replayable context has explicit inputs and limits

These are proposed guarantees while the required artifacts remain retained and the caller remains authorized. Stable identity does not promise indefinite storage, continuing access or unchanged business data.

| Level | Contract |
| --- | --- |
| Identity | A snapshot identifies its complete compile-input closure; a publication identifies the observation/snapshot/deployment binding. Identity alone proves neither output correctness nor a successful recorded deployment. |
| Snapshot reconstruction | Reconstruct complete snapshot membership and immutable versions while they remain retained. |
| Envelope reconstruction | Reconstruct what was served from its retained manifest and referenced content, without rerunning discovery. Apply current access, revocation, quarantine and purge checks. |
| Controlled retrieval replay | Repeat the same selection only with the fixed publication, query/walk, bindings, fact versions, lifecycle inputs, ranking, ordering, packing and equivalent effective access. Free discovery and different inputs carry no equal-selection promise. |
| Computation-contract reconstruction | Recover the declared computation, executor and attester artifacts while the complete artifact closure remains available. |
| Result reproduction | Requires retained data-version evidence as well as the contract. Mutable facts or an expired data snapshot can prevent reproducing the number, even when the context is known. |

New retrieval requests can receive different opaque envelope IDs while selecting the same context. Replayability does not require exposing a deterministic content hash or restoring an old permission grant.

## B13 — acceptance and phase additions

**Acceptance introduction:** Accepting this RFC agrees to a design and its gates. It does not mark those gates complete.

Add these items to the existing acceptance list, consolidating overlapping prose:

- **Replayable context:** A fixed authorized publication and selection contract return the same versioned definition, cohort rule and declared computation, with selection evidence. Catalog pins either resolve as requested or fail stale.
- **Explainable access:** Every disclosed path is authorized under current policy. Requester/execution binding and privileged records explain returned assets; denied intermediates and revoked cached access fail closed without leaking asset existence.
- **Verifiable execution:** A substituted query or result fails validation; incomplete authoritative evidence yields `UNVERIFIABLE`. The receipt binds the actual execution to the declared computation and supplied context.
- **First workload:** An initially empty BigQuery project can host the projected graph. Data-dependent queries still require the relevant versioned facts.

Keep the existing optionality, conformance, identity, authored-link and BQAA items. Change “no blocking questions remain” to “The recommendations in §04 define the proposed scope; unresolved implementation evidence belongs to the phase gates below.” Keep named-validator and sign-off work explicitly open.

**Phases introduction:** The existing Germany fixture remains the regression baseline. Alder adds an illustrative acceptance case for three outcomes: Phase 1 builds the graph projection, Phase 2 aligns Catalog publication pins, Phase 3 establishes controlled retrieval and explainable access, and Phase 4 establishes computation evidence. None of these additions marks a phase complete.

Apply these additions to **both** the phase overview table and the corresponding detailed gates:

| Phase | Outcome / gate addition |
| --- | --- |
| 0 — Contract + fixture | Specify the controlled retrieval inputs and versioned manifest requirements before runtime implementation. Preserve the existing Germany vectors and open validation/sign-off work. Alder is a proposed additional case, not a claimed new fixture on disk. |
| 1 — Compiler + BQ core | Establish the projection as a first workload. Repeated publication-scoped relational selection over fixed fixtures uses explicit stable ordering and preserves linked definition/rule/declaration paths. No agent IAM or attestation completion claim. |
| 2 — Catalog projection | Retain existing pin-or-fail-stale/coexistence gates. Test the chosen full-entry read path for actual runtime pins; the recorded `okf` aspect reads do not substitute for that test. |
| 3 — Retrieval + access | Repeat controlled retrieval under fixed selection inputs and equivalent access; compare ordered versioned items/paths/shape. Change seed, fact version, time policy or packing to demonstrate the guarantee's limits. Deny an intermediate node and revoke access before cached replay: no disclosure. Validate requester binding and privileged audit records without denied-asset leaks. |
| 4 — Execution evidence | With correct context but total-ARR SQL, reject the query/declaration mismatch. Substitute the displayed result and reject its binding. Remove evidence and return `UNVERIFIABLE`. Retain all existing attester/key/privacy negative tests. |
| 5 — Hardening + pilot | Keep optional Graph/index compatibility and relational equivalence tests. A Finance pilot exercises retrieval, access and computation boundaries on its own data; do not prescribe Alder's invented 96% as its expected result. |

Add to the risk table:

| Risk | Mitigation | Gate |
| --- | --- | --- |
| “Pinned” retrieval still uses mutable or unstable inputs | Version selection inputs; stable ordering/ties; separate free discovery from controlled retrieval and reconstruction | Phases 1 and 3 |
| Historical context restores access that has been revoked | Reevaluate current policy, cached output and intermediate nodes; privileged explanations only | Phase 3 |
| Context citation is mistaken for computation evidence | Separate selection record from validated job/context/result receipt | Phase 4 |

## B14 — observed evidence and closing

Replace the current prototype note with:

**What the recorded demos establish.** The [derived-OKF demo](./demo/) shows the Germany context handoff and unproven-answer framing; that path performs no Catalog write and attests nothing. The [full demo](./full-demo/) separately records operator-run Catalog sample setup/push and reads, BigQuery DDL with seeded rows, serving probes and attribution queries. It also documents the proposed sync and IAM design. These are separate evidence paths, not a completed Alder runtime.

The checked-in probes return `NO_HEAD`, `AMBIGUOUS_LEGACY` and `FAIL_CLOSED`. The seeded publication rows are not governed commits. Phase A identities and negative IAM checks, governed sync/runtime pins, Graph-over-OKF retrieval and validated computation receipts remain unbuilt or unproven by those captures. Demo computation receipts remain `UNVERIFIABLE`. [Capture inventory and limitations →](./full-demo/live/README.md) · [25-second CLI tape →](./demo/#walkthrough)

For deeper evidence, use a small list or disclosure, not a second essay:

- **Observed overclaim:** A [recorded Germany session](./full-demo/live/session_04fa3d56.json) called its answer verified after context lookup without computation evidence. A [separate prompted session](./full-demo/live/session_f21ee192.json) reports unproven answers with stub receipts. This is not a before/after test of an implemented enforcement runtime.
- **Observed serving state:** [Head probe](./full-demo/live/beat5_serve_stmt1.json), [resolution probe](./full-demo/live/beat5_serve_stmt3.json) and [seeded publications](./full-demo/live/beat5_serve_stmt4.json). No recorded head advance establishes `BQ_COMMITTED`.
- **Observed query provenance:** [Session-summary query evidence](./full-demo/live/provenance_sessions_summary.json) and [job identity capture](./full-demo/live/bq_jobs_identity.json) concern the operator's actual SELECT jobs. They are not validated OKF metric receipts or Alder execution evidence.

Keep the existing Phase 0 note as a dated report of **off-site working files**, not freshly verified local evidence. Its pending named-validator, regenerated-vector rerun and owner sign-offs must remain pending. Main RFC numeric phases and full-demo's “Phase A” are different planning schemes; do not map their completion statuses onto one another.

**Closing H2:** Give the agent context it can replay—and a number it can account for

OKF supplies the authored definition, relations and computation declaration. Catalog makes that knowledge discoverable and governed. The proposed BigQuery runtime selects a pinned context, explains current access and checks execution evidence. BQAA observes use without becoming the authority for any of them.

**BigQuery turns the OKF graph into replayable context for agents—with explainable access and evidence that the declared computation ran.**

**One pilot:** Sponsor a Finance-owned retention pilot through these gates. Project its knowledge graph and version the required cohort facts. Repeat the selected context, test access boundaries, then validate the actual retention computation. Substitute the query or withhold execution evidence: the reported number must stay unproven.

**Footer provenance addition:** Runtime framing and proposed retrieval/access/execution contracts updated 2026-09-05. Earlier consolidation and Catalog-alignment reviews apply to their dated baselines; this revision makes no new implementation-completion or review-approval claim.
