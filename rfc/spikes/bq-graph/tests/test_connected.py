"""Connected end-to-end run (okf_bq_graph.connected, 2026-09-14): Catalog IAM transitions, the fact read-back canonical
form, per-case acceptance, and the whole hermetic run with its honest failure modes (a revocation that is claimed but
not enforced, a store that stays readable, drifted facts, a grant that never lands, an unverified restore). No cloud.
Tests that need the pinned Acme checkout or the SDK checkout skip when absent."""
import copy
import datetime as dt
import decimal
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

import okf_bq_graph.catalog_access as CA
import okf_bq_graph.chain as CH
import okf_bq_graph.connected as E2E
from okf_bq_graph import SOURCE_PIN
from okf_bq_graph.authz import HIDDEN, SA_ALIAS
from okf_bq_graph.catalog import CatalogConfig, Response
from okf_bq_graph.compile import compile_bundle

TODAY = dt.date(2026, 9, 14)
AS_OF = "2026-09-14T00:00:00Z"
SA = "okf-receipt-restricted@test-project-0728-467323.iam.gserviceaccount.com"
MEMBER = f"serviceAccount:{SA}"
GROUP = CatalogConfig().group


# ----------------------------------------------------------------------------- Catalog IAM transitions
class _Resp:
    def __init__(self, status, body):
        self.status_code, self.content = status, json.dumps(body).encode() if body is not None else b""


class FakeIam:
    """getIamPolicy / setIamPolicy per resource with etags; `lose_set` drops the response of the next set AFTER applying it."""

    def __init__(self, bindings=None):
        self.policies = {GROUP: {"bindings": copy.deepcopy(bindings or []), "etag": "e0"}}
        self.sets, self.lose_set, self.corrupt_restore = 0, False, False

    def request(self, method, url, params=None, json=None, timeout=None):
        res, verb = url.split("v1/", 1)[1].rsplit(":", 1)
        pol = self.policies[res]
        if verb == "getIamPolicy":
            return _Resp(200, dict(pol))
        assert pol["etag"] == json["policy"].get("etag"), "set must carry the current etag"
        self.sets += 1
        bindings = copy.deepcopy(json["policy"]["bindings"])
        if self.corrupt_restore and not bindings:
            bindings = [{"role": "roles/viewer", "members": ["user:someone@example.test"]}]
        self.policies[res] = {"bindings": bindings, "etag": f"e{self.sets}"}
        if self.lose_set:
            self.lose_set = False
            raise ConnectionError("response lost after the policy was written")
        return _Resp(200, self.policies[res])


def test_catalog_access_grant_revoke_restore_readback():
    iam = FakeIam()
    ca = CA.CatalogAccess([GROUP], MEMBER, iam)
    assert ca.grant()["resources"] == {GROUP: "GRANTED"} and CA.holds(iam.policies[GROUP]["bindings"], CA.CATALOG_VIEWER, MEMBER)
    assert ca.revoke()["resources"] == {GROUP: "REVOKED"} and iam.policies[GROUP]["bindings"] == []
    r = ca.restore()
    assert r["status"] == "VERIFIED" and r["steps"][GROUP]["readback_equal"] and not r["steps"][GROUP]["member_holds_role_after"]


def test_catalog_access_leaves_a_preexisting_binding_and_restores_other_members():
    other = {"role": CA.CATALOG_VIEWER, "members": ["user:owner@example.test"]}
    iam = FakeIam([copy.deepcopy(other)])
    ca = CA.CatalogAccess([GROUP], MEMBER, iam)
    ca.grant()
    assert sorted(iam.policies[GROUP]["bindings"][0]["members"]) == sorted(["user:owner@example.test", MEMBER])
    assert ca.restore()["status"] == "VERIFIED" and CA.canonical_bindings(iam.policies[GROUP]["bindings"]) == CA.canonical_bindings([other])
    pre = FakeIam([{"role": CA.CATALOG_VIEWER, "members": [MEMBER]}])
    ca2 = CA.CatalogAccess([GROUP], MEMBER, pre)
    assert ca2.grant()["status"] == "PREEXISTING" and pre.sets == 0 and ca2.restore()["status"] == "NOT_NEEDED"


