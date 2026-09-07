"""Restricted-requester chain (chain.py --requester restricted, 2026-09-06 Slice A, hermetic): the policy-emulating
broker, the oracle cached-replay path, the pre-execution authorization stage, the four cases' stage-reachability
acceptance, the end-to-end hermetic run and its evidence hygiene, and the live broker's wiring against fakes (no
cloud: the live pass is Slice B). Tests that need the pinned Acme checkout or the SDK checkout skip when absent."""
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import okf_bq_graph.chain as CH
import okf_bq_graph.principal as PR
import okf_bq_graph.retrieve as RT
from okf_bq_graph import DATASET, SOURCE_PIN
import okf_bq_graph.authz as AZ
from okf_bq_graph.authz import HIDDEN, SA_ALIAS, RLS_DS
from okf_bq_graph.compile import compile_bundle
from okf_bq_graph.oracle import Graph

AS_OF = "2026-09-06T00:00:00Z"
SA = "okf-receipt-restricted@test-project-0728-467323.iam.gserviceaccount.com"
DEPS = ["p.d.orders", "p.d.order_lines"]


@pytest.fixture(scope="module")
def sdk_root():
    root = CH.sdk_root()
    if not os.path.isfile(os.path.join(root, CH.EXAMPLE_REL, "run.py")):
        pytest.skip("SDK receipt spike checkout not present")
    return root


@pytest.fixture(scope="module")
def projection(sample_root):
    return compile_bundle(sample_root, "acme_retail", SOURCE_PIN)


# ---- policy emulation over the projection
def test_filtered_projection_drops_hidden_rows_sections_and_touching_edges(projection):
    f = PR.filtered_projection(projection, (HIDDEN,))
    gone = {n["node_id"] for n in projection["nodes"]} - {n["node_id"] for n in f["nodes"]}
    assert gone and all(n["local_id"] == HIDDEN or n["local_id"].startswith(HIDDEN + "#") for n in projection["nodes"] if n["node_id"] in gone)
    assert not any(e["src_id"] in gone or e["dst_id"] in gone for e in f["edges"])
    assert any(n["local_id"] == "metrics/gross-margin-legacy" for n in f["nodes"])      # only the hidden concept goes, not its neighbours
    assert PR.filtered_projection(projection, ()) is projection


def test_policy_graph_follows_the_current_policy(projection):
    state = dict(PR.policy())
    g = PR.PolicyGraph(projection, state)
    assert g.governed("metrics/gross-margin-legacy", AS_OF)["paths"] == [{"concept_hops": 2, "via": ["metrics/gross-margin-legacy", HIDDEN, "computations/gross-margin-period"]}]
    state["hidden"] = (HIDDEN,)
    r = g.governed("metrics/gross-margin-legacy", AS_OF)
    assert r["status"] == "OK" and r["paths"] == [] and r["computations"] == [] and not any(HIDDEN in json.dumps(x) for x in (r["paths"], r["replacement"]))
    assert g.visible(["metrics/gross-margin-legacy"]) and not g.visible([HIDDEN])
    state["dataset_reader"] = False
    assert g.governed("metrics/gross-margin", AS_OF)["status"] == "DENIED" and not g.visible(["metrics/gross-margin"])


def test_oracle_cached_replay_rechecks_visibility_and_denies_after_revocation(projection):
    state = dict(PR.policy())
    clients = {"engine": "oracle", "graph": PR.PolicyGraph(projection, state), "projection": projection, "cache": {}}
    warm = RT.retrieve(CH.SEED, "acme_retail", projection["publication_id"], SA_ALIAS, AS_OF, clients)
    assert warm["status"] == "OK" and warm["scope"]["cache"] == "MISS_STORED" and len(warm["computations"]) == 1
    hit = RT.retrieve(CH.SEED, "acme_retail", projection["publication_id"], SA_ALIAS, AS_OF, clients)
    assert hit["scope"]["cache"] == "HIT_RECHECKED" and hit["computations"] == warm["computations"]
    state["hidden"] = ("computations/gross-margin-period",)                               # row-level revocation of a disclosed node
    replay = RT.retrieve(CH.SEED, "acme_retail", projection["publication_id"], SA_ALIAS, AS_OF, clients)
    assert replay["status"] == "DENIED" and replay["scope"]["cache"] == "HIT_DENIED" and replay["computations"] == [] and replay["concepts"] == []
    state["hidden"] = (); state["dataset_reader"] = False                                 # dataset grant revoked
    replay2 = RT.retrieve(CH.SEED, "acme_retail", projection["publication_id"], SA_ALIAS, AS_OF, clients)
    assert replay2["scope"]["cache"] == "HIT_DENIED"
    fresh = RT.retrieve(CH.SEED, "acme_retail", projection["publication_id"], "other-requester", AS_OF, clients)   # different key: not a replay
    assert fresh["status"] == "DENIED" and "cache" not in fresh["scope"]


def test_oracle_cached_replay_rechecks_authorizing_edges_too(projection):   # Opus P1: the BigQuery `_recheck` contract, nodes AND edges
    comp = next(n["node_id"] for n in projection["nodes"] if n["local_id"] == "computations/gross-margin-period" and n["kind"] == "Concept")
    edge_revoked = dict(projection, edges=[e for e in projection["edges"] if not (e["dst_id"] == comp and e["relation"] == "LINKS_TO")])   # nodes untouched
    clients = {"engine": "oracle", "graph": Graph(projection), "projection": projection, "cache": {}}
    first = RT.retrieve(CH.SEED, "acme_retail", projection["publication_id"], "r", AS_OF, clients)
    assert first["scope"]["cache"] == "MISS_STORED" and first["computations"] and "edge_ids" not in first["computations"][0]
    entry = next(iter(clients["cache"].values()))
    assert entry["dependency_version"] == RT.CACHE_DEPENDENCY_VERSION and len(entry["disclosed_edge_ids"]) == 1 and entry["disclosed_edge_ids"][0].startswith("acme_retail|")
    clients["graph"] = Graph(edge_revoked)
    fresh = RT.retrieve(CH.SEED, "acme_retail", projection["publication_id"], "other", AS_OF, clients)
    assert fresh["status"] == "OK" and fresh["paths"] == [] and fresh["computations"] == []                      # a fresh request discloses nothing ...
    replay = RT.retrieve(CH.SEED, "acme_retail", projection["publication_id"], "r", AS_OF, clients)
    assert replay["status"] == "DENIED" and replay["scope"]["cache"] == "HIT_DENIED" and replay["computations"] == []   # ... and neither does the replay
    clients["graph"] = Graph(projection)
    assert RT.retrieve(CH.SEED, "acme_retail", projection["publication_id"], "r", AS_OF, clients)["scope"]["cache"] == "HIT_RECHECKED"
    entry["dependency_version"] = 1                                                                             # a legacy entry is rerun, never rechecked partially
    assert RT.retrieve(CH.SEED, "acme_retail", projection["publication_id"], "r", AS_OF, clients)["scope"]["cache"] == "MISS_STORED"
    unpinned = RT.retrieve(CH.SEED, "acme_retail", "active", "r", AS_OF, clients)                               # an unpinned publication is never cached
    assert "cache" not in unpinned["scope"]


