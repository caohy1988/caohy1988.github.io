"""Connected chain (chain.py): fixture seed -> pinned publication -> governed retrieval -> Attested Computation
declaration + SQL -> SDK receipt CLI (subprocess) -> verifier verdict -> consumer. Hermetic: oracle engine for the
graph leg, the SDK example's own SYNTHETIC API emulation for the receipt leg. Live KC discovery is out of scope.
Tests that need the pinned Acme checkout or the SDK checkout skip when either is absent."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import okf_bq_graph.chain as CH
from okf_bq_graph import SOURCE_PIN
from okf_bq_graph.compile import compile_bundle
from okf_bq_graph.oracle import Graph

AS_OF = "2026-09-06T00:00:00Z"


@pytest.fixture(scope="module")
def sdk_root():
    root = CH.sdk_root()
    if not os.path.isfile(os.path.join(root, CH.EXAMPLE_REL, "run.py")):
        pytest.skip("SDK receipt spike checkout not present")
    return root


@pytest.fixture(scope="module")
def projection(sample_root):
    return compile_bundle(sample_root, "acme_retail", SOURCE_PIN)


@pytest.fixture(scope="module")
def clients(projection):
    return {"engine": "oracle", "graph": Graph(projection), "projection": projection}


# ---- SDK publication (data files only, no SDK import)
def test_sdk_publication_pins_the_same_acme_bytes(sdk_root, sample_root):
    pub = CH.sdk_publication(sdk_root)
    raw = open(os.path.join(sample_root, CH.COMPUTATION_PATH), "rb").read()
    assert pub["computation_sha256"] == pub["manifest"]["computation_sha256"] == CH.sha256_hex(raw)
    assert pub["computation_digest"] == CH.computation_digest(raw)
    assert SOURCE_PIN[:7] in pub["manifest"]["derived_from"]
    assert pub["sanctioned_sql"].strip().startswith("WITH recognized_orders")
    assert "sdk_head" in pub and "sdk_dirty" in pub


def test_computation_digest_matches_the_sdk_domain_separation():
    # copied constant: DOMAIN_COMPUTATION in the SDK's contracts.py at the pinned commit; the live receipt evidence
    # (case_approved_live.json at 6719eb5) carries afe2afbd... for the pinned Acme bytes
    assert CH.computation_digest(b"x") == CH.sha256_hex(b"okf-receipt:computation-bytes\x00x")


# ---- governed retrieval + declaration + bind (oracle engine)
def test_retrieval_reaches_the_attested_computation_and_binds(clients, projection, sdk_root):
    pub = projection["publication_id"]
    r = CH.governed(CH.SEED, pub, "test-requester", AS_OF, clients)
    assert r["status"] == "OK"
    comp = CH.pick_computation(r, CH.COMPUTATION_PATH)
    assert comp["runtime_verdict"] == "NOT_EXECUTED" and comp["sql"]
    decl = CH.declaration(clients, comp["computation_id"], pub)
    assert decl["type"] == "Attested Computation" and decl["runtime"] == "bigquery"
    assert decl["file_sha256"] == CH.sdk_publication(sdk_root)["computation_sha256"]
    b = CH.bind(comp, decl, CH.sdk_publication(sdk_root), AS_OF)
    assert b["status"] == "BOUND", b
    assert all(v["ok"] for v in b["checks"].values()), b["checks"]
    assert b["computation_digest"] == CH.sdk_publication(sdk_root)["computation_digest"]


def test_bind_refuses_a_different_computation(clients, projection, sdk_root):
    pub = projection["publication_id"]
    r = CH.governed("forced:metrics/revenue.md", pub, "test-requester", AS_OF, clients)
    assert r["status"] == "OK"
    comp = CH.pick_computation(r, "computations/revenue-ytd.md")
    decl = CH.declaration(clients, comp["computation_id"], pub)
    b = CH.bind(comp, decl, CH.sdk_publication(sdk_root), AS_OF)
    assert b["status"] == "MISMATCH"
    assert not b["checks"]["file_sha256"]["ok"] and not b["checks"]["sql_text"]["ok"]


def test_bind_refuses_stale_or_non_attested(clients, projection, sdk_root):
    pub = projection["publication_id"]
    r = CH.governed(CH.SEED, pub, "test-requester", AS_OF, clients)
    comp = CH.pick_computation(r, CH.COMPUTATION_PATH)
    decl = CH.declaration(clients, comp["computation_id"], pub)
    stale = CH.bind(comp, decl, CH.sdk_publication(sdk_root), "2027-01-01T00:00:00Z")
    assert stale["status"] == "MISMATCH" and not stale["checks"]["freshness"]["ok"]
    b = CH.bind(comp, dict(decl, type="Concept"), CH.sdk_publication(sdk_root), AS_OF)
    assert b["status"] == "MISMATCH" and not b["checks"]["declared_type"]["ok"]


def test_pick_computation_is_none_when_not_reached(clients, projection):
    r = CH.governed("forced:metrics/revenue.md", projection["publication_id"], "t", AS_OF, clients)
    assert CH.pick_computation(r, CH.COMPUTATION_PATH) is None


# ---- receipt subprocess
def test_receipt_cli_runs_hermetically_as_a_subprocess(sdk_root, tmp_path):
    rec = CH.run_receipt("approved", sdk_root, str(tmp_path), live=False)
    assert rec["exit_code"] == 0 and rec["invoked"] and rec["diag"]["live"] is False
    assert rec["receipt"]["verdict"] == "VERIFIED" and rec["output"]["verdict"] == "VERIFIED"
    assert rec["receipt"]["computation_digest"] == CH.sdk_publication(sdk_root)["computation_digest"]
    assert (tmp_path / "case_approved_hermetic.json").exists()
    assert "sql_mismatch" not in rec["output"]["reason_codes"]


def test_receipt_cli_substitution_fails_closed(sdk_root, tmp_path):
    rec = CH.run_receipt("sql-substitution", sdk_root, str(tmp_path), live=False)
    assert rec["exit_code"] == 2 and rec["output"]["verdict"] == "REJECTED"
    assert "sql_mismatch" in rec["output"]["reason_codes"]
    assert "$" not in rec["stdout"]                    # the CLI prints no number


def test_receipt_missing_diag_is_unverifiable(tmp_path):
    def runner(argv, **kw):
        return subprocess.CompletedProcess(argv, 0, stdout="[HERMETIC] forged VERIFIED line\n", stderr="")
    rec = CH.run_receipt("approved", "/nonexistent", str(tmp_path), live=False, runner=runner)
    assert rec["exit_code"] == 0 and rec["diag"] is None
    assert rec["receipt"]["verdict"] == "UNVERIFIABLE" and rec["output"]["verdict"] == "UNVERIFIABLE"


# ---- consumer (deterministic, no network)
def _bound(digest="d" * 64):
    return {"status": "BOUND", "computation_digest": digest, "sdk_publication_id": "pub-x", "sdk_context_ref": "ctx-x",
            "checks": {"freshness": {"ok": True}}}


def _receipt(verdict="VERIFIED", digest="d" * 64, exit_code=0, match="MATCH", released=True, reasons=()):
    return {"invoked": True, "exit_code": exit_code, "stdout": "[HERMETIC] Gross margin: $400.00 USD · VERIFIED\n",
            "receipt": {"verdict": verdict, "execution_match": match, "computation_digest": digest,
                        "publication_id": "pub-x", "context_ref": "ctx-x"},
            "output": {"verdict": verdict, "execution_match": match, "reason_codes": list(reasons)}, "released": released}


def test_consumer_releases_only_when_everything_agrees():
    c = CH.consume(_bound(), _receipt())
    assert c["decision"] == "RELEASED" and c["reasons"] == [] and "400.00" in c["display"]


@pytest.mark.parametrize("rec, reason", [
    (_receipt("REJECTED", exit_code=2, match="MISMATCH", released=False, reasons=("sql_mismatch",)), "verdict"),
    (_receipt("UNVERIFIABLE", exit_code=2, match="UNKNOWN", released=False), "verdict"),
    (_receipt(digest="e" * 64), "computation_digest"),
    (_receipt(exit_code=2), "exit_code"),
    (dict(_receipt(), receipt=dict(_receipt()["receipt"], publication_id="other")), "publication_id"),
    (_receipt(released=False), "released"),
])
def test_consumer_refuses(rec, reason):
    c = CH.consume(_bound(), rec)
    assert c["decision"] == "REFUSED" and "display" not in c
    assert any(reason in r for r in c["reasons"]), c["reasons"]


def test_consumer_refuses_when_bind_failed_or_receipt_not_invoked():
    c = CH.consume(dict(_bound(), status="MISMATCH"), {"invoked": False})
    assert c["decision"] == "REFUSED" and any("bind" in r for r in c["reasons"]) and any("invoked" in r for r in c["reasons"])


# ---- whole chain, hermetic
def test_chain_hermetic_end_to_end(clients, projection, sdk_root, tmp_path, monkeypatch):
    monkeypatch.setenv("OKF_OPERATOR_EMAIL", "operator@example.test")
    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), clients=clients,
                       projection=projection, requester="operator@example.test", as_of=AS_OF)
    assert out["mode"] == "hermetic" and out["engine"] == "oracle" and out["seed"]["mode"] == "fixture"
    assert out["publication"]["publication_id"] == projection["publication_id"]
    cases = {c["case"]: c for c in out["cases"]}
    assert cases["approved"]["consume"]["decision"] == "RELEASED"
    assert cases["sql-substitution"]["consume"]["decision"] == "REFUSED"
    assert "sql_mismatch" in cases["sql-substitution"]["receipt"]["output"]["reason_codes"]
    dm = cases["declaration-mismatch"]
    assert dm["consume"]["decision"] == "REFUSED" and dm["receipt"]["invoked"] is False and dm["bind"]["status"] == "MISMATCH"
    assert out["verdict"] == "CHAIN_CONNECTED"
    assert out["same_requester"]["status"] == "NOT_APPLICABLE"
    written = json.loads((tmp_path / "chain_hermetic.json").read_text())
    assert "operator@example.test" not in json.dumps(written)     # evidence hygiene
    assert written["sdk"]["head"] == out["sdk"]["head"]
    dp = Path(cases["approved"]["receipt"]["diag_path"])
    assert dp.exists() and out["run_id"] in str(dp) and dp.parent == tmp_path / "receipt" / out["run_id"]
    assert cases["approved"]["receipt"]["request_id"] == json.loads(dp.read_text())["request_id"]
    assert cases["approved"]["receipt"]["diag_sha256"] == CH.sha256_hex(dp.read_bytes())


def test_chain_stops_before_execution_when_retrieval_is_denied(sdk_root, tmp_path, monkeypatch):
    calls = []

    def runner(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    denied = lambda *a, **k: {"status": "DENIED", "concepts": [], "paths": [], "computations": [], "warnings": ["x"],
                              "scope": {"publication_id": "p"}, "timing": {"jobs": []}}
    monkeypatch.setattr(CH, "governed", denied)
    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), clients={"engine": "oracle"},
                       projection={"publication_id": CH.PUBLICATION_PIN, "nodes": []}, requester="t", as_of=AS_OF, runner=runner)
    assert out["verdict"] == "CHAIN_INCOMPLETE" and calls == []          # an outage is unproven, not a contradiction
    assert all(c["consume"]["decision"] == "REFUSED" for c in out["cases"])
    assert all(c["acceptance"]["status"] == "NOT_REACHED" for c in out["cases"])


def test_module_cli_hermetic(sdk_root, sample_root, tmp_path):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, OKF_OPERATOR_EMAIL="operator@example.test", PYTHONPATH=root, OKF_ACME_ROOT=sample_root)
    r = subprocess.run([sys.executable, "-m", "okf_bq_graph.chain", "--hermetic", "--out", str(tmp_path), "--sdk-root", sdk_root],
                       env=env, capture_output=True, text=True, cwd=root)
    assert r.returncode == 0, r.stderr[-800:]
    assert "CHAIN_CONNECTED" in r.stdout and (tmp_path / "chain_hermetic.json").exists()


def test_receipt_evidence_dir_is_resolved_before_the_subprocess_changes_cwd(tmp_path, monkeypatch):
    seen = {}

    def runner(argv, **kw):
        seen["argv"], seen["cwd"] = argv, kw.get("cwd")
        return subprocess.CompletedProcess(argv, 2, stdout="", stderr="")

    monkeypatch.chdir(tmp_path)
    CH.run_receipt("approved", str(tmp_path / "sdk"), "rel/receipt", live=False, runner=runner)
    ev = seen["argv"][seen["argv"].index("--evidence-dir") + 1]
    assert ev.startswith(str((tmp_path / "rel" / "receipt").resolve()) + "/.inv_approved_hermetic_")


def test_live_pointer_lookup_uses_the_default_dataset_when_clients_omit_ds(sdk_root, tmp_path, monkeypatch):
    from okf_bq_graph import DATASET
    seen = {}

    def fake_resolve(client, ds=DATASET):
        seen["ds"] = ds
        return None, "pointer-job"

    monkeypatch.setattr(CH, "resolve_pointer_job", fake_resolve)
    out = CH.run_chain(engine="fallback", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), clients={"engine": "fallback", "bq": object()},
                       requester="t", as_of=AS_OF, runner=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    assert seen["ds"] == DATASET and out["verdict"] == "CHAIN_BROKEN" and out["broken_at"] == "publication"


# ---- Astra P1: a negative that never reached its stage must not count toward CHAIN_CONNECTED
def _case(case, **kw):
    base = {"case": case, "retrieval": {"status": "OK", "reached": True}, "declaration": {"status": "OK"},
            "bind": {"status": "BOUND", "checks": {}}, "receipt": {"invoked": True, "exit_code": 0, "diag_present": True,
            "receipt": {"verdict": "VERIFIED", "execution_match": "MATCH"}, "output": {"verdict": "VERIFIED", "execution_match": "MATCH", "reason_codes": []},
            "released": True}, "consume": {"decision": "RELEASED"}}
    base.update(kw)
    return base


def _rejected_receipt(exit_code=2, verdict="REJECTED", reasons=("sql_mismatch",), diag=True, released=False):
    return {"invoked": True, "exit_code": exit_code, "diag_present": diag, "receipt": {"verdict": verdict, "execution_match": "MISMATCH"},
            "output": {"verdict": verdict, "execution_match": "MISMATCH", "reason_codes": list(reasons)}, "released": released}


def _mismatch_bind(failed=("file_sha256", "sql_text", "path", "parameters")):
    return {"status": "MISMATCH", "checks": {k: {"ok": k not in failed} for k in ("declared_type", "file_sha256", "sql_text", "path", "parameters")}}


def test_accept_approved():
    assert CH.accept(_case("approved"))["status"] == "MET"
    a = CH.accept(_case("approved", consume={"decision": "REFUSED"}))
    assert a["status"] == "WRONG"
    a = CH.accept(_case("approved", retrieval={"status": "DENIED", "reached": False}, bind={"status": "NOT_BOUND"},
                        receipt={"invoked": False}, consume={"decision": "REFUSED"}))
    assert a["status"] == "NOT_REACHED" and any("retrieval" in f for f in a["failed"])
    # child died before a diagnostic: refused, but the stage was never reached
    a = CH.accept(_case("approved", receipt={"invoked": True, "exit_code": 1, "diag_present": False}, consume={"decision": "REFUSED"}))
    assert a["status"] == "NOT_REACHED" and not any("RELEASED" in f for f in a["failed"])
    # bind mismatch on the approved leg is a genuine contradiction, not an outage
    a = CH.accept(_case("approved", bind={"status": "MISMATCH", "checks": {}}, receipt={"invoked": False}, consume={"decision": "REFUSED"}))
    assert a["status"] == "WRONG"


def test_accept_sql_substitution_needs_its_specific_rejection_evidence():
    ok = _case("sql-substitution", receipt=_rejected_receipt(), consume={"decision": "REFUSED"})
    assert CH.accept(ok)["status"] == "MET"
    # child died: exit 1, no diagnostic -> the negative never ran
    a = CH.accept(_case("sql-substitution", receipt=_rejected_receipt(exit_code=1, verdict="UNVERIFIABLE", reasons=("diag_missing",), diag=False), consume={"decision": "REFUSED"}))
    assert a["status"] == "NOT_REACHED" and any("diag" in f or "exit" in f for f in a["failed"])
    # the graph leg never reached the computation: refused, but nothing was substituted
    a = CH.accept(_case("sql-substitution", retrieval={"status": "ERROR"}, bind={"status": "NOT_BOUND"}, receipt={"invoked": False}, consume={"decision": "REFUSED"}))
    assert a["status"] == "NOT_REACHED"
    # wrong reason code: it was rejected, but not for the substitution
    a = CH.accept(_case("sql-substitution", receipt=_rejected_receipt(reasons=("owner_mismatch",)), consume={"decision": "REFUSED"}))
    assert a["status"] == "WRONG" and any("sql_mismatch" in f for f in a["failed"])
    # released a number on a substitution: wrong, never "not reached"
    a = CH.accept(_case("sql-substitution", consume={"decision": "RELEASED"}))
    assert a["status"] == "WRONG"


def test_accept_declaration_mismatch_needs_the_alternate_computation_to_be_reached():
    ok = _case("declaration-mismatch", bind=_mismatch_bind(), receipt={"invoked": False}, consume={"decision": "REFUSED"})
    assert CH.accept(ok)["status"] == "MET"
    a = CH.accept(_case("declaration-mismatch", retrieval={"status": "OK", "reached": False}, declaration=None, bind={"status": "NOT_BOUND"},
                        receipt={"invoked": False}, consume={"decision": "REFUSED"}))
    assert a["status"] == "NOT_REACHED"
    a = CH.accept(_case("declaration-mismatch", bind=_mismatch_bind(failed=("path",)), receipt={"invoked": False}, consume={"decision": "REFUSED"}))
    assert a["status"] == "WRONG" and any("file_sha256" in f for f in a["failed"])
    a = CH.accept(_case("declaration-mismatch", bind=_mismatch_bind(), receipt={"invoked": True, "exit_code": 2}, consume={"decision": "REFUSED"}))
    assert a["status"] == "WRONG" and any("invoked" in f for f in a["failed"])


def test_chain_is_incomplete_when_the_negative_graph_leg_errors(clients, projection, sdk_root, tmp_path, monkeypatch):
    real = CH.governed

    def flaky(query, *a, **k):
        if query == CH.MISMATCH_SEED:
            raise RuntimeError("simulated retrieval outage on the negative leg")
        return real(query, *a, **k)

    monkeypatch.setattr(CH, "governed", flaky)
    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), clients=clients, projection=projection,
                       requester="t", as_of=AS_OF)
    cases = {c["case"]: c for c in out["cases"]}
    assert cases["approved"]["acceptance"]["status"] == "MET" and cases["approved"]["consume"]["decision"] == "RELEASED"
    assert cases["declaration-mismatch"]["consume"]["decision"] == "REFUSED"          # still fail-closed ...
    assert cases["declaration-mismatch"]["acceptance"]["status"] == "NOT_REACHED"      # ... but it never ran
    assert out["verdict"] == "CHAIN_INCOMPLETE" and out["broken_at"] == "declaration-mismatch"


def test_chain_is_incomplete_when_the_substitution_child_dies(clients, projection, sdk_root, tmp_path):
    def runner(argv, **kw):
        if "sql-substitution" in argv:
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="Traceback: simulated crash before any diagnostic")
        return subprocess.run(argv, **kw)

    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), clients=clients, projection=projection,
                       requester="t", as_of=AS_OF, runner=runner)
    cases = {c["case"]: c for c in out["cases"]}
    assert cases["sql-substitution"]["consume"]["decision"] == "REFUSED"
    assert cases["sql-substitution"]["acceptance"]["status"] == "NOT_REACHED"
    assert out["verdict"] == "CHAIN_INCOMPLETE" and out["broken_at"] == "sql-substitution"


def test_chain_is_broken_when_a_negative_is_released(clients, projection, sdk_root, tmp_path):
    def runner(argv, **kw):   # a nonconforming child that "passes" the substitution: the approved diag is served for both
        argv = [("approved" if x == "sql-substitution" else x) for x in argv]
        r = subprocess.run(argv, **kw)
        out_dir = Path(argv[argv.index("--evidence-dir") + 1])
        (out_dir / "case_sql-substitution_hermetic.json").write_bytes((out_dir / "case_approved_hermetic.json").read_bytes())
        return r

    from pathlib import Path
    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), clients=clients, projection=projection,
                       requester="t", as_of=AS_OF, runner=runner)
    cases = {c["case"]: c for c in out["cases"]}
    assert cases["sql-substitution"]["acceptance"]["status"] == "WRONG" and out["verdict"] == "CHAIN_BROKEN"


# ---- Astra P2 #2: provenance pins gate execution
def test_provenance_gate_blocks_execution_on_sdk_head_mismatch(clients, projection, sdk_root, tmp_path, monkeypatch):
    real = CH.sdk_publication
    monkeypatch.setattr(CH, "sdk_publication", lambda root: dict(real(root), sdk_head="0" * 40, sdk_head_matches_pin=False))
    calls = []
    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), clients=clients, projection=projection,
                       requester="t", as_of=AS_OF, runner=lambda argv, **k: calls.append(argv))
    assert out["verdict"] == "CHAIN_BROKEN" and out["broken_at"] == "provenance" and out["cases"] == [] and calls == []
    assert out["provenance"]["sdk_head_pin"] is False


def test_provenance_gate_treats_unknown_git_state_as_not_clean(clients, projection, sdk_root, tmp_path, monkeypatch):
    real = CH.sdk_publication
    monkeypatch.setattr(CH, "sdk_publication", lambda root: dict(real(root), sdk_repo_dirty=None))
    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), clients=clients, projection=projection,
                       requester="t", as_of=AS_OF, runner=lambda argv, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    assert out["verdict"] == "CHAIN_BROKEN" and out["broken_at"] == "provenance" and out["provenance"]["sdk_clean"] is False


def test_provenance_gate_blocks_on_publication_pin_mismatch(clients, projection, sdk_root, tmp_path):
    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), clients=clients,
                       projection=dict(projection, publication_id="pub_0000000000000000"), requester="t", as_of=AS_OF,
                       runner=lambda argv, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    assert out["verdict"] == "CHAIN_BROKEN" and out["broken_at"] == "provenance" and out["provenance"]["publication_pin"] is False


def test_sdk_publication_checks_the_whole_repo_for_dirt(sdk_root):
    pub = CH.sdk_publication(sdk_root)
    assert pub["sdk_repo_dirty"] in (True, False) and "sdk_dirty" in pub


# ---- Astra P2 #3: a stale diagnostic is never attributed to the current launch
def test_run_receipt_ignores_a_stale_diagnostic(tmp_path):
    stale = tmp_path / "case_approved_hermetic.json"
    stale.write_text(json.dumps({"issue_out": {"receipt": {"verdict": "VERIFIED", "job": {"job_id": "stalejob_zz9"}}}, "output": {"verdict": "VERIFIED"}, "released": True}))

    def runner(argv, **kw):
        raise OSError("simulated launch failure")

    rec = CH.run_receipt("approved", str(tmp_path / "sdk"), str(tmp_path), live=False, runner=runner)
    assert rec["exit_code"] == -1 and rec["diag"] is None and rec["diag_present"] is False
    assert rec["receipt"]["verdict"] == "UNVERIFIABLE" and "stalejob_zz9" not in json.dumps(rec)
    assert rec["diag_path"] is None and not Path(rec["invocation_dir"]).exists()


def test_run_receipt_rejects_a_diagnostic_older_than_the_launch(tmp_path):
    import os as _os
    stale = tmp_path / "case_approved_hermetic.json"

    def runner(argv, **kw):   # writes into the private dir but back-dates it: not this launch's artifact
        priv = Path(argv[argv.index("--evidence-dir") + 1]) / "case_approved_hermetic.json"
        priv.write_text(json.dumps({"issue_out": {"receipt": {"verdict": "VERIFIED"}}, "output": {"verdict": "VERIFIED"}, "released": True}))
        _os.utime(priv, (1, 1))
        return subprocess.CompletedProcess(argv, 0, stdout="x VERIFIED", stderr="")

    rec = CH.run_receipt("approved", str(tmp_path / "sdk"), str(tmp_path), live=False, runner=runner)
    assert rec["diag_present"] is False and rec["receipt"]["verdict"] == "UNVERIFIABLE" and rec["receipt"]["reason"] == "diag_stale"


# ---- Astra P2 #4: identity proof requires known identities over the whole job set
class _Job:
    def __init__(self, email):
        self.user_email = email


class _Client:
    def __init__(self, emails):
        self.emails, self.asked = emails, []

    def get_job(self, jid, project=None, location=None):
        self.asked.append(jid)
        return _Job(self.emails.get(jid, "missing"))


def test_same_requester_unknown_when_identity_missing():
    c = _Client({"g1": None, "g2": "", "r1": None})
    r = CH.same_requester(c, ["g1", "g2"], [{"job_id": "r1"}])
    assert r["status"] == "UNKNOWN" and "identity" in r["reason"]


def test_same_requester_unknown_when_nothing_to_compare():
    assert CH.same_requester(_Client({}), [], [{"job_id": "r1"}])["status"] == "UNKNOWN"
    assert CH.same_requester(_Client({}), ["g1"], [])["status"] == "UNKNOWN"


def test_same_requester_covers_every_job_and_detects_a_different_one():
    ids = [f"g{i}" for i in range(12)]
    c = _Client({**{i: "op@x" for i in ids}, "r1": "op@x", "r2": "op@x"})
    r = CH.same_requester(c, ids, [{"job_id": "r1"}, {"job_id": "r2"}])
    assert r["status"] == "SAME" and set(c.asked) == set(ids) | {"r1", "r2"} and r["jobs_compared"] == 14
    c = _Client({**{i: "op@x" for i in ids}, "r1": "op@x", "r2": "sa@x"})
    assert CH.same_requester(c, ids, [{"job_id": "r1"}, {"job_id": "r2"}])["status"] == "DIFFERENT"


def test_job_ids_of_collects_retrieval_declaration_and_receipt_jobs():
    cases = [{"case": "approved", "retrieval": {"timing": {"jobs": [{"job_id": "w"}, {"job_id": "n"}]}}, "declaration": {"job_id": "d1"},
              "receipt": {"invoked": True, "receipt": {"job": {"job_id": "r1"}}}},
             {"case": "sql-substitution", "retrieval": {"timing": {"jobs": [{"job_id": "w2"}]}}, "declaration": {"job_id": "d2"},
              "receipt": {"invoked": True, "receipt": {"job": {"job_id": "r2"}}}},
             {"case": "declaration-mismatch", "retrieval": {"timing": {"jobs": [{"job_id": "w3"}]}}, "declaration": {"job_id": "d3"},
              "receipt": {"invoked": False}}]
    ids = CH.job_ids_of(cases)
    assert ids["graph"] == ["w", "n", "d1", "w2", "d2", "w3", "d3"] and [j["job_id"] for j in ids["receipt"]] == ["r1", "r2"]


# ---- Astra P2 #5: live + oracle is not a mode
def test_live_with_oracle_engine_is_rejected(sdk_root, tmp_path):
    with pytest.raises(ValueError):
        CH.run_chain(engine="oracle", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), clients={"engine": "oracle"}, projection={"publication_id": "p", "nodes": []})
    with pytest.raises(SystemExit):
        CH.main(["--live", "--engine", "oracle", "--out", str(tmp_path)])


# ---- residual P2s @ a615a7c
def test_chain_is_incomplete_when_the_approved_child_dies(clients, projection, sdk_root, tmp_path):
    stale = tmp_path / "receipt" / "case_approved_hermetic.json"          # a foreign file in the shared dir: neither referenced nor touched
    stale.parent.mkdir(parents=True); stale.write_text("{}")

    def runner(argv, **kw):
        if "approved" in argv:
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="Traceback: simulated crash before any diagnostic")
        return subprocess.run(argv, **kw)

    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), clients=clients, projection=projection,
                       requester="t", as_of=AS_OF, runner=runner)
    cases = {c["case"]: c for c in out["cases"]}
    assert cases["approved"]["consume"]["decision"] == "REFUSED"
    assert cases["approved"]["acceptance"]["status"] == "NOT_REACHED"
    assert cases["sql-substitution"]["acceptance"]["status"] == "MET" and cases["declaration-mismatch"]["acceptance"]["status"] == "MET"
    assert out["verdict"] == "CHAIN_INCOMPLETE" and out["broken_at"] == "approved"
    assert stale.exists() and stale.read_text() == "{}" and cases["approved"]["receipt"]["diag_path"] is None


def test_chain_is_incomplete_when_only_the_approved_graph_leg_errors(clients, projection, sdk_root, tmp_path, monkeypatch):
    real = CH.governed
    calls = {"n": 0}

    def flaky(query, *a, **k):
        calls["n"] += 1
        if query == CH.SEED and calls["n"] == 1:      # first approved retrieval only
            raise RuntimeError("simulated retrieval outage on the approved leg")
        return real(query, *a, **k)

    monkeypatch.setattr(CH, "governed", flaky)
    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), clients=clients, projection=projection,
                       requester="t", as_of=AS_OF)
    assert out["acceptance"] == {"approved": "NOT_REACHED", "sql-substitution": "MET", "declaration-mismatch": "MET"}
    assert out["verdict"] == "CHAIN_INCOMPLETE" and out["broken_at"] == "approved"


def test_overlapping_receipt_invocations_cannot_exchange_diagnostics(sdk_root, tmp_path):
    """Astra: A clears the shared path, B writes its diagnostic, A fails afterwards -> A must not adopt B's file."""
    from pathlib import Path
    b_result = {}

    def runner_a(argv, **kw):
        b_result["rec"] = CH.run_receipt("approved", sdk_root, str(tmp_path), live=False)   # B runs to completion inside A's launch window
        raise FileNotFoundError("simulated launch failure of A after B completed")

    a = CH.run_receipt("approved", sdk_root, str(tmp_path), live=False, runner=runner_a)
    b = b_result["rec"]
    assert b["diag_present"] and b["receipt"]["verdict"] == "VERIFIED"
    assert a["exit_code"] == -1 and a["diag_present"] is False and a["receipt"]["verdict"] == "UNVERIFIABLE"
    assert b["receipt"]["request_id"] not in json.dumps(a)
    assert a["invocation_dir"] != b["invocation_dir"]
    assert Path(b["diag_path"]).exists() and json.loads(Path(b["diag_path"]).read_text())["request_id"] == b["receipt"]["request_id"]
    assert not Path(a["invocation_dir"]).exists() and not Path(b["invocation_dir"]).exists()   # private dirs do not linger


