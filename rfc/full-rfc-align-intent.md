# Intent — full RFC alignment and human tone

Date: 2026-09-05 PT. Evidence cutoff: the supplied 2026-09-06 UTC status. Baseline: `d3f66f437977d6fa18e695477c849d06444f7781`. Target of the subsequent implementation: `rfc/index.html`.

## Outcome

A reader can explain why the proposed BigQuery runtime is worth pursuing for a specific customer, what the two recorded examples establish, and what must still work together before the combined product claim is justified. The opening reads like the board-pack brief; the full RFC retains the argument, contracts, tradeoffs, acceptance requirements and Phase 0–5 design behind it.

The central sentence becomes conditional: **The proposed BigQuery runtime would turn the OKF graph into replayable context for agents—with explainable access and evidence that the declared computation ran.** Use the same sentence in the masthead and closing. The profile remains a proposal even though separate retrieval and receipt examples now exist.

## What changes

The strongest opportunity is for analytical agents whose relevant facts already live in BigQuery, on Enterprise or Enterprise Plus capacity, within customer-accepted latency, freshness, concurrency and cost budgets. No customer has agreed that operating budget yet. This is a scoped opportunity judgment, not measured product readiness or a claim about where fictional Alder stores data. A more general Knowledge Catalog serving layer needs a separate case against simpler SQL retrieval, Neo4j and Spanner Graph.

The recorded work advances two separate pieces. One Acme example retrieved linked rules and the declared SQL on an Enterprise reservation; that SQL was found, not run. Another Acme example executed a caller-owned job, checked authoritative job and result evidence in a fresh process, and enforced result release at a consumer. It is example code and tests, not a library feature or the independent attester proposed by the full RFC. Neither example ran Alder's story, closed the wider demo's placeholder checks, or demonstrated the connected runtime.

The implementation must preserve the difference between an attempted measurement and a completed benchmark: **speed benchmarks are not finished yet (0 of 9 cells complete)**. Per-requester graph access and publication consistency are unfinished; source pins are not a live Catalog discovery integration. Recorded capacity teardown is not proof of every job or fixture resource being cleaned up.

Receipt work remains the first deliverable to carry forward and must not wait for graph results. The two experiments run in parallel; numeric phases still describe the full implementation's dependencies. A successful example earns confidence only in its demonstrated part. The combined claim requires one connected catalog-to-result path, publication consistency, and negative authorization tests. The 2026-09-19 checkpoint is an evidence review, not a production deadline.

## Tone and depth

Use statements such as “Especially strong when,” “What the examples show,” “What remains to prove,” and “The access checks are unfinished.” Do not replace engineering score labels with vague optimism. Each limitation names what has not been established and what evidence would settle it.

Keep Replayable context, Explainable access and Verifiable execution as the three outcomes. Keep the paired KC + OKF / + BQ runtime comparison. Preserve the long design: identities and hashes, source authority, Catalog reconciliation, publication consistency, controlled retrieval, authorization, execution evidence, BQAA ownership, reproducibility, acceptance and delivery phases. Do not transplant the board-pack layout or collapse the full RFC into another short brief.

## Authority and boundaries

The user request governs this pass. `JOINT_final.md` governs the opportunity scope, sequencing, promotion rule and downgrade conditions; `SPIKE_STATUS.md` supersedes its pre-experiment delivery facts. Both source files remain in the EM directory `/tmp/okf-full-rfc/`. The pinned reports listed in the [spec](full-rfc-align-spec.md) supply the detailed limits. The merged `rfc/board-pack/index.html` and `rfc/board-pack/STORY.md` govern the human tone and illustrative story. This packet supersedes conflicting instructions in `rfc/full-update-*` for this alignment; those older files remain historical and unchanged.

Keep OKF v0.2 portable and unchanged, relational serving authority, the independent-attester target, exact public identifiers and the numeric Phase structure. Germany active-customer revenue remains the Phase 0 fixture and recorded-demo identity. Alder, Maya, the $4 million proposal and 118%/96% arithmetic remain illustrative. Acme is the separate experiment fixture, not a replacement for either.

This Astra pass writes only four planning files, mirrors them under `rfc/`, commits and pushes `feat/full-rfc-align-human`. It creates no PR, review comment, merge, deployment, HTML implementation or cloud run. Fable owns the next HTML implementation; Haiyuan remains the merge gate. `rfc/demo/`, `rfc/full-demo/`, `rfc/board-pack/`, their evidence, and the legacy redirect stay unchanged.

## Handoff

The [spec](full-rfc-align-spec.md) owns requirements, evidence links, tone rules and preservation checks. The [content map](full-rfc-align-content-map.md) names every section and provides replacement copy. The [plan](full-rfc-align-plan.md) orders the work and defines review evidence. Fable should need no older chat, score translation or invented product decision to implement this packet.
