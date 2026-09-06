"""Astra P1#4 / P2#11: cached replay must fail closed on edge-only revocation and must re-evaluate freshness."""
import re

import pytest

import okf_bq_graph.retrieve as RT

PUB = "pub_x"
B = "acme_retail"
SEED = f"{B}|{PUB}|Concept|metrics/gross-margin"
COMP = f"{B}|{PUB}|Concept|computations/gross-margin-period"
SEC = f"{B}|{PUB}|Section|computations/gross-margin-period#s0"
EDGE = f"{B}|{PUB}|LINKS_TO|abc"
MID = f"{B}|{PUB}|Concept|metrics/gross-margin-current"
EDGE2 = f"{B}|{PUB}|LINKS_TO|def"


def _fake_run_factory(state):
    def fake_run(clients, name, query, params, timer):
        if name == "walk":
            return [{"seed_id": SEED, "seed": "metrics/gross-margin", "hop_concepts": ["metrics/gross-margin", "computations/gross-margin-period"],
                     "concept_hops": 1, "edge_ids": [EDGE], "computation_id": COMP, "computation_path": "computations/gross-margin-period.md",
                     "computation_status": "stable", "computation_runtime": "bigquery"}] if state["edge_visible"] else []
        if name == "context":
            rows = [{"concept_id": COMP, "edge_id": f"{B}|{PUB}|HAS_SECTION|s", "relation": "HAS_SECTION", "edge_declaration": "body.h1", "edge_at": None,
                     "edge_resolution": None, "edge_inferred": False, "other_id": SEC, "other_kind": "Section", "other_local_id": "computations/gross-margin-period#s0",
                     "other_title": "Computation", "other_type": None, "other_status": None, "other_actor_kind": None, "other_stub": False,
                     "other_text": "```sql\nSELECT 1\n```", "other_text_sha256": "x", "other_stale_after": None, "other_path": None, "other_runtime": None}]
            if state["edge_visible"]:
                rows.append({"concept_id": SEED, "edge_id": EDGE, "relation": "LINKS_TO", "edge_declaration": "body_link", "edge_at": None,
                             "edge_resolution": "relative", "edge_inferred": False, "other_id": COMP, "other_kind": "Concept",
                             "other_local_id": "computations/gross-margin-period", "other_title": "GM", "other_type": "Attested Computation",
                             "other_status": "stable", "other_actor_kind": None, "other_stub": False, "other_text": None, "other_text_sha256": None,
                             "other_stale_after": None, "other_path": None, "other_runtime": None})
            return rows
        if name == "nodes":
            return [{"node_id": SEED, "local_id": "metrics/gross-margin", "path": "metrics/gross-margin.md", "title": "GM", "type": "Metric",
                     "status": "stable", "stale_after": "2026-09-05T00:30:00Z", "stub": False, "runtime": None},
                    {"node_id": COMP, "local_id": "computations/gross-margin-period", "path": "computations/gross-margin-period.md", "title": "C",
                     "type": "Attested Computation", "status": "stable", "stale_after": None, "stub": False, "runtime": "bigquery"}]
        if name == "recheck":
            nids = [p for p in params if p.name == "nids"][0].values
            eids = [p for p in params if p.name == "eids"][0].values
            return [{"n": len(nids), "e": len(eids) if state["edge_visible"] else 0}]
        raise AssertionError(name)
    return fake_run


def test_edge_only_revocation_denies_cached_replay(monkeypatch):
    state = {"edge_visible": True}
    monkeypatch.setattr(RT, "_run", _fake_run_factory(state))
    cache = {}
    clients = {"engine": "gql", "bq": object(), "cache": cache, "ds": "d"}
    warm = RT.retrieve("forced:metrics/gross-margin.md", B, PUB, "r", "2026-09-05T00:10:00Z", clients)
    assert warm["status"] == "OK" and len(warm["computations"]) == 1 and warm["scope"]["cache"] == "MISS_STORED"
    hit = RT.retrieve("forced:metrics/gross-margin.md", B, PUB, "r", "2026-09-05T00:10:00Z", clients)
    assert hit["scope"]["cache"] == "HIT_RECHECKED" and len(hit["computations"]) == 1
    state["edge_visible"] = False           # edge policy hides the LINKS_TO row; nodes stay visible
    replay = RT.retrieve("forced:metrics/gross-margin.md", B, PUB, "r", "2026-09-05T00:10:00Z", clients)
    assert replay["status"] == "DENIED" and replay["computations"] == [] and replay["scope"]["cache"] == "HIT_DENIED"


def test_cached_replay_reevaluates_freshness_and_as_of(monkeypatch):
    state = {"edge_visible": True}
    monkeypatch.setattr(RT, "_run", _fake_run_factory(state))
    cache = {}
    clients = {"engine": "gql", "bq": object(), "cache": cache, "ds": "d"}
    a = RT.retrieve("forced:metrics/gross-margin.md", B, PUB, "r", "2026-09-05T00:10:00Z", clients)
    assert a["concepts"][0]["freshness"]["verdict"] == "FRESH"
    b = RT.retrieve("forced:metrics/gross-margin.md", B, PUB, "r", "2026-09-05T00:40:00Z", clients)   # same hour, past stale_after
    assert b["concepts"][0]["freshness"]["verdict"] == "STALE" and b["scope"]["as_of"] == "2026-09-05T00:40:00Z"
    # exact-instant key: the second request was a miss, not a replay of the first
    assert b["scope"]["cache"] == "MISS_STORED" and len(cache) == 2


