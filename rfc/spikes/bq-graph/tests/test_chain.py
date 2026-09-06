"""Connected chain (chain.py): fixture seed -> pinned publication -> governed retrieval -> Attested Computation
declaration + SQL -> SDK receipt CLI (subprocess) -> verifier verdict -> consumer. Hermetic: oracle engine for the
graph leg, the SDK example's own SYNTHETIC API emulation for the receipt leg. Live KC discovery is out of scope.
Tests that need the pinned Acme checkout or the SDK checkout skip when either is absent."""
import json
import os
import subprocess
import sys

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
    assert (tmp_path / "receipt" / "case_approved_hermetic.json").exists()


def test_chain_stops_before_execution_when_retrieval_is_denied(sdk_root, tmp_path, monkeypatch):
    calls = []

    def runner(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    denied = lambda *a, **k: {"status": "DENIED", "concepts": [], "paths": [], "computations": [], "warnings": ["x"],
                              "scope": {"publication_id": "p"}, "timing": {"jobs": []}}
    monkeypatch.setattr(CH, "governed", denied)
    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), clients={"engine": "oracle"},
                       projection={"publication_id": "p", "nodes": []}, requester="t", as_of=AS_OF, runner=runner)
    assert out["verdict"] == "CHAIN_BROKEN" and calls == []
    assert all(c["consume"]["decision"] == "REFUSED" for c in out["cases"])


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
    assert seen["argv"][seen["argv"].index("--evidence-dir") + 1] == str((tmp_path / "rel" / "receipt").resolve())


def test_live_pointer_lookup_uses_the_default_dataset_when_clients_omit_ds(sdk_root, tmp_path, monkeypatch):
    import okf_bq_graph.publish as PUB
    from okf_bq_graph import DATASET
    seen = {}

    def fake_resolve(client, bundle_id, ds=DATASET):
        seen["ds"] = ds
        return None

    monkeypatch.setattr(PUB, "resolve_pointer", fake_resolve)
    out = CH.run_chain(engine="fallback", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), clients={"engine": "fallback", "bq": object()},
                       requester="t", as_of=AS_OF, runner=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    assert seen["ds"] == DATASET and out["verdict"] == "CHAIN_BROKEN" and out["broken_at"] == "publication"