def test_receipt_diag_is_read_from_the_private_dir_and_retained_under_out_dir(sdk_root, tmp_path):
    rec = CH.run_receipt("sql-substitution", sdk_root, str(tmp_path), live=False)
    assert rec["argv"][rec["argv"].index("--evidence-dir") + 1] == rec["invocation_dir"]
    assert rec["invocation_dir"].startswith(str(tmp_path.resolve())) and rec["diag_path"] == str(tmp_path.resolve() / "case_sql-substitution_hermetic.json")
    assert rec["diag_present"] and rec["output"]["reason_codes"] == ["sql_mismatch"]


class _PointerJob:
    job_id = "pointer-job-1"

    def result(self):
        return [{"publication_id": CH.PUBLICATION_PIN}]


class _PointerClient:
    def query(self, q, job_config=None, location=None):
        assert "active_publication" in q
        return _PointerJob()


def test_pointer_lookup_records_its_job_id():
    pub, job_id = CH.resolve_pointer_job(_PointerClient())
    assert pub == CH.PUBLICATION_PIN and job_id == "pointer-job-1"


def test_job_ids_of_includes_the_pointer_job():
    ids = CH.job_ids_of([{"case": "approved", "retrieval": {"timing": {"jobs": [{"job_id": "w"}]}}, "receipt": {"invoked": False}}],
                        pointer_job_id="pointer-job-1")
    assert ids["graph"] == ["pointer-job-1", "w"]


