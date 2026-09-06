"""Second-principal negatives (authz.second_principal_cases): hermetic checks of the judges, controls, sanitization,
policy statements, GQL refusal, abort finalization and teardown isolation. No cloud (conftest pins a synthetic
operator). The live pass writes evidence/authz_cases.json."""
import json
import os
import subprocess
import sys

import pytest

import okf_bq_graph.authz as AZ

SA = "okf-receipt-restricted@test-project-0728-467323.iam.gserviceaccount.com"
OP = AZ.operator(refresh=True).split(":", 1)[-1]
PUB = "pub_190192147fd7fd78"
B = "acme_retail"
HID = AZ.HIDDEN
SEED = "metrics/gross-margin-legacy"
IDS = [SEED, HID, "metrics/gross-margin-current", "computations/gross-margin-period", "metrics/revenue", "computations/revenue-ytd", "policies/margin-standard"]
PROBE_DENIED = {"nodes": 0, "hidden": 0, "edges": 0, "vectors": 19}


def _res(status="OK", computations=(), concepts=(), paths=(), warnings=(), cache=None, jobs=()):
    scope = {"bundle_id": B, "publication_id": PUB, "requester": AZ.SA_ALIAS}
    if cache:
        scope["cache"] = cache
    return {"status": status, "computations": list(computations), "concepts": list(concepts), "paths": list(paths),
            "warnings": list(warnings), "scope": scope, "timing": {"total_ms": 1.0, "jobs": [{"job_id": j} for j in jobs]}}


def _comp(seed, via, concept="computations/gross-margin-period", sql="SELECT 1"):
    return {"seed": seed, "concept": concept, "computation_id": f"{B}|{PUB}|Concept|{concept}", "via": via, "concept_hops": len(via) - 1, "sql": sql}


ALLOWED = _res(computations=[_comp("metrics/revenue", ["metrics/revenue", "computations/revenue-ytd"], "computations/revenue-ytd")],
               concepts=[{"concept": "metrics/revenue"}], paths=[{"seed": "metrics/revenue", "via": ["metrics/revenue", "computations/revenue-ytd"]}])
NEGATIVE = _res(concepts=[{"concept": SEED, "replacement": {"concept": None, "label": "NONE"}}])
CONTROL = AZ.allowed_control(ALLOWED, NEGATIVE, SEED)
NO_CONTROL = AZ.allowed_control(_res("DENIED"), NEGATIVE, SEED)


# ---- identity / redaction / sanitization
def test_operator_is_synthetic_and_lazy(monkeypatch):
    assert OP == "operator@example.test"
    monkeypatch.delenv("OKF_OPERATOR_EMAIL"); monkeypatch.setenv("PATH", "")
    assert AZ.operator(refresh=True) == "user:"            # gcloud absent: tolerated, no exception
    with pytest.raises(RuntimeError):
        AZ._operator_member()                              # but a live grant refuses to run without an identity
    assert AZ.redact({"x": "keep"}, SA) == {"x": "keep"}   # empty operator never degenerates into replace("")
    monkeypatch.setenv("OKF_OPERATOR_EMAIL", "operator@example.test"); AZ.operator(refresh=True)


def test_run_module_imports_without_gcloud():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {k: v for k, v in os.environ.items() if k not in ("OKF_OPERATOR_EMAIL", "PATH")}
    env.update(PATH="", PYTHONPATH=root)
    r = subprocess.run([sys.executable, "-c", "import okf_bq_graph.run, okf_bq_graph.authz; print('imported')"], env=env, capture_output=True, text=True)
    assert r.returncode == 0 and "imported" in r.stdout, r.stderr[-400:]


def test_restricted_sa_env_override(monkeypatch):
    monkeypatch.delenv("OKF_SPIKE_RESTRICTED_SA", raising=False)
    assert AZ.restricted_sa() == AZ.SA_DEFAULT
    monkeypatch.setenv("OKF_SPIKE_RESTRICTED_SA", "other@x.iam.gserviceaccount.com")
    assert AZ.restricted_sa() == "other@x.iam.gserviceaccount.com"
    assert "@" not in AZ.SA_ALIAS


