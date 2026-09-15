"""Publish in BigQuery, then consume through the connected path (2026-09-15): the RFC's full path in one invocation.

    author (operator)                                                         requester (sa:okf-receipt-restricted)
    compile pinned Acme bundle -> BigQuery: append rows -> full-row readback ->  Catalog discovery of that entry -> pin ->
    READY -> atomic head MERGE -> Catalog pin generated from the READY rows      READY publication (head observed) -> governed
                                                                               retrieval -> access + revocation -> receipt
                                                                               -> enforcing consumer

BigQuery is the publish and serving authority (RFC §04); the Catalog entry is the discovery projection written only
after the head advanced (§05 `BQ_COMMITTED` -> `KC_APPLIED`). The publish path is `catalog_lifecycle.Lifecycle` on a
run-owned, relational-only dataset (`okf_kp_publish_<run>`) and a run-owned entry; the consume half is the unchanged
`connected.run_connected` whose `CatalogConfig` names exactly that entry and dataset. Everything owned is deleted at the
end with absence read back. See docs/{intent,spec,plan}-publish-author-bq.md.

Modes. `--live` touches test-project-0728-467323 (live BigQuery, Dataplex Catalog, IAM, SDK receipt CLI). `--hermetic`
publishes into `HermeticCloud` (an in-memory CloudOps) and the consumer is built ONLY from what that publish wrote.

Honest limits: synthetic data; relational fallback, not GQL; content-addressed publication id (same id as the long-lived
spike publication, fresh rows/jobs/dataset); §05 simplified (no sync_id, deployment_heads, *_current views); n = 1.
"""
from __future__ import annotations

import argparse
import copy
import dataclasses
import datetime as _dt
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Optional

from . import BUNDLE_ID, DATASET, LOCATION, PROJECT, SOURCE_PIN
from . import catalog as C
from . import connected as E2E
from .catalog_lifecycle import Lifecycle, LifecycleConfig
from .compile import compile_bundle, validate_projection
from .journal import Journal

RUNNER_VERSION = "okf_bq_graph.publish_connected/0.1.0"
ROOT = E2E.ROOT
OUT_DIR = ROOT / "evidence" / "publish-connected"
ENTRY_LOCAL = "metrics/gross-margin"
CONCEPT_PATH = "metrics/gross-margin.md"
DATASET_STEM, ENTRY_STEM, PROFILE = "okf_kp_publish", "acme-retail-kp-publish", "okf-kp-publish/1"
HERMETIC_AUTHOR = "author@example.test"
SEC05_STATES = ("PLANNED", "PREPARING", "BQ_STAGED", "BQ_COMMITTED", "KC_APPLIED", "COMPLETE")
ROW_KEYS = ("publication_id", "bundle_id", "source_pin", "compiler_version", "source_manifest_sha256", "nodes_sha256", "edges_sha256",
            "node_count", "edge_count", "section_count", "validation_status", "validation_reasons", "created_at", "ready_at")
LABELS = dict(E2E.LABELS, **{
    "publish": "BigQuery is the publish authority: run-owned relational dataset, full-row readback, READY row, atomic head MERGE",
    "catalog_role": "discovery projection: the run-owned entry's pin is generated from the READY rows after the head advanced",
    "publication_id": "content-addressed from the pinned source: the same id the long-lived spike dataset holds, deployed "
                      "fresh (new dataset, rows and jobs); not a new knowledge revision",
    "sec05": "RFC §05 states recorded on a simplified protocol: one owned dataset with active_publication, no sync_id, "
             "deployment_heads or *_current views",
    "teardown": "the owned dataset and entry are deleted at the end (absence read back); job metadata stays readable",
})
VERDICT_RULE = ("E2E_PUBLISH_CONNECTED only when the author provenance holds, the BigQuery publication is READY on full-row "
                "readback, the head was observed switched to it, the Catalog pin generated from those rows parses OK, the "
                "publish journal has no unresolved job, the consumer resolved exactly that publication in that dataset, the "
                "connected run is E2E_CONNECTED, every author job ran as the author, the originals are unchanged and cleanup "
                "is COMPLETE; E2E_BROKEN when the connected run is broken, the consumer served another publication or "
                "dataset, or an author job ran as someone else; E2E_INCOMPLETE otherwise")


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _git(root: str, *args: str) -> Optional[str]:
    try:
        r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def lifecycle_config(run_id: str, timeout_s: float = 60.0) -> LifecycleConfig:
    return LifecycleConfig(run_id=run_id, timeout_s=timeout_s, dataset_stem=DATASET_STEM, entry_stem=ENTRY_STEM, profile=PROFILE)