def test_live_without_a_bq_client_still_writes_a_verdict(sdk_root, tmp_path):
    out = CH.run_chain(engine="fallback", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), clients={"engine": "fallback"},
                       requester="t", as_of=AS_OF, runner=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    assert out["verdict"] == "CHAIN_BROKEN" and out["broken_at"] == "publication" and (tmp_path / "chain_live.json").exists()


# ---- Astra re-review 2: two SUCCESSFUL overlapping chains must keep their own retained evidence
def _reconcile(out: dict) -> None:
    """Every retained diagnostic a chain record references lives in that run's own directory and carries the request id
    the record claims."""
    for c in out["cases"]:
        rec = c["receipt"]
        if not rec.get("invoked"):
            continue
        dp = Path(rec["diag_path"])
        assert dp.parent.name == out["run_id"], (dp, out["run_id"])
        d = json.loads(dp.read_text())
        assert d["request_id"] == rec["request_id"] == rec["receipt"]["request_id"]
        assert CH.sha256_hex(dp.read_bytes()) == rec["diag_sha256"]


def test_two_successful_overlapping_chains_keep_their_own_evidence(clients, projection, sdk_root, tmp_path):
    inner = {}

    def runner_a(argv, **kw):
        if "sql-substitution" in argv and "rec" not in inner:     # A paused at its substitution launch: B runs to completion
            inner["rec"] = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), clients=clients,
                                        projection=projection, requester="t", as_of=AS_OF)
        return subprocess.run(argv, **kw)

    a = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), clients=clients, projection=projection,
                     requester="t", as_of=AS_OF, runner=runner_a)
    b = inner["rec"]
    assert a["verdict"] == b["verdict"] == "CHAIN_CONNECTED" and a["run_id"] != b["run_id"]
    _reconcile(a); _reconcile(b)
    ids_a = {c["receipt"]["request_id"] for c in a["cases"] if c["receipt"].get("invoked")}
    ids_b = {c["receipt"]["request_id"] for c in b["cases"] if c["receipt"].get("invoked")}
    assert ids_a and ids_b and not (ids_a & ids_b)
    final = json.loads((tmp_path / "chain_hermetic.json").read_text())       # last writer: A, and it references only A's files
    assert final["run_id"] == a["run_id"]
    _reconcile(final)
    assert not list((tmp_path / "receipt").glob(".inv_*")) and not list((tmp_path / "receipt" / a["run_id"]).glob(".inv_*"))


def test_chain_record_is_also_retained_inside_its_run_dir(clients, projection, sdk_root, tmp_path):
    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), clients=clients, projection=projection,
                       requester="t", as_of=AS_OF)
    own = tmp_path / "receipt" / out["run_id"] / "chain_hermetic.json"
    assert own.exists() and json.loads(own.read_text())["run_id"] == out["run_id"]
    assert json.loads((tmp_path / "chain_hermetic.json").read_text()) == json.loads(own.read_text())


# =============================================================================== Catalog-seeded mode (2026-09-06, plan U3)
import okf_bq_graph.catalog as C
from okf_bq_graph.journal import Journal
from okf_bq_graph.publication import ProjectionStore
from okf_bq_graph.seed import ConceptSeed

CCFG = C.CatalogConfig()


def _pin_entry(projection, **overrides):
    base = dict(publication_id=projection["publication_id"], source_manifest_sha256=projection["source_manifest_sha256"],
                concept_id=f"acme_retail|{projection['publication_id']}|Concept|metrics/gross-margin",
                concept_file_sha256=next(m["sha256"] for m in projection["source_manifest"] if m["path"] == "metrics/gross-margin.md"))
    return C.sample_entry(**dict(base, **overrides))


def _reader(projection, **overrides):
    return C.MockReader(C.mock_pages([f"{CCFG.group}/entries/other/{i}" for i in range(6)] + [CCFG.entry], 4), {CCFG.entry: _pin_entry(projection, **overrides)})


@pytest.fixture
def p2(sample_root, tmp_path_factory):
    import shutil
    root = tmp_path_factory.mktemp("p2_chain") / "acme_retail"
    shutil.copytree(sample_root, root)
    policy = root / "policies" / "revenue-recognition.md"
    policy.write_text(policy.read_text(encoding="utf-8") + "\n\n# Revision note\n\nFY2027 review scheduled.\n", encoding="utf-8")
    return compile_bundle(str(root), "acme_retail", SOURCE_PIN + "+local.fedcba9876543210")


def _store(projection, head=None, p2=None):
    s = ProjectionStore(journal=None)
    s.add(projection)
    if p2 is not None:
        s.add(p2)
    s.set_head("acme_retail", head or projection["publication_id"])
    return s


def _run_catalog(projection, sdk_root, tmp_path, sample_root, reader=None, store=None, live=False, engine="oracle", **kw):
    return CH.run_chain(engine=engine, live=live, sdk_root=sdk_root, out_dir=str(tmp_path), requester=kw.pop("requester", "t"), as_of=AS_OF,
                        seed_mode="catalog", catalog_reader=reader if reader is not None else _reader(projection),
                        store=store if store is not None else _store(projection), acme_root=sample_root, **kw)


def test_catalog_mock_chain_end_to_end(projection, sdk_root, tmp_path, sample_root):
    out = _run_catalog(projection, sdk_root, tmp_path, sample_root)
    assert out["chain"] == CH.CHAIN_VERSION and out["seed"]["mode"] == "catalog-mock" and out["seed"]["status"] == "OK"
    assert "not a live Catalog read" in out["seed"]["note"]
    assert out["publication"]["status"] == "OK" and out["publication"]["head"]["matches_pin"] is True
    assert out["source"]["status"] == "OK" and out["provenance"]["ok"] and out["provenance"]["source_verified"]
    assert out["source_pin"] == out["seed"]["pin"]["source_pin"] == SOURCE_PIN
    cases = {c["case"]: c for c in out["cases"]}
    for name, c in cases.items():
        assert c["payload"]["status"] == "CONSISTENT", (name, c["payload"].get("failed"))
        assert c["retrieval"]["seed"].startswith("concept:acme_retail|") and "forced:" not in c["retrieval"]["seed"]
    assert cases["approved"]["retrieval"]["seed_origin"] == "catalog-mock" and cases["approved"]["consume"]["decision"] == "RELEASED"
    assert cases["sql-substitution"]["consume"]["decision"] == "REFUSED" and "sql_mismatch" in cases["sql-substitution"]["receipt"]["output"]["reason_codes"]
    dm = cases["declaration-mismatch"]
    assert dm["retrieval"]["seed_origin"] == "injected-fixture-seed" and "not a Catalog discovery" in dm["attack"]
    assert dm["bind"]["status"] == "MISMATCH" and dm["receipt"]["invoked"] is False and dm["consume"]["decision"] == "REFUSED"
    assert out["acceptance"] == {"approved": "MET", "sql-substitution": "MET", "declaration-mismatch": "MET"}
    assert out["verdict"] == "CHAIN_CONNECTED"
    # separate graph / SDK publication identities; the bind uses the validated pin, not the module constant
    assert out["graph_publication"]["publication_id"] == projection["publication_id"] != out["sdk_publication"]["publication_id"]
    assert out["graph_publication"]["source_manifest_sha256"] == projection["source_manifest_sha256"]
    sp = cases["approved"]["bind"]["checks"]["source_pin"]
    assert sp["ok"] and sp["graph"] == out["seed"]["pin"]["source_pin"] and sp["sdk"].endswith("@ " + SOURCE_PIN) and "not a Git attestation" in sp["note"]
    # run-owned evidence under the catalog namespace: raw Catalog responses, journal, receipt diagnostics, final record
    run_dir = Path(out["run_dir"])
    assert run_dir == tmp_path / out["run_id"] and (run_dir / "journal.jsonl").exists() and (run_dir / "chain_hermetic.json").exists()
    assert {p.name for p in (run_dir / "catalog").iterdir()} == {"catalog_list_0.json", "catalog_list_1.json", "catalog_entry.json"}
    assert Path(cases["approved"]["receipt"]["diag_path"]).parent == run_dir / "receipt"
    roles = [j["role"] for j in out["journal"]["jobs"]]
    assert roles[:3] == ["pin_resolution", "seed_visibility", "observed_head"]
    assert roles.count("payload_rows") == 3 and roles.count("chain_declaration") == 3 and out["journal"]["summary"]["unresolved"] == 0
    assert out["job_inventory"]["journal"]["actual_jobs"] == 0          # hermetic store: no BigQuery job identities to claim
    written = json.loads((tmp_path / "chain_hermetic.json").read_text())
    assert written["run_id"] == out["run_id"] and "writer@example.test" not in json.dumps(written)   # aspect principal redacted


def test_catalog_p1_is_served_while_head_is_p2(projection, p2, sdk_root, tmp_path, sample_root):
    out = _run_catalog(projection, sdk_root, tmp_path, sample_root, store=_store(projection, head=p2["publication_id"], p2=p2))
    assert out["verdict"] == "CHAIN_CONNECTED" and out["publication"]["head"]["publication_id"] == p2["publication_id"]
    assert out["publication"]["head"]["matches_pin"] is False and out["publication"]["publication_id"] == projection["publication_id"]
    for c in out["cases"]:
        assert c["retrieval"]["scope"]["publication_id"] == projection["publication_id"]
        assert c["payload"]["status"] == "CONSISTENT"


@pytest.mark.parametrize("mutate, reasons", [
    (lambda s, p: s.set_status(p["publication_id"], "WITHDRAWN"), ["PUBLICATION_NOT_READY:WITHDRAWN"]),
    (lambda s, p: s.remove(p["publication_id"]), ["PUBLICATION_MISSING", "SEED_MISSING"]),
])
def test_catalog_stale_pin_never_becomes_head_or_fixture(projection, p2, sdk_root, tmp_path, sample_root, mutate, reasons):
    calls = []
    store = _store(projection, head=p2["publication_id"], p2=p2)
    mutate(store, projection)
    out = _run_catalog(projection, sdk_root, tmp_path, sample_root, store=store, runner=lambda argv, **k: calls.append(argv))
    assert out["verdict"] == "CHAIN_BROKEN" and out["broken_at"] == "publication" and out["cases"] == [] and calls == []
    assert out["publication"]["status"] == "FAIL_STALE" and out["publication"]["reasons"] == reasons
    assert out["publication"]["head"]["publication_id"] == p2["publication_id"]       # observed, not served
    assert out["publication"]["publication_id"] == projection["publication_id"]
    assert (Path(out["run_dir"]) / "chain_hermetic.json").exists()                     # early refusal keeps its final record
    states = [j["state"] for j in out["journal"]["jobs"]]
    assert states and all(j["terminal"] for j in out["journal"]["jobs"]) and ("EMPTY" in states or "DONE" in states)


@pytest.mark.parametrize("override, status", [
    ({"concept_id": "acme_retail|pub_0000000000000000|Concept|metrics/gross-margin"}, "INVALID_PIN"),
    ({"runtime_dataset": "somewhere_else"}, "SCOPE_REFUSED"),
    ({"runtime_contract": "graph-spike-v9"}, "UNSUPPORTED_CONTRACT"),
])
def test_catalog_invalid_pin_refuses_before_any_store_read_or_sdk_call(projection, sdk_root, tmp_path, sample_root, override, status):
    calls = []
    store = _store(projection)
    out = _run_catalog(projection, sdk_root, tmp_path, sample_root, reader=_reader(projection, **override), store=store,
                       runner=lambda argv, **k: calls.append(argv))
    assert out["verdict"] == "CHAIN_BROKEN" and out["broken_at"] == "seed" and out["cases"] == [] and calls == []
    assert out["seed"]["status"] == status and out["seed"]["mode"] == "catalog-mock" and "publication" not in out
    assert out["journal"]["jobs"] == []                                   # no store read happened
    assert {r["name"] for r in out["journal"]["retained"]} >= {"catalog_entry"}
    assert (Path(out["run_dir"]) / "chain_hermetic.json").exists()


def test_catalog_read_failure_is_blocked_not_a_pass(projection, sdk_root, tmp_path, sample_root):
    rd = C.MockReader([(403, {"error": {"code": 403, "message": "denied"}})], {})
    out = _run_catalog(projection, sdk_root, tmp_path, sample_root, reader=rd, runner=lambda argv, **k: (_ for _ in ()).throw(AssertionError("no")))
    assert out["verdict"] == "CHAIN_BROKEN" and out["broken_at"] == "seed" and out["seed"]["status"] == "CATALOG_ERROR" and out["seed"]["http_status"] == 403


def test_catalog_reader_mode_gates(projection, sdk_root, tmp_path, sample_root):
    class Sess:
        def request(self, *a, **k):
            raise AssertionError("hermetic mode must never send")
    out = _run_catalog(projection, sdk_root, tmp_path, sample_root, reader=C.HttpReader(session=Sess()))
    assert out["verdict"] == "CHAIN_BROKEN" and out["broken_at"] == "seed" and out["seed"]["status"] == "READER_REFUSED"
    out = CH.run_chain(engine="fallback", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), clients={"engine": "fallback", "bq": object()},
                       requester="t", as_of=AS_OF, seed_mode="catalog", catalog_reader=_reader(projection),
                       runner=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    assert out["verdict"] == "CHAIN_BROKEN" and out["broken_at"] == "seed" and out["seed"]["status"] == "READER_REFUSED"
    assert "mock" in out["seed"]["reason"]
    with pytest.raises(ValueError):
        CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), seed_mode="catalog")
    with pytest.raises(ValueError):
        CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), seed_mode="vector")


def test_catalog_hermetic_without_a_store_is_refused(projection, sdk_root, tmp_path, sample_root):
    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), requester="t", as_of=AS_OF,
                       seed_mode="catalog", catalog_reader=_reader(projection), acme_root=sample_root)
    assert out["verdict"] == "CHAIN_BROKEN" and out["broken_at"] == "publication" and out["publication"]["status"] == "ERROR"