def test_redact_hides_sa_operator_and_any_email():
    obj = {"error": f"403 {SA} does not have bigquery.tables.getData", "who": OP, "other": "someone@example.com", "n": 3}
    r = AZ.redact(obj, SA)
    text = json.dumps(r)
    assert SA not in text and OP not in text and "someone@example.com" not in text
    assert AZ.SA_ALIAS in r["error"] and r["who"] == "operator" and r["other"] == "<email>" and r["n"] == 3


def test_leaks_is_exact_and_leaked_ids_lists_only_present():
    assert not AZ.leaks({"via": [SEED]}, HID)
    assert AZ.leaks({"x": f"{B}|{PUB}|Section|{HID}#s1"}, HID)
    assert AZ.leaked_ids({"via": [SEED, "metrics/revenue"]}, IDS) == [SEED, "metrics/revenue"]


def test_sanitize_ids_masks_every_form_longest_first():
    obj = {"via": [SEED, HID], "node": f"{B}|{PUB}|Section|{HID}#s1", "path": f"{HID}.md",
           "warn": f"seed {SEED} not found", "key_hidden": True, "err": f"Forbidden: row {HID} denied"}
    out = AZ.sanitize_ids(obj, IDS)
    text = json.dumps(out)
    assert not any(AZ.leaks(out, i) for i in IDS)
    assert out["via"] == [AZ.id_token(SEED), AZ.id_token(HID)] and AZ.id_token(SEED) != AZ.id_token(HID)
    assert out["node"].endswith(f"|Section|{AZ.id_token(HID)}#s1") and out["path"] == AZ.id_token(HID) + ".md"
    assert out["key_hidden"] is True and "<id:" in out["err"] and "-legacy" not in text


# ---- policy statements
def test_rls_statements_grantees_and_shapes():
    op = AZ.operator()
    s = AZ.rls_statements([op, f"serviceAccount:{SA}"])
    assert set(s) == {"nodes", "edges", "section_vectors"}
    for q in s.values():
        assert f"GRANT TO ('{op}', 'serviceAccount:{SA}')" in q and "FILTER USING (FALSE)" not in q
    assert f"local_id <> '{HID}'" in s["nodes"] and "REGEXP_CONTAINS(src_id" in s["edges"] and "Section" in s["section_vectors"]
    split = AZ.rls_statements([op], vector_grantees=[op, f"serviceAccount:{SA}"])
    assert SA not in split["nodes"] and SA not in split["edges"] and SA in split["section_vectors"]
    off = AZ.rls_statements([op], hide=False)
    assert all("FILTER USING (FALSE)" in q for q in off.values())


# ---- allowed control (P1 #1)
def test_allowed_control_requires_allowed_success_and_visible_seed():
    assert CONTROL["ok"] and CONTROL["negative_seed_visible"]
    assert not NO_CONTROL["ok"] and "allowed retrieval" in NO_CONTROL["reason"]
    stale = AZ.allowed_control(ALLOWED, _res("NO_SEED"), SEED)
    assert not stale["ok"] and "seed concept" in stale["reason"]
    leaky_allowed = AZ.allowed_control(_res(computations=[_comp("metrics/revenue", ["metrics/revenue", HID, "computations/revenue-ytd"])]), NEGATIVE, SEED)
    assert not leaky_allowed["ok"]


def test_negatives_are_blocked_without_control():
    for j in (AZ.judge_hidden_intermediate(NEGATIVE, NO_CONTROL), AZ.judge_hidden_intermediate(NEGATIVE, None),
              AZ.judge_denied_bundle(_res("DENIED"), IDS, None, NO_CONTROL), AZ.judge_output_denied(_res("NO_SEED"), PROBE_DENIED, IDS, SEED, NO_CONTROL)):
        assert j["label"] == "BLOCKED" and j["verdict"] == "NO_ALLOWED_CONTROL" and "control" in j["reason"]


