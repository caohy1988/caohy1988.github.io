# Spec — full RFC framing and contract alignment

Date: 2026-09-05. Scope: document implementation in `rfc/index.html`; runtime implementation is outside this slice. [Intent](full-update-intent.md) · [Content map](full-update-content-map.md) · [Draft](full-update-DRAFT.md).

## Requirements

### Narrative and scope

- R1. Update the title/lede, summary, motivation, architecture, design details, reproducibility, acceptance, phases and closing as one coherent RFC. Keep existing section IDs and numeric section references stable. The old demo-slice intent/spec/plan stay untouched.
- R2. Use the locked punchline and the exact three outcome names: Replayable context, Explainable access, Verifiable execution. Present one compact **KC + OKF | + BQ runtime** comparison in the summary, explicitly labeled proposed guarantees. Define KC and OKF before abbreviating them. This compares the baseline without this runtime, not everything a custom retriever could ever do.
- R3. Replace the Germany motivation narrative with Alder's illustrative board-pack near-miss: Maya, 8:55, a 9 a.m. meeting, a $4m expansion proposal, 118% claimed retention and 96% same-customer retention. Include the compact arithmetic `(9.6 + 2.2) / 10.0 = 118%` versus `9.6 / 10.0 = 96%`, all ARR measured across one quarter. Preview all three gaps in plain language; link to `./board-pack/`. Do not duplicate the entire brief or its SVG.
- R4. Preserve Germany as the existing Phase 0 regression fixture and recorded-demo scenario. Alder is an additional proposed narrative/acceptance example, not a replacement fixture or an executed pilot. Keep the full-demo story and evidence separate.
- R5. Explain the empty-BigQuery case: project the authored OKF graph into BigQuery and version the facts needed by retrieval or execution. No existing revenue warehouse is required; no projection means no BigQuery retrieval. Preserve source-bundle authority and optional OKF v0.2 profile conformance.

### Three runtime contracts

- R6. Make controlled retrieval a first-class **proposed** contract distinct from deterministic compilation. Pin publication, seed/selection, query or bounded-walk definition, bindings, fact versions, traversal limits, lifecycle evaluation inputs, ranking/tie-breaking, output schema and packing. Hold effective authorization equivalent for an equal-output claim; reevaluate current access for every request. Fix any index build used. Avoid volatile functions, unstable ordering and unversioned external dependencies.
- R7. Promise the same selected versioned items, paths, ordering and context shape only under R6's fixed inputs and current authorization. New request IDs, times and opaque random `envelope_id`s need not match. Free-form LLM planning and optional similarity discovery are outside this guarantee until their selected inputs are fixed. Vector search can be deterministic; graph retrieval does not imply identical model answers or factual truth.
- R8. Keep **envelope reconstruction** separate from rerunning retrieval. A retained manifest reconstructs what was served without reranking; a controlled query rerun reproduces its selection only under R6. Permission revocation, quarantine, purge or expired retention must stop a replay or change permitted output. Never restore old permissions to force equality.
- R9. Scope EntryGroup wording to this custom-entry Catalog projection. Other Catalog operations, entry/aspect types and source-system permissions have their own checks. Runtime access joins identity ↔ current policy ↔ projected assets and binds authenticated requester to execution identity; a shared service account alone is insufficient attribution. Metadata visibility does not grant underlying file/data access.
- R10. Preserve the v1 single-security-domain boundary with caller-delegated BigQuery authorization. Mixed-policy bundles fail closed unless an external policy resolver is configured; the Catalog body projection must not leak what the runtime denies. Fine-grained path enforcement remains proposed integration work, not an automatic native Graph ACL feature. Check candidates, intermediate nodes, edges, evidence, computations, outputs and cached envelopes before disclosure. Full decisions belong in privileged audit records; user-visible explanations must not expose denied asset existence.
- R11. Separate retrieval evidence from computation evidence. The retained retrieval manifest records how context was selected; “retrieval receipt” is a reader-facing description of that proposed record, not a new attestation verdict or new public ID. The execution receipt binds publication/envelope, computation artifact and declared parameters to the actual job and result path. Validate the reported result's binding as well as the query; a definition citation cannot validate substituted total-ARR SQL. Preserve `ATTESTED`, `UNVERIFIABLE`, `REJECTED`, the independent attester, integrity proofs, key lifecycle and the stated threat model. A job ID alone is insufficient. Missing evidence stays unproven; demonstrated mismatch is rejected. No data-quality guarantee.
- R12. Preserve relational tables as serving authority. “OKF graph projection” describes compiled knowledge relations and does not require the optional BigQuery Property Graph/GQL surface. No baseline correctness gate depends on that surface. Update broad “searchable/traversable/attestably computed” claims and relevant architecture labels to reflect R6–R11.

