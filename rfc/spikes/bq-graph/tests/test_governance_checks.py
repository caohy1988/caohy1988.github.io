"""Opus F1 / Astra P1#2 & #5: the leak detector must not false-positive on -legacy, and the single-pin checker must
fail on an injected mixed-publication response."""
from okf_bq_graph.run import _leaks, single_pin


def test_leak_regex_is_exact():
    assert not _leaks({"seed": "metrics/gross-margin-legacy", "via": ["metrics/gross-margin-legacy"]}, "metrics/gross-margin")
    assert _leaks({"x": "acme|pub|Section|metrics/gross-margin#s1"}, "metrics/gross-margin")
    assert _leaks({"x": "metrics/gross-margin"}, "metrics/gross-margin")
    assert _leaks({"replacement": {"concept": "metrics/gross-margin"}}, "metrics/gross-margin")


def _resp(pin, comp_pin=None, sha="s1"):
    cp = comp_pin or pin
    return {"scope": {"publication_id": pin},
            "concepts": [{"concept_id": f"b|{pin}|Concept|metrics/gross-margin-legacy", "matched_sections": []}],
            "computations": [{"concept": "computations/gross-margin-period", "computation_id": f"b|{cp}|Concept|computations/gross-margin-period",
                              "section_id": f"b|{cp}|Section|computations/gross-margin-period#s0", "sql_sha256": sha}]}


EXPECTED = {"old": {"computations/gross-margin-period": "s1"}, "new": {"computations/gross-margin-period": "s2"}}


def test_single_pin_passes_consistent_response():
    assert single_pin(_resp("old"), EXPECTED)["ok"]
    assert single_pin(_resp("new", sha="s2"), EXPECTED)["ok"]


def test_single_pin_fails_mixed_ids():
    r = single_pin(_resp("old", comp_pin="new"), EXPECTED)
    assert not r["ok"] and set(r["pins"]) == {"old", "new"}


def test_single_pin_fails_foreign_sql_digest():
    r = single_pin(_resp("old", sha="s2"), EXPECTED)     # ids all 'old' but SQL bytes from the new publication
    assert not r["ok"] and "digest" in r["reason"]