# ---- judges
def test_judge_hidden_intermediate_enforced_and_leak():
    ok = AZ.judge_hidden_intermediate(NEGATIVE, CONTROL)
    assert ok["label"] == "MEASURED" and ok["verdict"] == "ENFORCED" and ok["replacement"] == {"concept": None, "label": "NONE"}
    leak = AZ.judge_hidden_intermediate(_res(computations=[_comp(SEED, [SEED, HID, "computations/gross-margin-period"])]), CONTROL)
    assert leak["label"] == "FAILED" and leak["leaks_hidden_id"] and leak["computations"] == 1
    assert AZ.judge_hidden_intermediate(_res(warnings=[f"path via {HID} removed"]), CONTROL)["label"] == "FAILED"
    assert AZ.judge_hidden_intermediate(_res("NO_SEED"), CONTROL)["label"] == "FAILED"     # empty because nothing was visible is not enforcement
    assert AZ.judge_hidden_intermediate(_res(paths=[{"via": [SEED]}]), CONTROL)["label"] == "FAILED"


def test_judge_denied_bundle():
    ok = AZ.judge_denied_bundle(_res("DENIED", warnings=["authorization error: Forbidden"]), IDS, "Forbidden: 403 Access Denied: Table nodes", CONTROL)
    assert ok["label"] == "MEASURED" and ok["leaked_id_count"] == 0 and ok["api_error_class"] == "Forbidden"
    bad_err = AZ.judge_denied_bundle(_res("DENIED"), IDS, f"Forbidden: row for {HID} denied", CONTROL)
    assert bad_err["label"] == "FAILED" and bad_err["leaked_id_count"] == 1
    rows = AZ.judge_denied_bundle(_res("OK", concepts=[{"concept": "metrics/revenue"}]), IDS, None, CONTROL)
    assert rows["label"] == "FAILED" and rows["concepts"] == 1


def test_judge_output_denied():
    ok = AZ.judge_output_denied(_res("NO_SEED", warnings=[f"seed {SEED} not found in pinned publication"]), PROBE_DENIED, IDS, SEED, CONTROL)
    assert ok["label"] == "MEASURED" and ok["seed_visible"] and ok["walk_denied"] and ok["leaked_id_count"] == 0 and "row count" in ok["seed_visibility_evidence"]
    named = AZ.judge_output_denied(_res("NO_SEED", warnings=[f"seed {SEED} not found; try {HID}"]), PROBE_DENIED, IDS, SEED, CONTROL)
    assert named["label"] == "FAILED" and named["leaked_id_count"] == 1
    no_seed_access = AZ.judge_output_denied(_res("NO_SEED"), {"nodes": 0, "hidden": 0, "edges": 0, "vectors": 0}, IDS, SEED, CONTROL)
    assert no_seed_access["label"] == "FAILED" and not no_seed_access["seed_visible"]
    walk_ran = AZ.judge_output_denied(_res("OK", computations=[_comp(SEED, [SEED, "computations/gross-margin-period"])]), PROBE_DENIED, IDS, SEED, CONTROL)
    assert walk_ran["label"] == "FAILED"


def test_natural_seed_variant_propagates_failure(): # P1 #6
    case = AZ.judge_output_denied(_res("NO_SEED"), PROBE_DENIED, IDS, SEED, CONTROL)
    bad = AZ.judge_output_denied(_res("OK", concepts=[{"concept": "policies/margin-standard"}]), PROBE_DENIED, IDS, "", CONTROL)
    folded = AZ.fold_variant(dict(case), "natural_seed", bad)
    assert folded["label"] == "FAILED" and folded["verdict"] == "NATURAL_SEED_LEAK_OR_UNEXPECTED" and folded["natural_seed"]["label"] == "FAILED"
    good = AZ.judge_output_denied(_res("DENIED", warnings=["authorization error: Forbidden"]), PROBE_DENIED, IDS, "", CONTROL)
    assert AZ.fold_variant(dict(case), "natural_seed", good)["label"] == "MEASURED"
    not_run = AZ.fold_variant(dict(case), "natural_seed", {"label": "NOT_RUN", "verdict": None, "error": "x"})
    assert not_run["label"] == "MEASURED" and not_run["natural_seed"]["label"] == "NOT_RUN"