### Honesty, evidence and presentation

- R13. Put a concise RFC/proposed status near the lede and label the comparison and architecture as proposed. State what existing captures do and do not demonstrate. Preserve carefully scoped normative state names, including `BQ_COMMITTED`, and future `ATTESTED` verdict definitions. Do not claim either occurred in Alder or the recorded stub demos; do not mark Phase A or any numeric phase complete without scoped evidence.
- R14. Use main-RFC links `./board-pack/`, `./demo/`, `./demo/#walkthrough` and `./full-demo/` accurately. No “BigQuery VP” audience label or old brief path in new reader-facing copy. Main currently already has the correct board-pack link; no migration is needed. Leave the legacy redirect and full-demo's own show notes alone.
- R15. Preserve the long RFC's readable light palette, semantic headings, source links and native disclosures. Add local CSS in its existing style block only as needed for the comparison/callout/navigation. Use a labeled paired layout or an accessible table that remains usable at 1280/900/768/375/320 without document overflow. Do not copy the short page's whole dark design, add a six-step UI, or introduce JavaScript.
- R16. Keep comparison guardrails adjacent to their claims. Preserve readable screen and print output; any newly moved/collapsed baseline or design text must remain available to keyboard and print users. Reuse the no-JS print approach already documented by the board-pack implementation if necessary; do not depend only on Chromium's `::details-content` behavior.

## Preserve these contracts verbatim in meaning

| Existing contract | Required treatment |
| --- | --- |
| Observation / snapshot / publication / deployment / sync identities | Do not change hash formulas, canonical encoding or membership rules. Correct “snapshot proves output” shorthand to “identifies compile-input closure.” |
| `envelope_id` and equality commitments | Keep random, opaque tenant-scoped IDs and privileged keyed digests. No public content-hash identifiers. |
| `okf`, `okf-context-runtime`, `okf-computation` | Keep shipped authored signals, separate pins/stamps and runtime computation facts in their existing separate aspects. Never append runtime pins to shared `okf`. |
| Publication state machine | Keep atomic BigQuery head advance, then Catalog reconciliation; pin-or-fail-stale and no rollback for Catalog failure. |
| OKF links and authoring | Untyped core Markdown links remain untyped; producer extensions are optional; no LLM-guessed predicates or ACL frontmatter. |
| BQAA seam | Keep `context_ref` and observer ownership. No new public telemetry fields, raw principals, policy decisions or graph paths. |
| Attestation threat model | Verify process integrity under trusted components; no guarantee against compromised components or bad source data. |
| Existing Germany evidence and Phase 0 vectors | Preserve identities and historical qualification; don't relabel them as Alder evidence or proof of phase completion. |

## Acceptance examples for the proposed runtime text

These are requirements the updated RFC must describe, **not tests of a runtime implemented in this PR**.

| ID | Given / action | Required statement in the RFC |
| --- | --- | --- |
| AE1 | Same retained publication, approved selection contract, bindings, versioned facts and effective access; repeat retrieval | Same ordered selected items/paths/schema; independent request IDs may differ. |
| AE2 | Catalog shows an older publication | Serve that authorized retained publication or fail stale; never silently use a new head. |
| AE3 | An intermediate asset is denied, or access is revoked before cached replay | Stop disclosure; current policy wins over historical context. Explanations do not leak denied asset identities/counts. |
| AE4 | Correct Finance definition is cited, but total-ARR SQL is run | The query/context mismatch cannot receive `ATTESTED`; the 118% claim is unproven. |
| AE5 | Job ID exists but parameters, artifact, output binding or authoritative evidence is missing | Return `UNVERIFIABLE`, not success. |
| AE6 | BigQuery project has no customer warehouse | Graph projection can be the first workload; data-dependent retrieval/results require the needed versioned facts. |
| AE7 | Vector/LLM discovery picks a different seed or packing budget changes | Inputs changed; no same-context guarantee. Retained-envelope reconstruction is a separate operation. |
| AE8 | Old query is rerun over changed business facts | Context identity alone does not reproduce the result. Data-version evidence is required. |

## Document verification

- Cover every content-map row; resolve contradictory old sentences rather than adding disclaimers beneath them.
- Read the opening as a customer/runtime argument, then follow each of the three points into the detail, acceptance and phase sections.
- Check links, IDs, disclosure keyboard behavior, requested widths and print. Inspect each main diagram's readable text equivalent at narrow widths.
- Confirm only this slice's artifacts and main HTML are changed in Fable's implementation. No fixture, capture, board-pack, redirect or full-demo edits.
- Retain exact verdict/state names where they define a proposal. A search hit for `ATTESTED` is not itself a defect; an unsupported completed-capability claim is.
