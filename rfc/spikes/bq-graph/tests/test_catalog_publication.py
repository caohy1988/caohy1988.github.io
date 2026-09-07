"""U2: exact publication routing + payload consistency. P1 is the clean pinned Acme compilation; P2 is a genuinely
different compilation of a temporary source copy with one non-computation policy section changed (recorded as a local
derivation, never labelled as the clean upstream commit). Every read goes through the journaled hermetic store."""
import hashlib
import json
import shutil
from pathlib import Path

import pytest

import okf_bq_graph.catalog as C
import okf_bq_graph.publication as PUB
import okf_bq_graph.retrieve as RT
from okf_bq_graph import SOURCE_PIN
from okf_bq_graph.compile import compile_bundle
from okf_bq_graph.journal import Journal
from okf_bq_graph.model import sha256_text
from okf_bq_graph.seed import ConceptSeed

AS_OF = "2026-09-06T00:00:00Z"
CFG = C.CatalogConfig()
GM = "computations/gross-margin-period.md"


@pytest.fixture(scope="module")
def p1(sample_root):
    return compile_bundle(sample_root, "acme_retail", SOURCE_PIN)


@pytest.fixture(scope="module")
def p2(sample_root, tmp_path_factory):
    root = tmp_path_factory.mktemp("p2_source") / "acme_retail"
    shutil.copytree(sample_root, root)
    policy = root / "policies" / "margin-standard.md"
    policy.write_text(policy.read_text(encoding="utf-8") + "\n\n# Revision note\n\nFY2027 review scheduled.\n", encoding="utf-8")
    proj = compile_bundle(str(root), "acme_retail", SOURCE_PIN + "+local.0123456789abcdef")
    proj["_derivation"] = {"base_pin": SOURCE_PIN, "tree_root": str(root), "changed": ["policies/margin-standard.md"]}
    return proj


@pytest.fixture
def pin(p1):
    e = C.sample_entry(publication_id=p1["publication_id"], source_manifest_sha256=p1["source_manifest_sha256"],
                       concept_id=f"acme_retail|{p1['publication_id']}|Concept|metrics/gross-margin",
                       concept_file_sha256=next(m["sha256"] for m in p1["source_manifest"] if m["path"] == "metrics/gross-margin.md"))
    r = C.parse_pin(e, CFG)
    assert isinstance(r, C.CatalogPin)
    return r


@pytest.fixture
def store(tmp_path, p1, p2):
    j = Journal(tmp_path / "run", "run-1")
    s = PUB.ProjectionStore(j)
    s.add(p1); s.add(p2)
    s.set_head("acme_retail", p2["publication_id"])          # head already advanced to P2
    return s


def clients(store):
    return {"engine": "oracle", "graphs": store.graphs}


def _retrieve(store, pin, seed=None):
    seed = seed or pin.seed("catalog-mock")
    return RT.retrieve(seed, pin.bundle_id, pin.publication_id, "t", AS_OF, clients(store))


def _comp(r, path=GM):
    return next(c for c in r["computations"] if c["path"] == path)


def _decl(store, pin, comp):
    n = next(n for n in store.nodes[pin.publication_id] if n["node_id"] == comp["computation_id"])
    attrs = json.loads(n["attrs"])
    return {"status": "OK", "node_id": n["node_id"], "path": n["path"], "type": n["type"], "runtime": n["runtime"],
            "lifecycle_status": n["status"] or "stable", "stale_after": n["stale_after"], "file_sha256": n["file_sha256"],
            "parameters": attrs.get("parameters"), "receipt_fields": attrs.get("receipt"), "job_id": None}


# ---- the two publications really differ
def test_p1_and_p2_are_distinct_compilations_with_the_same_computation_bytes(p1, p2):
    assert p1["publication_id"] != p2["publication_id"] and p1["source_manifest_sha256"] != p2["source_manifest_sha256"]
    assert p1["output_manifest"]["nodes_sha256"] != p2["output_manifest"]["nodes_sha256"]
    f1 = next(m["sha256"] for m in p1["source_manifest"] if m["path"] == GM)
    f2 = next(m["sha256"] for m in p2["source_manifest"] if m["path"] == GM)
    assert f1 == f2                      # non-computation change: the old P1 receipt stays a valid control
    assert p2["source_pin"].startswith(SOURCE_PIN + "+local.")


