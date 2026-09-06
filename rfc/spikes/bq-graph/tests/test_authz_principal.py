"""Second-principal negatives (authz.second_principal_cases): hermetic checks of the judges, redaction, policy
statements and the BLOCKED path. No cloud. The live pass writes evidence/authz_cases.json."""
import json

import pytest

import okf_bq_graph.authz as AZ

SA = "okf-receipt-restricted@test-project-0728-467323.iam.gserviceaccount.com"
OP = AZ.OPERATOR.split(":", 1)[-1]
PUB = "pub_190192147fd7fd78"
B = "acme_retail"
HID = AZ.HIDDEN
IDS = ["metrics/gross-margin-legacy", "metrics/gross-margin", "metrics/gross-margin-current", "computations/gross-margin-period",
       "metrics/revenue", "computations/revenue-ytd", "policies/margin-standard"]


def _res(status="OK", computations=(), concepts=(), paths=(), warnings=(), cache=None, jobs=()):
    scope = {"bundle_id": B, "publication_id": PUB, "requester": AZ.SA_ALIAS}
    if cache:
        scope["cache"] = cache
    return {"status": status, "computations": list(computations), "concepts": list(concepts), "paths": list(paths),
            "warnings": list(warnings), "scope": scope, "timing": {"total_ms": 1.0, "jobs": [{"job_id": j} for j in jobs]}}


def _comp(seed, via, concept="computations/gross-margin-period", sql="SELECT 1"):
    return {"seed": seed, "concept": concept, "computation_id": f"{B}|{PUB}|Concept|{concept}", "via": via, "concept_hops": len(via) - 1, "sql": sql}


# ---- identity / redaction
def test_restricted_sa_env_override(monkeypatch):
    monkeypatch.delenv("OKF_SPIKE_RESTRICTED_SA", raising=False)
    assert AZ.restricted_sa() == AZ.SA_DEFAULT
    monkeypatch.setenv("OKF_SPIKE_RESTRICTED_SA", "other@x.iam.gserviceaccount.com")
    assert AZ.restricted_sa() == "other@x.iam.gserviceaccount.com"
    assert AZ.SA_ALIAS not in AZ.SA_DEFAULT and "@" not in AZ.SA_ALIAS


def test_redact_hides_sa_operator_and_any_email():
    obj = {"error": f"403 {SA} does not have bigquery.tables.getData", "who": OP, "other": "someone@example.com", "n": 3}
    r = AZ.redact(obj, SA)
    text = json.dumps(r)
    assert SA not in text and OP not in text and "someone@example.com" not in text
    assert AZ.SA_ALIAS in r["error"] and r["who"] == "operator" and r["other"] == "<email>" and r["n"] == 3


def test_leaks_is_exact_and_leaked_ids_lists_only_present():
    assert not AZ.leaks({"via": ["metrics/gross-margin-legacy"]}, HID)
    assert AZ.leaks({"x": f"{B}|{PUB}|Section|{HID}#s1"}, HID)
    assert AZ.leaked_ids({"via": ["metrics/gross-margin-legacy", "metrics/revenue"]}, IDS) == ["metrics/gross-margin-legacy", "metrics/revenue"]


# ---- policy statements
def test_rls_statements_grantees_and_shapes():
    s = AZ.rls_statements([AZ.OPERATOR, f"serviceAccount:{SA}"])
    assert set(s) == {"nodes", "edges", "section_vectors"}
    for q in s.values():
        assert f"GRANT TO ('{AZ.OPERATOR}', 'serviceAccount:{SA}')" in q and "FILTER USING (FALSE)" not in q
    assert f"local_id <> '{HID}'" in s["nodes"] and "REGEXP_CONTAINS(src_id" in s["edges"] and "Section" in s["section_vectors"]
    split = AZ.rls_statements([AZ.OPERATOR], vector_grantees=[AZ.OPERATOR, f"serviceAccount:{SA}"])
    assert SA not in split["nodes"] and SA not in split["edges"] and SA in split["section_vectors"]
    off = AZ.rls_statements([AZ.OPERATOR], hide=False)
    assert all("FILTER USING (FALSE)" in q for q in off.values())