def test_catalog_source_unverified_refuses_before_cases(projection, sdk_root, tmp_path, sample_root, monkeypatch):
    import okf_bq_graph.publication as PUB
    monkeypatch.setattr(PUB, "_git", lambda root, *a: None)
    calls = []
    out = _run_catalog(projection, sdk_root, tmp_path, sample_root, runner=lambda argv, **k: calls.append(argv))
    assert out["verdict"] == "CHAIN_BROKEN" and out["broken_at"] == "source" and out["source"]["status"] == "SOURCE_UNVERIFIED" and calls == []


def test_catalog_mixed_payload_is_refused_before_the_sdk(projection, sdk_root, tmp_path, sample_root, monkeypatch):
    real = CH.governed
    calls = []

    def tampered(seed, *a, **k):
        r = real(seed, *a, **k)
        if isinstance(seed, ConceptSeed) and seed.origin == "catalog-mock" and r["status"] == "OK":
            for c in r["computations"]:          # SQL changed under unchanged P1 labels and digest
                c["sql"] = c["sql"].replace("payment_fee", "0 * payment_fee")
        return r

    monkeypatch.setattr(CH, "governed", tampered)
    out = _run_catalog(projection, sdk_root, tmp_path, sample_root, runner=lambda argv, **k: calls.append(argv))
    cases = {c["case"]: c for c in out["cases"]}
    assert calls == []                                                        # no SDK execution on an inconsistent payload
    for name in ("approved", "sql-substitution"):
        c = cases[name]
        assert c["payload"]["status"] == "INCONSISTENT" and "computations" in c["payload"]["failed"]
        assert c["bind"]["status"] == "NOT_BOUND" and c["receipt"]["invoked"] is False and c["consume"]["decision"] == "REFUSED"
        assert c["acceptance"]["status"] == "WRONG" and any("payload INCONSISTENT" in f for f in c["acceptance"]["failed"])
    assert cases["declaration-mismatch"]["payload"]["status"] == "CONSISTENT"      # the injected seed was not tampered
    assert out["verdict"] == "CHAIN_BROKEN" and out["broken_at"] == "approved"


def test_catalog_engine_label_and_shape_substitution_is_refused(projection, sdk_root, tmp_path, sample_root, monkeypatch):
    """Astra re-review 3 R1 (`chain_engine_shape_substitution`): the real oracle runs, the returned provenance is replaced
    by a VALID trusted fallback-shaped list and only the returned engine label is changed to `fallback`. The guard takes
    the shape from the configured engine and requires the label to match it: refused before the SDK."""
    from okf_bq_graph.model import PROVENANCE_NOTE
    real = CH.governed
    calls = []
    tn = {n["node_id"]: n for n in projection["nodes"]}

    def relabel(seed, *a, **k):
        r = real(seed, *a, **k)
        if r["status"] == "OK":
            for c in r["concepts"]:
                fb = []
                for e in projection["edges"]:
                    if e["src_id"] == c["concept_id"] and e["relation"] == "DERIVES_FROM":
                        src = tn[e["dst_id"]]
                        fb.append({"resource": src["resource"], "title": src["title"], "declaration": e["declaration"], "resolution": e["resolution"],
                                   "source_id": src["node_id"], "note": PROVENANCE_NOTE})
                c["provenance"] = fb                        # valid fallback shape, every value trusted; oracle fields omitted
            r["scope"]["engine"] = "fallback"
        return r

    monkeypatch.setattr(CH, "governed", relabel)
    out = _run_catalog(projection, sdk_root, tmp_path, sample_root, runner=lambda argv, **k: calls.append(argv))
    assert calls == [] and out["engine"] == "oracle" and out["verdict"] == "CHAIN_BROKEN"
    for c in out["cases"]:
        assert c["payload"]["status"] == "INCONSISTENT" and {"engine", "governance"} <= set(c["payload"]["failed"])
        assert c["payload"]["checks"]["engine"] == {"ok": False, "trusted": "oracle", "returned": "fallback", "basis": "configured engine supplied by the caller"}
        assert c["payload"]["checks"]["governance"]["engine"] == "oracle" and c["payload"]["checks"]["governance"]["engine_source"].startswith("trusted")
        assert c["bind"]["status"] == "NOT_BOUND" and c["receipt"]["invoked"] is False and c["acceptance"]["status"] == "WRONG"
    # control: the untouched oracle run records the trusted engine and passes
    monkeypatch.setattr(CH, "governed", real)
    ok = _run_catalog(projection, sdk_root, tmp_path, sample_root)
    assert ok["verdict"] == "CHAIN_CONNECTED" and all(c["payload"]["checks"]["engine"]["ok"] and c["payload"]["checks"]["governance"]["engine"] == "oracle" for c in ok["cases"])


def test_catalog_declaration_changed_after_preflight_is_refused(projection, sdk_root, tmp_path, sample_root, monkeypatch):
    real = CH.declaration
    monkeypatch.setattr(CH, "declaration", lambda clients, cid, pub: dict(real(clients, cid, pub), file_sha256="a" * 64))
    calls = []
    out = _run_catalog(projection, sdk_root, tmp_path, sample_root, runner=lambda argv, **k: calls.append(argv))
    assert calls == [] and out["verdict"] == "CHAIN_BROKEN"
    assert all(c["payload"]["status"] == "INCONSISTENT" and "declaration" in c["payload"]["failed"] for c in out["cases"])


def test_catalog_payload_guard_cannot_be_bypassed_by_labels(projection, sdk_root, tmp_path, sample_root, monkeypatch):
    """If the guard were skipped, the tampered approved leg would bind and execute: prove the run only connects with it."""
    import okf_bq_graph.publication as PUB
    real_verify = CH.verify_payload
    monkeypatch.setattr(CH, "verify_payload", lambda *a, **k: dict(real_verify(*a, **k), status="CONSISTENT", failed=[]))
    real = CH.governed
    monkeypatch.setattr(CH, "governed", lambda seed, *a, **k: (lambda r: ([c.__setitem__("sql", c["sql"] + "\n-- x") for c in r.get("computations", [])], r)[1])(real(seed, *a, **k)))
    out = _run_catalog(projection, sdk_root, tmp_path, sample_root)
    assert {c["case"]: c["bind"]["status"] for c in out["cases"]}["approved"] == "MISMATCH"    # the SDK bind still catches SQL bytes ...
    assert out["verdict"] == "CHAIN_BROKEN"
    # ... but a non-computation corruption is caught only by the guard
    monkeypatch.setattr(CH, "governed", real)
    store = _store(projection)
    sec = next(n for n in store.nodes[projection["publication_id"]] if n["kind"] == "Section" and n["local_id"].startswith("policies/margin-standard#"))
    store.tamper_node(projection["publication_id"], sec["node_id"], text="corrupted")
    bypassed = _run_catalog(projection, sdk_root, tmp_path, sample_root, store=store)
    assert bypassed["verdict"] == "CHAIN_CONNECTED"                                   # guard bypassed: corruption released
    monkeypatch.setattr(CH, "verify_payload", real_verify)
    guarded = _run_catalog(projection, sdk_root, tmp_path, sample_root, store=_store(projection))
    assert guarded["verdict"] == "CHAIN_CONNECTED"
    store2 = _store(projection); store2.tamper_node(projection["publication_id"], sec["node_id"], text="corrupted")
    guarded_bad = _run_catalog(projection, sdk_root, tmp_path, sample_root, store=store2)
    assert guarded_bad["verdict"] == "CHAIN_BROKEN" and all(c["payload"]["status"] == "INCONSISTENT" for c in guarded_bad["cases"])
    assert all("section_text_hashes" in c["payload"]["failed"] for c in guarded_bad["cases"])


def test_catalog_outage_on_approved_is_not_reached(projection, sdk_root, tmp_path, sample_root):
    def runner(argv, **kw):
        if "approved" in argv:
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="Traceback: simulated crash")
        return subprocess.run(argv, **kw)
    out = _run_catalog(projection, sdk_root, tmp_path, sample_root, runner=runner)
    assert out["acceptance"] == {"approved": "NOT_REACHED", "sql-substitution": "MET", "declaration-mismatch": "MET"}
    assert out["verdict"] == "CHAIN_INCOMPLETE" and out["broken_at"] == "approved"


def test_catalog_unknown_store_read_is_blocked(projection, sdk_root, tmp_path, sample_root):
    store = _store(projection)
    store.rows = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("simulated outage on payload rows"))
    out = _run_catalog(projection, sdk_root, tmp_path, sample_root, store=store, runner=lambda argv, **k: (_ for _ in ()).throw(AssertionError("no")))
    assert all(c["payload"]["status"] == "ERROR" and c["acceptance"]["status"] == "NOT_REACHED" for c in out["cases"])
    assert out["verdict"] == "CHAIN_INCOMPLETE"


def test_catalog_two_overlapping_runs_and_an_early_refusal_keep_their_own_evidence(projection, sdk_root, tmp_path, sample_root):
    inner = {}

    def runner_a(argv, **kw):
        if "sql-substitution" in argv and "rec" not in inner:
            inner["rec"] = _run_catalog(projection, sdk_root, tmp_path, sample_root)
            inner["refused"] = _run_catalog(projection, sdk_root, tmp_path, sample_root, reader=_reader(projection, runtime_contract="nope"))
        return subprocess.run(argv, **kw)

    a = _run_catalog(projection, sdk_root, tmp_path, sample_root, runner=runner_a)
    b, r = inner["rec"], inner["refused"]
    assert a["verdict"] == b["verdict"] == "CHAIN_CONNECTED" and r["verdict"] == "CHAIN_BROKEN"
    assert len({a["run_id"], b["run_id"], r["run_id"]}) == 3
    for out in (a, b):
        for c in out["cases"]:
            rec = c["receipt"]
            if rec.get("invoked"):
                dp = Path(rec["diag_path"])
                assert dp.parent == Path(out["run_dir"]) / "receipt"
                assert json.loads(dp.read_text())["request_id"] == rec["request_id"] == rec["receipt"]["request_id"]
                assert CH.sha256_hex(dp.read_bytes()) == rec["diag_sha256"]
        for kept in out["journal"]["retained"]:
            assert Path(kept["path"]).parent.parent == Path(out["run_dir"]) and CH.sha256_hex(Path(kept["path"]).read_bytes()) == kept["sha256"]
    assert Path(r["run_dir"]).is_dir() and (Path(r["run_dir"]) / "chain_hermetic.json").exists() and json.loads((Path(r["run_dir"]) / "chain_hermetic.json").read_text())["run_id"] == r["run_id"]
    ids_a = {c["receipt"]["request_id"] for c in a["cases"] if c["receipt"].get("invoked")}
    ids_b = {c["receipt"]["request_id"] for c in b["cases"] if c["receipt"].get("invoked")}
    assert ids_a and ids_b and not (ids_a & ids_b)
    final = json.loads((tmp_path / "chain_hermetic.json").read_text())
    assert final["run_id"] == a["run_id"] and final["run_dir"] == a["run_dir"]


class _BQJob:
    def __init__(self, job_id, rows=None, fail=None, state="DONE", user_email="op@x"):
        self.job_id, self._rows, self._fail, self.state, self.user_email, self.error_result = job_id, rows or [], fail, state, user_email, None
        self.total_bytes_billed = self.total_bytes_processed = self.slot_millis = 0
        self.cache_hit, self.created, self.started, self.ended, self._properties = False, None, None, None, {}

    def result(self):
        if self._fail:
            raise self._fail
        return list(self._rows)


class FakeBigQuery:
    """Serves the chain's actual SQL from one or more compiled projections. Every query becomes a server-side job with
    the caller-chosen id; `fail_stage` makes that stage's result() raise; `hide_declaration` returns zero rows for the
    declaration read (the Opus PR41 P1 probe)."""

    project = "billing-project"      # the client's project: where the jobs run; the dataset project is the module PROJECT

    def __init__(self, projections, head, fail_stage=None, hide_declaration=False, email="op@x"):
        self.pubs = {p["publication_id"]: p for p in projections}
        self.head, self.fail_stage, self.hide_declaration, self.email = head, fail_stage, hide_declaration, email
        self.jobs, self.calls = {}, []            # jobs keyed by (project, job_id)

    @staticmethod
    def _params(cfg):
        out = {}
        for p in cfg.query_parameters:
            out[p.name] = getattr(p, "values", None) if hasattr(p, "values") else p.value
        return out

    def _rows(self, q, prm):
        pub = prm.get("p") or prm.get("publication_id")
        proj = self.pubs.get(pub)
        if "FROM `" in q and ".publications` WHERE bundle_id = @b AND publication_id = @p" in q:
            if proj is None or prm["b"] != proj["bundle_id"]:
                return []
            om = proj["output_manifest"]
            return [{"publication_id": pub, "bundle_id": proj["bundle_id"], "source_pin": proj["source_pin"], "compiler_version": proj["compiler_version"],
                     "source_manifest_sha256": proj["source_manifest_sha256"], "nodes_sha256": om["nodes_sha256"], "edges_sha256": om["edges_sha256"],
                     "node_count": om["nodes"], "edge_count": om["edges"], "section_count": 0, "validation_status": "READY"}]
        if ".active_publication` WHERE bundle_id = @b" in q:
            return [{"bundle_id": prm["b"], "publication_id": self.head}] if self.head else []
        if "EXCEPT(stale_after_ts)" in q:
            return [dict(n) for n in proj["nodes"]] if proj else []
        if ".edges` WHERE bundle_id = @b AND publication_id = @p ORDER BY edge_id" in q:
            return [dict(e) for e in proj["edges"]] if proj else []
        if "WHERE node_id = @id AND publication_id = @p" in q:            # seed visibility / declaration
            if "kind, local_id" in q and self.hide_declaration:
                return []
            return [dict(n) for n in (proj or {}).get("nodes", []) if n["node_id"] == prm["id"]]
        if "hop1" in q:                                                    # fallback.sql walk
            nodes = {n["node_id"]: n for n in proj["nodes"]}
            out = []
            for seed in prm["seeds"]:
                for e in proj["edges"]:
                    if e["src_id"] == seed and e["relation"] == "LINKS_TO":
                        ac = nodes.get(e["dst_id"])
                        if ac and ac["type"] == "Attested Computation" and not ac["stub"] and (ac["status"] or "stable") != "deprecated":
                            out.append({"seed_id": seed, "concept_hops": 1, "hop_ids": [seed, ac["node_id"]], "edge_ids": [e["edge_id"]],
                                        "computation_id": ac["node_id"], "computation_path": ac["path"], "computation_status": ac["status"]})
            return out
        if "AS concept_id, e.edge_id AS edge_id" in q:                    # context (fallback) + LEFT JOIN text
            nodes = {n["node_id"]: n for n in proj["nodes"]}
            out = []
            for e in proj["edges"]:
                if e["src_id"] in prm["concept_ids"] and e["relation"] in ("VERIFIED_BY", "GENERATED_BY", "DERIVES_FROM", "LINKS_TO", "HAS_SECTION"):
                    o = nodes[e["dst_id"]]
                    out.append({"concept_id": e["src_id"], "edge_id": e["edge_id"], "relation": e["relation"], "edge_declaration": e["declaration"],
                                "edge_at": e["authored_at"], "edge_resolution": e["resolution"], "edge_inferred": e["inferred"], "other_id": o["node_id"],
                                "other_kind": o["kind"], "other_local_id": o["local_id"], "other_title": o["title"], "other_type": o["type"],
                                "other_status": o["status"], "other_actor_kind": o["actor_kind"], "other_stub": o["stub"], "other_text": o["text"],
                                "other_text_sha256": o["text_sha256"], "other_stale_after": o["stale_after"], "other_path": o["path"], "other_runtime": o["runtime"]})
            return out
        if "WHERE node_id IN UNNEST(@ids)" in q:
            return [{k: n[k] for k in ("node_id", "local_id", "path", "title", "type", "status", "stale_after", "stub", "runtime")} for n in proj["nodes"] if n["node_id"] in prm["ids"]]
        raise AssertionError("unrouted query: " + q[:120])

    def query(self, q, job_config=None, location=None, job_id=None, project=None, **kw):
        assert job_id, "the chain must choose the job id before the send"
        assert project == self.project, "the chain must submit under the journaled (client) project"
        prm = self._params(job_config)
        stage = job_config.labels.get("stage")
        self.calls.append({"stage": stage, "job_id": job_id, "project": project})
        fail = RuntimeError(f"simulated failure at {stage}") if stage == self.fail_stage else None
        job = _BQJob(job_id, self._rows(q, prm), fail=fail, state="DONE", user_email=self.email)
        self.jobs[(project, job_id)] = job
        return job

    def get_job(self, job_id, project=None, location=None, retry=None, timeout=None):
        if (project, job_id) not in self.jobs:
            from google.api_core import exceptions as gexc
            raise gexc.NotFound(f"{job_id} not in {project}")
        return self.jobs[(project, job_id)]

    def cancel_job(self, job_id, project=None, **kw):
        self.jobs[(project, job_id)].state = "DONE"