# ---- scenario 1: P1 requested while head=P2 -> everything returned is P1
def test_p1_is_served_exactly_while_head_is_p2(store, pin, p1):
    res = PUB.resolve_publication(store, pin)
    assert res["status"] == "OK" and res["reasons"] == [] and all(res["checks"].values())
    assert res["head"]["publication_id"] != pin.publication_id and res["head"]["matches_pin"] is False
    r = _retrieve(store, pin)
    assert r["status"] == "OK" and r["scope"]["publication_id"] == pin.publication_id
    assert r["concepts"][0]["concept_id"] == pin.concept_id and r["concepts"][0]["seed_origin"] == "catalog-mock"
    comp = _comp(r)
    assert comp["computation_id"].startswith(f"acme_retail|{p1['publication_id']}|Concept|")
    assert comp["section_id"].startswith(f"acme_retail|{p1['publication_id']}|Section|")
    v = PUB.verify_payload(store, pin, p1, r, comp, _decl(store, pin, comp), expected_path=GM)
    assert v["status"] == "CONSISTENT", v["failed"]
    assert all(v["checks"][k]["ok"] for k in ("retained_node_rows", "retained_edge_rows", "recomputed_manifests", "section_text_hashes",
                                              "result_scope", "seed_concept", "paths", "computations", "selected_computation", "declaration"))
    roles = [e["role"] for e in store.journal.jobs()]
    assert roles == ["pin_resolution", "seed_visibility", "observed_head", "payload_rows"]
    assert all(e["terminal"] for e in store.journal.jobs())


# ---- scenario 2: missing / non-READY / duplicate / absent seed -> typed refusal, no content
def test_missing_publication_is_fail_stale(store, pin):
    store.remove(pin.publication_id)
    res = PUB.resolve_publication(store, pin)
    assert res["status"] == "FAIL_STALE" and set(res["reasons"]) == {"PUBLICATION_MISSING", "SEED_MISSING"}
    assert res["publication"] is None and res["head"]["publication_id"] is not None     # head observed, never substituted
    r = _retrieve(store, pin)
    assert r["status"] == "NO_PUBLICATION" and r["computations"] == [] and r["concepts"] == []
    jobs = store.journal.jobs()
    assert [e["state"] for e in jobs] == ["EMPTY", "EMPTY", "DONE"]          # empty lookups are still journaled jobs


@pytest.mark.parametrize("status", ["INVALID_READBACK", "WITHDRAWN", "PENDING"])
def test_non_ready_publication_is_fail_stale(store, pin, status):
    store.set_status(pin.publication_id, status)
    res = PUB.resolve_publication(store, pin)
    assert res["status"] == "FAIL_STALE" and res["reasons"] == [f"PUBLICATION_NOT_READY:{status}"]


def test_duplicate_publication_row_is_fail_stale(store, pin, p1):
    store.add(p1)                                        # a second READY row with the same id: ambiguous retained state
    res = PUB.resolve_publication(store, pin)
    assert res["status"] == "FAIL_STALE" and "PUBLICATION_DUPLICATE" in res["reasons"]


def test_absent_or_duplicated_seed_is_fail_stale(store, pin):
    store.nodes[pin.publication_id] = [n for n in store.nodes[pin.publication_id] if n["node_id"] != pin.concept_id]
    res = PUB.resolve_publication(store, pin)
    assert res["status"] == "FAIL_STALE" and res["reasons"] == ["SEED_MISSING"]


def test_pin_that_disagrees_with_retained_source_binding_is_refused(store, pin):
    for r in store.publications:
        if r["publication_id"] == pin.publication_id:
            r["source_pin"] = "0" * 40
    res = PUB.resolve_publication(store, pin)
    assert res["status"] == "PIN_MISMATCH" and res["reasons"] == ["PIN_MISMATCH:source_pin"]


def test_seed_row_with_the_wrong_file_digest_is_refused(store, pin):
    store.tamper_node(pin.publication_id, pin.concept_id, file_sha256="f" * 64)
    res = PUB.resolve_publication(store, pin)
    assert res["status"] == "PIN_MISMATCH" and res["reasons"] == ["PIN_MISMATCH:seed_file_sha256"]


def test_store_error_is_blocked_not_stale(store, pin):
    def boom(*a, **k):
        raise ConnectionError("simulated IAM/transport failure")
    store.publication = boom
    res = PUB.resolve_publication(store, pin)
    assert res["status"] == "ERROR" and "ConnectionError" in res["error"]


