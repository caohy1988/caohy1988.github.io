"""U1: Catalog reader + validated seed contract. Every read here is injected through the same parser the HTTP reader
uses; nothing in this file can produce a `catalog` (live) seed label."""
import json

import pytest

import okf_bq_graph.catalog as C
from okf_bq_graph.seed import ConceptSeed

CFG = C.CatalogConfig()
OTHER = [f"{CFG.group}/entries/acme-retail-kc-unblock/{p}" for p in
         ("metrics/revenue", "metrics/gross-margin-legacy", "policies/margin-standard", "computations/gross-margin-period",
          "computations/revenue-ytd", "skills/run-on-bq", "index", "log", "metrics/cogs", "policies/revenue-recognition")]


def reader(names=None, entry=None, per_page=4, **kw):
    names = OTHER + [CFG.entry] if names is None else names
    entry = C.sample_entry() if entry is None else entry
    return C.MockReader(C.mock_pages(names, per_page), {CFG.entry: entry}, **kw)


# ---- scenario 1: valid multi-page discovery + ALL response -> exactly the returned pin/concept
def test_multi_page_discovery_returns_the_exact_pin_and_concept():
    rd = reader(per_page=4)
    seed = C.read_seed(rd, CFG)
    assert isinstance(seed, C.CatalogSeed) and seed.ok and seed.mode == "catalog-mock"
    assert seed.discovery["pages"] == 3 and seed.discovery["entries_listed"] == 11 and seed.discovery["matches"] == 1
    assert seed.pin.publication_id == "pub_190192147fd7fd78"
    assert seed.pin.concept_id == "acme_retail|pub_190192147fd7fd78|Concept|metrics/gross-margin"
    assert seed.pin.source_pin == "31da799a9aef176df12e91abbd119ea9385b75ec"
    assert seed.pin.seed("catalog-mock") == ConceptSeed(seed.pin.concept_id, origin="catalog-mock")
    assert str(seed.pin.seed("catalog-mock")).startswith("concept:") and "forced:" not in str(seed.pin.seed("catalog-mock"))
    # only the configured entry body is fetched, with view=ALL, after the whole list
    gets = [c for c in rd.calls if c[0] == "get"]
    assert gets == [("get", CFG.entry, "ALL")]
    assert [c[3] for c in rd.calls if c[0] == "list"] == [None, "p1", "p2"]
    assert seed.authored_aspects == ["201486563047.us-central1.okf", "655216118709.global.overview"]
    rec = seed.record()
    assert rec["status"] == "OK" and rec["mode"] == "catalog-mock" and "not a live Catalog read" in rec["note"]
    assert len(seed.raw_entry_sha256) == 64 and len(seed.discovery["list_sha256"]) == 3


def test_concept_id_capitalised_kind_is_required():
    e = C.sample_entry(concept_id="acme_retail|pub_190192147fd7fd78|concept|metrics/gross-margin")
    r = C.read_seed(reader(entry=e), CFG)
    assert isinstance(r, C.CatalogRefusal) and r.status == "INVALID_PIN" and "concept_id" in r.reason
    assert r.details["expected"].split("|")[2] == "Concept"


# ---- scenario 2: empty/missing entry, duplicate candidate, page cap, keys-only aspect -> refusal, no fallback
def test_missing_entry_refuses_without_fetching_any_body():
    rd = reader(names=OTHER)
    r = C.read_seed(rd, CFG)
    assert r.status == "ENTRY_NOT_FOUND" and r.stage == "list"
    assert not [c for c in rd.calls if c[0] == "get"]


def test_empty_group_refuses():
    rd = C.MockReader([{"entries": []}], {})
    r = C.read_seed(rd, CFG)
    assert r.status == "ENTRY_NOT_FOUND" and r.details["entries_listed"] == 0