# ----------------------------------------------------------------------------- journal that narrates the publish
class ProgressJournal(Journal):
    """The lifecycle journal, reporting every closed operation as it happens: BigQuery jobs with their ids, writes with
    their targets. This is what the tape shows for the publish beat."""

    def __init__(self, run_dir: str | os.PathLike, run_id: str, progress: Callable[..., None]):
        self._progress = progress
        super().__init__(run_dir, run_id)

    def _emit(self, e: dict) -> None:
        if e.get("job_id"):
            self._progress("bq_job", role=e["role"], job=e["job_id"], state=e["state"], rows=e.get("rows"))
        elif e.get("mutates"):
            self._progress("write", role=e["role"], target=e.get("target"), state=e["state"])

    def terminal(self, entry: dict, state: str, rows: Optional[int] = None, error: Optional[str] = None, **stats: Any) -> dict:
        out = super().terminal(entry, state, rows=rows, error=error, **stats)
        self._emit(out)
        return out

    def unknown(self, entry: dict, error: str, **stats: Any) -> dict:
        out = super().unknown(entry, error, **stats)
        self._emit(out)
        return out

    def reconcile(self, entry: dict, state: str, observed: Optional[str] = None, **stats: Any) -> dict:
        out = super().reconcile(entry, state, observed=observed, **stats)
        self._emit(out)
        return out


