"""Exact retained-publication routing and payload consistency (plan U2 / KTD2-KTD3).

A validated Catalog pin names one (bundle, publication) and one seed Concept. This module:

* resolves exactly one retained READY publication row plus the exact visible seed row from the retained store, using
  parameterised values and the configured destination only, observing the current head without ever following it
  (`resolve_publication`; missing/non-READY/duplicate/absent-seed -> FAIL_STALE, source/manifest/digest disagreement
  -> PIN_MISMATCH);
* establishes the trusted compilation of the exact clean pinned source (`trusted_source`: git HEAD equals the pin,
  the bundle tree is clean, the compiled manifest/publication id equal the pin; anything unknown -> SOURCE_UNVERIFIED);
* verifies the actual retained rows and the actual retrieval/declaration payload against that trusted projection
  before anything is bound or executed (`verify_payload`): full-row comparison excluding only the storage-derived
  `stale_after_ts`, recomputed node/edge manifests, recomputed section text hashes, scoped path endpoints and edge
  continuity, section membership, SQL bytes, declaration bytes/fields. READY metadata, counts or digest labels alone
  never satisfy it.

Stores: `ProjectionStore` (hermetic, one or more compiled projections with READY state and a head pointer) and
`BigQueryStore` (parameterised SELECTs against the configured dataset). Both journal every read as a job before
waiting on it, including empty and failed reads.
"""
from __future__ import annotations

import copy
import hashlib
import json
import posixpath
import subprocess
from pathlib import Path
from typing import Any, Optional

from .model import node_id as _node_id, sha256_text, stable_json
from .oracle import SQL_FENCE_RE, Graph

STORAGE_DERIVED = ("stale_after_ts",)
MAX_BYTES_BILLED = 100 * 1024 * 1024
PUBLICATION_COLUMNS = ("publication_id", "bundle_id", "source_pin", "compiler_version", "source_manifest_sha256", "nodes_sha256",
                       "edges_sha256", "node_count", "edge_count", "section_count", "validation_status")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_rows(rows: list[dict]) -> list[dict]:
    """Rows as the compiler emits them: storage-derived fields removed, tags as lists, sorted by id."""
    out = []
    for r in rows:
        d = {k: v for k, v in dict(r).items() if k not in STORAGE_DERIVED}
        if "tags" in d and d["tags"] is None:
            d["tags"] = []
        out.append(d)
    key = "node_id" if out and "node_id" in out[0] else "edge_id"
    return sorted(out, key=lambda r: r.get(key, ""))


