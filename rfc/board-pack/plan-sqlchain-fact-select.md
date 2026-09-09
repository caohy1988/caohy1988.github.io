# Plan — after the fact-data version is SELECTED: what fills the request-to-consumer cells

Status: proposed sequencing only. No dates, no staffing claim, no spending authorization. Each slice is small enough
to review on its own. Intent in `intent-sqlchain-fact-select.md`; the record and its gates in
`spec-sqlchain-fact-select.md`. Nothing below changes a measurement or accepts a threshold.

## What this selection changed and what it did not

| Item | Before | After this slice |
| --- | --- | --- |
| `facts.state` | `UNSELECTED`; blocked both consumer cells with `FACTS_UNSELECTED` | `SELECTED` (synthetic fixture digest); blocks nothing |
| Consumer cells `sqlchain_forced_c1` / `_c5` | `INCOMPLETE`, `NOT_IMPLEMENTED + FACTS_UNSELECTED`, 0 of 20 | `INCOMPLETE`, `NOT_IMPLEMENTED`, 0 of 20 |
| Customer (Alder) fact data | a clause inside the fact row | its own row, `NOT SELECTED — customer dependency` |
| Live dataset rows versus the digest | not stated | `UNVERIFIED` (no live read made) |
| September 7 chain versus the digest | not stated | `UNPROVEN` (consistent result; load job retained as a prefix) |
| Cost cells | five `UNMEASURED` | five `UNMEASURED` |
| Thresholds | all PROPOSED | all PROPOSED |

## Slices

### FS-0 — select and record (this slice)

The record, the vendored artifacts, the extractor, the validation gates, the regenerated card, the surface wording
and the tests in the spec. Offline only. Done when the pull request is open and the offline suite is green.

### FS-1 — hermetic sampled request-to-consumer runner

A driver (`okf_bq_graph.consumer_run`, dry-run and hermetic modes only) that refuses unless `facts.state` is
`SELECTED`, takes one predeclared requester question (the `f_current` forced seed to the gross-margin computation
with the January parameters `2026-01-01` to `2026-01-31`), and repeats it through retrieval, binding, the
caller-delegated job, verification and the consumer decision, retaining every attempt: retrieval time, bind
outcome, job submit and poll times, verdict, decision, the SDK's own elapsed time, the selected content digest and
the evaluation date. Hermetic mode uses the oracle engine and the SDK example's hermetic runner, which returns the
planned `400` and does not compute it from the seven tables; the runner therefore also carries a separate row-based
oracle check over the vendored manifest, so a passing hermetic attempt establishes orchestration and refusal
behaviour, not data equivalence or GoogleSQL execution. The `f_revenue` seed requests a computation the receipt
publication does not carry; its expected outcome is a refusal, declared in advance, not a substituted margin answer.
The `live_precheck` and expiry refusals recorded on the selection become driver behaviour here. Consumer cells then
read `NOT_IMPLEMENTED → RUNNER_HERMETIC_ONLY`, which is still a refusal; hermetic attempts never fill a live cell.
Offline only; a new budget block for consumer sampling is declared in the plan but not spent.

### FS-2 — live sampling, C=1 first, under the owner's paid gate

Same-requester mode first. Before any attempt: the live precheck as recorded on the selection — a full-schema,
full-row readback of the seven tables canonicalised and matched to the content digest, with that verified immutable
or protected table set bound to every attempt's evidence; row counts and the January result are smoke checks that
cannot establish identity — on-demand routing verified per job including the receipt leg's child jobs, and its own budget line
(`consumer_max_bytes_billed_gib`, `consumer_max_usd`, `consumer_max_wall_seconds_per_cell`) inside the existing
ceilings (900 s per cell, 3,600 s per campaign, 64 GiB, $0.50 at the declared $6.25 per TiB, which makes the byte
ceiling the binding one). Two warmups plus twenty measured attempts at C=1; C=5 only after C=1 completes, because
the retrieval slowdown at five at once has no established cause. Cost per success stays total cost of all attempts
divided by released, receipt-verified answers; refusals count in the numerator only. Either this runs before the
materialization expires (about 2026-10-05) or the fixture is re-loaded first under the same gate, same digest, new
load job recorded on the selection. A passing readback is a necessary condition, not proof that the rows stayed
equal during the campaign; binding the verified content into each attempt's evidence is the runner's job.

### FS-3 — restricted-identity mode

The FS-2 campaign repeated with the separate restricted requester: broker grants, row-policy snapshot and restore,
teardown receipts, the pitfalls already on record for the restricted chain. Its own budget line and its own cells,
labelled as restricted mode, never pooled with same-requester attempts.

### Optional — durable copy of the selected content

A table-copy or snapshot dataset holding the seven tables, created after a verified load, read-only, recorded on
the selection as `durable_copy` with its job. A paid live write under the owner's gate. The digest stays the
version; the copy is a materialization of it. Not required by any slice above.

## Reopen conditions

- A customer or Finance owner selects real cohort data: a new `customer_data` record with its own version, owner
  and acceptance; the synthetic selection stays as the engineering comparison's version, not a stand-in.
- The SDK spike branch holding the pin is rebased or deleted: the vendored copies and digests still identify the
  content; the `fixture_path` pin becomes a historical pointer and says so.
- A live precheck fails: the campaign stops `FACTS_DRIFTED`, nothing is filled, and the selection is not silently
  re-pointed at whatever the dataset now holds.