# ---- scenario 3: requested scope must match the served projection; historical P1 stays valid under head=P2
def test_oracle_refuses_to_serve_another_publication_under_the_requested_label(store, pin, p2):
    other = ConceptSeed(f"acme_retail|{p2['publication_id']}|Concept|metrics/gross-margin", origin="catalog-mock")
    # a concept seed from P2 requested under P1's label: refused as mixed, nothing served
    r = RT.retrieve(other, "acme_retail", pin.publication_id, "t", AS_OF, clients(store))
    assert r["status"] == "MIXED_PUBLICATION" and r["concepts"] == []
    # a single-graph engine holding P2 asked for P1: refused, not relabelled
    r = RT.retrieve(pin.seed("catalog-mock"), "acme_retail", pin.publication_id, "t", AS_OF, {"engine": "oracle", "graph": store.graphs[p2["publication_id"]]})
    assert r["status"] == "NO_PUBLICATION" and r["computations"] == []
    # forced seed, wrong bundle label
    r = RT.retrieve("forced:metrics/gross-margin.md", "bundle_b", pin.publication_id, "t", AS_OF, {"engine": "oracle", "graph": store.graphs[pin.publication_id]})
    assert r["status"] == "NO_PUBLICATION"
    # "active" against a single graph keeps working for the fixture harness and records the served publication
    r = RT.retrieve("forced:metrics/gross-margin.md", "acme_retail", "active", "t", AS_OF, {"engine": "oracle", "graph": store.graphs[pin.publication_id]})
    assert r["status"] == "OK" and r["scope"]["publication_id"] == pin.publication_id
    # but a concept seed never rides on "active"
    r = RT.retrieve(pin.seed("catalog-mock"), "acme_retail", "active", "t", AS_OF, {"engine": "oracle", "graph": store.graphs[pin.publication_id]})
    assert r["status"] == "MIXED_PUBLICATION"


def test_concept_seed_disables_the_cache_on_bigquery_engines(monkeypatch):
    from tests.test_cache import _fake_run_factory, B, PUB as XPUB, SEED
    monkeypatch.setattr(RT, "_run", _fake_run_factory({"edge_visible": True}))
    cache = {}
    cl = {"engine": "fallback", "bq": object(), "cache": cache, "ds": "d"}
    seed = ConceptSeed(SEED, origin="catalog-mock")
    r = RT.retrieve(seed, B, XPUB, "r", "2026-09-05T00:10:00Z", cl)
    assert r["status"] == "OK" and len(r["computations"]) == 1 and r["scope"]["cache"] == RT.CACHE_DISABLED_CONCEPT_SEED and cache == {}
    assert r["concepts"][0]["seed_origin"] == "catalog-mock" and r["concepts"][0]["forced"] is False
    assert any("catalog-mock seed" in w for w in r["warnings"]) and not any("forced" in w for w in r["warnings"])
    again = RT.retrieve(seed, B, XPUB, "r", "2026-09-05T00:10:00Z", cl)
    assert again["scope"]["cache"] == RT.CACHE_DISABLED_CONCEPT_SEED and cache == {}
    # a mismatching concept seed is refused before any job runs
    r = RT.retrieve(ConceptSeed(f"{B}|pub_other0000000000|Concept|metrics/gross-margin"), B, XPUB, "r", "2026-09-05T00:10:00Z", cl)
    assert r["status"] == "MIXED_PUBLICATION" and r["timing"]["jobs"] == []


# ---- scenario 4/5: mixed payloads with plausible P1 labels are detected before receipt
def test_p2_endpoint_mixed_into_a_p1_path_is_detected(store, pin, p1, p2):
    r = _retrieve(store, pin)
    comp = _comp(r)
    # attacker swaps the computation endpoint for P2's node while every scope label still says P1
    comp["computation_id"] = f"acme_retail|{p2['publication_id']}|Concept|computations/gross-margin-period"
    v = PUB.verify_payload(store, pin, p1, r, comp, _decl(store, pin, dict(comp, computation_id=f"acme_retail|{p1['publication_id']}|Concept|computations/gross-margin-period")), expected_path=GM)
    assert v["status"] == "INCONSISTENT" and {"paths", "computations", "selected_computation", "declaration"} <= set(v["failed"])


