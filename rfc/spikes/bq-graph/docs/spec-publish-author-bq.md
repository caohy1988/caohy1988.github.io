# Spec: publish in BigQuery, then consume (runner `okf_bq_graph.publish_connected/0.1.0`)

Companion to `intent-publish-author-bq.md`. Extends `spec-connected-e2e.md`; everything there still holds for the
consume half.

## 1. Choice of publish authority

Two BigQuery publish paths exist in the spike:

- **`publish.publish()`** always runs graph DDL (`ensure_graph`) and may embed. It writes the long-lived spike dataset.
  Its content-addressed publication is already `READY` there, so a re-run returns `ALREADY_READY` with no fresh load
  jobs.
- **`catalog_lifecycle.Lifecycle`** with the live adapter `catalog_live.LiveCloud` is the one chosen. It is
  relational-only (graph DDL, embeddings, reservations and grants are refused by `FORBIDDEN_SQL`). Its dataset and entry
  are run-owned with ownership stamps. It validates full rows before `READY`, advances the head with an atomic `MERGE`,
  and gives every job-backed operation a driver-chosen job id journaled before dispatch. It generates the Catalog pin
  from `READY` rows, and its cleanup reads back absence. This path already ran live in Slice B2
  (`evidence/catalog-chain/b2-20260907t162636z-cd45`).

## 2. Invocation and ownership

- CLI: `python3 -m okf_bq_graph.publish_connected --hermetic | --live [--wait-s N] [--timeout-s N]`.
- Run id: `kp-<yyyymmddthhmmssz>-<hex4>`, lowercase because it seeds dataset names and job ids.
- Run directory: `evidence/publish-connected/<run_id>/`, created with `mkdir(exist_ok=False)` before any cloud call. It
  holds:
  - `publish/`: lifecycle journal, `ownership.json`, `cleanup.json`;
  - `connected/<e2e run id>/`: the unchanged connected record;
  - `publish_connected_<mode>.json`.
- The record is also written atomically to `evidence/publish-connected/publish_connected_<mode>.json`.
- `LifecycleConfig` gains `dataset_stem` (default `okf_catalog_chain`) and `entry_stem` (default
  `acme-retail-catalog-chain`). Existing names are unchanged. This runner uses:

| Field | Value |
|---|---|
| dataset | `okf_kp_publish_<run_suffix>` |
| entry | `<group>/entries/acme-retail-kp-publish/<run_id>/metrics/gross-margin` |
| profile | `okf-kp-publish/1` |
| deployment | `acme-retail-kp-publish-<run_id>` |

## 3. Principals

- **Author = operator (ADC).**
  - Runs every lifecycle BigQuery job and Catalog write.
  - Live: after the run, `job_audit.roles_bound_to` reads each author job back with `jobs.get`. The role is `author`,
    and the expected identity is the operator. Result: BOUND, UNBOUND or UNKNOWN.
  - Hermetic: the same check runs against `HermeticCloud`'s job registry, labelled `hermetic job registry`.
- **Requester = `sa:okf-receipt-restricted`.** As in `spec-connected-e2e.md` §2. It never publishes. The two journals
  are separate, so the connected identity audit (requester roles) never sees author jobs.

## 4. Stages

| # | Stage | RFC §05 state | Under | Record |
|---|---|---|---|---|
| P0 | provenance: compile the Acme bundle at `SOURCE_PIN`; the checkout HEAD equals the pin; `validate_projection` valid | PLANNED | local | `author` |
| P1 | snapshot originals (read only: original entry sha, original head) | PREPARING | operator | `publish.originals` |
| P2 | `provision()`: owned dataset (stamped) + four relational tables | PREPARING | operator | jobs |
| P3 | `publish_relational(P)`: load nodes, load edges, full-row readback, validation checks, `publications` row `READY` | BQ_STAGED | operator | `publish.ready` |
| P4 | `advance_head(P)`: `MERGE active_publication` after `_ready(P)` re-read; head read before and after | BQ_COMMITTED | operator | `publish.head` |
| P5 | `write_pin(ENTRY_LOCAL, P, CONCEPT_PATH)`: pin generated from the `READY` publication and seed rows; create entry; readback through `parse_pin` = `OK` | KC_APPLIED | operator | `publish.catalog_pin` |
| C | `connected.run_connected(env, cfg=owned CatalogConfig)`: the five cases, grants, stable observation, teardown, requester identity | — | requester | `connected` |
| X | consumed-publication check (§5) | — | local | `consumed` |
| P6 | `verify_originals_unchanged()` then `cleanup()`: delete entry + dataset, absence read back, pending/job reconciliation | COMPLETE | operator | `publish.cleanup` |
| P7 | author identity (live) | — | operator reads | `publish.author_identity` |

Rules:

- If P3 is not `READY`, or P4 is not `SWITCHED`, or P5 is not `OK`, stage C does not run. Its record is `NOT_RUN`.
- P6 always runs (in `finally`), after C's own teardown, so ACL restores read back before the dataset is deleted.
- `state_trace` records each §05 state reached, with a timestamp and the job ids that establish it:
  - `BQ_STAGED`: the load jobs plus the `READY` insert;
  - `BQ_COMMITTED`: the `MERGE`;
  - `KC_APPLIED`: the create-entry attempt and its readback.