def test_job_ids_of_includes_the_cached_replay_recheck_job():   # Astra P2 #2
    case = {"case": "revocation-before-replay", "retrieval": {"timing": {"jobs": [{"job_id": "w1"}]}}, "declaration": {"job_id": "d1"},
            "receipt": {"invoked": True, "receipt": {"job": {"job_id": "r1"}}},
            "replay": {"retrieval": {"status": "DENIED", "cache": "HIT_DENIED", "timing": {"jobs": [{"stage": "recheck", "job_id": "rc1"}]}}}}
    ids = CH.job_ids_of([case], "pointer-job")
    assert ids["graph"] == ["pointer-job", "w1", "d1", "rc1"] and [j["job_id"] for j in ids["receipt"]] == ["r1"]
    owner = _Owner({"pointer-job": SA, "w1": SA, "d1": SA, "r1": SA, "rc1": "operator@x"})
    assert PR.bound_to(owner, ids["graph"], ids["receipt"], SA)["status"] == "UNBOUND"      # a replay job under another principal breaks the claim
    assert PR.bound_to(owner, ids["graph"][:-1], ids["receipt"], SA)["status"] == "BOUND"    # the old set would have missed it


def test_oracle_without_a_cache_is_unchanged(projection):
    clients = {"engine": "oracle", "graph": Graph(projection), "projection": projection}
    r = RT.retrieve(CH.SEED, "acme_retail", projection["publication_id"], "t", AS_OF, clients)
    assert r["status"] == "OK" and "cache" not in r["scope"]


def test_plain_graph_with_a_cache_rechecks_by_visibility(projection):
    clients = {"engine": "oracle", "graph": Graph(projection), "projection": projection, "cache": {}}
    RT.retrieve(CH.SEED, "acme_retail", projection["publication_id"], "t", AS_OF, clients)
    assert RT.retrieve(CH.SEED, "acme_retail", projection["publication_id"], "t", AS_OF, clients)["scope"]["cache"] == "HIT_RECHECKED"


# ---- hermetic broker
def test_hermetic_broker_authorize_and_transitions(projection):
    b = PR.HermeticBroker(projection, sa_email=SA)
    assert b.describe()["iam"] is False and SA not in json.dumps(b.describe()) and b.describe()["principal"] == SA_ALIAS
    a0 = b.authorize(DEPS)
    assert a0["status"] == "ALLOWED" and a0["denied"] == 0 and [t["status"] for t in a0["tables"]] == ["ALLOWED", "ALLOWED"]
    b.apply(PR.policy(sdk_tables=False))
    a = b.authorize(DEPS)
    assert a["status"] == "DENIED" and a["denied"] == 2 and all(t["status"] == "DENIED" for t in a["tables"])
    assert b.authorize([])["status"] == "UNKNOWN"                                              # nothing probed is not ALLOWED
    b.grant(); b.revoke()
    assert b.state["dataset_reader"] is False and b.state["sdk_tables"] is False
    assert [j["event"] for j in b.journal] == ["apply", "apply", "revoke"] and all(j["observed"] for j in b.journal)
    assert b.graph_clients()["cache"] == {} and b.graph_clients()["cache"] is not b.graph_clients()["cache"]
    assert b.receipt_env() == {} and b.receipt_launches == 1
    assert b.identity(["g"], [{"job_id": "r"}])["status"] == "NOT_APPLICABLE" and b.teardown()["status"] == "NOT_NEEDED"


# ---- consumer re-checks authorization at decision time
def _bound(digest="d" * 64):
    return {"status": "BOUND", "computation_digest": digest, "sdk_publication_id": "pub-x", "sdk_context_ref": "ctx-x", "checks": {}}


def _receipt():
    return {"invoked": True, "exit_code": 0, "stdout": "[HERMETIC] Gross margin: $400.00 USD · VERIFIED\n",
            "receipt": {"verdict": "VERIFIED", "execution_match": "MATCH", "computation_digest": "d" * 64, "publication_id": "pub-x", "context_ref": "ctx-x"},
            "output": {"verdict": "VERIFIED", "execution_match": "MATCH", "reason_codes": []}, "released": True}


def test_consumer_refuses_a_verified_receipt_when_authorization_is_not_allowed():
    assert CH.consume(_bound(), _receipt(), {"status": "ALLOWED"})["decision"] == "RELEASED"
    for st in ("DENIED", "UNKNOWN", None):
        c = CH.consume(_bound(), _receipt(), {"status": st, "denied": 3})
        assert c["decision"] == "REFUSED" and any("authorization" in r for r in c["reasons"]), c
    assert CH.consume(_bound(), _receipt())["decision"] == "RELEASED"                      # operator chain: unchanged contract


