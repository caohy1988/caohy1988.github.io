"""Connected chain (chain.py): fixture seed -> pinned publication -> governed retrieval -> Attested Computation
declaration + SQL -> SDK receipt CLI (subprocess) -> verifier verdict -> consumer. Hermetic: oracle engine for the
graph leg, the SDK example's own SYNTHETIC API emulation for the receipt leg. Live KC discovery is out of scope.
Tests that need the pinned Acme checkout or the SDK checkout skip when either is absent."""
import json
import os
import subprocess
import sys
from pathlib import Path

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
