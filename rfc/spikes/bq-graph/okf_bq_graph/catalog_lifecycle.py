"""Isolated, bounded relational-only publication + Catalog pin lifecycle for Slice B2 (plan U4 / KTD5-KTD6).

Everything this driver mutates is run-owned and derived from local configuration BEFORE any Catalog read:
  dataset        okf_catalog_chain_<run_suffix>            (US; relational tables only: nodes, edges, publications, active_publication)
  entries        <group>/entries/acme-retail-catalog-chain/<run_id>/<local>
  deployment     acme-retail-catalog-chain-<run_id>         (managed_by_deployment on every owned pin)
The original KC entry, the ten older demo entries and the original graph dataset/head are read (snapshot) and never
written. A returned Catalog pin can never authorize its own destination: the trusted allowlist is this configuration.

What it deliberately does NOT do: `publish.publish()` (which always calls `ensure_graph()` = graph DDL, appends with
WRITE_APPEND and may embed), embeddings, reservations, IAM changes, prefix/glob deletes. P2 is compiled from a
retained temporary source tree with its derivation recorded; its source pin is `<base>+local.<manifest16>`, never the
clean upstream label. Every cloud operation is journaled before it is waited on, carries a bounded timeout, and the
cleanup receipt is COMPLETE only when every owned resource's absence was read back.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import secrets
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

from . import BUNDLE_ID, DATASET, PROJECT
from .catalog import (DEFAULT_ASPECT_KEY, DEFAULT_ENTRY, DEFAULT_ENTRY_TYPE, DEFAULT_GROUP, CatalogConfig, CatalogPin, parse_pin)
from .compile import compile_bundle, validate_projection
from .model import sha256_bytes, sha256_text, stable_json
from .publication import canonical_rows

RELATIONAL_TABLES = ("nodes", "edges", "publications", "active_publication")
FORBIDDEN_SQL = ("PROPERTY GRAPH", "ML.GENERATE_EMBEDDING", "section_vectors", "CREATE MODEL", "RESERVATION", "GRANT ", "REVOKE ")
DEFAULT_TIMEOUT = 30.0


class ScopeViolation(RuntimeError):
    """A mutation targeted something this run does not own. Raised before any cloud call."""


# ----------------------------------------------------------------------------- configuration (the allowlist)
@dataclass(frozen=True)
class LifecycleConfig:
    run_id: str
    project: str = PROJECT
    location: str = "US"
    catalog_group: str = DEFAULT_GROUP
    entry_type: str = DEFAULT_ENTRY_TYPE
    aspect_key: str = DEFAULT_ASPECT_KEY
    bundle_id: str = BUNDLE_ID
    original_entry: str = DEFAULT_ENTRY
    original_dataset: str = DATASET
    profile: str = "okf-catalog-chain/1"
    source_repository: str = "https://github.com/GoogleCloudPlatform/knowledge-catalog"
    source_root: str = "okf/bundles/acme_retail"
    compiler_version: str = "okf_bq_graph.compile/0.1.0"
    timeout_s: float = DEFAULT_TIMEOUT
    settle_s: Optional[float] = None    # recheck cadence for a pending (timed-out) create; NEVER closes the attempt by itself (default 2 x timeout_s)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{3,63}", self.run_id):
            raise ValueError("run_id must be 4-64 chars of [A-Za-z0-9._-]")

    @property
    def settle(self) -> float:
        return self.settle_s if self.settle_s is not None else 2.0 * self.timeout_s

    @property
    def run_suffix(self) -> str:
        return re.sub(r"[^a-z0-9]", "_", self.run_id.lower())

    @property
    def dataset(self) -> str:
        return f"okf_catalog_chain_{self.run_suffix}"

    @property
    def entry_prefix(self) -> str:
        return f"{self.catalog_group}/entries/acme-retail-catalog-chain/{self.run_id}/"

    @property
    def deployment(self) -> str:
        return f"acme-retail-catalog-chain-{self.run_id}"

    def allowlist(self) -> dict:
        """Derived locally before any Catalog read; the trusted destination/entry/deployment scope for B2 pins."""
        return {"dataset": self.dataset, "entry_prefix": self.entry_prefix, "deployment": self.deployment, "profile": self.profile,
                "protected": {"entry": self.original_entry, "dataset": self.original_dataset}}

    def catalog_config(self, entry_local: str) -> CatalogConfig:
        return CatalogConfig(group=self.catalog_group, entry=self.entry_prefix + entry_local, aspect_key=self.aspect_key, entry_type=self.entry_type,
                             runtime_project=self.project, runtime_dataset=self.dataset, runtime_location=self.location, bundle_id=self.bundle_id,
                             source_repository=self.source_repository, source_root=self.source_root, managed_by_profile=self.profile,
                             managed_by_deployment=self.deployment, compiler_version=self.compiler_version, allow_local_derived_source=True)

    def owns_dataset(self, ds: str) -> bool:
        return ds == self.dataset and ds != self.original_dataset

    def owns_entry(self, name: str) -> bool:
        """Exact prefix plus a safe local segment: no empty, `.`/`..` or leading-slash components, no traversal."""
        if not name.startswith(self.entry_prefix) or name == self.original_entry:
            return False
        local = name[len(self.entry_prefix):]
        return bool(local) and all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", part) and part not in (".", "..") for part in local.split("/"))


# ----------------------------------------------------------------------------- cloud operations (bounded, protocol-level)
class CloudOps(Protocol):
    """Every call takes `timeout` (seconds) and returns when the operation is terminal or raises. Job-backed BigQuery
    operations receive a driver-chosen `job_id` (journaled with project/location BEFORE dispatch) so a timed-out call
    can be reconciled through `job_state`; resources are created with an ownership stamp (`labels`) that adoption
    after a lost response must match."""
    def get_dataset(self, dataset: str, timeout: float) -> Optional[dict]: ...           # {"labels": {...}} or None (absence = None)
    def create_dataset(self, dataset: str, location: str, labels: dict, attempt_id: str, timeout: float) -> dict: ...
    def delete_dataset(self, dataset: str, timeout: float) -> dict: ...
    def run_ddl(self, dataset: str, statement: str, job_id: str, timeout: float) -> dict: ...
    def load_rows(self, dataset: str, table: str, rows: list[dict], job_id: str, timeout: float) -> dict: ...
    def select_rows(self, dataset: str, table: str, where: dict, job_id: str, timeout: float, exclude: tuple = ()) -> list[dict]: ...
    def insert_row(self, dataset: str, table: str, row: dict, job_id: str, timeout: float) -> dict: ...
    def update_status(self, dataset: str, publication_id: str, status: str, job_id: str, timeout: float) -> dict: ...
    def merge_head(self, dataset: str, bundle_id: str, publication_id: str, job_id: str, timeout: float) -> dict: ...
    def job_state(self, job_id: str, timeout: float) -> Optional[dict]: ...              # {"state": ..., "error": ...} or None when the server has no such job
    def cancel_job(self, job_id: str, timeout: float) -> dict: ...
    def get_entry(self, name: str, timeout: float) -> Optional[dict]: ...
    def create_entry(self, name: str, body: dict, attempt_id: str, timeout: float) -> dict: ...
    def attempt_outcome(self, kind: str, name: str, attempt_id: str, timeout: float) -> Optional[str]: ...
    #   "APPLIED" | "NOT_APPLIED" when the adapter can establish the terminal outcome of that exact create attempt (its own
    #   request bookkeeping / operation record); None when it cannot. Elapsed time is never an outcome.
    def patch_entry(self, name: str, body: dict, aspect_keys: list[str], timeout: float) -> dict: ...
    def delete_entry(self, name: str, timeout: float) -> dict: ...


OWNER_LABEL = "okf_owner"           # BigQuery dataset label / Catalog entrySource label carrying the invocation stamp
ATTEMPT_LABEL = "okf_attempt"       # ... and the create attempt that produced the resource (one resource discharges one attempt)
JOB_OPS = ("run_ddl", "load_rows", "select_rows", "insert_row", "update_status", "merge_head")


def relational_schema(ds_full: str) -> list[str]:
    """Only the four relational tables from sql/schema.sql; never section_vectors, never graph.sql."""
    from .publish import sql
    text = "\n".join(l for l in sql("schema.sql", ds_full).splitlines() if not l.strip().startswith("--"))
    out = []
    for stmt in text.split(";"):
        s = stmt.strip()
        if not s:
            continue
        m = re.search(r"CREATE TABLE IF NOT EXISTS `[^`]+\.(\w+)`", s)
        if m and m.group(1) in RELATIONAL_TABLES:
            out.append(s)
    return out


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


# ----------------------------------------------------------------------------- P2 derivation
def prepare_derived_source(clean_root: str, base_pin: str, work_dir: str, change_file: str = "policies/margin-standard.md",
                           appended: str = "\n\n# Revision note\n\nFY2027 cost-allocation review scheduled (catalog-chain lifecycle test).\n") -> dict:
    """Copy the clean pinned bundle, change one non-computation file, compile, and record the derivation. The
    resulting pin is `<base>+local.<manifest sha256[:16]>`: a retained local tree, never the clean upstream commit."""
    root = Path(work_dir) / "acme_retail"
    if root.exists():
        raise FileExistsError(root)
    shutil.copytree(clean_root, root)
    target = root / change_file
    if not target.is_file() or change_file.startswith("computations/"):
        shutil.rmtree(root, ignore_errors=True)
        raise ValueError(f"change_file must be an existing non-computation bundle file: {change_file}")
    before = sha256_bytes(target.read_bytes())
    target.write_text(target.read_text(encoding="utf-8") + appended, encoding="utf-8")
    after = sha256_bytes(target.read_bytes())
    probe = compile_bundle(str(root), BUNDLE_ID, base_pin)             # manifest digest of the changed tree (pin-independent files)
    manifest16 = sha256_text(stable_json([{"path": m["path"], "sha256": m["sha256"]} for m in probe["source_manifest"]]))[:16]
    source_pin = f"{base_pin}+local.{manifest16}"
    projection = compile_bundle(str(root), BUNDLE_ID, source_pin)
    derivation = {"base_pin": base_pin, "tree_root": str(root), "source_pin": source_pin, "changed_files": [{"path": change_file, "before_sha256": before, "after_sha256": after}],
                  "manifest_sha256": projection["source_manifest_sha256"], "publication_id": projection["publication_id"],
                  "compiled_at": _now(), "note": "local derivation of the pinned source for the owned republish experiment; not a clean upstream revision"}
    (Path(work_dir) / "derivation.json").write_text(json.dumps(derivation, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"projection": projection, "derivation": derivation}


# ----------------------------------------------------------------------------- driver
@dataclass
class Owned:
    """Confirmed resources plus `pending`: writes whose response was lost. A pending resource may exist server-side,
    so it is persisted BEFORE the write and blocks a COMPLETE cleanup until its actual state was read back."""
    dataset: Optional[str] = None
    tables: list[str] = field(default_factory=list)
    publications: list[str] = field(default_factory=list)
    ready_verified: list[str] = field(default_factory=list)   # publications whose full-row readback was READY (restore may only reinstate these)
    entries: list[str] = field(default_factory=list)
    pending: list[dict] = field(default_factory=list)          # {"kind": "dataset"|"entry", "name": ..., "at", "at_ts", "state"}
    foreign: list[dict] = field(default_factory=list)          # resources under our names that carry another stamp: preserved, never touched
    head_set: bool = False

    def record(self) -> dict:
        return {"dataset": self.dataset, "tables": list(self.tables), "publications": list(self.publications), "ready_verified": list(self.ready_verified),
                "entries": list(self.entries), "pending": [dict(x) for x in self.pending], "foreign": [dict(x) for x in self.foreign], "head_set": self.head_set}


class Lifecycle:
    def __init__(self, cfg: LifecycleConfig, cloud: CloudOps, journal: Any, clock: Callable[[], float] = time.time):
        self.cfg, self.cloud, self.journal, self.clock = cfg, cloud, journal, clock
        self.owned = Owned()
        self._projections: dict[str, dict] = {}
        self.snapshot: dict[str, Any] = {}
        # the invocation stamp: unique per Lifecycle instance, written onto every created resource, required for adoption.
        # A run id that merely normalises to the same dataset name (review-run-A vs review_run_a) never matches it.
        self.invocation_id = f"{cfg.run_id}-{secrets.token_hex(6)}"
        self.owner_stamp = hashlib.sha256(self.invocation_id.encode()).hexdigest()[:32]
        self.journal.note("lifecycle_allowlist", invocation_id=self.invocation_id, owner_stamp=self.owner_stamp, **cfg.allowlist())
        self._ownership_file = Path(journal.run_dir) / "ownership.json"
        self._write_ownership("init")

    def stamp_labels(self, attempt_id: Optional[str] = None) -> dict:
        """Invocation stamp plus, for creates, the attempt stamp: a present resource discharges exactly one attempt."""
        labels = {OWNER_LABEL: self.owner_stamp, "okf_run": self.cfg.run_suffix[:63]}
        if attempt_id:
            labels[ATTEMPT_LABEL] = attempt_id[:63]
        return labels

    def _stamped_by_us(self, labels: Optional[dict], attempt_id: Optional[str] = None) -> bool:
        if not (isinstance(labels, dict) and labels.get(OWNER_LABEL) == self.owner_stamp):
            return False
        return attempt_id is None or labels.get(ATTEMPT_LABEL) == attempt_id[:63]

    # -- bounded, journaled operation
    def _op(self, role: str, description: str, fn: Callable[..., Any], *args: Any, mutates: bool = False, target: Optional[str] = None,
            job: bool = False, meta: Optional[dict] = None, **kw: Any) -> Any:
        """One bounded, journaled cloud call. Job-backed BigQuery operations (`job=True`) get a driver-chosen job id
        journaled with (project, location) BEFORE dispatch; if the call raises, the job's own server state decides
        (never the target resource's presence). Non-job writes that raise are UNKNOWN until their resource is read
        back with our stamp."""
        job_backed = job
        jid = f"okf_cc_{self.cfg.run_suffix}_{role}_{uuid.uuid4().hex[:12]}"[:1024] if job_backed else None
        e = self.journal.intend(role, description, "cloud", actual=True, mutates=mutates, target=target, timeout_s=self.cfg.timeout_s,
                                job_backed=job_backed, **(meta or {}))
        self.journal.submitted(e, job_id=jid, project=self.cfg.project if job_backed else None, location=self.cfg.location if job_backed else None)
        self._last_entry = e
        if job_backed:
            kw["job_id"] = jid
        try:
            out = fn(*args, timeout=self.cfg.timeout_s, **kw)
        except Exception as ex:  # noqa: BLE001
            err = f"{type(ex).__name__}: {str(ex)[:300]}"
            if job_backed:
                self.journal.unknown(e, err)
                self._reconcile_job_entry(e)        # jobs.get decides: NOT_SUBMITTED / DONE / ERROR / CANCELLED, or stays UNKNOWN
            elif mutates:
                self.journal.unknown(e, err)          # the write may have landed: unresolved until the resource is read back with our stamp
            else:
                self.journal.terminal(e, "ERROR", error=err)
            raise
        self.journal.terminal(e, "DONE", rows=len(out) if isinstance(out, list) else None)
        return out

    def _reconcile_job_entry(self, e: dict, cancel: bool = True) -> dict:
        """Read the job's actual server state under its journaled reference. Unreadable or still running after one
        cancel attempt leaves the entry unresolved with its id."""
        jid = e.get("job_id")
        if not jid or e.get("terminal"):
            return e
        try:
            st = self.cloud.job_state(jid, timeout=self.cfg.timeout_s)
        except Exception as ex:  # noqa: BLE001
            e["reconcile_error"] = f"{type(ex).__name__}: {str(ex)[:200]}"
            self.journal.note("reconcile_failed", seq=e["seq"], job_id=jid, error=e["reconcile_error"])
            return e
        if st is None:
            return self.journal.reconcile(e, "NOT_SUBMITTED", observed="job_state: no such job")
        state = st.get("state")
        if state == "DONE":
            return self.journal.reconcile(e, "ERROR" if st.get("error") else "DONE", observed="DONE", error=st.get("error") or e.get("error"))
        if cancel:
            try:
                self.cloud.cancel_job(jid, timeout=self.cfg.timeout_s)
                st2 = self.cloud.job_state(jid, timeout=self.cfg.timeout_s)
            except Exception as ex:  # noqa: BLE001
                e["reconcile_error"] = f"cancel/readback {type(ex).__name__}: {str(ex)[:200]}"
                e["observed"] = state
                self.journal.note("reconcile_failed", seq=e["seq"], job_id=jid, error=e["reconcile_error"])
                return e
            if st2 is not None and st2.get("state") == "DONE":
                return self.journal.reconcile(e, "CANCELLED", observed=f"{state} -> DONE after cancel", error=st2.get("error") or e.get("error"))
            e["observed"] = (st2 or {}).get("state", state)
        else:
            e["observed"] = state
        self.journal.note("job_unresolved", seq=e["seq"], job_id=jid, observed=e["observed"])
        return e

    def _pending(self, kind: str, name: str) -> dict:
        """Register a create attempt before the write. A second create for a target that still has an unresolved
        attempt is refused: two in-flight attempts on one name cannot be told apart by the resource alone (Astra PR41
        re-review 3, R3) — run cleanup to reconcile the first attempt, then retry."""
        open_ = [x for x in self.owned.pending if x["kind"] == kind and x["name"] == name]
        if open_:
            raise ScopeViolation(f"{kind} {name} has an unresolved create attempt {open_[0]['attempt_id']} ({open_[0]['state']}): reconcile it before retrying")
        rec = {"kind": kind, "name": name, "attempt_id": f"okf_att_{self.cfg.run_suffix}_{uuid.uuid4().hex[:12]}", "at": _now(), "at_ts": self.clock(),
               "state": "IN_FLIGHT", "owner_stamp": self.owner_stamp}
        self.owned.pending.append(rec)
        self._write_ownership(f"pending_{kind}")
        return rec

    def _confirm(self, rec: dict) -> None:
        self.owned.pending = [x for x in self.owned.pending if x is not rec]

    def _write_ownership(self, event: str) -> None:
        rec = {"event": event, "at": _now(), "run_id": self.cfg.run_id, "allowlist": self.cfg.allowlist(), "owned": self.owned.record()}
        self._ownership_file.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        self.journal.note("ownership", ownership_event=event, **{k: v for k, v in rec.items() if k not in ("event", "at")})

    def _guard_dataset(self, ds: str) -> None:
        if not self.cfg.owns_dataset(ds):
            raise ScopeViolation(f"dataset {ds} is not owned by run {self.cfg.run_id}")

    def _guard_entry(self, name: str) -> None:
        if not self.cfg.owns_entry(name):
            raise ScopeViolation(f"entry {name} is not owned by run {self.cfg.run_id}")

    @staticmethod
    def _guard_sql(statement: str) -> None:
        up = statement.upper()
        for bad in FORBIDDEN_SQL:
            if bad.upper() in up:
                raise ScopeViolation(f"forbidden statement on the relational-only path: {bad}")

    # -- 0. snapshot originals (read only)
    def snapshot_originals(self) -> dict:
        entry = self._op("snapshot_original_entry", "GET original entry view=ALL (read only)", self.cloud.get_entry, self.cfg.original_entry, target=self.cfg.original_entry)
        head = self._op("snapshot_original_head", "original active_publication (read only)", self.cloud.select_rows, self.cfg.original_dataset, "active_publication",
                        {"bundle_id": self.cfg.bundle_id}, target=f"{self.cfg.original_dataset}.active_publication", job=True)
        snap = {"entry_present": entry is not None, "entry_sha256": sha256_text(stable_json(entry)) if entry is not None else None,
                "runtime_aspect_present": bool(entry and self.cfg.aspect_key in (entry.get("aspects") or {})),
                "head": head[0]["publication_id"] if len(head) == 1 else None, "head_rows": len(head), "at": _now()}
        self.snapshot = snap
        self.journal.note("snapshot_originals", **snap)
        return snap

    def verify_originals_unchanged(self) -> dict:
        entry = self._op("reread_original_entry", "GET original entry after experiment (read only)", self.cloud.get_entry, self.cfg.original_entry, target=self.cfg.original_entry)
        head = self._op("reread_original_head", "original active_publication after experiment (read only)", self.cloud.select_rows, self.cfg.original_dataset,
                        "active_publication", {"bundle_id": self.cfg.bundle_id}, target=f"{self.cfg.original_dataset}.active_publication", job=True)
        now = {"entry_sha256": sha256_text(stable_json(entry)) if entry is not None else None, "head": head[0]["publication_id"] if len(head) == 1 else None}
        unchanged = now["entry_sha256"] == self.snapshot.get("entry_sha256") and now["head"] == self.snapshot.get("head")
        rec = {"status": "UNCHANGED" if unchanged else "CHANGED_EXTERNALLY_PRESERVED", "before": {k: self.snapshot.get(k) for k in ("entry_sha256", "head")}, "after": now,
               "note": "an unexpected external change is reported and preserved, never rolled back by this driver"}
        self.journal.note("originals_recheck", **rec)
        return rec

    # -- 1. provision owned dataset (relational tables only)
    def provision(self) -> dict:
        ds = self.cfg.dataset
        self._guard_dataset(ds)
        if self._op("dataset_precheck", "owned dataset must not pre-exist (GET; absence = None)", self.cloud.get_dataset, ds, target=ds) is not None:
            raise ScopeViolation(f"dataset {ds} already exists: not created by this run, refusing to adopt it")
        pend = self._pending("dataset", ds)                  # persisted before the write: a lost response still owns the attempt
        self._op("create_dataset", "create owned dataset (stamped)", self.cloud.create_dataset, ds, self.cfg.location, self.stamp_labels(pend["attempt_id"]),
                 pend["attempt_id"], mutates=True, target=ds, meta={"attempt_id": pend["attempt_id"]})
        self._confirm(pend)
        self.owned.dataset = ds
        self._write_ownership("dataset_created")
        for stmt in relational_schema(f"{self.cfg.project}.{ds}"):
            self._guard_sql(stmt)
            table = re.search(r"CREATE TABLE IF NOT EXISTS `[^`]+\.(\w+)`", stmt).group(1)
            self._op("create_table", f"create {table}", self.cloud.run_ddl, ds, stmt, mutates=True, target=f"{ds}.{table}", job=True)
            self.owned.tables.append(table)
        self._write_ownership("tables_created")
        return {"dataset": ds, "tables": list(self.owned.tables)}

    # -- 2. publish relational-only, read-validate full rows, READY (no head switch)
    def publish_relational(self, projection: dict, derivation: Optional[dict] = None, inject_failure: Optional[str] = None) -> dict:
        ds = self.cfg.dataset
        self._guard_dataset(ds)
        if self.owned.dataset != ds:
            raise ScopeViolation("publish before provision: no owned dataset")
        P, B = projection["publication_id"], projection["bundle_id"]
        if B != self.cfg.bundle_id:
            raise ScopeViolation(f"projection bundle {B} is not {self.cfg.bundle_id}")
        if P in self.owned.publications:
            raise ScopeViolation(f"publication {P} already published by this run: immutable, never rewritten")
        v = validate_projection(projection)
        rec: dict[str, Any] = {"publication_id": P, "validation": v, "derivation": derivation, "state": None}
        if not v["valid"]:
            rec["state"] = "REJECTED"
            self.journal.note("publish", **rec)
            return rec
        existing = self._op("publication_exists", "owned publications row must not pre-exist", self.cloud.select_rows, ds, "publications", {"publication_id": P}, target=f"{ds}.publications", job=True)
        if existing:
            raise ScopeViolation(f"publication {P} already present in owned dataset")
        nodes = [dict(n, stale_after_ts=None) for n in projection["nodes"]]
        self.owned.publications.append(P)                    # rows are owned from the first write attempt, not from its response
        self._projections[P] = projection
        self._write_ownership("rows_loading")
        self._op("load_nodes", f"load {len(nodes)} node rows", self.cloud.load_rows, ds, "nodes", nodes, mutates=True, target=f"{ds}.nodes", job=True)
        self._op("load_edges", f"load {len(projection['edges'])} edge rows", self.cloud.load_rows, ds, "edges", projection["edges"], mutates=True, target=f"{ds}.edges", job=True)
        self._write_ownership("rows_loaded")
        if inject_failure == "before_ready":
            rec["state"] = "INTERRUPTED_BEFORE_READY"
            self.journal.note("publish", **rec)
            raise RuntimeError("injected failure before READY: rows loaded, no publication row, never READY")
        r_nodes = self._op("readback_nodes", "full retained node rows", self.cloud.select_rows, ds, "nodes", {"publication_id": P, "bundle_id": B}, exclude=("stale_after_ts",), target=f"{ds}.nodes", job=True)
        r_edges = self._op("readback_edges", "full retained edge rows", self.cloud.select_rows, ds, "edges", {"publication_id": P, "bundle_id": B}, target=f"{ds}.edges", job=True)
        rn, re_ = canonical_rows(r_nodes), canonical_rows(r_edges)
        om = projection["output_manifest"]
        ids = {n["node_id"] for n in rn}
        checks = {"node_rows": rn == canonical_rows(projection["nodes"]), "edge_rows": re_ == canonical_rows(projection["edges"]),
                  "nodes_sha256": sha256_text(stable_json(rn)) == om["nodes_sha256"], "edges_sha256": sha256_text(stable_json(re_)) == om["edges_sha256"],
                  "section_hashes": all(sha256_text(n["text"] or "") == n["text_sha256"] for n in rn if n["kind"] == "Section"),
                  "dangling": all(e["src_id"] in ids and e["dst_id"] in ids for e in re_),
                  "distinct": len(ids) == len(rn)}
        status = "READY" if all(checks.values()) else "INVALID_READBACK"
        row = {"publication_id": P, "bundle_id": B, "source_pin": projection["source_pin"], "compiler_version": projection["compiler_version"],
               "source_manifest_sha256": projection["source_manifest_sha256"], "nodes_sha256": om["nodes_sha256"], "edges_sha256": om["edges_sha256"],
               "node_count": om["nodes"], "edge_count": om["edges"], "section_count": sum(1 for n in rn if n["kind"] == "Section"), "vector_count": 0,
               "embedding_model": None, "validation_status": status, "validation_reasons": [k for k, ok in checks.items() if not ok],
               "created_at": _now(), "ready_at": _now() if status == "READY" else None}
        self._op("insert_publication", f"publications row {status}", self.cloud.insert_row, ds, "publications", row, mutates=True, target=f"{ds}.publications", job=True)
        if status == "READY":
            self.owned.ready_verified.append(P)
            self._write_ownership("ready_verified")
        rec.update(state=status, readback=checks, row=row)
        self.journal.note("publish", **rec)
        return rec

    def _ready(self, P: str) -> bool:
        rows = self._op("publication_status", "owned publication status", self.cloud.select_rows, self.cfg.dataset, "publications", {"publication_id": P}, target=f"{self.cfg.dataset}.publications", job=True)
        return len(rows) == 1 and rows[0].get("validation_status") == "READY"

    # -- 3. head switch (atomic MERGE; only a READY owned publication; injectable interruption before the switch)
    def advance_head(self, P: str, inject_failure: Optional[str] = None) -> dict:
        ds = self.cfg.dataset
        self._guard_dataset(ds)
        if P not in self.owned.publications:
            raise ScopeViolation(f"{P} was not published by this run")
        if not self._ready(P):
            raise RuntimeError(f"{P} is not READY in the owned dataset: never becomes head")
        before = self.read_head()
        if inject_failure == "before_head":
            self.journal.note("head_switch", state="INTERRUPTED_BEFORE_HEAD", from_=before, to=P)
            raise RuntimeError("injected failure before head switch: old head keeps serving")
        self._op("merge_head", f"active_publication -> {P}", self.cloud.merge_head, ds, self.cfg.bundle_id, P, mutates=True, target=f"{ds}.active_publication", job=True)
        self.owned.head_set = True
        self._write_ownership("head_switched")
        after = self.read_head()
        rec = {"state": "SWITCHED" if after == P else "SWITCH_NOT_OBSERVED", "from": before, "to": P, "observed": after}
        self.journal.note("head_switch", **rec)
        return rec

    def read_head(self) -> Optional[str]:
        rows = self._op("read_head", "owned active_publication", self.cloud.select_rows, self.cfg.dataset, "active_publication", {"bundle_id": self.cfg.bundle_id}, target=f"{self.cfg.dataset}.active_publication", job=True)
        return rows[0]["publication_id"] if len(rows) == 1 else None

    # -- 4. owned Catalog pin generated from verified rows, authored aspects preserved by explicit keys
    def pin_from_rows(self, P: str, concept_path: str) -> dict:
        ds = self.cfg.dataset
        pub = self._op("pin_source_publication", "owned publication row for the pin", self.cloud.select_rows, ds, "publications", {"publication_id": P}, target=f"{ds}.publications", job=True)
        if len(pub) != 1 or pub[0]["validation_status"] != "READY":
            raise RuntimeError(f"{P} is not a single READY owned publication; no pin can be generated")
        seed = self._op("pin_source_seed", "owned seed node row for the pin", self.cloud.select_rows, ds, "nodes",
                        {"publication_id": P, "bundle_id": self.cfg.bundle_id, "path": concept_path, "kind": "Concept"}, target=f"{ds}.nodes", job=True)
        if len(seed) != 1:
            raise RuntimeError(f"seed {concept_path} is not exactly one Concept row in {P}")
        p, s = pub[0], seed[0]
        return {"runtime_contract": "graph-spike-v1", "runtime_project": self.cfg.project, "runtime_dataset": ds, "runtime_location": self.cfg.location,
                "bundle_id": self.cfg.bundle_id, "publication_id": P, "concept_id": s["node_id"], "concept_path": s["path"], "concept_file_sha256": s["file_sha256"],
                "source_pin": p["source_pin"], "source_manifest_sha256": p["source_manifest_sha256"], "source_repository": self.cfg.source_repository,
                "source_root": self.cfg.source_root, "managed_by_profile": self.cfg.profile, "managed_by_deployment": self.cfg.deployment,
                "compiler_version": p["compiler_version"], "binding_verified_at": _now()}

    def write_pin(self, entry_local: str, P: str, concept_path: str, authored_aspects: Optional[dict] = None, pin_override: Optional[dict] = None) -> dict:
        """Create or patch the owned entry with explicit aspect keys (never delete-missing). `pin_override` patches the
        generated pin for adversary cases (wrong publication/seed) and is recorded as such."""
        name = self.cfg.entry_prefix + entry_local
        self._guard_entry(name)
        data = self.pin_from_rows(P, concept_path)
        if pin_override:
            data.update(pin_override)
        aspects = {self.cfg.aspect_key: {"data": data}}
        for k, v in (authored_aspects or {}).items():
            aspects[k] = {"data": v}
        body = {"name": name, "entryType": self.cfg.entry_type,
                "entrySource": {"system": "okf-catalog-chain", "labels": {"bundle": self.cfg.bundle_id, "run": self.cfg.run_id, **self.stamp_labels()}},
                "aspects": aspects}
        exists = self._op("entry_exists", "owned entry pre-read", self.cloud.get_entry, name, target=name) is not None
        if exists and name not in self.owned.entries:
            raise ScopeViolation(f"entry {name} exists but was not created by this run")
        if exists:
            self._op("patch_entry", f"patch owned entry aspects {sorted(aspects)}", self.cloud.patch_entry, name, body, sorted(aspects), mutates=True, target=name)
        else:
            pend = self._pending("entry", name)
            body["entrySource"]["labels"].update(self.stamp_labels(pend["attempt_id"]))
            self._op("create_entry", "create owned entry", self.cloud.create_entry, name, body, pend["attempt_id"], mutates=True, target=name,
                     meta={"attempt_id": pend["attempt_id"]})
            self._confirm(pend)
            self.owned.entries.append(name)
            self._write_ownership("entry_created")
        back = self._op("readback_entry", "GET owned entry view=ALL", self.cloud.get_entry, name, target=name)
        parsed = parse_pin(back, self.cfg.catalog_config(entry_local))
        rec = {"entry": name, "publication_id": P, "adversarial_override": sorted(pin_override) if pin_override else [],
               "readback_status": "OK" if isinstance(parsed, CatalogPin) else parsed.status,
               "authored_aspects_present": all(k in (back or {}).get("aspects", {}) for k in (authored_aspects or {}))}
        self.journal.note("write_pin", **rec)
        return rec

    def remove_runtime_aspect(self, entry_local: str) -> dict:
        """Adversary: drop only the runtime aspect from an owned entry (authored aspects stay)."""
        name = self.cfg.entry_prefix + entry_local
        self._guard_entry(name)
        if name not in self.owned.entries:
            raise ScopeViolation(f"entry {name} not owned")
        cur = self._op("entry_pre_read", "owned entry before aspect removal", self.cloud.get_entry, name, target=name) or {}
        aspects = {k: v for k, v in (cur.get("aspects") or {}).items() if k != self.cfg.aspect_key}
        body = dict(cur, aspects=aspects)
        self._op("patch_entry", "remove runtime aspect (owned)", self.cloud.patch_entry, name, body, [self.cfg.aspect_key], mutates=True, target=name)
        back = self._op("readback_entry", "GET owned entry after removal", self.cloud.get_entry, name, target=name)
        return {"entry": name, "runtime_aspect_present": self.cfg.aspect_key in (back or {}).get("aspects", {}), "authored_aspects": sorted(aspects)}

    # -- 5. availability adversaries on owned publications
    def withdraw(self, P: str) -> dict:
        self._guard_dataset(self.cfg.dataset)
        if P not in self.owned.publications:
            raise ScopeViolation(f"{P} not owned")
        if P not in self.owned.ready_verified:
            raise RuntimeError(f"{P} was never verified READY by this run: only a verified READY publication is withdrawn as an adversary")
        self._op("withdraw", f"publications.validation_status -> WITHDRAWN for {P}", self.cloud.update_status, self.cfg.dataset, P, "WITHDRAWN", mutates=True, target=f"{self.cfg.dataset}.publications", job=True)
        return {"publication_id": P, "ready": self._ready(P)}

    def _readback_checks(self, P: str) -> dict:
        """The same full-row validation `publish_relational` uses, against the current retained rows."""
        ds, B = self.cfg.dataset, self.cfg.bundle_id
        projection = self._projections[P]
        r_nodes = self._op("readback_nodes", "full retained node rows", self.cloud.select_rows, ds, "nodes", {"publication_id": P, "bundle_id": B}, exclude=("stale_after_ts",), target=f"{ds}.nodes", job=True)
        r_edges = self._op("readback_edges", "full retained edge rows", self.cloud.select_rows, ds, "edges", {"publication_id": P, "bundle_id": B}, target=f"{ds}.edges", job=True)
        rn, re_ = canonical_rows(r_nodes), canonical_rows(r_edges)
        om = projection["output_manifest"]
        ids = {n["node_id"] for n in rn}
        return {"node_rows": rn == canonical_rows(projection["nodes"]), "edge_rows": re_ == canonical_rows(projection["edges"]),
                "nodes_sha256": sha256_text(stable_json(rn)) == om["nodes_sha256"], "edges_sha256": sha256_text(stable_json(re_)) == om["edges_sha256"],
                "section_hashes": all(sha256_text(n["text"] or "") == n["text_sha256"] for n in rn if n["kind"] == "Section"),
                "dangling": all(e["src_id"] in ids and e["dst_id"] in ids for e in re_), "distinct": len(ids) == len(rn), "sections": sum(1 for n in rn if n["kind"] == "Section")}

    def restore(self, P: str) -> dict:
        """Reinstate READY only for a publication this run verified READY, only from WITHDRAWN, and only after the
        retained rows re-validate (Astra PR41 P2: restore must not promote INVALID_READBACK or corrupted rows)."""
        self._guard_dataset(self.cfg.dataset)
        if P not in self.owned.publications:
            raise ScopeViolation(f"{P} not owned")
        if P not in self.owned.ready_verified:
            raise RuntimeError(f"{P} was never verified READY by this run: nothing to restore")
        rows = self._op("publication_status", "owned publication status before restore", self.cloud.select_rows, self.cfg.dataset, "publications", {"publication_id": P}, target=f"{self.cfg.dataset}.publications", job=True)
        if len(rows) != 1 or rows[0].get("validation_status") != "WITHDRAWN":
            raise RuntimeError(f"{P} is not a single WITHDRAWN row (status={[r.get('validation_status') for r in rows]}): restore refused")
        checks = self._readback_checks(P)
        if not all(v for k, v in checks.items() if k != "sections"):
            self.journal.note("restore_refused", publication_id=P, readback=checks)
            return {"publication_id": P, "ready": False, "state": "RESTORE_REFUSED", "readback": checks}
        self._op("restore", f"publications.validation_status -> READY for {P}", self.cloud.update_status, self.cfg.dataset, P, "READY", mutates=True, target=f"{self.cfg.dataset}.publications", job=True)
        return {"publication_id": P, "ready": self._ready(P), "state": "RESTORED", "readback": checks}

    # -- 6. cleanup: exact owned resources only, readback of absence, receipt
    def _reconcile_pending(self) -> list[dict]:
        """Read back every pending write (lost response) under its own name. The outcome is decided by evidence, never
        by presence alone and never by elapsed time (Astra PR41 re-review 2, R3):
          PRESENT_ADOPTED        present AND carries this invocation's stamp -> ours; deleted below
          FOREIGN_PRESERVED      present with another / no stamp -> not ours; left untouched, stays pending (INCOMPLETE)
          OTHER_ATTEMPT_PRESENT  present with our owner stamp but another attempt's stamp -> that attempt adopts it; this one
                                 stays pending (its own outcome is still unknown)
          NOT_APPLIED_VERIFIED   absent AND the adapter establishes that this exact attempt terminated without applying
          ABSENT_PENDING         absent, outcome unknown -> the attempt stays pending (INCOMPLETE); `recheck_after_s` schedules
                                 the next look (cfg.settle cadence) and a later cleanup re-reads it
        Unreadable -> stays pending and blocks COMPLETE. Rerunning cleanup re-reads what is still pending."""
        steps: list[dict] = []
        now = self.clock()
        for rec in list(self.owned.pending):
            step = {"resource": rec["name"], "kind": f"pending_{rec['kind']}", "attempt_id": rec.get("attempt_id"), "deleted": False, "absent_verified": False,
                    "reconciled": None, "age_s": round(now - rec.get("at_ts", now), 3), "settle_s": self.cfg.settle}
            try:
                if rec["kind"] == "entry":
                    body = self._op("reconcile_pending_entry", "GET pending entry", self.cloud.get_entry, rec["name"], target=rec["name"])
                    present = body is not None
                    labels = ((body or {}).get("entrySource") or {}).get("labels")
                elif rec["kind"] == "dataset":
                    meta = self._op("reconcile_pending_dataset", "GET pending dataset (labels)", self.cloud.get_dataset, rec["name"], target=rec["name"])
                    present = meta is not None
                    labels = (meta or {}).get("labels")
                else:
                    present, labels = False, None
                ours = present and self._stamped_by_us(labels, rec.get("attempt_id"))          # this exact attempt produced it
                ours_other_attempt = present and not ours and self._stamped_by_us(labels)   # ours, but another attempt's resource
                if ours_other_attempt:
                    # the resource discharges only the attempt that produced it; this attempt's own outcome stays unknown
                    step["reconciled"] = "OTHER_ATTEMPT_PRESENT"
                    step["present_attempt"] = (labels or {}).get(ATTEMPT_LABEL)
                    rec["state"] = "OTHER_ATTEMPT_PRESENT"
                    rec["rechecks"] = rec.get("rechecks", 0) + 1
                    rec["last_checked"] = _now()
                elif present and ours:
                    step["reconciled"] = "PRESENT_ADOPTED"
                    if rec["kind"] == "entry" and rec["name"] not in self.owned.entries:
                        self.owned.entries.append(rec["name"])
                    if rec["kind"] == "dataset":
                        self.owned.dataset = rec["name"]
                    self._confirm(rec)
                    self._close_pending_journal(rec, "APPLIED", step["reconciled"])
                elif present:
                    step["reconciled"] = "FOREIGN_PRESERVED"
                    rec["state"] = "FOREIGN"
                    if not any(f["name"] == rec["name"] for f in self.owned.foreign):
                        self.owned.foreign.append({"kind": rec["kind"], "name": rec["name"], "observed_at": _now()})
                else:
                    outcome = None
                    if rec.get("attempt_id") and hasattr(self.cloud, "attempt_outcome"):
                        outcome = self._op("reconcile_pending_attempt", "terminal outcome of the create attempt (adapter bookkeeping)",
                                           self.cloud.attempt_outcome, rec["kind"], rec["name"], rec["attempt_id"], target=rec["name"])
                    step["attempt_outcome"] = outcome
                    if outcome == "NOT_APPLIED":
                        step["reconciled"] = "NOT_APPLIED_VERIFIED"
                        step["absent_verified"] = True
                        self._confirm(rec)
                        self._close_pending_journal(rec, "NOT_APPLIED", step["reconciled"])
                    else:                                   # unknown (or APPLIED-but-absent: contradictory, keep looking)
                        step["reconciled"] = "ABSENT_PENDING"
                        rec["state"] = "ABSENT_PENDING"
                        rec["rechecks"] = rec.get("rechecks", 0) + 1
                        rec["recheck_after_s"] = self.cfg.settle
                        rec["last_checked"] = _now()
            except Exception as e:  # noqa: BLE001
                step["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            steps.append(step)
        self._write_ownership("pending_reconciled")
        return steps

    def _close_pending_journal(self, rec: dict, state: str, observed: str) -> None:
        """Close only the journal entry of THIS attempt (matched by attempt_id), never every write aimed at the name."""
        for e in self.journal.entries:
            if not e.get("terminal") and e.get("attempt_id") == rec.get("attempt_id") and e.get("mutates") and not e.get("job_backed"):
                self.journal.reconcile(e, state, observed=observed)

    def cleanup(self) -> dict:
        steps: list[dict] = self._reconcile_pending()
        for name in list(self.owned.entries):
            step = {"resource": name, "kind": "entry", "deleted": False, "absent_verified": False}
            try:
                self._guard_entry(name)
                self._op("delete_entry", "delete owned entry", self.cloud.delete_entry, name, mutates=True, target=name)
                step["deleted"] = True
                step["absent_verified"] = self._op("readback_entry_absent", "GET owned entry after delete", self.cloud.get_entry, name, target=name) is None
                if step["absent_verified"]:
                    self.owned.entries.remove(name)              # verified gone: a rerun of cleanup (pending re-checks) does not delete it again
            except Exception as e:  # noqa: BLE001 - each step is attempted; the receipt says which failed
                step["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            steps.append(step)
        if self.owned.dataset:
            ds = self.owned.dataset
            step = {"resource": ds, "kind": "dataset", "deleted": False, "absent_verified": False}
            try:
                self._guard_dataset(ds)
                self._op("delete_dataset", "delete owned dataset (all owned tables)", self.cloud.delete_dataset, ds, mutates=True, target=ds)
                step["deleted"] = True
                step["absent_verified"] = self._op("readback_dataset_absent", "GET dataset after delete (absence = None)", self.cloud.get_dataset, ds, target=ds) is None
                if step["absent_verified"]:
                    self.owned.dataset = None
            except Exception as e:  # noqa: BLE001
                step["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            steps.append(step)
        # job-backed operations that raised are re-read under their own (project, location, job_id): resource deletion is
        # never evidence about a server job (Astra PR41 re-review R5). Still running / unreadable stays unresolved.
        job_steps = []
        for e in list(self.journal.entries):
            if not e.get("terminal") and e.get("job_backed"):
                self._reconcile_job_entry(e)
                job_steps.append({"seq": e["seq"], "role": e["role"], "job_id": e.get("job_id"), "state": e["state"], "observed": e.get("observed")})
        unresolved = self.journal.unresolved()
        pending = list(self.owned.pending)
        foreign = list(self.owned.foreign)
        self._write_ownership("cleanup")

        def step_ok(s: dict) -> bool:   # a pending write is closed by a stamped adoption (then deleted below) or by settled absence
            if s["kind"].startswith("pending_"):
                return "error" not in s and s.get("reconciled") in ("NOT_APPLIED_VERIFIED", "PRESENT_ADOPTED")
            return bool(s["deleted"] and s["absent_verified"])
        complete = bool(steps) and all(step_ok(s) for s in steps) and not unresolved and not pending and not foreign
        status = "COMPLETE" if complete else ("NOTHING_OWNED" if not steps and not unresolved and not pending and not foreign else "INCOMPLETE")
        receipt = {"status": status, "steps": steps, "job_reconciliation": job_steps, "at": _now(), "unresolved_jobs": len(unresolved), "pending": pending,
                   "foreign_preserved": foreign, "owner_stamp": self.owner_stamp,
                   "unresolved": [{"seq": e["seq"], "role": e["role"], "target": e.get("target"), "job_id": e.get("job_id"), "error": e.get("error")} for e in unresolved],
                   "note": "only exact run-owned (stamped) resources; no prefix or glob deletion; a missing absence readback, a pending create attempt "
                           "whose outcome is not established (absent is not non-applied; elapsed time is not an outcome), a resource present under a "
                           "foreign stamp, or a job whose server state was not read back is INCOMPLETE; rerun cleanup to re-check pending attempts"}
        (Path(self.journal.run_dir) / "cleanup.json").write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        self.journal.note("cleanup", **receipt)
        return receipt