# ---- judges
def test_judge_hidden_intermediate_enforced_and_leak():
    ok = AZ.judge_hidden_intermediate(_res(concepts=[{"concept": "metrics/gross-margin-legacy", "replacement": {"concept": None, "label": "NONE"}}]))
    assert ok["label"] == "MEASURED" and ok["verdict"] == "ENFORCED" and ok["replacement"] == {"concept": None, "label": "NONE"}
    leak = AZ.judge_hidden_intermediate(_res(computations=[_comp("metrics/gross-margin-legacy", ["metrics/gross-margin-legacy", HID, "computations/gross-margin-period"])]))
    assert leak["label"] == "FAILED" and leak["leaks_hidden_id"] and leak["computations"] == 1
    explain_leak = AZ.judge_hidden_intermediate(_res(warnings=[f"path via {HID} removed"]))
    assert explain_leak["label"] == "FAILED"


def test_judge_denied_bundle():
    ok = AZ.judge_denied_bundle(_res("DENIED", warnings=["authorization error: Forbidden"]), IDS, "Forbidden: 403 Access Denied: Table nodes")
    assert ok["label"] == "MEASURED" and ok["leaked_id_count"] == 0 and ok["api_error_class"] == "Forbidden"
    bad_err = AZ.judge_denied_bundle(_res("DENIED"), IDS, f"Forbidden: row for {HID} denied")
    assert bad_err["label"] == "FAILED" and bad_err["leaked_id_count"] == 1
    rows = AZ.judge_denied_bundle(_res("OK", concepts=[{"concept": "metrics/revenue"}]), IDS)
    assert rows["label"] == "FAILED" and rows["rows"] == 1


def test_judge_output_denied():
    probe = {"nodes": 0, "hidden": 0, "edges": 0, "vectors": 19}
    seed = "metrics/gross-margin-legacy"
    ok = AZ.judge_output_denied(_res("NO_SEED", warnings=[f"seed {seed} not found in pinned publication"]), probe, IDS, seed)
    assert ok["label"] == "MEASURED" and ok["seed_visible"] and ok["walk_denied"] and ok["leaked_id_count"] == 0
    named = AZ.judge_output_denied(_res("NO_SEED", warnings=[f"seed {seed} not found; try {HID}"]), probe, IDS, seed)
    assert named["label"] == "FAILED" and named["leaked_id_count"] == 1
    no_seed_access = AZ.judge_output_denied(_res("NO_SEED"), {"nodes": 0, "hidden": 0, "edges": 0, "vectors": 0}, IDS, seed)
    assert no_seed_access["label"] == "FAILED" and not no_seed_access["seed_visible"]
    walk_ran = AZ.judge_output_denied(_res("OK", computations=[_comp(seed, [seed, "computations/gross-margin-period"])]), probe, IDS, seed)
    assert walk_ran["label"] == "FAILED"


def test_judge_owner_fallback():
    owner = _res(computations=[_comp("metrics/gross-margin-legacy", ["metrics/gross-margin-legacy", HID, "computations/gross-margin-period"])])
    sa = _res()
    ok = AZ.judge_owner_fallback(owner, sa, [SA, SA, SA], SA, [OP, OP, OP], OP)
    assert ok["label"] == "MEASURED" and ok["verdict"] == "NO_FALLBACK" and ok["sa_jobs"] == 3 and ok["owner_saw_hidden"] and not ok["sa_saw_hidden"]
    fell_back = AZ.judge_owner_fallback(owner, sa, [SA, OP, SA], SA, [OP], OP)
    assert fell_back["label"] == "FAILED" and not fell_back["sa_jobs_bound_to_sa"]
    no_jobs = AZ.judge_owner_fallback(owner, sa, [], SA, [OP], OP)
    assert no_jobs["label"] == "FAILED"
    same_view = AZ.judge_owner_fallback(owner, owner, [SA], SA, [OP], OP)
    assert same_view["label"] == "FAILED" and same_view["sa_saw_hidden"]