# ---- acceptance: refusal alone never counts
def _rc(case, **kw):
    base = {"case": case, "hidden": [HIDDEN] if case == "denied-intermediate" else [],
            "retrieval": {"status": "OK", "reached": True, "paths": [{"via": ["a", "b"]}], "computations": [CH.COMPUTATION_PATH], "hidden_id_in_full_result": []},
            "declaration": {"status": "OK"}, "bind": {"status": "BOUND", "checks": {}},
            "authorization": {"status": "ALLOWED", "denied": 0},
            "receipt": {"invoked": True, "exit_code": 0, "diag_present": True, "receipt": {"verdict": "VERIFIED"}, "output": {"verdict": "VERIFIED"}, "released": True},
            "receipt_invocations": 1, "consume": {"decision": "RELEASED", "reasons": []}}
    base.update(kw)
    return base


def test_accept_approved_restricted():
    assert CH.accept(_rc("approved-restricted"))["status"] == "MET"
    assert CH.accept(_rc("approved-restricted", consume={"decision": "REFUSED", "reasons": ["x"]}))["status"] == "WRONG"
    a = CH.accept(_rc("approved-restricted", authorization={"status": "DENIED", "denied": 7}, receipt={"invoked": False}, consume={"decision": "REFUSED", "reasons": []}))
    assert a["status"] == "NOT_REACHED" and any("grant not effective" in f for f in a["failed"])    # refused, but nothing executed
    a = CH.accept(_rc("approved-restricted", retrieval={"status": "DENIED", "reached": False}, bind={"status": "NOT_REACHED"}, receipt={"invoked": False}, consume={"decision": "REFUSED", "reasons": []}))
    assert a["status"] == "NOT_REACHED"
    assert CH.accept(_rc("approved-restricted", bind={"status": "MISMATCH", "checks": {}}, receipt={"invoked": False}, consume={"decision": "REFUSED", "reasons": []}))["status"] == "WRONG"


def _denied_case(**kw):
    c = _rc("denied-intermediate", retrieval={"status": "OK", "reached": False, "paths": [], "computations": [], "concepts": ["metrics/gross-margin-legacy"], "hidden_id_in_full_result": []},
            declaration=None, bind={"status": "NOT_REACHED", "reason": "retrieval_denied"}, authorization={"status": "NOT_RUN"},
            receipt={"invoked": False}, receipt_invocations=0, consume={"decision": "REFUSED", "reasons": ["bind"]})
    c.update(kw)
    return c


def test_accept_denied_intermediate_needs_visible_seed_no_path_and_no_leak():
    assert CH.accept(_denied_case())["status"] == "MET"
    a = CH.accept(_denied_case(retrieval={"status": "DENIED", "reached": False, "paths": [], "computations": [], "hidden_id_in_full_result": []}))
    assert a["status"] == "NOT_REACHED" and "outage" in a["failed"][0]                       # seed not visible: enforcement vs outage unknown
    a = CH.accept(_denied_case(retrieval={"status": "OK", "reached": True, "paths": [{"via": ["x", HIDDEN, "y"]}], "computations": [CH.COMPUTATION_PATH], "hidden_id_in_full_result": [HIDDEN]}))
    assert a["status"] == "WRONG" and any("traversed" in f for f in a["failed"]) and any("disclosure surface" in f for f in a["failed"])
    a = CH.accept(_denied_case(retrieval={"status": "OK", "reached": False, "paths": [], "computations": [], "warnings": [f"path via {HIDDEN} removed"], "hidden_id_in_full_result": []}))
    assert a["status"] == "WRONG" and any("disclosure surface" in f for f in a["failed"])     # the explain leaks the id
    a = CH.accept(_denied_case(retrieval={"status": "OK", "reached": False, "paths": [], "computations": [], "hidden_id_in_full_result": [HIDDEN]}))
    assert a["status"] == "WRONG" and any("full retrieval result" in f for f in a["failed"])
    assert CH.accept(_denied_case(receipt={"invoked": True, "exit_code": 0}))["status"] == "WRONG"
    assert CH.accept(_denied_case(consume={"decision": "RELEASED", "reasons": []}))["status"] == "WRONG"
    assert CH.accept(_denied_case(bind={"status": "NOT_BOUND", "reason": "other"}))["status"] == "WRONG"
    # the harness's own policy record names the hidden id by design: not a leak
    assert CH.accept(_denied_case(policy={"hidden": [HIDDEN]}, grant={"policy": {"hidden": [HIDDEN]}}, attack=f"hides {HIDDEN}"))["status"] == "MET"


def test_accept_unauthorized_output_needs_a_platform_denial_before_execution():
    ok = _rc("unauthorized-output", authorization={"status": "DENIED", "denied": 7}, receipt={"invoked": False}, receipt_invocations=0,
             consume={"decision": "REFUSED", "reasons": ["authorization DENIED at decision time"]})
    assert CH.accept(ok)["status"] == "MET"
    assert CH.accept(dict(ok, authorization={"status": "ALLOWED", "denied": 0}))["status"] == "WRONG"                    # not enforced
    assert CH.accept(dict(ok, authorization={"status": "UNKNOWN"}))["status"] == "NOT_REACHED"                          # probe did not decide
    assert CH.accept(dict(ok, authorization={"status": "DENIED", "denied": 0}))["status"] == "WRONG"
    assert CH.accept(dict(ok, receipt={"invoked": True, "exit_code": 2, "diag_present": True}))["status"] == "WRONG"
    assert CH.accept(dict(ok, consume={"decision": "REFUSED", "reasons": ["bind status"]}))["status"] == "WRONG"        # refused for another reason
    assert CH.accept(dict(ok, consume={"decision": "RELEASED", "reasons": []}))["status"] == "WRONG"
    assert CH.accept(dict(ok, retrieval={"status": "OK", "reached": False}, bind={"status": "NOT_REACHED"}))["status"] == "NOT_REACHED"


def _replay_case(**kw):
    c = _rc("revocation-before-replay",
            first_pass={"decision": "RELEASED", "reasons": [], "cache": "MISS_STORED"}, revocation={"observed": True},
            replay={"retrieval": {"status": "DENIED", "cache": "HIT_DENIED", "paths": [], "computations": [], "concepts": [], "disclosed_anything": False},
                    "authorization": {"status": "DENIED", "denied": 7}, "consume": {"decision": "REFUSED", "reasons": ["authorization DENIED"]}},
            consume={"decision": "REFUSED", "reasons": ["authorization DENIED"]})
    c.update(kw)
    return c