def test_catalog_access_restores_a_set_whose_response_was_lost():
    iam = FakeIam()
    ca = CA.CatalogAccess([GROUP], MEMBER, iam)
    iam.lose_set = True
    with pytest.raises(CA.CatalogAccessError):
        ca.grant()
    assert ca.mutated == [GROUP] and CA.holds(iam.policies[GROUP]["bindings"], CA.CATALOG_VIEWER, MEMBER)
    assert ca.restore()["status"] == "VERIFIED" and iam.policies[GROUP]["bindings"] == []


def test_catalog_access_restore_is_unverified_when_the_readback_differs():
    iam = FakeIam()
    ca = CA.CatalogAccess([GROUP], MEMBER, iam)
    ca.grant()
    iam.corrupt_restore = True
    r = ca.restore()
    assert r["status"] == "UNVERIFIED" and r["steps"][GROUP]["readback_equal"] is False


class _Reader:
    def __init__(self, *responses):
        self.responses = list(responses)

    def get_entry(self, name, view):
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r


def _entry_resp(status, data=True):
    cfg = CatalogConfig()
    body = {"aspects": {cfg.aspect_key: {"data": {"publication_id": "pub_x"}} if data else {}}}
    return Response(status, json.dumps(body).encode())


def test_observe_needs_aspect_data_for_allowed_and_403_for_denied():
    key, entry = CatalogConfig().aspect_key, CatalogConfig().entry
    assert CA.observe_entry(_Reader(_entry_resp(200)), entry, key)["status"] == "ALLOWED"
    assert CA.observe_entry(_Reader(_entry_resp(200, data=False)), entry, key)["status"] == "UNKNOWN"   # keys-only view is not access
    assert CA.observe_entry(_Reader(Response(403, b'{"error":{}}')), entry, key)["status"] == "DENIED"
    assert CA.observe_entry(_Reader(Response(404, b'{"error":{}}')), entry, key)["status"] == "UNKNOWN"
    assert CA.observe_entry(_Reader(Response(503, b"")), entry, key)["status"] == "UNKNOWN"
    assert CA.observe_entry(_Reader(ConnectionError("x")), entry, key)["status"] == "UNKNOWN"


def test_wait_reports_the_last_observation_when_time_runs_out():
    t = [0.0]
    ca = CA.CatalogAccess([GROUP], MEMBER, FakeIam(), sleep=lambda s: t.__setitem__(0, t[0] + s), clock=lambda: t[0])
    w = ca.wait("DENIED", _Reader(_entry_resp(200)), CatalogConfig().entry, CatalogConfig().aspect_key, wait_s=30)
    assert w["observed"] is False and w["status"] == "ALLOWED" and w["waited_s"] >= 30
    w = ca.wait("DENIED", _Reader(_entry_resp(200), _entry_resp(200), Response(403, b"{}")), CatalogConfig().entry, CatalogConfig().aspect_key, wait_s=300)
    assert w["observed"] is True and w["polls"] == 3


# ----------------------------------------------------------------------------- facts read-back canonical form
def _bq_rows_from_manifest(manifest):
    """The vendored canonical manifest turned back into what the BigQuery client returns (Decimal, int, datetime, date)."""
    tables = {}
    for name, t in manifest["tables"].items():
        schema = [{"name": f["name"], "type": {"INT64": "INTEGER"}.get(f["type"], f["type"]), "mode": f["mode"]} for f in t["schema"]]
        rows = []
        for row in t["rows"]:
            d = {}
            for f, v in zip(t["schema"], row):
                if v is None:
                    d[f["name"]] = None
                elif f["type"] == "NUMERIC":
                    d[f["name"]] = decimal.Decimal(v)
                elif f["type"] == "INT64":
                    d[f["name"]] = int(v)
                elif f["type"] == "TIMESTAMP":
                    d[f["name"]] = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
                elif f["type"] == "DATE":
                    d[f["name"]] = dt.date.fromisoformat(v)
                else:
                    d[f["name"]] = v
            rows.append(d)
        tables[name] = (schema, list(reversed(rows)))        # server order is not canonical order
    return tables


