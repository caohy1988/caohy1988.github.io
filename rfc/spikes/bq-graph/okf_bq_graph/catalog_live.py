"""Slice B2 live glue (plan U5): a bounded live `CloudOps` adapter for `catalog_lifecycle.Lifecycle` (BigQuery + Dataplex
Catalog) and the owned-lifecycle experiment driver that runs the Catalog-seeded receipt chain against run-owned
resources, grades every case MET / WRONG / NOT_REACHED / BLOCKED, and cleans up with absence readback.

Everything the experiment mutates is derived from `LifecycleConfig` BEFORE any Catalog read (KTD6). The original KC
entry, the ten older demo entries and the original graph dataset/head are read only (snapshot + recheck).

Cases (in order; each chain invocation is a full `chain.run_chain(--live --seed-mode catalog)` against the owned
entry/dataset, writing its own run directory under `<run_dir>/chains/<label>/`):
  b2-control              fresh Catalog read of the owned P1 pin controls the chain (approved / sql-substitution / declaration-mismatch)
  historical-inflight     P2 published READY; the owned head is switched P1->P2 BETWEEN the chain's pin resolution and its payload
                          read (barrier on `chain.resolve_publication`); the request must still serve exactly P1
  historical-fresh        a new Catalog-P1 request after the switch: head observed = P2, P1 served exactly
  fail-stale-withdrawn    P1 WITHDRAWN in the owned dataset while Catalog still holds the P1 pin: FAIL_STALE, no content, no receipt
  missing-runtime-aspect  the runtime aspect removed from the owned entry (authored aspects stay): ASPECT_MISSING at seed
  wrong-publication-pin   owned entry re-pinned to a well-formed publication that was never retained: FAIL_STALE
  wrong-seed-pin          owned entry re-pinned to a concept that does not exist in P1: FAIL_STALE
  mixed-payload-injection live-backed CLIENT fault injection: the actual live P1 retrieval result is altered after BigQuery
                          returned it and before the payload guard (P2 section id mixed into the P1 computation; SQL bytes
                          changed under the unchanged P1 digest label). BigQuery did not return a torn publication.
  recovery-control        valid pin restored, fresh chain passes again
  cleanup                 originals re-read (must be unchanged), owned entry + dataset deleted with absence readback, every
                          lifecycle operation terminal
  job-identity            the follow-up audit: every job this run submitted -- lifecycle AND every child chain, graph-only
                          refusals included -- read back under its own (project, location, job id) for actual principal,
                          terminal state and error

A case is `MET` only when its boundary behaved correctly AND the identity evidence for that chain's jobs is complete;
`behaviour` keeps the boundary verdict separately, so an incomplete-evidence downgrade never erases a correct refusal.
`WRONG` is reserved for a boundary that was actually reached and answered incorrectly: an outage (an absent SDK, an
unreadable store) is `NOT_REACHED` with the blocker named. The experiment and the teardown hold separate budgets, and
`BudgetedCloud` refuses new mutations once the experiment cap is gone rather than only skipping the next chain.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import hashlib
import json
import re
import secrets
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

from . import BUNDLE_ID, LOCATION, PROJECT, SOURCE_PIN
from .catalog import CATALOG_API
from .catalog_lifecycle import FORBIDDEN_SQL, Lifecycle, LifecycleConfig, NotDispatched, ScopeViolation, prepare_derived_source
from .journal import Journal
from .publication import MAX_BYTES_BILLED

B2_VERSION = "okf_bq_graph.catalog_live/0.2.0"
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
ENTRY_LOCAL = "metrics/gross-margin"
CONCEPT_PATH = "metrics/gross-margin.md"
GRADES = ("MET", "WRONG", "NOT_REACHED", "BLOCKED")


class CatalogHttpError(RuntimeError):
    def __init__(self, status: Optional[int], text: str):
        super().__init__(f"HTTP {status}: {text[:300]}")
        self.status = status


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _jsonable(v: Any) -> Any:
    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.isoformat()
    if isinstance(v, bytes):
        return v.hex()
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v


# ----------------------------------------------------------------------------- live adapter
class LiveCloud:
    """`CloudOps` against real BigQuery (google-cloud-bigquery client) and Dataplex Catalog (google-auth AuthorizedSession).
    Every call is bounded by the caller's `timeout` (client `timeout`, no client-side retries: `retry=None`,
    `job_retry=None`; HTTP connect 10 s / read `timeout`, no redirects). Job-backed operations use the driver-chosen
    job id under (project, location) so `job_state` can read them back. `attempt_outcome` answers ONLY from this
    adapter's own bookkeeping of the create call it dispatched: a definitive 4xx/Conflict from the server is
    NOT_APPLIED, a 2xx is APPLIED, a timeout / transport failure / 5xx is unknown (None). NOTE: `QueryJob.result(timeout)`
    is a harness limit, not a hard bound on HTTP or result-page I/O (vault 2026-09-06 graph lifecycle correction)."""

    def __init__(self, client: Any, project: str = PROJECT, location: str = LOCATION, session: Any = None, api: str = CATALOG_API,
                 max_bytes_billed: int = MAX_BYTES_BILLED, retain: Optional[Callable[[str, bytes], Any]] = None,
                 labels: Optional[dict] = None, table_expiration_ms: int = 2 * 24 * 3600 * 1000):
        self.client, self.project, self.location, self._session, self.api = client, project, location, session, api
        self.max_bytes_billed, self.retain, self.table_expiration_ms = max_bytes_billed, retain, table_expiration_ms
        self.labels = labels or {"okf_spike": "bq_graph_20260905", "okf_role": "catalog-chain-b2"}
        self.attempts: dict[str, dict] = {}
        self.calls: list[dict] = []
        self._n = 0

    # -- BigQuery helpers
    def _ref(self, dataset: str) -> str:
        return f"{self.project}.{dataset}"

    @staticmethod
    def _ident(name: str) -> str:
        if not IDENT_RE.fullmatch(name):
            raise ValueError(f"unsafe identifier: {name!r}")
        return name

    def _job_config(self, role: str, params: Optional[list] = None) -> Any:
        from google.cloud import bigquery
        cfg = bigquery.QueryJobConfig(query_parameters=params or [], use_query_cache=False, maximum_bytes_billed=self.max_bytes_billed,
                                      labels=dict(self.labels, stage=role.replace("_", "-")[:63]))
        return cfg

    def _query(self, role: str, sql: str, params: list, job_id: str, timeout: float) -> tuple[list[dict], Any]:
        up = sql.upper()
        for bad in FORBIDDEN_SQL:
            if bad.upper() in up:
                raise ScopeViolation(f"forbidden statement on the relational-only path: {bad}")
        self.calls.append({"op": role, "job_id": job_id, "at": _now()})
        job = self.client.query(sql, job_config=self._job_config(role, params), location=self.location, job_id=job_id, project=self.project,
                                retry=None, job_retry=None, timeout=timeout)
        rows = [_jsonable(dict(r)) for r in job.result(timeout=timeout)]
        return rows, job

    @staticmethod
    def _scalar(name: str, value: Any, field_type: Optional[str] = None) -> Any:
        from google.cloud import bigquery
        if field_type is None:
            field_type = "BOOL" if isinstance(value, bool) else "INT64" if isinstance(value, int) else "STRING"
        if field_type == "TIMESTAMP" and isinstance(value, str):
            value = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return bigquery.ScalarQueryParameter(name, field_type, value)

    def _schema(self, dataset: str, table: str, timeout: float) -> Any:
        return self.client.get_table(f"{self._ref(dataset)}.{table}", retry=None, timeout=timeout)

    # -- CloudOps: datasets
    def get_dataset(self, dataset: str, timeout: float) -> Optional[dict]:
        from google.api_core.exceptions import NotFound
        self.calls.append({"op": "get_dataset", "target": dataset, "at": _now()})
        try:
            ds = self.client.get_dataset(self._ref(dataset), retry=None, timeout=timeout)
        except NotFound:
            return None
        return {"labels": dict(ds.labels or {}), "location": getattr(ds, "location", None), "dataset_id": getattr(ds, "dataset_id", dataset)}

    def create_dataset(self, dataset: str, location: str, labels: dict, attempt_id: str, timeout: float) -> dict:
        from google.api_core.exceptions import BadRequest, Conflict, Forbidden
        from google.cloud import bigquery
        ds = bigquery.Dataset(self._ref(dataset))
        ds.location = location
        ds.labels = dict(labels)
        ds.default_table_expiration_ms = self.table_expiration_ms
        ds.description = f"okf catalog-chain B2 run-owned dataset (attempt {attempt_id}); relational tables only; deleted by the run's cleanup"
        rec = self.attempts.setdefault(attempt_id, {"kind": "dataset", "name": dataset, "outcome": None, "dispatched_at": _now()})
        self.calls.append({"op": "create_dataset", "target": dataset, "attempt_id": attempt_id, "at": _now()})
        try:
            created = self.client.create_dataset(ds, exists_ok=False, retry=None, timeout=timeout)
        except (Conflict, BadRequest, Forbidden) as e:      # the server answered definitively: this attempt did not apply
            rec.update(outcome="NOT_APPLIED", error=f"{type(e).__name__}: {str(e)[:200]}")
            raise
        except Exception as e:  # noqa: BLE001 - timeout / transport / 5xx: unknown, never inferred from elapsed time
            rec.update(outcome=None, error=f"{type(e).__name__}: {str(e)[:200]}")
            raise
        rec.update(outcome="APPLIED", applied_at=_now())
        return {"dataset": getattr(created, "dataset_id", dataset), "location": getattr(created, "location", location)}

    def delete_dataset(self, dataset: str, timeout: float) -> dict:
        self.calls.append({"op": "delete_dataset", "target": dataset, "at": _now()})
        self.client.delete_dataset(self._ref(dataset), delete_contents=True, not_found_ok=False, retry=None, timeout=timeout)
        return {"deleted": dataset}

    # -- CloudOps: job-backed table operations
    def run_ddl(self, dataset: str, statement: str, job_id: str, timeout: float) -> dict:
        if f"`{self._ref(dataset)}." not in statement:
            raise ScopeViolation(f"DDL does not target the owned dataset {dataset}")
        _rows, job = self._query("run_ddl", statement, [], job_id, timeout)
        return {"job_id": job.job_id, "state": job.state}

    def load_rows(self, dataset: str, table: str, rows: list[dict], job_id: str, timeout: float) -> dict:
        from google.cloud import bigquery
        t = self._schema(dataset, self._ident(table), timeout)
        cfg = bigquery.LoadJobConfig(schema=t.schema, write_disposition="WRITE_APPEND", source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON)
        self.calls.append({"op": "load_rows", "job_id": job_id, "target": f"{dataset}.{table}", "rows": len(rows), "at": _now()})
        job = self.client.load_table_from_json([_jsonable(r) for r in rows], f"{self._ref(dataset)}.{table}", job_config=cfg, job_id=job_id,
                                               location=self.location, project=self.project, timeout=timeout)
        job.result(timeout=timeout)
        if job.error_result:
            raise RuntimeError(f"load job {job_id} finished with error: {job.error_result}")
        return {"job_id": job.job_id, "output_rows": getattr(job, "output_rows", None)}

    def select_rows(self, dataset: str, table: str, where: dict, job_id: str, timeout: float, exclude: tuple = ()) -> list[dict]:
        cols = "*" if not exclude else "* EXCEPT (" + ", ".join(self._ident(c) for c in exclude) + ")"
        conds, params = [], []
        for i, (k, v) in enumerate(sorted(where.items())):
            conds.append(f"{self._ident(k)} = @w{i}")
            params.append(self._scalar(f"w{i}", v))
        sql = f"SELECT {cols} FROM `{self._ref(dataset)}.{self._ident(table)}`" + (" WHERE " + " AND ".join(conds) if conds else "")
        rows, _job = self._query("select_rows", sql, params, job_id, timeout)
        return rows

    def insert_row(self, dataset: str, table: str, row: dict, job_id: str, timeout: float) -> dict:
        t = self._schema(dataset, self._ident(table), timeout)
        types = {f.name: (f.field_type, f.mode) for f in t.schema}
        from google.cloud import bigquery
        cols, params = [], []
        for k, v in row.items():
            self._ident(k)
            if k not in types:
                raise ValueError(f"column {k} not in {table}")
            ftype, mode = types[k]
            cols.append(k)
            if mode == "REPEATED":
                params.append(bigquery.ArrayQueryParameter(k, ftype, list(v or [])))
            else:
                params.append(self._scalar(k, v, {"INTEGER": "INT64", "BOOLEAN": "BOOL", "FLOAT": "FLOAT64"}.get(ftype, ftype)))
        sql = f"INSERT INTO `{self._ref(dataset)}.{table}` (" + ", ".join(cols) + ") VALUES (" + ", ".join(f"@{c}" for c in cols) + ")"
        _rows, job = self._query("insert_row", sql, params, job_id, timeout)
        return {"job_id": job.job_id, "rows": getattr(job, "num_dml_affected_rows", None)}

    def update_status(self, dataset: str, publication_id: str, status: str, job_id: str, timeout: float) -> dict:
        sql = f"UPDATE `{self._ref(dataset)}.publications` SET validation_status = @s WHERE publication_id = @p"
        _rows, job = self._query("update_status", sql, [self._scalar("s", status), self._scalar("p", publication_id)], job_id, timeout)
        return {"job_id": job.job_id, "rows": getattr(job, "num_dml_affected_rows", None)}

    def merge_head(self, dataset: str, bundle_id: str, publication_id: str, job_id: str, timeout: float) -> dict:
        full = self._ref(dataset)
        sql = f"""MERGE `{full}.active_publication` t USING (SELECT @b AS bundle_id, @p AS publication_id) s ON t.bundle_id = s.bundle_id
      WHEN MATCHED THEN UPDATE SET previous_publication_id = t.publication_id, publication_id = s.publication_id, switched_at = CURRENT_TIMESTAMP()
      WHEN NOT MATCHED THEN INSERT (bundle_id, publication_id, switched_at, previous_publication_id) VALUES (s.bundle_id, s.publication_id, CURRENT_TIMESTAMP(), NULL)"""
        _rows, job = self._query("merge_head", sql, [self._scalar("b", bundle_id), self._scalar("p", publication_id)], job_id, timeout)
        return {"job_id": job.job_id, "rows": getattr(job, "num_dml_affected_rows", None)}

    def job_state(self, job_id: str, timeout: float, project: Optional[str] = None, location: Optional[str] = None) -> Optional[dict]:
        """Read one job back under its OWN journaled reference. `project`/`location` default to this adapter's, but a
        child chain's jobs carry their own reference and must be read under it — reading a job under the wrong
        (project, location) returns NotFound, which is not evidence that the job does not exist."""
        from google.api_core.exceptions import NotFound
        proj, loc = project or self.project, location or self.location
        self.calls.append({"op": "job_state", "job_id": job_id, "project": proj, "location": loc, "at": _now()})
        try:
            job = self.client.get_job(job_id, project=proj, location=loc, retry=None, timeout=timeout)
        except NotFound:
            return None
        return {"state": job.state, "error": _jsonable(job.error_result), "user_email": getattr(job, "user_email", None),
                "project": proj, "location": loc}

    def cancel_job(self, job_id: str, timeout: float) -> dict:
        self.calls.append({"op": "cancel_job", "job_id": job_id, "at": _now()})
        self.client.cancel_job(job_id, project=self.project, location=self.location, retry=None, timeout=timeout)
        return {"cancel_requested": job_id}

    # -- Dataplex Catalog (HTTP)
    def _sess(self) -> Any:
        if self._session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession, Request
            creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            req = Request()

            def bounded(*a: Any, **kw: Any) -> Any:
                kw["timeout"] = 20
                return req(*a, **kw)
            self._session = AuthorizedSession(creds, auth_request=bounded, max_refresh_attempts=1)
        return self._session

    def _http(self, op: str, method: str, url: str, timeout: float, params: Optional[dict] = None, body: Optional[dict] = None) -> tuple[int, Any, bytes]:
        self._n += 1
        self.calls.append({"op": op, "method": method, "url": url, "params": params, "at": _now()})
        r = self._sess().request(method, url, params=params or {}, json=body, timeout=(10, timeout), allow_redirects=False)
        raw = r.content or b""
        if self.retain is not None:
            self.retain(f"{op}_{self._n:03d}_{r.status_code}", json.dumps({"method": method, "url": url, "params": params, "status": r.status_code,
                                                                          "body": _try_json(raw), "at": _now()}, indent=1, sort_keys=True).encode("utf-8"))
        return r.status_code, _try_json(raw), raw

    def get_entry(self, name: str, timeout: float) -> Optional[dict]:
        status, body, raw = self._http("get_entry", "GET", f"{self.api}{name}", timeout, params={"view": "ALL"})
        if status == 404:
            return None
        if status != 200 or not isinstance(body, dict):
            raise CatalogHttpError(status, raw.decode("utf-8", "replace"))
        return body

    def create_entry(self, name: str, body: dict, attempt_id: str, timeout: float) -> dict:
        if "/entries/" not in name:
            raise ValueError(f"not an entry name: {name}")
        group, entry_id = name.split("/entries/", 1)
        payload = {k: v for k, v in body.items() if k != "name"}
        rec = self.attempts.setdefault(attempt_id, {"kind": "entry", "name": name, "outcome": None, "dispatched_at": _now()})
        try:
            status, resp, raw = self._http("create_entry", "POST", f"{self.api}{group}/entries", timeout, params={"entryId": entry_id}, body=payload)
        except Exception as e:  # noqa: BLE001 - transport failure: unknown outcome
            rec.update(outcome=None, error=f"{type(e).__name__}: {str(e)[:200]}")
            raise
        if status == 200:
            rec.update(outcome="APPLIED", applied_at=_now())
            return resp if isinstance(resp, dict) else {}
        if 400 <= status < 500:
            rec.update(outcome="NOT_APPLIED", error=f"HTTP {status}")
        else:
            rec.update(outcome=None, error=f"HTTP {status}")
        raise CatalogHttpError(status, raw.decode("utf-8", "replace"))

    def attempt_outcome(self, kind: str, name: str, attempt_id: str, timeout: float) -> Optional[str]:
        rec = self.attempts.get(attempt_id)
        if not rec or rec.get("kind") != kind or rec.get("name") != name:
            return None
        return rec.get("outcome")

    def patch_entry(self, name: str, body: dict, aspect_keys: list[str], timeout: float) -> dict:
        """Explicit aspect keys only. Keys present in the body are upserted (`deleteMissingAspects=false`); keys listed
        but absent from the body are deleted with `deleteMissingAspects=true` scoped to exactly those keys (Dataplex
        entries.patch: aspects in `aspectKeys` absent from the request persist unless deleteMissingAspects is true)."""
        aspects = body.get("aspects") or {}
        present = [k for k in aspect_keys if k in aspects]
        missing = [k for k in aspect_keys if k not in aspects]
        out: dict[str, Any] = {"upserted": present, "deleted": missing}
        if present:
            payload = {"name": name, "aspects": {k: aspects[k] for k in present}}
            status, _resp, raw = self._http("patch_entry_upsert", "PATCH", f"{self.api}{name}", timeout,
                                            params={"updateMask": "aspects", "aspectKeys": present, "deleteMissingAspects": "false"}, body=payload)
            if status != 200:
                raise CatalogHttpError(status, raw.decode("utf-8", "replace"))
        if missing:
            payload = {"name": name, "aspects": {}}
            status, _resp, raw = self._http("patch_entry_delete", "PATCH", f"{self.api}{name}", timeout,
                                            params={"updateMask": "aspects", "aspectKeys": missing, "deleteMissingAspects": "true"}, body=payload)
            if status != 200:
                raise CatalogHttpError(status, raw.decode("utf-8", "replace"))
        return out

    def delete_entry(self, name: str, timeout: float) -> dict:
        status, _resp, raw = self._http("delete_entry", "DELETE", f"{self.api}{name}", timeout)
        if status != 200:
            raise CatalogHttpError(status, raw.decode("utf-8", "replace"))
        return {"deleted": name}


def _accepts_ref(fn: Any) -> bool:
    """Older `CloudOps` adapters take `job_state(job_id, timeout)` only; the audit reads a child chain's jobs under
    their own reference where the adapter supports it and records the missing reference where it does not."""
    import inspect
    try:
        return "project" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def _try_json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8")) if raw else None
    except (UnicodeDecodeError, ValueError):
        return None


# ----------------------------------------------------------------------------- budget
def identity_gate(all_rows: list[dict], unresolved: list[dict]) -> dict:
    """The B2 identity criterion, in one place so the in-run audit and any follow-up audit apply the SAME rule:
    every dispatched job read back under its own reference, terminal, carrying exactly one known principal, with no
    unresolved child job. Anything unknown leaves the gate INCOMPLETE - it is never assumed."""
    # a never-dispatched id is listed but carries no identity requirement: there is no job on the server to read
    rows = [j for j in all_rows if j.get("dispatched", True)]
    not_dispatched = [j["job_id"] for j in all_rows if not j.get("dispatched", True)]
    missing_ref = [j["job_id"] for j in rows if not (j.get("project") and j.get("location"))]
    unread = [j["job_id"] for j in rows if j.get("read") != "OK"]
    non_terminal = [j["job_id"] for j in rows if j.get("read") == "OK" and j.get("state") != "DONE"]
    errored = [j["job_id"] for j in rows if j.get("read") == "OK" and j.get("error")]
    no_identity = [j["job_id"] for j in rows if j.get("read") == "OK" and not j.get("user_email")]
    principals = sorted({j["user_email"] for j in rows if j.get("user_email")})
    reasons = []
    if missing_ref:
        reasons.append(f"{len(missing_ref)} job(s) without a complete (project, location) reference")
    if unread:
        reasons.append(f"{len(unread)} job(s) not read back")
    if non_terminal:
        reasons.append(f"{len(non_terminal)} job(s) not DONE")
    if no_identity:
        reasons.append(f"{len(no_identity)} job(s) with no principal: equality of absent identities proves nothing")
    if len(principals) > 1:
        reasons.append(f"{len(principals)} distinct principals: {principals}")
    if unresolved:
        reasons.append(f"{len(unresolved)} unresolved child-chain job(s)")
    # An empty job set is COMPLETE, not incomplete: a boundary that refused before submitting anything (the
    # missing-aspect case refuses at seed) has no job whose identity could be unknown. What that case must
    # still prove is its BEHAVIOUR, which `grade_refusal` checks independently.
    return {"status": "COMPLETE" if not reasons else "INCOMPLETE",
            "jobs": len(rows), "principals": principals, "reasons": reasons,
            "note": None if rows else "no job was submitted at this boundary",
            "missing_reference": missing_ref, "not_read_back": unread, "not_terminal": non_terminal,
            "errored": errored, "without_principal": no_identity, "not_dispatched": not_dispatched,
            "unresolved_child_jobs": unresolved}


class BudgetExceeded(NotDispatched):
    """The phase deadline passed before this operation was dispatched. Nothing was sent, so the journal closes the
    entry NOT_SUBMITTED instead of leaving an unresolved UNKNOWN that would block a clean teardown."""


# every CloudOps call the driver's phase budget bounds; the ones that change cloud state are refused outright once the
# experiment deadline passes, so a cap expiry cannot leave new experimental mutations behind (Astra PR42 P2 #1).
MUTATING_OPS = frozenset({"create_dataset", "delete_dataset", "run_ddl", "load_rows", "insert_row", "update_status",
                          "merge_head", "create_entry", "patch_entry", "delete_entry"})
READ_OPS = frozenset({"get_dataset", "select_rows", "job_state", "cancel_job", "get_entry", "attempt_outcome"})
CLOUD_OPS = MUTATING_OPS | READ_OPS


class BudgetedCloud:
    """A `CloudOps` façade that enforces the driver's phase deadline on the operations themselves, not only between
    cases. Two things happen on every call:

      * **Refusal after expiry.** Once the phase deadline has passed no further call is dispatched — `BudgetExceeded`
        is raised before anything reaches the network. The experiment phase therefore cannot advance a head, withdraw a
        publication or patch an entry after its cap (the defect Astra's cap probe reproduced).
      * **Deadline propagation.** The caller's `timeout` is clamped to the time actually left in the phase, so one
        blocking call cannot outlive the budget it was issued under.

    `open_phase` starts a new, separately bounded phase. Cleanup runs in its own phase with its own deadline, so an
    exhausted experiment budget never prevents teardown — the deletes and their absence readbacks still get a bounded
    allowance of their own."""

    def __init__(self, inner: Any, clock: Callable[[], float], budget_s: float, phase: str = "experiment"):
        object.__setattr__(self, "inner", inner)
        object.__setattr__(self, "clock", clock)
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "deadline", clock() + budget_s)
        object.__setattr__(self, "refused", [])

    def open_phase(self, phase: str, budget_s: float) -> dict:
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "deadline", self.clock() + budget_s)
        return {"phase": phase, "budget_s": budget_s, "opens_at": _now()}

    def remaining(self) -> float:
        return round(self.deadline - self.clock(), 3)

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self.inner, name)
        if name not in CLOUD_OPS or not callable(attr):
            return attr

        def bounded(*a: Any, **kw: Any) -> Any:
            left = self.remaining()
            if left <= 0:
                rec = {"op": name, "phase": self.phase, "mutates": name in MUTATING_OPS, "at": _now(), "over_by_s": -left}
                self.refused.append(rec)
                raise BudgetExceeded(f"{self.phase} budget exhausted {-left}s ago: {name} was not dispatched")
            if isinstance(kw.get("timeout"), (int, float)):
                kw["timeout"] = min(kw["timeout"], left)      # a blocking call never outlives the phase it was issued under
            return attr(*a, **kw)
        return bounded


# ----------------------------------------------------------------------------- experiment driver
@contextlib.contextmanager
def _patched(module: Any, name: str, fn: Any):
    real = getattr(module, name)
    setattr(module, name, fn)
    try:
        yield real
    finally:
        setattr(module, name, real)


def _authored_from(entry: Optional[dict], aspect_key: str) -> dict:
    """Authored (non-runtime) aspects of the original entry, copied verbatim as the owned entry's authored aspects."""
    out = {}
    for k, v in ((entry or {}).get("aspects") or {}).items():
        if k != aspect_key and isinstance(v, dict) and isinstance(v.get("data"), dict):
            out[k] = v["data"]
    return out


class B2Experiment:
    """Owns one run directory; every chain invocation and lifecycle mutation is recorded there."""

    def __init__(self, out_root: str, cfg: LifecycleConfig, cloud: Any, bq_client: Any, reader_factory: Callable[[], Any], sdk_root: str,
                 acme_root: str, chain_runner: Callable[..., dict], chain_module: Any = None, wall_cap_s: float = 1200.0,
                 clock: Callable[[], float] = time.monotonic, redact: Optional[Callable[[Any], Any]] = None,
                 cleanup_cap_s: float = 300.0, chain_min_s: float = 120.0):
        self.cfg, self.bq, self.reader_factory, self.sdk_root, self.acme_root = cfg, bq_client, reader_factory, sdk_root, acme_root
        self.chain_runner, self.wall_cap_s, self.clock = chain_runner, wall_cap_s, clock
        self.cleanup_cap_s, self.chain_min_s = cleanup_cap_s, chain_min_s
        if chain_module is None:
            from . import chain as chain_module
        self.chain_module = chain_module
        self.redact = redact or (lambda x: x)
        self.run_dir = Path(out_root) / cfg.run_id
        self.run_dir.mkdir(parents=True, exist_ok=False)      # KTD5: the run-owned directory exists before any external operation
        self.journal = Journal(self.run_dir, cfg.run_id)
        if getattr(cloud, "retain", None) is None and hasattr(cloud, "retain"):
            cloud.retain = lambda name, raw: self.journal.retain(name, raw, subdir="catalog_ops")
        # the lifecycle only ever sees the budgeted façade: its deadline bounds the operations, not just the gaps between cases
        self.raw_cloud = cloud
        self.cloud = BudgetedCloud(cloud, clock, wall_cap_s, phase="experiment")
        self.life = Lifecycle(cfg, self.cloud, self.journal)
        self.t0 = self.clock()
        self.summary: dict[str, Any] = {"b2": B2_VERSION, "run_id": cfg.run_id, "run_dir": str(self.run_dir), "started_at": _now(),
                                        "allowlist": cfg.allowlist(), "invocation_id": self.life.invocation_id, "owner_stamp": self.life.owner_stamp,
                                        "budget": {"wall_cap_s": wall_cap_s, "max_bytes_billed_per_select": MAX_BYTES_BILLED,
                                                   "embeddings": False, "reservations": False, "iam_changes": False, "graph_ddl": False,
                                                   "sdk_subprocess": "chain.run_receipt, 900 s per invocation, at most 2 per full chain (approved, sql-substitution)",
                                                   "cloud_timeout_s": cfg.timeout_s},
                                        "cases": [], "steps": [], "chains": {}, "publications": {}, "verdict": None}
        self.summary["budget"].update(cleanup_cap_s=cleanup_cap_s, chain_min_s=chain_min_s)
        self.P1: Optional[str] = None
        self.P2: Optional[str] = None
        self.p2_projection: Optional[dict] = None
        self.blocked_reason: Optional[str] = None
        self.chain_jobs: dict[str, list[dict]] = {}          # chain label -> full (project, location, job_id) references it submitted
        self.chain_unresolved: dict[str, list[dict]] = {}

    # -- bookkeeping
    def _elapsed(self) -> float:
        return round(self.clock() - self.t0, 3)

    def _step(self, name: str, **rec: Any) -> dict:
        r = {"step": name, "at": _now(), "elapsed_s": self._elapsed(), **rec}
        self.summary["steps"].append(_jsonable(r))
        self.journal.note("b2_step", **_jsonable(r))
        self._flush()
        return r

    def _case(self, name: str, gate: str, expected: str, status: str, chain_label: Optional[str] = None, **rec: Any) -> dict:
        """`status` is the case's BEHAVIOUR at its boundary. It can still be downgraded once `_job_audit` has run:
        a correct refusal whose job identities were never established is not a complete result (Astra PR42 P1). The
        behaviour verdict is preserved separately so the downgrade never erases what the boundary actually did."""
        assert status in GRADES, status
        c = {"case": name, "origin_gate": gate, "expected": expected, "status": status, "behaviour": status,
             "chain_label": chain_label, "at": _now(), "elapsed_s": self._elapsed(), **rec}
        self.summary["cases"].append(_jsonable(c))
        self.journal.note("b2_case", **_jsonable(c))
        self._flush()
        return c

    def _flush(self) -> None:
        text = json.dumps(self.redact(_jsonable(self.summary)), indent=1, sort_keys=True, default=str) + "\n"
        tmp = self.run_dir / ".b2_summary.json.tmp"
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self.run_dir / "b2_summary.json")

    def _over_budget(self) -> Optional[str]:
        if self.blocked_reason:
            return self.blocked_reason
        if self._elapsed() > self.wall_cap_s:
            return f"wall cap {self.wall_cap_s}s exceeded at {self._elapsed()}s"
        return None

    def _guard(self, what: str) -> None:
        """Refuse to BEGIN new experimental work once the cap is gone. `BudgetedCloud` refuses the individual
        operations too; this stops a case before it has half-mutated the owned resources."""
        over = self._over_budget()
        if over:
            raise BudgetExceeded(f"{what} not started: {over}")

    def _chain_budget(self) -> Optional[str]:
        """`run_chain` takes no deadline, so the driver cannot interrupt one that is already running. What it can do is
        refuse to START a chain that cannot plausibly finish inside the cap (`chain_min_s`), and bound every lifecycle
        operation around it through `BudgetedCloud`. This limitation is recorded rather than papered over."""
        left = round(self.wall_cap_s - self._elapsed(), 3)
        if left < self.chain_min_s:
            return f"only {left}s of the {self.wall_cap_s}s cap left; a chain needs at least {self.chain_min_s}s"
        return None

    # -- one chain invocation against the owned entry/dataset
    def _chain(self, label: str, entry_local: str = ENTRY_LOCAL, hooks: Optional[dict] = None) -> dict:
        cfg = self.cfg.catalog_config(entry_local)
        out_dir = self.run_dir / "chains" / label
        out_dir.mkdir(parents=True, exist_ok=True)
        clients = {"engine": "fallback", "bq": self.bq, "ds": cfg.runtime_dataset}
        self.journal.note("chain_started", label=label, entry=cfg.entry, dataset=cfg.runtime_dataset, hooks=sorted(hooks or {}))
        with contextlib.ExitStack() as stack:
            for name, fn in (hooks or {}).items():
                stack.enter_context(_patched(self.chain_module, name, fn))
            out = self.chain_runner(engine="fallback", live=True, sdk_root=self.sdk_root, out_dir=str(out_dir), clients=clients, acme_root=self.acme_root,
                                    seed_mode="catalog", catalog_reader=self.reader_factory(), catalog_cfg=cfg)
        digest = {"verdict": out.get("verdict"), "broken_at": out.get("broken_at"), "run_dir": out.get("run_dir"), "seed_mode": (out.get("seed") or {}).get("mode"),
                  "seed_status": (out.get("seed") or {}).get("status"), "entry": (out.get("seed") or {}).get("entry") or (out.get("catalog") or {}).get("entry"),
                  "publication": {k: (out.get("publication") or {}).get(k) for k in ("status", "publication_id", "reasons", "head")},
                  "store_dataset": (out.get("store") or {}).get("dataset"), "graph_publication": (out.get("graph_publication") or {}).get("publication_id"),
                  "cases": {c["case"]: {"payload": (c.get("payload") or {}).get("status"), "bind": (c.get("bind") or {}).get("status"),
                                        "receipt_invoked": bool((c.get("receipt") or {}).get("invoked")), "consume": (c.get("consume") or {}).get("decision"),
                                        "acceptance": (c.get("acceptance") or {}).get("status")} for c in out.get("cases", [])},
                  "same_requester": (out.get("same_requester") or {}).get("status"), "unresolved_jobs": (out.get("evidence") or {}).get("unresolved_jobs"),
                  "graph_jobs": len((out.get("job_inventory") or {}).get("graph", [])), "receipt_jobs": (out.get("job_inventory") or {}).get("receipt")}
        self.chain_jobs[label] = self._chain_job_refs(label, out)
        unresolved = list((out.get("job_inventory") or {}).get("unresolved") or [])
        if not unresolved:      # an early refusal has no job_inventory: fall back to the chain journal's own entries
            unresolved = [{"role": e.get("role"), "job_id": e.get("job_id"), "state": e.get("state")}
                          for e in (out.get("journal") or {}).get("jobs") or [] if not e.get("terminal")]
        self.chain_unresolved[label] = unresolved
        digest["job_refs"] = len(self.chain_jobs[label])
        self.summary["chains"][label] = _jsonable(digest)
        self.journal.note("chain_finished", label=label, **_jsonable(digest))
        self._flush()
        return out

    @staticmethod
    def _chain_job_refs(label: str, out: dict) -> list[dict]:
        """Every job a child chain submitted, as a FULL `(project, location, job_id)` reference. Graph-leg ids and their
        references come from the chain's journal-backed inventory; receipt-leg jobs carry their own reference on the
        case record (the flattened `job_inventory.receipt` list keeps only ids). A chain that refused early submits
        graph jobs and no receipt job at all — those still need identity evidence, which is exactly the gap the chain's
        own `same_requester` cannot close because it exits when either leg is empty."""
        ji = out.get("job_inventory") or {}
        refs, rows, seen = ji.get("refs") or {}, [], set()
        # A chain that refuses early returns through `_broken()`, which never builds `job_inventory` at all — yet those
        # runs DID submit pin-resolution / seed-visibility / head-observation jobs. Their references live only in the
        # chain's own journal, so the audit starts there: an invisible job is the worst kind of missing evidence.
        for e in (out.get("journal") or {}).get("jobs") or []:
            if e.get("job_id") and e["job_id"] not in seen:
                seen.add(e["job_id"])
                rows.append({"source": f"chain:{label}", "leg": "graph", "role": e.get("role"), "job_id": e["job_id"],
                             "project": e.get("project"), "location": e.get("location"), "journal_state": e.get("state"),
                             "dispatched": e.get("state") != "NOT_SUBMITTED"})
        for jid in ji.get("graph") or []:
            if jid and jid not in seen:
                seen.add(jid)
                r = refs.get(jid) or {}
                rows.append({"source": f"chain:{label}", "leg": "graph", "job_id": jid, "project": r.get("project"), "location": r.get("location")})
        for c in out.get("cases", []) or []:
            rec = c.get("receipt") or {}
            job = (rec.get("receipt") or {}).get("job") if rec.get("invoked") else None
            if job and job.get("job_id") and job["job_id"] not in seen:
                seen.add(job["job_id"])
                rows.append({"source": f"chain:{label}", "leg": "receipt", "case": c.get("case"), "job_id": job["job_id"],
                             "project": job.get("project"), "location": job.get("location")})
        return rows

    def _chain_or_error(self, label: str, **kw: Any) -> tuple[Optional[dict], Optional[str]]:
        over = self._over_budget() or self._chain_budget()
        if over:
            self.summary["chains"][label] = {"error": f"not started: {over}"}
            self.journal.note("chain_skipped", label=label, reason=over)
            return None, f"not started: {over}"
        try:
            return self._chain(label, **kw), None
        except BudgetExceeded as e:
            self.summary["chains"][label] = {"error": f"budget: {e}"}
            self.journal.note("chain_budget_exceeded", label=label, error=str(e))
            raise
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:300]}"
            self.summary["chains"][label] = {"error": err}
            self.journal.note("chain_error", label=label, error=err)
            return None, err

    # -- graders (pure)
    @staticmethod
    def blocker(out: dict) -> Optional[str]:
        """The reached-stage blocker, if this chain never got to the boundary the case is about.

        A stage that returned `ERROR` is an OUTAGE — an absent SDK checkout, an unreadable store, a transport failure —
        not a boundary that behaved incorrectly. `WRONG` must stay reserved for a boundary that was actually reached and
        got the wrong answer, so a missing prerequisite grades `NOT_REACHED` with the blocker named and leaves the later
        cases `BLOCKED` (Astra PR42 P2 #2). A typed refusal such as `FAIL_STALE` is NOT an error: it is a reached
        boundary, and stays gradeable."""
        if out.get("verdict") == "CHAIN_INCOMPLETE":
            return f"chain incomplete at {out.get('broken_at')}"
        at = out.get("broken_at")
        rec = out.get(at) if isinstance(out.get(at), dict) else None
        if rec and rec.get("status") == "ERROR":
            return f"{at} unavailable: {str(rec.get('error'))[:200]}"
        return None

    @staticmethod
    def grade_connected(out: dict, cfg: Any, served: str, expected_head: Optional[str]) -> tuple[str, list[str]]:
        """MET only when the fresh live read controlled the chain end to end on the owned resources."""
        failed = []
        seed, pub = out.get("seed") or {}, out.get("publication") or {}
        if seed.get("mode") != "catalog":
            failed.append(f"seed.mode {seed.get('mode')} != catalog")
        if seed.get("entry") != cfg.entry and (out.get("catalog") or {}).get("entry") != cfg.entry:
            failed.append("seed entry is not the owned entry")
        if (out.get("store") or {}).get("dataset") != cfg.runtime_dataset:
            failed.append(f"store dataset {(out.get('store') or {}).get('dataset')} != owned {cfg.runtime_dataset}")
        if pub.get("status") != "OK" or pub.get("publication_id") != served:
            failed.append(f"publication {pub.get('status')} {pub.get('publication_id')} != OK {served}")
        if (out.get("graph_publication") or {}).get("publication_id") != served:
            failed.append("graph_publication is not the requested pin")
        head = (pub.get("head") or {}).get("publication_id")
        if expected_head is not None and head != expected_head:
            failed.append(f"observed head {head} != expected {expected_head}")
        cases = {c["case"]: c for c in out.get("cases", [])}
        for name in ("approved", "sql-substitution", "declaration-mismatch"):
            c = cases.get(name)
            if c is None:
                failed.append(f"case {name} missing")
            elif (c.get("acceptance") or {}).get("status") != "MET":
                failed.append(f"case {name} acceptance {(c.get('acceptance') or {}).get('status')}")
            elif (c.get("payload") or {}).get("status") != "CONSISTENT":
                failed.append(f"case {name} payload {(c.get('payload') or {}).get('status')}")
        if out.get("verdict") != "CHAIN_CONNECTED":
            failed.append(f"verdict {out.get('verdict')} at {out.get('broken_at')}")
        if failed:
            blocker = B2Experiment.blocker(out)
            if blocker:
                return "NOT_REACHED", [f"BLOCKER {blocker}"] + failed
            return "WRONG", failed
        return "MET", []

    @staticmethod
    def grade_refusal(out: dict, stage: str, status: str, reason_prefix: Optional[str] = None) -> tuple[str, list[str]]:
        """MET when the run refused at exactly `stage` with `status`, disclosed no case content and invoked no receipt."""
        failed = []
        if out.get("verdict") != "CHAIN_BROKEN" or out.get("broken_at") != stage:
            failed.append(f"verdict {out.get('verdict')} broken_at {out.get('broken_at')} != CHAIN_BROKEN at {stage}")
        rec = out.get(stage) or {}
        if rec.get("status") != status:
            failed.append(f"{stage}.status {rec.get('status')} != {status}")
        if reason_prefix and not any(str(r).startswith(reason_prefix) for r in (rec.get("reasons") or [])):
            failed.append(f"{stage}.reasons {rec.get('reasons')} lack {reason_prefix}")
        if out.get("cases"):
            failed.append(f"{len(out['cases'])} case(s) ran after the refusal")
        if any((c.get("receipt") or {}).get("invoked") for c in out.get("cases", [])):
            failed.append("a receipt was invoked")
        if failed:
            blocker = B2Experiment.blocker(out)
            if blocker:
                return "NOT_REACHED", [f"BLOCKER {blocker}"] + failed
            return "WRONG", failed
        return "MET", []

    @staticmethod
    def grade_injection(out: dict, tampered: tuple = ("approved", "sql-substitution")) -> tuple[str, list[str]]:
        """MET when every tampered case was refused by the payload guard BEFORE the SDK (payload INCONSISTENT, NOT_BOUND,
        no receipt) and the untouched case stayed CONSISTENT; the chain itself must grade the tampered cases WRONG."""
        failed = []
        cases = {c["case"]: c for c in out.get("cases", [])}
        for name in tampered:
            c = cases.get(name)
            if c is None:
                failed.append(f"{name} did not run"); continue
            if (c.get("payload") or {}).get("status") != "INCONSISTENT":
                failed.append(f"{name} payload {(c.get('payload') or {}).get('status')} != INCONSISTENT")
            if (c.get("bind") or {}).get("status") != "NOT_BOUND":
                failed.append(f"{name} bind {(c.get('bind') or {}).get('status')} != NOT_BOUND")
            if (c.get("receipt") or {}).get("invoked"):
                failed.append(f"{name} receipt invoked after a torn payload")
            if (c.get("consume") or {}).get("decision") != "REFUSED":
                failed.append(f"{name} consume {(c.get('consume') or {}).get('decision')} != REFUSED")
        for name, c in cases.items():
            if name not in tampered and (c.get("payload") or {}).get("status") != "CONSISTENT":
                failed.append(f"untouched {name} payload {(c.get('payload') or {}).get('status')}")
        if out.get("verdict") != "CHAIN_BROKEN":
            failed.append(f"verdict {out.get('verdict')} != CHAIN_BROKEN (the chain must report the torn payload)")
        if failed:
            blocker = B2Experiment.blocker(out)
            if blocker or not cases:
                return "NOT_REACHED", ([f"BLOCKER {blocker}"] if blocker else ["BLOCKER no case ran"]) + failed
            return "WRONG", failed
        return "MET", []

    # -- the experiment
    def run(self) -> dict:
        try:
            self._setup()
            self._control()
            self._historical()
            self._fail_stale()
            self._missing_aspect()
            self._wrong_pins()
            self._mixed_payload()
            self._recovery()
        except BudgetExceeded as e:      # the cap stops NEW experimental work; teardown gets its own budget below
            self.blocked_reason = self.blocked_reason or f"BudgetExceeded: {e}"
            self._step("experiment_budget_exhausted", error=str(e), refused_operations=list(self.cloud.refused))
        except Exception as e:  # noqa: BLE001 - every remaining case is BLOCKED with the reason; cleanup still runs
            self.blocked_reason = self.blocked_reason or f"{type(e).__name__}: {str(e)[:300]}"
            self._step("experiment_aborted", error=self.blocked_reason)
        finally:
            # a separately bounded teardown phase: an exhausted experiment budget must never block cleanup
            self._step("cleanup_phase_opened", **self.cloud.open_phase("cleanup", self.cleanup_cap_s))
            self._cleanup()
        done = {c["case"] for c in self.summary["cases"]}
        for name, gate in (("b2-control", "R1/R2"), ("historical-inflight", "R3"), ("historical-fresh", "R3"), ("fail-stale-withdrawn", "R3/R6"),
                           ("missing-runtime-aspect", "R1/R6"), ("wrong-publication-pin", "R6"), ("wrong-seed-pin", "R6"),
                           ("mixed-payload-injection", "R4"), ("recovery-control", "R6"), ("cleanup", "R7/R8")):
            if name not in done:
                self._case(name, gate, "-", "BLOCKED", reason=self.blocked_reason or "not reached (earlier case blocked the sequence)")
        # the follow-up audit runs LAST, so it covers the teardown jobs too, and inside the cleanup budget
        try:
            audit = self._job_audit()
        except Exception as e:  # noqa: BLE001 - an audit that cannot run leaves every identity gate incomplete
            audit = {"overall": {"status": "INCOMPLETE", "reasons": [f"audit failed: {type(e).__name__}: {str(e)[:200]}"], "jobs": 0, "principals": []},
                     "lifecycle": {"status": "INCOMPLETE", "reasons": ["audit failed"], "jobs": 0, "principals": []}, "by_chain": {}, "counts": {}}
        self.summary["job_identity"] = {k: v for k, v in audit.items() if k != "jobs"}
        self._apply_identity_gate(audit)
        self._case("job-identity", "R5", "every lifecycle and child-chain job read back under its own reference: terminal, one principal",
                   "MET" if audit["overall"]["status"] == "COMPLETE" else "NOT_REACHED",
                   failed=audit["overall"]["reasons"], counts=audit.get("counts"), principals=audit["overall"]["principals"],
                   retained=audit.get("retained"))
        statuses = [c["status"] for c in self.summary["cases"]]
        self.summary["verdict"] = ("B2_ALL_MET" if all(s == "MET" for s in statuses) else "B2_WRONG" if "WRONG" in statuses else "B2_INCOMPLETE")
        self.summary["finished_at"] = _now()
        self.summary["elapsed_s"] = self._elapsed()
        self.summary["lifecycle_journal"] = self.journal.summary()
        self.summary["budget"]["refused_after_cap"] = list(self.cloud.refused)
        self.summary["publications"] = {"P1": self.P1, "P2": self.P2}
        self._flush()
        (self.run_dir / "b2_summary.md").write_text(self.markdown(), encoding="utf-8")
        return self.summary

    def _setup(self) -> None:
        self._guard("setup")
        cfg, life = self.cfg, self.life
        # 0. originals (read only), authored aspects copied from the original entry
        snap = life.snapshot_originals()
        self._step("snapshot_originals", **snap)
        if not snap["entry_present"] or snap["head"] is None:
            self.blocked_reason = "original entry or original head not readable: the prerequisite is not established"
            raise RuntimeError(self.blocked_reason)
        orig = life._op("read_original_authored", "GET original entry for authored aspect copy (read only)", life.cloud.get_entry, cfg.original_entry, target=cfg.original_entry)
        self.authored = _authored_from(orig, cfg.aspect_key)
        # 1. P1 from the clean pinned source (verified: git HEAD == pin, bundle tree clean)
        from .publication import _git
        from .compile import compile_bundle
        head, dirty = _git(self.acme_root, "rev-parse", "HEAD"), _git(self.acme_root, "status", "--porcelain", "--", ".")
        src = {"git_head": head, "matches_pin": head == SOURCE_PIN, "bundle_tree_clean": dirty == ""}
        self._step("trusted_source", **src)
        if not (src["matches_pin"] and src["bundle_tree_clean"]):
            self.blocked_reason = f"source checkout not at the clean pin: {src}"
            raise RuntimeError(self.blocked_reason)
        p1 = compile_bundle(self.acme_root, cfg.bundle_id, SOURCE_PIN)
        self.P1 = p1["publication_id"]
        # 2. owned dataset + P1 READY + head + owned pin
        self._step("provision", **life.provision())
        pub = life.publish_relational(p1)
        self._step("publish_p1", publication_id=self.P1, state=pub["state"], readback=pub.get("readback"))
        if pub["state"] != "READY":
            self.blocked_reason = f"P1 readback {pub['state']}: no valid control publication"
            raise RuntimeError(self.blocked_reason)
        self._step("head_p1", **life.advance_head(self.P1))
        pin = life.write_pin(ENTRY_LOCAL, self.P1, CONCEPT_PATH, authored_aspects=self.authored)
        self._step("write_pin_p1", **pin)
        if pin["readback_status"] != "OK" or not pin["authored_aspects_present"]:
            self.blocked_reason = f"owned pin readback {pin['readback_status']} authored_present={pin['authored_aspects_present']}"
            raise RuntimeError(self.blocked_reason)
        # P2 from a retained local derivation (one non-computation policy file changed), READY but NOT head yet
        d = prepare_derived_source(self.acme_root, SOURCE_PIN, str(self.run_dir / "derived"))
        self.p2_projection, derivation = d["projection"], d["derivation"]
        self.P2 = self.p2_projection["publication_id"]
        pub2 = life.publish_relational(self.p2_projection, derivation=derivation)
        self._step("publish_p2", publication_id=self.P2, state=pub2["state"], derivation=derivation, readback=pub2.get("readback"), head_after=life.read_head())
        if pub2["state"] != "READY":
            self.blocked_reason = f"P2 readback {pub2['state']}"
            raise RuntimeError(self.blocked_reason)

    def _control(self) -> None:
        self._guard("b2-control")
        cfgc = self.cfg.catalog_config(ENTRY_LOCAL)
        out, err = self._chain_or_error("b2-control")
        if out is None:
            self._case("b2-control", "R1/R2", "CHAIN_CONNECTED on the owned entry/dataset with head = P1", "NOT_REACHED", error=err)
            self.blocked_reason = f"control chain did not run: {err}"
            raise RuntimeError(self.blocked_reason)
        status, failed = self.grade_connected(out, cfgc, self.P1, self.P1)
        self._case("b2-control", "R1/R2", "CHAIN_CONNECTED on the owned entry/dataset with head = P1", status, chain_label="b2-control",
                   failed=failed, chain=self.summary["chains"]["b2-control"])
        if status != "MET":
            blocker = self.blocker(out)
            self.blocked_reason = (f"control blocked: {blocker}" if blocker else f"control not MET: {failed}")
            raise RuntimeError(self.blocked_reason)

    def _historical(self) -> None:
        self._guard("historical-inflight")
        cfgc, life = self.cfg.catalog_config(ENTRY_LOCAL), self.life
        real = self.chain_module.resolve_publication
        barrier: dict[str, Any] = {"fired": False}

        def resolve_then_switch(store: Any, pin: Any) -> dict:
            res = real(store, pin)
            barrier.update(fired=True, resolution=res.get("status"), head_at_resolution=(res.get("head") or {}).get("publication_id"))
            if res.get("status") == "OK" and not barrier.get("switched"):
                barrier["switch"] = life.advance_head(self.P2)          # the owned head moves BEFORE this request reads its payload
                barrier["switched"] = True
                barrier["head_after_switch"] = life.read_head()
            return res
        out, err = self._chain_or_error("historical-inflight", hooks={"resolve_publication": resolve_then_switch})
        self._step("historical_barrier", **barrier)
        if out is None:
            self._case("historical-inflight", "R3", "P1 served exactly while the head moved to P2 mid-request", "NOT_REACHED", error=err, barrier=barrier)
        elif not barrier.get("switched") or (barrier.get("switch") or {}).get("state") != "SWITCHED":
            self._case("historical-inflight", "R3", "P1 served exactly while the head moved to P2 mid-request", "NOT_REACHED",
                       reason="the head switch did not happen inside the request", barrier=barrier)
        else:
            status, failed = self.grade_connected(out, cfgc, self.P1, self.P1)   # head observed at resolution time was P1
            note = None
            if status != "MET" and (out.get("publication") or {}).get("status") == "FAIL_STALE":
                note = "historical serving unavailable: FAIL_STALE is a safe refusal, not a retained serve"
            self._case("historical-inflight", "R3", "P1 served exactly while the head moved to P2 mid-request", status, chain_label="historical-inflight",
                       failed=failed, note=note, barrier=barrier, chain=self.summary["chains"]["historical-inflight"])
        # a fresh Catalog-P1 request after the switch
        self._guard("historical-fresh")
        head_now = life.read_head()
        out2, err2 = self._chain_or_error("historical-fresh")
        if out2 is None:
            self._case("historical-fresh", "R3", "fresh P1 request after the switch: head observed = P2, P1 served exactly", "NOT_REACHED", error=err2, head=head_now)
        else:
            status, failed = self.grade_connected(out2, cfgc, self.P1, self.P2)
            self._case("historical-fresh", "R3", "fresh P1 request after the switch: head observed = P2, P1 served exactly", status,
                       chain_label="historical-fresh", failed=failed, head=head_now, chain=self.summary["chains"]["historical-fresh"])

    def _fail_stale(self) -> None:
        self._guard("fail-stale-withdrawn")
        life = self.life
        w = life.withdraw(self.P1)
        self._step("withdraw_p1", **w)
        try:
            if w["ready"]:
                self._case("fail-stale-withdrawn", "R3/R6", "FAIL_STALE, no content, no receipt", "NOT_REACHED", reason="P1 still READY after withdraw")
                return
            out, err = self._chain_or_error("fail-stale-withdrawn")
            if out is None:
                self._case("fail-stale-withdrawn", "R3/R6", "FAIL_STALE, no content, no receipt", "NOT_REACHED", error=err)
                return
            status, failed = self.grade_refusal(out, "publication", "FAIL_STALE", "PUBLICATION_NOT_READY:WITHDRAWN")
            self._case("fail-stale-withdrawn", "R3/R6", "FAIL_STALE, no content, no receipt", status, chain_label="fail-stale-withdrawn",
                       failed=failed, chain=self.summary["chains"]["fail-stale-withdrawn"])
        finally:
            r = life.restore(self.P1)
            self._step("restore_p1", **r)
            if r.get("state") != "RESTORED" or not r.get("ready"):
                self.blocked_reason = f"P1 restore {r.get('state')}: control state not recovered"
                raise RuntimeError(self.blocked_reason)

    def _missing_aspect(self) -> None:
        self._guard("missing-runtime-aspect")
        life = self.life
        rm = life.remove_runtime_aspect(ENTRY_LOCAL)
        self._step("remove_runtime_aspect", **rm)
        try:
            if rm["runtime_aspect_present"]:
                self._case("missing-runtime-aspect", "R1/R6", "ASPECT_MISSING at seed, authored aspects intact", "NOT_REACHED", reason="aspect still present after removal")
                return
            out, err = self._chain_or_error("missing-runtime-aspect")
            if out is None:
                self._case("missing-runtime-aspect", "R1/R6", "ASPECT_MISSING at seed, authored aspects intact", "NOT_REACHED", error=err)
                return
            status, failed = self.grade_refusal(out, "seed", "ASPECT_MISSING")
            expected_authored = sorted(self.authored)
            if sorted(rm.get("authored_aspects") or []) != expected_authored:
                failed.append(f"authored aspects after removal {rm.get('authored_aspects')} != {expected_authored}")
                status = "WRONG" if status == "MET" else status
            self._case("missing-runtime-aspect", "R1/R6", "ASPECT_MISSING at seed, authored aspects intact", status,
                       chain_label="missing-runtime-aspect", failed=failed, chain=self.summary["chains"]["missing-runtime-aspect"])
        finally:
            self._restore_pin("after_missing_aspect")

    def _restore_pin(self, label: str) -> None:
        pin = self.life.write_pin(ENTRY_LOCAL, self.P1, CONCEPT_PATH, authored_aspects=self.authored)
        self._step(f"restore_pin_{label}", **pin)
        if pin["readback_status"] != "OK" or not pin["authored_aspects_present"]:
            self.blocked_reason = f"valid pin not restored ({label}): {pin['readback_status']}"
            raise RuntimeError(self.blocked_reason)

    def _wrong_pins(self) -> None:
        self._guard("wrong-pins")
        life, B = self.life, self.cfg.bundle_id
        ghost = "pub_" + hashlib.sha256(f"never-retained:{self.cfg.run_id}".encode()).hexdigest()[:16]
        for name, override, prefix in (
                ("wrong-publication-pin", {"publication_id": ghost, "concept_id": f"{B}|{ghost}|Concept|metrics/gross-margin"}, "PUBLICATION_MISSING"),
                ("wrong-seed-pin", {"concept_id": f"{B}|{self.P1}|Concept|metrics/no-such-concept", "concept_path": "metrics/no-such-concept.md"}, "SEED_MISSING")):
            w = life.write_pin(ENTRY_LOCAL, self.P1, CONCEPT_PATH, authored_aspects=self.authored, pin_override=override)
            self._step(f"write_{name}", **w)
            try:
                out, err = self._chain_or_error(name)
                if out is None:
                    self._case(name, "R6", f"FAIL_STALE ({prefix}), no content, no receipt", "NOT_REACHED", error=err, override=override)
                    continue
                status, failed = self.grade_refusal(out, "publication", "FAIL_STALE", prefix)
                self._case(name, "R6", f"FAIL_STALE ({prefix}), no content, no receipt", status, chain_label=name, failed=failed,
                           override=override, chain=self.summary["chains"][name])
            finally:
                self._restore_pin(name)

    def _mixed_payload(self) -> None:
        self._guard("mixed-payload-injection")
        real = self.chain_module.governed
        inj_dir = self.run_dir / "injection"
        inj_dir.mkdir(exist_ok=True)
        calls: list[dict] = []
        P1, P2 = self.P1, self.P2

        def tampered(seed: Any, *a: Any, **k: Any) -> dict:
            r = real(seed, *a, **k)
            n = len(calls) + 1
            raw = (json.dumps(self.redact(_jsonable(r)), indent=1, sort_keys=True, default=str) + "\n").encode("utf-8")
            kept = inj_dir / f"raw_live_result_{n}.json"
            kept.write_bytes(raw)
            rec = {"call": n, "seed": str(seed), "seed_origin": getattr(seed, "origin", None), "live_status": r.get("status"),
                   "raw_retained": {"path": str(kept), "sha256": hashlib.sha256(raw).hexdigest()}, "mutations": []}
            if getattr(seed, "origin", None) == "catalog" and r.get("status") == "OK":
                if n == 1:      # approved: a P2 section row/id mixed into the P1 computation (labels still say P1)
                    for c in r.get("computations", []):
                        before = c.get("section_id")
                        if before and P1 in before:
                            c["section_id"] = before.replace(P1, P2)
                            rec["mutations"].append({"field": "computations[].section_id", "before": before, "after": c["section_id"], "kind": "P2 section id mixed into P1 result"})
                elif n == 2:    # sql-substitution: content altered, scope/hash labels untouched
                    for c in r.get("computations", []):
                        if "payment_fee" in (c.get("sql") or ""):
                            c["sql"] = c["sql"].replace("payment_fee", "0 * payment_fee", 1)
                            rec["mutations"].append({"field": "computations[].sql", "kind": "SQL bytes changed under the unchanged sql_sha256 / P1 labels",
                                                     "label_sql_sha256": c.get("sql_sha256")})
            calls.append(rec)
            return r
        out, err = self._chain_or_error("mixed-payload-injection", hooks={"governed": tampered})
        meta = {"kind": "live-backed client fault injection", "where": "after the live BigQuery governed retrieval returned, before the payload guard",
                "note": "BigQuery did not return a torn publication; the retrieval result was altered in the client", "calls": calls}
        (inj_dir / "fault_injection.json").write_text(json.dumps(self.redact(meta), indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
        self._step("mixed_payload_injection", **meta)
        if out is None:
            self._case("mixed-payload-injection", "R4", "tampered cases refused by the payload guard before the SDK", "NOT_REACHED", error=err, injection=meta)
            return
        if not any(c["mutations"] for c in calls):
            self._case("mixed-payload-injection", "R4", "tampered cases refused by the payload guard before the SDK", "NOT_REACHED", reason="no mutation was applied", injection=meta)
            return
        status, failed = self.grade_injection(out)
        self._case("mixed-payload-injection", "R4", "tampered cases refused by the payload guard before the SDK", status,
                   chain_label="mixed-payload-injection", failed=failed, injection=meta, chain=self.summary["chains"]["mixed-payload-injection"])

    def _recovery(self) -> None:
        self._guard("recovery-control")
        cfgc = self.cfg.catalog_config(ENTRY_LOCAL)
        out, err = self._chain_or_error("recovery-control")
        if out is None:
            self._case("recovery-control", "R6", "valid pin restored: CHAIN_CONNECTED again (head = P2, P1 served)", "NOT_REACHED", error=err)
            return
        status, failed = self.grade_connected(out, cfgc, self.P1, self.P2)
        self._case("recovery-control", "R6", "valid pin restored: CHAIN_CONNECTED again (head = P2, P1 served)", status,
                   chain_label="recovery-control", failed=failed, chain=self.summary["chains"]["recovery-control"])

    def _cleanup(self) -> None:
        life = self.life
        rec: dict[str, Any] = {}
        try:
            rec["originals"] = life.verify_originals_unchanged() if life.snapshot else {"status": "NOT_SNAPSHOTTED"}
        except Exception as e:  # noqa: BLE001
            rec["originals"] = {"status": "ERROR", "error": f"{type(e).__name__}: {str(e)[:200]}"}
        try:
            rec["cleanup"] = life.cleanup()
        except Exception as e:  # noqa: BLE001
            rec["cleanup"] = {"status": "ERROR", "error": f"{type(e).__name__}: {str(e)[:200]}"}
        rec["unresolved_operations"] = len(self.journal.unresolved())
        # operations != BigQuery jobs: the journal also holds Catalog GET/PATCH/DELETE and dataset create/delete, which
        # submit no job at all. Reporting the operation count as a job count is what Astra's PR42 P1 caught.
        js = self.journal.summary()
        rec["counts"] = {"lifecycle_operations": js["entries"], "lifecycle_bigquery_jobs": js["with_job_id"]}
        rec["derived_tree"] = self._prune_derived()
        self._step("cleanup", **rec)
        ok = rec["originals"].get("status") == "UNCHANGED" and rec["cleanup"].get("status") == "COMPLETE" and rec["unresolved_operations"] == 0
        failed = [] if ok else [f"originals {rec['originals'].get('status')}", f"cleanup {rec['cleanup'].get('status')}",
                                f"unresolved_operations {rec['unresolved_operations']}"]
        self._case("cleanup", "R7/R8", "originals UNCHANGED, owned resources absent on readback, every lifecycle operation terminal",
                   "MET" if ok else "NOT_REACHED", failed=failed, originals=rec["originals"], cleanup_status=rec["cleanup"].get("status"),
                   cleanup_steps=[{k: s.get(k) for k in ("resource", "kind", "deleted", "absent_verified", "reconciled", "error")} for s in rec["cleanup"].get("steps", [])],
                   counts=rec["counts"], unresolved_operations=rec["unresolved_operations"])

    # -- job identity (Astra PR42 P1)
    def _lifecycle_job_refs(self) -> list[dict]:
        """The driver's OWN job-backed operations, as full references. `journal.jobs()` also holds the non-job cloud
        operations (Catalog GETs/PATCHes, dataset create/delete); those are operations, not BigQuery jobs, and are
        counted separately — conflating the two is what produced the wrong '78 lifecycle jobs' wording."""
        return [{"source": "lifecycle", "leg": "lifecycle", "role": e.get("role"), "job_id": e["job_id"],
                 "project": e.get("project"), "location": e.get("location"), "journal_state": e.get("state"),
                 "journal_terminal": bool(e.get("terminal")),
                 # a job id is chosen before dispatch, so the journal can hold one for a job that never existed. NOT_SUBMITTED
                 # is established locally (refused before the send) or by jobs.get; either way there is no job to identify.
                 "dispatched": e.get("state") != "NOT_SUBMITTED"}
                for e in self.journal.jobs() if e.get("job_id")]

    def _job_audit(self, timeout: Optional[float] = None) -> dict:
        """Read every job this run submitted back under its own full reference and retain what the server says.

        The gap this closes: the chain's `same_requester` needs BOTH legs populated, so it returns `UNKNOWN` for any
        adversary that correctly refused before the SDK (graph jobs, no receipt) and `NOT_RUN` for one that refused
        before any case. That is the *expected* shape of those negatives, which meant the strongest B2 results were the
        ones with the weakest identity evidence. This audit does not depend on either leg being non-empty: it walks the
        exact job set — lifecycle + every child chain, graph-only refusals included — and records the actual principal,
        terminal state and error for each. A job it cannot read leaves the gate incomplete; it never invents identity.

        Read-only: `jobs.get` submits no job, so auditing cannot grow the set it is auditing."""
        t = timeout if timeout is not None else self.cfg.timeout_s
        refs = self._lifecycle_job_refs()
        for label, rows in self.chain_jobs.items():
            refs.extend(rows)
        jobs, seen = [], set()
        for r in refs:
            key = (r.get("project"), r.get("location"), r["job_id"])
            if key in seen:
                continue
            seen.add(key)
            rec = dict(r)
            if not r.get("dispatched", True):
                rec.update(read="NOT_DISPATCHED", state="NOT_SUBMITTED", user_email=None, error=None)
                jobs.append(rec)
                continue
            try:
                st = self.raw_cloud.job_state(r["job_id"], timeout=t, project=r.get("project"), location=r.get("location")) \
                    if _accepts_ref(self.raw_cloud.job_state) else self.raw_cloud.job_state(r["job_id"], timeout=t)
                if st is None:
                    rec.update(read="NOT_FOUND", state=None, user_email=None, error=None)
                else:
                    rec.update(read="OK", state=st.get("state"), user_email=st.get("user_email"), error=_jsonable(st.get("error")))
            except Exception as e:  # noqa: BLE001 - an unreadable job leaves the gate incomplete; it is never assumed terminal
                rec.update(read="ERROR", state=None, user_email=None, error=f"{type(e).__name__}: {str(e)[:200]}")
            jobs.append(rec)

        gate = identity_gate
        by_chain = {label: gate([j for j in jobs if j["source"] == f"chain:{label}"], self.chain_unresolved.get(label, []))
                    for label in self.chain_jobs}
        lifecycle = gate([j for j in jobs if j["source"] == "lifecycle"], [])
        overall = gate(jobs, [u for v in self.chain_unresolved.values() for u in v])
        ops = self.journal.summary()
        audit = {"note": "every job this run submitted, read back under its own (project, location, job id); lifecycle "
                         "OPERATIONS are counted separately from lifecycle BigQuery JOBS",
                 "overall": overall, "lifecycle": lifecycle, "by_chain": by_chain,
                 "counts": {"lifecycle_operations": ops["entries"], "lifecycle_bigquery_jobs": ops["with_job_id"],
                            "chain_jobs": sum(len(v) for v in self.chain_jobs.values()), "total_jobs": len(jobs)},
                 "jobs": jobs, "at": _now()}
        raw = (json.dumps(self.redact(_jsonable(audit)), indent=1, sort_keys=True, default=str) + "\n").encode("utf-8")
        (self.run_dir / "job_identity.json").write_bytes(raw)
        audit["retained"] = {"path": str(self.run_dir / "job_identity.json"), "sha256": hashlib.sha256(raw).hexdigest()}
        return audit

    def _apply_identity_gate(self, audit: dict) -> None:
        """A correct boundary with unknown job identity is not a complete result. The behaviour verdict is kept in
        `behaviour`; `status` carries the combined result the run is allowed to claim."""
        for c in self.summary["cases"]:
            label = c.get("chain_label")
            g = audit["by_chain"].get(label) if label else (audit["lifecycle"] if c["case"] == "cleanup" else None)
            if g is None:
                continue
            c["identity"] = {k: g[k] for k in ("status", "jobs", "principals", "reasons")}
            if c["status"] == "MET" and g["status"] != "COMPLETE":
                c["status"] = "NOT_REACHED"
                c.setdefault("failed", []).append(f"job identity evidence incomplete: {'; '.join(g['reasons'])}")

    def _prune_derived(self) -> dict:
        """The retained P2 tree is a full copy of the pinned bundle; after the run only `derivation.json` and the changed
        file(s) are kept (the tree is reproducible from the clean pin + derivation.json)."""
        import shutil
        d = self.run_dir / "derived"
        if not d.is_dir():
            return {"status": "ABSENT"}
        try:
            der = json.loads((d / "derivation.json").read_text(encoding="utf-8"))
            keep = {Path(c["path"]) for c in der.get("changed_files", [])}
            root = Path(der["tree_root"])
            kept_dir = d / "changed_files"
            kept_dir.mkdir(exist_ok=True)
            for rel in keep:
                src = root / rel
                if src.is_file():
                    dst = kept_dir / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dst)
            shutil.rmtree(root, ignore_errors=True)
            return {"status": "PRUNED", "kept": sorted(str(k) for k in keep), "tree_root_removed": str(root)}
        except Exception as e:  # noqa: BLE001
            return {"status": "ERROR", "error": f"{type(e).__name__}: {str(e)[:200]}"}

    def markdown(self) -> str:
        s = self.summary
        lines = [f"# Slice B2 owned lifecycle — {s['run_id']}", "",
                 f"verdict `{s['verdict']}` · P1 `{s['publications'].get('P1')}` · P2 `{s['publications'].get('P2')}` · elapsed {s.get('elapsed_s')} s · "
                 f"dataset `{s['allowlist']['dataset']}` · entry prefix `{s['allowlist']['entry_prefix']}`", "",
                 "| case | gate | expected | status | job identity | detail |", "|---|---|---|---|---|---|"]
        for c in s["cases"]:
            detail = "; ".join(c.get("failed") or []) or c.get("note") or c.get("reason") or c.get("error") or ""
            ch = c.get("chain") or {}
            if ch.get("verdict"):
                detail = (detail + " " if detail else "") + f"chain {ch['verdict']}" + (f" at {ch['broken_at']}" if ch.get("broken_at") else "") + \
                    f", head {((ch.get('publication') or {}).get('head') or {}).get('publication_id')}"
            beh = c.get("behaviour")
            status = f"**{c['status']}**" + (f" (boundary {beh})" if beh and beh != c["status"] else "")
            ident = (c.get("identity") or {}).get("status") or "-"
            lines.append(f"| {c['case']} | {c['origin_gate']} | {c['expected']} | {status} | {ident} | {detail[:300]} |")
        ji = s.get("job_identity") or {}
        counts = ji.get("counts") or {}
        if counts:
            lines += ["", f"Job set: {counts.get('lifecycle_operations')} lifecycle operations of which "
                          f"{counts.get('lifecycle_bigquery_jobs')} are BigQuery jobs, plus {counts.get('chain_jobs')} child-chain jobs "
                          f"= {counts.get('total_jobs')} jobs audited; principals {(ji.get('overall') or {}).get('principals')}."]
        return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------- CLI
def main(argv: Optional[list[str]] = None) -> int:
    import os
    ap = argparse.ArgumentParser(description="Slice B2: owned Catalog entry + isolated dataset lifecycle around the live Catalog-seeded receipt chain")
    ap.add_argument("--live", action="store_true", help="required: this driver has no hermetic mode (tests inject fakes through B2Experiment)")
    ap.add_argument("--out", default="evidence/catalog-chain", help="evidence root; the run writes <out>/<run_id>/")
    ap.add_argument("--run-id", default=None, help="default b2-<utc stamp>-<hex4>; also names the owned dataset/entry prefix")
    ap.add_argument("--acme-root", default=os.environ.get("OKF_ACME_ROOT", "/Users/haiyuancao/knowledge-catalog/okf/bundles/acme_retail"))
    ap.add_argument("--sdk-root", default=None)
    ap.add_argument("--timeout-s", type=float, default=30.0, help="per cloud operation (harness limit, not an SLO)")
    ap.add_argument("--wall-cap-s", type=float, default=1200.0, help="experiment phase; new mutations are refused once it expires")
    ap.add_argument("--cleanup-cap-s", type=float, default=300.0, help="separate teardown budget, unaffected by the experiment cap")
    ap.add_argument("--chain-min-s", type=float, default=120.0, help="a chain is not started with less than this left of the cap")
    a = ap.parse_args(argv)
    if not a.live:
        ap.error("--live is required: the B2 driver only runs against real BigQuery + Dataplex (hermetic coverage is tests/test_catalog_live.py)")
    from google.cloud import bigquery
    from .authz import redact
    from .catalog import HttpReader
    from .chain import run_chain, sdk_root
    run_id = a.run_id or f"b2-{_dt.datetime.now(_dt.timezone.utc):%Y%m%dt%H%M%Sz}-{secrets.token_hex(2)}"
    cfg = LifecycleConfig(run_id=run_id, timeout_s=a.timeout_s)
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    cloud = LiveCloud(client)
    exp = B2Experiment(a.out, cfg, cloud, client, HttpReader, a.sdk_root or sdk_root(), a.acme_root, run_chain, wall_cap_s=a.wall_cap_s,
                       redact=redact, cleanup_cap_s=a.cleanup_cap_s, chain_min_s=a.chain_min_s)
    print(f"run_id={run_id} run_dir={exp.run_dir} dataset={cfg.dataset} entry_prefix={cfg.entry_prefix}", flush=True)
    s = exp.run()
    for c in s["cases"]:
        print(f"{c['case']:24s} {c['status']:12s} {'; '.join(c.get('failed') or [])[:160]}", flush=True)
    ji = s.get("job_identity") or {}
    print(f"verdict={s['verdict']} elapsed_s={s['elapsed_s']} cleanup={next((c.get('cleanup_status') for c in s['cases'] if c['case'] == 'cleanup'), None)} "
          f"lifecycle_unresolved={s['lifecycle_journal']['unresolved']} job_identity={(ji.get('overall') or {}).get('status')} "
          f"jobs_audited={(ji.get('counts') or {}).get('total_jobs')} summary={exp.run_dir / 'b2_summary.json'}", flush=True)
    return 0 if s["verdict"] == "B2_ALL_MET" else 1


if __name__ == "__main__":
    sys.exit(main())