def test_accept_revocation_before_replay():
    assert CH.accept(_replay_case())["status"] == "MET"
    a = CH.accept(_replay_case(first_pass={"decision": "REFUSED", "reasons": ["x"]}))
    assert a["status"] == "NOT_REACHED" and any("first pass" in f for f in a["failed"])
    assert CH.accept(_replay_case(revocation={"observed": False}))["status"] == "NOT_REACHED"
    rp = _replay_case()["replay"]
    assert CH.accept(_replay_case(replay=dict(rp, retrieval=dict(rp["retrieval"], status="OK", cache="HIT_RECHECKED", disclosed_anything=True))))["status"] == "WRONG"
    a = CH.accept(_replay_case(replay=dict(rp, retrieval=dict(rp["retrieval"], cache="MISS_STORED"))))
    assert a["status"] == "NOT_REACHED" and any("cached-replay path" in f for f in a["failed"])    # denied, but not from cache
    assert CH.accept(_replay_case(replay=dict(rp, authorization={"status": "ALLOWED"})))["status"] == "WRONG"
    assert CH.accept(_replay_case(replay=dict(rp, authorization={"status": "UNKNOWN"})))["status"] == "NOT_REACHED"
    assert CH.accept(_replay_case(replay=dict(rp, consume={"decision": "RELEASED", "reasons": []}), consume={"decision": "RELEASED", "reasons": []}))["status"] == "WRONG"
    assert CH.accept(_replay_case(receipt_invocations=2))["status"] == "WRONG"


# ---- whole chain, hermetic
@pytest.fixture(scope="module")
def restricted_run(projection, sdk_root, tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("rc")
    launches = []

    def runner(argv, **kw):
        launches.append((argv, kw.get("env", {}).get("GOOGLE_APPLICATION_CREDENTIALS")))
        return subprocess.run(argv, **kw)

    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(out_dir), projection=projection, as_of=AS_OF,
                       requester_mode="restricted", runner=runner)
    return out, out_dir, launches


def test_restricted_chain_hermetic_end_to_end(restricted_run):
    out, out_dir, launches = restricted_run
    assert out["verdict"] == "CHAIN_CONNECTED" and out["chain"] == "okf_bq_graph.chain/0.5.0"
    assert out["requester"]["mode"] == "restricted-sa" and out["requester"]["principal"] == SA_ALIAS and out["requester"]["broker"]["iam"] is False
    assert out["seed"]["mode"] == "fixture" and out["engine"] == "oracle" and out["mode"] == "hermetic"
    assert out["acceptance"] == {c: "MET" for c in CH.RESTRICTED_CASES}
    assert out["decisions"] == {"approved-restricted": "RELEASED", "denied-intermediate": "REFUSED", "unauthorized-output": "REFUSED", "revocation-before-replay": "REFUSED"}
    assert out["identity"]["status"] == "NOT_APPLICABLE" and out["same_requester"]["status"] == "NOT_APPLICABLE"
    assert out["teardown"]["status"] == "NOT_NEEDED" and out["grant"]["event"] == "apply"
    assert len(launches) == 2 and all(cred is None for _, cred in launches)        # approved-restricted + the replay case's first pass, hermetic env
    assert out["receipt_launches"] == {"chain_counted": 2, "broker_counted": 2} and "synthetic" in out["identity"]["job_set"]["note"]
    assert [j["event"] for j in out["broker_journal"]] == ["apply", "apply", "apply", "apply", "apply", "revoke"]


def test_restricted_cases_reach_their_stages(restricted_run):
    out, _, _ = restricted_run
    cases = {c["case"]: c for c in out["cases"]}
    ap = cases["approved-restricted"]
    assert ap["bind"]["status"] == "BOUND" and ap["authorization"]["status"] == "ALLOWED" and ap["receipt"]["exit_code"] == 0 and ap["consume"]["decision"] == "RELEASED"
    di = cases["denied-intermediate"]
    assert di["retrieval"]["status"] == "OK" and di["retrieval"]["reached"] is False and di["retrieval"]["concepts"] == ["metrics/gross-margin-legacy"]
    assert di["retrieval"]["paths"] == [] and di["retrieval"]["computations"] == [] and di["retrieval"]["hidden_id_in_full_result"] == []
    assert di["bind"] == {"status": "NOT_REACHED", "reason": "retrieval_denied", "detail": di["bind"]["detail"]} and di["receipt"]["invoked"] is False
    assert not AZ.leaks({k: di[k] for k in CH.DISCLOSURE_SURFACE if k in di}, HIDDEN)   # exact id: the legacy seed name is not a leak
    uo = cases["unauthorized-output"]
    assert uo["bind"]["status"] == "BOUND" and uo["authorization"]["status"] == "DENIED" and uo["authorization"]["denied"] == 7
    assert uo["receipt"]["invoked"] is False and any("authorization DENIED" in r for r in uo["consume"]["reasons"])
    rv = cases["revocation-before-replay"]
    assert rv["first_pass"]["decision"] == "RELEASED" and rv["first_pass"]["cache"] == "MISS_STORED" and rv["receipt_invocations"] == 1
    assert rv["revocation"]["observed"] is True and rv["revocation"]["policy"]["dataset_reader"] is False
    assert rv["replay"]["retrieval"]["status"] == "DENIED" and rv["replay"]["retrieval"]["cache"] == "HIT_DENIED" and rv["replay"]["retrieval"]["disclosed_anything"] is False
    assert rv["replay"]["authorization"]["status"] == "DENIED" and rv["replay"]["consume"]["decision"] == "REFUSED" and rv["consume"]["decision"] == "REFUSED"
    assert "timing" in rv["replay"]["retrieval"] and out["identity"]["job_set"]["replay_jobs_included"] is True