def test_manifest_from_bigquery_rows_hashes_to_the_selected_digest():
    vendored = E2E.vendored_manifest()
    m = E2E.manifest_from_rows(_bq_rows_from_manifest(vendored))
    assert m == vendored
    ok = E2E.admit_facts(lambda: m, TODAY)
    assert ok["status"] == "OK" and ok["bound_content_digest"] == E2E.selected_fact_version()["content_manifest_sha256"]
    tables = _bq_rows_from_manifest(vendored)
    tables["fulfillment_cost"][1][0]["allocated_cost"] = decimal.Decimal("21")      # one non-January amount changes
    drifted = E2E.admit_facts(lambda: E2E.manifest_from_rows(tables), TODAY)
    assert drifted["status"] == "FACTS_DRIFTED" and "fulfillment_cost" in drifted["differing_tables"]
    assert E2E.admit_facts(lambda: (_ for _ in ()).throw(PermissionError("403")), TODAY)["status"] == "DENIED"
    assert E2E.admit_facts(lambda: m, dt.date(2026, 12, 1))["status"] == "MATERIALIZATION_EXPIRED"


def test_run_receipt_honours_the_interpreter(tmp_path):
    seen = []
    CH.run_receipt("approved", str(tmp_path), str(tmp_path / "r"), live=False, python="/opt/sdk-python",
                   runner=lambda argv, **kw: seen.append(argv) or subprocess.CompletedProcess(argv, 1, "", ""))
    assert seen[0][0] == "/opt/sdk-python"


# ----------------------------------------------------------------------------- acceptance
def _seeded(**kw):
    c = {"case": E2E.APPROVED, "catalog": {"status": "OK"}, "publication": {"status": "OK"}, "source": {"status": "OK"},
         "retrieval": {"status": "OK", "reached": True}, "declaration": {"status": "OK"}, "payload": {"status": "CONSISTENT"},
         "bind": {"status": "BOUND"}, "authorization": {"status": "ALLOWED", "denied": 0}, "facts": {"status": "OK"},
         "receipt": {"invoked": True, "exit_code": 0, "diag_present": True, "receipt": {"verdict": "VERIFIED"}, "output": {"verdict": "VERIFIED"}},
         "consume": {"decision": "RELEASED", "reasons": []}}
    c.update(kw)
    return c


def test_accept_connected_approved():
    assert E2E.accept(_seeded())["status"] == "MET"
    assert E2E.accept(_seeded(catalog={"status": "CATALOG_ERROR", "http_status": 403}, consume={"decision": "REFUSED"}))["status"] == "NOT_REACHED"
    assert E2E.accept(_seeded(publication={"status": "FAIL_STALE", "reasons": ["PUBLICATION_MISSING"]}, consume={"decision": "REFUSED"}))["status"] == "WRONG"
    assert E2E.accept(_seeded(payload={"status": "INCONSISTENT", "failed": ["sql"]}, consume={"decision": "REFUSED"}))["status"] == "WRONG"
    assert E2E.accept(_seeded(authorization={"status": "DENIED", "denied": 7}, receipt={"invoked": False}, consume={"decision": "REFUSED"}))["status"] == "NOT_REACHED"
    assert E2E.accept(_seeded(facts={"status": "FACTS_DRIFTED"}, receipt={"invoked": False}, consume={"decision": "REFUSED"}))["status"] == "WRONG"
    assert E2E.accept(_seeded(facts={"status": "ERROR"}, receipt={"invoked": False}, consume={"decision": "REFUSED"}))["status"] == "NOT_REACHED"
    assert E2E.accept(_seeded(consume={"decision": "REFUSED", "reasons": ["x"]}))["status"] == "WRONG"
    assert E2E.accept(_seeded(payload={"status": "ERROR"}, consume={"decision": "RELEASED"}))["status"] == "WRONG"    # released on an unheld stage


def test_accept_connected_unauthorized_output():
    ok = _seeded(case=E2E.UNAUTH, authorization={"status": "DENIED", "denied": 7}, facts=None, receipt={"invoked": False},
                 consume={"decision": "REFUSED", "reasons": ["authorization DENIED at decision time"]})
    assert E2E.accept(ok)["status"] == "MET"
    assert E2E.accept(dict(ok, authorization={"status": "ALLOWED"}))["status"] == "WRONG"
    assert E2E.accept(dict(ok, authorization={"status": "UNKNOWN"}))["status"] == "NOT_REACHED"
    assert E2E.accept(dict(ok, receipt={"invoked": True}))["status"] == "WRONG"
    assert E2E.accept(dict(ok, consume={"decision": "REFUSED", "reasons": ["facts"]}))["status"] == "WRONG"


