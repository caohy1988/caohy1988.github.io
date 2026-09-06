import pytest
from okf_bq_graph.compile import compile_bundle
from okf_bq_graph.oracle import Graph
from okf_bq_graph import SOURCE_PIN

AS_OF = "2026-09-05T00:00:00Z"


@pytest.fixture(scope="module")
def g(sample_root):
    return Graph(compile_bundle(sample_root, "acme_retail", SOURCE_PIN))


@pytest.fixture(scope="module")
def gb(bundle_b_root):
    return Graph(compile_bundle(bundle_b_root, "bundle_b", "fixture"))


def test_deprecated_anchor_reaches_sanctioned_computation(g):
    r = g.governed("metrics/gross-margin-legacy", AS_OF)
    assert r["status"] == "OK" and r["lifecycle_status"] == "deprecated"
    assert r["computations"][0]["path"] == "computations/gross-margin-period.md"
    assert r["computations"][0]["runtime_verdict"] == "NOT_EXECUTED"
    assert r["paths"][0]["concept_hops"] == 2
    assert r["paths"][0]["via"] == ["metrics/gross-margin-legacy", "metrics/gross-margin", "computations/gross-margin-period"]
    assert r["replacement"] == {"concept": "metrics/gross-margin", "label": "inferred",
                                "reason": "unique stable same-type LINKS_TO candidate; no supersedes declaration"}
    assert r["trust_tier"] == "human-reviewed"
    assert r["freshness"]["verdict"] == "UNKNOWN_DEADLINE"   # legacy has no stale_after
    sql = r["computations"][0]["sql"]
    assert "cogs_full" in sql and "payment_fee" in sql and "fulfillment_cost" in sql and "shipping_cost" in sql
    assert r["computations"][0]["sql_sha256"]


def test_current_anchor_direct_hop(g):
    r = g.governed("metrics/gross-margin", AS_OF)
    assert r["lifecycle_status"] == "stable" and r["trust_tier"] == "human-reviewed"
    assert r["freshness"] == {"verdict": "FRESH", "stale_after": "2026-12-31T00:00:00Z"}
    assert r["paths"][0]["concept_hops"] == 1
    assert r["computations"][0]["path"] == "computations/gross-margin-period.md"
    assert r["replacement"] is None
    assert {p["resource"] for p in r["provenance"]} == {"policies/margin-standard.md", "policies/revenue-recognition.md"}
    assert all(p["resolves_to"] for p in r["provenance"])
    assert r["verifications"] == [{"by": "human:jsmith@acme", "kind": "human", "at": "2026-07-01T09:00:00Z"}]


def test_freshness_boundaries(g):
    c = g.concept("metrics/gross-margin")
    assert Graph.freshness(c, "2026-12-30T23:59:59Z")["verdict"] == "FRESH"
    assert Graph.freshness(c, "2026-12-31T00:00:00Z")["verdict"] == "STALE"
    assert Graph.freshness(c, "2027-01-01T00:00:00Z")["verdict"] == "STALE"
    assert Graph.freshness({"stale_after": None}, AS_OF)["verdict"] == "UNKNOWN_DEADLINE"


def test_trust_tiers(g, gb):
    assert g.trust(g.concept("skills/run-on-bq")["node_id"])["trust_tier"] == "unverified"
    assert gb.trust(gb.concept("metrics/gross-margin")["node_id"])["trust_tier"] == "machine-confirmed"
    assert g.trust(g.concept("metrics/revenue")["node_id"])["trust_tier"] == "human-reviewed"


def test_impact_of_margin_policy(g):
    r = g.impact("policies/margin-standard")
    names = {x["impacted"]: x for x in r["impacted"]}
    assert "metrics/gross-margin" in names and "computations/gross-margin-period" in names
    assert names["metrics/gross-margin"]["hops"] == 2   # Concept -DERIVES_FROM-> Source -RESOLVES_TO-> policy
    assert names["computations/gross-margin-period"]["hops"] == 2
    assert "policies/margin-standard" not in names
    assert r["truncated"] is False


def test_stub_backlog_original_empty_and_injected(g, gb):
    assert g.stub_backlog() == []
    b = gb.stub_backlog()
    assert [x["missing_concept"] for x in b] == ["computations/missing-comp", "computations/skills/run-on-bq", "metrics/not-written"]
    nw = b[2]
    assert nw["reference_count"] == 2
    assert nw["wanted_by"] == [{"concept": "metrics/gross-margin-legacy", "section": "Deprecated", "relation": "LINKS_TO"},
                               {"concept": "metrics/gross-margin-legacy", "section": "Duplicate hits", "relation": "LINKS_TO"}]
    # a missing executor is a stub resource reached by EXECUTED_BY, never an executable computation
    assert b[1]["wanted_by"] == [{"concept": "computations/gross-margin-period", "section": None, "relation": "EXECUTED_BY"}]


def test_ambiguous_replacement_and_no_stub_sql(gb):
    r = gb.governed("metrics/gross-margin-legacy", AS_OF)
    assert r["replacement"]["label"] == "AMBIGUOUS"
    assert r["replacement"]["candidates"] == ["metrics/gross-margin", "metrics/gross-margin-alt"]
    assert r["replacement"]["concept"] is None
    # the 2-hop walk still finds the real computation via gross-margin, never the stub via gross-margin-alt
    assert [c["concept"] for c in r["computations"]] == ["computations/gross-margin-period"]
    alt = gb.governed("metrics/gross-margin-alt", AS_OF)
    assert alt["computations"] == []
