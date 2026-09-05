# Intent — the board story and three runtime advantages

## Audience and goal

This short customer/runtime brief should make the Alder near-miss clear in 30 seconds, then explain three distinct reasons to add a BigQuery runtime to Knowledge Catalog + OKF in two to three minutes. Keep one continuous static page, with the concrete story before the architecture and no audience label addressing a product executive.

At 8:55, Maya Chen, VP of Finance at fictional subscription software company Alder, opens a board pack supporting a $4 million expansion plan. An analyst catches new customers in the agent's “verified” 118% retention figure; the starting cohort retained 96%. Maya pulls the slide with three gaps unresolved: the linked cohort rule and declared computation were not pinned with Finance's definition, she cannot trace the policy allowing this agent to use the total-ARR asset, and no execution receipt binds its query and result to the declared retention calculation.

Publish the brief at `/rfc/board-pack/`. One native Technical design disclosure follows the comparisons and first-workload line, before the punchline. Keep it closed by default so the skim stays short; readers can expand the proposed retrieval, access and execution mechanisms. The details must be keyboard accessible and included in print.

## The comparison

Replace the former role cards with three paired comparisons, labeled **KC + OKF** and **+ BQ runtime**. Retain a short role introduction: Catalog discovers and governs; OKF authors the graph. The right column describes proposed runtime responsibilities.

1. **Replayable context.** Catalog discovery and the authored OKF graph do not themselves assemble pinned linked context. BigQuery hosts the projection and retrieves it with a pinned publication and explicit SQL or bounded walks. Fixed query, parameters, fact versions, access scope and ordering return the same selected context and shape. Maya's agent receives the retention definition, cohort rule and declared computation together.
2. **Explainable access.** Scope the EntryGroup statement to custom entries today. The proposed runtime joins identity, policy and projected assets, binds the requester to the execution identity, enforces access along the retrieval path and records returned nodes. It can explain why Maya's agent could use the total-ARR asset. The story describes an unexplained authorization path, not a proven permissions violation.
3. **Verifiable execution.** Finding a declaration does not prove the calculation ran. The runtime runs retention and validates a job ↔ context ↔ result receipt against the declared computation. A substituted query or missing evidence leaves the number unproven.

The graph projection and versioned facts can be the first BigQuery workload; an existing revenue warehouse is not required. Data must actually enter the projection to be queried there. The case is the combined runtime contract, not a claim that no other engine could implement it.

**BigQuery turns the OKF graph into replayable context for agents—with explainable access and evidence that the declared computation ran.**

## Guardrails and ask

Similarity ranks candidates but does not pin linked context; vector search is not inherently nondeterministic. Replayable context does not promise identical LLM answers. Access metadata requires enforcement; source permissions must stay current, and metadata visibility does not grant access to the underlying file. Per-node decisions need an authenticated requester binding, not a self-reported agent label.

Ask for one Finance-owned retention pilot: repeat pinned retrieval, test access boundaries, and compute retention over one quarter of cohort data. Withholding execution evidence must leave the number unproven.

## Honesty and scope

Alder, Maya and the figures are illustrative. Graph-over-OKF, per-node authorization and validated receipts remain RFC proposals. Existing full-demo computation attesters are stubs; receipts are UNVERIFIABLE. Governed sync and Phase A IAM remain unbuilt. Native BigQuery capabilities do not establish completion of this proposed integration.

Move all brief files to `rfc/board-pack/`, update the canonical and RFC index href, and keep the visible Board-pack near-miss label. Leave only a meta-refresh redirect with a fallback link at `/rfc/bq-vp/`. Preserve the hero, arithmetic, three comparisons, punchline, pilot ask and existing honesty labels; do not restore the footer or evidence deep-dive link. Leave `/rfc/full-demo/` unchanged unless an old brief href needs updating. Work on `feat/rfc-retention-runtime-details` from main at `de43648`; commit, push, open a PR against main, and report its URL and HEAD. Save the session record under `/tmp/okf-vp-details/`. Do not merge; Opus + Kimi are the requested review gate.
