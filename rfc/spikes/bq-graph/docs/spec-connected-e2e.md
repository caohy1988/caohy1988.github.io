# Spec: connected end-to-end run

Companion to `intent-connected-e2e.md`. This spec describes the runner `okf_bq_graph.connected` (version
`okf_bq_graph.connected/0.1.0`), the new repository `caohy1988/okf-connected-e2e`, the evidence it produces, and the
site copy.

## 1. Invocation and ownership

- `python3 -m okf_bq_graph.connected --hermetic | --live [--wait-s N]`
  - Hermetic mode runs fakes for Catalog, BigQuery, IAM and the SDK runner.
  - Live mode touches `test-project-0728-467323` only.
- Run id: `e2e-<yyyymmddthhmmssz>-<hex8>`. It is lowercase because it seeds BigQuery job labels; the
  `live_` prefix is avoided because of secret scanning.
- The run directory is `evidence/connected-e2e/<run_id>/`. It is created with `mkdir(exist_ok=False)` before any
  external call, which makes it create-or-fail ownership.
- The record `connected_<mode>.json` is written inside the run directory and atomically to
  `evidence/connected-e2e/connected_<mode>.json`.
- Every write redacts e-mails (`authz.redact`). Publication local ids and paths are masked with
  `authz.sanitize_ids` on the published copy; judges run on the unmasked payloads in memory.

## 2. Principals

- **Requester.** `sa:okf-receipt-restricted`, through `principal.RestrictedBroker` (IAM `generateAccessToken`).
  - Graph leg: the impersonated BigQuery client.
  - Receipt leg: an `impersonated_service_account` ADC file plus the `userinfo.email` scope shim for the SDK
    subprocess.
  - Catalog leg (new): an `AuthorizedSession` over impersonated credentials with `cloud-platform` +
    `userinfo.email` scopes.
- **Operator** (ADC). Grants, revokes and restores, and reads job identities and IAM policies back. The operator never
  executes a case stage.
- **Receipt subprocess interpreter.** `OKF_SDK_PYTHON` when set, otherwise `sys.executable`. This is needed because a
  virtualenv disables user site-packages, so the `usercustomize` shim would not load (README "Receipt leg").
  `chain.run_receipt` gains an optional `python` argument, and existing callers are unchanged.

## 3. Catalog access (new: `okf_bq_graph/catalog_access.py`)

`CatalogAccess(entry_group, member, role="roles/dataplex.catalogViewer", session_factory)` works as follows:

- **`snapshot()`**: `GET {group}:getIamPolicy` under the operator, recording bindings and etag. It runs before the
  first mutation.
- **`grant()`**: `POST {group}:setIamPolicy` with the snapshot's bindings plus `{role, [member]}`. If the member
  already holds the role, it is left untouched and marked pre-existing.
- **`revoke()`**: sets bindings with the member removed from `role`.
- **`restore()`**: sets the bindings back to the snapshot, then reads them back. The result is `VERIFIED` only when
  the sorted bindings equal the snapshot.
- **`observe(reader)`**: an `entries.get(view=ALL)` of the configured entry under the requester's session, returning
  `ALLOWED` (200 + aspect data), `DENIED` (403) or `UNKNOWN` (anything else).
- **`wait(want, reader, wait_s, every_s=10)`**: polls `observe` and records the waited seconds and the observation.
  Elapsed time alone is never treated as an outcome.
- **Journal.** Every IAM call is journaled with its HTTP status and response SHA-256. Policy bodies are retained
  redacted (members masked to aliases).

## 4. Stages and cases (live)

Order is fixed. `S*` are run-level stages; cases are graded MET / WRONG / NOT_REACHED.

| Stage | What | Under |
|---|---|---|
| S0 provenance | SDK head == `6719eb5` and whole checkout clean; Acme checkout HEAD == pin source revision and bundle tree clean (checked again by `trusted_source`) | local |
| S1 grant | Catalog snapshot + grant, observed ALLOWED; broker `apply(policy())` (graph dataset reader, SDK dataset reader), observed ALLOWED | operator mutates, requester observes |
| S2 connected-approved | see §4.1 | requester |
| S3 connected-sql-substitution | fresh Catalog-seeded retrieval + payload guard + bind; SDK `sql-substitution` | requester |
| S4 connected-denied-intermediate | broker `apply(policy(dataset="rls", hidden=(HIDDEN,)))`; injected legacy seed on `_rls` | requester |
| S5 connected-unauthorized-output | broker `apply(policy(sdk_tables=False))`; Catalog-seeded path to bind; authorization | requester |
| S6 connected-revocation | see §4.2 | requester |
| S7 teardown | Catalog `restore()`; broker `teardown()` (ACLs, `_rls` grantees, credential directory) | operator |
| S8 identity | `broker.identity` over graph, receipt, requester-probe and policy-admin jobs | operator reads |