def test_p2_edge_mixed_into_a_p1_path_is_detected(store, pin, p1):
    r = _retrieve(store, pin)
    comp = _comp(r)
    comp["via"] = ["metrics/gross-margin", "metrics/revenue", "computations/gross-margin-period"]    # no such LINKS_TO chain in P1
    comp["concept_hops"] = 2
    v = PUB.verify_payload(store, pin, p1, r, comp, _decl(store, pin, comp), expected_path=GM)
    assert v["status"] == "INCONSISTENT" and "paths" in v["failed"]
    item = v["checks"]["paths"]["items"][0]
    assert item["nodes_in_trusted"] and item["endpoints"] and not item["edges_continuous"]


def test_section_text_changed_with_old_hash_and_p1_labels_is_detected(store, pin, p1):
    sec = next(n for n in store.nodes[pin.publication_id] if n["kind"] == "Section" and n["local_id"].startswith("policies/margin-standard#"))
    store.tamper_node(pin.publication_id, sec["node_id"], text=(sec["text"] or "") + "\n\nrevenue minus product cost only")   # text_sha256 untouched
    r = _retrieve(store, pin)
    comp = _comp(r)
    v = PUB.verify_payload(store, pin, p1, r, comp, _decl(store, pin, comp), expected_path=GM)
    assert v["status"] == "INCONSISTENT"
    assert {"retained_node_rows", "recomputed_manifests", "section_text_hashes"} <= set(v["failed"])
    assert v["checks"]["section_text_hashes"]["mismatched"] == [sec["node_id"]]
    # the computation bind itself was untouched: the corruption of a non-computation section fails independently
    assert v["checks"]["computations"]["ok"] and v["checks"]["declaration"]["ok"]


def test_sql_changed_after_preflight_with_the_old_digest_label_is_detected(store, pin, p1):
    r = _retrieve(store, pin)
    comp = _comp(r)
    comp["sql"] = comp["sql"].replace("payment_fee", "0 * payment_fee")           # sql_sha256 label left as it was
    v = PUB.verify_payload(store, pin, p1, r, comp, _decl(store, pin, comp), expected_path=GM)
    assert v["status"] == "INCONSISTENT" and v["failed"] == ["computations", "selected_computation"]
    assert not v["checks"]["computations"]["items"][0]["sql_bytes"] and not v["checks"]["selected_computation"]["bytes_check"]["sql_bytes"]


def test_declaration_changed_after_preflight_is_detected(store, pin, p1):
    r = _retrieve(store, pin)
    comp = _comp(r)
    d = _decl(store, pin, comp)
    for bad in (dict(d, file_sha256="a" * 64), dict(d, parameters=[{"name": "period_start", "type": "DATE"}]),
                dict(d, node_id=f"acme_retail|{p1['publication_id']}|Concept|computations/revenue-ytd"), dict(d, type="Concept"),
                dict(d, stale_after="2030-01-01T00:00:00Z")):
        v = PUB.verify_payload(store, pin, p1, r, comp, bad, expected_path=GM)
        assert v["status"] == "INCONSISTENT" and "declaration" in v["failed"], bad


def test_section_swapped_for_another_computations_section_is_detected(store, pin, p1):
    r = _retrieve(store, pin)
    comp = _comp(r)
    comp["section_id"] = f"acme_retail|{p1['publication_id']}|Section|computations/revenue-ytd#s0"
    v = PUB.verify_payload(store, pin, p1, r, comp, _decl(store, pin, comp), expected_path=GM)
    assert v["status"] == "INCONSISTENT" and not v["checks"]["computations"]["items"][0]["section_membership"]


def test_result_relabelled_to_p1_from_a_p2_retrieval_is_detected(store, pin, p1, p2):
    other = ConceptSeed(f"acme_retail|{p2['publication_id']}|Concept|metrics/gross-margin", origin="catalog-mock")
    r = RT.retrieve(other, "acme_retail", p2["publication_id"], "t", AS_OF, clients(store))
    assert r["status"] == "OK"
    r["scope"]["publication_id"] = pin.publication_id                    # label says P1, content is P2
    comp = _comp(r)
    v = PUB.verify_payload(store, pin, p1, r, comp, None, expected_path=GM)
    assert v["status"] == "INCONSISTENT" and "seed_concept" in v["failed"] and "paths" in v["failed"]