# ----------------------------------------------------------------------------- hermetic cloud
class HermeticCloud:
    """In-memory `CloudOps` with a server-side job registry (every job carries the author identity). Emulation: it
    proves the harness and the ordering, not the platform."""

    def __init__(self, principal: str = HERMETIC_AUTHOR, original_head: str = "pub_190192147fd7fd78"):
        self.principal = principal
        self.datasets: dict[str, dict] = {DATASET: {"active_publication": [{"bundle_id": BUNDLE_ID, "publication_id": original_head}]}}
        self.dataset_meta: dict[str, dict] = {DATASET: {"labels": {}}}
        self.entries: dict[str, dict] = {C.DEFAULT_ENTRY: C.sample_entry()}
        self.jobs: dict[str, dict] = {}
        self.ops: list[dict] = []
        self.tamper: Optional[Callable[[str, list], list]] = None   # (table, rows) -> rows, applied to readbacks
        self.keep_on_delete = False                                  # a delete that silently does nothing

    def _rec(self, op: str, target: str, timeout: float, mutates: bool = False, job_id: Optional[str] = None) -> None:
        if not (isinstance(timeout, (int, float)) and timeout > 0):
            raise ValueError("every cloud operation must be bounded")
        self.ops.append({"op": op, "target": target, "mutates": mutates, "job_id": job_id})

    def _job(self, job_id: str) -> dict:
        if not job_id or job_id in self.jobs:
            raise ValueError("job-backed operations need a unique driver-chosen id")
        self.jobs[job_id] = {"state": "DONE", "error": None, "user_email": self.principal}
        return {"job_id": job_id}

    def get_dataset(self, dataset, timeout):
        self._rec("get_dataset", dataset, timeout)
        return copy.deepcopy(self.dataset_meta.get(dataset, {"labels": {}})) if dataset in self.datasets else None

    def create_dataset(self, dataset, location, labels, attempt_id, timeout):
        self._rec("create_dataset", dataset, timeout, True)
        if dataset in self.datasets:
            raise RuntimeError(f"409 dataset {dataset} exists")
        self.datasets[dataset] = {}
        self.dataset_meta[dataset] = {"labels": dict(labels)}
        return {}

    def delete_dataset(self, dataset, timeout):
        self._rec("delete_dataset", dataset, timeout, True)
        if not self.keep_on_delete:
            self.datasets.pop(dataset, None)
            self.dataset_meta.pop(dataset, None)
        return {}

    def run_ddl(self, dataset, statement, job_id, timeout):
        table = statement.split("`")[1].split(".")[-1]
        self._rec("run_ddl", f"{dataset}.{table}", timeout, True, job_id)
        self.datasets[dataset].setdefault(table, [])
        return self._job(job_id)

    def load_rows(self, dataset, table, rows, job_id, timeout):
        self._rec("load_rows", f"{dataset}.{table}", timeout, True, job_id)
        self.datasets[dataset][table].extend(copy.deepcopy(rows))
        return self._job(job_id)

    def select_rows(self, dataset, table, where, job_id, timeout, exclude=()):
        self._rec("select_rows", f"{dataset}.{table}", timeout, job_id=job_id)
        self._job(job_id)
        rows = [r for r in self.datasets.get(dataset, {}).get(table, []) if all(r.get(k) == v for k, v in where.items())]
        rows = [{k: v for k, v in r.items() if k not in exclude} for r in copy.deepcopy(rows)]
        return self.tamper(table, rows) if self.tamper else rows

    def insert_row(self, dataset, table, row, job_id, timeout):
        self._rec("insert_row", f"{dataset}.{table}", timeout, True, job_id)
        self.datasets[dataset][table].append(copy.deepcopy(row))
        return self._job(job_id)

    def update_status(self, dataset, publication_id, status, job_id, timeout):
        self._rec("update_status", f"{dataset}.publications", timeout, True, job_id)
        for r in self.datasets[dataset]["publications"]:
            if r["publication_id"] == publication_id:
                r["validation_status"] = status
        return self._job(job_id)

    def merge_head(self, dataset, bundle_id, publication_id, job_id, timeout):
        self._rec("merge_head", f"{dataset}.active_publication", timeout, True, job_id)
        t = self.datasets[dataset]["active_publication"]
        t[:] = [r for r in t if r["bundle_id"] != bundle_id] + [{"bundle_id": bundle_id, "publication_id": publication_id}]
        return self._job(job_id)

    def job_state(self, job_id, timeout, project=None, location=None):
        self._rec("job_state", job_id, timeout)
        return copy.deepcopy(self.jobs.get(job_id))

    def cancel_job(self, job_id, timeout):
        self._rec("cancel_job", job_id, timeout)
        return {}

    def get_job(self, job_id, project=None, location=None):
        """`jobs.get` shape for the author identity read-back."""
        if job_id not in self.jobs:
            raise KeyError(f"404 job {job_id}")
        return SimpleNamespace(user_email=self.jobs[job_id]["user_email"], state=self.jobs[job_id]["state"])

    def get_entry(self, name, timeout):
        self._rec("get_entry", name, timeout)
        return copy.deepcopy(self.entries.get(name))

    def create_entry(self, name, body, attempt_id, timeout):
        self._rec("create_entry", name, timeout, True)
        if name in self.entries:
            raise RuntimeError(f"409 entry {name} exists")
        self.entries[name] = copy.deepcopy(body)
        return {}

    def attempt_outcome(self, kind, name, attempt_id, timeout):
        self._rec("attempt_outcome", name, timeout)
        return None

    def patch_entry(self, name, body, aspect_keys, timeout):
        self._rec("patch_entry", name, timeout, True)
        cur = self.entries[name]
        for k in aspect_keys:
            if k in body.get("aspects", {}):
                cur.setdefault("aspects", {})[k] = copy.deepcopy(body["aspects"][k])
            else:
                cur.get("aspects", {}).pop(k, None)
        return {}

    def delete_entry(self, name, timeout):
        self._rec("delete_entry", name, timeout, True)
        if not self.keep_on_delete:
            self.entries.pop(name, None)
        return {}

    def catalog_view(self, group: str) -> tuple[list, dict]:
        """What a Catalog list + get would return right now: pages of entry names under the group, and entry bodies."""
        names = sorted(n for n in self.entries if n.startswith(group + "/entries/"))
        return C.mock_pages(names, 100), {n: copy.deepcopy(self.entries[n]) for n in names}