# ----------------------------------------------------------------------------- stores
class ProjectionStore:
    """Hermetic retained store: compiled projections as if published, each with a validation status and a head
    pointer per bundle. Test helpers mutate it to model stale, withdrawn, duplicated or tampered retained state."""
    engine = "hermetic-store"

    def __init__(self, journal: Any, dataset: str = "hermetic"):
        self.journal, self.dataset = journal, dataset
        self.publications: list[dict] = []          # publication rows (duplicates allowed to model bad state)
        self.nodes: dict[str, list[dict]] = {}
        self.edges: dict[str, list[dict]] = {}
        self.heads: dict[str, str] = {}
        self.graphs: dict[str, Graph] = {}

    def add(self, projection: dict, status: str = "READY") -> str:
        P = projection["publication_id"]
        om = projection["output_manifest"]
        self.publications.append({"publication_id": P, "bundle_id": projection["bundle_id"], "source_pin": projection["source_pin"],
                                  "compiler_version": projection["compiler_version"],
                                  "source_manifest_sha256": projection["source_manifest_sha256"],
                                  "nodes_sha256": om["nodes_sha256"], "edges_sha256": om["edges_sha256"],
                                  "node_count": om["nodes"], "edge_count": om["edges"],
                                  "section_count": sum(1 for n in projection["nodes"] if n["kind"] == "Section"),
                                  "validation_status": status})
        self.nodes[P] = [dict(n, stale_after_ts=None) for n in copy.deepcopy(projection["nodes"])]
        self.edges[P] = copy.deepcopy(projection["edges"])
        self.graphs[P] = Graph(projection)
        return P

    def set_head(self, bundle: str, pub: Optional[str]) -> None:
        if pub is None:
            self.heads.pop(bundle, None)
        else:
            self.heads[bundle] = pub

    def set_status(self, pub: str, status: str) -> None:
        for r in self.publications:
            if r["publication_id"] == pub:
                r["validation_status"] = status

    def remove(self, pub: str) -> None:
        self.publications = [r for r in self.publications if r["publication_id"] != pub]
        self.nodes.pop(pub, None); self.edges.pop(pub, None); self.graphs.pop(pub, None)

    def tamper_node(self, pub: str, node_id: str, **fields: Any) -> None:
        for n in self.nodes[pub]:
            if n["node_id"] == node_id:
                n.update(fields)

    def _job(self, role: str, desc: str, rows: list[dict]) -> dict:
        e = self.journal.intend(role, desc, self.engine, actual=False, dataset=self.dataset)
        self.journal.submitted(e, job_id=None)
        self.journal.terminal(e, "DONE" if rows else "EMPTY", rows=len(rows))
        return e

    def publication(self, bundle: str, pub: str) -> tuple[list[dict], dict]:
        rows = [dict(r) for r in self.publications if r["bundle_id"] == bundle and r["publication_id"] == pub]
        return rows, self._job("pin_resolution", "publications WHERE bundle_id=@b AND publication_id=@p", rows)

    def seed(self, node_id: str, bundle: str, pub: str) -> tuple[list[dict], dict]:
        rows = [{"node_id": n["node_id"], "path": n["path"], "file_sha256": n["file_sha256"], "kind": n["kind"],
                 "publication_id": n["publication_id"], "bundle_id": n["bundle_id"]}
                for n in self.nodes.get(pub, []) if n["node_id"] == node_id and n["bundle_id"] == bundle]
        return rows, self._job("seed_visibility", "nodes WHERE node_id=@id AND publication_id=@p AND bundle_id=@b", rows)

    def head(self, bundle: str) -> tuple[list[dict], dict]:
        rows = [{"bundle_id": bundle, "publication_id": self.heads[bundle]}] if bundle in self.heads else []
        return rows, self._job("observed_head", "active_publication WHERE bundle_id=@b (observation only)", rows)

    def rows(self, bundle: str, pub: str) -> tuple[list[dict], list[dict], dict]:
        nodes = [dict(n) for n in self.nodes.get(pub, []) if n["bundle_id"] == bundle]
        edges = [dict(e) for e in self.edges.get(pub, []) if e["bundle_id"] == bundle]
        return nodes, edges, self._job("payload_rows", "nodes/edges WHERE bundle_id=@b AND publication_id=@p (full retained rows)", nodes + edges)


