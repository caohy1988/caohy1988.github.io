"""Deterministic relational/Python reference traversal over a projection.

Pins the expected governed context, impact and stub-backlog sets so the GQL
results can be compared exactly (spec §4, plan Task 2). Semantics follow the
pinned Neo4j queries (johnymontana/neo4j-okf @ d0641b9) with the spec's
tightenings: ambiguity -> no replacement; unknown deadline -> UNKNOWN_DEADLINE;
trust derived from VERIFIED_BY at query time.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from collections import defaultdict, deque
from typing import Any, Optional

from .model import IMPACT_RELATIONS

SQL_FENCE_RE = re.compile(r"```sql\s*\n(.*?)\n```", re.DOTALL)
CTX_RELATIONS = ("VERIFIED_BY", "GENERATED_BY", "DERIVES_FROM", "LINKS_TO", "HAS_SECTION")   # retrieve.py's context relations


def parse_ts(s: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


class Graph:
    def __init__(self, projection: dict):
        self.p = projection
        self.bundle_id = projection["bundle_id"]
        self.publication_id = projection["publication_id"]
        self.nodes: dict[str, dict] = {n["node_id"]: n for n in projection["nodes"]}
        self.out: dict[str, list[dict]] = defaultdict(list)
        self.inc: dict[str, list[dict]] = defaultdict(list)
        for e in projection["edges"]:
            self.out[e["src_id"]].append(e)
            self.inc[e["dst_id"]].append(e)
        self.by_local: dict[tuple, str] = {(n["kind"], n["local_id"]): n["node_id"] for n in projection["nodes"]}
        self.edge_ids: set[str] = {e["edge_id"] for e in projection["edges"]}

    # -- lookups
    def concept(self, local: str) -> Optional[dict]:
        nid = self.by_local.get(("Concept", local))
        return self.nodes.get(nid) if nid else None

    def local(self, nid: str) -> str:
        return nid.split("|", 3)[3]

    def neighbors(self, nid: str, rel: str) -> list[tuple[dict, dict]]:
        return [(e, self.nodes[e["dst_id"]]) for e in self.out[nid] if e["relation"] == rel]

    def visible(self, node_ids: list[str] | tuple, edge_ids: list[str] | tuple = ()) -> bool:
        """Cached-replay re-check (retrieve.py), the BigQuery `_recheck` contract: every node the cached answer depends
        on (seed and path concepts, the Computation section, verifying actors, provenance sources) AND every edge that
        authorized it (walk hops, HAS_SECTION, VERIFIED_BY, DERIVES_FROM, RESOLVES_TO, LINKS_TO context) must still be in
        the projection this graph answers from, by scoped id. A policy-filtered projection (principal.PolicyGraph)
        answers False for hidden rows; an edge-only revocation with every node untouched answers False too."""
        return all(x in self.nodes for x in node_ids) and all(e in self.edge_ids for e in edge_ids)

    def dependencies(self, seed_id: str, walk_nodes: set, walk_edges: set, computation_ids: list[str]) -> Optional[dict]:
        """The authorization dependencies of one governed answer, the set BigQuery's `_cache_dependencies` records:
        the walk (seed, path nodes, hop edges) plus, for the seed and every reached computation, each context edge
        (`CTX_RELATIONS`, the relations `_assemble` reads for trust, provenance, replacement and the sanctioned SQL
        section) with both endpoints, and the RESOLVES_TO edges the oracle's provenance discloses. None when any id is
        missing or outside the pinned scope: such an answer is never cached."""
        prefix = f"{self.bundle_id}|{self.publication_id}|"
        nodes, edges = set(walk_nodes) | {seed_id}, set(walk_edges)
        for nid in [seed_id, *computation_ids]:
            for e in self.out[nid]:
                if e["relation"] in CTX_RELATIONS:
                    edges.add(e["edge_id"]); nodes.add(e["dst_id"])
                    if e["relation"] == "DERIVES_FROM":
                        for x in self.out[e["dst_id"]]:
                            if x["relation"] == "RESOLVES_TO":
                                edges.add(x["edge_id"]); nodes.add(x["dst_id"])
        if not all(isinstance(i, str) and i.startswith(prefix) and len(i) > len(prefix) for i in nodes | edges):
            return None
        return {"node_ids": sorted(nodes), "edge_ids": sorted(edges)}

    # -- derived properties (spec §4)
    def trust(self, nid: str) -> dict:
        vers = [(e, self.nodes[e["dst_id"]]) for e in self.out[nid] if e["relation"] == "VERIFIED_BY"]
        kinds = [a["actor_kind"] for _, a in vers]
        tier = "unverified" if not kinds else ("human-reviewed" if "human" in kinds else "machine-confirmed")
        return {"trust_tier": tier,
                "verifications": sorted({"by": a["title"], "kind": a["actor_kind"], "at": e["authored_at"]} for e, a in vers) if False else
                sorted(({"by": a["title"], "kind": a["actor_kind"], "at": e["authored_at"]} for e, a in vers), key=lambda x: (x["at"] or "", x["by"]))}

    @staticmethod
    def freshness(node: dict, as_of: str) -> dict:
        sa = node.get("stale_after")
        if not sa:
            return {"verdict": "UNKNOWN_DEADLINE", "stale_after": None}
        try:
            stale = parse_ts(as_of) >= parse_ts(sa)
        except ValueError:
            return {"verdict": "UNKNOWN_DEADLINE", "stale_after": sa, "reason": "unparseable"}
        return {"verdict": "STALE" if stale else "FRESH", "stale_after": sa}

    def provenance(self, nid: str) -> list[dict]:
        out = []
        for e, s in self.neighbors(nid, "DERIVES_FROM"):
            resolves = [self.local(x["dst_id"]) for x in self.out[s["node_id"]] if x["relation"] == "RESOLVES_TO"]
            out.append({"resource": s["resource"], "title": s["title"], "declaration": e["declaration"],
                        "declared": json.loads(e["attrs"] or "{}"), "intrinsic": json.loads(s["attrs"] or "{}"),
                        "resolves_to": resolves})
        return sorted(out, key=lambda x: x["declaration"])

    def sanctioned_sql(self, comp_nid: str) -> Optional[dict]:
        for e, s in self.neighbors(comp_nid, "HAS_SECTION"):
            if s["heading"] == "Computation" or s["heading"].startswith("Computation (part"):
                m = SQL_FENCE_RE.search(s["text"] or "")
                sql = m.group(1) if m else (s["text"] or "")
                return {"section_id": s["node_id"], "sql": sql,
                        "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(), "fenced": bool(m)}
        return None

    # -- governed retrieval for one seed concept (spec §4 table)
    def governed(self, concept_local: str, as_of: str) -> dict:
        c = self.concept(concept_local)
        if c is None:
            return {"status": "NOT_FOUND", "concept": concept_local}
        cid = c["node_id"]
        trust = self.trust(cid)
        computations = []
        # hop 1
        for e1, n1 in self.neighbors(cid, "LINKS_TO"):
            if n1["type"] == "Attested Computation" and (n1["status"] or "stable") != "deprecated" and not n1["stub"]:
                computations.append((1, [self.local(cid), self.local(n1["node_id"])], n1, [e1["edge_id"]], [cid, n1["node_id"]]))
        # hop 2 only for deprecated anchors (pinned Neo4j semantics)
        if (c["status"] or "stable") == "deprecated":
            for e1, n1 in self.neighbors(cid, "LINKS_TO"):
                if n1["stub"] or n1["node_id"] == cid:
                    continue
                for e2, n2 in self.neighbors(n1["node_id"], "LINKS_TO"):
                    if n2["type"] == "Attested Computation" and (n2["status"] or "stable") != "deprecated" and not n2["stub"]:
                        computations.append((2, [self.local(cid), self.local(n1["node_id"]), self.local(n2["node_id"])], n2,
                                             [e1["edge_id"], e2["edge_id"]], [cid, n1["node_id"], n2["node_id"]]))
        best: dict[str, tuple] = {}
        for hops, path, n, edges, path_ids in computations:
            if n["node_id"] not in best or hops < best[n["node_id"]][0]:
                best[n["node_id"]] = (hops, path, n, edges, path_ids)
        comps = []
        walk_nodes, walk_edges = set(), set()
        for hops, path, n, edges, path_ids in sorted(best.values(), key=lambda x: (x[0], x[2]["node_id"])):
            walk_nodes.update(path_ids); walk_edges.update(edges)
            sql = self.sanctioned_sql(n["node_id"])
            comps.append({"path": n["path"], "concept": self.local(n["node_id"]), "concept_hops": hops,
                          "via": path, "runtime": n["runtime"], "status": n["status"],
                          "trust_tier": self.trust(n["node_id"])["trust_tier"],
                          "freshness": self.freshness(n, as_of), "sql": sql["sql"] if sql else None,
                          "sql_sha256": sql["sql_sha256"] if sql else None,
                          "runtime_verdict": "NOT_EXECUTED"})
        replacement = None
        if (c["status"] or "stable") == "deprecated":
            cands = sorted({self.local(n["node_id"]) for _, n in self.neighbors(cid, "LINKS_TO")
                            if n["type"] == c["type"] and (n["status"] or "stable") == "stable" and not n["stub"]})
            if len(cands) == 1:
                replacement = {"concept": cands[0], "label": "inferred", "reason": "unique stable same-type LINKS_TO candidate; no supersedes declaration"}
            elif len(cands) > 1:
                replacement = {"concept": None, "label": "AMBIGUOUS", "candidates": cands}
            else:
                replacement = {"concept": None, "label": "NONE"}
        return {
            "status": "OK", "bundle_id": self.bundle_id, "publication_id": self.publication_id,
            "concept": self.local(cid), "path": c["path"], "title": c["title"], "type": c["type"],
            "lifecycle_status": c["status"] or "stable", "trust_tier": trust["trust_tier"],
            "verifications": trust["verifications"], "freshness": self.freshness(c, as_of), "as_of": as_of,
            "provenance": self.provenance(cid), "replacement": replacement, "computations": comps,
            "paths": [{"concept_hops": x["concept_hops"], "via": x["via"]} for x in comps],
            "dependencies": self.dependencies(cid, walk_nodes, walk_edges, list(best)),
        }

    # -- impact: incoming dependency paths up to `max_depth` edges (spec §4)
    def _impact_best(self, tid: str, max_depth: int, relations: tuple) -> dict[str, tuple[int, list[str]]]:
        best: dict[str, tuple[int, list[str]]] = {}
        # BFS over incoming edges, simple paths only (no node repeated), bounded depth
        q = deque([(tid, [tid])])
        while q:
            cur, path = q.popleft()
            depth = len(path) - 1
            if depth >= max_depth:
                continue
            for e in self.inc[cur]:
                if e["relation"] not in relations:
                    continue
                s = e["src_id"]
                if s in path:
                    continue  # bound cycles / self
                npath = path + [s]
                n = self.nodes[s]
                if n["kind"] == "Concept" and not n["stub"] and s != tid:
                    h = len(npath) - 1
                    if s not in best or h < best[s][0]:
                        best[s] = (h, [self.local(x) for x in reversed(npath)])
                q.append((s, npath))
        return best

    def impact(self, target_local: str, max_depth: int = 6, relations: tuple = IMPACT_RELATIONS) -> dict:
        t = self.concept(target_local)
        if t is None:
            return {"status": "NOT_FOUND", "impacted": []}
        tid = t["node_id"]
        best = self._impact_best(tid, max_depth, relations)
        # truncation: a deeper bound reaches concepts the six-edge bound missed
        deeper = self._impact_best(tid, max_depth + 4, relations)
        truncated = bool(set(deeper) - set(best))
        rows = []
        for s, (h, p) in best.items():
            n = self.nodes[s]
            rows.append({"impacted": self.local(s), "type": n["type"], "status": n["status"] or "stable",
                         "trust_tier": self.trust(s)["trust_tier"], "hops": h, "path": p})
        rows.sort(key=lambda r: (r["hops"], r["impacted"]))
        return {"status": "OK", "target": target_local, "max_depth": max_depth, "truncated": truncated,
                "impacted": rows}

    def stub_backlog(self) -> list[dict]:
        out = []
        for nid, n in self.nodes.items():
            if n["kind"] != "Concept" or not n["stub"]:
                continue
            refs = [e for e in self.inc[nid] if e["relation"] in ("LINKS_TO", "EXECUTED_BY", "RESOLVES_TO")]
            wanted = sorted({(self.local(e["src_id"]), json.loads(e["attrs"] or "{}").get("section"), e["relation"]) for e in refs})
            out.append({"missing_concept": self.local(nid), "reference_count": len(refs),
                        "wanted_by": [{"concept": c, "section": s, "relation": r} for c, s, r in wanted]})
        return sorted(out, key=lambda r: r["missing_concept"])

    def seed_from_section(self, section_nid: str) -> Optional[str]:
        for e in self.inc[section_nid]:
            if e["relation"] == "HAS_SECTION":
                return self.local(e["src_id"])
        return None
