# OKF `acme_retail` → BigQuery Graph spike (2026-09-05)

**Question.** Can BigQuery Graph (GA GQL, Enterprise capacity) preserve the useful semantics of Acme's OKF graph and perform
seed-plus-two-hop governed retrieval within an analytical agent's operating envelope, at an honest Enterprise cost?
Plans: intent / spec / plan in `/tmp/okf-spikes/graph/` (vault copies `Ship/rfc/2026-09-05-spike-graph-*.md`).
Joint framing: `JOINT_final.md` (parallel-spike, receipts-gated). **Results: [`evidence/report.md`](./evidence/report.md).**

This is an experimental module, not a production serving-tier commitment. It does not implement or substitute for a
result-bound receipt; the sanctioned SQL it returns is retrieval evidence only (`runtime_verdict = NOT_EXECUTED`).

## What is here

| Path | Purpose |
|---|---|
| `okf_bq_graph/capacity.py` | Task 1 read-only capacity inventory (reservations, assignments, ancestry, IAM, public SKUs) → `evidence/capacity.json` |
| `okf_bq_graph/reservation.py` | Execution-only Enterprise window open/close with cleanup manifest (`evidence/cleanup_manifest.json`) |
| `okf_bq_graph/model.py`, `compile.py` | Deterministic OKF v0.2 → scoped node/edge projection (no LLM, never executes bundle code, strict path resolution, unknown frontmatter preserved) |
| `okf_bq_graph/oracle.py` | Relational/Python reference: governed context, impact (≤6 edges, simple paths), stub backlog; pinned expectations |
| `okf_bq_graph/publish.py` | Immutable publication: append → readback validation (counts, dangling, vector digests) → `READY` → atomic pointer `MERGE`; failure injection before pointer |
| `okf_bq_graph/retrieve.py` | `retrieve / impact / stub_backlog` with engines `gql` (GA `VECTOR_SEARCH` seed + GQL walk), `fallback` (relational joins, on-demand), `oracle`; cache with re-check at disclosure; fail-closed |
| `okf_bq_graph/scale.py` | Synthetic 100 / 1,000 namespace-isolated copies in their own datasets (vectors reused by text digest) |
| `okf_bq_graph/authz.py` | Governance fixtures: RLS dataset (hidden intermediate), metadata-only dataset, authorized views + graph over views; `cases` runs the five second-principal negatives under the existing restricted SA via impersonation (`OKF_SPIKE_RESTRICTED_SA`, no new principal) → `evidence/authz_cases.json` |
| `okf_bq_graph/chain.py` | Connected chain (2026-09-06): fixture seed → pinned publication → governed retrieval returns the Attested Computation declaration + SQL → bind to the SDK receipt example's pinned publication (data files only) → SDK CLI as a subprocess executes and verifies under the caller → consumer releases only on VERIFIED; two fail-closed substitution cases → `evidence/chain/` |
| `okf_bq_graph/benchmark.py`, `run.py`, `lifecycle.py`, `safety.py`, `partial.py`, `bin/safety_teardown.sh` | Bounded runner (20 warmups + 100 measured per cell, nearest-rank percentiles, failures retained), the window orchestrator (signal-safe cleanup lifecycle, job cancel, independent watcher), and the honest aggregation of interrupted cells (INCOMPLETE / NOT_RUN) |
| `okf_bq_graph/cost.py`, `report.py`, `assemble.py` | Slot attribution (exact named reservation vs other pools) and the charged autoscale slot-seconds bill from `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE`; non-mutating report tables; report assembly |
| `sql/*.sql` | `schema.sql`, `graph.sql` (property graph DDL), `seed.sql` (vector seed), `governed.sql` (two-hop GQL), `context.sql`, `impact.sql`, `stubs.sql`, `fallback.sql` |
| `fixtures/bundle_b/` | Negative fixture: identical relative paths, missing targets, duplicate hits, ambiguous replacement, `../` escape |
| `fixtures/cases.json`, `fixtures/scale.json` | Query set and benchmark cell matrix |
| `tests/` | `test_compile.py`, `test_oracle.py`, `test_retrieve.py` (contract runs against oracle by default; `OKF_LIVE_ENGINE=gql|fallback` runs it live) |
| `evidence/` | Raw captures: capacity gate, smoke jobs, projection, publish log, integration/governance JSON, `requests.jsonl`, `summary.json`, `cost.json`, comparison, report |