### 4.1 connected-approved (the positive path)

1. **Catalog discovery.** `catalog.read_seed(HttpReader(session=requester_session), CatalogConfig())`. This is a
   paginated list plus `get(view=ALL)`. Raw responses are retained under `catalog/`. The pin is validated and frozen.
   `seed.caller` records `tokeninfo` of the requester session masked to its alias (`caller_is_requester: true`).
2. **Pinned publication.** `resolve_publication(BigQueryStore(requester_client, ...))`. It requires exactly one READY
   row plus the exact seed row; the head is observed and never followed.
3. **Trusted source.** `trusted_source(pin, acme_root)` compiles the clean pinned checkout.
4. **Governed retrieval.** `retrieve(pin.seed("catalog"), ...)` runs with engine `fallback` on the requester clients
   (`ds = cfg.runtime_dataset`, `journal`), and the result is retained. Then the declaration is read through the store.
5. **Payload guard.** `verify_payload(store, pin, trusted, result, comp, decl, engine="fallback")` must be
   `CONSISTENT`.
6. **Bind.** `chain.bind(comp, decl, sdk_pub, as_of, source_pin=pin.source_pin)` must be `BOUND`.
7. **Authorization, then fact read-back (secondary bar).** Authorization (step 8) is evaluated first, so a denied
   requester is refused naming authorization and no read-back is attempted. Under the requester, every table of the vendored `content.json` is read in full
   (schema from `get_table`, rows by `SELECT *`) and canonicalised as `okf-fact-content/1`. The result is judged with
   `consumer_run.admit_live`, which must return `OK` with the bound content digest. `FACTS_DRIFTED` or `MATERIALIZATION_EXPIRED`
   refuses before execution.
8. **Authorization.** `broker.authorize(sdk_pub["dependencies"])` must be `ALLOWED`.
9. **Receipt.** `run_receipt("approved", sdk_root, receipt_dir, live=True, env_extra=broker.receipt_env(),
   label="connected-approved", python=sdk_python)`. This is caller-delegated execution under the requester; the SDK's
   verifier seals the receipt.
10. **Consumer.** `chain.consume(bind, receipt, authz)`, plus a new condition: fact admission must be `OK`. `RELEASED`
    only if every binding holds.

Acceptance is MET when:
- Catalog is `OK` with mode `catalog`;
- the publication is `OK`, the source is `OK` and the payload is `CONSISTENT`;
- bind is `BOUND`, facts are `OK` and authorization is `ALLOWED`;
- the receipt exit is 0 with both verdicts VERIFIED / MATCH, and the decision is `RELEASED`.

The grading splits two ways:
- `NOT_REACHED`: an upstream outage or unpropagated grant.
- `WRONG`: a reached stage contradicted, for example payload INCONSISTENT, or a release with a failed check.

### 4.2 connected-revocation

1. **Control.** Broker `apply(policy())` and Catalog grant still present. The harness observes Catalog `ALLOWED`,
   graph dataset `ALLOWED` and authorization `ALLOWED`, all under the requester. No receipt is launched.
2. **Revoke.** Catalog `revoke()`; broker revocation of the base graph dataset reader, the `_rls` dataset reader, the
   SDK dataset reader and the `_rls` grantee. It waits until the requester observes Catalog `DENIED`, the graph probe
   `DENIED` and authorization `DENIED`. Each wait is bounded by `--wait-s` (default 600) and recorded.
3. **Fresh request.** `read_seed` under the requester must be refused (`CATALOG_ERROR`, HTTP 403) at `seed`. Nothing
   downstream runs.
4. **Retained-pin bypass.** Using the S2 pin, as an agent that cached it would:
   - `resolve_publication` must be `ERROR` (access denied);
   - `retrieve` must return `DENIED` / no concepts, paths or computations.
   Both attempts are journaled, so any job they submit is in the identity set.
