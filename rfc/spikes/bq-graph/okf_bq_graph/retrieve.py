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
from .model import PROVENANCE_NOTE, node_id as _node_id
from .lifecycle import window_executor, WindowStopped
from .oracle import Graph, SQL_FENCE_RE, parse_ts
from .publish import sql, resolve_pointer
from .seed import ConceptSeed

FORCED = "forced:"
CACHE_DEPENDENCY_VERSION = 2  # prior entries may omit the second traversal edge
CACHE_DISABLED_CONCEPT_SEED = "DISABLED_CONCEPT_SEED"   # Catalog-seeded requests never fill or replay a cache (plan KTD6)


def _p(name: str, typ: str, val: Any) -> bigquery.ScalarQueryParameter:
    return bigquery.ScalarQueryParameter(name, typ, val)


class Timer:
    def __init__(self) -> None:
        self.t0 = time.monotonic()
        self.stages: dict[str, float] = {}
        self.jobs: list[dict] = []

    def stage(self, name: str, start: float) -> None:
        self.stages[name] = round((time.monotonic() - start) * 1000, 1)

    def job(self, name: str, job: bigquery.QueryJob, state: str = "DONE", error: Optional[str] = None,
            at: Optional[int] = None) -> int:
        """Record one job and return its index. `at` rewrites an entry recorded earlier at submission time, so a job
        that was submitted and then failed keeps its place in the inventory instead of disappearing (Astra PR 45 #1:
        a denied cached-replay re-check is still a submitted job, and the identity claim covers it)."""
        st = getattr(job, "_properties", {}).get("statistics", {})
        entry = {"stage": name, "job_id": job.job_id, "state": state, "error": error,
                 "project": getattr(job, "project", None), "location": getattr(job, "location", None),
                 "slot_ms": job.slot_millis,
                 "bytes_processed": job.total_bytes_processed, "bytes_billed": job.total_bytes_billed,
                 "cache_hit": job.cache_hit, "reservation_id": st.get("reservation_id"),
                 "edition": st.get("edition"),
                 # what the server said about the job itself: routing and billing are established only from a DONE
                 # job whose statistics were actually returned (absent statistics are unknown, not on-demand / free)
                 "server_state": getattr(job, "state", None), "stats_present": bool(st),
                 "created": job.created.isoformat() if job.created else None,
                 "started": job.started.isoformat() if job.started else None,
                 "ended": job.ended.isoformat() if job.ended else None}
        if at is None:
            self.jobs.append(entry)
            return len(self.jobs) - 1
        self.jobs[at] = {**self.jobs[at], **entry}
        return at

    def done(self) -> dict:
        return {"stages_ms": self.stages, "total_ms": round((time.monotonic() - self.t0) * 1000, 1), "jobs": self.jobs}


EDITION_ERR = "require a reservation with Enterprise"


class BudgetExhausted(RuntimeError):
    """The caller's shared billed-byte / USD ledger has no room for another job. Nothing was submitted."""


class RoutingViolation(RuntimeError):
    """A job the caller required to run on-demand reports a reservation or an edition in its statistics."""