## 5. Consumed-publication check

From the connected record's `connected-approved` case, all of the following must hold, or the result is `MISMATCH`:

- `catalog.status == "OK"` and the seed mode is `catalog` (live) or `catalog-mock` (hermetic);
- the pin's `publication_id == P` and `runtime_dataset ==` the owned dataset, using the unmasked in-memory pin;
- `publication.status == "OK"`, `publication.head.publication_id == P` and `matches_pin` is true;
- the connected environment's store dataset equals the owned dataset.

## 6. Environment changes (backward compatible)

- `principal.RestrictedBroker(graph_dataset=DATASET)`. `_graph_ds()` returns `RLS_DS` for an `_rls` policy, otherwise
  `graph_dataset`.
- `connected.LiveEnv` passes `graph_dataset=cfg.runtime_dataset`. `graph_probe` and `requester_revoke` use
  `broker.graph_dataset`. The default `CatalogConfig` keeps `DATASET`, so the consume-only path is unchanged.
- `connected.HermeticEnv` accepts optional `catalog_pages` / `catalog_entries` (defaults: the fixture file) and a
  `head` (default: the projection's own id).
- `publish_connected.HermeticCloud` is an in-memory `CloudOps`: datasets, rows, jobs registry and entries.
- Hermetic consume is built **only from what hermetic publish wrote**:
  - the store holds the rows read back from `HermeticCloud` and its `active_publication`;
  - the Catalog reader lists and gets the entries in `HermeticCloud`;
  - a hermetic run whose publish is skipped or broken therefore cannot discover a pin.

## 7. Verdict

**`E2E_PUBLISH_CONNECTED`** when all of these hold:

- the author provenance is ok;
- `publish.ready == READY` and `publish.head.state == SWITCHED` (from `None` to P in the owned dataset);
- `publish.catalog_pin.readback_status == OK`;
- the publish journal has no unresolved entries;
- `consumed.status == MATCH`;
- `connected.verdict == E2E_CONNECTED`;
- `publish.cleanup.status == COMPLETE`;
- originals are `UNCHANGED`;
- author identity is `BOUND` (operator `jobs.get` live; the in-memory job registry hermetic).

**`E2E_BROKEN`** when any of these hold:

- `connected.verdict == E2E_BROKEN`;
- `consumed.status == MISMATCH` after the approved case reached publication;
- a publish readback was `INVALID_READBACK` yet a later stage ran;
- author identity is `UNBOUND`.

**`E2E_INCOMPLETE`** otherwise. `broken_at` names the first failing stage.

The consumed-publication check and the author identity are verdict inputs, not decoration.

## 8. Evidence and hygiene

- The record keeps each job's role, driver-chosen job id, state, target and timestamps. It also keeps:
  - the `READY` row: publication id, counts, digests, `ready_at`;
  - the head before and after, and the `MERGE` job id;
  - the entry name, `readback_status` and `state_trace`.
- Published copies go through `authz.redact`, and the home directory is elided.
- Job ids, dataset names and the publication id are not secrets and stay visible. They are the audit trail Astra
  re-reads with `jobs.get`.
- `summary(out)` feeds the CLI and agent. It adds a `publish` block to `connected.summary`: states, counts, job-id
  count, head switched, pin readback, cleanup and author identity. Identifiers stay out of the model payload; job ids
  print only in the terminal progress lines.

## 9. Companion repo `okf-connected-e2e` 0.2.0

- `okf-e2e run|agent [--live]` now runs the full path (`publish_connected`) by default. `--consume-only` keeps the
  PR #1 behaviour and is labelled as such in the banner.
- Banner: "Author/Publish (BigQuery) → Catalog discovery → pin → retrieval → access + revocation → receipt → consumer".
- Terminal progress prints each author job (`role job_id state`), then `READY`, `head from → to`, and the Catalog pin
  readback.
- Tool payload gains `publication` with no ids:
  - `authority: "BigQuery"`, `state`, `head_switched`;
  - `author_jobs`, `author_identity`;
  - `catalog_pin`, `consumed_matches`, `cleanup`.
- The answer is withheld unless `run_verdict == E2E_PUBLISH_CONNECTED`, or `E2E_CONNECTED` under `--consume-only`.
- `SPIKE_REF` is bumped to the spike commit containing this runner.

## 10. Tests (hermetic, no cloud)

`tests/test_publish_connected.py`:

- Full hermetic run → `E2E_PUBLISH_CONNECTED`:
  - states in order;
  - author jobs journaled before terminal;
  - the pin comes from rows;
  - the consumer pinned P in the owned dataset;
  - cleanup `COMPLETE`.
- Negative runs:
  - readback corruption → never `READY`, consume `NOT_RUN`, verdict not connected;
  - interruption before head → consume `NOT_RUN`, head unchanged, cleanup `COMPLETE`;
  - Catalog pin names another dataset → consumed `MISMATCH` → `E2E_BROKEN` (or the parser refuses `SCOPE_REFUSED` →
    `INCOMPLETE`, never connected);
  - cleanup cannot read back absence → `INCOMPLETE`;
  - author identity `UNBOUND` → `E2E_BROKEN`.
- Backward compatibility: the default `CatalogConfig` keeps the broker graph dataset `DATASET`; the existing connected
  tests pass unchanged.
