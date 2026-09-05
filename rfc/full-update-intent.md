# Intent — the full RFC for a replayable knowledge runtime

Date: 2026-09-05. Target: `rfc/index.html`, based on main `b2b3c90123acf1733b0c22e574287034d40553ee`.

## Outcome

A reader of the main RFC can explain why an organization would add BigQuery to Knowledge Catalog and OKF, including when it has no existing BigQuery warehouse. The reader can connect each proposed runtime capability to a customer failure, a technical mechanism and an acceptance gate.

**BigQuery turns the OKF graph into replayable context for agents—with explainable access and evidence that the declared computation ran.**

The main RFC becomes the complete argument and design behind that sentence. `rfc/board-pack/` remains its short, illustrative customer brief. This is a substantive update across the main document, not another introductory banner above an unchanged RFC.

## Problem

The current main RFC has strong identity, publication and attestation detail. Its introduction still emphasizes distributing two projections, its motivation leads with Germany revenue, and its determinism claim primarily concerns compilation. A reader must infer how those pieces answer the three questions now made concrete on the board-pack page.

At Alder, Maya's agent found Finance's retention definition, missed the accompanying starting-cohort rule, and reused a total-ARR query. She cannot explain the policy that allowed the agent to use that asset. The pack says “verified,” without execution evidence tying the number to the retention calculation. These are three distinct gaps: connected context, access explanation, and computation evidence.

## Product framing

1. **Replayable context.** KC discovers and governs; OKF authors linked knowledge and computation declarations. The proposed BigQuery runtime serves that graph projection through a pinned, explicit retrieval contract. Similarity search alone does not bind the linked context together; vector search is not inherently nondeterministic.
2. **Explainable access.** Bind an authenticated requester to the execution identity, enforce current policy on the projected assets along the path, and retain governed evidence of what was returned. Policy metadata is an input to enforcement, not enforcement itself.
3. **Verifiable execution.** Separately bind the declared computation, actual BigQuery job, parameters, context and reported result. A successful lookup or a job ID alone does not prove that calculation ran.

BigQuery is the proposed place to host the knowledge projection, query its relations alongside needed facts, and retain execution evidence under explicit authorization. Determinism is not exclusive to BigQuery, and OKF conformance never requires it. The graph can be the first BigQuery workload; it must actually be projected there before retrieval can run there.

## Boundaries

- Keep OKF v0.2 unchanged and portable: no new required frontmatter, typed core predicates, ACL syntax or mandatory runtime dependency.
- Preserve the main RFC's source authority, relational baseline, identity chain, independent reconcilers, separate runtime Catalog aspect, caller-delegated execution, independent attester, privacy rules and numeric Phase 0–5 structure.
- Strengthen the proposed retrieval contract without promising identical LLM answers, permanent access or repeatable results from mutable facts.
- Alder, Maya, 8:55, the $4m proposal and 118%/96% are illustrative. Access was unexplained, not established to be forbidden. The numbers do not establish that the spending proposal itself is bad.
- Preserve Germany's fixture identity and the separate demo evidence. Do not replace recorded sessions or hash vectors with Alder, or imply a recorded probe exercised the full runtime.
- Preserve `rfc/board-pack/`, its SVG and the legacy redirect. Do not rewrite `rfc/demo/` or `rfc/full-demo/` for this slice.

## This handoff

Astra supplies this intent, [the spec](full-update-spec.md), [the content map](full-update-content-map.md), [the implementation plan](full-update-plan.md), and [draft copy](full-update-DRAFT.md). Fable implements the main HTML update and opens or updates the PR afterward. Astra commits and pushes only these artifacts; no PR or merge in this pass.

The existing `rfc/intent.md`, `rfc/spec.md` and `rfc/plan.md` belong to the original BQAA→derived-OKF demo slice. They are not superseded. `rfc/kc-align-*` remain historical alignment artifacts; the current main RFC and `kc-align-spec.md` take precedence over stale pin-placement wording in the older alignment intent/plan.

## Success

The opening skim communicates the proposed runtime's three outcomes and the Alder stakes. The detailed read specifies what is pinned, what authorization still changes, what each evidence artifact proves, and what remains unbuilt. A maintainer can locate the corresponding Phase 1–4 gates without treating a customer illustration as a conformance fixture or a successful deployment.