def _revocation(**kw):
    c = {"case": E2E.REVOKE, "first_release": {"decision": "RELEASED"},
         "control": {"catalog": {"status": "ALLOWED"}, "graph": {"status": "ALLOWED"}, "authorization": {"status": "ALLOWED"}},
         "revocation": {"observed": True, "catalog_wait": {"status": "DENIED"}, "requester": {"observed": True}},
         "fresh_request": {"catalog": {"status": "CATALOG_ERROR", "http_status": 403}, "downstream_ran": False},
         "bypass": {"publication": {"status": "ERROR"}, "retrieval": {"status": "DENIED", "disclosed_anything": False}},
         "authorization": {"status": "DENIED", "denied": 7}, "receipt_invocations_after_revocation": 0,
         "consume": {"decision": "REFUSED", "reasons": ["authorization DENIED at decision time"]}}
    c.update(kw)
    return c


def test_accept_connected_revocation():
    assert E2E.accept(_revocation())["status"] == "MET"
    assert E2E.accept(_revocation(first_release={"decision": "REFUSED"}))["status"] == "NOT_REACHED"
    assert E2E.accept(_revocation(control={"catalog": {"status": "DENIED"}, "graph": {"status": "ALLOWED"}, "authorization": {"status": "ALLOWED"}}))["status"] == "NOT_REACHED"
    assert E2E.accept(_revocation(revocation={"observed": False}))["status"] == "NOT_REACHED"
    assert E2E.accept(_revocation(fresh_request={"catalog": {"status": "OK"}, "downstream_ran": True}))["status"] == "WRONG"
    assert E2E.accept(_revocation(fresh_request={"catalog": {"status": "CATALOG_ERROR", "http_status": 503}}))["status"] == "NOT_REACHED"
    assert E2E.accept(_revocation(bypass={"publication": {"status": "OK"}, "retrieval": {"status": "DENIED"}}))["status"] == "WRONG"
    assert E2E.accept(_revocation(bypass={"publication": {"status": "ERROR"}, "retrieval": {"status": "OK", "disclosed_anything": True}}))["status"] == "WRONG"
    assert E2E.accept(_revocation(authorization={"status": "ALLOWED"}))["status"] == "WRONG"
    assert E2E.accept(_revocation(consume={"decision": "RELEASED", "reasons": []}))["status"] == "WRONG"
    assert E2E.accept(_revocation(receipt_invocations_after_revocation=1))["status"] == "WRONG"
    assert E2E.accept({"case": E2E.APPROVED, "status": "NOT_RUN", "reason": "grant"})["status"] == "NOT_REACHED"


# ----------------------------------------------------------------------------- whole run, hermetic
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
def recorded(projection, sdk_root, sample_root, tmp_path_factory):
    """One real hermetic run (the SDK's SYNTHETIC emulation as a subprocess); its diagnostics are kept so the regression
    runs below can replay the same child output without relaunching it."""
    out_dir = tmp_path_factory.mktemp("e2e")
    launches = []

    def runner(argv, **kw):
        r = subprocess.run(argv, **kw)
        inv = Path(argv[argv.index("--evidence-dir") + 1])
        case = argv[argv.index("--case") + 1]
        launches.append({"argv": argv, "case": case, "stdout": r.stdout, "returncode": r.returncode,
                         "diag": (inv / f"case_{case}_hermetic.json").read_bytes()})
        return r

    env = E2E.HermeticEnv(projection, sdk_root, CatalogConfig(), runner=runner)
    events = []
    out = E2E.run_connected(env, sdk_root, sample_root, out_dir=out_dir, as_of=AS_OF, today=TODAY,
                            progress=lambda ev, **kw: events.append((ev, kw)))
    return out, out_dir, launches, events


def replay_runner(launches):
    by_case = {l["case"]: l for l in launches}

    def run(argv, **kw):
        case = argv[argv.index("--case") + 1]
        inv = Path(argv[argv.index("--evidence-dir") + 1])
        rec = by_case[case]
        (inv / f"case_{case}_hermetic.json").write_bytes(rec["diag"])
        return subprocess.CompletedProcess(argv, rec["returncode"], rec["stdout"], "")
    return run