def test_restricted_evidence_is_hygienic_and_retained(restricted_run):
    out, out_dir, _ = restricted_run
    written = json.loads((out_dir / "chain_hermetic_restricted.json").read_text())
    text = json.dumps(written)
    assert SA not in text and "operator@example.test" not in text and SA_ALIAS in text and not re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", text)
    assert written["run_id"] == out["run_id"] and (out_dir / "receipt" / out["run_id"] / "chain_hermetic_restricted.json").exists()
    assert not (out_dir / "chain_hermetic.json").exists()                                    # the operator record is a different file
    retained = []
    for c in written["cases"]:
        if c["receipt"].get("invoked"):
            dp = Path(c["receipt"]["diag_path"])
            retained.append(dp)
            assert dp.parent == out_dir / "receipt" / out["run_id"] and dp.name == f"case_{c['case']}_hermetic.json"
            assert json.loads(dp.read_text())["request_id"] == c["receipt"]["request_id"] and CH.sha256_hex(dp.read_bytes()) == c["receipt"]["diag_sha256"]
    assert len(retained) == 2 and len(set(retained)) == 2       # two chain cases ran the SDK's `approved`: two retained files, never one overwriting the other


def test_restricted_chain_is_incomplete_when_a_grant_is_not_effective(projection, sdk_root, tmp_path):
    class Broken(PR.HermeticBroker):
        def authorize(self, deps):
            return dict(super().authorize(deps), status="DENIED", denied=len(deps))     # nothing is ever allowed: grants never took

    calls = []
    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), projection=projection, as_of=AS_OF,
                       requester_mode="restricted", broker=Broken(projection), runner=lambda argv, **k: calls.append(argv))
    assert calls == [] and out["verdict"] == "CHAIN_INCOMPLETE" and out["broken_at"] == "approved-restricted"
    assert out["acceptance"]["approved-restricted"] == "NOT_REACHED" and out["acceptance"]["unauthorized-output"] == "MET"
    assert out["acceptance"]["revocation-before-replay"] == "NOT_REACHED"                  # never released, so nothing was revoked from


def test_restricted_chain_is_broken_when_the_policy_is_not_enforced(projection, sdk_root, tmp_path):
    class Leaky(PR.HermeticBroker):
        def graph_clients(self):
            return {"engine": "oracle", "graph": Graph(self.projection), "projection": self.projection, "cache": {}}   # ignores hidden rows

    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), projection=projection, as_of=AS_OF,
                       requester_mode="restricted", broker=Leaky(projection), cases=("denied-intermediate",))
    di = out["cases"][0]
    assert di["retrieval"]["reached"] is True and di["retrieval"]["hidden_id_in_full_result"] == [HIDDEN]
    assert di["acceptance"]["status"] == "WRONG" and out["verdict"] == "CHAIN_BROKEN" and out["broken_at"] == "denied-intermediate"
    assert di["consume"]["decision"] == "RELEASED"                                            # the harness would have released: exactly what WRONG must catch


def test_restricted_chain_is_broken_when_a_revocation_is_ignored(projection, sdk_root, tmp_path):
    class Sticky(PR.HermeticBroker):
        def revoke(self):
            return self._log("revoke", policy=dict(self.state, hidden=[]), observed=True)   # claims revocation, changes nothing

    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), projection=projection, as_of=AS_OF,
                       requester_mode="restricted", broker=Sticky(projection), cases=("revocation-before-replay",))
    rv = out["cases"][0]
    assert rv["replay"]["retrieval"]["cache"] == "HIT_RECHECKED" and rv["replay"]["consume"]["decision"] == "RELEASED"
    assert rv["acceptance"]["status"] == "WRONG" and out["verdict"] == "CHAIN_BROKEN"


def test_restricted_chain_tears_down_even_when_a_case_raises(projection, sdk_root, tmp_path, monkeypatch):
    b = PR.HermeticBroker(projection)
    monkeypatch.setattr(CH, "governed", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("simulated outage")))
    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), projection=projection, as_of=AS_OF,
                       requester_mode="restricted", broker=b)
    assert out["verdict"] == "CHAIN_INCOMPLETE" and all(s == "NOT_REACHED" for s in out["acceptance"].values()) and out["teardown"]["status"] == "NOT_NEEDED"
    assert all(c["receipt"]["invoked"] is False for c in out["cases"])


def test_module_cli_hermetic_restricted(sdk_root, sample_root, tmp_path):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, OKF_OPERATOR_EMAIL="operator@example.test", PYTHONPATH=root, OKF_ACME_ROOT=sample_root)
    r = subprocess.run([sys.executable, "-m", "okf_bq_graph.chain", "--hermetic", "--requester", "restricted", "--out", str(tmp_path), "--sdk-root", sdk_root],
                       env=env, capture_output=True, text=True, cwd=root)
    assert r.returncode == 0, r.stderr[-800:]
    assert "CHAIN_CONNECTED" in r.stdout and "identity=NOT_APPLICABLE" in r.stdout and "requester=restricted-sa" in r.stdout
    assert (tmp_path / "chain_hermetic_restricted.json").exists() and not (tmp_path / "chain_hermetic.json").exists()


def test_operator_chain_record_shape_is_unchanged(projection, sdk_root, tmp_path):
    out = CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), projection=projection, as_of=AS_OF)
    assert out["verdict"] == "CHAIN_CONNECTED" and out["requester"]["mode"] == "same-requester" and "identity" not in out and "teardown" not in out
    assert [c["case"] for c in out["cases"]] == list(CH.CASES) and (tmp_path / "chain_hermetic.json").exists()


def test_unknown_requester_mode_is_rejected(sdk_root, tmp_path):
    with pytest.raises(ValueError):
        CH.run_chain(engine="oracle", live=False, sdk_root=sdk_root, out_dir=str(tmp_path), requester_mode="admin")
    with pytest.raises(SystemExit):
        CH.main(["--hermetic", "--requester", "admin", "--out", str(tmp_path)])


# ---- live wiring against fakes (Slice B runs it for real)
class _Job:
    def __init__(self, email):
        self.user_email = email