def test_judge_owner_fallback():
    owner = _res(computations=[_comp(SEED, [SEED, HID, "computations/gross-margin-period"])])
    sa = _res()
    ok = AZ.judge_owner_fallback(owner, sa, [SA, SA, SA], SA, [OP, OP, OP], OP, owner_on_restricted=_res())
    assert ok["label"] == "MEASURED" and ok["verdict"] == "NO_FALLBACK" and ok["sa_jobs"] == 3 and ok["owner_saw_hidden"] and not ok["sa_saw_hidden"]
    assert ok["owner_on_restricted_fixture"]["saw_hidden"] is False and "ungoverned base dataset" in ok["note"]
    fell_back = AZ.judge_owner_fallback(owner, sa, [SA, OP, SA], SA, [OP], OP)
    assert fell_back["label"] == "FAILED" and not fell_back["sa_jobs_bound_to_sa"]
    assert AZ.judge_owner_fallback(owner, sa, [], SA, [OP], OP)["label"] == "FAILED"
    same_view = AZ.judge_owner_fallback(owner, owner, [SA], SA, [OP], OP)
    assert same_view["label"] == "FAILED" and same_view["sa_saw_hidden"]


WARM = _res(cache="MISS_STORED", computations=[_comp("metrics/revenue", ["metrics/revenue", "computations/revenue-ytd"], "computations/revenue-ytd")])
HIT = _res(cache="HIT_RECHECKED", computations=WARM["computations"])
REPLAY = _res("DENIED", cache="HIT_DENIED", warnings=["cached replay: current authorization check failed or unknown"])
FRESH = _res("DENIED", warnings=["authorization error: Forbidden"])


def test_judge_revocation_checks_every_surface():  # P1 #2
    ok = AZ.judge_revocation(WARM, HIT, REPLAY, FRESH, True, IDS)
    assert ok["label"] == "MEASURED" and ok["verdict"] == "FAIL_CLOSED" and ok["replay"]["cache"] == "HIT_DENIED"
    assert AZ.judge_revocation(WARM, HIT, HIT, FRESH, True, IDS)["label"] == "FAILED"           # served from cache
    assert AZ.judge_revocation(WARM, HIT, REPLAY, FRESH, False, IDS)["label"] == "FAILED"       # revocation never observed
    bad_replays = [_res("DENIED", cache="HIT_DENIED", concepts=[{"concept": "metrics/revenue"}]),
                   _res("DENIED", cache="HIT_DENIED", paths=[{"via": ["metrics/revenue"]}]),
                   _res("DENIED", cache="HIT_DENIED", warnings=[f"denied: {HID}"]),
                   _res("NO_SEED", cache="HIT_DENIED"),                                        # not an explicit denial
                   _res("DENIED", cache="MISS_STORED")]                                         # re-ran and stored again
    for r in bad_replays:
        assert AZ.judge_revocation(WARM, HIT, r, FRESH, True, IDS)["label"] == "FAILED", r
    bad_fresh = [_res("DENIED", concepts=[{"concept": "metrics/revenue"}]), _res("DENIED", paths=[{"via": ["x"]}]),
                 _res("DENIED", warnings=[f"seed {HID}"]), _res("NO_SEED")]
    for f in bad_fresh:
        assert AZ.judge_revocation(WARM, HIT, REPLAY, f, True, IDS)["label"] == "FAILED", f
    na = AZ.judge_revocation(_res(cache="BYPASS_INCOMPLETE_DEPENDENCIES"), HIT, REPLAY, FRESH, True, IDS)
    assert na["label"] == "NOT_APPLICABLE" and "cache" in na["reason"]