def test_hermetic_connected_run_end_to_end(recorded):
    out, out_dir, launches, events = recorded
    assert out["verdict"] == "E2E_CONNECTED", (out.get("broken_at"), out["acceptance"])
    assert out["acceptance"] == {c: "MET" for c in E2E.CASES}
    assert out["decisions"] == {E2E.APPROVED: "RELEASED", E2E.SUBST: "REFUSED", E2E.DENIED_INT: "REFUSED", E2E.UNAUTH: "REFUSED", E2E.REVOKE: "REFUSED"}
    assert [l["case"] for l in launches] == ["approved", "sql-substitution"]            # nothing executes after revocation
    by = {c["case"]: c for c in out["cases"]}
    ap = by[E2E.APPROVED]
    assert ap["catalog"]["status"] == "OK" and ap["catalog"]["mode"] == "catalog-mock" and ap["publication"]["status"] == "OK"
    assert ap["payload"]["status"] == "CONSISTENT" and ap["bind"]["status"] == "BOUND" and ap["facts"]["status"] == "OK"
    assert ap["consume"]["display"].endswith("$400.00 USD · VERIFIED")
    assert out["grant"]["catalog_before"]["status"] == "DENIED" and out["grant"]["catalog_wait"]["observed"]
    rv = by[E2E.REVOKE]
    assert rv["fresh_request"]["catalog"]["http_status"] == 403 and rv["fresh_request"]["downstream_ran"] is False
    assert rv["bypass"]["publication"]["status"] == "ERROR" and rv["bypass"]["retrieval"]["status"] == "DENIED"
    assert rv["consume"]["decision"] == "REFUSED" and rv["receipt_invocations_after_revocation"] == 0
    assert by[E2E.UNAUTH]["authorization"]["denied"] == 7 and by[E2E.UNAUTH]["receipt"]["invoked"] is False
    assert by[E2E.DENIED_INT]["retrieval"]["paths"] == [] and by[E2E.DENIED_INT]["seed_origin"] == "injected-fixture-seed"
    assert out["identity"]["status"] == "NOT_APPLICABLE" and out["teardown"]["catalog"]["status"] == "VERIFIED"
    s = E2E.summary(out)
    assert s["answer"].endswith("VERIFIED") and s["receipt_ref"].startswith("<id:") and s["access"]["fresh_request_after_revocation"] == "CATALOG_ERROR"


def test_hermetic_record_is_hygienic_and_run_owned(recorded):
    out, out_dir, _, _ = recorded
    run_dir = out_dir / out["run_id"]
    written = (out_dir / "connected_hermetic.json").read_text()
    assert written == (run_dir / "connected_hermetic.json").read_text()
    assert "operator@example.test" not in written and SA not in written and not re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", written)
    for local in ("computations/gross-margin-period", "metrics/gross-margin-legacy", HIDDEN):
        assert not re.search(re.escape(local) + r"(?![-\w])", written), local
    assert "<id:" in written and SA_ALIAS in written
    for p in (run_dir / "catalog").iterdir():
        text = p.read_text()
        assert not re.search(re.escape(HIDDEN) + r"(?![-\w])", text) and "@" not in text
    with pytest.raises(FileExistsError):                      # a run directory is never shared
        (out_dir / out["run_id"]).mkdir(parents=False, exist_ok=False)


def _run(projection, sdk_root, sample_root, tmp_path, launches, env_cls=E2E.HermeticEnv, **kw):
    env = env_cls(projection, sdk_root, CatalogConfig(), runner=replay_runner(launches), **kw)
    return env, E2E.run_connected(env, sdk_root, sample_root, out_dir=tmp_path, as_of=AS_OF, today=TODAY)


def test_a_revocation_that_is_claimed_but_not_enforced_is_broken(projection, sdk_root, sample_root, tmp_path, recorded):
    class Lying(E2E.HermeticEnv):
        def catalog_revoke(self):
            return {"status": "REVOKED"}                     # the Catalog keeps serving the requester

        def catalog_wait(self, want):
            return {"want": want, "observed": True, "status": want, "waited_s": 0}

    _, out = _run(projection, sdk_root, sample_root, tmp_path, recorded[2], env_cls=Lying)
    rv = {c["case"]: c for c in out["cases"]}[E2E.REVOKE]
    assert rv["fresh_request"]["catalog"]["status"] == "OK" and rv["acceptance"]["status"] == "WRONG"
    assert out["verdict"] == "E2E_BROKEN" and out["broken_at"] == E2E.REVOKE


