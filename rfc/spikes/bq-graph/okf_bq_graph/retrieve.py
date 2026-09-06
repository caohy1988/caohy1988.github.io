"""Governed retrieval, impact and stub backlog (spec §4, Task 4).

engine = "gql"      : GA SQL VECTOR_SEARCH seed + GQL walk/context (needs Enterprise reservation)
engine = "fallback" : same seed + relational joins (on-demand; labelled FALLBACK)
engine = "oracle"   : in-process reference over a projection (no cloud)

`clients` is caller-supplied: {"bq": bigquery.Client under the requester's credentials,
"ds": dataset, "engine": ..., "projection": dict (oracle only)}. Any permission error
fails closed with status DENIED and no content.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import time
from typing import Any, Optional

from google.api_core import exceptions as gexc
from google.cloud import bigquery

from . import DATASET, LOCATION, PROJECT
from .model import node_id as _node_id
from .lifecycle import window_executor
from .oracle import Graph, SQL_FENCE_RE, parse_ts
from .publish import sql, resolve_pointer

FORCED = "forced:"
CACHE_DEPENDENCY_VERSION = 2  # prior entries may omit the second traversal edge


def _p(name: str, typ: str, val: Any) -> bigquery.ScalarQueryParameter:
    return bigquery.ScalarQueryParameter(name, typ, val)


class Timer:
    def __init__(self) -> None:
        self.t0 = time.monotonic()
        self.stages: dict[str, float] = {}
        self.jobs: list[dict] = []

    def stage(self, name: str, start: float) -> None:
        self.stages[name] = round((time.monotonic() - start) * 1000, 1)

    def job(self, name: str, job: bigquery.QueryJob) -> None:
        st = getattr(job, "_properties", {}).get("statistics", {})
        self.jobs.append({"stage": name, "job_id": job.job_id, "slot_ms": job.slot_millis,
                          "bytes_processed": job.total_bytes_processed, "bytes_billed": job.total_bytes_billed,
                          "cache_hit": job.cache_hit, "reservation_id": st.get("reservation_id"),
                          "edition": st.get("edition"),
                          "created": job.created.isoformat() if job.created else None,
                          "started": job.started.isoformat() if job.started else None,
                          "ended": job.ended.isoformat() if job.ended else None})

    def done(self) -> dict:
        return {"stages_ms": self.stages, "total_ms": round((time.monotonic() - self.t0) * 1000, 1), "jobs": self.jobs}


EDITION_ERR = "require a reservation with Enterprise"


def _run(clients: dict, name: str, query: str, params: list, timer: Timer) -> list[dict]:
    """One BigQuery job. A job that is mis-routed to on-demand during assignment propagation (edition error)
    is retried at most twice; the retry count is recorded so the benchmark can report it."""
    cfg = bigquery.QueryJobConfig(query_parameters=params, use_query_cache=clients.get("use_cache", False),
                                  labels={"okf_spike": "bq_graph_20260905", "stage": name})
    t = time.monotonic()
    retries = 0
    while True:
        job = clients["bq"].query(query, job_config=cfg, location=LOCATION)
        try:
            rows = [dict(r) for r in job.result()]
            break
        except gexc.GoogleAPICallError as e:
            if EDITION_ERR in str(e) and retries < 2 and clients.get("engine") == "gql":
                retries += 1; time.sleep(2); continue
            raise
    timer.stage(name, t)
    timer.job(name, job)
    if retries:
        timer.jobs[-1]["routing_retries"] = retries
    return rows


def _denied(reason: str, scope: dict, timer: Timer, status: str = "DENIED") -> dict:
    return {"status": status, "concepts": [], "paths": [], "computations": [], "warnings": [reason],
            "scope": scope, "timing": timer.done()}


def _cache_key(ds, bundle_id, publication_id, requester, query, as_of, top_k) -> str:
    # exact normalized as-of instant: two requests straddling a stale_after boundary never share an entry
    inst = parse_ts(as_of).astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return "|".join([ds, bundle_id, publication_id, str(requester), query, inst, str(top_k)])


def _recheck(clients: dict, full: str, publication_id: str, node_ids: list[str], edge_ids: list[str], timer: Timer) -> bool:
    """Every disclosure re-checks CURRENT authorization under the requester's own client: every previously
    disclosed node AND every edge that authorized the disclosed paths/provenance must still be visible.
    Unknown/failed check blocks. (Edge-only revocation previously slipped through: Astra P1#4.)"""
    try:
        rows = _run(clients, "recheck", f"""
            SELECT (SELECT COUNT(DISTINCT node_id) FROM `{full}.nodes` WHERE node_id IN UNNEST(@nids) AND publication_id = @p) AS n,
                   (SELECT COUNT(DISTINCT edge_id) FROM `{full}.edges` WHERE edge_id IN UNNEST(@eids) AND publication_id = @p) AS e""",
                    [bigquery.ArrayQueryParameter("nids", "STRING", node_ids), bigquery.ArrayQueryParameter("eids", "STRING", edge_ids),
                     _p("p", "STRING", publication_id)], timer)
        return rows[0]["n"] == len(node_ids) and rows[0]["e"] == len(edge_ids)
    except Exception:  # noqa: BLE001 - unknown policy-check state blocks
        return False


def _refresh(out: dict, as_of: str) -> dict:
    """Re-evaluate every freshness verdict at the caller's as_of (cached replay must not carry an old verdict)."""
    for c in out.get("concepts", []):
        c["freshness"] = _freshness(c["freshness"].get("stale_after"), as_of)
    for c in out.get("computations", []):
        c["freshness"] = _freshness(c["freshness"].get("stale_after"), as_of)
    out["scope"] = dict(out.get("scope", {}), as_of=as_of)
    return out


def _cache_dependencies(seeds, walks, ctx, seed_nodes, bundle_id, publication_id):
    """Cache only when every path/context row supplies its full authorization dependencies.

    Context for seeds and reached computations cannot reconstruct an omitted edge
    leaving an intermediate node. Never substitute context edges for walk edges.
    """
    prefix = f"{bundle_id}|{publication_id}|"

    def scoped_id(value):
        return isinstance(value, str) and value.startswith(prefix) and len(value) > len(prefix)

    nodes = {n["node_id"] for n in seed_nodes}
    nodes.update(s["concept_id"] for s in seeds)
    nodes.update(section["section_id"] for s in seeds for section in s["sections"])
    edges = set()
    for ws in walks.values():
        for w in ws:
            hops, path_edges = w.get("concept_hops"), w.get("edge_ids")
            if (type(hops) is not int or hops not in (1, 2)
                    or not isinstance(path_edges, (list, tuple)) or len(path_edges) != hops
                    or not all(scoped_id(edge) for edge in path_edges)
                    or len(set(path_edges)) != hops):
                return None
            path_nodes = w.get("hop_ids")  # relational fallback returns scoped node IDs
            if path_nodes is None:
                local_ids = w.get("hop_concepts")  # GQL returns ordered local concept IDs
                if not isinstance(local_ids, (list, tuple)) or not all(isinstance(x, str) and x for x in local_ids):
                    return None
                path_nodes = [_node_id(bundle_id, publication_id, "Concept", x) for x in local_ids]
            if (not isinstance(path_nodes, (list, tuple)) or len(path_nodes) != hops + 1
                    or not all(scoped_id(node) for node in path_nodes)
                    or path_nodes[0] != w["seed_id"] or path_nodes[-1] != w["computation_id"]):
                return None
            nodes.update(path_nodes)
            edges.update(path_edges)
    for row in ctx:
        if not scoped_id(row.get("edge_id")):
            return None
        nodes.update((row["concept_id"], row["other_id"]))
        edges.add(row["edge_id"])
    if not all(scoped_id(node) for node in nodes):
        return None
    return sorted(nodes), sorted(edges)


def retrieve(query: str, bundle_id: str, publication_id: str, requester: Any, as_of: str,
             clients: dict, top_k: int = 5) -> dict:
    timer = Timer()
    engine = clients.get("engine", "gql")
    ds = clients.get("ds", DATASET)
    full = f"{PROJECT}.{ds}"
    scope: dict[str, Any] = {"bundle_id": bundle_id, "publication_id": publication_id, "engine": engine,
                             "requester": str(requester), "as_of": as_of, "top_k": top_k}
    if engine == "oracle":
        return _retrieve_oracle(query, bundle_id, publication_id, as_of, clients, top_k, scope, timer)
    cache = clients.get("cache")
    ckey = _cache_key(ds, bundle_id, publication_id, requester, query, as_of, top_k) if cache is not None else None
    if ckey is not None and ckey in cache and publication_id != "active":
        cached = cache[ckey]
        if cached.get("dependency_version") == CACHE_DEPENDENCY_VERSION:
            if _recheck(clients, full, publication_id, cached["disclosed_ids"], cached["disclosed_edge_ids"], timer):
                out = _refresh(json.loads(json.dumps(cached["result"])), as_of)
                out["scope"] = dict(out["scope"], cache="HIT_RECHECKED"); out["timing"] = timer.done()
                return out
            return _denied("cached replay: current authorization check failed or unknown", dict(scope, cache="HIT_DENIED"), timer)
        cache.pop(ckey, None)  # legacy entries must rerun governed retrieval, not recheck partial dependencies
    try:
        # resolve pointer once; pin for seed, walk and SQL fetch
        if publication_id == "active":
            t = time.monotonic()
            publication_id = resolve_pointer(clients["bq"], bundle_id, ds)
            timer.stage("pointer", t)
            if not publication_id:
                return _denied("no active publication", scope, timer, "NO_PUBLICATION")
            scope["publication_id"] = publication_id
        warnings: list[str] = []
        # --- seed
        if query.startswith(FORCED):
            local = query[len(FORCED):]
            local = local[:-3] if local.endswith(".md") else local
            seeds = [{"concept_id": _node_id(bundle_id, publication_id, "Concept", local), "sections": [], "forced": True}]
            warnings.append("forced seed: harness-only deterministic override, not a semantic ranking")
            timer.stage("seed", time.monotonic())
        else:
            rows = _run(clients, "seed", sql("seed.sql", full),
                        [_p("query", "STRING", query), _p("bundle_id", "STRING", bundle_id),
                         _p("publication_id", "STRING", publication_id), _p("top_k", "INT64", top_k)], timer)
            by_concept: dict[str, dict] = {}
            for r in rows:
                if not r["section_id"].startswith(f"{bundle_id}|{publication_id}|"):
                    return _denied("seed outside pinned scope", scope, timer, "MIXED_PUBLICATION")
                c = by_concept.setdefault(r["concept_id"], {"concept_id": r["concept_id"], "sections": [], "forced": False})
                c["sections"].append({"section_id": r["section_id"], "heading": r["heading"], "distance": r["distance"]})
            seeds = list(by_concept.values())
        if not seeds:
            return {"status": "NO_SEED", "concepts": [], "paths": [], "computations": [], "warnings": warnings,
                    "scope": scope, "timing": timer.done()}
        # --- walk (GQL or relational fallback), one job per seed concept
        walk_sql = sql("governed.sql" if engine == "gql" else "fallback.sql", full)
        walks: dict[str, list[dict]] = {s["concept_id"]: [] for s in seeds}
        for w in _run(clients, "walk", walk_sql,
                      [bigquery.ArrayQueryParameter("seeds", "STRING", [s["concept_id"] for s in seeds]),
                       _p("bundle_id", "STRING", bundle_id), _p("publication_id", "STRING", publication_id)], timer):
            walks.setdefault(w["seed_id"], []).append(w)
        # --- context: verifiers, provenance, links, sections (+ section text) for seeds and reached computations
        ids = sorted({s["concept_id"] for s in seeds} | {w["computation_id"] for ws in walks.values() for w in ws})
        ctx_sql = (sql("context.sql", full) if engine == "gql" else _context_fallback(full))
        ctx_sql = f"""SELECT g.*, n.text AS other_text, n.text_sha256 AS other_text_sha256, n.stale_after AS other_stale_after,
                             n.path AS other_path, n.runtime AS other_runtime
                      FROM ({ctx_sql.replace('ORDER BY concept_id, relation, other_id', '')}) g
                      LEFT JOIN `{full}.nodes` n ON n.node_id = g.other_id AND n.publication_id = @publication_id
                      ORDER BY concept_id, relation, other_id"""
        nodes_sql = f"""SELECT node_id, local_id, path, title, type, status, stale_after, stub, runtime
                        FROM `{full}.nodes` WHERE node_id IN UNNEST(@ids) AND publication_id = @publication_id"""
        with window_executor(clients["bq"], max_workers=2) as ex:   # two independent jobs; latency counts the longer one
            f_ctx = ex.submit(_run, clients, "context", ctx_sql,
                              [bigquery.ArrayQueryParameter("concept_ids", "STRING", ids), _p("publication_id", "STRING", publication_id)], timer)
            f_nodes = ex.submit(_run, clients, "nodes", nodes_sql,
                                [bigquery.ArrayQueryParameter("ids", "STRING", ids), _p("publication_id", "STRING", publication_id)], timer)
            ctx, seed_nodes = f_ctx.result(), f_nodes.result()
    except (gexc.Forbidden, gexc.Unauthorized) as e:
        return _denied(f"authorization error: {type(e).__name__}", scope, timer)
    except gexc.NotFound as e:
        return _denied(f"not found (treated as denied): {type(e).__name__}", scope, timer)
    # --- assembly (local)
    t = time.monotonic()
    out = _assemble(seeds, walks, ctx, seed_nodes, as_of, warnings, scope, engine)
    timer.stage("assembly", t)
    out["timing"] = timer.done()
    if ckey is not None and out["status"] == "OK":
        dependencies = _cache_dependencies(seeds, walks, ctx, seed_nodes, bundle_id, publication_id)
        if dependencies is None:
            out["scope"] = dict(out["scope"], cache="BYPASS_INCOMPLETE_DEPENDENCIES")
            return out
        disclosed, edge_ids = dependencies
        cache[ckey] = {"dependency_version": CACHE_DEPENDENCY_VERSION, "disclosed_ids": disclosed,
                       "disclosed_edge_ids": edge_ids, "result": json.loads(json.dumps(out, default=str))}
        out["scope"] = dict(out["scope"], cache="MISS_STORED")
    return out


def _context_fallback(full: str) -> str:
    return f"""
    SELECT c.node_id AS concept_id, e.edge_id AS edge_id, e.relation, e.declaration AS edge_declaration, e.authored_at AS edge_at,
           e.resolution AS edge_resolution, e.inferred AS edge_inferred, o.node_id AS other_id, o.kind AS other_kind,
           o.local_id AS other_local_id, o.title AS other_title, o.type AS other_type, o.status AS other_status,
           o.actor_kind AS other_actor_kind, o.stub AS other_stub
    FROM `{full}.nodes` c
    JOIN `{full}.edges` e ON e.src_id = c.node_id AND e.publication_id = @publication_id
         AND e.relation IN ('VERIFIED_BY', 'GENERATED_BY', 'DERIVES_FROM', 'LINKS_TO', 'HAS_SECTION')
    JOIN `{full}.nodes` o ON o.node_id = e.dst_id AND o.publication_id = @publication_id
    WHERE c.node_id IN UNNEST(@concept_ids) AND c.publication_id = @publication_id
    ORDER BY concept_id, relation, other_id"""


def _freshness(stale_after: Optional[str], as_of: str) -> dict:
    if not stale_after:
        return {"verdict": "UNKNOWN_DEADLINE", "stale_after": None}
    try:
        return {"verdict": "STALE" if parse_ts(as_of) >= parse_ts(stale_after) else "FRESH", "stale_after": stale_after}
    except ValueError:
        return {"verdict": "UNKNOWN_DEADLINE", "stale_after": stale_after, "reason": "unparseable"}


def _assemble(seeds, walks, ctx, seed_nodes, as_of, warnings, scope, engine) -> dict:
    nodes = {n["node_id"]: n for n in seed_nodes}
    by_c: dict[str, list[dict]] = {}
    for r in ctx:
        by_c.setdefault(r["concept_id"], []).append(r)
    local = lambda i: i.split("|", 3)[3]

    def trust(cid: str) -> tuple[str, list[dict]]:
        vs = [r for r in by_c.get(cid, []) if r["relation"] == "VERIFIED_BY"]
        kinds = [r["other_actor_kind"] for r in vs]
        tier = "unverified" if not kinds else ("human-reviewed" if "human" in kinds else "machine-confirmed")
        return tier, sorted(({"by": r["other_title"], "kind": r["other_actor_kind"], "at": r["edge_at"]} for r in vs),
                            key=lambda x: (x["at"] or "", x["by"]))

    def sanctioned(cid: str) -> Optional[dict]:
        secs = [r for r in by_c.get(cid, []) if r["relation"] == "HAS_SECTION" and (r["other_title"] or "").startswith("Computation")]
        secs.sort(key=lambda r: r["other_id"])
        if not secs:
            return None
        text = secs[0]["other_text"] or ""
        m = SQL_FENCE_RE.search(text)
        s = m.group(1) if m else text
        return {"section_id": secs[0]["other_id"], "sql": s, "sql_sha256": hashlib.sha256(s.encode()).hexdigest(),
                "section_text_sha256": secs[0]["other_text_sha256"]}

    concepts, paths, computations = [], [], []
    for s in seeds:
        cid = s["concept_id"]
        n = nodes.get(cid)
        if n is None:
            warnings.append(f"seed {local(cid)} not found in pinned publication")
            continue
        tier, vers = trust(cid)
        prov = [{"resource": r["other_local_id"][4:] if r["other_local_id"].startswith("src:") else r["other_local_id"],
                 "title": r["other_title"], "declaration": r["edge_declaration"], "resolution": r["edge_resolution"],
                 "source_id": r["other_id"],
                 "note": "declaration-scoped signals (usage_count/window) and resolves_to are not exposed as graph properties; fetch from edges/nodes tables if needed"}
                for r in by_c.get(cid, []) if r["relation"] == "DERIVES_FROM"]
        replacement = None
        if (n["status"] or "stable") == "deprecated":
            cands = sorted({r["other_local_id"] for r in by_c.get(cid, []) if r["relation"] == "LINKS_TO"
                            and r["other_type"] == n["type"] and (r["other_status"] or "stable") == "stable" and not r["other_stub"]})
            if len(cands) == 1:
                replacement = {"concept": cands[0], "label": "inferred", "reason": "unique stable same-type LINKS_TO candidate; no supersedes declaration"}
            elif cands:
                replacement = {"concept": None, "label": "AMBIGUOUS", "candidates": cands}
            else:
                replacement = {"concept": None, "label": "NONE"}
        concepts.append({"concept": local(cid), "concept_id": cid, "path": n["path"], "title": n["title"], "type": n["type"],
                         "lifecycle_status": n["status"] or "stable", "trust_tier": tier, "verifications": vers,
                         "freshness": _freshness(n["stale_after"], as_of), "provenance": sorted(prov, key=lambda x: x["declaration"]),
                         "replacement": replacement, "matched_sections": s["sections"], "forced": s["forced"]})
        best: dict[str, dict] = {}
        for w in walks.get(cid, []):
            k = w["computation_id"]
            if k not in best or w["concept_hops"] < best[k]["concept_hops"]:
                best[k] = w
        for w in sorted(best.values(), key=lambda x: (x["concept_hops"], x["computation_id"])):
            ac = nodes.get(w["computation_id"], {})
            ct, _ = trust(w["computation_id"])
            sq = sanctioned(w["computation_id"])
            via = [local(x) for x in w["hop_ids"]] if "hop_ids" in w else list(w.get("hop_concepts") or [])
            if sq is None:
                warnings.append("SOURCE_DENIED_OR_MISSING: sanctioned computation reachable but its Computation section is not visible; SQL withheld")
            computations.append({"seed": local(cid), "concept": local(w["computation_id"]), "computation_id": w["computation_id"],
                                 "section_id": sq["section_id"] if sq else None, "path": w["computation_path"],
                                 "concept_hops": w["concept_hops"], "via": via, "status": w["computation_status"],
                                 "runtime": ac.get("runtime"), "trust_tier": ct, "freshness": _freshness(ac.get("stale_after"), as_of),
                                 "sql": sq["sql"] if sq else None, "sql_sha256": sq["sql_sha256"] if sq else None,
                                 "runtime_verdict": "NOT_EXECUTED"})
            paths.append({"seed": local(cid), "concept_hops": w["concept_hops"], "via": via})
    status = "OK" if concepts else "NO_SEED"
    return {"status": status, "concepts": concepts, "paths": paths, "computations": computations,
            "warnings": warnings + ([] if engine == "gql" else ["FALLBACK engine: relational joins, not BigQuery Graph"]),
            "scope": scope}


def _retrieve_oracle(query, bundle_id, publication_id, as_of, clients, top_k, scope, timer) -> dict:
    g: Graph = clients["graph"] if "graph" in clients else Graph(clients["projection"])
    if not query.startswith(FORCED):
        return _denied("oracle engine supports forced seeds only (no vectors)", scope, timer, "NO_SEED")
    local = query[len(FORCED):]
    local = local[:-3] if local.endswith(".md") else local
    r = g.governed(local, as_of)
    if r["status"] != "OK":
        return _denied("seed not found", scope, timer, "NO_SEED")
    concept = {k: r[k] for k in ("concept", "path", "title", "type", "lifecycle_status", "trust_tier", "verifications",
                                 "freshness", "provenance", "replacement")}
    concept.update({"matched_sections": [], "forced": True})
    comps = [dict(c, seed=r["concept"]) for c in r["computations"]]
    return {"status": "OK", "concepts": [concept], "paths": [dict(p, seed=r["concept"]) for p in r["paths"]],
            "computations": comps, "warnings": ["forced seed: harness-only deterministic override, not a semantic ranking",
                                                 "ORACLE engine: in-process reference, not BigQuery"],
            "scope": scope, "timing": timer.done()}


def impact(target: str, bundle_id: str, publication_id: str, requester: Any, clients: dict, max_depth: int = 6) -> dict:
    timer = Timer()
    engine = clients.get("engine", "gql")
    if engine == "oracle":
        g: Graph = clients["graph"] if "graph" in clients else Graph(clients["projection"])
        r = g.impact(target[:-3] if target.endswith(".md") else target, max_depth)
        r["timing"] = timer.done(); r["engine"] = "oracle"
        return r
    full = f"{PROJECT}.{clients.get('ds', DATASET)}"
    local = target[:-3] if target.endswith(".md") else target
    tid = _node_id(bundle_id, publication_id, "Concept", local)
    if engine != "gql":
        return {"status": "NOT_RUN", "engine": engine, "warnings": ["impact requires GQL (variable-length acyclic paths)"],
                "impacted": [], "timing": timer.done()}
    try:
        rows = _run(clients, "impact", sql("impact.sql", full).replace("{1,6}", "{1,%d}" % max_depth),
                    [_p("target", "STRING", tid), _p("publication_id", "STRING", publication_id)], timer)
    except (gexc.Forbidden, gexc.Unauthorized):
        return {"status": "DENIED", "impacted": [], "timing": timer.done()}
    return {"status": "OK", "engine": "gql", "target": local, "max_depth": max_depth,
            "impacted": [{"impacted": r["impacted"], "type": r["impacted_type"], "status": r["impacted_status"] or "stable",
                          "hops": r["hops"], "path": list(r["path"])} for r in rows],
            "timing": timer.done()}


def stub_backlog(bundle_id: str, publication_id: str, requester: Any, clients: dict) -> dict:
    timer = Timer()
    engine = clients.get("engine", "gql")
    if engine == "oracle":
        g: Graph = clients["graph"] if "graph" in clients else Graph(clients["projection"])
        return {"status": "OK", "engine": "oracle", "backlog": g.stub_backlog(), "timing": timer.done()}
    full = f"{PROJECT}.{clients.get('ds', DATASET)}"
    if engine != "gql":
        q = f"""SELECT g.local_id AS missing_concept, COUNT(*) AS reference_count,
                       ARRAY_AGG(STRUCT(c.local_id AS referrer, l.relation AS relation, JSON_VALUE(l.attrs, '$.section') AS section)
                                 ORDER BY c.local_id, l.relation, JSON_VALUE(l.attrs, '$.section')) AS wanted_by
                FROM `{full}.edges` l JOIN `{full}.nodes` g ON g.node_id = l.dst_id JOIN `{full}.nodes` c ON c.node_id = l.src_id
                WHERE l.publication_id = @publication_id AND l.relation IN ('LINKS_TO','EXECUTED_BY','RESOLVES_TO')
                  AND g.kind = 'Concept' AND g.stub AND c.bundle_id = @bundle_id
                GROUP BY missing_concept ORDER BY missing_concept"""
    else:
        q = sql("stubs.sql", full)
    try:
        rows = _run(clients, "stubs", q, [_p("bundle_id", "STRING", bundle_id), _p("publication_id", "STRING", publication_id)], timer)
    except (gexc.Forbidden, gexc.Unauthorized):
        return {"status": "DENIED", "backlog": [], "timing": timer.done()}
    return {"status": "OK", "engine": engine,
            "backlog": [{"missing_concept": r["missing_concept"], "reference_count": r["reference_count"],
                         "wanted_by": [{"concept": w["referrer"], "section": w["section"], "relation": w["relation"]} for w in r["wanted_by"]]}
                        for r in rows], "timing": timer.done()}