Source pin: `/Users/haiyuancao/knowledge-catalog/okf/bundles/acme_retail` @ knowledge-catalog `31da799a9aef176df12e91abbd119ea9385b75ec`
(17 markdown files + 2 artifacts; per-file SHA-256 in `evidence/projection_acme.json`). Publication id
`pub_190192147fd7fd78` is derived from the source manifest digest, not from PR 474's observation publication.

## Second principal (2026-09-06)

The 2026-09-05 run recorded every case that needs a second real principal as BLOCKED (IAM principal creation was
denied). No principal was created since: `python3 -m okf_bq_graph.authz cases` impersonates the receipt spike's
existing restricted service account (`OKF_SPIKE_RESTRICTED_SA`, alias `sa:okf-receipt-restricted`; the operator needs
`roles/iam.serviceAccountTokenCreator` on it) and runs five negatives with temporary dataset-reader and row-policy
grants on the `_rls` fixture, removed step by step and read back in `finally` (each teardown step is attempted even
if an earlier one fails; VERIFIED only when all succeed, the grantees exclude the SA and the SA is observed denied).

No negative is graded without a working **allowed control** on the same restricted fixture under the same principal
(an allowed seed returns OK with a computation; the negative's own seed is visible); otherwise the case is BLOCKED.
Result (`evidence/authz_cases.json`, relational fallback engine, on-demand): 5/5 MEASURED — hidden intermediate
ENFORCED, denied bundle DENIED with no identifier in the response or the API error, output denied with the vector
store visible (natural-language seed DENIED under the SA and folded into the verdict), owner-credential fallback
NO_FALLBACK (`jobs.get user_email` bound to the SA for every SA job; the owner arm runs on the ungoverned base dataset,
and the owner on the governed fixture sees no hidden path either), revocation before cached replay FAIL_CLOSED on every
disclosure surface, plus an owner-stored cache entry replayed under the SA is DENIED (the re-check runs under the
caller's credential, not the requester label). A shared-setup failure blocks the unreached cases with the stage and
reason and still finalizes the evidence.

Still BLOCKED: the same cases inside a GQL traversal. GQL needs an Enterprise window, i.e. the spike's bounded window
lifecycle for both the owner and the impersonated client; `--engine gql` is refused before preflight until that is
wired, and the window gate also refuses while a legacy job journal is unreconciled. Under the SA the natural-language
seed is DENIED (the remote embedding model is not usable by that principal), so seed visibility was shown by a plain
row count, not by `VECTOR_SEARCH`. Judges run on the original payloads; the published evidence carries the SA alias
only and masks every identifier of the pinned publication as `<id:sha256[:8]>`. The token is the unsalted SHA-256
prefix of the local id: anyone holding the pinned bundle can recompute it and audit the evidence, so it is
reversible by design for bundle holders and only prevents naming identifiers to readers who do not have the
bundle. It is a publication-hygiene measure, not secrecy.

`evidence/authz_cases.json` is the artifact of the harness at commit `0d07e47`. Later hermetic-only fix passes
(masked log lines, per-policy teardown steps `restore_policy_<table>`, per-observation fields such as
`replay_observation` / `fresh_observation` / `revocation_judgment`, the `NOT_NEEDED` teardown status when no
grant was attempted) change the evidence shape on failure paths only; the recorded measurements are unchanged.
The next live pass regenerates the file in the current shape.

## Connected chain (2026-09-06)

`python3 -m okf_bq_graph.chain --hermetic` (default) or `--live` runs one Acme path end to end and records every stage in
`evidence/chain/chain_<mode>.json`, with the SDK CLI's own per-case diagnostics under `evidence/chain/receipt/`:

1. **Seed — fixture.** `forced:metrics/gross-margin.md`, the harness override (not a semantic ranking). Live Knowledge
   Catalog discovery is out of scope for this chain; nothing here calls a KC endpoint.
2. **Pinned publication.** `pub_190192147fd7fd78`, read from the `active_publication` pointer (live) or the compiled
   projection (hermetic) and checked against the pin.
3. **Governed retrieval.** This spike's `retrieve` reaches `computations/gross-margin-period.md` in one hop and returns the
   Attested Computation declaration (type, runtime, parameters, `file_sha256`, read from the `nodes` table under the same
   client) and its SQL, still `runtime_verdict = NOT_EXECUTED`.
4. **Bind.** The declaration is matched to the SDK receipt example's pinned fixture publication using its data files only
   (`fixtures/publication.json` + the copied Acme bytes): same file SHA-256 (`5e96ae11…`, also the manifest's
   `computation_sha256`), same SQL text, same parameter list, same source pin `31da799`, type `Attested Computation`,
   runtime `bigquery`, FRESH at `as_of`, lifecycle `stable`. Any failed check is `MISMATCH` and nothing executes.
5. **Receipt.** `examples/okf_attested_computation/run.py` at SDK `6719eb5`, invoked as a subprocess (no SDK source edits),
   executes the sanctioned computation under the caller's credential; its independent verifier re-reads `jobs.get` /
   `getQueryResults` and seals a receipt. The verdict is read from the CLI's per-case JSON, never from stdout.
6. **Consume.** The number is released only when the CLI exits 0, both the sealed receipt and the consumer output say
   `VERIFIED` with `execution_match = MATCH`, the receipt's `computation_digest` equals the digest recomputed here from the
   bound bytes (`sha256("okf-receipt:computation-bytes" || 0x00 || bytes)`, the domain constant copied from the SDK's
   `contracts.py` at the pin), and the receipt's publication id / context ref are the bound ones. `UNVERIFIABLE` or
   `REJECTED` anywhere → `REFUSED`, no number.

Fail-closed cases run in the same pass: **`sql-substitution`** (the SDK's fixed case: a product-cost-only formula is
executed for the approved request and 600 is claimed; verifier `REJECTED sql_mismatch`, consumer `REFUSED`, no number) and
**`declaration-mismatch`** (graph-side swap: a different reachable computation, `computations/revenue-ytd.md`, is offered
in place of the bound one; bind `MISMATCH` on file digest, SQL text and path, and the receipt CLI is never invoked). The
CLI has no free-form case, so a "total ARR" swap is not what executes; the executed-SQL swap is the SDK's formula swap.

Labels carried in the evidence: **same requester** (graph leg and receipt leg under the operator's own ADC credential;
`sa:okf-receipt-restricted` is not exercised by this chain); **hermetic** = oracle graph engine + the SDK's SYNTHETIC API
emulation, `same_requester = NOT_APPLICABLE`; **live** = relational `fallback` engine on the published tables (on-demand,
**not** BigQuery Graph; `--engine gql` needs an Enterprise window this module does not open; `--live --engine oracle` is
refused) + SDK `--live` (real BigQuery jobs against the SDK's SYNTHETIC fixture dataset), plus a `jobs.get` check that
**every** job the chain submitted (the pointer lookup, the retrieval and declaration jobs of all three cases, both
receipt jobs) carries one **known** `user_email` (`same_requester = SAME`; any missing identity or unreadable job is
UNKNOWN, never SAME).

Verdict rule (`verdict_rule` in the evidence). Before any case executes, a **provenance gate** requires the pointer to
equal the publication pin, the SDK head to equal `6719eb5` and the whole SDK checkout to be clean (unknown git state
counts as not clean); otherwise no case runs and the verdict is `CHAIN_BROKEN` at `provenance`. In live mode exactly one
query job precedes the gate, the `active_publication` pointer lookup; its job id is recorded and it is part of the
identity set. Each case then carries an
**acceptance** record separate from the fail-closed consumer decision: `MET` only when the case reached its intended
stage and produced its specific evidence — `approved`: reached, bound, CLI exit 0, VERIFIED, RELEASED;
`sql-substitution`: reached, bound, CLI invoked with a fresh diagnostic, exit 2, both verdicts REJECTED, `execution_match`
MISMATCH, reason `sql_mismatch`, not released, REFUSED; `declaration-mismatch`: the alternate computation reached and its
declaration visible, bind MISMATCH with `file_sha256` and `sql_text` among the failed checks, CLI never invoked, REFUSED.
`NOT_REACHED` (an upstream or child failure before the intended stage on any leg, `approved` included: still refused,
but the stage never ran) gives `CHAIN_INCOMPLETE`; `WRONG` (the stage was reached and contradicts the expectation, e.g. a released substitution or a
rejection for a different reason) gives `CHAIN_BROKEN`. `CHAIN_CONNECTED` needs every case `MET` and, live, the identity
check `SAME`. Each receipt launch writes its diagnostic into an invocation-private directory that no other launch can
see, the file must be newer than the launch, and the retained `receipt/case_<case>_<mode>.json` is copied only from that
private artifact (retained copies are cleared at the start of every run), so neither a stale nor an overlapping run's
file can be attributed to the current one.

Hermetic result: `CHAIN_CONNECTED` (`evidence/chain/chain_hermetic.json`; provenance ok, all ten bind checks hold,
`approved` RELEASED `$400.00 USD · VERIFIED` on the synthetic fixture, both substitutions REFUSED, all three acceptances
`MET`). Live result (2026-09-06 21:52Z, one foreground pass, `evidence/chain/chain_live.json`): **CHAIN_CONNECTED** —
provenance ok (pointer = pin, SDK head = pin, checkout clean); relational fallback engine (on-demand, three retrieval jobs
+ one declaration job per case, 2.2 s retrieval) reached the computation in one hop, all ten bind checks hold; SDK
`--live` executed the sanctioned SQL under the operator's credential (receipt job `okf_rcpt_fbec89a0…`, verifier VERIFIED
/ MATCH, access probe ALLOWED, 5.7 s CLI wall) and the consumer RELEASED `$400.00 USD · VERIFIED` on the SDK's synthetic
fixture dataset; `sql-substitution` reached, executed, REJECTED `sql_mismatch` → REFUSED (exit 2, no number);
`declaration-mismatch` reached revenue-ytd, MISMATCH on file digest, parameters, path and SQL text → REFUSED, CLI never
invoked; all three acceptances `MET`; `same_requester = SAME` over 14 jobs (12 graph jobs + 2 receipt jobs, one known
`user_email`, masked as `operator`). The whole pass took 23 s. The earlier 21:35Z pass (commit `cef88d7`) reached the same
decisions under the pre-acceptance verdict rule and a three-job identity sample; it was re-run so the committed artifact is
the output of the rule it claims. The retained live artifact is the output of runner `chain/0.2.0` at `a615a7c`: its
identity set is the 14 case jobs and does not include the pointer-lookup job, which the current runner (`chain/0.3.0`)
adds; the later changes (invocation-private diagnostics, `approved` outage labelled NOT_REACHED) alter no recorded field
of a passing run, so it was not re-run.

## Graph model (spec §3)

Node kinds `Concept | Section | Source | Actor | Artifact | LogEntry`; stubs are `Concept{stub=true}`. Relations
`LINKS_TO, HAS_SECTION, NEXT, CITES, MENTIONS, DERIVES_FROM, RESOLVES_TO, GENERATED_BY, VERIFIED_BY, EXECUTED_BY, ATTESTED_BY, REFERENCES`.
`node_id = bundle|publication|kind|local`; `edge_id = bundle|publication|relation|sha256(endpoints, declaration, ordinal)`.
One property graph `okf_graph` with uniform `Node`/`Edge` labels; every query carries `publication_id` predicates.
Acme compiles to 44 nodes / 109 edges / 22 sections, 0 stubs; `bundle_b` to 17 / 28 / 6 with 3 stubs.

## Setup (a prepared environment is assumed by the commands below)

```bash
cd rfc/spikes/bq-graph
python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
gcloud auth login && gcloud auth application-default login && gcloud config set project test-project-0728-467323
export OKF_ACME_ROOT=/path/to/knowledge-catalog/okf/bundles/acme_retail     # pinned at commit 31da799 (tests skip if absent)
export OKF_OPERATOR_EMAIL=$(gcloud config get-value account)                # used for job filtering and policy grants; never committed
# one-time: dataset + remote embedding model (needs an existing BigQuery→Vertex connection with roles/aiplatform.user)
bq mk --dataset --location=US --default_table_expiration=1209600 okf_graph_spike_20260905
bq query --use_legacy_sql=false "CREATE MODEL IF NOT EXISTS okf_graph_spike_20260905.text_embedding REMOTE WITH CONNECTION \`test-project-0728-467323.us.bq-llm\` OPTIONS (ENDPOINT='text-embedding-005')"
```

## Run

```bash
env -u OKF_LIVE_ENGINE python3 -m pytest tests -q             # oracle engine + offline regressions
python3 -m okf_bq_graph.capacity US us-central1 EU           # read-only inventory
python3 -m okf_bq_graph.compile <bundle_root> evidence/projection_acme.json
python3 -m okf_bq_graph.publish <bundle_root>                # on-demand: tables, vectors, graph DDL, pointer
OKF_LIVE_ENGINE=fallback python3 -m pytest tests/test_retrieve.py -q   # live, on-demand
python3 -m okf_bq_graph.chain --hermetic                  # connected chain, no cloud (oracle graph + SDK emulation)
python3 -m okf_bq_graph.chain --live                      # connected chain, on-demand fallback engine + SDK --live
python3 -m okf_bq_graph.run integration --minutes 25         # opens the Enterprise window, runs GQL cases, closes it
python3 -m okf_bq_graph.run benchmark --minutes 85           # benchmark cells from fixtures/scale.json
python3 -m okf_bq_graph.run all --minutes 85                 # both in one window
python3 -m okf_bq_graph.cost 2026-09-05T23:40:00Z 2026-09-06T00:35:00Z   # reconcile jobs + charged reservation timeline
python3 -m okf_bq_graph.partial && python3 -m okf_bq_graph.assemble      # honest cell summary + report.md
```

The `run` modes create a paid reservation; `bin/safety_teardown.sh` is spawned automatically as an independent watcher.

Benchmark requests and summaries carry a `run_id`; `partial` refreshes unfinished cells from matching raw records and
keeps repeated cell names in separate runs. The retained 48 historical requests have no run ID and remain unchanged;
their summaries use `legacy-unlabeled`. Duplicate request IDs within a cell/run stop recovery before writing, since their
run boundaries cannot be inferred safely. Completed driver summaries remain unchanged. All nine corpus/concurrency
combinations appear, including zero-sample `NOT_RUN_BUDGET` rows with known targets and null percentiles. Recovery does
not turn an interrupted run into `COMPLETE`, even if its retained attempt count reaches the target.

Everything cloud-side lives in `okf_graph_spike_20260905{,_x100,_x1000,_rls,_meta,_av}` (US, 14-day default expiration)
and in the temporary reservation `okf-graph-spike-20260905` (Enterprise, 0 baseline, autoscale ≤100, no idle borrowing),
which is created only inside a measured window and deleted at its end (`evidence/cleanup_manifest.json`).

Deadline cleanup uses one admission gate for all driver query/load clients. Jobs have explicit window IDs journaled in
`evidence/jobs_<window>.json` before submission. Query results use a job-local SDK client: both API entry and actual HTTP
dispatch enforce the remaining deadline, disable SDK retries, and cap RPC timeouts at one second. Every lazy page and
buffered row checks stop/deadline; late responses are discarded. The private SDK adapter is tested with real
Client/QueryJob/RowIterator objects and pins BigQuery **3.45.0**; revalidate it before changing that dependency.

Interrupt handlers only stop admission and unwind. The driver's watchdog starts capacity deletion on stop/deadline
independently of result I/O, executor joins and cancellation. The offline blocked-page regression requires deletion
to start within 0.5 seconds of the deadline while the HTTP call is still blocked. This is a local scheduling assertion,
not a measured cloud deletion SLA: individual `bq` commands still have their own 30-second limits. Workers are joined
before driver completion. The detached watcher closes capacity first, then reconciles jobs and records diagnostics in
`evidence/watcher_<window>.jsonl`. Open/close operations share a process-safe manifest lock; verified original capacity
receipts remain valid when the reservation name is reused.

Capacity deletion and job cleanup have separate receipts. Both preflight and `open_window` require a verified
`evidence/jobs_<window>.cleanup.json` matching the complete journal inventory before opening another window. Failed,
missing, stale or malformed job receipts block admission even when capacity is `CLOSED_VERIFIED`. The watcher retries
job reconciliation without rewriting the driver journal or the valid capacity receipt. Legacy windows with no job
journal remain blocked until their job inventory is explicitly reconciled; historical capacity receipts alone do not
prove this. No legacy receipt was upgraded and no cloud workload was run in fix pass 3.

The fallback walk requires visible node rows from the pinned publication at each endpoint before extending either hop.
Offline execution of the shipped SQL covers a hidden intermediate with both edges still visible and an intermediate
from another publication. This repairs the conditional authorization defect; fallback governance remains unmeasured
live and existing G6/G7 uncertainty labels remain unchanged.

A new measurement run preserves previous run summaries and requires a fresh `run_id`; raw attempts retain that ID.
Run `partial` to recover interrupted cells. It refreshes incomplete rows without merging separate runs or promoting
recovered partial evidence to a completed driver measurement.
