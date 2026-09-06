"""Landmine assertions. `clients` selects the oracle by default; set OKF_LIVE_ENGINE=gql|fallback
(with a published Acme projection and, for gql, an Enterprise assignment) to run the same contract live."""
import os
import pytest
from okf_bq_graph.compile import compile_bundle
from okf_bq_graph.oracle import Graph
from okf_bq_graph.retrieve import retrieve, impact, stub_backlog
from okf_bq_graph import SOURCE_PIN, PROJECT, LOCATION

AS_OF = "2026-09-05T00:00:00Z"
ENGINE = os.environ.get("OKF_LIVE_ENGINE", "oracle")


@pytest.fixture(scope="module")
def projection(sample_root):
    return compile_bundle(sample_root, "acme_retail", SOURCE_PIN)


@pytest.fixture(scope="module")
def publication(projection):
    return projection["publication_id"]


@pytest.fixture(scope="module")
def clients(projection):
    if ENGINE == "oracle":
        return {"engine": "oracle", "graph": Graph(projection)}
    from google.cloud import bigquery
    return {"engine": ENGINE, "bq": bigquery.Client(project=PROJECT, location=LOCATION)}


@pytest.fixture
def requester():
    return "test-requester"


def test_deprecated_anchor_reaches_sanctioned_computation(clients, requester, publication):
    result = retrieve("forced:metrics/gross-margin-legacy.md", "acme_retail",
                      publication, requester, "2026-09-05T00:00:00Z", clients)
    assert result["status"] == "OK"
    assert result["computations"][0]["path"] == "computations/gross-margin-period.md"
    assert result["computations"][0]["runtime_verdict"] == "NOT_EXECUTED"
    assert result["paths"][0]["concept_hops"] == 2
    c = result["concepts"][0]
    assert c["lifecycle_status"] == "deprecated" and c["trust_tier"] == "human-reviewed"
    assert c["replacement"]["concept"] == "metrics/gross-margin" and c["replacement"]["label"] == "inferred"
    assert "payment_fee" in result["computations"][0]["sql"]
    assert result["computations"][0]["sql_sha256"]
    assert result["scope"]["publication_id"] == publication
    assert any("forced seed" in w for w in result["warnings"])


def test_current_anchor_direct(clients, requester, publication):
    result = retrieve("forced:metrics/gross-margin.md", "acme_retail", publication, requester, AS_OF, clients)
    assert result["status"] == "OK"
    assert result["paths"][0]["concept_hops"] == 1
    assert result["concepts"][0]["freshness"]["verdict"] == "FRESH"
    assert result["concepts"][0]["replacement"] is None
    assert {p["resource"] for p in result["concepts"][0]["provenance"]} == {"policies/margin-standard.md", "policies/revenue-recognition.md"}


def test_stale_boundary(clients, requester, publication):
    r = retrieve("forced:metrics/gross-margin.md", "acme_retail", publication, requester, "2026-12-31T00:00:00Z", clients)
    assert r["concepts"][0]["freshness"]["verdict"] == "STALE"
    r = retrieve("forced:metrics/gross-margin.md", "acme_retail", publication, requester, "2027-01-01T00:00:00Z", clients)
    assert r["concepts"][0]["freshness"]["verdict"] == "STALE"


def test_missing_seed_fails_closed(clients, requester, publication):
    r = retrieve("forced:metrics/does-not-exist.md", "acme_retail", publication, requester, AS_OF, clients)
    assert r["status"] in ("NO_SEED", "DENIED") and r["computations"] == []


def test_impact_and_backlog(clients, requester, publication):
    if ENGINE == "fallback":
        pytest.skip("impact requires GQL")
    r = impact("policies/margin-standard.md", "acme_retail", publication, requester, clients)
    assert r["status"] == "OK"
    names = {x["impacted"]: x["hops"] for x in r["impacted"]}
    assert names["metrics/gross-margin"] == 2 and names["computations/gross-margin-period"] == 2
    assert "policies/margin-standard" not in names
    b = stub_backlog("acme_retail", publication, requester, clients)
    assert b["status"] == "OK" and b["backlog"] == []