def test_duplicate_candidate_is_ambiguous_and_nothing_is_fetched():
    rd = reader(names=OTHER[:3] + [CFG.entry] + OTHER[3:] + [CFG.entry])
    r = C.read_seed(rd, CFG)
    assert r.status == "ENTRY_AMBIGUOUS" and r.details["matches"] == 2
    assert not [c for c in rd.calls if c[0] == "get"]


def test_page_cap_exhaustion_refuses_even_when_the_entry_was_already_seen():
    names = [CFG.entry] + OTHER * 3
    rd = reader(names=names, per_page=5)
    r = C.read_seed(rd, C.CatalogConfig(max_pages=2))
    assert r.status == "PAGE_CAP" and r.details["pages"] == 2 and not [c for c in rd.calls if c[0] == "get"]


def test_keys_only_aspect_is_refused_as_non_all_view():
    e = C.sample_entry()
    e["aspects"][CFG.aspect_key] = {"aspectType": "x"}          # FULL view shape for an optional aspect: key without data
    r = C.read_seed(reader(entry=e), CFG)
    assert r.status == "ASPECT_KEYS_ONLY"


def test_missing_runtime_aspect_is_refused_even_with_authored_okf_present():
    e = C.sample_entry()
    del e["aspects"][CFG.aspect_key]
    r = C.read_seed(reader(entry=e), CFG)
    assert r.status == "ASPECT_MISSING" and "okf" in json.dumps(e["aspects"])   # authored aspect is not a runtime path


# ---- scenario 3: malformed / unsupported / scope / traversal / inconsistent -> reject before any content access
@pytest.mark.parametrize("override, status, needle", [
    ({"publication_id": ""}, "INVALID_PIN", "publication_id"),
    ({"publication_id": None}, "INVALID_PIN", "publication_id"),
    ({"publication_id": 42}, "INVALID_PIN", "publication_id"),
    ({"publication_id": "pub_190192147FD7FD78"}, "INVALID_PIN", "pub_<16 hex>"),
    ({"publication_id": "pub_1901"}, "INVALID_PIN", "pub_<16 hex>"),
    ({"source_pin": "31da799"}, "INVALID_PIN", "source_pin"),
    ({"source_pin": "31da799a9aef176df12e91abbd119ea9385b75ec+local.0123456789abcdef"}, "INVALID_PIN", "source_pin"),
    ({"source_manifest_sha256": "zz"}, "INVALID_PIN", "source_manifest_sha256"),
    ({"concept_file_sha256": "912be604"}, "INVALID_PIN", "concept_file_sha256"),
    ({"runtime_contract": "graph-spike-v2"}, "UNSUPPORTED_CONTRACT", "graph-spike-v2"),
    ({"runtime_contract": ""}, "INVALID_PIN", "runtime_contract"),
    ({"runtime_dataset": "okf_graph_spike_20260906"}, "SCOPE_REFUSED", "runtime_dataset"),
    ({"runtime_project": "other-project"}, "SCOPE_REFUSED", "runtime_project"),
    ({"runtime_location": "us-central1"}, "SCOPE_REFUSED", "runtime_location"),
    ({"managed_by_deployment": "someone-else"}, "SCOPE_REFUSED", "managed_by_deployment"),
    ({"managed_by_profile": "okf-kc-self-unblock/2"}, "SCOPE_REFUSED", "managed_by_profile"),
    ({"source_repository": "https://github.com/evil/knowledge-catalog"}, "SCOPE_REFUSED", "source_repository"),
    ({"source_root": "okf/bundles/other"}, "SCOPE_REFUSED", "source_root"),
    ({"bundle_id": "acme_retail_2"}, "SCOPE_REFUSED", "bundle_id"),
    ({"compiler_version": "okf_bq_graph.compile/0.2.0"}, "SCOPE_REFUSED", "compiler_version"),
    ({"concept_path": "../metrics/gross-margin.md", "concept_id": "acme_retail|pub_190192147fd7fd78|Concept|../metrics/gross-margin"}, "INVALID_PIN", "concept_path"),
    ({"concept_path": "/metrics/gross-margin.md", "concept_id": "acme_retail|pub_190192147fd7fd78|Concept|/metrics/gross-margin"}, "INVALID_PIN", "concept_path"),
    ({"concept_path": "metrics/./gross-margin.md"}, "INVALID_PIN", "concept_path"),
    ({"concept_path": "metrics/gross-margin.txt"}, "INVALID_PIN", "concept_path"),
    ({"concept_id": "acme_retail|pub_0000000000000000|Concept|metrics/gross-margin"}, "INVALID_PIN", "concept_id"),
    ({"concept_id": "acme_retail|pub_190192147fd7fd78|Concept|metrics/revenue"}, "INVALID_PIN", "concept_id"),
    ({"concept_id": "acme_retail|pub_190192147fd7fd78|Concept|metrics/gross-margin "}, "INVALID_PIN", "concept_id"),
    ({"managed_by_principal": ["a"]}, "INVALID_PIN", "managed_by_principal"),
])
def test_malformed_or_out_of_scope_pin_is_rejected(override, status, needle):
    r = C.read_seed(reader(entry=C.sample_entry(**override)), CFG)
    assert isinstance(r, C.CatalogRefusal), r
    assert r.status == status and needle in r.reason, (r.status, r.reason)