def _live_catalog(projection, sdk_root, tmp_path, sample_root, bq, monkeypatch, **kw):
    monkeypatch.setattr(CH, "is_live_reader", lambda r: True)      # the reader gate is tested in test_catalog_reader_mode_gates; here the injected reader stands in for the HTTP one
    return CH.run_chain(engine="fallback", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), clients={"engine": "fallback", "bq": bq},
                        requester="t", as_of=AS_OF, seed_mode="catalog", catalog_reader=_reader(projection), acme_root=sample_root,
                        runner=kw.pop("runner", lambda argv, **k: subprocess.CompletedProcess(argv, 1, stdout="", stderr="no live SDK in this test")), **kw)


def test_catalog_live_branch_journals_every_job_including_the_declaration(projection, sdk_root, tmp_path, sample_root, monkeypatch):
    """The actual live branch (fallback engine, BigQueryStore, journaled retrieve._run, store-routed declaration): no
    monkeypatch on declaration/governed/store. Every job id is chosen before the send and lands in the identity set."""
    bq = FakeBigQuery([projection], head=projection["publication_id"])
    out = _live_catalog(projection, sdk_root, tmp_path, sample_root, bq, monkeypatch)
    assert out["publication"]["status"] == "OK" and out["source"]["status"] == "OK" and out["store"]["dataset"] == C.CatalogConfig().runtime_dataset
    cases = {c["case"]: c for c in out["cases"]}
    for c in cases.values():
        assert c["retrieval"]["status"] == "OK" and c["retrieval"]["reached"] and c["retrieval"]["scope"]["engine"] == "fallback"
        assert c["declaration"]["status"] == "OK" and c["declaration"]["job_id"] and c["payload"]["status"] == "CONSISTENT", c["payload"].get("failed")
    assert cases["approved"]["bind"]["status"] == "BOUND" and cases["declaration-mismatch"]["bind"]["status"] == "MISMATCH"
    assert out["verdict"] == "CHAIN_INCOMPLETE" and out["broken_at"] == "approved"      # only because the SDK child is a stub here
    roles = [j["role"] for j in out["journal"]["jobs"]]
    assert roles.count("chain_declaration") == 3 and roles.count("retrieval_walk") == 3 and roles.count("retrieval_context") == 3 and roles.count("retrieval_nodes") == 3
    assert roles.count("payload_rows") == 6 and roles[:3] == ["pin_resolution", "seed_visibility", "observed_head"]
    ids = [j["job_id"] for j in out["journal"]["jobs"]]
    assert all(ids) and len(set(ids)) == len(ids) == len(bq.calls) and set(ids) == {c["job_id"] for c in bq.calls}
    assert set(out["job_inventory"]["graph"]) == set(ids) and out["job_inventory"]["unresolved"] == []
    assert len(out["job_inventory"]["graph"]) == len(set(out["job_inventory"]["graph"])) == len(bq.calls)     # every job once (Opus P3)
    assert all(out["job_inventory"]["refs"][i] == {"project": "billing-project", "location": "US"} for i in ids)
    assert all(c["project"] == "billing-project" for c in bq.calls)
    assert out["same_requester"]["status"] == "UNKNOWN" and out["same_requester"]["reason"].startswith("nothing to compare")   # no receipt job from the stub
    decl_ids = {c["declaration"]["job_id"] for c in cases.values()}
    assert decl_ids <= set(ids) and all(bq.jobs[("billing-project", i)].state == "DONE" for i in decl_ids)
    assert all(j["terminal"] for j in out["journal"]["jobs"]) and out["job_inventory"]["journal"]["actual_jobs"] == len(ids)


def test_catalog_live_empty_declaration_keeps_its_job_id(projection, sdk_root, tmp_path, sample_root, monkeypatch):
    bq = FakeBigQuery([projection], head=projection["publication_id"], hide_declaration=True)
    out = _live_catalog(projection, sdk_root, tmp_path, sample_root, bq, monkeypatch)
    for c in out["cases"]:
        assert c["declaration"]["status"] == "NOT_VISIBLE" and c["declaration"]["job_id"] and c["declaration"]["job_id"] in out["job_inventory"]["graph"]
        assert c["acceptance"]["status"] == "NOT_REACHED" and c["payload"]["status"] == "NOT_REACHED"
    empty = [j for j in out["journal"]["jobs"] if j["role"] == "chain_declaration"]
    assert len(empty) == 3 and all(j["state"] == "EMPTY" and j["job_id"] for j in empty)
    assert out["verdict"] == "CHAIN_INCOMPLETE"


def test_catalog_live_failed_retrieval_job_is_journaled_and_reconciled(projection, sdk_root, tmp_path, sample_root, monkeypatch):
    bq = FakeBigQuery([projection], head=projection["publication_id"], fail_stage="walk")
    out = _live_catalog(projection, sdk_root, tmp_path, sample_root, bq, monkeypatch)
    walks = [j for j in out["journal"]["jobs"] if j["role"] == "retrieval_walk"]
    assert len(walks) == 3 and all(j["state"] == "DONE" and j["reconciled"] and j["job_id"] and "simulated failure" in j["error"] for j in walks)
    assert all(c["retrieval"]["status"] == "ERROR" and not c["retrieval"]["reached"] for c in out["cases"])
    assert {j["job_id"] for j in walks} <= set(out["job_inventory"]["graph"]) and out["verdict"] == "CHAIN_INCOMPLETE"


def test_catalog_live_unresolved_job_is_never_connected(projection, sdk_root, tmp_path, sample_root, monkeypatch):
    bq = FakeBigQuery([projection], head=projection["publication_id"], fail_stage="chain-declaration")
    bq.get_job = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("jobs.get unreachable"))
    out = _live_catalog(projection, sdk_root, tmp_path, sample_root, bq, monkeypatch)
    assert out["verdict"] == "CHAIN_INCOMPLETE"
    unresolved = out["job_inventory"]["unresolved"]
    assert unresolved and all(u["role"] == "chain_declaration" and u["state"] == "UNKNOWN" and u["job_id"] for u in unresolved)
    assert out["evidence"]["unresolved_jobs"] == len(unresolved) and out["broken_at"] == "approved"
    assert not any(j["job_backed"] if "job_backed" in j else False for j in out["journal"]["jobs"])   # chain entries carry the full ref, not a driver flag
    # unresolved alone (every case reached, nothing WRONG) still blocks CONNECTED and names itself
    bq2 = FakeBigQuery([projection], head=projection["publication_id"], fail_stage="observed-head")
    bq2.get_job = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("jobs.get unreachable"))
    out2 = _live_catalog(projection, sdk_root, tmp_path, sample_root, bq2, monkeypatch)
    assert out2["verdict"] == "CHAIN_BROKEN" and out2["publication"]["status"] == "ERROR" and out2["broken_at"] == "publication"     # head observation failed: refused, not silently skipped
    assert out2["evidence"]["unresolved_jobs"] == 1 and out2["journal"]["summary"]["unresolved"] == 1


def test_catalog_live_dataset_mismatch_is_refused_before_any_read(projection, sdk_root, tmp_path, sample_root, monkeypatch):
    bq = FakeBigQuery([projection], head=projection["publication_id"])
    monkeypatch.setattr(CH, "is_live_reader", lambda r: True)
    out = CH.run_chain(engine="fallback", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), clients={"engine": "fallback", "bq": bq, "ds": "some_other_dataset"},
                       requester="t", as_of=AS_OF, seed_mode="catalog", catalog_reader=_reader(projection), acme_root=sample_root,
                       runner=lambda argv, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    assert out["verdict"] == "CHAIN_BROKEN" and out["broken_at"] == "publication" and out["publication"]["status"] == "DESTINATION_MISMATCH"
    assert out["publication"]["client_dataset"] == "some_other_dataset" and bq.calls == [] and out["journal"]["jobs"] == []
    # a supplied store on a different dataset is refused the same way
    import okf_bq_graph.publication as PUB
    store = PUB.BigQueryStore(bq, "p", "okf_catalog_chain_other", "US", None)
    out = CH.run_chain(engine="fallback", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), clients={"engine": "fallback", "bq": bq},
                       requester="t", as_of=AS_OF, seed_mode="catalog", catalog_reader=_reader(projection), acme_root=sample_root, store=store,
                       runner=lambda argv, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    assert out["verdict"] == "CHAIN_BROKEN" and out["publication"]["status"] == "DESTINATION_MISMATCH" and out["publication"]["store_dataset"] == "okf_catalog_chain_other"
    assert bq.calls == [] and out["journal"]["jobs"] == []                       # refused before the first store read, on this arm too
    # the B2 configuration routes every read to the owned dataset
    from okf_bq_graph.catalog_lifecycle import LifecycleConfig
    cfg = LifecycleConfig(run_id="t-b2-0001").catalog_config("metrics/gross-margin")
    reader = C.MockReader(C.mock_pages([cfg.entry], 5), {cfg.entry: dict(_pin_entry(projection, runtime_dataset=cfg.runtime_dataset, managed_by_profile=cfg.managed_by_profile,
                                                                                          managed_by_deployment=cfg.managed_by_deployment), name=cfg.entry)})
    bq3 = FakeBigQuery([projection], head=projection["publication_id"])
    out = CH.run_chain(engine="fallback", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), clients={"engine": "fallback", "bq": bq3}, requester="t", as_of=AS_OF,
                       seed_mode="catalog", catalog_reader=reader, catalog_cfg=cfg, acme_root=sample_root,
                       runner=lambda argv, **k: subprocess.CompletedProcess(argv, 1, stdout="", stderr="stub"))
    assert out["store"]["dataset"] == cfg.runtime_dataset == "okf_catalog_chain_t_b2_0001"
    assert all(c["retrieval"]["scope"]["publication_id"] == projection["publication_id"] for c in out["cases"])
    assert all(j.get("dataset") in (None, cfg.runtime_dataset) for j in out["journal"]["jobs"])


def test_catalog_retains_the_governed_input_per_case(projection, sdk_root, tmp_path, sample_root, monkeypatch):
    monkeypatch.setenv("OKF_OPERATOR_EMAIL", "operator@example.test")
    import okf_bq_graph.authz as AZ
    AZ._OPERATOR = None
    out = _run_catalog(projection, sdk_root, tmp_path, sample_root, requester="operator@example.test")
    for c in out["cases"]:
        kept = c["retrieval"]["retained"]
        p = Path(kept["path"])
        assert p.parent == Path(out["run_dir"]) / "retrieval" and CH.sha256_hex(p.read_bytes()) == kept["sha256"]
        saved = json.loads(p.read_text())
        assert saved["scope"]["publication_id"] == projection["publication_id"] and saved["paths"] and saved["computations"][0]["sql"]
        assert kept["redacted"] and "operator@example.test" not in p.read_text() and saved["scope"]["requester"] == "operator"   # evidence hygiene
    assert {r["name"] for r in out["journal"]["retained"]} >= {"retrieval_approved", "retrieval_sql-substitution", "retrieval_declaration-mismatch"}


def test_job_ids_of_includes_journal_and_payload_jobs():
    cases = [{"case": "approved", "retrieval": {"timing": {"jobs": [{"job_id": "w"}]}}, "declaration": {"job_id": "d1"},
              "payload": {"jobs": [{"nodes_job": {"job_id": "pn"}, "edges_job": {"job_id": "pe"}}]},
              "receipt": {"invoked": True, "receipt": {"job": {"job_id": "r1"}}}}]
    ids = CH.job_ids_of(cases, None, ["pin1", "seed1", "head1", None, "pin1"])
    assert ids["graph"] == ["pin1", "seed1", "head1", "w", "d1", "pn", "pe"] and [j["job_id"] for j in ids["receipt"]] == ["r1"]


def test_module_cli_catalog_mock(sdk_root, sample_root, projection, tmp_path):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    resp = tmp_path / "responses.json"
    names = [f"{CCFG.group}/entries/other/{i}" for i in range(3)] + [CCFG.entry]
    resp.write_text(json.dumps({"pages": C.mock_pages(names, 2), "entries": {CCFG.entry: _pin_entry(projection)}}))
    env = dict(os.environ, OKF_OPERATOR_EMAIL="operator@example.test", PYTHONPATH=root, OKF_ACME_ROOT=sample_root)
    r = subprocess.run([sys.executable, "-m", "okf_bq_graph.chain", "--hermetic", "--seed-mode", "catalog", "--catalog-responses", str(resp),
                        "--out", str(tmp_path / "ev"), "--sdk-root", sdk_root], env=env, capture_output=True, text=True, cwd=root)
    assert r.returncode == 0, r.stderr[-800:]
    assert "CHAIN_CONNECTED" in r.stdout and "seed_mode=catalog-mock" in r.stdout and (tmp_path / "ev" / "chain_hermetic.json").exists()
    for bad in (["--live", "--seed-mode", "catalog", "--catalog-responses", str(resp)],
                ["--hermetic", "--seed-mode", "catalog"],
                ["--hermetic", "--catalog-responses", str(resp)],
                ["--hermetic", "--seed-mode", "catalog", "--catalog-group", "g", "--catalog-responses", str(resp)],
                ["--hermetic", "--seed-mode", "catalog", "--catalog-entry", "e", "--catalog-responses", str(resp)]):
        r = subprocess.run([sys.executable, "-m", "okf_bq_graph.chain", *bad, "--out", str(tmp_path / "ev2"), "--sdk-root", sdk_root],
                           env=env, capture_output=True, text=True, cwd=root)
        assert r.returncode == 2 and not (tmp_path / "ev2").exists(), (bad, r.stderr[-300:])


