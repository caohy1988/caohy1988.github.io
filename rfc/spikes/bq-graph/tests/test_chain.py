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

    def query(self, q, job_config=None, location=None, job_id=None, project=None):
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