# ----------------------------------------------------------------------------- consume environments
def hermetic_env_factory(sdk_root: str, runner: Callable = subprocess.run) -> Callable[[C.CatalogConfig, Any, dict], Any]:
    """The hermetic consumer sees only what the hermetic publish wrote: the owned dataset's rows and head, and the
    Catalog entries in `HermeticCloud`. The compiled projection supplies only non-row metadata (manifests, pins)."""

    def make(ccfg: C.CatalogConfig, cloud: HermeticCloud, projection: dict) -> Any:
        ds = cloud.datasets.get(ccfg.runtime_dataset) or {}
        P = projection["publication_id"]
        nodes = [{k: v for k, v in n.items() if k != "stale_after_ts"} for n in ds.get("nodes", []) if n.get("publication_id") == P]
        edges = [dict(e) for e in ds.get("edges", []) if e.get("publication_id") == P]
        heads = [r["publication_id"] for r in ds.get("active_publication", []) if r["bundle_id"] == ccfg.bundle_id]
        served = dict(copy.deepcopy(projection), nodes=nodes, edges=edges)
        pages, entries = cloud.catalog_view(ccfg.group)
        return E2E.HermeticEnv(served, sdk_root, ccfg, runner=runner, catalog_pages=pages, catalog_entries=entries,
                               head=heads[0] if len(heads) == 1 else None)

    return make


def live_env_factory(sdk_root: str, wait_s: int = 600, sdk_python: Optional[str] = None) -> Callable[[C.CatalogConfig, Any, dict], Any]:
    from . import chain as CH

    def make(ccfg: C.CatalogConfig, cloud: Any, projection: dict) -> Any:
        return E2E.LiveEnv(CH.sdk_publication(sdk_root), sdk_root, ccfg, wait_s=wait_s, sdk_python=sdk_python, catalog_resources=[ccfg.group])

    return make


# ----------------------------------------------------------------------------- checks
def consumed_check(out: dict, publication_id: str, dataset: str, entry: str, store_dataset: Optional[str]) -> dict:
    """Did the consumer serve exactly what this run published? Read from the connected run's in-memory (unmasked)
    approved case: its own Catalog read named the owned entry and a pin to (publication_id, owned dataset), and the store
    resolved that READY publication with the head observed on it."""
    ap = next((c for c in out.get("cases") or [] if c.get("case") == E2E.APPROVED), {})
    cat = ap.get("catalog") or {}
    pin = cat.get("pin") or {}
    pub = ap.get("publication") or {}
    head = pub.get("head") or {}
    catalog_ok = cat.get("status") == "OK"
    checks = {"catalog_ok": catalog_ok, "entry_is_owned": cat.get("entry") == entry, "pin_publication": pin.get("publication_id") == publication_id,
              "pin_dataset": pin.get("runtime_dataset") == dataset, "store_dataset": store_dataset == dataset,
              "publication_ok": pub.get("status") == "OK",
              "head_is_published": head.get("publication_id") == publication_id and head.get("matches_pin") is True}
    if all(checks.values()):
        status = "MATCH"
    elif catalog_ok and not all(checks[k] for k in ("entry_is_owned", "pin_publication", "pin_dataset", "store_dataset")):
        status = "MISMATCH"
    elif checks["publication_ok"] and not checks["head_is_published"]:
        status = "MISMATCH"
    else:
        status = "NOT_REACHED"
    return {"status": status, "checks": checks, "publication_id": publication_id, "dataset": dataset, "entry": entry,
            "observed": {"catalog": cat.get("status"), "pin_publication_id": pin.get("publication_id"), "pin_runtime_dataset": pin.get("runtime_dataset"),
                         "publication": pub.get("status"), "head": head.get("publication_id")}}


def author_identity(client: Any, jobs: list[dict], expected: Optional[str], checked_by: str) -> dict:
    from .principal import job_ref, roles_bound_to
    refs = [job_ref(j["job_id"], j.get("project"), j.get("location"), role=j.get("role")) for j in jobs
            if j.get("job_id") and j.get("state") in ("DONE", "ERROR", "CANCELLED")]
    out = roles_bound_to(client, [{"role": "author", "expected": expected, "required": True, "jobs": refs}])
    out["checked_by"] = checked_by
    return out