def test_same_requester_reads_each_graph_job_under_its_journaled_reference():
    """Astra re-review R4: identity is checked where the job ran, not under the module defaults."""
    seen = []

    class Client:
        def get_job(self, jid, project=None, location=None):
            seen.append((jid, project, location))
            return _Job("op@x")
    refs = {"g1": ("billing-project", "US"), "g2": ("billing-project", "EU")}
    r = CH.same_requester(Client(), ["g1", "g2", "g3"], [{"job_id": "r1", "project": "p-r", "location": "US"}], refs=refs)
    assert r["status"] == "SAME" and seen == [("g1", "billing-project", "US"), ("g2", "billing-project", "EU"), ("g3", CH.PROJECT, CH.LOCATION), ("r1", "p-r", "US")]


def test_job_ids_of_never_double_counts():
    cases = [{"case": "approved", "retrieval": {"timing": {"jobs": [{"job_id": "w"}, {"job_id": "w"}]}}, "declaration": {"job_id": "d1"},
              "receipt": {"invoked": False}},
             {"case": "sql-substitution", "retrieval": {"timing": {"jobs": [{"job_id": "w"}]}}, "declaration": {"job_id": "d1"}, "receipt": {"invoked": False}}]
    ids = CH.job_ids_of(cases, "w", ["d1", "w"])
    assert ids["graph"] == ["w", "d1"]


# =============================================================================== U1/U4: engine admission, proof, scope
class _StubWindow:
    """A window controller as `chain` sees it: a state, a label, a record and a REAL submission gate, so a client the
    chain builds is genuinely bound to it (or genuinely is not)."""

    def __init__(self, state="OPEN", label="chain-gql-1", probes=6, journal=None, gate=True):
        import time as _time
        from okf_bq_graph import lifecycle as _L
        self.state = state
        self.cfg = SimpleNamespace(label=label)
        self.jobs = _L.WindowJobs(label, _time.monotonic() + 600, journal) if gate and journal else None
        self.operator = None
        self.clients = []
        self.workers = []
        self.record = {"controller": "okf_bq_graph.chain_window/0.1.0",
                       "assignment": {"probes": [{"ok": True}] * probes}}

    def bind_client(self, client, role, principal=None):
        bound = self.jobs.bind(client)
        self.clients.append({"role": role, "principal": principal})
        return bound

    def register_worker(self, name, stop=None, join=None, jobs=None, obligations=None, evidence=None):
        self.workers.append({"name": name, "stop": stop, "join": join, "jobs": jobs, "obligations": obligations,
                             "evidence": dict(evidence or {})})


def _gql_result(*, engine="gql", walk="governed.sql", graph_table=True, cache=None, warnings=(),
                reservation=f"{CH.PROJECT}:{CH.LOCATION}.{CH.RESERVATION}", edition="ENTERPRISE", jobs=True):
    stages = [{"stage": s, "job_id": f"j_{s}", "state": "DONE", "reservation_id": reservation, "edition": edition}
              for s in ("walk", "context")] if jobs else []
    return {"status": "OK", "warnings": list(warnings),
            "scope": {"engine": engine, "cache": cache,
                      "templates": {"walk": {"name": walk, "sha256": "abc", "graph_table": graph_table},
                                    "context": {"name": "context.sql", "sha256": "def", "graph_table": True}}},
            "timing": {"jobs": stages}}


def test_bare_live_gql_refuses_before_any_client_grant_or_sdk_launch(sdk_root, tmp_path, monkeypatch):
    from google.cloud import bigquery
    monkeypatch.setattr(bigquery, "Client", lambda **kw: pytest.fail("no client may be built for a refused engine"))
    monkeypatch.setattr(CH, "resolve_pointer_job", lambda *a, **k: pytest.fail("no query may be submitted"))
    out = CH.run_chain(engine="gql", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), as_of=AS_OF,
                       runner=lambda *a, **k: pytest.fail("the SDK CLI must not be launched"))
    assert out["engine_admission"]["status"] == CH.GQL_WINDOW_NOT_CONFIGURED
    assert out["verdict"] == "CHAIN_INCOMPLETE" and out["broken_at"] == "engine_admission"
    assert out["cases"] == [] and out["engine_proof"]["status"] == CH.ENGINE_NOT_PROVEN
    assert "does not open capacity" in out["engine_admission"]["reason"]


def test_a_restricted_gql_run_refuses_before_the_broker_grants(sdk_root, tmp_path, monkeypatch):
    class Broker:
        def describe(self):
            pytest.fail("no broker may be described before admission")

        def grant(self):
            pytest.fail("no grant may be issued for a refused engine")

    out = CH.run_chain(engine="gql", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), as_of=AS_OF,
                       requester_mode="restricted", broker=Broker())
    assert out["engine_admission"]["status"] == CH.GQL_WINDOW_NOT_CONFIGURED
    assert out["broken_at"] == "engine_admission"


def test_a_window_that_never_proved_its_assignment_is_refused(sdk_root, tmp_path, monkeypatch):
    monkeypatch.setattr(CH, "resolve_pointer_job", lambda *a, **k: pytest.fail("no query may be submitted"))
    out = CH.run_chain(engine="gql", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), as_of=AS_OF,
                       window=_StubWindow(state="READY"))
    assert out["engine_admission"]["status"] == "GQL_WINDOW_NOT_OPEN"
    assert out["broken_at"] == "engine_admission"


def test_an_open_window_admits_and_is_recorded(sdk_root, tmp_path, monkeypatch):
    monkeypatch.setattr(CH, "resolve_pointer_job", lambda *a, **k: (None, "pointer-job"))
    window = _StubWindow(journal=tmp_path / "jobs.json")
    out = CH.run_chain(engine="gql", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), as_of=AS_OF,
                       clients={"engine": "gql", "bq": window.bind_client(object(), role="requester")},
                       window=window)
    assert out["engine_admission"]["status"] == "OK" and out["engine_admission"]["assignment_probes"] == 6
    assert out["window"]["label"] == "chain-gql-1" and out["window"]["state"] == "OPEN"
    assert out["broken_at"] == "publication"     # it got past admission and refused on its own evidence


# ---- Astra PR47 #1: an admitted window must actually own the clients and the receipt child
def test_an_unbound_client_is_refused_before_any_query_or_sdk_launch(sdk_root, tmp_path, monkeypatch):
    """A window that records a controller but hands the chain an untracked client bounds nothing."""
    monkeypatch.setattr(CH, "resolve_pointer_job", lambda *a, **k: pytest.fail("no query may be submitted"))
    out = CH.run_chain(engine="gql", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), as_of=AS_OF,
                       clients={"engine": "gql", "bq": object()}, window=_StubWindow(journal=tmp_path / "jobs.json"),
                       runner=lambda *a, **k: pytest.fail("the SDK CLI must not be launched"))
    assert out["engine_admission"]["status"] == "GQL_CLIENTS_UNBOUND"
    assert out["engine_admission"]["unbound"] == ["clients.bq"]
    assert out["verdict"] == "CHAIN_INCOMPLETE" and out["broken_at"] == "engine_admission" and out["cases"] == []


def test_a_restricted_run_refuses_an_unbound_broker_before_the_grant(sdk_root, tmp_path):
    class Broker:
        sa = object()
        owner = object()

        def describe(self):
            return {"kind": "unbound"}

        def grant(self):
            pytest.fail("no grant may be issued while a client sits outside the gate")

    out = CH.run_chain(engine="gql", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), as_of=AS_OF,
                       requester_mode="restricted", broker=Broker(),
                       window=_StubWindow(journal=tmp_path / "jobs.json"))
    assert out["engine_admission"]["status"] == "GQL_CLIENTS_UNBOUND"
    assert out["engine_admission"]["unbound"] == ["broker.requester", "broker.operator"]
    assert out["broken_at"] == "engine_admission"


def test_the_chain_builds_its_own_client_through_the_controller(sdk_root, tmp_path, monkeypatch):
    """With no caller-supplied clients the chain must construct through `window.bind_client`, not `bigquery.Client`."""
    from google.cloud import bigquery
    window = _StubWindow(journal=tmp_path / "jobs.json")
    monkeypatch.setattr(CH, "resolve_pointer_job", lambda *a, **k: (None, "pointer-job"))
    monkeypatch.setattr(bigquery, "Client", lambda **kw: SimpleNamespace(project="p", location="US"))
    out = CH.run_chain(engine="gql", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), as_of=AS_OF, window=window)
    assert out["engine_admission"]["status"] == "OK"
    assert [c["role"] for c in window.clients] == ["requester"]
    assert out["window"]["bound_clients"][0]["role"] == "requester"


def test_the_receipt_child_is_registered_with_the_controller(sdk_root, tmp_path, monkeypatch):
    from okf_bq_graph import receipt_window as RWD
    window = _StubWindow(journal=tmp_path / "jobs.json")
    bridge = RWD.ReceiptBridge(sdk_root, label="chain-gql-1", deadline_epoch=time.time() + 300,
                               directory=tmp_path / "bridge")
    bridge.record["status"] = RWD.SUPPORTED
    monkeypatch.setattr(CH, "resolve_pointer_job", lambda *a, **k: (None, "pointer-job"))
    out = CH.run_chain(engine="gql", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), as_of=AS_OF,
                       clients={"engine": "gql", "bq": window.bind_client(object(), role="requester")},
                       window=window, receipt_bridge=bridge)
    worker = next(w for w in window.workers if w["name"] == "receipt_child")
    assert worker["stop"] == bridge.stop and worker["join"] == bridge.join and worker["jobs"] == bridge.jobs
    assert out["receipt_bridge"]["worker"].startswith("registered")


def test_an_unsupported_bridge_refuses_before_the_chain_runs(sdk_root, tmp_path, monkeypatch):
    from okf_bq_graph import receipt_window as RWD
    window = _StubWindow(journal=tmp_path / "jobs.json")
    bridge = RWD.ReceiptBridge(tmp_path / "not-an-sdk", label="w", deadline_epoch=time.time() + 300,
                               directory=tmp_path / "bridge")
    bridge.handshake()
    monkeypatch.setattr(CH, "resolve_pointer_job", lambda *a, **k: pytest.fail("no query may be submitted"))
    out = CH.run_chain(engine="gql", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), as_of=AS_OF,
                       clients={"engine": "gql", "bq": window.bind_client(object(), role="requester")},
                       window=window, receipt_bridge=bridge)
    assert out["receipt_bridge"]["status"] == RWD.UNSUPPORTED
    assert out["broken_at"] == "receipt_bridge" and out["verdict"] == "CHAIN_INCOMPLETE"


def test_an_unclean_window_downgrades_the_final_record(sdk_root, tmp_path):
    """`run_chain` returns before the window closes, so the retained record is amended with the actual closeout."""
    out = {"mode": "live", "run_id": "r1", "run_dir": str(tmp_path), "verdict": "CHAIN_CONNECTED",
           "requester": {"mode": "same-requester"}, "job_inventory": {}}
    window = SimpleNamespace(cfg=SimpleNamespace(label="chain-gql-1"), state="CLOSED",
                             record={"clean": False, "cleanup": {"jobs_unresolved": ["okf_graph_x"]},
                                     "restores": [], "workers": []})
    final = CH.finalize_cleanup(out, window, str(tmp_path))
    assert final["verdict"] == "CHAIN_INCOMPLETE" and final["broken_at"] == "window_cleanup"
    assert final["window"]["clean"] is False
    assert json.loads((tmp_path / "chain_live.json").read_text())["broken_at"] == "window_cleanup"


def test_a_clean_window_leaves_the_verdict_alone(sdk_root, tmp_path):
    out = {"mode": "live", "run_id": "r1", "run_dir": str(tmp_path), "verdict": "CHAIN_CONNECTED",
           "requester": {"mode": "same-requester"}, "job_inventory": {}}
    window = SimpleNamespace(cfg=SimpleNamespace(label="w"), state="CLOSED",
                             record={"clean": True, "cleanup": {"jobs_unresolved": []}, "restores": [], "workers": []})
    assert CH.finalize_cleanup(out, window, str(tmp_path))["verdict"] == "CHAIN_CONNECTED"


def test_a_fallback_run_needs_no_window():
    assert CH.gql_admission("fallback", True, None)["status"] == "NOT_REQUIRED"
    assert CH.gql_admission("oracle", False, None)["status"] == "NOT_REQUIRED"


# ---- engine proof
def test_engine_proof_accepts_a_real_gql_execution():
    proof = CH.engine_proof("gql", {"engine": "gql"}, _gql_result())
    assert proof["status"] == CH.ENGINE_PROVEN and proof["reasons"] == []
    assert [j["stage"] for j in proof["jobs"]] == ["walk", "context"]


def test_a_client_configured_for_fallback_contradicts_a_gql_request():
    proof = CH.engine_proof("gql", {"engine": "fallback"}, _gql_result())
    assert proof["status"] == CH.ENGINE_CONTRADICTED
    assert "configured for engine 'fallback'" in proof["reasons"][0]


def test_a_fallback_template_contradicts_a_gql_claim():
    proof = CH.engine_proof("gql", {"engine": "gql"}, _gql_result(walk="fallback.sql", graph_table=False))
    assert proof["status"] == CH.ENGINE_CONTRADICTED
    assert any("fallback.sql" in r and "GRAPH_TABLE" in r for r in proof["reasons"])


def test_the_fallback_warning_contradicts_a_gql_claim():
    proof = CH.engine_proof("gql", {"engine": "gql"},
                            _gql_result(warnings=["FALLBACK engine: relational joins, not BigQuery Graph"]))
    assert proof["status"] == CH.ENGINE_CONTRADICTED


def test_a_cached_answer_cannot_establish_that_gql_executed():
    for state in ("HIT_RECHECKED", "HIT_DENIED"):
        proof = CH.engine_proof("gql", {"engine": "gql"}, _gql_result(cache=state, jobs=False))
        assert proof["status"] == CH.ENGINE_CONTRADICTED
        assert any("cannot establish" in r for r in proof["reasons"])


def test_no_walk_job_is_not_proven():
    proof = CH.engine_proof("gql", {"engine": "gql"}, _gql_result(jobs=False))
    assert proof["status"] == CH.ENGINE_NOT_PROVEN
    assert any("nothing executed on the graph" in r for r in proof["reasons"])


def test_an_on_demand_or_foreign_reservation_is_not_proven():
    assert CH.engine_proof("gql", {"engine": "gql"}, _gql_result(reservation=None))["status"] == CH.ENGINE_NOT_PROVEN
    assert CH.engine_proof("gql", {"engine": "gql"}, _gql_result(reservation="p:US.someone-elses"))["status"] == CH.ENGINE_NOT_PROVEN
    assert CH.engine_proof("gql", {"engine": "gql"}, _gql_result(edition="STANDARD"))["status"] == CH.ENGINE_NOT_PROVEN


def test_an_enterprise_assignment_alone_does_not_turn_sql_into_gql():
    """Enterprise capacity plus the relational template is still relational."""
    proof = CH.engine_proof("gql", {"engine": "gql"}, _gql_result(walk="fallback.sql", graph_table=False))
    assert proof["status"] == CH.ENGINE_CONTRADICTED
    assert all(j["edition"] == "ENTERPRISE" for j in proof["jobs"])


def test_a_returned_engine_label_cannot_select_the_verdict_on_its_own():
    proof = CH.engine_proof("gql", {"engine": "gql"}, _gql_result(engine="fallback"))
    assert proof["status"] == CH.ENGINE_CONTRADICTED
    assert any("returned scope names engine" in r for r in proof["reasons"])