def _run(clients: dict, name: str, query: str, params: list, timer: Timer) -> list[dict]:
    """One BigQuery job. A job that is mis-routed to on-demand during assignment propagation (edition error)
    is retried at most twice; the retry count is recorded so the benchmark can report it.

    Two optional caller policies ride in `clients` (the SQL-baseline driver sets both; every other caller is unchanged):

    * `clients["bytes_ledger"]` — an object with `hold() -> int | None`, `settle(hold, bytes_billed, job_id)` and
      `unresolved(hold, job_id, reason)`. A hold is taken BEFORE submission and becomes the job's
      `maximum_bytes_billed`, so BigQuery itself refuses a job that would bill past the caller's remaining room; when
      no hold is available the job is not submitted and `BudgetExhausted` is raised. A job settles its hold against
      the bytes it actually billed only when the server reported a terminal (DONE) job with statistics, failures
      included. Anything else - a submission whose response was lost after the gate journaled its id, a job whose
      final statistics could not be read - keeps the hold as liability against that job id until a readback resolves
      it (Astra PR55 RR #1). A submission that raised before any id existed is liability nobody can resolve.
    * `clients["routing"]` — an object with a `reservation` string, `check(job_entry)` and `observe(job_entry)`. The
      string is written into the job configuration (`"none"` is BigQuery's on-demand override, so an inherited project
      assignment cannot route the job onto a reservation). EVERY submitted job is observed - successes, failures and
      jobs whose outcome is unknown - so a reservation_id or edition on a failed job is a recorded violation too, and
      a job without terminal statistics stays unknown rather than counting as on-demand (Astra PR55 RR #2). A
      violation on the success path raises `RoutingViolation`; on a failure path the original error propagates and the
      recorded violation stops admission through the caller's stop check.
    """
    cfg = bigquery.QueryJobConfig(query_parameters=params, use_query_cache=clients.get("use_cache", False),
                                  labels={"okf_spike": "bq_graph_20260905", "stage": name})
    journal = clients.get("journal")      # catalog chain: every retrieval job is journaled before the send, incl. failures
    ledger = clients.get("bytes_ledger")
    routing = clients.get("routing")
    if routing is not None:
        cfg.reservation = routing.reservation
    t = time.monotonic()
    retries = 0
    while True:
        if journal is not None:
            from .publication import run_journaled
            try:
                rows, job, _entry = run_journaled(clients["bq"], journal, f"retrieval_{name}", f"governed retrieval stage {name}", query, cfg, LOCATION,
                                                  project=PROJECT, dataset=clients.get("ds", DATASET))
                break
            except gexc.GoogleAPICallError as e:
                if EDITION_ERR in str(e) and retries < 2 and clients.get("engine") == "gql":
                    retries += 1; time.sleep(2); continue
                raise
        hold = None
        if ledger is not None:
            hold = ledger.hold()
            if hold is None:
                raise BudgetExhausted(f"{name}: {ledger.stop_reason()}; no job submitted")
            cfg.maximum_bytes_billed = hold
        try:
            job = clients["bq"].query(query, job_config=cfg, location=LOCATION)
        except BaseException as e:
            # A gate journals the id before it sends, so an exception here does not establish non-submission: the
            # job may be running. The hold stays as liability against that id; routing for it is unknown.
            lost_id = getattr(e, "okf_job_id", None)
            if lost_id is not None:
                timer.jobs.append({"stage": name, "job_id": lost_id, "state": "SUBMISSION_UNCONFIRMED",
                                   "error": f"{type(e).__name__}: {str(e)[:200]}", "project": PROJECT, "location": LOCATION,
                                   "bytes_billed": None, "reservation_id": None, "edition": None,
                                   "server_state": None, "stats_present": False,
                                   "job_ref": getattr(e, "okf_job_ref", None)})
            if hold is not None:
                if lost_id is None and isinstance(e, WindowStopped):
                    ledger.settle(hold, 0)      # the gate refused admission before journaling an id: nothing was sent
                else:
                    ledger.unresolved(hold, lost_id, f"submission raised {type(e).__name__} after the id was journaled"
                                      if lost_id is not None else f"submission raised {type(e).__name__} with no journaled id")
            if routing is not None and lost_id is not None:
                routing.observe({"job_id": lost_id, "stage": name, "server_state": None, "stats_present": False,
                                 "reservation_id": None, "edition": None})
            raise
        at = timer.job(name, job, state="SUBMITTED")   # in the inventory before any wait: a failure must not erase it
        try:
            rows = [dict(r) for r in job.result()]
            timer.job(name, job, at=at)
        except gexc.GoogleAPICallError as e:
            timer.job(name, job, state="FAILED", error=f"{type(e).__name__}: {str(e)[:200]}", at=at)
            if EDITION_ERR in str(e) and retries < 2 and clients.get("engine") == "gql":
                retries += 1; time.sleep(2); continue
            raise
        finally:
            entry = timer.jobs[at]
            terminal = entry.get("server_state") == "DONE" and entry.get("stats_present") and entry.get("bytes_billed") is not None
            if hold is not None:
                if terminal:
                    ledger.settle(hold, entry["bytes_billed"], entry["job_id"])
                else:
                    ledger.unresolved(hold, entry["job_id"], f"no terminal billing read for {name} (state {entry.get('server_state')})")
            if routing is not None and entry["state"] != "DONE":
                routing.observe(entry)          # failures and unknown outcomes are observed too; the error propagates
        if routing is not None:
            routing.check(timer.jobs[at])
        break
    timer.stage(name, t)
    if journal is not None:
        timer.job(name, job)
    if retries:
        timer.jobs[-1]["routing_retries"] = retries
    return rows


def _denied(reason: str, scope: dict, timer: Timer, status: str = "DENIED") -> dict:
    return {"status": status, "concepts": [], "paths": [], "computations": [], "warnings": [reason],
            "scope": scope, "timing": timer.done()}


def _cache_key(ds, bundle_id, publication_id, requester, query, as_of, top_k, engine) -> str:
    """The engine is part of the key. A GQL request and a relational-fallback request are different executions over
    different SQL, and serving one from the other's entry would let a fallback answer be presented as a Graph answer
    (Slice A U4/KTD4). The exact normalized as-of instant keeps two requests straddling a `stale_after` boundary
    apart."""
    inst = parse_ts(as_of).astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return "|".join([str(engine), ds, bundle_id, publication_id, str(requester), query, inst, str(top_k)])