def test_judge_revocation():
    warm = _res(cache="MISS_STORED", computations=[_comp("metrics/revenue", ["metrics/revenue", "computations/revenue-ytd"], "computations/revenue-ytd")])
    hit = _res(cache="HIT_RECHECKED", computations=warm["computations"])
    replay = _res("DENIED", cache="HIT_DENIED", warnings=["cached replay: current authorization check failed or unknown"])
    fresh = _res("DENIED", warnings=["authorization error: Forbidden"])
    ok = AZ.judge_revocation(warm, hit, replay, fresh, True)
    assert ok["label"] == "MEASURED" and ok["verdict"] == "FAIL_CLOSED"
    served = AZ.judge_revocation(warm, hit, hit, fresh, True)
    assert served["label"] == "FAILED"
    unobserved = AZ.judge_revocation(warm, hit, replay, fresh, False)
    assert unobserved["label"] == "FAILED"
    na = AZ.judge_revocation(_res(cache="BYPASS_INCOMPLETE_DEPENDENCIES"), hit, replay, fresh, True)
    assert na["label"] == "NOT_APPLICABLE" and "cache" in na["reason"]


# ---- BLOCKED path: impersonation unavailable -> every case BLOCKED with the redacted API error, nothing else touched
def test_preflight_blocked_records_redacted_error():
    def boom(principal):
        raise PermissionError(f"403 Permission 'iam.serviceAccounts.getAccessToken' denied on {principal}")
    pre, client = AZ.preflight(SA, factory=boom)
    assert client is None and pre["status"] == "BLOCKED" and SA not in pre["error"] and AZ.SA_ALIAS in pre["error"] and "getAccessToken" in pre["error"]


def test_cases_all_blocked_when_preflight_fails(tmp_path):
    class Owner:  # must never be used when impersonation is unavailable
        def __getattr__(self, name):
            raise AssertionError(f"owner client used: {name}")

    def boom(principal):
        raise PermissionError(f"403 {principal} getAccessToken denied")
    out = AZ.second_principal_cases(Owner(), PUB, "2026-09-05T00:00:00Z", sa_email=SA, factory=boom, out_path=str(tmp_path / "c.json"))
    assert set(out["cases"]) == set(AZ.CASES) and all(c["label"] == "BLOCKED" for c in out["cases"].values())
    assert all("preflight" in c["reason"] for c in out["cases"].values())
    text = (tmp_path / "c.json").read_text()
    assert SA not in text and OP not in text and out["summary"] == {k: "BLOCKED" for k in AZ.CASES}
    assert all(label in AZ.LABELS for label in out["summary"].values())


def test_labels_are_closed_set():
    assert AZ.LABELS == ("MEASURED", "FAILED", "BLOCKED", "NOT_APPLICABLE")
    assert set(AZ.CASES) == {"hidden_intermediate", "denied_bundle", "output_denied_seed_visible", "owner_fallback_negative", "revocation_before_cached_replay"}


def test_rls_grantees_reads_policy_iam_members():
    class Conn:
        def api_request(self, method, path, data=None):
            if method == "GET":
                return {"rowAccessPolicies": [{"rowAccessPolicyReference": {"policyId": "hide_" + path.split("/tables/")[1].split("/")[0]}}]}
            assert method == "POST" and path.endswith(":getIamPolicy")
            return {"bindings": [{"role": "roles/bigquery.filteredDataViewer", "members": [AZ.OPERATOR, f"serviceAccount:{SA}"]}]}

    class Client:
        _connection = Conn()
    g = AZ.rls_grantees(Client())
    assert set(g) == {"nodes", "edges", "section_vectors"} and all(v == sorted([AZ.OPERATOR, f"serviceAccount:{SA}"]) for v in g.values())
    assert any(SA in m for ms in AZ.redact(g, SA).values() for m in ms) is False  # alias only after redaction


def test_gql_window_gate_reports_reason(monkeypatch):
    import okf_bq_graph.reservation as R
    monkeypatch.setattr(R, "_load", lambda: {"windows": []})
    assert AZ.gql_window_gate() == {"open": True}
    monkeypatch.setattr(R, "require_clean_windows", lambda m: (_ for _ in ()).throw(RuntimeError("job cleanup is unverified for smoke-1")))
    g = AZ.gql_window_gate()
    assert not g["open"] and "smoke-1" in g["reason"]