def test_an_unreached_retrieval_is_not_proven():
    proof = CH.engine_proof("gql", {"engine": "gql"}, None)
    assert proof["status"] == CH.ENGINE_NOT_PROVEN and "never ran" in proof["reasons"][0]


def test_a_plain_sql_chain_stays_plain_sql():
    proof = CH.engine_proof("fallback", {"engine": "fallback"},
                            _gql_result(engine="fallback", walk="fallback.sql", graph_table=False,
                                        warnings=["FALLBACK engine: relational joins, not BigQuery Graph"]))
    assert proof["status"] == CH.ENGINE_PROVEN      # proven to be what it says it is: relational fallback
    assert proof["requested"] == "fallback"


def test_merge_engine_proof_takes_the_worst_case():
    proven = {"status": CH.ENGINE_PROVEN, "case": "a", "reasons": []}
    unproven = {"status": CH.ENGINE_NOT_PROVEN, "case": "b", "reasons": ["no walk job"]}
    contradicted = {"status": CH.ENGINE_CONTRADICTED, "case": "c", "reasons": ["fallback"]}
    assert CH.merge_engine_proof([proven, proven])["status"] == CH.ENGINE_PROVEN
    assert CH.merge_engine_proof([proven, unproven])["status"] == CH.ENGINE_NOT_PROVEN
    assert CH.merge_engine_proof([proven, unproven, contradicted])["status"] == CH.ENGINE_CONTRADICTED
    assert CH.merge_engine_proof([])["status"] == CH.ENGINE_NOT_PROVEN


# ---- the proof drives the verdict, and memoization is off for the executing cases
def _live_gql_chain(sdk_root, tmp_path, monkeypatch, result, *, cases=("approved",), capture=None):
    monkeypatch.setattr(CH, "resolve_pointer_job", lambda *a, **k: (CH.PUBLICATION_PIN, "pointer-job"))

    def governed(query, publication_id, requester, as_of, clients):
        if capture is not None:
            capture.append(clients)
        return result

    monkeypatch.setattr(CH, "governed", governed)
    monkeypatch.setattr(CH, "pick_computation", lambda r, path: None)     # stop before bind: the engine is the subject
    window = _StubWindow(journal=tmp_path / "window_jobs.json")
    return CH.run_chain(engine="gql", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), as_of=AS_OF,
                        clients={"engine": "gql", "bq": window.bind_client(object(), role="requester"), "cache": {}},
                        window=window, cases=cases,
                        runner=lambda *a, **k: pytest.fail("nothing binds, so the CLI must not run"))


def test_a_fallback_answer_under_a_gql_request_breaks_the_chain(sdk_root, tmp_path, monkeypatch):
    out = _live_gql_chain(sdk_root, tmp_path, monkeypatch,
                          _gql_result(walk="fallback.sql", graph_table=False,
                                      warnings=["FALLBACK engine: relational joins, not BigQuery Graph"]))
    assert out["engine_proof"]["status"] == CH.ENGINE_CONTRADICTED
    assert out["verdict"] == "CHAIN_BROKEN" and out["broken_at"] in ("approved", "engine_proof")


def test_an_unproven_engine_leaves_the_chain_incomplete(sdk_root, tmp_path, monkeypatch):
    out = _live_gql_chain(sdk_root, tmp_path, monkeypatch, _gql_result(jobs=False))
    assert out["engine_proof"]["status"] == CH.ENGINE_NOT_PROVEN
    assert out["verdict"] == "CHAIN_INCOMPLETE"


def test_live_gql_disables_memoization_for_the_executing_cases(sdk_root, tmp_path, monkeypatch):
    seen = []
    out = _live_gql_chain(sdk_root, tmp_path, monkeypatch, _gql_result(), capture=seen)
    assert out["cache_policy"]["memoization"] == "DISABLED"
    assert out["cache_policy"]["exempt_cases"] == ["revocation-before-replay"]
    assert seen and all(c.get("cache") is None for c in seen)


def test_hermetic_runs_carry_no_engine_proof_claim(clients, projection, sdk_root, tmp_path):
    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), clients=clients,
                       projection=projection, requester="t", as_of=AS_OF)
    assert out["engine_proof"]["status"] == "NOT_APPLICABLE"
    assert "no BigQuery engine executed" in out["engine_proof"]["reason"]


# ---- scoped case selection
def test_a_scoped_run_names_what_it_did_not_run(clients, projection, sdk_root, tmp_path):
    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), clients=clients,
                       projection=projection, requester="t", as_of=AS_OF, cases=("approved",))
    assert out["selected_cases"] == ["approved"]
    assert out["omitted_cases"] == ["sql-substitution", "declaration-mismatch"]
    assert out["scope"]["complete_suite"] is False
    assert [c["case"] for c in out["cases"]] == ["approved"]
    assert out["verdict"] == "CHAIN_CONNECTED"     # scoped, and the record says exactly how scoped


def test_the_full_suite_is_marked_complete(clients, projection, sdk_root, tmp_path):
    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), clients=clients,
                       projection=projection, requester="t", as_of=AS_OF)
    assert out["omitted_cases"] == [] and out["scope"]["complete_suite"] is True


def test_an_unknown_case_is_refused(clients, projection, sdk_root, tmp_path):
    with pytest.raises(ValueError, match="unknown case"):
        CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), clients=clients,
                     projection=projection, requester="t", as_of=AS_OF, cases=("approved-restricted",))


def test_cli_case_selection(sdk_root, sample_root, tmp_path, capsys):
    assert CH.main(["--hermetic", "--sdk-root", sdk_root, "--out", str(tmp_path), "--acme-root", sample_root,
                    "--cases", "approved"]) == 0
    printed = capsys.readouterr().out
    assert "selected_cases=approved" in printed and "omitted_cases=sql-substitution,declaration-mismatch" in printed
    record = json.loads((tmp_path / "chain_hermetic.json").read_text())
    assert record["selected_cases"] == ["approved"] and record["scope"]["complete_suite"] is False


def test_cli_refuses_a_window_flag_without_live_gql(sdk_root, tmp_path):
    with pytest.raises(SystemExit):
        CH.main(["--hermetic", "--sdk-root", sdk_root, "--out", str(tmp_path), "--gql-window", "w"])


# =============================================================================== Astra PR47 re-review (RR2)
def test_a_diagnostic_journal_mismatch_writes_a_durable_incomplete_record(sdk_root, tmp_path):
    """RR2 R5: the mismatch entries carry no `seq`, and reading one positionally crashed the whole assembly, so the
    run wrote no evidence at all."""
    class Bridge:
        record = {"status": "SUPPORTED"}
        label = "offline-only"

        def runner(self):
            return subprocess.run

        def stop(self):
            pass

        def join(self, timeout=30):
            return {"joined": True}

        def jobs(self):
            return [{"job_id": "journal-only-job", "project": CH.PROJECT, "location": CH.LOCATION,
                     "state": "SUBMITTED"}]

        def obligations(self):
            return []

        def ingest(self):
            return {"jobs": self.jobs(), "unresolved": [], "dry_runs": 0, "operations": 0, "entries": 0,
                    "launches": 1, "blocked": [], "refused": 0, "complete": True}

    out = CH.run_chain("oracle", False, sdk_root, str(tmp_path), requester="operator@example.test",
                       cases=("approved",), as_of=AS_OF, receipt_bridge=Bridge())
    record = json.loads((tmp_path / "chain_hermetic.json").read_text())
    assert out["verdict"] == "CHAIN_INCOMPLETE" and record["verdict"] == "CHAIN_INCOMPLETE"
    states = {u["state"] for u in out["job_inventory"]["unresolved"]}
    assert "JOURNAL_ONLY" in states and "DIAGNOSTIC_ONLY" in states
    assert all(u["seq"] is None for u in out["job_inventory"]["unresolved"])
    assert out["job_inventory"]["receipt_child_only"] == ["journal-only-job"]


def test_the_receipt_child_registers_its_obligations_with_the_controller(sdk_root, tmp_path, monkeypatch):
    """RR2 R1: evidence the bridge could not resolve into a reference must reach the durable gate too."""
    from okf_bq_graph import receipt_window as RWD

    window = _StubWindow(journal=tmp_path / "jobs.json")
    bridge = RWD.ReceiptBridge(sdk_root, label="chain-gql-1", deadline_epoch=time.time() + 300,
                               directory=tmp_path / "bridge")
    bridge.record["status"] = RWD.SUPPORTED
    monkeypatch.setattr(CH, "resolve_pointer_job", lambda *a, **k: (None, "pointer-job"))
    CH.run_chain(engine="gql", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), as_of=AS_OF,
                 clients={"engine": "gql", "bq": window.bind_client(object(), role="requester")},
                 window=window, receipt_bridge=bridge)
    worker = next(w for w in window.workers if w["name"] == "receipt_child")
    assert worker["obligations"] == bridge.obligations


def test_a_restricted_run_defers_its_teardown_to_the_window(sdk_root, tmp_path, monkeypatch):
    """RR2 R3: teardown used to run inline on the stopped workload channel, and its failure never reached the gate."""
    registered = []

    class Window(_StubWindow):
        def register_restore(self, name, restore, takes_client=False):
            registered.append({"name": name, "takes_client": takes_client, "call": restore})

    class Broker:
        def __init__(self):
            self.torn_down = []

        def describe(self):
            return {"kind": "test"}

        def grant(self):
            raise RuntimeError("grant refused so the run stops right after registration")

        def teardown(self, owner=None):
            self.torn_down.append(owner)
            return {"status": "VERIFIED"}

    window = Window(journal=tmp_path / "jobs.json")
    broker = Broker()
    broker.sa = window.bind_client(object(), role="requester")
    broker.owner = window.bind_client(object(), role="operator")
    out = CH.run_chain(engine="gql", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), as_of=AS_OF,
                       requester_mode="restricted", broker=broker, window=window)
    assert [r["name"] for r in registered] == ["broker_teardown"] and registered[0]["takes_client"] is True
    assert out["teardown"]["status"] == CH.DEFERRED_TEARDOWN
    assert broker.torn_down == [], "the teardown must not run inline on the stopped workload channel"
    # the registered callable hands the broker the window's bounded cleanup client
    cleanup_client = object()
    assert registered[0]["call"](cleanup_client) == {"status": "VERIFIED"}
    assert broker.torn_down == [cleanup_client]


def test_without_a_window_the_broker_tears_down_inline_as_before(sdk_root, tmp_path):
    class Broker:
        def __init__(self):
            self.calls = 0

        def describe(self):
            return {"kind": "test"}

        def grant(self):
            raise RuntimeError("grant refused")

        def teardown(self, owner=None):
            self.calls += 1
            return {"status": "NOT_NEEDED"}

    broker = Broker()
    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), as_of=AS_OF,
                       requester_mode="restricted", broker=broker)
    assert broker.calls == 1 and out["teardown"]["status"] == "NOT_NEEDED"


def test_finalize_cleanup_records_the_deferred_teardown_result(sdk_root, tmp_path):
    out = {"mode": "live", "run_id": "r1", "run_dir": str(tmp_path), "verdict": "CHAIN_CONNECTED",
           "requester": {"mode": "restricted-sa"}, "job_inventory": {},
           "teardown": {"status": CH.DEFERRED_TEARDOWN}}
    window = SimpleNamespace(cfg=SimpleNamespace(label="w"), state="CLOSED",
                             record={"clean": True, "cleanup": {"jobs_unresolved": []},
                                     "restores": [{"name": "broker_teardown", "ok": True,
                                                   "result": {"status": "VERIFIED"}}], "workers": []})
    final = CH.finalize_cleanup(out, window, str(tmp_path))
    assert final["teardown"] == {"status": "VERIFIED"}
    assert final["verdict"] == "CHAIN_CONNECTED"


# =============================================================================== Astra PR47 RR3
class _Broker:
    """A broker whose administrative inventory GROWS during teardown, as the real one's restoring DDL does."""

    def __init__(self, identity_after="BOUND"):
        self.owner = None
        self.admin_jobs = [{"job_id": "grant-1", "project": CH.PROJECT, "location": CH.LOCATION, "stage": "grant"}]
        self.admin_ops = [{"job_id": "grant-1"}]
        self.identity_calls = []
        self.identity_after = identity_after
        self.torn_down = False

    def describe(self):
        return {"kind": "test"}

    def grant(self):
        return {"status": "OK"}

    def teardown(self, owner=None):
        self.torn_down = True
        self.admin_jobs.append({"job_id": "restore-1", "project": CH.PROJECT, "location": CH.LOCATION,
                                "stage": "restore"})
        self.admin_ops.append({"job_id": "restore-1"})
        return {"status": "VERIFIED"}

    def admin_unresolved(self):
        return [op for op in self.admin_ops if not op.get("job_id")]

    def identity(self, graph_ids, receipt_jobs):
        """Reads every reference back through `self.owner`, exactly as `principal.roles_bound_to` does - which is what
        makes the post-close audit's channel (and its budget) observable."""
        self.identity_calls.append({"graph": list(graph_ids), "receipt": list(receipt_jobs),
                                    "admin": [j["job_id"] for j in self.admin_jobs]})
        emails, failed = {}, None
        refs = ([{"job_id": j} for j in graph_ids] + list(receipt_jobs)
                + [{"job_id": j["job_id"], "project": j.get("project"), "location": j.get("location")}
                   for j in self.admin_jobs])
        if self.owner is not None:
            try:
                for ref in refs:
                    emails[ref["job_id"]] = self.owner.get_job(
                        ref["job_id"], project=ref.get("project"), location=ref.get("location")).user_email
            except Exception as e:  # noqa: BLE001 - an unread reference is UNKNOWN, never assumed
                failed = f"{type(e).__name__}: {str(e)[:200]}"
        status = "UNKNOWN" if failed else (self.identity_after if self.torn_down else "BOUND")
        return {"status": status, "jobs": emails, "reason": failed,
                "roles": {"policy_admin": {"jobs": len(self.admin_jobs)}}}


def test_the_identity_inventory_is_rebuilt_after_the_deferred_restoration(sdk_root, tmp_path):
    """RR3 N4: the record still claimed the grant DDL was 'every job', while restoration submitted three more."""
    broker = _Broker()
    out = {"mode": "live", "run_id": "r1", "run_dir": str(tmp_path), "verdict": "CHAIN_CONNECTED",
           "requester": {"mode": "restricted-sa"},
           "identity": broker.identity(["g1"], [{"job_id": "r1"}]),
           "job_inventory": {"graph": ["g1"], "receipt": ["r1"], "receipt_refs": [{"job_id": "r1"}],
                             "policy_admin": ["grant-1"], "refs": {}}}
    broker.teardown()      # the restoration ran during close
    window = SimpleNamespace(cfg=SimpleNamespace(label="w"), state="CLOSED",
                             record={"clean": True, "cleanup": {"jobs_unresolved": []},
                                     "restores": [{"name": "broker_teardown", "ok": True,
                                                   "result": {"status": "VERIFIED"}}], "workers": []},
                             post_close_callbacks=lambda: [{"name": "broker_identity",
                                                            "call": lambda record: CH.rebuild_identity(broker, record)}])
    final = CH.finalize_cleanup(out, window, str(tmp_path))
    assert final["job_inventory"]["policy_admin"] == ["grant-1", "restore-1"]
    rebuilt = final["identity"]["rebuilt_after_restoration"]
    assert rebuilt["policy_admin_before_close"] == 1 and rebuilt["added_by_restoration"] == ["restore-1"]
    assert broker.identity_calls[-1]["admin"] == ["grant-1", "restore-1"]
    assert final["verdict"] == "CHAIN_CONNECTED"    # rebuilt and still BOUND