def test_judge_cross_principal_replay():
    owner_warm = _res(cache="MISS_STORED", computations=[_comp(SEED, [SEED, HID, "computations/gross-margin-period"])])
    ok = AZ.judge_cross_principal_replay(owner_warm, _res("DENIED", cache="HIT_DENIED", warnings=["cached replay: current authorization check failed or unknown"]), IDS)
    assert ok["label"] == "MEASURED" and ok["verdict"] == "CACHE_BOUND_TO_CREDENTIAL"
    served = AZ.judge_cross_principal_replay(owner_warm, _res("OK", cache="HIT_RECHECKED", computations=owner_warm["computations"]), IDS)
    assert served["label"] == "FAILED"
    assert AZ.judge_cross_principal_replay(_res(cache="BYPASS_INCOMPLETE_DEPENDENCIES"), REPLAY, IDS)["label"] == "NOT_APPLICABLE"


def test_record_case_keeps_judge_reason():  # P2 #8
    cases = {"k": {"description": "d", "label": "BLOCKED", "reason": "not reached"}}
    AZ.record_case(cases, "k", lambda: {"label": "NOT_APPLICABLE", "verdict": "NO_CACHE_ENTRY", "reason": "warm run did not store"}, SA)
    assert cases["k"]["label"] == "NOT_APPLICABLE" and cases["k"]["reason"] == "warm run did not store"
    AZ.record_case(cases, "k", lambda: {"label": "MEASURED", "verdict": "X"}, SA)
    assert "reason" not in cases["k"]
    AZ.record_case(cases, "k", lambda: (_ for _ in ()).throw(RuntimeError(f"boom {SA}")), SA)
    assert cases["k"]["label"] == "BLOCKED" and SA not in cases["k"]["reason"] and "boom" in cases["k"]["reason"]


# ---- _finish hygiene (P1 #5): passing AND failing surfaces
def _ev(cases):
    return {"started_at": "t", "principal": AZ.SA_ALIAS, "engine": "fallback", "cases": cases, "grants": [], "stages": [], "teardown": {}}


def test_finish_masks_ids_on_failed_and_passing_surfaces(tmp_path):
    failed = AZ.judge_hidden_intermediate(_res(computations=[_comp(SEED, [SEED, HID, "computations/gross-margin-period"])]), CONTROL)
    failed["full_result"] = _res(computations=[_comp(SEED, [SEED, HID, "computations/gross-margin-period"])], warnings=[f"seed {SEED}"])
    passing = AZ.judge_owner_fallback(_res(computations=[_comp(SEED, [SEED, HID, "computations/gross-margin-period"])]), _res(), [SA], SA, [OP], OP)
    passing["owner_paths"] = [{"seed": SEED, "via": [SEED, HID, "computations/gross-margin-period"]}]
    blocked = {"label": "BLOCKED", "reason": f"RuntimeError: {SA} could not read {HID}.md"}
    out = AZ._finish(_ev({"a": failed, "b": passing, "c": blocked}), str(tmp_path / "e.json"), SA, IDS)
    text = (tmp_path / "e.json").read_text()
    assert not any(AZ.leaks(text, i) for i in IDS) and SA not in text and OP not in text
    assert out["summary"] == {"a": "FAILED", "b": "MEASURED", "c": "BLOCKED"}         # judged on originals, published masked
    assert out["cases"]["b"]["owner_paths"][0]["via"][1] == AZ.id_token(HID) and AZ.SA_ALIAS in out["cases"]["c"]["reason"]
    assert out["id_sanitization"]["universe_known"] and out["cases"]["a"]["leaks_hidden_id"] is True


def test_finish_masks_fixture_constants_even_without_universe(tmp_path):
    out = AZ._finish(_ev({"a": {"label": "BLOCKED", "reason": f"aborted: {HID} and {SEED}"}}), str(tmp_path / "e.json"), SA, [])
    assert not out["id_sanitization"]["universe_known"] and "<id:" in out["cases"]["a"]["reason"] and HID not in (tmp_path / "e.json").read_text()


# ---- orchestration: GQL refusal (P1 #3), preflight BLOCKED, shared-setup abort (P1 #4), teardown isolation (P1 #7)
class _Never:
    def __getattr__(self, name):
        raise AssertionError(f"owner client used: {name}")


