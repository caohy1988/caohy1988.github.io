"""Opus F1 / Astra P1#2 & #5: the leak detector must not false-positive on -legacy, and the single-pin checker must
fail on an injected mixed-publication response."""
import hashlib
from okf_bq_graph.run import _leaks, single_pin


def test_leak_regex_is_exact():
    assert not _leaks({"seed": "metrics/gross-margin-legacy", "via": ["metrics/gross-margin-legacy"]}, "metrics/gross-margin")
    assert _leaks({"x": "acme|pub|Section|metrics/gross-margin#s1"}, "metrics/gross-margin")
    assert _leaks({"x": "metrics/gross-margin"}, "metrics/gross-margin")
    assert _leaks({"replacement": {"concept": "metrics/gross-margin"}}, "metrics/gross-margin")


def _resp(pin, comp_pin=None, sha=None):
    cp = comp_pin or pin
    sql = "SELECT 1" if pin == "old" else "SELECT 2"
    return {"scope": {"publication_id": pin},
            "concepts": [{"concept_id": f"b|{pin}|Concept|metrics/gross-margin-legacy", "matched_sections": []}],
            "computations": [{"concept": "computations/gross-margin-period", "computation_id": f"b|{cp}|Concept|computations/gross-margin-period",
                              "section_id": f"b|{cp}|Section|computations/gross-margin-period#s0", "sql": sql,
                              "sql_sha256": sha or hashlib.sha256(sql.encode()).hexdigest()}]}


EXPECTED = {pin: {"computations/gross-margin-period": hashlib.sha256(sql.encode()).hexdigest()}
            for pin, sql in (("old", "SELECT 1"), ("new", "SELECT 2"))}


def test_single_pin_passes_consistent_response():
    assert single_pin(_resp("old"), EXPECTED)["ok"]
    assert single_pin(_resp("new"), EXPECTED)["ok"]


def test_single_pin_fails_mixed_ids():
    r = single_pin(_resp("old", comp_pin="new"), EXPECTED)
    assert not r["ok"] and set(r["pins"]) == {"old", "new"}


def test_single_pin_fails_foreign_sql_digest():
    r = single_pin(_resp("old", sha=EXPECTED["new"]["computations/gross-margin-period"]), EXPECTED)
    assert not r["ok"] and "digest" in r["reason"]


def test_single_pin_hashes_returned_sql_bytes():
    r = _resp("old")
    r["computations"][0]["sql"] = "SELECT 2"
    assert not single_pin(r, EXPECTED)["ok"]


def test_single_pin_rejects_foreign_provenance():
    r = _resp("old")
    r["concepts"][0]["provenance"] = [{"source_id": "b|new|Source|warehouse"}]
    assert not single_pin(r, EXPECTED)["ok"]