def test_an_honestly_unobserved_revocation_is_incomplete_not_connected(projection, sdk_root, sample_root, tmp_path, recorded):
    class Sticky(E2E.HermeticEnv):
        def catalog_revoke(self):
            return {"status": "REVOKED"}

    _, out = _run(projection, sdk_root, sample_root, tmp_path, recorded[2], env_cls=Sticky)
    assert out["acceptance"][E2E.REVOKE] == "NOT_REACHED" and out["verdict"] == "E2E_INCOMPLETE" and out["broken_at"] == E2E.REVOKE


def test_a_store_that_stays_readable_after_revocation_is_broken(projection, sdk_root, sample_root, tmp_path, recorded):
    class Leaky(E2E.HermeticEnv):
        def store(self, journal):
            s = E2E.ProjectionStore(journal, "ungated")
            s.add(self.projection); s.set_head(self.projection["bundle_id"], self.projection["publication_id"])
            return s

    _, out = _run(projection, sdk_root, sample_root, tmp_path, recorded[2], env_cls=Leaky)
    rv = {c["case"]: c for c in out["cases"]}[E2E.REVOKE]
    assert rv["bypass"]["publication"]["status"] == "OK" and rv["acceptance"]["status"] == "WRONG" and out["verdict"] == "E2E_BROKEN"


def test_drifted_facts_withhold_the_number(projection, sdk_root, sample_root, tmp_path, recorded):
    def drifted():
        m = E2E.vendored_manifest()
        m["tables"]["fulfillment_cost"]["rows"][1][1] = "21.000000000"
        return m

    env, out = _run(projection, sdk_root, sample_root, tmp_path, recorded[2], facts=drifted)
    ap = {c["case"]: c for c in out["cases"]}[E2E.APPROVED]
    assert ap["facts"]["status"] == "FACTS_DRIFTED" and ap["receipt"]["invoked"] is False and ap["consume"]["decision"] == "REFUSED"
    assert ap["acceptance"]["status"] == "WRONG" and out["verdict"] == "E2E_BROKEN" and env.receipt_launches == 0


def test_a_grant_that_never_lands_runs_nothing(projection, sdk_root, sample_root, tmp_path, recorded):
    class NoGrant(E2E.HermeticCatalogAccess):
        def grant(self):
            self.mutated = True
            return {"status": "GRANTED"}

    env, out = _run(projection, sdk_root, sample_root, tmp_path, recorded[2], catalog=NoGrant())
    assert out["verdict"] == "E2E_INCOMPLETE" and out["broken_at"] == "grant" and env.receipt_launches == 0
    assert set(out["acceptance"].values()) == {"NOT_REACHED"} and len(out["cases"]) == len(E2E.CASES)
    assert out["teardown"]["catalog"]["status"] == "VERIFIED"                             # restore still ran


def test_an_unverified_restore_blocks_the_verdict(projection, sdk_root, sample_root, tmp_path, recorded):
    class BadRestore(E2E.HermeticCatalogAccess):
        def restore(self):
            return {"status": "UNVERIFIED", "steps": {"x": {"ok": False}}}

    _, out = _run(projection, sdk_root, sample_root, tmp_path, recorded[2], catalog=BadRestore())
    assert out["acceptance"] == {c: "MET" for c in E2E.CASES}
    assert out["verdict"] == "E2E_INCOMPLETE" and out["broken_at"] == "teardown"


def test_a_dirty_sdk_checkout_is_refused_before_any_grant(projection, sdk_root, sample_root, tmp_path, recorded, monkeypatch):
    real = CH.sdk_publication
    monkeypatch.setattr(CH, "sdk_publication", lambda root: dict(real(root), sdk_repo_dirty=True))
    env, out = _run(projection, sdk_root, sample_root, tmp_path, recorded[2])
    assert out["verdict"] == "E2E_BROKEN" and out["broken_at"] == "provenance" and env.access.mutated is False and out["cases"] == []