class BigQueryStore:
    """Parameterised reads against the configured destination. The job is journaled at submission (job id known
    before result()) and closed at terminal state; a failed or empty read is still a journaled job."""
    engine = "bigquery"

    def __init__(self, client: Any, project: str, dataset: str, location: str, journal: Any,
                 max_bytes_billed: int = MAX_BYTES_BILLED, job_timeout_ms: int = 60_000, labels: Optional[dict] = None):
        self.client, self.project, self.dataset, self.location, self.journal = client, project, dataset, location, journal
        self.max_bytes_billed, self.job_timeout_ms = max_bytes_billed, job_timeout_ms
        self.labels = labels or {"okf_spike": "bq_graph_20260905"}

    @property
    def full(self) -> str:
        return f"{self.project}.{self.dataset}"

    def _run(self, role: str, desc: str, query: str, params: list) -> tuple[list[dict], dict]:
        from google.cloud import bigquery
        cfg = bigquery.QueryJobConfig(query_parameters=params, use_query_cache=False, maximum_bytes_billed=self.max_bytes_billed,
                                      labels=dict(self.labels, stage=role.replace("_", "-")[:63]))
        cfg.job_timeout_ms = self.job_timeout_ms
        e = self.journal.intend(role, desc, self.engine, actual=True, dataset=self.dataset, query_sha256=_sha(query.encode()))
        try:
            job = self.client.query(query, job_config=cfg, location=self.location)
        except Exception as ex:  # noqa: BLE001
            self.journal.terminal(e, "NOT_SUBMITTED", error=f"{type(ex).__name__}: {str(ex)[:300]}")
            raise
        self.journal.submitted(e, job_id=job.job_id, project=self.project, location=self.location)
        try:
            rows = [dict(r) for r in job.result()]
        except Exception as ex:  # noqa: BLE001
            self.journal.terminal(e, "ERROR", error=f"{type(ex).__name__}: {str(ex)[:300]}")
            raise
        self.journal.terminal(e, "DONE" if rows else "EMPTY", rows=len(rows), bytes_billed=getattr(job, "total_bytes_billed", None),
                              bytes_processed=getattr(job, "total_bytes_processed", None))
        return rows, e

    @staticmethod
    def _p(name: str, val: str) -> Any:
        from google.cloud import bigquery
        return bigquery.ScalarQueryParameter(name, "STRING", val)

    def publication(self, bundle: str, pub: str) -> tuple[list[dict], dict]:
        cols = ", ".join(PUBLICATION_COLUMNS)
        return self._run("pin_resolution", "retained publication row", f"SELECT {cols} FROM `{self.full}.publications` WHERE bundle_id = @b AND publication_id = @p",
                         [self._p("b", bundle), self._p("p", pub)])

    def seed(self, node_id: str, bundle: str, pub: str) -> tuple[list[dict], dict]:
        return self._run("seed_visibility", "exact seed node row",
                         f"SELECT node_id, path, file_sha256, kind, publication_id, bundle_id FROM `{self.full}.nodes` WHERE node_id = @id AND publication_id = @p AND bundle_id = @b",
                         [self._p("id", node_id), self._p("p", pub), self._p("b", bundle)])

    def head(self, bundle: str) -> tuple[list[dict], dict]:
        return self._run("observed_head", "active_publication (observation only; never followed)",
                         f"SELECT bundle_id, publication_id FROM `{self.full}.active_publication` WHERE bundle_id = @b", [self._p("b", bundle)])

    def rows(self, bundle: str, pub: str) -> tuple[list[dict], list[dict], dict]:
        nodes, e1 = self._run("payload_rows", "full retained node rows",
                              f"SELECT * EXCEPT(stale_after_ts) FROM `{self.full}.nodes` WHERE bundle_id = @b AND publication_id = @p ORDER BY node_id",
                              [self._p("b", bundle), self._p("p", pub)])
        edges, e2 = self._run("payload_rows", "full retained edge rows",
                              f"SELECT * FROM `{self.full}.edges` WHERE bundle_id = @b AND publication_id = @p ORDER BY edge_id",
                              [self._p("b", bundle), self._p("p", pub)])
        return nodes, edges, {"nodes_job": e1, "edges_job": e2}


# ----------------------------------------------------------------------------- pin resolution
def resolve_publication(store: Any, pin: Any) -> dict:
    """Exactly one READY retained publication + exact seed for the pin; head observed only. Never substitutes."""
    reasons: list[str] = []
    jobs: list[dict] = []
    out: dict[str, Any] = {"publication_id": pin.publication_id, "bundle_id": pin.bundle_id, "concept_id": pin.concept_id}
    try:
        pubs, j = store.publication(pin.bundle_id, pin.publication_id); jobs.append(j)
        seeds, j = store.seed(pin.concept_id, pin.bundle_id, pin.publication_id); jobs.append(j)
        heads, j = store.head(pin.bundle_id); jobs.append(j)
    except Exception as e:  # noqa: BLE001 - transport / IAM: blocked, not stale, not a pass
        return {"status": "ERROR", "error": f"{type(e).__name__}: {str(e)[:300]}", "reasons": ["store read failed"], "jobs": jobs, **out}
    if not pubs:
        reasons.append("PUBLICATION_MISSING")
    elif len(pubs) > 1:
        reasons.append("PUBLICATION_DUPLICATE")
    elif pubs[0].get("validation_status") != "READY":
        reasons.append(f"PUBLICATION_NOT_READY:{pubs[0].get('validation_status')}")
    if not seeds:
        reasons.append("SEED_MISSING")
    elif len(seeds) > 1:
        reasons.append("SEED_DUPLICATE")
    status = "FAIL_STALE" if reasons else "OK"
    pub = pubs[0] if len(pubs) == 1 else None
    seed = seeds[0] if len(seeds) == 1 else None
    checks: dict[str, Any] = {}
    if status == "OK":
        checks = {"source_pin": pub["source_pin"] == pin.source_pin,
                  "source_manifest_sha256": pub["source_manifest_sha256"] == pin.source_manifest_sha256,
                  "compiler_version": pub["compiler_version"] == pin.compiler_version,
                  "seed_path": seed["path"] == pin.concept_path,
                  "seed_file_sha256": seed["file_sha256"] == pin.concept_file_sha256,
                  "seed_kind": seed.get("kind") == "Concept",
                  "seed_scope": seed["publication_id"] == pin.publication_id and seed["bundle_id"] == pin.bundle_id}
        bad = sorted(k for k, v in checks.items() if not v)
        if bad:
            status, reasons = "PIN_MISMATCH", [f"PIN_MISMATCH:{k}" for k in bad]
    head_id = heads[0]["publication_id"] if len(heads) == 1 else None
    return {"status": status, "reasons": reasons, "checks": checks, "publication": pub, "seed": seed,
            "head": {"publication_id": head_id, "rows": len(heads), "matches_pin": head_id == pin.publication_id,
                     "note": "observed only; the requested pin is served or refused, the head is never followed"},
            "jobs": jobs, **out}