def test_gql_engine_refused_before_preflight(tmp_path, monkeypatch):
    import okf_bq_graph.reservation as R
    monkeypatch.setattr(R, "_load", lambda: {"windows": []})
    calls = []
    out = AZ.second_principal_cases(_Never(), PUB, "2026-09-05T00:00:00Z", engine="gql", sa_email=SA,
                                    factory=lambda p: calls.append(p), out_path=str(tmp_path / "g.json"))
    assert calls == [] and out["gql_variant"]["label"] == "BLOCKED" and "bounded window lifecycle" in out["gql_variant"]["reason"]
    assert all(c["label"] == "BLOCKED" and "engine=gql refused" in c["reason"] for c in out["cases"].values())
    assert out["window_gate"] == {"open": True} and (tmp_path / "g.json").exists()


def test_cases_all_blocked_when_preflight_fails(tmp_path):
    def boom(principal):
        raise PermissionError(f"403 {principal} getAccessToken denied")
    out = AZ.second_principal_cases(_Never(), PUB, "2026-09-05T00:00:00Z", sa_email=SA, factory=boom, out_path=str(tmp_path / "c.json"))
    assert all(c["label"] == "BLOCKED" and "preflight" in c["reason"] for c in out["cases"].values())
    text = (tmp_path / "c.json").read_text()
    assert SA not in text and OP not in text and out["summary"] == {k: "BLOCKED" for k in AZ.CASES}
    assert out["gql_variant"]["label"] == "BLOCKED"


class _FakeJob:
    def __init__(self, rows=()):
        self.rows, self.job_id, self.user_email = list(rows), "job-1", SA

    def result(self):
        return self.rows


class _SAClient:
    """Impersonated client whose preflight works and whose probes always raise (denied)."""
    def query(self, q, job_config=None, location=None):
        if "SELECT 1" in q:
            return _FakeJob([{"ok": 1}])
        from google.api_core import exceptions as gexc
        raise gexc.Forbidden("403 denied")


class _Owner:
    """Owner whose universe query fails (shared setup abort); teardown steps behave per flags."""
    def __init__(self, fail_reader=False, fail_restore=False):
        self.fail_reader, self.fail_restore, self.log = fail_reader, fail_restore, []

    def query(self, q, job_config=None, location=None):
        if "DISTINCT local_id" in q:
            raise RuntimeError(f"owner denied_ids query failed for {HID}")
        if "ROW ACCESS POLICY" in q:
            self.log.append("restore")
            if self.fail_restore:
                raise RuntimeError("restore failed")
            return _FakeJob()
        return _FakeJob()

    def get_dataset(self, ref):
        self.log.append("get_dataset")
        if self.fail_reader:
            raise RuntimeError(f"get_dataset failed for {SA}")
        from google.cloud import bigquery
        d = bigquery.Dataset(ref); d.access_entries = []
        return d

    def update_dataset(self, d, fields):
        self.log.append("update_dataset")

    class _Conn:
        def api_request(self, method, path, data=None):
            return {"rowAccessPolicies": []} if method == "GET" else {"bindings": []}
    _connection = _Conn()


def test_shared_setup_failure_is_persisted_and_torn_down(tmp_path):
    owner = _Owner()
    out = AZ.second_principal_cases(owner, PUB, "2026-09-05T00:00:00Z", sa_email=SA, factory=lambda p: _SAClient(),
                                    out_path=str(tmp_path / "a.json"), wait_s=0)
    assert (tmp_path / "a.json").exists()
    assert out["abort"]["stage"] == "denied_id_universe" and "<id:" in out["abort"]["reason"] and HID not in json.dumps(out)
    assert all(c["label"] == "BLOCKED" and c["reason"].startswith("aborted at denied_id_universe") for c in out["cases"].values())
    td = out["teardown"]
    assert "restore" in owner.log and td["steps"]["remove_dataset_reader"]["ok"] and td["steps"]["restore_policies"]["ok"]
    assert td["sa_still_in_grantees"] is False and td["sa_denied_after_teardown"] is True and td["status"] == "VERIFIED"
    assert SA not in (tmp_path / "a.json").read_text()