class _Owner:
    def __init__(self, emails):
        self.emails, self.asked = emails, []

    def get_job(self, jid, project=None, location=None):
        self.asked.append(jid)
        return _Job(self.emails.get(jid, "missing"))


def test_bound_to_requires_the_sa_on_every_job_including_the_pointer_lookup():
    ids = ["pointer-job", "w1", "n1", "d1"]
    owner = _Owner({**{i: SA for i in ids}, "r1": SA})
    r = PR.bound_to(owner, ids, [{"job_id": "r1"}], SA)
    assert r["status"] == "BOUND" and set(owner.asked) == set(ids) | {"r1"} and r["jobs_compared"] == 5 and r["other_identities"] == []
    owner = _Owner({**{i: SA for i in ids}, "pointer-job": "operator@x", "r1": SA})
    r = PR.bound_to(owner, ids, [{"job_id": "r1"}], SA)
    assert r["status"] == "UNBOUND" and r["other_identities"] == ["operator@x"]
    assert PR.bound_to(_Owner({**{i: SA for i in ids}, "r1": None}), ids, [{"job_id": "r1"}], SA)["status"] == "UNKNOWN"
    assert PR.bound_to(_Owner({}), [], [{"job_id": "r1"}], SA)["status"] == "UNKNOWN"
    assert PR.bound_to(_Owner({}), ids, [], SA)["status"] == "UNKNOWN"

    class Boom(_Owner):
        def get_job(self, *a, **k):
            raise RuntimeError("jobs.get failed")
    assert PR.bound_to(Boom({}), ids, [{"job_id": "r1"}], SA)["status"] == "UNKNOWN"


def test_impersonated_credential_file_shape_and_permissions(tmp_path):
    src = tmp_path / "adc.json"
    src.write_text(json.dumps({"type": "authorized_user", "client_id": "c", "client_secret": "s", "refresh_token": "r"}))
    d = tmp_path / "priv"; d.mkdir()
    path = PR.impersonated_credential_file(SA, source_path=str(src), directory=str(d))
    doc = json.loads(Path(path).read_text())
    assert doc["type"] == "impersonated_service_account" and doc["service_account_impersonation_url"].endswith(f"{SA}:generateAccessToken")
    assert doc["source_credentials"]["refresh_token"] == "r" and doc["delegates"] == []
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600 and stat.S_IMODE(os.stat(d).st_mode) == 0o700
    src.write_text(json.dumps({"type": "impersonated_service_account"}))
    with pytest.raises(RuntimeError):
        PR.impersonated_credential_file(SA, source_path=str(src), directory=str(d))


class _SAClient:
    """Impersonated client whose dry runs are decided by a visibility table (no job is ever created)."""

    def __init__(self, allowed):
        self.allowed, self.queries = set(allowed), []

    def query(self, q, job_config=None, location=None):
        from google.api_core import exceptions as gexc
        self.queries.append(q)
        assert job_config.dry_run is True
        table = q.split("`")[1]
        if table not in self.allowed:
            raise gexc.Forbidden("403 access denied")
        return object()


class _Dataset:
    def __init__(self, ref, entries):
        self.ref, self.access_entries = ref, list(entries)


class _AclOwner(_Owner):
    """Owner client with real `bigquery.AccessEntry` ACLs per dataset, so the real `authz.set_dataset_reader` and the
    broker's snapshot/restore run unmodified (the API returns copies; `update_dataset` writes back)."""

    def __init__(self, acl):
        super().__init__({})
        self.acl = {ds: list(entries) for ds, entries in acl.items()}
        self.updates = []

    def get_dataset(self, ref):
        ds = ref.split(".", 1)[1]
        return _Dataset(ds, self.acl.setdefault(ds, []))

    def update_dataset(self, d, fields):
        assert fields == ["access_entries"]
        self.acl[d.ref] = list(d.access_entries); self.updates.append(d.ref)

    def roles(self, ds, principal=SA):
        return sorted(e.role for e in self.acl.get(ds, []) if (e.entity_id or "").replace("serviceAccount:", "") == principal)


SDK_DS = "okf_receipt_spike_20260905"
P = "test-project-0728-467323"
SDK_DEPS = [f"{P}.{SDK_DS}.orders", f"{P}.{SDK_DS}.order_lines"]
ALL_ALLOWED = {f"{P}.{DATASET}.nodes", f"{P}.{RLS_DS}.nodes", *SDK_DEPS}


def _entry(role):
    from google.cloud import bigquery
    return bigquery.AccessEntry(role, "userByEmail", SA)


def _live_broker(monkeypatch, allowed, acl=None, deps=SDK_DEPS, credfile=None, **kw):
    """A RestrictedBroker exactly as chain.py builds it (dependencies from the SDK publication, default wait), against a
    fake SA client, a fake ACL-bearing owner and a fake clock (so an unpropagated grant times out in test time)."""
    t = [0.0]
    monkeypatch.setattr(PR.time, "monotonic", lambda: t[0])
    monkeypatch.setattr(PR.time, "sleep", lambda s: t.__setitem__(0, t[0] + s))
    sa, owner = _SAClient(allowed), _AclOwner(acl or {})
    b = PR.RestrictedBroker("fallback", SDK_DS, dependencies=deps, sa_email=SA, factory=lambda p: sa, owner=owner,
                            credential_file=credfile or (lambda email, directory=None: os.path.join(directory, "adc.json")), **kw)
    return b, sa, owner


def test_live_broker_probes_under_the_sa_and_maps_forbidden_to_denied(monkeypatch):
    b, sa, owner = _live_broker(monkeypatch, allowed={"p.d.orders"})
    a = b.authorize(["p.d.orders", "p.d.order_lines"])
    assert a["status"] == "DENIED" and a["denied"] == 1 and [t["status"] for t in a["tables"]] == ["ALLOWED", "DENIED"]
    assert a["tables"][1]["error_class"] == "Forbidden" and len(sa.queries) == 2 and all("WHERE FALSE" in q for q in sa.queries)
    assert b.authorize([])["status"] == "UNKNOWN"
    assert b.authorize(["p.d.orders"])["status"] == "ALLOWED"
    assert b.describe()["iam"] is True and SA not in json.dumps(b.describe()) and b.graph_clients()["bq"] is sa and b.graph_clients()["ds"] == DATASET
    assert b.teardown()["status"] == "NOT_NEEDED"                                             # nothing touched is never VERIFIED


