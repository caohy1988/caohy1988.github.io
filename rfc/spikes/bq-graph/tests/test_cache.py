"""Astra P1#4 / P2#11: cached replay must fail closed on edge-only revocation and must re-evaluate freshness."""
import okf_bq_graph.retrieve as RT

PUB = "pub_x"
B = "acme_retail"
SEED = f"{B}|{PUB}|Concept|metrics/gross-margin"
COMP = f"{B}|{PUB}|Concept|computations/gross-margin-period"
SEC = f"{B}|{PUB}|Section|computations/gross-margin-period#s0"
EDGE = f"{B}|{PUB}|LINKS_TO|abc"


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