def test_missing_field_lists_every_missing_key():
    e = C.sample_entry()
    for k in ("source_pin", "managed_by_deployment"):
        del e["aspects"][CFG.aspect_key]["data"][k]
    r = C.read_seed(reader(entry=e), CFG)
    assert r.status == "INVALID_PIN" and r.details["missing"] == ["source_pin", "managed_by_deployment"]


def test_empty_or_non_object_aspect_data_is_invalid():
    for bad in ({}, [], "x"):
        e = C.sample_entry()
        e["aspects"][CFG.aspect_key]["data"] = bad
        assert C.read_seed(reader(entry=e), CFG).status == "INVALID_PIN"


def test_returned_entry_name_or_type_must_match():
    e = C.sample_entry(); e["name"] = OTHER[0]
    assert C.read_seed(reader(entry=e), CFG).status == "ENTRY_MISMATCH"
    e = C.sample_entry(); e["entryType"] = "projects/201486563047/locations/us-central1/entryTypes/generic"
    assert C.read_seed(reader(entry=e), CFG).status == "ENTRY_MISMATCH"


def test_local_derived_source_pin_only_when_config_allows_it():
    derived = "31da799a9aef176df12e91abbd119ea9385b75ec+local.0123456789abcdef"
    e = C.sample_entry(source_pin=derived)
    assert C.read_seed(reader(entry=e), CFG).status == "INVALID_PIN"
    s = C.read_seed(reader(entry=e), C.CatalogConfig(allow_local_derived_source=True))
    assert isinstance(s, C.CatalogSeed) and s.pin.source_pin == derived


def test_published_snapshot_id_is_optional_and_never_manufactured():
    s = C.read_seed(reader(), CFG)
    assert s.pin.published_snapshot_id is None
    s2 = C.read_seed(reader(entry=C.sample_entry(published_snapshot_id="snap-1")), CFG)
    assert s2.pin.published_snapshot_id == "snap-1" and s2.pin.source_manifest_sha256 != "snap-1"


# ---- scenario 4: HTTP / transport failures stay identifiable; nothing silently becomes a live run
@pytest.mark.parametrize("status", [403, 404, 429, 500])
def test_http_error_on_list_is_a_catalog_error_with_the_status(status):
    rd = C.MockReader([(status, {"error": {"code": status, "message": "nope"}})], {})
    r = C.read_seed(rd, CFG)
    assert r.status == "CATALOG_ERROR" and r.http_status == status and r.stage == "list" and "nope" in r.reason