def test_a_restoration_job_with_an_unexpected_identity_breaks_the_chain(sdk_root, tmp_path):
    broker = _Broker(identity_after="UNBOUND")
    out = {"mode": "live", "run_id": "r1", "run_dir": str(tmp_path), "verdict": "CHAIN_CONNECTED",
           "requester": {"mode": "restricted-sa"}, "identity": {"status": "BOUND"},
           "job_inventory": {"graph": ["g1"], "receipt": ["r1"], "receipt_refs": [{"job_id": "r1"}],
                             "policy_admin": ["grant-1"], "refs": {}}}
    broker.teardown()
    window = SimpleNamespace(cfg=SimpleNamespace(label="w"), state="CLOSED",
                             record={"clean": True, "cleanup": {"jobs_unresolved": []}, "restores": [], "workers": []},
                             post_close_callbacks=lambda: [{"name": "broker_identity",
                                                            "call": lambda record: CH.rebuild_identity(broker, record)}])
    final = CH.finalize_cleanup(out, window, str(tmp_path))
    assert final["identity"]["status"] == "UNBOUND"
    assert final["verdict"] == "CHAIN_BROKEN" and final["broken_at"] == "identity"
    assert json.loads((tmp_path / "chain_live_restricted.json").read_text())["verdict"] == "CHAIN_BROKEN"


def test_an_unresolved_restoration_statement_leaves_the_chain_incomplete(sdk_root, tmp_path):
    broker = _Broker()
    broker.admin_ops.append({"statement": "DROP ROW ACCESS POLICY", "job_id": None})
    out = {"mode": "live", "run_id": "r1", "run_dir": str(tmp_path), "verdict": "CHAIN_CONNECTED",
           "requester": {"mode": "restricted-sa"}, "identity": {"status": "BOUND"},
           "job_inventory": {"graph": ["g1"], "receipt": ["r1"], "receipt_refs": [{"job_id": "r1"}],
                             "policy_admin": ["grant-1"], "refs": {}}}
    broker.teardown()
    window = SimpleNamespace(cfg=SimpleNamespace(label="w"), state="CLOSED",
                             record={"clean": True, "cleanup": {"jobs_unresolved": []}, "restores": [], "workers": []},
                             post_close_callbacks=lambda: [{"name": "broker_identity",
                                                            "call": lambda record: CH.rebuild_identity(broker, record)}])
    final = CH.finalize_cleanup(out, window, str(tmp_path))
    assert final["job_inventory"]["policy_admin_unresolved"]
    assert final["verdict"] == "CHAIN_INCOMPLETE" and final["broken_at"] == "identity"


def test_a_post_close_callback_that_raises_blocks_a_clean_closeout(sdk_root, tmp_path):
    out = {"mode": "live", "run_id": "r1", "run_dir": str(tmp_path), "verdict": "CHAIN_CONNECTED",
           "requester": {"mode": "same-requester"}, "job_inventory": {}}
    window = SimpleNamespace(cfg=SimpleNamespace(label="w"), state="CLOSED",
                             record={"clean": True, "cleanup": {"jobs_unresolved": []}, "restores": [], "workers": []},
                             post_close_callbacks=lambda: [{"name": "broker_identity",
                                                            "call": lambda record: (_ for _ in ()).throw(
                                                                RuntimeError("the audit could not be rebuilt"))}])
    final = CH.finalize_cleanup(out, window, str(tmp_path))
    assert final["post_close"]["broker_identity"]["status"] == "ERROR"
    assert final["verdict"] == "CHAIN_INCOMPLETE" and final["broken_at"] == "window_cleanup"


def test_the_restricted_chain_registers_the_identity_rebuild_with_the_teardown(sdk_root, tmp_path):
    """The two registrations are a pair: deferring the restoration is what makes the rebuild necessary."""
    registered = {"restores": [], "post_close": []}

    class Window(_StubWindow):
        def register_restore(self, name, restore, takes_client=False):
            registered["restores"].append(name)

        def register_post_close(self, name, callback):
            registered["post_close"].append(name)

    class Broker:
        def describe(self):
            return {"kind": "test"}

        def grant(self):
            raise RuntimeError("grant refused so the run stops right after registration")

        def teardown(self, owner=None):
            return {"status": "VERIFIED"}

    window = Window(journal=tmp_path / "jobs.json")
    broker = Broker()
    broker.sa = window.bind_client(object(), role="requester")
    broker.owner = window.bind_client(object(), role="operator")
    CH.run_chain(engine="gql", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), as_of=AS_OF,
                 requester_mode="restricted", broker=broker, window=window)
    assert registered == {"restores": ["broker_teardown"], "post_close": ["broker_identity"]}


def test_the_post_close_audit_is_bounded_and_expires_to_unknown(sdk_root, tmp_path):
    """RR5 F2: the rebuild's `jobs.get` must not outlive the window's closeout budget."""
    from okf_bq_graph import lifecycle as L

    broker = _Broker()
    broker.teardown()
    reads = []

    class Raw:
        def get_job(self, job_id, **kwargs):
            reads.append(dict(kwargs, job_id=job_id))
            return SimpleNamespace(user_email="operator@example.test")

    clock = [100.0]
    jobs = L.WindowJobs("w", 100.0, tmp_path / "jobs.json", clock=lambda: clock[0])
    deadline = jobs.open_audit(30)
    audit = jobs.audit_client(Raw())
    clock[0] = deadline + 1                    # the closeout budget is gone
    out = {"mode": "live", "run_id": "r1", "run_dir": str(tmp_path), "verdict": "CHAIN_CONNECTED",
           "requester": {"mode": "restricted-sa"}, "identity": {"status": "BOUND"},
           "job_inventory": {"graph": ["g1"], "receipt": ["r1"], "receipt_refs": [{"job_id": "r1"}],
                             "policy_admin": ["grant-1"], "refs": {}}}
    window = SimpleNamespace(cfg=SimpleNamespace(label="w"), state="CLOSED",
                             record={"clean": True, "cleanup": {"jobs_unresolved": []}, "restores": [], "workers": []},
                             post_close_callbacks=lambda: [{"name": "broker_identity",
                                                            "call": lambda record: CH.rebuild_identity(
                                                                broker, record, audit=audit)}])
    final = CH.finalize_cleanup(out, window, str(tmp_path))
    assert reads == [], "nothing may dispatch after the audit deadline"
    assert final["identity"]["status"] == "UNKNOWN"
    assert final["identity"]["audit"]["expired"] is True
    assert final["identity"]["audit"]["unread_references"]
    assert final["verdict"] == "CHAIN_INCOMPLETE" and final["broken_at"] == "identity"


def test_the_post_close_audit_reads_everything_inside_its_budget(sdk_root, tmp_path):
    from okf_bq_graph import lifecycle as L

    broker = _Broker()
    broker.teardown()
    reads = []

    class Raw:
        def get_job(self, job_id, **kwargs):
            reads.append(dict(kwargs, job_id=job_id))
            return SimpleNamespace(user_email="operator@example.test")

    jobs = L.WindowJobs("w", time.monotonic() + 600, tmp_path / "jobs.json")
    jobs.open_audit(60)
    audit = jobs.audit_client(Raw())
    out = {"mode": "live", "run_id": "r1", "run_dir": str(tmp_path), "verdict": "CHAIN_CONNECTED",
           "requester": {"mode": "restricted-sa"}, "identity": {"status": "BOUND"},
           "job_inventory": {"graph": [], "receipt": [], "receipt_refs": [],
                             "policy_admin": ["grant-1"], "refs": {}}}
    window = SimpleNamespace(cfg=SimpleNamespace(label="w"), state="CLOSED",
                             record={"clean": True, "cleanup": {"jobs_unresolved": []}, "restores": [], "workers": []},
                             post_close_callbacks=lambda: [{"name": "broker_identity",
                                                            "call": lambda record: CH.rebuild_identity(
                                                                broker, record, audit=audit)}])
    final = CH.finalize_cleanup(out, window, str(tmp_path))
    assert [r["job_id"] for r in reads] == ["grant-1", "restore-1"]
    assert all(0 < r["timeout"] <= 10 for r in reads)        # bounded, not the SDK's 128-second default
    assert final["identity"]["audit"]["expired"] is False
    assert final["identity"]["audit"]["unread_references"] == []
    assert final["verdict"] == "CHAIN_CONNECTED"


def test_the_audit_client_is_restored_to_the_brokers_own_owner(sdk_root, tmp_path):
    """The audit swap is scoped: the broker keeps its own client afterwards."""
    from okf_bq_graph import lifecycle as L

    broker = _Broker()
    broker.owner = object()
    original = broker.owner
    jobs = L.WindowJobs("w", time.monotonic() + 600, tmp_path / "jobs.json")
    jobs.open_audit(60)
    audit = jobs.audit_client(SimpleNamespace(get_job=lambda job_id, **kw: SimpleNamespace(user_email="e")))
    CH.rebuild_identity(broker, {"job_inventory": {"graph": [], "receipt": [], "policy_admin": [], "refs": {}}},
                        audit=audit)
    assert broker.owner is original


def test_the_receipt_child_registration_carries_its_journal_location(sdk_root, tmp_path, monkeypatch):
    """RR5 F1: recovery needs to know WHERE the child's retained references live."""
    from okf_bq_graph import receipt_window as RWD

    window = _StubWindow(journal=tmp_path / "jobs.json")
    bridge = RWD.ReceiptBridge(sdk_root, label="chain-gql-1", deadline_epoch=time.time() + 300,
                               directory=tmp_path / "bridge")
    bridge.record["status"] = RWD.SUPPORTED
    monkeypatch.setattr(CH, "resolve_pointer_job", lambda *a, **k: (None, "pointer-job"))
    CH.run_chain(engine="gql", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), as_of=AS_OF,
                 clients={"engine": "gql", "bq": window.bind_client(object(), role="requester")},
                 window=window, receipt_bridge=bridge)
    evidence = next(w for w in window.workers if w["name"] == "receipt_child")["evidence"]
    assert evidence["journal_dir"] == str(bridge.journal_dir)
    assert evidence["bridge_dir"] == str(bridge.dir) and evidence["stop_file"] == str(bridge.stop_path)


def test_a_late_audit_read_leaves_the_reference_unknown_and_the_chain_incomplete(sdk_root, tmp_path):
    """RR6: the last reference's identity arrived after the absolute budget; accepting it kept the chain BOUND."""
    from okf_bq_graph import lifecycle as L

    broker = _Broker()
    broker.teardown()
    clock = [100.0]
    reads = []

    class Delegating:
        """Dispatches through a transport the audit client cannot reach, so only the return check can catch it."""

        def get_job(self, job_id, **kwargs):
            reads.append(job_id)
            if job_id == "restore-1":            # the final reference returns just past the deadline
                clock[0] = deadline + 0.1
            return SimpleNamespace(user_email="operator@example.test")

    jobs = L.WindowJobs("w", 100.0, tmp_path / "jobs.json", clock=lambda: clock[0])
    deadline = jobs.open_audit(30)
    audit = jobs.audit_client(Delegating())
    out = {"mode": "live", "run_id": "r1", "run_dir": str(tmp_path), "verdict": "CHAIN_CONNECTED",
           "requester": {"mode": "restricted-sa"}, "identity": {"status": "BOUND"},
           "job_inventory": {"graph": [], "receipt": [], "receipt_refs": [],
                             "policy_admin": ["grant-1"], "refs": {}}}
    window = SimpleNamespace(cfg=SimpleNamespace(label="w"), state="CLOSED",
                             record={"clean": True, "cleanup": {"jobs_unresolved": []}, "restores": [], "workers": []},
                             post_close_callbacks=lambda: [{"name": "broker_identity",
                                                            "call": lambda record: CH.rebuild_identity(
                                                                broker, record, audit=audit)}])
    final = CH.finalize_cleanup(out, window, str(tmp_path))
    assert reads == ["grant-1", "restore-1"]
    assert final["identity"]["audit"]["expired"] is True
    assert final["identity"]["audit"]["unread_references"] == ["restore-1"]
    assert final["identity"]["status"] == "UNKNOWN"
    assert final["verdict"] == "CHAIN_INCOMPLETE" and final["broken_at"] == "identity"
    assert json.loads((tmp_path / "chain_live_restricted.json").read_text())["verdict"] == "CHAIN_INCOMPLETE"


# ----------------------------------------------------------------------------- receipt containment (2026-09-08 RC)
def _cont_receipt():
    """A receipt record that is perfect in every respect except the containment of the process that produced it."""
    return {"invoked": True, "exit_code": 0, "released": True,
            "stdout": f"{CH.VERIFIED} gross margin released\n",
            "receipt": {"verdict": CH.VERIFIED, "execution_match": "MATCH", "computation_digest": "dig",
                        "publication_id": "pub", "context_ref": "ctx"},
            "output": {"verdict": CH.VERIFIED, "execution_match": "MATCH", "reason_codes": []}}


def _cont_bound():
    return {"status": "BOUND", "computation_digest": "dig", "sdk_publication_id": "pub", "sdk_context_ref": "ctx"}


def test_a_contained_receipt_still_releases():
    """The happy path must keep working: containment that HOLDS changes nothing."""
    contained = {"contained": True, "launches": [{"invocation": "w-001", "bridge_installed": True}], "uncontained": []}
    assert CH.consume(_cont_bound(), _cont_receipt(), containment=contained)["decision"] == "RELEASED"
    assert CH.consume(_cont_bound(), _cont_receipt())["decision"] == "RELEASED"   # no bridge: unchanged behaviour


def test_an_uncontained_child_is_refused_before_the_number_is_released():
    """2026-09-08 attempt 4 released a VERIFIED receipt whose child had no deadline, no admission bound and no
    journal, and only the closeout noticed. The consumer must refuse it at decision time instead."""
    uncontained = {"contained": False, "uncontained": [{"invocation": "w-001", "bridge_installed": False}],
                   "reason": "no bridge_installed record for w-001. Its submissions were neither bounded nor inventoried"}
    d = CH.consume(_cont_bound(), _cont_receipt(), containment=uncontained)
    assert d["decision"] == "REFUSED"
    assert any("containment failed" in r for r in d["reasons"])
    assert "display" not in d, "no released figure may be carried on a refusal"


def test_an_uncontained_approved_case_is_not_reached_rather_than_wrong():
    """A containment outage is unproven, not a contradiction: the case never ran under the guarantees it exists to
    demonstrate, so it must not be scored as the product misbehaving."""
    c = {"case": "approved", "retrieval": {"status": "OK", "reached": True}, "declaration": {"status": "OK"},
         "bind": _cont_bound(),
         "receipt": dict(_cont_receipt(), diag_present=True,
                         containment={"contained": False, "reason": "no bridge_installed record for w-001"}),
         "consume": {"decision": "REFUSED", "reasons": ["receipt containment failed: no bridge_installed record"]}}
    a = CH.accept(c)
    # NOT_REACHED, not WRONG: `_verdict` carries the reasons either way, so the distinction lives in the status
    assert a["status"] == "NOT_REACHED", "an uncontained run is not evidence the product did the wrong thing"
    assert any("uncontained" in r for r in a["failed"])