# ----------------------------------------------------------------------------- trusted source
def _git(root: str, *args: str) -> Optional[str]:
    try:
        r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def trusted_source(pin: Any, bundle_root: str, compile_fn: Any = None, derivation: Optional[dict] = None) -> dict:
    """Compile the exact clean pinned source and check it against the pin. `bundle_root` is the bundle directory inside
    the source checkout (its git repository must be at HEAD == pin.source_pin with a clean bundle tree). A local
    derivation (B2 owned P2) supplies `derivation={"base_pin", "tree_root", "manifest_sha256", ...}` and is compiled from
    that retained tree; it is labelled as derived and never as the clean upstream commit."""
    from .compile import compile_bundle
    compile_fn = compile_fn or compile_bundle
    checks: dict[str, Any] = {}
    if derivation is not None:
        root = derivation["tree_root"]
        checks["derived"] = True
        checks["derivation_base_matches_pin"] = pin.source_pin.startswith(derivation.get("base_pin", "") + "+local.") and bool(derivation.get("base_pin"))
        checks["tree_present"] = Path(root).is_dir()
        if not (checks["derivation_base_matches_pin"] and checks["tree_present"]):
            return {"status": "SOURCE_UNVERIFIED", "checks": checks, "projection": None}
    else:
        root = bundle_root
        head = _git(root, "rev-parse", "HEAD")
        rel = _git(root, "rev-parse", "--show-prefix") or ""
        dirty = _git(root, "status", "--porcelain", "--", ".")
        checks = {"derived": False, "git_head": head, "git_head_matches_pin": head == pin.source_pin,
                  "bundle_tree_clean": dirty == "" if dirty is not None else None, "bundle_git_prefix": rel.rstrip("/") or None,
                  "bundle_prefix_matches_source_root": (rel.rstrip("/") or None) == pin.source_root}
        if not (checks["git_head_matches_pin"] and checks["bundle_tree_clean"] is True and checks["bundle_prefix_matches_source_root"]):
            return {"status": "SOURCE_UNVERIFIED", "checks": checks, "projection": None}
    try:
        proj = compile_fn(root, pin.bundle_id, pin.source_pin)
    except Exception as e:  # noqa: BLE001
        return {"status": "SOURCE_UNVERIFIED", "checks": dict(checks, compile_error=f"{type(e).__name__}: {str(e)[:200]}"), "projection": None}
    seed_local = pin.concept_path[:-3]
    seed_node = next((n for n in proj["nodes"] if n["node_id"] == pin.concept_id), None)
    file_sha = next((m["sha256"] for m in proj["source_manifest"] if m["path"] == pin.concept_path), None)
    checks.update({"publication_id_matches_pin": proj["publication_id"] == pin.publication_id,
                   "source_manifest_matches_pin": proj["source_manifest_sha256"] == pin.source_manifest_sha256,
                   "compiler_version_matches_pin": proj["compiler_version"] == pin.compiler_version,
                   "seed_present": seed_node is not None and seed_node["kind"] == "Concept" and seed_node["local_id"] == seed_local,
                   "seed_file_sha256_matches_pin": file_sha == pin.concept_file_sha256 and (seed_node or {}).get("file_sha256") == pin.concept_file_sha256})
    ok = all(v is True for k, v in checks.items() if k.endswith(("_matches_pin", "_present", "_clean")) or k == "seed_present")
    return {"status": "OK" if ok else "SOURCE_UNVERIFIED", "checks": checks, "projection": proj if ok else None,
            "note": ("compiled from a retained local derivation of the pinned source; not the clean upstream commit" if derivation
                     else "compiled from the clean pinned checkout (git HEAD == pin, bundle tree clean)")}


# ----------------------------------------------------------------------------- payload consistency
def _fence(text: str) -> str:
    m = SQL_FENCE_RE.search(text or "")
    return m.group(1) if m else (text or "")