@pytest.mark.parametrize("status", [403, 404, 429])
def test_http_error_on_get_is_a_catalog_error_with_the_status(status):
    rd = reader(get_status=status)
    r = C.read_seed(rd, CFG)
    assert r.status == "CATALOG_ERROR" and r.http_status == status and r.stage == "get"
    assert r.details["discovery"]["matches"] == 1


def test_truncated_and_non_json_bodies_are_catalog_errors():
    rd = C.MockReader([b'{"entries": [{"name": "x"'], {})
    r = C.read_seed(rd, CFG)
    assert r.status == "CATALOG_ERROR" and r.http_status == 200 and "non-JSON" in r.reason
    rd = reader(entry=b"<html>maintenance</html>")
    r = C.read_seed(rd, CFG)
    assert r.status == "CATALOG_ERROR" and r.stage == "get"


def test_http_reader_transport_failure_is_reported_at_the_adapter_boundary():
    class Sess:
        def request(self, method, url, params=None, timeout=None, allow_redirects=True):
            assert method == "GET" and timeout == (10, 20) and allow_redirects is False
            raise TimeoutError("read timed out")
    r = C.read_seed(C.HttpReader(session=Sess()), CFG)
    assert r.status == "CATALOG_ERROR" and r.http_status is None and "TimeoutError" in r.reason and r.stage == "list"


def test_http_reader_passes_view_all_and_page_tokens_and_is_the_only_live_mode():
    seen = []

    class Resp:
        def __init__(self, status, body): self.status_code, self.content = status, body

    class Sess:
        def request(self, method, url, params=None, timeout=None, allow_redirects=True):
            seen.append((url, dict(params)))
            if url.endswith("/entries"):
                if params.get("pageToken") is None:
                    return Resp(200, json.dumps({"entries": [{"name": OTHER[0]}], "nextPageToken": "t1"}).encode())
                return Resp(200, json.dumps({"entries": [{"name": CFG.entry}]}).encode())
            return Resp(200, json.dumps(C.sample_entry()).encode())
    rd = C.HttpReader(session=Sess())
    s = C.read_seed(rd, CFG)
    assert isinstance(s, C.CatalogSeed) and s.mode == "catalog" and C.is_live_reader(rd) and not C.is_live_reader(reader())
    assert seen[0] == (C.CATALOG_API + CFG.group + "/entries", {"pageSize": 100})
    assert seen[1][1] == {"pageSize": 100, "pageToken": "t1"}
    assert seen[2] == (C.CATALOG_API + CFG.entry, {"view": "ALL"})


def test_retain_receives_every_raw_response_before_parsing():
    kept = {}
    rd = reader(per_page=6)
    s = C.read_seed(rd, CFG, retain=lambda name, raw: kept.__setitem__(name, raw))
    assert set(kept) == {"catalog_list_0", "catalog_list_1", "catalog_entry"}
    assert C.sha256_hex(kept["catalog_entry"]) == s.raw_entry_sha256
    kept.clear()
    C.read_seed(reader(get_status=403), CFG, retain=lambda name, raw: kept.__setitem__(name, raw))
    assert "catalog_entry" in kept        # the failed body is retained too


def test_config_refuses_an_entry_outside_its_group_and_bad_paging():
    with pytest.raises(ValueError):
        C.CatalogConfig(entry="projects/p/locations/us-central1/entryGroups/other/entries/x")
    with pytest.raises(ValueError):
        C.CatalogConfig(max_pages=0)


def test_concept_seed_rejects_malformed_ids():
    for bad in ("acme_retail|pub|Section|x", "a|b|Concept", "||Concept|x", "forced:metrics/gross-margin.md"):
        with pytest.raises(ValueError):
            ConceptSeed(bad)
    s = ConceptSeed("acme_retail|pub_190192147fd7fd78|Concept|metrics/gross-margin")
    assert (s.bundle_id, s.publication_id, s.local) == ("acme_retail", "pub_190192147fd7fd78", "metrics/gross-margin")
