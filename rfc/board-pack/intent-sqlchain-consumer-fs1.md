# Intent — a hermetic sampled request-to-consumer runner (FS-1, offline)

Status: an implementation slice, offline only. It builds the driver that the fact-data selection made specifiable
(`plan-sqlchain-fact-select.md`, slice FS-1) in its dry-run and hermetic modes, and nothing else. It runs nothing
live, spends nothing, measures no live cell and moves no threshold out of PROPOSED. Companions:
`spec-sqlchain-consumer-fs1.md` (the driver's contract, record and gates) and `plan-sqlchain-consumer-fs1.md`
(what FS-2 needs from it and the budget it declares without spending).

Source: the 2026-09-09 fact-data consult recommended, and the owner accepted, that the next slice after selecting the
synthetic fixture digest is a C=1 hermetic sampled runner first, then live sampling under the owner's paid gate. The
selection record already carries a `live_precheck` contract, a validity window and an expiry that "become driver
behaviour" in this slice.

## Problem

The ordinary-SQL comparison has two request-to-consumer cells (`sqlchain_forced_c1`, `sqlchain_forced_c5`) that have
read `INCOMPLETE / NOT_IMPLEMENTED` since the September 19 pack was scaffolded. Every current surface says the full
path from question to released number "has no runner". The connected chain (`okf_bq_graph.chain`) runs each of its
cases once and reports one wall time for the pass; the retrieval sampler (`okf_bq_graph.benchmark`) stops at
retrieval. Neither repeats one requester question through retrieval, binding, the caller-delegated job, independent
verification and the consumer decision, and neither retains a distribution of attempts for that path.

Building the live sampler directly would put the first exercise of the precheck, the expiry refusal, the bind
refusal and the per-attempt record on a paid campaign against tables that expire about 2026-10-05. The orchestration
and the refusals can be proven offline first, against the oracle engine and the SDK example's hermetic runner, so
that the live slice only adds what cannot be proven offline: the readback, the job and the bytes.

## What this slice builds, and what it does not

It builds `okf_bq_graph.consumer_run` with two modes. **Dry-run** prints the campaign (cells, the predeclared
question, the refusal probe, the gates and the declared-but-unspent budget) and opens nothing. **Hermetic** runs the
campaign with the in-process oracle engine on the graph leg and the SDK example's hermetic runner on the receipt
leg, and retains every attempt: retrieval time, bind outcome, the emulated job's identity and times, the verifier's
verdict, the consumer's decision, the SDK subprocess's own elapsed time, the selected content digest and the
evaluation date. The driver refuses unless `facts.state` is `SELECTED`, refuses an evaluation date outside the
selection's validity window, refuses a live admission after the recorded expiry, and stops `FACTS_DRIFTED` when a
readback manifest does not hash to the selected content digest. The last two are exercised offline against the
vendored manifest and mutated copies of it, because no live read exists in this slice.

The hermetic receipt leg returns the planned `400`; it does not compute it from the seven tables. So the runner also
carries a separate row-based oracle check: a bounded re-implementation of the sanctioned SQL's semantics over the
vendored content manifest, which must reproduce the expected January result (and the January–February result, which
a single-amount mutation changes while the January result does not) before any attempt runs. A passing hermetic
campaign therefore establishes **orchestration and refusal behaviour**: the stages run in order, every attempt is
retained, the predeclared refusal refuses at the stage it was declared to refuse at, and the gates fire. It does not
establish data equivalence, GoogleSQL execution, a job identity, a latency or a cost.

It does not build a live mode. There is no `--live` flag; the consumer cells stay `INCOMPLETE` and their reason
changes from `NOT_IMPLEMENTED` to `RUNNER_HERMETIC_ONLY`, which is still a refusal. A hermetic attempt never fills a
live cell and no hermetic number is printed on the baseline card as a measurement. It declares a consumer sampling
budget block inside the existing ceilings and does not spend it.

## Why it is worth doing on its own

The live slice is a paid campaign with an expiring materialization. Every gate it depends on — SELECTED only, the
validity window, the expiry, the precheck, the bind refusal for a computation the receipt publication does not
carry, the per-attempt record with refusals retained — is deterministic and can be proven offline. Doing that first
means the live slice's review is about the readback, the job identity and the bytes, not about whether the loop runs.
It also makes the two consumer cells' honesty exact: the blocker is now "no live mode", not "no runner".

## Out of scope

Live BigQuery reads, jobs or reloads; the readback itself; the restricted-identity mode (FS-3); any change to the SDK
or to the retained chain records; any change to the receipt fixture's SQL; any consumer-cell measurement; any cost
measurement; any threshold accepted; any change to the retrieval cells or their campaign records.