def _template(name: str, text: str) -> dict:
    """What was actually compiled for a stage, so a GQL claim can be checked against the SQL that ran."""
    return {"name": name, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "chars": len(text),
            "graph_table": "GRAPH_TABLE(" in text.upper()}


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


def retrieve(query: "str | ConceptSeed", bundle_id: str, publication_id: str, requester: Any, as_of: str,
             clients: dict, top_k: int = 5) -> dict:
    """`query` is a natural-language string (vector seed), a `forced:<local path>` fixture override, or a
    `ConceptSeed` carrying one exact scoped Concept id (the Catalog-returned seed). A concept seed must lie inside the
    requested (bundle, publication); it is never resolved against the active head, and it disables the cache."""
    timer = Timer()
    engine = clients.get("engine", "gql")
    ds = clients.get("ds", DATASET)
    full = f"{PROJECT}.{ds}"
    concept_seed = query if isinstance(query, ConceptSeed) else None
    scope: dict[str, Any] = {"bundle_id": bundle_id, "publication_id": publication_id, "engine": engine,
                             "requester": str(requester), "as_of": as_of, "top_k": top_k}
    if concept_seed is not None:
        scope["seed"] = {"concept_id": concept_seed.concept_id, "origin": concept_seed.origin}
        if publication_id == "active" or concept_seed.bundle_id != bundle_id or concept_seed.publication_id != publication_id:
            return _denied("concept seed outside the requested pinned scope", scope, timer, "MIXED_PUBLICATION")
    if engine == "oracle":
        return _retrieve_oracle(query, bundle_id, publication_id, as_of, clients, top_k, scope, timer)
    cache = clients.get("cache")
    if concept_seed is not None and cache is not None:
        cache = None
        scope["cache"] = CACHE_DISABLED_CONCEPT_SEED
    ckey = _cache_key(ds, bundle_id, publication_id, requester, str(query), as_of, top_k, engine) if cache is not None else None
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
        if concept_seed is not None:
            seeds = [{"concept_id": concept_seed.concept_id, "sections": [], "forced": False, "origin": concept_seed.origin}]
            warnings.append(f"{concept_seed.origin} seed: exact Concept id supplied by the runtime pin, not a semantic ranking")
            timer.stage("seed", time.monotonic())
        elif query.startswith(FORCED):
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
        walk_name = "governed.sql" if engine == "gql" else "fallback.sql"
        walk_sql = sql(walk_name, full)
        scope["templates"] = {"walk": _template(walk_name, walk_sql)}
        walks: dict[str, list[dict]] = {s["concept_id"]: [] for s in seeds}
        for w in _run(clients, "walk", walk_sql,
                      [bigquery.ArrayQueryParameter("seeds", "STRING", [s["concept_id"] for s in seeds]),
                       _p("bundle_id", "STRING", bundle_id), _p("publication_id", "STRING", publication_id)], timer):
            walks.setdefault(w["seed_id"], []).append(w)
        # --- context: verifiers, provenance, links, sections (+ section text) for seeds and reached computations
        ids = sorted({s["concept_id"] for s in seeds} | {w["computation_id"] for ws in walks.values() for w in ws})
        ctx_name = "context.sql" if engine == "gql" else "context.fallback"
        ctx_sql = (sql("context.sql", full) if engine == "gql" else _context_fallback(full))
        scope["templates"]["context"] = _template(ctx_name, ctx_sql)
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
    except BaseException as e:
        # A request cut mid-flight (gate deadline, ceiling, routing) still has a job inventory: the jobs it submitted
        # before the cut travel with the exception so the retained attempt names them (they are what the gate cancelled).
        e.okf_timing = timer.done()
        raise
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
                 "source_id": r["other_id"], "note": PROVENANCE_NOTE}
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
                         "replacement": replacement, "matched_sections": s["sections"], "forced": s["forced"],
                         "seed_origin": s.get("origin", "forced" if s["forced"] else "vector")})
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
    """In-process reference. `clients["graphs"]` (publication_id -> Graph) models a retained store holding several
    publications; the requested publication must be present and the selected Graph must carry the requested scope. A
    request for a publication the engine does not hold is NO_PUBLICATION with no content: the oracle never serves
    another publication under the requested label (Astra seams: retrieve.py:363 previously ignored the request)."""
    graphs = clients.get("graphs")
    if graphs is not None:
        g: Optional[Graph] = graphs.get(publication_id)
        if g is None:
            return _denied("requested publication is not retained by this engine", scope, timer, "NO_PUBLICATION")
    else:
        g = clients["graph"] if "graph" in clients else Graph(clients["projection"])
    pinned = publication_id != "active"           # an unpinned request is never cached (PR 40)
    if not pinned:
        scope["publication_id"] = publication_id = g.publication_id
    if g.bundle_id != bundle_id or g.publication_id != publication_id:
        return _denied(f"engine holds {g.bundle_id}|{g.publication_id}, not the requested scope", scope, timer, "NO_PUBLICATION")
    if isinstance(query, ConceptSeed):
        local = query.local
        seed_warning = f"{query.origin} seed: exact Concept id supplied by the runtime pin, not a semantic ranking"
        forced = False
    elif query.startswith(FORCED):
        local = query[len(FORCED):]
        local = local[:-3] if local.endswith(".md") else local
        seed_warning = "forced seed: harness-only deterministic override, not a semantic ranking"
        forced = True
    else:
        return _denied("oracle engine supports forced or concept seeds only (no vectors)", scope, timer, "NO_SEED")
    # cached replay under the BigQuery engines' `_cache_dependencies` / `_recheck` contract (PR 40): the entry carries every node
    # and edge the answer depends on (walk, SQL section, verifications, provenance, context), a hit is served only after
    # the graph re-confirms all of them by scoped id (principal.PolicyGraph answers under the current policy), an answer
    # whose dependencies cannot be established is never stored (BYPASS_INCOMPLETE_DEPENDENCIES), and a graph without a
    # re-check, a failed one, a stale dependency version or an unpinned publication is never served from cache.
    # A Catalog concept seed never fills or replays a cache (plan KTD6), on this engine as on the BigQuery ones.
    cache = clients.get("cache")
    if isinstance(query, ConceptSeed) and cache is not None:
        cache = None
        scope["cache"] = CACHE_DISABLED_CONCEPT_SEED
    ckey = (_cache_key("oracle", bundle_id, publication_id, scope["requester"], str(query), as_of, top_k, "oracle")
            if cache is not None and pinned else None)
    if ckey is not None and ckey in cache:
        cached = cache[ckey]
        if cached.get("dependency_version") == CACHE_DEPENDENCY_VERSION:
            visible = getattr(g, "visible", None)
            if visible is not None and visible(cached["disclosed_ids"], cached["disclosed_edge_ids"]):
                out = _refresh(json.loads(json.dumps(cached["result"])), as_of)
                out["scope"] = dict(out["scope"], cache="HIT_RECHECKED"); out["timing"] = timer.done()
                return out
            return _denied("cached replay: current authorization check failed or unknown", dict(scope, cache="HIT_DENIED"), timer)
        cache.pop(ckey, None)
    r = g.governed(local, as_of)
    if r["status"] == "DENIED":   # the policy-emulating graph's Forbidden
        return _denied("authorization error: policy denied (oracle emulation)", scope, timer)
    if r["status"] != "OK":
        return _denied("seed not found", scope, timer, "NO_SEED")
    cid = _node_id(bundle_id, publication_id, "Concept", r["concept"])
    concept = {k: r[k] for k in ("concept", "path", "title", "type", "lifecycle_status", "trust_tier", "verifications",
                                 "freshness", "provenance", "replacement")}
    concept.update({"concept_id": cid, "matched_sections": [], "forced": forced,
                    "seed_origin": query.origin if isinstance(query, ConceptSeed) else "forced"})
    deps = r.get("dependencies")   # the authorizing nodes and edges stay in the cache entry, not the answer (PR 40)
    comps = []
    for c in r["computations"]:
        comp_id = _node_id(bundle_id, publication_id, "Concept", c["concept"])
        sq = g.sanctioned_sql(comp_id)
        comps.append(dict(c, seed=r["concept"], computation_id=comp_id, section_id=sq["section_id"] if sq else None))
    out = {"status": "OK", "concepts": [concept], "paths": [dict(p, seed=r["concept"]) for p in r["paths"]],
           "computations": comps, "warnings": [seed_warning, "ORACLE engine: in-process reference, not BigQuery"],
           "scope": scope, "timing": timer.done()}
    if ckey is not None:
        if deps is None:
            out["scope"] = dict(out["scope"], cache="BYPASS_INCOMPLETE_DEPENDENCIES")
            return out
        cache[ckey] = {"dependency_version": CACHE_DEPENDENCY_VERSION, "disclosed_ids": deps["node_ids"], "disclosed_edge_ids": deps["edge_ids"],
                       "result": json.loads(json.dumps(out, default=str))}
        out["scope"] = dict(out["scope"], cache="MISS_STORED")
    return out


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
