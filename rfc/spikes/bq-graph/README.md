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
| `okf_bq_graph/job_audit.py` | Reconciles a retained live chain record's job inventory against the platform's own `jobs.list`/`jobs.get` for that record's window (read-only; no query, no grant change). A requester job in the window the record never claimed, or an administrative statement the record admits it could not name, is `INCOMPLETE`; a listing that stopped with pages left is `INDETERMINATE`; another identity's job is reported, not condemned → `evidence/chain/job_audit_chain_live_restricted.json` |
| `okf_bq_graph/principal.py` | Requester brokers for the chain (2026-09-06 Slice A): a hermetic policy-emulating broker (no IAM, no job) exercised by `chain.py --requester restricted`, and the IAM-impersonation broker for the restricted SA (graph leg via `authz.impersonated_client`, SDK subprocess via an `impersonated_service_account` ADC file plus a `userinfo.email` scope shim, `_rls` row-policy grantee snapshot/restore, dry-run authorization probe per dependency table) exercised live in Slice B → `evidence/chain/chain_hermetic_restricted.json`, `evidence/chain/chain_live_restricted.json` |
| `okf_bq_graph/benchmark.py`, `run.py`, `lifecycle.py`, `safety.py`, `partial.py`, `bin/safety_teardown.sh` | Bounded runner (20 warmups + 100 measured per cell, nearest-rank percentiles, failures retained), the window orchestrator (signal-safe cleanup lifecycle, job cancel, independent watcher), and the honest aggregation of interrupted cells (INCOMPLETE / NOT_RUN) |
| `okf_bq_graph/sql_baseline.py` | Predeclared ordinary-SQL baseline for the 2026-09-19 checkpoint (Slice A, 2026-09-07): validates `fixtures/sql_baseline.json`, reads the recorded prior SQL observations out of the retained evidence, projects the declared samples against the declared budget, and writes a card whose every cell is empty. It opens no client and spends nothing; its own gate refuses a card in which a cell acquired a number or a prior observation claimed to fill one → `evidence/sql-baseline/{plan.json,baseline.md}` |
| `okf_bq_graph/sql_baseline_run.py` | Driver for the four predeclared retrieval cells (Slice B Pass 1, 2026-09-08, hermetic): reads the sql-baseline plan rather than `fixtures/scale.json`, builds one `benchmark.measure` cell per retrieval cell with **only that cell's shape** as its query list, engine `fallback`, both caches off, on-demand with no reservation window (`cell_seconds` + a `TOTAL_TIME_BUDGET` deadline only), and a fresh `sqlbase-*` run_id checked against the retained GQL summary before any client exists. `--dry-run` prints cells / queries / budget and constructs no client; `--live` (Pass 2) runs foreground and retains `evidence/sql-baseline/run_<run_id>.json`. Consumer cells (`sqlchain_*`) are refused with `FACTS_UNSELECTED + NOT_IMPLEMENTED`. **No cell has been run.** |
| `okf_bq_graph/cost.py`, `report.py`, `assemble.py` | Slot attribution (exact named reservation vs other pools) and the charged autoscale slot-seconds bill from `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE`; non-mutating report tables; report assembly |
| `sql/*.sql` | `schema.sql`, `graph.sql` (property graph DDL), `seed.sql` (vector seed), `governed.sql` (two-hop GQL), `context.sql`, `impact.sql`, `stubs.sql`, `fallback.sql` |
| `fixtures/bundle_b/` | Negative fixture: identical relative paths, missing targets, duplicate hits, ambiguous replacement, `../` escape |
| `fixtures/cases.json`, `fixtures/scale.json` | Query set and benchmark cell matrix |
| `okf_bq_graph/catalog.py`, `seed.py`, `publication.py`, `journal.py`, `catalog_lifecycle.py` | Catalog-seeded chain (2026-09-06): Dataplex list/get reader + trusted-config parser, exact `ConceptSeed`, retained-publication resolution + trusted-source compilation + payload consistency guard, run-owned job journal, isolated relational-only lifecycle driver for the owned republish experiment |
| `okf_bq_graph/catalog_live.py` | Slice B2 live glue (2026-09-07): the `CloudOps` adapter against real BigQuery + Dataplex (bounded, no client retries, typed create-attempt outcomes), `BudgetedCloud` (the phase deadline bounds the operations, not just the gaps between cases), the job-identity audit over the exact submitted job set, and the owned-lifecycle experiment driver that runs the Catalog-seeded chain against run-owned resources and grades every case MET / WRONG / NOT_REACHED / BLOCKED → `evidence/catalog-chain/<run_id>/` |
| `tests/` | `test_compile.py`, `test_oracle.py`, `test_retrieve.py` (contract runs against oracle by default; `OKF_LIVE_ENGINE=gql|fallback` runs it live); `test_catalog.py`, `test_catalog_publication.py`, `test_catalog_lifecycle.py`, `test_catalog_live.py` + the catalog cases in `test_chain.py` (all hermetic, injected Catalog responses / fake cloud) |
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
`evidence/chain/chain_<mode>.json`, with the SDK CLI's own per-case diagnostics under `evidence/chain/receipt/<run_id>/`
(the live artifacts from runner `chain/0.2.0` sit directly under `receipt/`, the layout of that runner version):

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