def verify_payload(store: Any, pin: Any, trusted: dict, result: dict, comp: Optional[dict], decl: Optional[dict],
                   expected_path: Optional[str] = None, seed_id: Optional[str] = None) -> dict:
    """Actual retained rows and the actual retrieval/declaration payload versus the trusted projection of the pin.
    Every check is recorded; any failure is INCONSISTENT and nothing downstream may bind or execute. `seed_id` is the
    concept the request was seeded with (default: the pin's concept; the injected declaration-mismatch adversary
    names its own, still inside the pinned publication)."""
    B, P = pin.bundle_id, pin.publication_id
    seed_id = seed_id or pin.concept_id
    if seed_id.split("|", 3)[:2] != [B, P]:
        return {"status": "INCONSISTENT", "checks": {"seed_scope": {"ok": False, "seed_id": seed_id}}, "jobs": [], "failed": ["seed_scope"]}
    checks: dict[str, Any] = {}
    jobs: list[Any] = []
    try:
        nodes, edges, j = store.rows(B, P); jobs.append(j)
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "error": f"{type(e).__name__}: {str(e)[:300]}", "checks": checks, "jobs": jobs}
    t_nodes, t_edges = canonical_rows(trusted["nodes"]), canonical_rows(trusted["edges"])
    r_nodes, r_edges = canonical_rows(nodes), canonical_rows(edges)
    checks["retained_node_rows"] = {"ok": r_nodes == t_nodes, "retained": len(r_nodes), "trusted": len(t_nodes),
                                    "first_diff": next((n["node_id"] for n, t in zip(r_nodes, t_nodes) if n != t), None) if len(r_nodes) == len(t_nodes) else "count"}
    checks["retained_edge_rows"] = {"ok": r_edges == t_edges, "retained": len(r_edges), "trusted": len(t_edges)}
    om = trusted["output_manifest"]
    checks["recomputed_manifests"] = {"ok": sha256_text(stable_json(r_nodes)) == om["nodes_sha256"] and sha256_text(stable_json(r_edges)) == om["edges_sha256"],
                                      "nodes_sha256": sha256_text(stable_json(r_nodes)), "edges_sha256": sha256_text(stable_json(r_edges)),
                                      "trusted_nodes_sha256": om["nodes_sha256"], "trusted_edges_sha256": om["edges_sha256"]}
    bad_secs = [n["node_id"] for n in r_nodes if n["kind"] == "Section" and sha256_text(n["text"] or "") != n["text_sha256"]]
    checks["section_text_hashes"] = {"ok": not bad_secs, "sections": sum(1 for n in r_nodes if n["kind"] == "Section"), "mismatched": bad_secs[:5]}
    tn = {n["node_id"]: n for n in t_nodes}
    links = {(e["src_id"], e["dst_id"]) for e in t_edges if e["relation"] == "LINKS_TO"}
    has_section = {(e["src_id"], e["dst_id"]) for e in t_edges if e["relation"] == "HAS_SECTION"}
    scope = result.get("scope") or {}
    checks["result_scope"] = {"ok": scope.get("publication_id") == P and scope.get("bundle_id") == B, "scope": {k: scope.get(k) for k in ("bundle_id", "publication_id")}}
    concepts = result.get("concepts") or []
    seed_ok = len(concepts) == 1 and concepts[0].get("concept_id", _node_id(B, P, "Concept", concepts[0].get("concept", ""))) == seed_id
    seed_node = tn.get(seed_id)
    if seed_ok and seed_node is not None:
        c = concepts[0]
        seed_ok = (c.get("path") == seed_node["path"] and c.get("title") == seed_node["title"] and c.get("type") == seed_node["type"]
                   and (c.get("lifecycle_status") or "stable") == (seed_node["status"] or "stable"))
    checks["seed_concept"] = {"ok": bool(seed_ok and seed_node is not None), "concept_id": concepts[0].get("concept_id") if concepts else None, "expected": seed_id}
    def check_comp(comp_r: dict) -> tuple[dict, dict]:
        cid = comp_r.get("computation_id") or _node_id(B, P, "Concept", comp_r.get("concept", ""))
        via = [_node_id(B, P, "Concept", x) for x in (comp_r.get("via") or [])]
        ok_nodes = all(v in tn and tn[v]["kind"] == "Concept" for v in via) and cid in tn
        ok_ends = bool(via) and via[0] == seed_id and via[-1] == cid and len(via) == (comp_r.get("concept_hops") or 0) + 1
        ok_edges = all((a, b) in links for a, b in zip(via, via[1:]))
        path = {"computation_id": cid, "nodes_in_trusted": ok_nodes, "endpoints": ok_ends, "edges_continuous": ok_edges, "via": via}
        sec = comp_r.get("section_id")
        t_sec = tn.get(sec) if sec else None
        sec_ok = t_sec is not None and t_sec["kind"] == "Section" and (cid, sec) in has_section and (t_sec["title"] or "").startswith("Computation")
        t_sql = _fence(t_sec["text"]) if t_sec is not None else None
        sql_ok = bool(comp_r.get("sql")) and comp_r.get("sql") == t_sql and comp_r.get("sql_sha256") == hashlib.sha256((comp_r.get("sql") or "").encode()).hexdigest()
        t_comp = tn.get(cid) or {}
        fields_ok = (comp_r.get("path") == t_comp.get("path") and comp_r.get("runtime") == t_comp.get("runtime")
                     and (comp_r.get("status") or "stable") == (t_comp.get("status") or "stable") and comp_r.get("runtime_verdict") == "NOT_EXECUTED")
        item = {"computation_id": cid, "section_membership": sec_ok, "sql_bytes": sql_ok, "fields": fields_ok,
                "trusted_sql_sha256": hashlib.sha256((t_sql or "").encode()).hexdigest() if t_sql is not None else None}
        return path, item

    def comp_ok(path: dict, item: dict) -> bool:
        return (path["nodes_in_trusted"] and path["endpoints"] and path["edges_continuous"]
                and item["section_membership"] and item["sql_bytes"] and item["fields"])

    path_checks, comp_checks = [], []
    for comp_r in result.get("computations") or []:
        path, item = check_comp(comp_r)
        path_checks.append(path); comp_checks.append(item)
    checks["paths"] = {"ok": bool(path_checks) and all(p["nodes_in_trusted"] and p["endpoints"] and p["edges_continuous"] for p in path_checks), "items": path_checks}
    checks["computations"] = {"ok": bool(comp_checks) and all(c["section_membership"] and c["sql_bytes"] and c["fields"] for c in comp_checks), "items": comp_checks}
    if comp is not None:
        # the selected computation object is re-verified byte for byte: a change after preflight (SQL, section, path)
        # under an unchanged id/label fails here even if the result list still agrees with the trusted projection
        s_path, s_item = check_comp(comp)
        cid = s_path["computation_id"]
        t_comp = tn.get(cid) or {}
        checks["selected_computation"] = {"ok": cid in tn and comp_ok(s_path, s_item)
                                                and (expected_path is None or comp.get("path") == expected_path == t_comp.get("path"))
                                                and any(c["computation_id"] == cid for c in comp_checks),
                                          "computation_id": cid, "path": comp.get("path"), "path_check": s_path, "bytes_check": s_item}
    if decl is not None:
        cid = decl.get("node_id")
        t_comp = tn.get(cid) or {}
        t_attrs = json.loads(t_comp.get("attrs") or "{}") if t_comp else {}
        src_sha = next((m["sha256"] for m in trusted.get("source_manifest", []) if m["path"] == t_comp.get("path")), None)
        checks["declaration"] = {"ok": (decl.get("status") == "OK" and cid in tn and comp is not None and cid == comp.get("computation_id")
                                        and decl.get("file_sha256") == t_comp.get("file_sha256") == src_sha and bool(src_sha)
                                        and decl.get("type") == t_comp.get("type") and decl.get("runtime") == t_comp.get("runtime")
                                        and decl.get("path") == t_comp.get("path") and decl.get("stale_after") == t_comp.get("stale_after")
                                        and (decl.get("lifecycle_status") or "stable") == (t_comp.get("status") or "stable")
                                        and decl.get("parameters") == t_attrs.get("parameters")),
                                 "node_id": cid, "file_sha256": decl.get("file_sha256"), "trusted_file_sha256": t_comp.get("file_sha256"),
                                 "source_file_sha256": src_sha}
    ok = all(v["ok"] for v in checks.values())
    return {"status": "CONSISTENT" if ok else "INCONSISTENT", "checks": checks, "jobs": jobs,
            "failed": sorted(k for k, v in checks.items() if not v["ok"]),
            "note": "full retained rows, recomputed manifests/section hashes, scoped path endpoints/edges, SQL and declaration bytes "
                    "compared to the trusted compilation of the pinned source; labels and digests alone are not accepted"}
