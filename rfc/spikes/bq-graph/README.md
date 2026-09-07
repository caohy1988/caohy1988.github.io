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
| `okf_bq_graph/principal.py` | Requester brokers for the chain (2026-09-06 Slice A): a hermetic policy-emulating broker (no IAM, no job) exercised by `chain.py --requester restricted`, and the IAM-impersonation broker for the restricted SA (graph leg via `authz.impersonated_client`, SDK subprocess via an `impersonated_service_account` ADC file, dry-run authorization probe per dependency table) wired for the live Slice B, not exercised → `evidence/chain/chain_hermetic_restricted.json` |
| `okf_bq_graph/benchmark.py`, `run.py`, `lifecycle.py`, `safety.py`, `partial.py`, `bin/safety_teardown.sh` | Bounded runner (20 warmups + 100 measured per cell, nearest-rank percentiles, failures retained), the window orchestrator (signal-safe cleanup lifecycle, job cancel, independent watcher), and the honest aggregation of interrupted cells (INCOMPLETE / NOT_RUN) |
| `okf_bq_graph/cost.py`, `report.py`, `assemble.py` | Slot attribution (exact named reservation vs other pools) and the charged autoscale slot-seconds bill from `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE`; non-mutating report tables; report assembly |
| `sql/*.sql` | `schema.sql`, `graph.sql` (property graph DDL), `seed.sql` (vector seed), `governed.sql` (two-hop GQL), `context.sql`, `impact.sql`, `stubs.sql`, `fallback.sql` |
| `fixtures/bundle_b/` | Negative fixture: identical relative paths, missing targets, duplicate hits, ambiguous replacement, `../` escape |
| `fixtures/cases.json`, `fixtures/scale.json` | Query set and benchmark cell matrix |
| `okf_bq_graph/catalog.py`, `seed.py`, `publication.py`, `journal.py`, `catalog_lifecycle.py` | Catalog-seeded chain (2026-09-06): Dataplex list/get reader + trusted-config parser, exact `ConceptSeed`, retained-publication resolution + trusted-source compilation + payload consistency guard, run-owned job journal, isolated relational-only lifecycle driver for the owned republish experiment |
| `tests/` | `test_compile.py`, `test_oracle.py`, `test_retrieve.py` (contract runs against oracle by default; `OKF_LIVE_ENGINE=gql|fallback` runs it live); `test_catalog.py`, `test_catalog_publication.py`, `test_catalog_lifecycle.py` + the catalog cases in `test_chain.py` (all hermetic, injected Catalog responses) |
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

### Restricted requester (2026-09-06 Slice A, hermetic only)

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
acceptances `MET`, no e-mail in the record. Live (`--live --requester restricted`): the IAM impersonation broker is wired
(graph leg through `authz.impersonated_client`; SDK subprocess under an `impersonated_service_account` ADC file written to a
private 0700 directory and removed in teardown, run.py unedited; dataset-level reader grants through
`authz.set_dataset_reader` only where the SA holds no entry (a pre-existing READER, WRITER or OWNER is left as it is,
never downgraded), waited for by probing under the SA, with the bound SDK publication's dependency tables known before
the first probe; identity `BOUND` only when the operator's `jobs.get` shows the SA's `user_email` on every job including
the pointer lookup and the cached-replay re-check job, `UNBOUND` → `CHAIN_BROKEN`, `UNKNOWN` → `CHAIN_INCOMPLETE`;
teardown restores every touched dataset's ACL to the snapshot taken before the broker's first mutation and reads it
back, `VERIFIED` only with at least one step and every read-back equal, `NOT_NEEDED` when nothing was touched) and
exercised only against fakes (a fake SA client and an owner holding real `AccessEntry` ACLs, through the real helper),
but **no live pass has run**: the retained live chain evidence is still `requester.mode = same-requester`, and the second principal
remains "not exercised in this chain" on every published surface until Slice B lands its own evidence.

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
(`tests/test_chain.py::FakeBigQuery`); no live job has run.

Hermetic result (`evidence/catalog-chain/chain_hermetic.json`, injected responses, `seed.mode = catalog-mock`): `CHAIN_CONNECTED`
— pin OK, publication OK with head observed = pin, source OK, all three payloads `CONSISTENT`, `approved` RELEASED on the SDK's
synthetic fixture, `sql-substitution` REJECTED `sql_mismatch` → REFUSED, `declaration-mismatch` MISMATCH → REFUSED, CLI never
invoked; all acceptances `MET`. **This is a hermetic contract result, not a live Catalog success**: no Catalog, BigQuery or
receipt job ran. Live B1/B2 (fresh read of the KC entry, owned dataset + entry lifecycle, P1→P2 head switch, FAIL_STALE,
live-backed mixed-payload injection, cleanup readback) are the next pass.

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
run it against an in-memory fake cloud; the live resources do not exist yet.

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
python3 -m okf_bq_graph.chain --live                      # connected chain, on-demand fallback engine + SDK --live
python3 -m okf_bq_graph.chain --hermetic --seed-mode catalog --catalog-responses fixtures/catalog_responses.json   # Catalog contract, injected responses (catalog-mock)
python3 -m okf_bq_graph.chain --live --seed-mode catalog  # fresh Dataplex list/get of the KC-unblock entry -> retained publication -> receipt (Slice B1; not yet run)
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