def verdict(rec: dict) -> tuple[str, Optional[str], dict]:
    pub = rec.get("publish") or {}
    con = rec.get("connected") or {}
    cons = rec.get("consumed") or {}
    ident = (pub.get("author_identity") or {}).get("status")
    checks = {"author": (rec.get("author") or {}).get("ok") is True,
              "ready": (pub.get("ready") or {}).get("state") == "READY",
              "head_switched": (pub.get("head") or {}).get("state") == "SWITCHED",
              "catalog_pin": (pub.get("catalog_pin") or {}).get("readback_status") == "OK",
              "publish_journal_resolved": pub.get("unresolved_jobs") == 0,
              "consumed": cons.get("status") == "MATCH",
              "connected": con.get("verdict") == "E2E_CONNECTED",
              "author_identity": ident == "BOUND",
              "originals": (pub.get("originals_recheck") or {}).get("status") == "UNCHANGED",
              "cleanup": (pub.get("cleanup") or {}).get("status") == "COMPLETE"}
    if all(checks.values()):
        return "E2E_PUBLISH_CONNECTED", None, checks
    if con.get("verdict") == "E2E_BROKEN":
        return "E2E_BROKEN", f"connected:{con.get('broken_at')}", checks
    if cons.get("status") == "MISMATCH":
        return "E2E_BROKEN", "consumed", checks
    if ident == "UNBOUND":
        return "E2E_BROKEN", "author_identity", checks
    if (pub.get("ready") or {}).get("state") not in (None, "READY") and rec.get("connected") is not None:
        return "E2E_BROKEN", "ready", checks
    return "E2E_INCOMPLETE", rec.get("stopped_at") or next(k for k, ok in checks.items() if not ok), checks