def test_live_broker_fresh_from_the_constructor_grants_without_hand_wiring(monkeypatch):   # Astra P2 #1
    b, sa, owner = _live_broker(monkeypatch, allowed=ALL_ALLOWED)
    e = b.grant()                                                                             # no b.dependencies assignment, default wait_s
    assert e["observed"] is True and e["sdk"]["status"] == "ALLOWED" and e["graph"]["status"] == "ALLOWED" and e["sdk"]["waited_s"] == 0
    assert owner.roles(DATASET) == ["READER"] and owner.roles(SDK_DS) == ["READER"] and b.granted == {DATASET, SDK_DS}
    assert sa.queries and all(q.split("`")[1] in ALL_ALLOWED for q in sa.queries)


def test_live_broker_never_touches_or_downgrades_preexisting_grants_and_restores_them(monkeypatch):   # Astra P1 / Opus
    acl = {DATASET: [_entry("READER")], SDK_DS: [_entry("WRITER")], RLS_DS: []}
    b, sa, owner = _live_broker(monkeypatch, allowed=ALL_ALLOWED, acl=acl)
    b.grant()
    assert owner.updates == [] and owner.roles(DATASET) == ["READER"] and owner.roles(SDK_DS) == ["WRITER"]   # pre-existing: untouched, WRITER not downgraded
    assert b.granted == set() and [j["event"] for j in b.journal[:-1]] == ["grant_preexisting", "grant_preexisting"]
    b.apply(PR.policy(dataset="rls", hidden=(HIDDEN,)))
    assert owner.roles(RLS_DS) == ["READER"] and b.granted == {RLS_DS} and b.graph_clients()["ds"] == RLS_DS
    b.apply(PR.policy())
    sa.allowed = set()
    r = b.revoke()                                                                             # the revocation case must observe a denial: pre-existing entries go too ...
    assert r["observed"] is True and owner.roles(DATASET) == [] and owner.roles(SDK_DS) == [] and owner.roles(RLS_DS) == ["READER"]
    td = b.teardown()                                                                          # ... and come back exactly, while the broker's own grant is gone
    assert td["status"] == "VERIFIED" and all(s["ok"] for s in td["steps"].values())
    assert owner.roles(DATASET) == ["READER"] and owner.roles(SDK_DS) == ["WRITER"] and owner.roles(RLS_DS) == []
    assert td["datasets"][SDK_DS] == {"original_roles": ["WRITER"], "roles_after": ["WRITER"], "added_by_broker": False}
    assert td["datasets"][RLS_DS] == {"original_roles": [], "roles_after": [], "added_by_broker": True}
    assert set(td["steps"]) == {f"{k}_{ds}" for k in ("restore", "readback") for ds in (DATASET, SDK_DS, RLS_DS)}


def test_live_broker_failed_setup_still_restores_the_original_acl(monkeypatch):   # Astra P1: failed launch through the real helper
    acl = {DATASET: [_entry("READER")], SDK_DS: []}
    b, sa, owner = _live_broker(monkeypatch, allowed={f"{P}.{DATASET}.nodes"})            # SDK tables never become readable
    b.owner.acl.update({k: list(v) for k, v in acl.items()})
    with pytest.raises(RuntimeError, match="did not propagate"):
        b.grant()
    assert owner.roles(SDK_DS) == ["READER"] and b.granted == {SDK_DS}                     # the broker's own grant is in place when the wait gave up
    assert b.journal[-1]["observed"] is False and b.journal[-1]["sdk"]["waited_s"] >= b.wait_s
    td = b.teardown()
    assert td["status"] == "VERIFIED" and owner.roles(SDK_DS) == [] and owner.roles(DATASET) == ["READER"]
    assert td["steps"][f"readback_{SDK_DS}"]["ok"] and td["steps"][f"readback_{DATASET}"]["ok"]


def test_live_broker_teardown_is_unverified_when_a_readback_disagrees(monkeypatch):
    b, sa, owner = _live_broker(monkeypatch, allowed=ALL_ALLOWED)
    b.grant()
    real_restore = b._restore
    b._restore = lambda ds: None                                                              # restore silently does nothing
    td = b.teardown()
    assert td["status"] == "UNVERIFIED" and not td["steps"][f"readback_{DATASET}"]["ok"] and owner.roles(DATASET) == ["READER"]
    real_restore(DATASET); real_restore(SDK_DS)
    assert owner.roles(DATASET) == [] and owner.roles(SDK_DS) == []


def test_live_restricted_chain_builds_the_broker_with_the_sdk_dependencies_and_tears_down_on_a_failed_grant(sdk_root, tmp_path, monkeypatch):
    """Astra P2 #1 through the actual chain: the broker chain.py constructs knows the bound publication's tables before
    its first grant probe, so an all-allowing platform gets past `grant`; and a platform that never propagates leaves
    the chain CHAIN_INCOMPLETE at grant with the ACL restored."""
    seen = {}
    t = [0.0]
    monkeypatch.setattr(PR.time, "monotonic", lambda: t[0]); monkeypatch.setattr(PR.time, "sleep", lambda s: t.__setitem__(0, t[0] + s))
    deps = CH.sdk_publication(sdk_root)["dependencies"]

    def make(allowed, acl):
        sa, owner = _SAClient(allowed), _AclOwner(acl)

        def factory(engine, sdk_dataset, dependencies=None, **kw):
            seen["dependencies"], seen["sdk_dataset"] = list(dependencies or []), sdk_dataset
            return PR.RestrictedBroker(engine, sdk_dataset, dependencies=dependencies, sa_email=SA, factory=lambda p: sa, owner=owner,
                                       credential_file=lambda email, directory=None: os.path.join(directory, "adc.json"))
        return factory, owner

    factory, owner = make({f"{P}.{DATASET}.nodes", *deps}, {DATASET: [_entry("READER")]})
    monkeypatch.setattr(CH, "RestrictedBroker", factory)
    monkeypatch.setattr(CH, "resolve_pointer_job", lambda client, ds=DATASET: (None, "pointer-job"))
    out = CH.run_chain(engine="fallback", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), requester_mode="restricted", as_of=AS_OF,
                       runner=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    assert seen["dependencies"] == deps and len(deps) == 7 and seen["sdk_dataset"] == SDK_DS
    assert out["grant"]["observed"] is True and out["broken_at"] == "publication"             # past the grant, stopped by the (fake) empty pointer
    assert out["teardown"]["status"] == "VERIFIED" and owner.roles(DATASET) == ["READER"] and owner.roles(SDK_DS) == []
    factory, owner = make(set(), {DATASET: [_entry("READER")]})
    monkeypatch.setattr(CH, "RestrictedBroker", factory)
    out = CH.run_chain(engine="fallback", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), requester_mode="restricted", as_of=AS_OF,
                       runner=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    assert out["verdict"] == "CHAIN_INCOMPLETE" and out["broken_at"] == "grant" and out["cases"] == [] and "did not propagate" in out["grant"]["error"]
    assert out["teardown"]["status"] == "VERIFIED" and owner.roles(DATASET) == ["READER"] and owner.roles(SDK_DS) == []