Labels carried in the evidence (this section is the operator-requester chain, `--requester operator`, the default; the
restricted requester has its own record and its own labels below): **same requester** (graph leg and receipt leg under
the operator's own ADC credential; `sa:okf-receipt-restricted` is not exercised by this chain); **hermetic** = oracle graph engine + the SDK's SYNTHETIC API
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
check `SAME`. Every run owns `receipt/<run_id>/`: each receipt launch writes its diagnostic into an invocation-private
directory inside it that no other launch can see, the file must be newer than the launch, and it is moved (never copied
over a shared name) to `receipt/<run_id>/case_<case>_<mode>.json`. Each receipt record carries the diagnostic's
`request_id` and SHA-256, the chain record carries its `run_id`, `chain_<mode>.json` is written atomically and also
retained inside the run directory, and no run deletes anything outside its own directory. Two successful overlapping
runs therefore keep and reference only their own evidence (regression: a full chain completes inside another chain's
substitution launch; every reference reconciles by request id and digest).

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
adds; the later changes (invocation-private and run-owned diagnostics, `approved` outage labelled NOT_REACHED) alter no
recorded field of a passing run, so it was not re-run.

### Restricted requester (2026-09-06 Slice A hermetic; 2026-09-07 Slice B live)

`python3 -m okf_bq_graph.chain --hermetic --requester restricted` runs both legs through a requester broker for
`sa:okf-receipt-restricted` (`okf_bq_graph/principal.py`) instead of the operator: `requester.mode = restricted-sa`, the
record is `evidence/chain/chain_hermetic_restricted.json` (runner `chain/0.5.0`), and the three original cases are replaced
by four cases with the same stage-reachability acceptance (`MET` / `NOT_REACHED` / `WRONG`; a refusal alone never counts):

* **`approved-restricted`** (grants present): reached, bound, authorized, executed, VERIFIED, `RELEASED`.
* **`denied-intermediate`** (the `_rls` shape: the row policy hides `metrics/gross-margin`; seed
  `forced:metrics/gross-margin-legacy.md`, whose only path to the computation runs through it): retrieval `OK` with the
  seed concept visible, no path, no computation, the hidden id absent from the full retrieval result and from every
  surface the requester received (retrieval, declaration, bind, authorization, receipt, consumer; the harness's own
  policy record in the same case object names the id by design); bind `NOT_REACHED` with reason `retrieval_denied`; CLI
  never invoked; `REFUSED`. A traversed hidden
  row, a leaked id or an invoked CLI is `WRONG`; a seed that is not visible is `NOT_REACHED` (enforcement cannot be told
  from an outage).
* **`unauthorized-output`** (seed and declaration visible, no read on the SDK fixture's dependency tables): reached and
  bound, then a new **pre-execution authorization** stage probes every dependency table of the bound publication under the
  requester's own credential (hermetic: the broker's policy; live: a dry-run `SELECT` per table, the SDK's own
  `probe_sources` shape) and returns `DENIED`; CLI never invoked; `REFUSED` naming the denial. `ALLOWED` here is `WRONG`,
  a probe that produced no platform decision is `NOT_REACHED`.
* **`revocation-before-replay`**: the first pass runs the full path and is `RELEASED` (cache `MISS_STORED`); the broker
  then revokes the requester's dataset grant and its SDK-table read; the same request is replayed from the case-private
  cache and is `HIT_DENIED` with nothing disclosed (the oracle engine now carries the BigQuery engines'
  `_cache_dependencies` / `_recheck` contract: the entry records every node and edge the answer depends on, the walk
  hops, the Computation section and its `HAS_SECTION` edge, the `VERIFIED_BY` actors, the `DERIVES_FROM` sources and
  their `RESOLVES_TO` targets, the `LINKS_TO` context, and a hit is served only after the graph re-confirms all of them
  by scoped id, so an edge-only revocation with every node untouched, a hidden Computation section or a revoked
  verification is `HIT_DENIED` too; an answer whose dependencies cannot be established is never cached
  (`BYPASS_INCOMPLETE_DEPENDENCIES`), a legacy dependency version is rerun, an unpinned publication is never cached);
  the authorization probe is `DENIED`; the consumer re-decides the stored receipt and `REFUSED`; the CLI was invoked exactly
  once. A released replay, a replay served after revocation, an `ALLOWED` probe or a second CLI launch is `WRONG`; a
  first pass that never released or a replay that was not a cache hit is `NOT_REACHED`.

The consumer now takes the authorization probe as an input and refuses anything but `ALLOWED` at decision time, so a
receipt sealed before a revocation cannot be replayed into a release. Each retained diagnostic is named after the chain
case (`case_<chain-case>_<mode>.json`), since two chain cases run the SDK's `approved`.

What the hermetic record is and is not. The broker is a policy emulation over the compiled projection: the principal is a
label, no IAM call and no BigQuery job happen, `identity = NOT_APPLICABLE`, and nothing in it is platform enforcement. It
proves that the harness reaches each stage, refuses for the stated reason and grades itself honestly (regressions: a
broker that ignores hidden rows makes `denied-intermediate` `WRONG` and the chain `CHAIN_BROKEN`; one that claims a
revocation it did not apply makes the replay `RELEASED` and `WRONG`; a grant that never takes effect leaves
`approved-restricted` `NOT_REACHED` and the chain `CHAIN_INCOMPLETE`). Hermetic result: **`CHAIN_CONNECTED`**, all four
acceptances `MET`, no e-mail in the record.

#### Live restricted pass (Slice B, 2026-09-07)

`python3 -m okf_bq_graph.chain --live --requester restricted` (runner `chain/0.8.0`, record
`evidence/chain/chain_live_restricted.json`, run directory
`evidence/chain/receipt/online_restricted-20260907T224831Z-f32d6d1b`). Result: **`CHAIN_CONNECTED`**, all four acceptances
`MET`, `identity = BOUND`, `teardown = VERIFIED`, no e-mail in the record. The execution legs ran under
`sa:okf-receipt-restricted`, not the operator: the operator's credential only granted, revoked, restored and read job
identities. Every number below is read off that record; dependency-denial counts and propagation waits differ between
runs, so a summary carried over from an earlier run describes nothing.

* **Identity.** The operator's `jobs.get` over **all 29 jobs the run submitted**, each checked against the principal of
  the role that submitted it: **20 under the requester** (17 graph-leg jobs, including the pointer lookup and the
  cached-replay re-check; 2 receipt-leg jobs; 1 broker row-policy observation) and **9 under the operator** (the
  grant/drop/restore row-policy DDL, administrative work rather than execution). No third identity appears. A required
  role with nothing to compare, an unreadable job, a missing identity or an unknown expected principal is `UNKNOWN`
  (`CHAIN_INCOMPLETE`); an unexpected identity is `UNBOUND` (`CHAIN_BROKEN`).
* **The record cannot audit itself.** An inventory is a claim about the run's own bookkeeping: a job it failed to retain
  is invisible to it by construction. `python3 -m okf_bq_graph.job_audit evidence/chain/chain_live_restricted.json`
  reads `jobs.list`/`jobs.get` for the record's own window under the operator — no query submitted, no grant changed —
  and compares. Retained as `evidence/chain/job_audit_chain_live_restricted.json`: **`RECONCILED`**, 30 jobs listed in
  the window and the listing drained (`truncated: false`), all 29 inventory jobs matched, **0 requester jobs unaccounted
  for**, 0 inventory jobs the platform did not list, and the record declares no administrative statement it could not
  name. The one extra is an unrelated scheduled query under a third identity: reported, not condemned, because the
  project is shared and the run's claim is about the requester. A listing that stops with pages left is
  `INDETERMINATE`, never a pass: matching an inventory against a prefix of the window proves nothing about the rest of
  it, and `max_results` caps the whole iterator rather than the page, so paging is sized with `page_size` and the
  iterator is drained.
* **Graph leg.** `authz.impersonated_client` (IAM `generateAccessToken`).
* **Receipt leg.** The SDK example as a subprocess under an `impersonated_service_account` ADC file, run.py unedited.
  The SDK establishes its requester from `oauth2/tokeninfo`, which returns no e-mail for a token minted for
  `cloud-platform` alone, and google-auth ignores an impersonated ADC file's own `scopes` when the caller passes them
  explicitly (2.49.2, `from_impersonated_service_account_info`: `scopes = scopes or info.get("scopes")`). The broker
  therefore writes a `usercustomize.py` beside the ADC file and puts its directory on the subprocess's `PYTHONPATH`; it
  adds the `userinfo.email` scope the operator's own gcloud ADC already carries, and nothing else. It is deliberately
  **not** `sitecustomize.py`, which would shadow the interpreter's own and leave `sys.path` incomplete. The shim changes
  the credential's scope, never its identity: tokeninfo reports the SA, and every receipt job carries it. Both artifacts
  live in the private 0700 directory teardown removes.
* **Grants.** Dataset-level reader entries through `authz.set_dataset_reader`, only where the SA holds no entry (a
  pre-existing READER, WRITER or OWNER is left as it is, never downgraded), each waited for by probing under the SA,
  with the bound SDK publication's dependency tables known before the first probe. `denied-intermediate` also needs the
  SA in the `_rls` fixture's three hidden-intermediate row access policies: under BigQuery RLS a non-grantee reads zero
  rows even with dataset READER, which is an outage, not enforcement. The broker snapshots those policies' grantees and
  predicates, adds the SA only while a case runs on `_rls`, drops it again when a case leaves, and refuses to touch a
  fixture it could not restore. It observes the effect with a real row-count query under the SA, not a dry run (a dry
  run passes on dataset READER alone): the run recorded **40 rows visible, 0 of them the hidden intermediate**. Because
  `authz.set_rls` replaces a policy by name and BigQuery has no other replace semantics, the broker also refuses a
  fixture whose policies carry unexpected ids: replacing them by the fixture's names would add policies beside them and
  leave a table it could not restore.
* **Teardown.** Every touched dataset's ACL restored to the snapshot taken before the broker's first mutation and read
  back; the `_rls` grantee lists and predicates restored and read back (`sa_in_grantees_after: false`); the credential
  directory removed. `VERIFIED` only with at least one step and every read-back equal to its snapshot.
* **Administrative statements are accounted for attempt by attempt.** `authz.set_rls` attempts all three policy
  statements and only then raises if any failed, so a caller that retains job references from its return value loses the
  whole batch — the statements that succeeded, and the one whose job was submitted before its result failed — the moment
  one of them fails. References are therefore kept at submission, through `publish.run`'s `on_job` hook, and each
  statement is settled `DONE`/`FAILED` individually. The hook opens its record **before the request leaves**
  (`DISPATCHING`), so an attempt whose submission was accepted but whose response never came back keeps its own entry
  with no id (`UNRESOLVED`) instead of disappearing behind the previous attempt: a failed statement reports the id of
  *its own* last attempt, or none, and never borrows the id of the attempt before it. Such an attempt is not re-issued
  either — the request may have been accepted, and retrying it would create a second policy job nobody is watching.
* **The SDK's own job retry is disabled for anything this spike accounts for.** At the pinned `google-cloud-bigquery`
  3.45.0, a retryable terminal failure makes `QueryJob.result()` submit a **new** job and repoint the object at it
  (measured in `tests/test_sdk_job_retry.py` against the real client: two jobs exist, `job.job_id` changes). A hook that
  fired at submission would then hold the id of a job that failed, mark it `DONE` because the helper returned success,
  and never learn the id of the job that actually ran. `publish.run` therefore passes `job_retry=None` whenever a caller
  is tracking, and retries itself — one accounted attempt at a time, each with its own submission and outcome events, so
  a retried statement puts **both** jobs in the inventory with their own states. An untracked caller keeps the SDK's
  default behaviour.
* **What the run cannot account for blocks the claim.** An attempt that never named a job, an attempt that never
  reached a terminal state, and a job that appears without the submission hook seeing it are all `UNRESOLVED` — the
  last means something submitted jobs behind the broker, so earlier attempts may be missing too. Any of them makes the
  identity `UNKNOWN`, the chain `CHAIN_INCOMPLETE`, and the reconciliation refuse to certify the record. That matters
  because an unnamed job of the run's own would otherwise be indistinguishable from the unrelated operator work the
  audit is entitled to ignore. The record publishes the broker's own judgement of this rather than recomputing it, so a
  narrower copy of the rule cannot quietly drop a category on the way to the audit.
* **The retained run predates those fixes and is measurably unaffected by them.** It was produced by runner
  `chain/0.8.0`; the current runner is `chain/0.11.0`. All nine of its policy statements succeeded — the record lists
  nine `policy_admin` jobs and its teardown is `VERIFIED` with both `restore_rls_policies` and `readback_rls_policies`
  `ok` — so no batch of its partially failed. Nor was any job substituted underneath it: its reconciliation lists
  exactly **nine operator jobs in the window, all nine of them claimed**, and the only unaccounted job is an unrelated
  scheduled query under a third identity. A hidden retry would have left a tenth operator job in that window with
  nothing claiming it. That is a measurement, not an assumption, which is why the run is left exactly as it is rather
  than re-run.
* **The superseded first pass is kept, not rewritten.** `online_restricted-20260907T221038Z-900abfcd` is the run Astra
  reviewed at `11ae4c9` under runner `chain/0.7.0`. Its own measurements stand (it refused `unauthorized-output` with
  5/7 dependencies denied and observed the revocation at 0 s/1 s), but its identity gate checked 18 jobs while the run
  had submitted 29, and its denied replay re-check was dropped before it could be counted. It is retained as history;
  the shared `chain_live_restricted.json` and every claim above are the `224831Z` run.
* **The four cases, as this record measured them.** `approved-restricted`: 7/7 dependencies `ALLOWED`, receipt
  `VERIFIED`, `RELEASED`. `denied-intermediate`: seed visible, no path, no computation, no hidden id, CLI never invoked,
  `REFUSED`. `unauthorized-output`: `BOUND`, then 7/7 dependency probes `DENIED` under the requester's own credential,
  CLI never invoked, `REFUSED` before execution. `revocation-before-replay`: `RELEASED` once (`MISS_STORED`), revocation
  observed by the requester (graph 92 s, SDK 2 s — a poll interval, not a propagation bound), replay `HIT_DENIED`
  disclosing nothing with its denied re-check job retained, 7/7 replay probes `DENIED`, `REFUSED`, CLI invoked exactly
  once. A refusal needs only one denied dependency, since the computation requires them all: an earlier run refused the
  same two cases with 5/7 and 2/7 denied while the ACL change was still propagating.

What this pass does not claim: the SDK still runs against its own SYNTHETIC fixture dataset, the graph engine is the
relational `fallback` (not BigQuery Graph / GQL), the seed is the forced fixture seed, and the receipt is verified by
the SDK's own verifier, not by an independent attester.

## Catalog-seeded chain (2026-09-06, Slice A hermetic; runner `chain/0.6.0` after the PR 40 merge)

`python3 -m okf_bq_graph.chain --seed-mode catalog` replaces the fixture seed with a **fresh Dataplex Catalog read**: paginated
`entries.list` on the configured entry group selects the configured entry by exact name (no other entry body is fetched), then
`entries.get(view=ALL)` returns the `okf-context-runtime` aspect with its values (the default FULL view can expose only keys for
optional aspects). Authored `okf` / `overview` aspects are recorded as present and never used as runtime input. Modules:
`okf_bq_graph/catalog.py` (reader + parser + trusted `CatalogConfig` allowlist), `seed.py` (`ConceptSeed`, an exact scoped
Concept id that is never wrapped in `forced:`), `publication.py` (retained store, exact pin resolution, trusted source,
payload guard), `journal.py` (run-owned job journal + raw retention), `catalog_lifecycle.py` (Slice B2 driver, hermetically
tested only).

The returned pin is **validated, then frozen**: every field typed and non-empty, `runtime_contract` in the supported set,
project / dataset / location / bundle / source repository+root / managed profile+deployment / compiler version equal to trusted
configuration (Catalog values can never widen the allowlist or name a SQL destination), `pub_<16 hex>` / 40-hex source pin /
64-hex digests, a safe bundle-relative `concept_path`, and `concept_id` exactly `bundle|publication|Concept|path` (case-sensitive).
Refusals are typed (`CATALOG_ERROR` for 403/404/429/timeout/non-JSON, `PAGE_CAP`, `ENTRY_NOT_FOUND`, `ENTRY_AMBIGUOUS`,
`ENTRY_MISMATCH`, `ASPECT_MISSING`, `ASPECT_KEYS_ONLY`, `INVALID_PIN`, `UNSUPPORTED_CONTRACT`, `SCOPE_REFUSED`) and end the run at
`broken_at = seed` with no store read, no retrieval, no SDK call and no fixture / head / vector / saved-JSON fallback. A live
invocation configured with a mock or saved-response reader is `READER_REFUSED`; a hermetic invocation with the HTTP reader
likewise.

The pin is then resolved with **parameterised reads against the configured dataset only**: exactly one retained `publications`
row (must be `READY`) plus exactly one visible seed node row whose path and `file_sha256` equal the pin; the retained row's
source pin, source manifest and compiler version must equal the pin (`PIN_MISMATCH` otherwise); missing / non-READY / duplicate
publication or absent seed is `FAIL_STALE`; a transport or IAM failure is `ERROR` (blocked, never a pass). The current head
(`active_publication`) is read for observation only and is never followed: a P1 pin is served exactly while the head is P2.
The exact clean pinned source is then compiled as the **trusted projection** (`trusted_source`: git HEAD == pin, bundle tree
clean, bundle path == `source_root`, compiled publication id / manifest / seed digest == pin; anything unknown is
`SOURCE_UNVERIFIED` and refuses). The provenance gate adds `source_verified` to the SDK head/clean checks.

Each case then runs governed retrieval with the exact Concept id and, before binding, a **payload consistency guard**
(`verify_payload`): the full retained node and edge rows for the publication (excluding only the storage-derived
`stale_after_ts`) must equal the trusted rows, the node/edge manifests are recomputed from the retained rows and compared
to the publication's digests, every retained Section text is re-hashed, the result's scope, seed concept fields, every path's
scoped endpoints and LINKS_TO continuity, the computation's section membership, its SQL bytes and recomputed `sql_sha256`, and
the declaration's node id / file digest (also against the source manifest) / type / runtime / lifecycle / `stale_after` /
parameters are all checked against the trusted projection. The separately selected computation object is re-verified byte
for byte. The **disclosed `paths` list itself** is validated (scoped endpoints, LINKS_TO continuity, hop count, exact match
with the computations' vias) and the **governance fields the caller consumes** — trust tier, verifications, provenance,
freshness as the whole `{verdict, stale_after}` record at `scope.as_of`, deprecated-seed replacement, for the seed and each
computation — are recomputed from the trusted VERIFIED_BY / DERIVES_FROM / RESOLVES_TO / LINKS_TO edges. The chain passes
the engine it **configured and ran** into the guard; the result's own `scope.engine` label must equal it (`engine` check)
and the provenance shape is selected from that trusted engine, never from the returned label — a valid fallback-shaped
provenance under a `fallback` label coming out of an oracle run fails on both counts (Astra re-review 3, R1). Provenance is
checked against the **complete item shape of that engine**: the oracle emits exactly
`resource, title, declaration, declared, intrinsic, resolves_to`; the relational engines emit exactly
`resource, title, declaration, resolution, source_id, note` (the note verbatim, `model.PROVENANCE_NOTE`). Every required key
must be present, no other key may be present, and every value must equal the trusted one; an unknown engine has no shape
and fails (Astra PR 41 P1, re-review R1 and re-review 2: computation-derived checks are not the returned payload, a reduced
field subset is not the field, and a missing key is not an empty value). The governed input itself is retained per case
under `retrieval/retrieval_<case>.json` with its SHA-256, not only the re-read rows. `INCONSISTENT` leaves the case `NOT_BOUND`, never invokes the SDK, and grades `WRONG` (a reached stage that
contradicts the pinned publication is not an outage); `ERROR` is `NOT_REACHED`. Regressions cover: a P2 endpoint or a
non-existent edge mixed into a P1 path, a section's text changed under its old hash and P1 labels, SQL changed after preflight
under the old digest label, a declaration changed after preflight, a P2 result relabelled as P1, and a run with the guard
bypassed (which releases a corrupted non-computation section that the SDK bind cannot see).

`bind` now takes the verified source revision from the validated pin and requires the SDK fixture manifest's `derived_from`
to end with the full 40-hex revision; the check's note records that this lineage label is free text at the pinned SDK commit,
not a Git attestation. The chain record names `graph_publication` (bundle, publication, source pin, source manifest, node/edge
digests) and `sdk_publication` (the receipt example's fixture publication and context ref) separately. `approved` and
`sql-substitution` use the Catalog-derived seed; `declaration-mismatch` uses an explicitly labelled injected fixture seed
(`seed_origin = injected-fixture-seed`, `metrics/revenue` under the same pinned publication), never a second Catalog discovery.
The cache is disabled for concept seeds (`scope.cache = DISABLED_CONCEPT_SEED`); the oracle engine now refuses to serve a
publication other than the one requested (`NO_PUBLICATION`) instead of relabelling whatever graph it holds.

**Evidence begins before the Catalog read.** Catalog mode writes everything under `evidence/catalog-chain/<run_id>/`: raw
`catalog/catalog_list_<n>.json` and `catalog_entry.json` responses with SHA-256, `retrieval/retrieval_<case>.json` (the
governed input), `journal.jsonl`, `receipt/case_<case>_<mode>.json` diagnostics, and the run's own `chain_<mode>.json`;
`evidence/catalog-chain/chain_<mode>.json` is the atomically written latest record. Early refusals keep the same retained final
record. **Job journal.** In live catalog mode every BigQuery query the chain submits goes through `publication.run_journaled`:
pin resolution, seed visibility, observed head, payload rows (nodes + edges), the three retrieval stages (`retrieval_walk`,
`retrieval_context`, `retrieval_nodes`, via `retrieve._run` when `clients["journal"]` is set) and the declaration read
(`chain_declaration`, via `BigQueryStore.declaration` on every engine). The job reference is one `(project, location, job_id)`
chosen by the chain and written to the journal **before the send**: the project is the client's billing project (passed
explicitly to `client.query`), recorded separately from the dataset project, and the same reference is used by
`reconcile_job` and by the `same_requester` identity check (Astra re-review R4: a job submitted under the client's project
is never looked up under the dataset project). An empty read keeps its id (`EMPTY`); a local exception at submit or
`result()` never becomes a terminal state on its own — `reconcile_job` reads `jobs.get` under that reference (bounded, no
retries): not found → `NOT_SUBMITTED`, server DONE → `DONE`/`ERROR`, RUNNING → one cancel + readback → `CANCELLED`, anything
unreadable stays `UNKNOWN` with its id and the run is `CHAIN_INCOMPLETE` at `unresolved_jobs`. Every journaled id enters the
`same_requester` identity set once (`job_inventory.graph`, deduplicated; `job_inventory.refs` carries each reference).
The hermetic store journals the same roles with no job id (`actual_jobs = 0`). The configured runtime dataset is the single
destination for pin resolution, payload rows, retrieval and declaration: a client or store wired to a different dataset is
refused as `DESTINATION_MISMATCH` before the first store read, whether the client or a supplied store diverges (Opus PR 41 P2;
the B2 lifecycle configuration routes everything to the owned dataset). Fixture mode (`--seed-mode fixture`, the default) is unchanged apart from the journal and keeps `evidence/chain/`;
its live declaration read now also keeps its job id when the lookup is empty.
These live-branch behaviours are exercised hermetically against a fake BigQuery client that serves the chain's real SQL
(`tests/test_chain.py::FakeBigQuery`), and are now also exercised live (Slice B1/B2 below).

Hermetic result (`evidence/catalog-chain/chain_hermetic.json`, injected responses, `seed.mode = catalog-mock`): `CHAIN_CONNECTED`
— pin OK, publication OK with head observed = pin, source OK, all three payloads `CONSISTENT`, `approved` RELEASED on the SDK's
synthetic fixture, `sql-substitution` REJECTED `sql_mismatch` → REFUSED, `declaration-mismatch` MISMATCH → REFUSED, CLI never
invoked; all acceptances `MET`. **This is a hermetic contract result, not a live Catalog success**: no Catalog, BigQuery or
receipt job ran. Live B1 and B2 have since run; their results are below.

`okf_bq_graph/catalog_lifecycle.py` is the isolated Slice B2 driver: owned dataset `okf_catalog_chain_<run_suffix>` (US,
relational tables only — never `graph.sql`, `section_vectors` embedding, reservations or IAM), owned entries under
`<group>/entries/acme-retail-catalog-chain/<run_id>/`, deployment `acme-retail-catalog-chain-<run_id>`; the allowlist is derived
from this local configuration before any Catalog read, so a returned pin cannot authorize its own destination. It snapshots the
original entry and head read-only, publishes with a full-row readback (READY only when the retained rows, recomputed digests,
section hashes, dangling and distinctness checks all hold), advances the head with one MERGE only for a READY owned publication
(`inject_failure="before_head"` leaves the old head; `"before_ready"` leaves loaded rows that can never become READY or head),
generates owned pins from the verified rows, preserves authored aspects with explicit aspect keys (no delete-missing), and
cleans up only exact owned resources with absence readback (`cleanup.json` is `COMPLETE` only then). **Ownership is a
stamp, not a name:** every `Lifecycle` instance has an invocation stamp (`okf_owner` label on the dataset, `entrySource.labels`
on entries) written at creation; ownership of a pending create is persisted to `ownership.json` **before** the write, and a
pending resource read back later is adopted **only** if it carries this invocation's stamp — a resource under the same
(normalised) name with another or no stamp is `FOREIGN_PRESERVED`, left untouched, and blocks `COMPLETE` (Astra re-review R2:
`review-run-A` and `review_run_a` share a dataset name but never a stamp). A timed-out create is a **pending attempt** with
its own `attempt_id` (passed to `create_dataset` / `create_entry` and written onto the resource as the `okf_attempt` stamp
beside the owner stamp); an absent readback never closes it and **elapsed time is not an outcome**: it stays
`ABSENT_PENDING` (receipt `INCOMPLETE`, `recheck_after_s = settle_s` only schedules the next look) until either the resource
appears carrying this invocation's stamp **and this attempt's stamp** (adopted and deleted on that cleanup run) or the adapter
establishes through `attempt_outcome(kind, name, attempt_id)` that this exact attempt terminated without applying
(`NOT_APPLIED_VERIFIED`). One present resource discharges exactly the attempt that produced it: a resource stamped by
another of our attempts is `OTHER_ATTEMPT_PRESENT` and leaves this attempt pending, and a second create for a target that
still has an unresolved attempt is refused (`ScopeViolation`) until cleanup has reconciled the first (Astra re-review 3, R3). The in-memory fake returns no outcome by default, so a lost create stays pending across every
rerun until it materialises; a real adapter may only answer from its own request/operation bookkeeping (Astra re-review R3
and re-review 2; cleanup is rerunnable and a create that completes after any window is still owned and removed). Job-backed
BigQuery operations (DDL, loads, inserts, updates, MERGE, SELECTs) get a driver-chosen `(project, location, job_id)` journaled
before dispatch; a call that raises is reconciled through `job_state` (not found → `NOT_SUBMITTED`, DONE → `DONE`/`ERROR`,
RUNNING → one cancel + readback → `CANCELLED`, unreadable / still running → `UNKNOWN`), and cleanup re-reads every unresolved
job under its own reference: **deleting the target dataset is never evidence about the job** (Astra re-review R5; the former
`MOOT` state is gone). `withdraw`/`restore` apply only to publications this run verified READY; `restore` requires the
current row to be `WITHDRAWN` and re-runs the full-row readback before reinstating READY (`RESTORE_REFUSED` otherwise), so an
`INVALID_READBACK` or corrupted publication can never be promoted (Astra PR 41 P2). P2 comes from
`prepare_derived_source`: a retained temporary copy with one non-computation policy file changed, pinned as
`<base>+local.<manifest16>` and recorded in `derivation.json`, never labelled as the clean upstream commit. Hermetic tests
run it against an in-memory fake cloud; `okf_bq_graph/catalog_live.py` is the live adapter and experiment driver on top of it
(Slice B2 below).

## Catalog-seeded chain, live (2026-09-07, Slice B)

Two live runs. Both are **operator ADC on both legs**, relational/on-demand only — no embeddings, reservations, IAM
changes, Enterprise window or graph DDL, and every SELECT capped at 100 MiB billed. The SDK identity stays an explicit
synthetic fixture publication even though the graph leg is live.

### B1 — the original KC entry drives the chain (`live-20260907T153329Z-21d91539`)

`python3 -m okf_bq_graph.chain --live --seed-mode catalog`. A fresh Dataplex read of the **existing** KC entry
(1 list page, 11 entries, exactly 1 match) resolved pin `pub_190192147fd7fd78` against the retained
`publications`/`nodes` rows in `okf_graph_spike_20260905`; the head was observed equal to the pin and never followed.
The clean pinned checkout (`git HEAD == 31da799a`, bundle tree clean) was compiled as the trusted projection.

`CHAIN_CONNECTED`: all three payloads `CONSISTENT`; `approved` → BOUND → receipt `VERIFIED` → consumer `RELEASED`;
`sql-substitution` → BOUND → receipt `REJECTED` → `REFUSED`; `declaration-mismatch` → bind `MISMATCH`, receipt **not
invoked** → `REFUSED`. 21 journaled graph jobs + 2 receipt jobs = 23 compared, `same_requester = SAME`,
`unresolved_jobs = 0`. Evidence: `evidence/catalog-chain/live-20260907T153329Z-21d91539/`.

### B2 — owned lifecycle: republish, stale and payload gates (`b2-20260907t162636z-cd45`)

`python3 -m okf_bq_graph.catalog_live --live`. 222.97 s wall. B1 cannot reach these gates: it must not mutate the
original entry, head or dataset. So the driver stands up an **isolated** dataset and its own Catalog entry (allowlist
derived from `LifecycleConfig` before any Catalog read), publishes P1 `pub_190192147fd7fd78` and a genuinely distinct
P2 `pub_ae9b6cb130731d01`, and runs nine full chains against them.

| Case | Result | What the live run showed |
|---|---|---|
| `b2-control` | **MET** | `CHAIN_CONNECTED` on the owned entry/dataset, head = P1, all three receipt cases MET |
| `historical-inflight` | **MET** | the owned head moved P1→P2 *between* pin resolution and the payload read (barrier: resolution head `pub_190192147fd7fd78`, `SWITCHED`, head after `pub_ae9b6cb130731d01`) and the request still served P1 **exactly** — a retained serve, not a `FAIL_STALE` refusal |
| `historical-fresh` | **MET** | a new request after the switch: head observed = P2, P1 served exactly |
| `fail-stale-withdrawn` | **MET** | P1 withdrawn while Catalog still pinned it → `FAIL_STALE` `PUBLICATION_NOT_READY:WITHDRAWN` at `publication`, zero cases, no receipt |
| `missing-runtime-aspect` | **MET** | `ASPECT_MISSING` at `seed`; both authored aspects intact; the authored overview never supplied a substitute seed |
| `wrong-publication-pin` | **MET** | `FAIL_STALE` `PUBLICATION_MISSING`/`SEED_MISSING`; no alternate entry, no head fallback |
| `wrong-seed-pin` | **MET** | `FAIL_STALE` `SEED_MISSING` |
| `mixed-payload-injection` | **MET** | both tampered cases `INCONSISTENT` → `NOT_BOUND` → no receipt → `REFUSED`; the untouched `declaration-mismatch` case stayed `CONSISTENT` |
| `recovery-control` | **MET** | valid pin restored, `CHAIN_CONNECTED` again (head = P2, P1 served) |
| `cleanup` | **MET** | originals `UNCHANGED` (identical entry SHA-256 and head before/after), owned entry and dataset deleted with absence readback, 78 lifecycle **operations** `DONE` (of which **48 are BigQuery jobs**; the rest are Catalog GET/PATCH/DELETE and dataset create/delete, which submit no job), 0 unresolved |
| `job-identity` | **MET** | all **170** jobs the run submitted — 48 lifecycle + 114 graph + 8 receipt — read back under their own `(project, location, job id)`: every one `DONE`, one principal, none unread or without an identity |

P2 is a real compilation of a retained temporary tree with one **non-computation** policy file changed, pinned
`<base>+local.<manifest16>` and recorded in `derivation.json` — never labelled as the clean upstream commit. The tree
is pruned after the run to `derivation.json` + the changed file.

**The mixed-payload case is live-backed CLIENT fault injection.** The actual live retrieval result was altered after
BigQuery returned it and before the payload guard: a P2 section id mixed into the P1 computation, and SQL bytes
changed under an *unchanged* `sql_sha256` label. **BigQuery did not return a torn publication.** Each raw live result
is retained with its SHA-256 *before* mutation under `injection/`.

**Checked after the run against the cloud, not against the driver's own receipt.** Two separate checks, and the
distinction matters. A time-window `INFORMATION_SCHEMA` aggregate showed 170 jobs `DONE`, 0 errored, one principal,
largest single job 70 MiB against the 100 MiB cap — but an aggregate over a window counts jobs, it does not
enumerate or reconcile them. The **follow-up audit** (`bin/followup_job_audit.py`,
[`job_identity_followup.json`](./evidence/catalog-chain/b2-20260907t162636z-cd45/job_identity_followup.json)) does:
it rebuilds the exact job set from the retained evidence and reads all **170 back individually** under their own
references — 170/170 `OK`, all `DONE`, one principal, none missing an identity. Separately, `entries.list` is back
to exactly 11 entries with no `catalog-chain` entry left, the owned dataset is absent, and
`okf_graph_spike_20260905` is untouched.

Why the follow-up audit exists: the chain's own `same_requester` needs both legs populated, so it says `UNKNOWN` for
the mixed-payload chain (21 graph jobs, no receipt — the *expected* shape of that adversary) and `NOT_RUN` for the
early refusals. The strongest negatives therefore had the weakest identity evidence. Three refusal chains are worse
still: they return through `chain._broken()`, which never builds a `job_inventory`, so their 3 jobs each existed only
in their own chain journal. The driver now audits the exact set in-run and a case is `MET` only when its boundary
behaved correctly **and** that chain's identity evidence is complete; the boundary verdict is kept separately in
`behaviour`, so an incomplete-evidence downgrade never erases a correct refusal.

### What these runs do not establish

Not the connected bar, not RFC Phase A/2, and no upgrade to the board pack, STORY or the older `chain/0.2.0` fixture
run. In **these** runs a single operator holds both legs, so they establish no restricted-SA enforcement (the separate
restricted-requester chain does, and only for itself: "Live restricted pass (Slice B, 2026-09-07)" above) and no
independent constrained attester; the receipt boundary still binds to a synthetic SDK fixture publication. Enterprise/GQL, least privilege,
scalability, performance and operating acceptance all stay out of scope.

## Graph engine inside the chain — Slice A, hermetic (2026-09-07)

Every chain run retained so far used the **relational `fallback`** engine (or the in-process oracle). Nothing here
changes that: **there is still no live GQL chain evidence**, and this slice ran no cloud workload, opened no window and
upgraded no legacy receipt. What it lands is the plumbing plus the refusals, tested offline.

**`--live --engine gql` now refuses instead of guessing.** `chain.py` opens no Enterprise capacity of its own, so a bare
GQL request could only end in an edition error or in a relational answer wearing a Graph label. It stops first, with a
typed record written **before any grant, client query or SDK launch**:

```
engine_admission = {"status": "GQL_WINDOW_NOT_CONFIGURED", ...}
verdict = CHAIN_INCOMPLETE, broken_at = engine_admission
```

`--gql-window LABEL` supplies the owned controller (`okf_bq_graph.chain_window`); a controller that has not proven an
open assignment is `GQL_WINDOW_NOT_OPEN`. Recording a controller is not enough: every BigQuery client the chain or the
requester broker uses is constructed **through** `window.bind_client`, and a client that would submit outside that gate
is `GQL_CLIENTS_UNBOUND` — refused before any grant, query or SDK launch. The receipt child registers as a controller
worker, so stop reaches it, close joins it before the union is sealed, and its retained job references are adopted into
the window's cleanup. `run_chain` returns before the window closes, so the retained record is amended afterwards: a
chain that ran inside a window whose capacity, jobs, restores or worker joins are outstanding is downgraded to
`CHAIN_INCOMPLETE` / `broken_at = window_cleanup` whatever its case outcomes were.

**`okf_bq_graph.chain_window` — one controller for the whole window.** Lifted out of `run.py::main` with the clock,
opener/closer, watcher, client factory and probe injected. It owns an exclusive `flock` lease over one **explicitly
named** capacity manifest and evidence directory: a *missing* manifest is a refusal, not an empty ledger, so a fresh
worktree cannot forget an earlier window's obligations. It refuses a reused label, carries the cumulative
120-minute ceiling, spawns the independent closer **before** any paid resource, proves the assignment with real probes
(failures retained), hands every operator/requester client out already bound to one submission gate, and starts capacity
closure **without** waiting for result I/O or `jobs.cancel`.

* **Nonownership is established before any mutation.** The reservation inventory is read first; if the name already
  exists, or the listing cannot be read at all, the controller refuses (`RESERVATION_PRE_EXISTING` /
  `OWNERSHIP_UNKNOWN`) having created and deleted nothing. If a race still produces an "already exists" on create, only
  what *this* invocation made is released (`reservation.release_own_resources`) — the production closer, which deletes
  the reservation and every assignment pointing at it, is never run on capacity we do not own. That decision is made
  **before** the watchdog's waiter is released, so a stop arriving mid-collision cannot let a woken closer delete the
  peer's capacity first; and the manifest records the reservation as `pre_existing`, so a **detached** closer or a
  retry after a partial rollback honours it too — an in-process flag protects nothing across processes.
* **Restores get a bounded cleanup channel.** Stopping the only submission channel makes a row-policy or ACL restore
  raise, and the obligation disappears. Close now opens a separate bounded channel (`WindowJobs.open_cleanup`) so
  restoration DDL can still be submitted, journaled and read back after workload admission closed.
* **A failed restore is a durable blocker, from the moment it is registered.** `register_restore` writes the
  obligation to `restores_<label>.json` as PENDING immediately — *before* the caller performs its first mutation — and
  rewrites it with the outcome at close. A callback that only lives in memory does not survive the failure the
  detached watcher exists to handle: a driver killed between the grant and the close would otherwise leave no file at
  all, and `restores_clear` reads a missing file as "nothing was ever changed". `require_clean_windows` refuses while
  any obligation file has outstanding entries — a fresh worktree, a fresh label or verified capacity does not clear it.
* **The actual send re-checks admission, on both transports and in both phases.** `submit()` checks, then calls
  `client.query(...)`; a credential refresh inside that call can outlive the stop and let the job POST leave
  afterwards. Both of the client's transports are guarded — `client._http` **and**
  `AuthorizedSession._auth_request.session`, the separate plain `requests.Session` an internal 401 refresh actually
  dispatches through — each getting a fresh remaining budget rather than the timeout copied from the original
  submission. The same applies during **result reads**: `_ResultHTTP` copies the session, and `__dict__.update` would
  otherwise carry the caller's shared `_auth_request` straight onto the copy, so the job-local transport is given its
  own guarded `Request`. The submission guard is installed for the duration of the submission only, and the result
  guard lives on the job-local copy, so cancellation and terminal readbacks keep working on the caller's own
  untouched transport.
* **Worker membership is durable before the worker's first launch.** `register_worker` persists a PENDING
  reconciliation obligation — naming the worker and *where* its retained references live — before the child is ever
  launched. In memory it survived only a normal close: a driver killed after the child had submitted left nothing on
  disk saying a receipt child existed, so `safety.cleanup` reconciled an empty parent inventory, wrote
  `verified: true`, never read the child's job, and the next controller opened while it was still RUNNING. The
  obligation is resolved at close (RECONCILED) or left outstanding (FAILED), and the reopening gate honours it.
* **A worker's obligations are the window's obligations, in recovery too.** A registered worker contributes both job
  references and evidence it could not resolve into one. References are adopted with their **full**
  `(project, location)` — a child job in another project read under the module defaults returns NotFound while the
  real job keeps running — and a reference whose submission the worker never confirmed cannot be closed by that
  absence. Those references are written into the journal *and* the receipt, and `cancel_journal` (the path
  `safety.cleanup` uses) reads them back, so the detached retry cannot re-certify under the defaults what the initial
  close correctly refused. Evidence with no id at all
  (a damaged or silent child journal) is persisted alongside the restore obligations. `require_clean_windows` also
  scans the evidence directory for `jobs_*.json` and `restores_*.json`, so a run that crashed before recording its
  manifest row still blocks the next window.
* **A dry run is a bounded operation, not a job.** BigQuery returns no `jobReference` for one, so the window neither
  invents nor journals an id — an invented id's 404 would otherwise read back as `verified_done`.

Unresolved jobs, a failed restore or a worker that could not be joined make the close `clean: false`, and the receipt it
writes does not satisfy the reopen gate.

**`okf_bq_graph.receipt_window` — the SDK child inside the window.** `subprocess.run(timeout=…)` bounds a process, not a
server: killing the child cancels no job. A private `usercustomize.py` (never `sitecustomize.py`) installs guards in the
child around the *actual* seams — `google.auth.default` (the existing e-mail-scope shim, composed),
`AuthorizedSession.send` (so a credential refresh and the internal 401 retry each get a fresh budget),
`Client.query`, `Connection.api_request` (the verifier's direct REST reads) and `urllib.request.urlopen` (the tokeninfo
call `broker.open_live_session` makes before any client exists). No SDK source is edited and the pin is not moved.

* The child is handed a **nonsecret** identity: label, an **absolute `time.time()` epoch deadline** (never rebased onto
  a child-sampled start), a stop file and its own journal path.
* The guarded send seam is the **base `requests.Session.send`**, not just `AuthorizedSession`. `AuthorizedSession` does
  not define `send`, and more importantly `creds.refresh(Request())` uses the `Request`'s *own* plain `requests.Session`
  — so guarding only the subclass leaves the credential refresh unbounded and admitted after stop.
* The SDK's deterministic `execute.job_id_for` id is journaled **before** the send and **never replaced**; automatic job
  retry is disabled, because a retry inside `result()` submits a new job and replaces the id.
* **Dry runs are bounded operations, not jobs** (`actual_job: false`): no phantom id reaches cleanup or identity.
* **One journal per launch.** The child's sequence counter restarts in every interpreter, so a shared journal makes two
  launches collide on `seq` and silently keeps only the last. Each launch gets its own file and its own invocation id,
  and `ingest()` folds on `(invocation, journal, seq)` and reconciles every launch.
* **The journal fails closed.** A write failure is not swallowed: intent must be durable *before* dispatch, or
  `JournalUnavailable` stops it. A missing, unreadable, unparsable or entirely silent launch journal is itself an
  UNRESOLVED lifecycle obligation, never an empty inventory. A job the SDK diagnostic names that the child never
  journaled — and the reverse — is unresolved too.
* A submission whose response is lost stays `UNRESOLVED`; only admission closed *before* a call is a known
  non-submission (`REFUSED`). An unresolved child submission blocks `job_audit`.
* `preflight()`/`handshake()` prove the seams and the installed guards **before any paid window opens**. A pin without
  them yields `SDK_WINDOW_BRIDGE_UNSUPPORTED` — no window is opened, and Slice B stays blocked until a separately scoped
  SDK change and an explicit pin update are reviewed. An interpreter with user site-packages disabled (`site.
  ENABLE_USER_SITE` false, as in a `--no-user-site` virtualenv) never runs `usercustomize`, so no start-up guard can be
  installed: that is reported as `USERCUSTOMIZE_DISABLED` and refused rather than assumed bounded. The handshake runs
  on its own probe environment: it allocates no workload launch and names no journal, so a successful preflight cannot
  leave a permanently "damaged" launch behind in the workload inventory.
* **Pending work reaches the parent.** `jobs()` hands the controller confirmed *and* pending references, so a lost
  response enters the window journal, the cleanup receipt and the reopening gate rather than living only in the chain
  record. The restricted broker's teardown is **registered** as a window restore before its first mutation and runs on
  the bounded cleanup channel with the cleanup client; a teardown that *returns* `UNVERIFIED` without raising is a
  failure like any other. Because that restoration submits its own administrative DDL *during* close — after the chain
  record's inventory and identity verdict were computed — the chain also registers a **post-close** rebuild: the
  finalizer re-reads the broker's administrative jobs, re-runs the identity audit over the complete set, and lets the
  rebuilt verdict govern the final record (`CHAIN_BROKEN` at `identity` on an unexpected principal, `CHAIN_INCOMPLETE`
  on an unresolved statement). That audit gets its **own bounded read-only channel**, opened at close with an absolute
  deadline: `WindowAuditClient` exposes `get_job`/`list_jobs` only — no blanket `__getattr__` delegation to the raw
  client — gives each read an explicit timeout from the remaining budget instead of the SDK's 128-second default, and
  raises `AuditExpired` once the deadline or read budget is gone. The budget is re-decided at **every dispatch inside
  one read**, not once per read: `retry=None` stops api-core retrying, but `AuthorizedSession` still answers a 401 by
  refreshing the credential and re-sending, so a read admitted with five seconds left could otherwise refresh through
  the deadline and retry afterwards. And because a send already in flight — or a transport this client cannot reach —
  can still answer late, a result that **arrived** after the deadline is rejected too. References it did not read stay
  UNKNOWN and the run finishes `CHAIN_INCOMPLETE`; an audit that outlives its budget is not evidence that the audit
  completed.

**Engine proof (KTD4).** The retrieval cache key now includes the **engine**, so a relational entry can never be replayed
under a GQL request, and `scope.templates` records the compiled walk/context template with its SHA-256 and whether it
contains `GRAPH_TABLE`. `chain.engine_proof` judges the trusted client configuration, the returned scope, that template
and the platform's own `reservation_id`/`edition` on the walk jobs. A returned engine label alone decides nothing. A
fallback template, a `FALLBACK` warning or a cache hit is `CONTRADICTED` → `CHAIN_BROKEN`; a missing walk job, an
on-demand reservation or a non-Enterprise edition is `NOT_PROVEN` → `CHAIN_INCOMPLETE`. Under a live GQL window
memoization is disabled for every case except `revocation-before-replay`, whose cached replay *is* its evidence.

**Scoped cases.** `--cases a,b` records `selected_cases`, `omitted_cases` and `scope.complete_suite`. An omitted case is
NOT_RUN; one approved case passing is never the suite's negative coverage.

**`okf_bq_graph.reconcile_window` — the legacy gate, read-only.** Five opened windows (`smoke-1`, `integration-0007`,
`integration-0009`, `all-0012`, `all-0017`) have no job journal at all, so the reopen gate cannot pass; `safety-0011` has
no `opened_at` and is a closer record, not a sixth opening. This module reconstructs a journal/receipt pair from
`jobs.list` (all users, FULL, every page, plus `parentJobId` child listings) and `jobs.get` per owned qualified
reference — and refuses whenever the evidence is short:

| Condition | Outcome |
|---|---|
| a page token left behind, a cap hit, an `unreachable` location, a transport error | BLOCKED (a prefix is not the window) |
| a job in the span with no ownership signal, or one carrying only the window's reservation **name** | AMBIGUOUS → BLOCKED until resolved by an explicit decision **with a reason** |
| a declared evidence source that cannot be read | BLOCKED (missing evidence, not a footnote) |
| a script parent whose declared `numChildJobs` is not matched by the children actually read | BLOCKED (child listings are **not** time-filtered; an exhausted page is not proof of membership) |
| a parent whose **terminal** snapshot declares more children than every listing pass produced | the new children are drained and read back; still short → BLOCKED |
| `jobs.get` returns 404, fails, or returns another reference | UNVERIFIED, never `verified_done` |
| a `PENDING`/`RUNNING` job | BLOCKED |
| quiescence not evidenced — it needs `established`, a **named record** and the moment the last submitter stopped — or a repeat listing adds references | BLOCKED |
| no owned job at all for an opened window | BLOCKED (an empty inventory is not evidence of an empty window) |

`numChildJobs` is the parent's declaration; `scriptStatistics` is a *child's* own context, so an ordinary terminal
script leaf is not mistaken for a parent that owes a child count. A server-side script can also finish a statement
after every listing pass — submitter shutdown does not stop it — so the **terminal** parent snapshot governs
membership, and children it reveals are drained and read before anything is sealed.

The listing covers the **submission lifetime**, not the capacity interval: it is bounded by the later of capacity close
and evidenced submitter shutdown, then extended while owned work reaches its edge, so a job created after capacity was
deleted is read rather than filtered away. A produced journal says `reconstructed: true`, names its sources with their
SHA-256 and is hashed into its receipt;
`verified` is **derived** from the readbacks, never accepted from an input. Staged files go to a caller-chosen directory
(`require_clean_windows(..., evidence_dir=…)` can gate them in place); publishing them into `evidence/` is a separate
authorized step, and an original artifact is never overwritten. Nothing in the module cancels, deletes or submits.

```bash
python3 -m okf_bq_graph.reconcile_window --plan plan.json --stage-dir /tmp/stage         # no transport: BLOCKED
python3 -m okf_bq_graph.reconcile_window --plan plan.json --stage-dir /tmp/stage --live  # authorized operator GET
python3 -m okf_bq_graph.chain --live --engine gql                                        # refuses: no owned window
python3 -m okf_bq_graph.chain --live --engine gql --gql-window <original-label> --cases approved
```

**What Slice A does not establish.** No live GQL retrieval, no live window, no reconciled legacy receipt, no benchmark
cell (G8 remains 0/9) and no accepted 2026-09-19 threshold. The hermetic suite ran against the **installed**
`google-cloud-bigquery 3.40.1`, while `pyproject.toml` pins `3.45.0`: the transport regressions here are real-object
tests at 3.40.1 and should be re-run at the pinned version before any live claim rests on them.

## Ordinary-SQL baseline for the 2026-09-19 checkpoint (2026-09-07, predeclared and empty)

`evidence/sql-baseline/baseline.md` is a plan, not a measurement. It exists because the checkpoint has to compare an
engine against a stated envelope, and the only ordinary-SQL numbers on record are three single observations from
integration runs. Regenerate it with `python3 -m okf_bq_graph.sql_baseline`; do not edit it by hand.

What it declares, on the same pinned corpus (`acme_retail` at `pub_190192147fd7fd78`, source pin `31da799a`) and the
same question set as the GQL cells:

* **Four retrieval cells** on the `fallback` engine — forced-seed and natural-question shapes, each at C=1 and at C=5,
  20 warmups + 100 measured, 60 s timeout, result cache off. The two shapes are never pooled: the natural shape runs a
  query embedding and a vector seed that the forced shape does not. C=5 is a planning default, not an accepted
  concurrency; C=1 is the only concurrency any recorded observation covers.
* **Two request-to-consumer cells**, `NOT_IMPLEMENTED`. `retrieval_ms` and `request_to_consumer_ms` are separate cells
  and are never substituted for one another, and the 2026-09-06 23-second three-case chain pass is neither metric.
  `benchmark.measure` stops at retrieval; `chain.py` runs each case once. Filling these needs a sampled driver that
  does not exist.
* **Five cost cells**, all `UNMEASURED` and listed rather than omitted, because an absent row reads as zero:
  publication visibility, publication upkeep, embeddings, storage, and cost per success with failed and refused
  attempts in the numerator and out of the denominator.
* **A budget and a stop rule**: 900 s per cell, 3600 s total, 64 GiB billed, $0.50 on-demand at list, no reservation.
  The card projects the declared samples from observed bytes per request (37.5 GiB → $0.23 at list) so no cell starts
  against a ceiling nobody checked. Embeddings, storage and upkeep are not in that projection.
* **Three recorded prior observations**, read out of `landmine_forced_fallback.json`, `all_all-0017.json` and
  `natural_question_fallback.json`. Each is n=1 at C=1 from an integration run, with no warmups, no declared sample
  size and no failure denominator, so none of them fills a cell — `tests/test_sql_baseline.py` fails the build if one
  starts to.

**The driver exists; no cell has been run (Slice B Pass 1, 2026-09-08).** `okf_bq_graph.run benchmark` was never the
right driver: it reads `fixtures/scale.json`, defaults its cells to the `gql` engine, pools the forced and natural
questions into one query list, and runs inside an Enterprise reservation window. `okf_bq_graph.sql_baseline_run` reads
this plan instead, hands each cell only its own shape (`tests/test_sql_baseline_run.py` runs the real
`benchmark.measure` with a faked `retrieve` and checks that no forced text reaches a natural cell or vice versa),
and labels the campaign with a fresh `sqlbase-<utc>-<hex>` run_id that is checked against the retained GQL summary
before a client is built. `--dry-run` constructs no client; `--live` is Pass 2 and needs Haiyuan's paid authorization.
Three execution guarantees were added after Astra's first review (PR 55, three P1s), each with an offline regression
that drives the real SDK with synthetic API responses:

* **On-demand is enforced and verified, not assumed.** Omitting a reservation window does not make a job on-demand;
  an unset routing inherits the project's assignments, and a standing Enterprise assignment exists. Every job carries
  BigQuery's job-level override `reservation = "none"`, and `RoutingGuard` reads every job's recorded statistics: a
  reservation_id or an edition on any job stops the campaign, and the record says `edition = "on-demand"` only when
  at least one job was checked and none violated. The standing reservation is neither listed nor touched.
* **Deadlines stop in-flight work.** Each cell gets its own `lifecycle.WindowJobs` gate (the job inventory, no
  capacity) with its deadline at the earlier of the 900 s cell budget and the 3600 s campaign deadline; submission,
  result polling and row pagination all stop there and in-flight jobs are cancelled with a receipt. A cell stopped
  that way is INCOMPLETE with `CELL_TIME_BUDGET` / `TOTAL_TIME_BUDGET`, including when the cut hit its last request.
* **Bytes and USD are enforced while running.** `BytesLedger` is one shared account over the whole campaign (warmups,
  failures, concurrent jobs). Each job takes a hold before submission that becomes its `maximum_bytes_billed`
  (≤ 1 GiB per job, ≤ the room left), settles against the bytes it actually billed, and when no room is left the next
  job is not submitted and the run stops `BYTES_BUDGET` / `USD_BUDGET`. The prior-observation projection is a
  pre-flight sanity check only.

`benchmark.run_cell` gained backward-compatible hooks for this: a per-cell `queries` list, `budget["deadline_reason"]`,
`budget["window_for_cell"]` and `budget["stop_check"]`; a cell that stopped for any reason is INCOMPLETE even when its
n-th attempt was retained. The reservation-window runner's `WINDOW_DEADLINE` label and behaviour are unchanged. The
card's retrieval cells read `NOT_RUN` with the exact command that fills each; the consumer cells still read
`NOT_IMPLEMENTED + FACTS_UNSELECTED`, and the driver refuses to run them.

**One correction this card carries.** `evidence/report.md` and `evidence/comparison.md` describe both forced fallback
observations as on-demand. Every job in `all_all-0017.json#fallback_forced` carries the spike's Enterprise reservation,
so that observation ran on Enterprise capacity. The card reads the edition from the jobs in each record. The dated
records are left as they are.

**An optional GQL comparison stays optional and later.** It must match this seed shape, corpus, authorization and
workload, and account for its reservation cost separately. The recorded GQL C=1 cell is 28 of 100 attempts; it is not a
completed cell and not a comparator.

The envelope those cells would be judged against — task, corpus, concurrency, volume, latency, freshness, retention,
success, cost ceiling and owner — is on the board pack at
[`/rfc/board-pack/#sep19-envelope`](../../board-pack/index.html#sep19-envelope), with every threshold labelled
PROPOSED. Haiyuan Cao (`caohy1988`) is the named owner as of 2026-09-07 and has accepted none of them.

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
python3 -m okf_bq_graph.chain --hermetic --requester restricted   # restricted-requester chain, no cloud (policy-emulating broker)
python3 -m okf_bq_graph.chain --live --requester restricted       # Slice B: both legs under sa:okf-receipt-restricted (IAM impersonation), ~5 min
python3 -m okf_bq_graph.job_audit evidence/chain/chain_live_restricted.json   # read-only: reconcile that record's inventory against jobs.list
python3 -m okf_bq_graph.chain --live                      # connected chain, on-demand fallback engine + SDK --live
python3 -m okf_bq_graph.chain --hermetic --seed-mode catalog --catalog-responses fixtures/catalog_responses.json   # Catalog contract, injected responses (catalog-mock)
python3 -m okf_bq_graph.chain --live --seed-mode catalog  # fresh Dataplex list/get of the KC-unblock entry -> retained publication -> receipt (Slice B1)
python3 -m okf_bq_graph.chain --live --engine gql         # Slice A: refuses with a typed record (no owned Enterprise window)
python3 -m okf_bq_graph.chain --live --engine gql --gql-window <label> --cases approved   # Slice B, gated: owned window + scoped case
python3 -m okf_bq_graph.reconcile_window --plan plan.json --stage-dir /tmp/stage          # read-only legacy window reconstruction
python3 -m okf_bq_graph.catalog_live --live --wall-cap-s 900 --timeout-s 30   # Slice B2: owned dataset + entry lifecycle around that chain, then cleanup (~4 min)
python3 bin/followup_job_audit.py evidence/catalog-chain/<run_id>                # read-only: re-read every job of a retained run under its own reference
python3 -m okf_bq_graph.run integration --minutes 25         # opens the Enterprise window, runs GQL cases, closes it
python3 -m okf_bq_graph.run benchmark --minutes 85           # benchmark cells from fixtures/scale.json
python3 -m okf_bq_graph.run all --minutes 85                 # both in one window
python3 -m okf_bq_graph.cost 2026-09-05T23:40:00Z 2026-09-06T00:35:00Z   # reconcile jobs + charged reservation timeline
python3 -m okf_bq_graph.partial && python3 -m okf_bq_graph.assemble      # honest cell summary + report.md
python3 -m okf_bq_graph.sql_baseline                         # offline: regenerate the predeclared SQL baseline card
python3 -m okf_bq_graph.sql_baseline_run --dry-run           # offline: print the baseline campaign (cells, queries, budget); no client
python3 -m okf_bq_graph.sql_baseline_run --live [--cells sqlbase_forced_c1 ...]   # Pass 2 (paid, on-demand, foreground): fill retrieval cells
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