def _two_hop_run_factory(state):
    base = _fake_run_factory({"edge_visible": True})

    def fake_run(clients, name, query, params, timer):
        state.setdefault("stages", []).append(name)
        hidden = state.get("hidden", set())
        if name == "walk":
            if hidden & {EDGE2, MID}:
                return []
            row = {"seed_id": SEED, "seed": "metrics/gross-margin",
                   "hop_concepts": ["metrics/gross-margin", "metrics/gross-margin-current", "computations/gross-margin-period"],
                   "concept_hops": 2, "edge_ids": [EDGE, EDGE2], "computation_id": COMP,
                   "computation_path": "computations/gross-margin-period.md", "computation_status": "stable",
                   "computation_runtime": "bigquery"}
            # Model the real BigQuery result boundary: an inner GRAPH_TABLE field
            # must not reach the fixture result unless the outer SELECT returns it.
            projection = re.search(r"SELECT\s+(.*?)\s+FROM GRAPH_TABLE", query, re.S).group(1)
            row = {column.strip(): row[column.strip()] for column in projection.split(",")}
            if state.get("omit_edges"):
                row.pop("edge_ids", None)
            elif "walk_edges" in state:
                row["edge_ids"] = state["walk_edges"]
            return [row]
        if name == "context":
            rows = base(clients, name, query, params, timer)
            # Context is queried for seed + computation, never the intermediate:
            # it cannot rescue an omitted second traversal-edge dependency.
            rows[1].update(other_id=MID, other_local_id="metrics/gross-margin-current", other_type="Metric")
            if state.get("omit_context_edges"):
                rows[0].pop("edge_id")
            queried_ids = next(p.values for p in params if p.name == "concept_ids")
            return [row for row in rows if row["concept_id"] in queried_ids and row["other_id"] not in hidden]
        if name == "nodes":
            rows = base(clients, name, query, params, timer)
            rows[0]["status"] = "deprecated"
            queried_ids = next(p.values for p in params if p.name == "ids")
            return [row for row in rows if row["node_id"] in queried_ids]
        if name == "recheck":
            ids = {p.name: set(p.values) for p in params if p.name in {"nids", "eids"}}
            state["rechecked"] = ids
            return [{"n": len(ids["nids"] - hidden), "e": len(ids["eids"] - hidden)}]
        raise AssertionError(name)

    return fake_run


def _two_hop_request(monkeypatch, state):
    monkeypatch.setattr(RT, "_run", _two_hop_run_factory(state))
    clients = {"engine": "gql", "bq": object(), "cache": {}, "ds": "d"}

    def request():
        return RT.retrieve("forced:metrics/gross-margin.md", B, PUB, "r", "2026-09-05T00:10:00Z", clients)

    return clients, request


@pytest.mark.parametrize("revoked", [EDGE2, MID])
def test_two_hop_revocation_with_actual_sql_result_columns(monkeypatch, revoked):
    state = {}
    clients, request = _two_hop_request(monkeypatch, state)
    warm = request()
    assert warm["scope"]["cache"] == "MISS_STORED" and len(warm["computations"]) == 1
    assert request()["scope"]["cache"] == "HIT_RECHECKED"
    assert {EDGE, EDGE2} <= state["rechecked"]["eids"]
    assert {SEED, MID, COMP, SEC} <= state["rechecked"]["nids"]
    state["hidden"] = {revoked}
    replay = request()
    assert replay["status"] == "DENIED" and replay["computations"] == []
    assert replay["scope"]["cache"] == "HIT_DENIED"
    clients.pop("cache")
    assert request()["computations"] == []  # governed retrieval agrees after revocation


@pytest.mark.parametrize("state", [
    {"omit_edges": True}, {"walk_edges": None}, {"walk_edges": []}, {"walk_edges": [EDGE]},
    {"walk_edges": [EDGE, ""]}, {"walk_edges": [EDGE, None]}, {"walk_edges": [EDGE, EDGE]},
    {"walk_edges": [EDGE, f"{B}|foreign_publication|LINKS_TO|def"]}, {"omit_context_edges": True},
])
def test_incomplete_dependencies_bypass_cache(monkeypatch, state):
    clients, request = _two_hop_request(monkeypatch, state)
    warm = request()
    assert warm["status"] == "OK" and len(warm["computations"]) == 1
    assert warm["scope"]["cache"] == "BYPASS_INCOMPLETE_DEPENDENCIES"
    assert clients["cache"] == {}
    state["hidden"] = {EDGE2}
    assert request()["computations"] == []
    assert state["stages"].count("walk") == 2 and "recheck" not in state["stages"]


def test_legacy_cache_without_complete_dependencies_is_retrieved_again(monkeypatch):
    state = {}
    clients, request = _two_hop_request(monkeypatch, state)
    request()
    key, cached = next(iter(clients["cache"].items()))
    # The old schema has no evidence that every traversal edge was collected.
    clients["cache"][key] = {"disclosed_ids": cached["disclosed_ids"],
                             "disclosed_edge_ids": [EDGE], "result": cached["result"]}
    state["hidden"] = {EDGE2}
    replay = request()
    assert replay["status"] == "OK" and replay["computations"] == []
    assert state["stages"].count("walk") == 2 and "recheck" not in state["stages"]