def test_live_broker_receipt_env_points_the_sdk_at_the_impersonated_file_and_teardown_removes_it(monkeypatch, tmp_path):
    seen = {}

    def credfile(email, directory=None):
        seen["email"], seen["dir"] = email, directory
        p = os.path.join(directory, "adc.json"); Path(p).write_text("{}"); return p

    b, sa, owner = _live_broker(monkeypatch, allowed=set(), credfile=credfile)
    env = b.receipt_env()
    assert seen["email"] == SA and env == {"GOOGLE_APPLICATION_CREDENTIALS": os.path.join(seen["dir"], "adc.json")} and os.path.exists(env["GOOGLE_APPLICATION_CREDENTIALS"])
    assert b.receipt_env() == env and b.receipt_launches == 2                                # one file per broker, reused
    td = b.teardown()
    assert td["status"] == "VERIFIED" and td["steps"] == {"remove_credential_file": {"ok": True}} and not os.path.exists(seen["dir"])


def test_live_restricted_chain_runs_the_pointer_lookup_under_the_broker_client_and_tears_down(sdk_root, tmp_path, monkeypatch):
    class Broker(PR.HermeticBroker):
        hermetic = False

        def __init__(self):
            self.journal, self.torn, self.receipt_launches = [], False, 0
            self.principal, self.email, self.state = SA_ALIAS, SA, dict(PR.policy())

        def describe(self):
            return {"kind": "fake-live", "iam": True, "principal": SA_ALIAS}

        def graph_clients(self):
            return {"engine": "fallback", "bq": "SA-CLIENT", "ds": DATASET, "cache": {}}

        def teardown(self):
            self.torn = True
            return {"status": "VERIFIED", "steps": {}}

    seen = {}

    def fake_resolve(client, ds=DATASET):
        seen["client"], seen["ds"] = client, ds
        return None, "pointer-job"

    monkeypatch.setattr(CH, "resolve_pointer_job", fake_resolve)
    b = Broker()
    out = CH.run_chain(engine="fallback", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), requester_mode="restricted", broker=b, as_of=AS_OF,
                       runner=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    assert seen == {"client": "SA-CLIENT", "ds": DATASET} and out["verdict"] == "CHAIN_BROKEN" and out["broken_at"] == "publication"
    assert b.torn and out["teardown"]["status"] == "VERIFIED" and out["grant"]["event"] == "apply" and (tmp_path / "chain_live_restricted.json").exists()


def test_live_restricted_identity_drives_the_verdict(sdk_root, projection, tmp_path, monkeypatch):
    """Every case MET but the identity check decides: BOUND connects, one job under another identity breaks, UNKNOWN is
    incomplete. The broker answers from the projection and the SDK runs hermetically; only the live verdict path is under test."""
    class LiveHermeticBroker(PR.HermeticBroker):
        hermetic = False

        def __init__(self, projection, ident):
            super().__init__(projection, sa_email=SA); self.ident = ident

        def graph_clients(self):
            return dict(super().graph_clients(), bq="SA-CLIENT")

        def identity(self, graph_job_ids, receipt_jobs):
            return dict(self.ident, jobs_compared=len(graph_job_ids) + len(receipt_jobs))

    monkeypatch.setattr(CH, "resolve_pointer_job", lambda client, ds=DATASET: (CH.PUBLICATION_PIN, "pointer-job"))

    def runner(argv, **kw):   # strip --live and rename the hermetic diagnostic to the name the live launch expects
        r = subprocess.run([x for x in argv if x != "--live"], **kw)
        d = Path(argv[argv.index("--evidence-dir") + 1])
        os.replace(d / "case_approved_hermetic.json", d / "case_approved_live.json")
        return r

    for ident, verdict in (({"status": "BOUND", "expected": SA}, "CHAIN_CONNECTED"),
                           ({"status": "UNBOUND", "other_identities": ["operator@x"]}, "CHAIN_BROKEN"),
                           ({"status": "UNKNOWN", "reason": "identity missing"}, "CHAIN_INCOMPLETE")):
        b = LiveHermeticBroker(projection, ident)
        out = CH.run_chain(engine="fallback", live=True, sdk_root=sdk_root, out_dir=str(tmp_path), requester_mode="restricted", broker=b,
                           as_of=AS_OF, runner=runner)
        assert out["acceptance"] == {c: "MET" for c in CH.RESTRICTED_CASES}, out["acceptance"]
        assert out["identity"]["job_set"]["pointer_lookup_included"] is True and out["mode"] == "live"
        assert out["verdict"] == verdict, (ident, out["verdict"], out.get("broken_at"))
        if verdict != "CHAIN_CONNECTED":
            assert out["broken_at"] == "identity"
        assert (tmp_path / "chain_live_restricted.json").exists()