# ----------------------------------------------------------------------------- the run
def run_publish_connected(cloud: Any, make_env: Callable[[C.CatalogConfig, Any, dict], Any], sdk_root: str, acme_root: str,
                          out_dir: Path | str = OUT_DIR, mode: str = "hermetic", identity_client: Any = None,
                          expected_author: Optional[str] = None, timeout_s: float = 60.0, as_of: Optional[str] = None,
                          today: Optional[_dt.date] = None, inject: Optional[dict] = None,
                          progress: Callable[..., None] = lambda *a, **k: None, run_id: Optional[str] = None) -> dict:
    """`inject` (hermetic negatives only): `publish` -> Lifecycle.publish_relational inject_failure, `head` ->
    advance_head inject_failure, `pin_override` -> write_pin pin_override."""
    inject = inject or {}
    started = _now()
    run_id = run_id or f"kp-{started:%Y%m%dt%H%M%Sz}-{secrets.token_hex(2)}"
    run_dir = Path(out_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)            # create-or-fail: this invocation owns the directory
    cfg = lifecycle_config(run_id, timeout_s)
    rec: dict[str, Any] = {"runner": RUNNER_VERSION, "run_id": run_id, "mode": mode, "started_at": started.isoformat(), "labels": LABELS,
                           "verdict_rule": VERDICT_RULE, "owned": cfg.allowlist(), "state_trace": [], "publish": {"authority": "BigQuery"},
                           "connected": None, "consumed": {"status": "NOT_RUN"},
                           "rfc_path": ["author/publish (BigQuery)", "discover (Catalog)", "pin + retrieve fixed context",
                                        "evaluate current access (incl. revocation)", "validate the calculation (receipt)", "enforcing consumer"]}
    journal = ProgressJournal(run_dir / "publish", run_id, progress)
    life = Lifecycle(cfg, cloud, journal)
    pub = rec["publish"]
    trace = rec["state_trace"]

    def state(name: str, since: int, **kw: Any) -> None:
        ids = [e["job_id"] for e in journal.entries[since:] if e.get("job_id")]
        trace.append({"state": name, "at": _now().isoformat(), "jobs": ids, **kw})
        progress("state", state=name, jobs=len(ids), **{k: v for k, v in kw.items() if not isinstance(v, (dict, list))})

    stage = "author"
    try:
        progress("author", detail=f"compile the synthetic Acme bundle at {SOURCE_PIN[:7]} into an immutable projection")
        head_sha = _git(acme_root, "rev-parse", "HEAD")
        dirty = _git(acme_root, "status", "--porcelain", "--", ".")
        projection = compile_bundle(acme_root, BUNDLE_ID, SOURCE_PIN)
        v = validate_projection(projection)
        om = projection["output_manifest"]
        P = projection["publication_id"]
        author = {"source_pin": SOURCE_PIN, "checkout_head_matches_pin": head_sha == SOURCE_PIN, "bundle_clean": dirty == "",
                  "projection_valid": bool(v.get("valid")), "publication_id": P, "source_manifest_sha256": projection["source_manifest_sha256"],
                  "compiler_version": projection["compiler_version"], "nodes": om["nodes"], "edges": om["edges"],
                  "nodes_sha256": om["nodes_sha256"], "edges_sha256": om["edges_sha256"]}
        author["ok"] = author["checkout_head_matches_pin"] and author["bundle_clean"] and author["projection_valid"]
        rec["author"] = author
        state("PLANNED", len(journal.entries), publication_id=P, nodes=om["nodes"], edges=om["edges"])
        if not author["ok"]:
            raise _Stop("author")

        stage = "provision"
        n0 = len(journal.entries)
        progress("publish", detail=f"BigQuery: owned dataset {cfg.dataset} (relational tables only)")
        pub["originals"] = life.snapshot_originals()
        pub["provision"] = life.provision()
        pub["dataset"] = cfg.dataset
        state("PREPARING", n0, dataset=cfg.dataset)

        stage = "publish"
        n0 = len(journal.entries)
        progress("publish", detail="append immutable node/edge rows, read every row back, validate, mark READY")
        ready = life.publish_relational(projection, inject_failure=inject.get("publish"))
        row = ready.get("row") or {}
        pub["ready"] = {"state": ready["state"], "publication_id": P, "readback": ready.get("readback"),
                        "row": {k: row.get(k) for k in ROW_KEYS} if row else None}
        progress("ready", validation_status=ready["state"], publication=P, nodes=row.get("node_count"), edges=row.get("edge_count"),
                 sections=row.get("section_count"))
        if ready["state"] != "READY":
            raise _Stop("publish")
        state("BQ_STAGED", n0, publication_id=P, validation_status="READY")

        stage = "head"
        n0 = len(journal.entries)
        progress("publish", detail="atomic head switch: MERGE active_publication, only for a READY publication")
        head = life.advance_head(P, inject_failure=inject.get("head"))
        merge = next((e for e in reversed(journal.entries) if e.get("role") == "merge_head"), {})
        pub["head"] = dict(head, merge_job_id=merge.get("job_id"), merge_state=merge.get("state"))
        progress("head", state=head["state"], from_=str(head["from"]), to=head["to"], merge_job=merge.get("job_id"))
        if head["state"] != "SWITCHED":
            raise _Stop("head")
        state("BQ_COMMITTED", n0, head_from=head["from"], head_to=head["to"], merge_job_id=merge.get("job_id"))

        stage = "catalog_pin"
        n0 = len(journal.entries)
        progress("publish", detail="Catalog discovery projection: owned entry pinned to the READY rows (written after commit)")
        pin = life.write_pin(ENTRY_LOCAL, P, CONCEPT_PATH, pin_override=inject.get("pin_override"))
        pub["catalog_pin"] = pin
        progress("catalog_pin", entry=pin["entry"], readback=pin["readback_status"])
        if pin["readback_status"] != "OK":
            raise _Stop("catalog_pin")
        state("KC_APPLIED", n0, entry=pin["entry"])
        n0 = len(journal.entries)
        still = life.read_head()
        pub["head_after_catalog"] = still
        if still != P:
            raise _Stop("head_after_catalog")
        state("COMPLETE", n0, head=still)

        stage = "consume"
        ccfg = dataclasses.replace(cfg.catalog_config(ENTRY_LOCAL), allow_local_derived_source=False)
        progress("consume", detail="the restricted requester now discovers, pins, retrieves, is authorized, runs the receipt, and is revoked")
        env = make_env(ccfg, cloud, projection)
        out = E2E.run_connected(env, sdk_root, acme_root, out_dir=run_dir / "connected", as_of=as_of, cfg=ccfg, today=today, progress=progress)
        rec["connected"] = {"verdict": out.get("verdict"), "broken_at": out.get("broken_at"), "run_id": out.get("run_id"),
                            "run_dir": out.get("run_dir"), "summary": E2E.summary(out)}
        stage = "consumed"
        rec["consumed"] = consumed_check(out, P, cfg.dataset, ccfg.entry, getattr(env, "cfg", ccfg).runtime_dataset)
        progress("consumed", status=rec["consumed"]["status"], connected=out.get("verdict"))
    except _Stop as s:
        rec["stopped_at"] = s.stage
    except Exception as e:  # noqa: BLE001 - an unexpected failure still cleans up and writes its record
        rec["run_error"] = E2E._err(e)
        rec["stopped_at"] = stage
    finally:
        progress("teardown", detail="originals re-read; owned entry + dataset deleted; absence read back")
        try:
            pub["originals_recheck"] = life.verify_originals_unchanged()
        except Exception as e:  # noqa: BLE001
            pub["originals_recheck"] = dict(E2E._err(e), status="UNKNOWN")
        try:
            c = life.cleanup()
            pub["cleanup"] = {"status": c["status"], "steps": c["steps"], "unresolved_jobs": c["unresolved_jobs"],
                              "pending": len(c["pending"]), "foreign_preserved": len(c["foreign_preserved"])}
        except Exception as e:  # noqa: BLE001
            pub["cleanup"] = dict(E2E._err(e), status="INCOMPLETE")
        progress("cleanup", status=pub["cleanup"]["status"])
    pub["jobs"] = [{"seq": e["seq"], "role": e["role"], "job_id": e.get("job_id"), "state": e.get("state"), "target": e.get("target"),
                    "rows": e.get("rows"), "project": e.get("project"), "location": e.get("location"), "at": e.get("terminal_at") or e.get("reconciled_at")}
                   for e in journal.entries if e.get("job_backed")]
    pub["writes"] = [{"seq": e["seq"], "role": e["role"], "state": e.get("state"), "target": e.get("target")}
                     for e in journal.entries if e.get("mutates") and not e.get("job_backed")]
    pub["unresolved_jobs"] = len(journal.unresolved())
    try:
        pub["author_identity"] = author_identity(identity_client if identity_client is not None else cloud, pub["jobs"], expected_author,
                                                 "operator jobs.get" if mode == "live" else "hermetic job registry")
    except Exception as e:  # noqa: BLE001
        pub["author_identity"] = dict(E2E._err(e), status="UNKNOWN")
    rec["verdict"], rec["broken_at"], rec["checks"] = verdict(rec)
    rec["finished_at"] = _now().isoformat()
    try:
        rec["run_dir"] = str(run_dir.resolve().relative_to(ROOT))
    except ValueError:
        rec["run_dir"] = str(run_dir)
    _write(rec, run_dir, out_dir)
    return rec