5. **Authorization.** Must be `DENIED`.
6. **Stored receipt.** `chain.consume(S2.bind, S2.receipt, authz=step 5)` must be `REFUSED`, with a reason naming the
   authorization.
7. **No new launch.** `receipt_invocations_after_revocation == 0`.

MET needs all seven.
- `NOT_REACHED`: the control failed or a revocation was not observed within the wait.
- `WRONG`: any stage after revocation served content, allowed, or released.
- **Cached replay.** It is not exercised: Catalog concept seeds disable the retrieval cache
  (`DISABLED_CONCEPT_SEED`). The record says so rather than claiming a replay.

### 4.3 Other cases

- **connected-sql-substitution.** Same acceptance as `chain.accept("sql-substitution")`. Payload must be
  `CONSISTENT`; exit 2; REJECTED / MISMATCH / `sql_mismatch`; REFUSED.
- **connected-denied-intermediate.** Same acceptance as `chain.accept_restricted("denied-intermediate")`:
  - the seed is visible and returns no path;
  - no hidden id appears on any disclosure surface;
  - bind is `NOT_REACHED/retrieval_denied`, the CLI is never invoked, and the decision is REFUSED.
  The seed origin is `injected-fixture-seed` over the `_rls` governance copy of the same publication. The Catalog pin
  names the base runtime dataset, so this case is labelled "not a Catalog discovery".
- **connected-unauthorized-output.** Catalog-seeded retrieval, payload guard and bind (all under the requester) must be
  `BOUND`. Authorization must be `DENIED` with at least one denied table. The CLI is never invoked, and REFUSED names
  the authorization.

## 5. Verdict

- `E2E_CONNECTED`: every case MET, identity `BOUND`, zero unresolved journal entries, Catalog restore `VERIFIED`, broker
  teardown `VERIFIED`, and provenance ok.
- `E2E_BROKEN`: any case WRONG, identity `UNBOUND`, or a provenance or pin failure.
- `E2E_INCOMPLETE`: anything else. The record names `broken_at`.

## 6. Agent and CLI (new repository `caohy1988/okf-connected-e2e`)

- **Package** `okf_connected_e2e`. It depends on `okf-bq-graph-spike` pinned by commit
  (`git+https://github.com/caohy1988/caohy1988.github.io@<sha>#subdirectory=rfc/spikes/bq-graph`) and on
  `google-adk`.
- **`okf-e2e run --live`** runs the connected runner with no model. It prints a banner (project, requester alias,
  engine, model "none") and stage progress.
- **`okf-e2e agent --live "<question>"`** is an ADK `Agent` with `Gemini(model=DEMO_MODEL_ID)`; the default
  `gemini-3.8-flash` is on Vertex `global`. The banner prints the model id, and any `gemini-1.*` / `gemini-2.*` model id
  is refused. The agent has one tool, `governed_gross_margin(period)`, which is limited to the fixed synthetic
  January 2026 request. That tool runs the connected runner and returns the **tool payload**:
  `{decision, answer (only when RELEASED), run_id, receipt_ref "<id:sha256[:8]>", cases:{name: decision},
  access_checks:{...: status}, labels:{data:"synthetic", apis:"live GCP", engine:"relational fallback"}}`.
  - A payload validator refuses to hand the model any value that contains an e-mail, a `concept_id` / node id, a
    `pub_` id, SQL text or a bundle path. The validator is unit-tested.
- **Hermetic tests** cover payload masking, the model-id guard, and banner content.

## 7. Evidence and site

- `evidence/connected-e2e/<run_id>/` holds `connected_live.json`, `journal.jsonl`, `catalog/` raw responses,
  `iam/` redacted policy snapshots, `retrieval/`, `facts/`, `receipt/` diagnostics, and the `transcript.txt` of the
  recorded agent run.
- `evidence/report-connected-e2e.md` holds the human report: job counts by role, receipts, digests, waits, and
  remaining gaps.
- `/rfc/` "What is still open":
  - the bar sentence becomes what this run proved, with its limits;
  - residual gaps are named: GQL traversal, independent attester, customer data, benchmarks/cost, n=1;
  - Finance stays a decision request.
- `/rfc/demo/` gains a new section with `okf-connected-e2e.mp4` and links to the code repository and evidence.
  The prior tapes stay.