def test_guard_is_not_a_scope_only_check(store, pin, p1):
    """Bypassing the row/byte checks would let a relabelled result pass: prove the byte checks are what fail."""
    r = _retrieve(store, pin)
    comp = _comp(r)
    ok = PUB.verify_payload(store, pin, p1, r, comp, _decl(store, pin, comp), expected_path=GM)
    tampered = dict(comp, sql=comp["sql"] + "\n-- x")
    bad = PUB.verify_payload(store, pin, p1, r, tampered, _decl(store, pin, comp), expected_path=GM)
    assert ok["status"] == "CONSISTENT" and bad["status"] == "INCONSISTENT"
    assert bad["checks"]["result_scope"]["ok"] and bad["checks"]["seed_concept"]["ok"]      # labels are fine; bytes are not


# ---- trusted source
def test_trusted_source_compiles_the_clean_checkout_and_matches_the_pin(sample_root, pin, p1):
    t = PUB.trusted_source(pin, sample_root)
    assert t["status"] == "OK", t["checks"]
    assert t["checks"]["git_head_matches_pin"] and t["checks"]["bundle_tree_clean"] is True and t["checks"]["derived"] is False
    assert t["projection"]["publication_id"] == p1["publication_id"]


def test_trusted_source_refuses_unknown_git_state_or_a_wrong_head(sample_root, pin, tmp_path, monkeypatch):
    t = PUB.trusted_source(pin, str(tmp_path))          # not a git checkout
    assert t["status"] == "SOURCE_UNVERIFIED" and t["projection"] is None
    monkeypatch.setattr(PUB, "_git", lambda root, *a: "0" * 40 if a[0] == "rev-parse" and a[-1] == "HEAD" else ("" if a[0] == "status" else "okf/bundles/acme_retail/"))
    t = PUB.trusted_source(pin, sample_root)
    assert t["status"] == "SOURCE_UNVERIFIED" and t["checks"]["git_head_matches_pin"] is False


def test_trusted_source_refuses_a_pin_whose_manifest_differs(sample_root, pin, p1):
    wrong = C.CatalogPin(**dict(pin.record(), source_manifest_sha256="1" * 64))
    t = PUB.trusted_source(wrong, sample_root)
    assert t["status"] == "SOURCE_UNVERIFIED" and t["checks"]["source_manifest_matches_pin"] is False and t["projection"] is None


def test_trusted_source_from_a_local_derivation_is_labelled_derived(p2, pin):
    d = p2["_derivation"]
    pin2 = C.CatalogPin(**dict(pin.record(), publication_id=p2["publication_id"], source_pin=p2["source_pin"],
                               source_manifest_sha256=p2["source_manifest_sha256"],
                               concept_id=f"acme_retail|{p2['publication_id']}|Concept|metrics/gross-margin"))
    t = PUB.trusted_source(pin2, "/nonexistent", derivation=d)
    assert t["status"] == "OK" and t["checks"]["derived"] is True and "not the clean upstream commit" in t["note"]
    assert PUB.trusted_source(pin2, "/nonexistent", derivation=dict(d, base_pin="0" * 40))["status"] == "SOURCE_UNVERIFIED"


# ---- journal
def test_journal_is_append_only_and_retains_originals(tmp_path):
    j = Journal(tmp_path / "r", "r1")
    e = j.intend("pin_resolution", "x", "bigquery", actual=True)
    assert not e["terminal"] and j.unresolved() == [e]
    j.submitted(e, job_id="job-1", project="p", location="US")
    j.terminal(e, "ERROR", error="boom")
    rec = j.retain("catalog_entry", b'{"a":1}')
    assert rec["sha256"] == hashlib.sha256(b'{"a":1}').hexdigest() and Path(rec["path"]).read_bytes() == b'{"a":1}'
    with pytest.raises(FileExistsError):
        j.retain("catalog_entry", b"{}")
    with pytest.raises(ValueError):
        j.terminal(e, "RUNNING")
    lines = [json.loads(l) for l in (tmp_path / "r" / "journal.jsonl").read_text().splitlines()]
    assert [l["event"] for l in lines] == ["opened", "intended", "submitted", "terminal", "retained"]
    assert j.summary()["unresolved"] == 0 and j.job_ids() == ["job-1"] and j.summary()["actual_jobs"] == 1