class _Stop(Exception):
    def __init__(self, stage: str):
        super().__init__(stage)
        self.stage = stage


def _write(rec: dict, run_dir: Path, out_dir: Path | str) -> None:
    from .authz import redact
    text = json.dumps(redact(rec), indent=1, sort_keys=True, default=str)
    home = os.path.expanduser("~")
    if home and home != "/":
        text = text.replace(home, "~")
    name = f"publish_connected_{rec['mode']}.json"
    (run_dir / name).write_text(text + "\n", encoding="utf-8")
    final = Path(out_dir) / name
    tmp = final.with_name(f".{name}.{rec['run_id']}.tmp")
    tmp.write_text(text + "\n", encoding="utf-8")
    os.replace(tmp, final)


# ----------------------------------------------------------------------------- summary (CLI / agent)
def summary(rec: dict) -> dict:
    pub = rec.get("publish") or {}
    head = pub.get("head") or {}
    ready = pub.get("ready") or {}
    row = ready.get("row") or {}
    con = rec.get("connected") or {}
    return {"run_id": rec.get("run_id"), "mode": rec.get("mode"), "runner": rec.get("runner"), "verdict": rec.get("verdict"),
            "broken_at": rec.get("broken_at"),
            "publish": {"authority": "BigQuery", "dataset": pub.get("dataset"), "publication_id": ready.get("publication_id"),
                        "states": [s["state"] for s in rec.get("state_trace") or []], "ready": ready.get("state"),
                        "rows": {"nodes": row.get("node_count"), "edges": row.get("edge_count"), "sections": row.get("section_count")},
                        "head": {"state": head.get("state"), "from": head.get("from"), "to": head.get("to"), "merge_job_id": head.get("merge_job_id")},
                        "author_jobs": [{"role": j["role"], "job_id": j["job_id"], "state": j["state"]} for j in pub.get("jobs") or [] if j.get("job_id")],
                        "author_identity": (pub.get("author_identity") or {}).get("status"),
                        "catalog_pin": (pub.get("catalog_pin") or {}).get("readback_status"), "entry": (pub.get("catalog_pin") or {}).get("entry"),
                        "originals": (pub.get("originals_recheck") or {}).get("status"), "cleanup": (pub.get("cleanup") or {}).get("status")},
            "consumed": (rec.get("consumed") or {}).get("status"), "stopped_at": rec.get("stopped_at"),
            "connected": con.get("summary") or {"verdict": con.get("verdict")},
            "checks": rec.get("checks"), "labels": LABELS, "run_dir": rec.get("run_dir")}