def test_teardown_continues_after_first_step_fails():
    owner = _Owner(fail_reader=True)
    td = AZ.teardown(owner, _SAClient(), SA, PUB, wait_s=0)
    assert not td["steps"]["remove_dataset_reader"]["ok"] and SA not in td["steps"]["remove_dataset_reader"]["error"]
    assert "restore" in owner.log and td["steps"]["restore_policies"]["ok"] and td["steps"]["readback_grantees"]["ok"]
    assert td["sa_denied_after_teardown"] is True and td["status"] == "UNVERIFIED"
    owner2 = _Owner(fail_restore=True)
    td2 = AZ.teardown(owner2, None, SA, PUB, wait_s=0)
    assert td2["steps"]["remove_dataset_reader"]["ok"] and owner2.log.count("restore") == 3      # every policy attempted
    assert all(not td2["steps"][f"restore_policy_{t}"]["ok"] for t in ("nodes", "edges", "section_vectors"))
    assert td2["steps"]["readback_grantees"]["ok"] and not td2["steps"]["sa_denied_after_teardown"]["ok"] and td2["status"] == "UNVERIFIED"


class _OwnerNodesPolicyFails(_Owner):
    """Only the nodes policy statement fails; edges and section_vectors must still be restored (P1 #7 residual)."""
    def query(self, q, job_config=None, location=None):
        if "ROW ACCESS POLICY" in q:
            self.log.append("restore:" + ("nodes" if ".nodes`" in q else "edges" if ".edges`" in q else "section_vectors"))
            if ".nodes`" in q:
                raise RuntimeError(f"nodes policy failed near {HID}")
            return _FakeJob()
        return super().query(q, job_config, location)


def test_each_policy_restoration_is_isolated():
    owner = _OwnerNodesPolicyFails(fail_reader=True)
    td = AZ.teardown(owner, None, SA, PUB, wait_s=0)
    assert owner.log.count("restore:nodes") == 1 and "restore:edges" in owner.log and "restore:section_vectors" in owner.log
    assert not td["steps"]["restore_policy_nodes"]["ok"] and td["steps"]["restore_policy_edges"]["ok"] and td["steps"]["restore_policy_section_vectors"]["ok"]
    assert HID not in json.dumps(td) and "<id:" in td["steps"]["restore_policy_nodes"]["error"] and td["status"] == "UNVERIFIED"
    with pytest.raises(RuntimeError, match="nodes"):        # strict callers still fail, after every statement was attempted
        AZ.set_rls(owner, [AZ.operator()])
    assert owner.log.count("restore:edges") == 2


# ---- P1 #5 residual: every log line is masked, not only the final JSON
def test_record_case_log_line_masks_ids_and_emails(capsys):
    cases = {"k": {"description": "d", "label": "BLOCKED", "reason": "not reached"}}
    AZ.record_case(cases, "k", lambda: (_ for _ in ()).throw(RuntimeError(f"{SA} could not read {HID}.md or {SEED}")), SA, IDS)
    out = capsys.readouterr().out
    assert HID not in out and SEED not in out and SA not in out and "<id:" in out and AZ.SA_ALIAS in out
    assert HID not in cases["k"]["reason"] and "<id:" in cases["k"]["reason"]
    AZ.record_case(cases, "k", lambda: {"label": "NOT_APPLICABLE", "verdict": "X", "reason": f"no entry for {HID}"}, SA, IDS)
    assert HID not in capsys.readouterr().out


def test_shared_setup_abort_log_is_masked(capsys, tmp_path):
    out = AZ.second_principal_cases(_Owner(), PUB, "2026-09-05T00:00:00Z", sa_email=SA, factory=lambda p: _SAClient(),
                                    out_path=str(tmp_path / "a.json"), wait_s=0)
    captured = capsys.readouterr().out
    assert "ABORT at denied_id_universe" in captured and HID not in captured and SA not in captured and OP not in captured
    assert HID not in json.dumps(out) and out["abort"]["stage"] == "denied_id_universe"


