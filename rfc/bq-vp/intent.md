# Intent — the board story and three runtime advantages

## Audience and goal

A BigQuery VP should understand the Alder near-miss in 30 seconds, then explain three distinct reasons to add a BigQuery runtime to Knowledge Catalog + OKF in two to three minutes. Keep one continuous static page, with the concrete story before the architecture.

At 8:55, Maya Chen, VP of Finance at fictional subscription software company Alder, catches an agent's 118% retention figure in a board pack supporting a $4 million expansion plan. It includes new customers. The starting cohort retained 96%; Maya pulls the slide before the 9 a.m. meeting.

## The comparison

Replace the former role cards with three paired comparisons, labeled **KC + OKF** and **+ BQ runtime**. Retain a short role introduction: Catalog discovers and governs; OKF authors the graph. The right column describes proposed runtime responsibilities.

1. **Replayable context.** Catalog discovery and the authored OKF graph do not themselves assemble pinned linked context. BigQuery hosts the projection and retrieves it with a pinned publication and explicit SQL or bounded walks. Fixed query, parameters, fact versions, access scope and ordering return the same selected context and shape. Maya's agent receives the retention definition, cohort rule and declared computation together.
2. **Explainable access.** Scope the EntryGroup statement to custom entries in this design. The proposed runtime joins identity, policy and projected assets, binds the requester to the execution identity, enforces access along the retrieval path and records returned nodes. It can explain why this agent could see a specific asset.
3. **Verifiable execution.** Finding a declaration does not prove the calculation ran. The runtime runs retention and validates a job ↔ context ↔ result receipt against the declared computation. A substituted query or missing evidence leaves the number unproven.

The graph projection and versioned facts can be the first BigQuery workload; an existing revenue warehouse is not required. Data must actually enter the projection to be queried there. The case is the combined runtime contract, not a claim that no other engine could implement it.

**BigQuery turns the OKF graph into replayable context for agents—with explainable access and evidence that the declared computation ran.**

## Guardrails and ask

Similarity ranks candidates but does not pin linked context; vector search is not inherently nondeterministic. Replayable context does not promise identical LLM answers. Access metadata requires enforcement; source permissions must stay current, and metadata visibility does not grant access to the underlying file. Per-node decisions need an authenticated requester binding, not a self-reported agent label.

Ask for one Finance-owned retention pilot: repeat pinned retrieval, test access boundaries, and compute retention over one quarter of cohort data. Withholding execution evidence must leave the number unproven.

## Honesty and scope

Alder, Maya and the figures are illustrative. Graph-over-OKF, per-node authorization and validated receipts remain RFC proposals. Existing full-demo computation attesters are stubs; receipts are UNVERIFIABLE. Governed sync and Phase A IAM remain unbuilt. Native BigQuery capabilities do not establish completion of this proposed integration.

Edit only the VP page and its local story/intent/spec/plan. Preserve the accurate RFC entry link and leave `/rfc/full-demo/` unchanged. Work on `feat/rfc-bq-vp-3pts` from main (including merged PR 21); commit, push, open a PR against main, and report its URL and HEAD. Save the session record under `/tmp/okf-vp-3pts-page/`. Do not merge.
