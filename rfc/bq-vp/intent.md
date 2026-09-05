# Intent — the board story and replayable context

## Audience and goal

A BigQuery VP should understand the Alder near-miss in 30 seconds, then understand the technical reason to bring BigQuery into Knowledge Catalog + OKF in two to three minutes. Keep one continuous page, with the concrete story before the architecture.

At 8:55, Maya Chen, VP of Finance at fictional subscription software company Alder, catches an agent's 118% retention figure in a board pack supporting a $4 million expansion plan. It includes new customers. The starting cohort retained 96%; Maya pulls the slide before the 9 a.m. meeting.

## The reason for BigQuery

**BigQuery turns the OKF graph into replayable context for agents.**

Catalog discovers and governs concepts. OKF authors their definitions, relationships, computation declarations and versions. The proposed BigQuery runtime projects that graph and retrieves context through explicit SQL or bounded graph walks against a pinned publication. Fixed queries, parameters, fact versions, access scope and ordering make the selected context and result shape reproducible.

Make this distinction first-class: discovery is not deterministic graph retrieval. Vector similarity and model-directed exploration can help find candidates; the proposed graph queries define which linked context is selected and make that selection replayable and recordable in a retrieval receipt.

BigQuery can begin by hosting the knowledge-graph projection and versioned facts. Its value does not depend on an existing revenue warehouse. The projection must actually enter BigQuery to be queried there.

## Story connection and ask

Maya needs the linked retention definition, starting-cohort rule and approved computation as one repeatable context selection. Execution of the metric follows separately: a computation receipt binds job, context and result; attribution names the agent and execution identity under IAM. A retrieval receipt is not evidence that the metric ran.

Ask for one Finance-owned retention pilot. Repeat the same pinned retrieval and compare returned context, then compute retention for one quarter of cohort data. Withholding execution evidence must leave the number unproven.

## Honesty and scope

The company, people, quote and numbers are illustrative. Graph-over-OKF, retrieval receipts and the governed runtime are proposed/RFC. Existing full-demo recordings are optional supporting evidence for a different scenario, not proof of this retrieval or Alder's figures. Do not claim built Graph, successful attestation, completed sync or Phase A IAM.

Edit the VP page and its local story/intent/spec/plan. Preserve the accurate RFC entry link and leave `/rfc/full-demo/` unchanged. Work on `feat/rfc-bq-vp-det-retrieval` from main at `bf92ee8`; commit, push, open a new PR against `main`, and report its URL and HEAD. Save the session record under `/tmp/okf-vp-det/`. Do not merge.