def print_summary(s: dict) -> None:
    p = s["publish"]
    print(f"publish (BigQuery): states={' -> '.join(p['states'])} ready={p['ready']} rows={p['rows']} dataset={p['dataset']}")
    print(f"  head {p['head']['from']} -> {p['head']['to']} ({p['head']['state']}, merge job {p['head']['merge_job_id']})")
    print(f"  author jobs={len(p['author_jobs'])} identity={p['author_identity']} catalog pin={p['catalog_pin']} originals={p['originals']} cleanup={p['cleanup']}")
    c = s.get("connected") or {}
    for name, v in (c.get("cases") or {}).items():
        print(f"{name:32s} decision={str(v.get('decision')):9s} acceptance={v.get('acceptance')}")
    print(f"consumed={s['consumed']} connected={c.get('verdict')} answer={c.get('answer')}")
    print(f"verdict={s['verdict']}" + (f" broken_at={s['broken_at']}" if s.get("broken_at") else "") + f" run_dir={s['run_dir']}")


def main(argv: Optional[list[str]] = None) -> int:
    from . import chain as CH
    ap = argparse.ArgumentParser(description="publish in BigQuery, then the connected run against that publication (RFC full path)")
    ap.add_argument("--live", action="store_true", help="live GCP (test-project-0728-467323); default hermetic")
    ap.add_argument("--hermetic", action="store_true")
    ap.add_argument("--out", default=str(OUT_DIR))
    ap.add_argument("--sdk-root", default=CH.sdk_root())
    ap.add_argument("--acme-root", default=os.environ.get("OKF_ACME_ROOT", "/Users/haiyuancao/knowledge-catalog/okf/bundles/acme_retail"))
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--wait-s", type=int, default=600)
    ap.add_argument("--timeout-s", type=float, default=60.0, help="per publish cloud operation (harness limit)")
    ap.add_argument("--sdk-python", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.live and a.hermetic:
        ap.error("--live and --hermetic are exclusive")
    rec = run(a.live, a.sdk_root, a.acme_root, out_dir=a.out, as_of=a.as_of, wait_s=a.wait_s, timeout_s=a.timeout_s,
              sdk_python=a.sdk_python, progress=E2E.print_progress)
    s = summary(rec)
    if a.json:
        print(json.dumps(s, indent=1, sort_keys=True, default=str))
    else:
        print_summary(s)
    return 0 if rec["verdict"] == "E2E_PUBLISH_CONNECTED" else 1


def run(live: bool, sdk_root: str, acme_root: str, out_dir: Path | str = OUT_DIR, as_of: Optional[str] = None, wait_s: int = 600,
        timeout_s: float = 60.0, sdk_python: Optional[str] = None, progress: Callable[..., None] = lambda *a, **k: None) -> dict:
    """One full-path invocation with the default environments (what the CLI and the companion agent call)."""
    if live:
        from google.cloud import bigquery
        from .authz import operator
        from .catalog_live import LiveCloud
        client = bigquery.Client(project=PROJECT, location=LOCATION)
        cloud = LiveCloud(client, labels={"okf_spike": "bq_graph_20260905", "okf_role": "kp-publish"})
        return run_publish_connected(cloud, live_env_factory(sdk_root, wait_s, sdk_python), sdk_root, acme_root, out_dir=out_dir, mode="live",
                                     identity_client=client, expected_author=operator().split(":", 1)[-1] or None, timeout_s=timeout_s,
                                     as_of=as_of, progress=progress)
    cloud = HermeticCloud()
    return run_publish_connected(cloud, hermetic_env_factory(sdk_root), sdk_root, acme_root, out_dir=out_dir, mode="hermetic",
                                 identity_client=cloud, expected_author=cloud.principal, timeout_s=timeout_s, as_of=as_of, progress=progress)


if __name__ == "__main__":
    sys.exit(main())