# ---- residual P2: executed failures survive aggregation
def test_fold_variant_failed_child_overrides_any_parent_label():
    na = {"label": "NOT_APPLICABLE", "verdict": "NO_CACHE_ENTRY", "reason": "warm run did not store"}
    bad = {"label": "FAILED", "verdict": "LEAK_OR_UNEXPECTED"}
    folded = AZ.fold_variant(dict(na), "cross_principal_replay", bad)
    assert folded["label"] == "FAILED" and folded["verdict"] == "CROSS_PRINCIPAL_REPLAY_LEAK_OR_UNEXPECTED" and folded["label_before_variant"] == "NOT_APPLICABLE"
    assert AZ.fold_variant({"label": "BLOCKED", "reason": "x"}, "v", bad)["label"] == "FAILED"
    assert AZ.fold_variant({"label": "MEASURED"}, "v", {"label": "NOT_RUN"})["label"] == "MEASURED"


def test_record_case_retains_partial_failed_observation_when_later_step_raises(capsys):
    cases = {"k": {"description": "d", "label": "BLOCKED", "reason": "not reached"}}

    def fn(partial):
        partial["replay_observation"] = {"label": "FAILED", "verdict": "REPLAY_LEAK_OR_UNEXPECTED", "concepts": 1}
        raise RuntimeError(f"fresh request raised for {HID}")
    AZ.record_case(cases, "k", fn, SA, IDS)
    c = cases["k"]
    assert c["label"] == "FAILED" and c["verdict"] == "PARTIAL_REPLAY_OBSERVATION_REPLAY_LEAK_OR_UNEXPECTED"
    assert c["replay_observation"]["concepts"] == 1 and "executed observation failed" in c["reason"] and HID not in c["reason"]
    assert HID not in capsys.readouterr().out

    def fn_ok_then_raise(partial):
        partial["replay_observation"] = {"label": "MEASURED", "verdict": "REPLAY_CLOSED"}
        raise RuntimeError("fresh request raised")
    AZ.record_case(cases, "k", fn_ok_then_raise, SA, IDS)
    assert cases["k"]["label"] == "BLOCKED" and cases["k"]["replay_observation"]["label"] == "MEASURED"


def test_labels_are_closed_set():
    assert AZ.LABELS == ("MEASURED", "FAILED", "BLOCKED", "NOT_APPLICABLE")
    assert set(AZ.CASES) == {"hidden_intermediate", "denied_bundle", "output_denied_seed_visible", "owner_fallback_negative", "revocation_before_cached_replay"}


def test_rls_grantees_reads_policy_iam_members():
    op = AZ.operator()

    class Conn:
        def api_request(self, method, path, data=None):
            if method == "GET":
                return {"rowAccessPolicies": [{"rowAccessPolicyReference": {"policyId": "hide_" + path.split("/tables/")[1].split("/")[0]}}]}
            assert method == "POST" and path.endswith(":getIamPolicy")
            return {"bindings": [{"role": "roles/bigquery.filteredDataViewer", "members": [op, f"serviceAccount:{SA}"]}]}

    class Client:
        _connection = Conn()
    g = AZ.rls_grantees(Client())
    assert set(g) == {"nodes", "edges", "section_vectors"} and all(v == sorted([op, f"serviceAccount:{SA}"]) for v in g.values())
    assert any(SA in m for ms in AZ.redact(g, SA).values() for m in ms) is False


def test_gql_window_gate_reports_reason(monkeypatch):
    import okf_bq_graph.reservation as R
    monkeypatch.setattr(R, "_load", lambda: {"windows": []})
    assert AZ.gql_window_gate() == {"open": True}
    monkeypatch.setattr(R, "require_clean_windows", lambda m: (_ for _ in ()).throw(RuntimeError("job cleanup is unverified for smoke-1")))
    g = AZ.gql_window_gate()
    assert not g["open"] and "smoke-1" in g["reason"]
