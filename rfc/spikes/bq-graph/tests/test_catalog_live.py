"""Slice B2 live glue, hermetically: the `LiveCloud` adapter against fake BigQuery/HTTP objects (request shapes, bounded
calls, typed outcomes, attempt bookkeeping) and the `B2Experiment` driver against the U4 in-memory FakeCloud with a
stub chain runner that resolves pins through the REAL `resolve_publication` (so withdraw / wrong pins / the in-flight
head switch are exercised by real code) and honours the driver's hooks. Nothing here touches a cloud."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import okf_bq_graph.catalog_live as LV
import okf_bq_graph.publication as PUB
from okf_bq_graph import SOURCE_PIN
from okf_bq_graph.catalog import parse_pin, CatalogPin
from okf_bq_graph.catalog_lifecycle import FORBIDDEN_SQL, LifecycleConfig, ScopeViolation
from okf_bq_graph.seed import ConceptSeed

from test_catalog_lifecycle import FakeCloud, Clock


# ============================================================================ LiveCloud against fakes
class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


@pytest.fixture(autouse=True)
def api_core(monkeypatch):
    """The adapter classifies create attempts off `google.api_core.exceptions`. Prefer the REAL package when it is
    installed (a stub `google.api_core` module would break every later `from google.cloud import bigquery`, which
    imports `google.api_core.client_options`); only synthesise it when the package is genuinely unavailable, and
    then re-point this module's local `NotFound` / `Conflict` at the real classes so the fakes raise what the
    adapter catches."""
    global NotFound, Conflict
    import sys, types
    try:
        import google.api_core.exceptions as real                       # noqa: PLC0415 - probe the hermetic env
    except Exception:                                                   # noqa: BLE001 - any import failure means "not installed"
        mod = types.ModuleType("google.api_core.exceptions")
        mod.NotFound, mod.Conflict = NotFound, Conflict
        mod.BadRequest, mod.Forbidden = type("BadRequest", (Exception,), {}), type("Forbidden", (Exception,), {})
        pkg = types.ModuleType("google.api_core")
        pkg.exceptions = mod
        monkeypatch.setitem(sys.modules, "google.api_core", pkg)
        monkeypatch.setitem(sys.modules, "google.api_core.exceptions", mod)
        yield mod
        return
    saved = (NotFound, Conflict)
    NotFound, Conflict = real.NotFound, real.Conflict
    try:
        yield real
    finally:
        NotFound, Conflict = saved


def Field(name, field_type, mode="NULLABLE"):
    """A table schema field. The adapter hands the read-back schema straight to `bigquery.LoadJobConfig`, so when the
    real client is installed the fake table has to carry real `SchemaField`s; the duck-typed stand-in is only for an
    env without google-cloud-bigquery (`.name` / `.field_type` / `.mode` is all the rest of the adapter reads)."""
    try:
        from google.cloud import bigquery                               # noqa: PLC0415 - probe the hermetic env
    except Exception:                                                   # noqa: BLE001 - any import failure means "not installed"
        return SimpleNamespace(name=name, field_type=field_type, mode=mode)
    return bigquery.SchemaField(name, field_type, mode=mode)


class FakeJob:
    def __init__(self, job_id, rows=(), state="DONE", error=None):
        self.job_id, self._rows, self.state, self.error_result = job_id, list(rows), state, error
        self.num_dml_affected_rows, self.output_rows, self.user_email = 1, len(self._rows), "op@example.test"

    def result(self, timeout=None):
        self.result_timeout = timeout
        return list(self._rows)


class FakeBQ:
    def __init__(self):
        self.project = "test-project-0728-467323"
        self.datasets, self.jobs, self.queries, self.loads, self.calls = {}, {}, [], [], []
        self.rows = []

    def get_dataset(self, ref, retry=None, timeout=None):
        self.calls.append(("get_dataset", ref, retry, timeout))
        if ref not in self.datasets:
            raise NotFound(ref)
        return self.datasets[ref]

    def create_dataset(self, ds, exists_ok=False, retry=None, timeout=None):
        self.calls.append(("create_dataset", ds.dataset_id if hasattr(ds, "dataset_id") else ds, retry, timeout))
        if getattr(self, "create_raises", None):
            raise self.create_raises
        self.datasets[f"{self.project}.{ds.dataset_id}"] = ds
        return ds

    def delete_dataset(self, ref, delete_contents=False, not_found_ok=True, retry=None, timeout=None):
        self.calls.append(("delete_dataset", ref, delete_contents, not_found_ok, retry, timeout))
        self.datasets.pop(ref)

    def get_table(self, ref, retry=None, timeout=None):
        self.calls.append(("get_table", ref, retry, timeout))
        return SimpleNamespace(schema=[Field("publication_id", "STRING"), Field("node_count", "INTEGER"), Field("validation_reasons", "STRING", "REPEATED"),
                                       Field("created_at", "TIMESTAMP"), Field("ready_at", "TIMESTAMP"), Field("stub", "BOOLEAN")])

    def query(self, sql, job_config=None, location=None, job_id=None, project=None, retry="unset", job_retry="unset", timeout=None):
        self.queries.append({"sql": sql, "cfg": job_config, "location": location, "job_id": job_id, "project": project, "retry": retry, "job_retry": job_retry, "timeout": timeout})
        job = FakeJob(job_id, self.rows)
        self.jobs[job_id] = job
        return job

    def load_table_from_json(self, rows, destination, job_config=None, job_id=None, location=None, project=None, timeout=None):
        self.loads.append({"rows": rows, "destination": destination, "cfg": job_config, "job_id": job_id, "location": location, "project": project, "timeout": timeout})
        job = FakeJob(job_id, rows)
        self.jobs[job_id] = job
        return job

    def get_job(self, job_id, project=None, location=None, retry=None, timeout=None):
        self.calls.append(("get_job", job_id, project, location, retry, timeout))
        if job_id not in self.jobs:
            raise NotFound(job_id)
        return self.jobs[job_id]

    def cancel_job(self, job_id, project=None, location=None, retry=None, timeout=None):
        self.calls.append(("cancel_job", job_id, project, location, retry, timeout))


class FakeResp:
    def __init__(self, status, body=None):
        self.status_code = status
        self.content = json.dumps(body).encode() if body is not None else b""


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def request(self, method, url, params=None, json=None, timeout=None, allow_redirects=True):
        self.calls.append({"method": method, "url": url, "params": params, "json": json, "timeout": timeout, "allow_redirects": allow_redirects})
        return self.responses.pop(0)


@pytest.fixture
def bq():
    return FakeBQ()


@pytest.fixture
def cloud(bq):
    return LV.LiveCloud(bq, session=FakeSession([]))


def test_get_dataset_absent_is_none_and_present_returns_labels(cloud, bq):
    assert cloud.get_dataset("okf_catalog_chain_x", 7) is None
    bq.datasets["test-project-0728-467323.okf_catalog_chain_x"] = SimpleNamespace(labels={"okf_owner": "abc"}, location="US", dataset_id="okf_catalog_chain_x")
    assert cloud.get_dataset("okf_catalog_chain_x", 7) == {"labels": {"okf_owner": "abc"}, "location": "US", "dataset_id": "okf_catalog_chain_x"}
    assert all(c[2] is None and c[3] == 7 for c in bq.calls)      # retry=None, bounded


def test_select_rows_is_parameterised_bounded_and_uncached(cloud, bq):
    import datetime as dt
    bq.rows = [{"node_id": "n", "created_at": dt.datetime(2026, 9, 7, tzinfo=dt.timezone.utc)}]
    rows = cloud.select_rows("okf_catalog_chain_x", "nodes", {"publication_id": "pub_1", "bundle_id": "acme_retail"}, "okf_cc_x_select_rows_1", 9, exclude=("stale_after_ts",))
    q = bq.queries[-1]
    assert q["sql"] == "SELECT * EXCEPT (stale_after_ts) FROM `test-project-0728-467323.okf_catalog_chain_x.nodes` WHERE bundle_id = @w0 AND publication_id = @w1"
    assert [(p.name, p.type_, p.value) for p in q["cfg"].query_parameters] == [("w0", "STRING", "acme_retail"), ("w1", "STRING", "pub_1")]
    assert q["cfg"].use_query_cache is False and q["cfg"].maximum_bytes_billed == PUB.MAX_BYTES_BILLED
    assert q["job_id"] == "okf_cc_x_select_rows_1" and q["project"] == bq.project and q["location"] == "US"
    assert q["retry"] is None and q["job_retry"] is None and q["timeout"] == 9 and bq.jobs[q["job_id"]].result_timeout == 9
    assert rows == [{"node_id": "n", "created_at": "2026-09-07T00:00:00+00:00"}]   # JSON-safe for the journal
    with pytest.raises(ValueError):
        cloud.select_rows("okf_catalog_chain_x", "nodes; DROP", {}, "okf_cc_x_1", 9)


def test_insert_row_types_parameters_from_the_table_schema(cloud, bq):
    cloud.insert_row("okf_catalog_chain_x", "publications", {"publication_id": "pub_1", "node_count": 44, "validation_reasons": [], "created_at": "2026-09-07T00:00:00Z",
                                                            "ready_at": None, "stub": False}, "okf_cc_x_insert_row_1", 5)
    q = bq.queries[-1]
    assert q["sql"].startswith("INSERT INTO `test-project-0728-467323.okf_catalog_chain_x.publications` (publication_id, node_count, validation_reasons, created_at, ready_at, stub) VALUES (@publication_id")
    types = {p.name: getattr(p, "type_", getattr(p, "array_type", None)) for p in q["cfg"].query_parameters}
    assert types == {"publication_id": "STRING", "node_count": "INT64", "validation_reasons": "STRING", "created_at": "TIMESTAMP", "ready_at": "TIMESTAMP", "stub": "BOOL"}
    created = next(p for p in q["cfg"].query_parameters if p.name == "created_at").value
    assert created.tzinfo is not None and created.year == 2026
    with pytest.raises(ValueError):
        cloud.insert_row("okf_catalog_chain_x", "publications", {"no_such_column": 1}, "okf_cc_x_insert_row_2", 5)


def test_forbidden_sql_and_foreign_ddl_are_refused_before_any_client_call(cloud, bq):
    for bad in FORBIDDEN_SQL:
        with pytest.raises(ScopeViolation):
            cloud.run_ddl("okf_catalog_chain_x", f"CREATE TABLE IF NOT EXISTS `test-project-0728-467323.okf_catalog_chain_x.t` (a STRING) -- {bad}", "okf_cc_x_ddl", 5)
    with pytest.raises(ScopeViolation):
        cloud.run_ddl("okf_catalog_chain_x", "CREATE TABLE IF NOT EXISTS `test-project-0728-467323.okf_graph_spike_20260905.nodes` (a STRING)", "okf_cc_x_ddl", 5)
    assert bq.queries == []
    cloud.run_ddl("okf_catalog_chain_x", "CREATE TABLE IF NOT EXISTS `test-project-0728-467323.okf_catalog_chain_x.nodes` (a STRING)", "okf_cc_x_ddl_ok", 5)
    assert bq.queries[-1]["job_id"] == "okf_cc_x_ddl_ok"


def test_load_rows_uses_the_driver_job_id_and_the_table_schema(cloud, bq):
    out = cloud.load_rows("okf_catalog_chain_x", "nodes", [{"node_id": "n", "tags": ["a"], "stub": False}], "okf_cc_x_load_rows_1", 6)
    l = bq.loads[-1]
    assert l["job_id"] == "okf_cc_x_load_rows_1" and l["destination"] == "test-project-0728-467323.okf_catalog_chain_x.nodes" and l["timeout"] == 6
    assert l["cfg"].write_disposition == "WRITE_APPEND" and l["cfg"].schema and out["job_id"] == "okf_cc_x_load_rows_1"
    with pytest.raises(ValueError):
        cloud.load_rows("okf_catalog_chain_x", "nodes`; DROP", [], "okf_cc_x_load_rows_2", 6)


def test_create_dataset_bookkeeping_is_the_only_source_of_attempt_outcome(cloud, bq):
    cloud.create_dataset("okf_catalog_chain_x", "US", {"okf_owner": "s"}, "okf_att_x_1", 5)
    ds = bq.datasets["test-project-0728-467323.okf_catalog_chain_x"]
    assert ds.location == "US" and ds.labels == {"okf_owner": "s"} and ds.default_table_expiration_ms == 2 * 24 * 3600 * 1000
    assert cloud.attempt_outcome("dataset", "okf_catalog_chain_x", "okf_att_x_1", 5) == "APPLIED"
    assert cloud.attempt_outcome("entry", "okf_catalog_chain_x", "okf_att_x_1", 5) is None       # kind/name must match the attempt
    bq.create_raises = Conflict("exists")
    with pytest.raises(Conflict):
        cloud.create_dataset("okf_catalog_chain_y", "US", {}, "okf_att_x_2", 5)
    assert cloud.attempt_outcome("dataset", "okf_catalog_chain_y", "okf_att_x_2", 5) == "NOT_APPLIED"
    bq.create_raises = TimeoutError("lost")
    with pytest.raises(TimeoutError):
        cloud.create_dataset("okf_catalog_chain_z", "US", {}, "okf_att_x_3", 5)
    assert cloud.attempt_outcome("dataset", "okf_catalog_chain_z", "okf_att_x_3", 5) is None      # unknown: never inferred from time
    assert cloud.attempt_outcome("dataset", "okf_catalog_chain_z", "okf_att_never", 5) is None


def test_job_state_and_cancel_use_the_journaled_reference(cloud, bq):
    assert cloud.job_state("okf_cc_missing", 4) is None
    bq.jobs["okf_cc_j"] = FakeJob("okf_cc_j", state="RUNNING")
    assert cloud.job_state("okf_cc_j", 4) == {"state": "RUNNING", "error": None, "user_email": "op@example.test"}
    cloud.cancel_job("okf_cc_j", 4)
    assert bq.calls[-1] == ("cancel_job", "okf_cc_j", bq.project, "US", None, 4)
    cloud.delete_dataset("okf_catalog_chain_x", 4) if "test-project-0728-467323.okf_catalog_chain_x" in bq.datasets else None
    bq.datasets["test-project-0728-467323.okf_catalog_chain_x"] = object()
    cloud.delete_dataset("okf_catalog_chain_x", 4)
    assert bq.calls[-1] == ("delete_dataset", "test-project-0728-467323.okf_catalog_chain_x", True, False, None, 4)


ENTRY = "projects/p/locations/us-central1/entryGroups/okf-rfc-demo/entries/acme-retail-catalog-chain/r1/metrics/gross-margin"


def test_get_entry_shapes(bq):
    retained = []
    sess = FakeSession([FakeResp(404), FakeResp(200, {"name": ENTRY, "aspects": {}}), FakeResp(403, {"error": "denied"})])
    cloud = LV.LiveCloud(bq, session=sess, retain=lambda n, raw: retained.append((n, raw)))
    assert cloud.get_entry(ENTRY, 8) is None
    assert cloud.get_entry(ENTRY, 8) == {"name": ENTRY, "aspects": {}}
    with pytest.raises(LV.CatalogHttpError) as e:
        cloud.get_entry(ENTRY, 8)
    assert e.value.status == 403
    for c in sess.calls:
        assert c["method"] == "GET" and c["url"] == LV.CATALOG_API + ENTRY and c["params"] == {"view": "ALL"} and c["timeout"] == (10, 8) and c["allow_redirects"] is False
    assert [n.split("_")[-1] for n, _ in retained] == ["404", "200", "403"] and all(json.loads(raw)["url"].endswith(ENTRY) for _, raw in retained)


def test_create_entry_posts_to_the_group_with_entry_id_and_books_the_attempt(bq):
    sess = FakeSession([FakeResp(200, {"name": ENTRY}), FakeResp(409, {"error": "exists"}), FakeResp(503, {"error": "unavailable"})])
    cloud = LV.LiveCloud(bq, session=sess)
    body = {"name": ENTRY, "entryType": "t", "aspects": {"k": {"data": {}}}, "entrySource": {"labels": {"okf_owner": "s"}}}
    assert cloud.create_entry(ENTRY, body, "okf_att_e_1", 8) == {"name": ENTRY}
    c = sess.calls[0]
    assert c["method"] == "POST" and c["url"] == LV.CATALOG_API + "projects/p/locations/us-central1/entryGroups/okf-rfc-demo/entries"
    assert c["params"] == {"entryId": "acme-retail-catalog-chain/r1/metrics/gross-margin"} and "name" not in c["json"] and c["json"]["entryType"] == "t"
    assert cloud.attempt_outcome("entry", ENTRY, "okf_att_e_1", 8) == "APPLIED"
    with pytest.raises(LV.CatalogHttpError):
        cloud.create_entry(ENTRY, body, "okf_att_e_2", 8)
    assert cloud.attempt_outcome("entry", ENTRY, "okf_att_e_2", 8) == "NOT_APPLIED"
    with pytest.raises(LV.CatalogHttpError):
        cloud.create_entry(ENTRY, body, "okf_att_e_3", 8)
    assert cloud.attempt_outcome("entry", ENTRY, "okf_att_e_3", 8) is None


def test_patch_entry_upserts_present_keys_and_deletes_only_listed_missing_keys(bq):
    sess = FakeSession([FakeResp(200, {}), FakeResp(200, {}), FakeResp(200, {})])
    cloud = LV.LiveCloud(bq, session=sess)
    body = {"name": ENTRY, "entryType": "t", "aspects": {"a.okf": {"data": {"x": 1}}, "rt": {"data": {"y": 2}}}}
    assert cloud.patch_entry(ENTRY, body, ["a.okf", "rt"], 8) == {"upserted": ["a.okf", "rt"], "deleted": []}
    c = sess.calls[0]
    assert c["method"] == "PATCH" and c["params"] == {"updateMask": "aspects", "aspectKeys": ["a.okf", "rt"], "deleteMissingAspects": "false"}
    assert c["json"] == {"name": ENTRY, "aspects": body["aspects"]}
    # removal of the runtime aspect: the key is listed, absent from the body -> a delete scoped to exactly that key
    assert cloud.patch_entry(ENTRY, {"name": ENTRY, "aspects": {"a.okf": {"data": {"x": 1}}}}, ["rt"], 8) == {"upserted": [], "deleted": ["rt"]}
    c = sess.calls[1]
    assert c["params"] == {"updateMask": "aspects", "aspectKeys": ["rt"], "deleteMissingAspects": "true"} and c["json"] == {"name": ENTRY, "aspects": {}}
    assert len(sess.calls) == 2
    sess.responses = [FakeResp(400, {"error": "bad"})]
    with pytest.raises(LV.CatalogHttpError):
        cloud.patch_entry(ENTRY, body, ["a.okf"], 8)


def test_delete_entry_requires_a_200(bq):
    sess = FakeSession([FakeResp(200, {}), FakeResp(404, {})])
    cloud = LV.LiveCloud(bq, session=sess)
    assert cloud.delete_entry(ENTRY, 8) == {"deleted": ENTRY}
    assert sess.calls[0]["method"] == "DELETE" and sess.calls[0]["url"] == LV.CATALOG_API + ENTRY
    with pytest.raises(LV.CatalogHttpError):
        cloud.delete_entry(ENTRY, 8)


# ============================================================================ B2Experiment against the U4 FakeCloud
RUN = "b2-t-0001"
CFG = LifecycleConfig(run_id=RUN, timeout_s=5.0)
GM_SECTION = "computations/gross-margin-period#s0"


class FakeStore:
    """The chain's retained store, backed by the FakeCloud's owned dataset rows; reads go through the REAL resolver."""
    engine = "fake"

    def __init__(self, cloud, dataset):
        self.cloud, self.dataset, self.journal = cloud, dataset, None

    def _rows(self, table, **where):
        return [copy.deepcopy(r) for r in self.cloud.datasets.get(self.dataset, {}).get(table, []) if all(r.get(k) == v for k, v in where.items())]

    def publication(self, bundle, pub):
        return self._rows("publications", bundle_id=bundle, publication_id=pub), {}

    def seed(self, node_id, bundle, pub):
        return self._rows("nodes", node_id=node_id, bundle_id=bundle, publication_id=pub), {}

    def head(self, bundle):
        return self._rows("active_publication", bundle_id=bundle), {}


def stub_chain_factory(cloud, mod, log):
    """A chain runner with the same outward record shape as `chain.run_chain` for the fields the driver grades: seed
    parsed by the real parser from the FakeCloud entry, pin resolved by the real `resolve_publication` (looked up on
    `mod` so the barrier hook applies), retrieval through `mod.governed` (so the injection hook applies), and a
    payload guard that refuses a section id outside the pinned publication or altered SQL bytes."""
    def run(engine, live, sdk_root, out_dir, clients, acme_root, seed_mode, catalog_reader, catalog_cfg, **kw):
        cfg = catalog_cfg
        out = {"run_dir": out_dir, "seed": {"mode": getattr(catalog_reader, "mode", None), "entry": cfg.entry}, "catalog": {"entry": cfg.entry},
               "store": {"dataset": clients["ds"]}, "cases": [], "engine": engine, "mode": "live" if live else "hermetic"}
        log.append({"entry": cfg.entry, "ds": clients["ds"]})
        entry = cloud.entries.get(cfg.entry)
        if entry is None:
            out["seed"].update(status="ENTRY_NOT_FOUND"); out.update(verdict="CHAIN_BROKEN", broken_at="seed"); return out
        if cfg.aspect_key not in (entry.get("aspects") or {}):
            out["seed"].update(status="ASPECT_MISSING"); out.update(verdict="CHAIN_BROKEN", broken_at="seed"); return out
        pin = parse_pin(entry, cfg)
        if not isinstance(pin, CatalogPin):
            out["seed"].update(status=pin.status); out.update(verdict="CHAIN_BROKEN", broken_at="seed"); return out
        out["seed"]["status"] = "OK"
        res = mod.resolve_publication(FakeStore(cloud, clients["ds"]), pin)
        out["publication"] = {"status": res["status"], "publication_id": pin.publication_id, "reasons": res.get("reasons"), "head": res.get("head")}
        if res["status"] != "OK":
            out.update(verdict="CHAIN_BROKEN", broken_at="publication"); return out
        pub = pin.publication_id
        out["graph_publication"] = {"publication_id": pub}
        for case in ("approved", "sql-substitution", "declaration-mismatch"):
            seed = ConceptSeed(f"{pin.bundle_id}|{pub}|Concept|metrics/revenue", origin="injected-fixture-seed") if case == "declaration-mismatch" else pin.seed("catalog")
            r = mod.governed(seed, pub, "user:operator", "2026-09-07T00:00:00Z", clients)
            comp = r["computations"][0]
            torn = comp["section_id"].split("|")[1] != pub or "0 * payment_fee" in comp["sql"]
            c = {"case": case, "payload": {"status": "INCONSISTENT" if torn else "CONSISTENT"}}
            if torn:
                c.update(bind={"status": "NOT_BOUND"}, receipt={"invoked": False}, consume={"decision": "REFUSED"}, acceptance={"status": "WRONG"})
            elif case == "declaration-mismatch":
                c.update(bind={"status": "MISMATCH"}, receipt={"invoked": False}, consume={"decision": "REFUSED"}, acceptance={"status": "MET"})
            else:
                verdict = "VERIFIED" if case == "approved" else "REJECTED"
                c.update(bind={"status": "BOUND"}, receipt={"invoked": True, "output": {"verdict": verdict}},
                         consume={"decision": "RELEASED" if case == "approved" else "REFUSED"}, acceptance={"status": "MET"})
            out["cases"].append(c)
        wrong = [c["case"] for c in out["cases"] if c["acceptance"]["status"] != "MET"]
        out.update(verdict="CHAIN_BROKEN" if wrong else "CHAIN_CONNECTED", broken_at=wrong[0] if wrong else None, same_requester={"status": "SAME"},
                   job_inventory={"graph": ["j1"], "receipt": []}, evidence={"unresolved_jobs": 0})
        return out
    return run


def real_governed(seed, pub, requester, as_of, clients):
    bundle = seed.concept_id.split("|")[0]
    return {"status": "OK", "computations": [{"computation_id": f"{bundle}|{pub}|Concept|computations/gross-margin-period", "section_id": f"{bundle}|{pub}|Section|{GM_SECTION}",
                                              "sql": "SELECT revenue - cogs - payment_fee FROM t", "sql_sha256": "d" * 64, "path": "computations/gross-margin-period.md"}]}


@pytest.fixture
def experiment(tmp_path, sample_root):
    cloud = FakeCloud()
    mod = SimpleNamespace(resolve_publication=PUB.resolve_publication, governed=real_governed)
    log = []
    reader = lambda: SimpleNamespace(mode="catalog")
    exp = LV.B2Experiment(str(tmp_path / "ev"), CFG, cloud, bq_client=object(), reader_factory=reader, sdk_root="/sdk", acme_root=sample_root,
                          chain_runner=stub_chain_factory(cloud, mod, log), chain_module=mod, clock=Clock())
    return exp, cloud, mod, log


def test_b2_experiment_all_cases_met_with_exact_cleanup(experiment):
    exp, cloud, mod, log = experiment
    s = exp.run()
    cases = {c["case"]: c for c in s["cases"]}
    assert [c["case"] for c in s["cases"]] == ["b2-control", "historical-inflight", "historical-fresh", "fail-stale-withdrawn", "missing-runtime-aspect",
                                               "wrong-publication-pin", "wrong-seed-pin", "mixed-payload-injection", "recovery-control", "cleanup"]
    assert s["verdict"] == "B2_ALL_MET", {k: (v["status"], v.get("failed")) for k, v in cases.items()}
    P1, P2 = s["publications"]["P1"], s["publications"]["P2"]
    assert P1 == "pub_190192147fd7fd78" and P2 != P1 and P2.startswith("pub_")
    # every chain ran against the owned entry + dataset only
    assert all(l["entry"] == CFG.entry_prefix + "metrics/gross-margin" and l["ds"] == CFG.dataset for l in log) and len(log) == 9
    # control: head P1; the in-flight request resolved with head P1, the switch happened inside it, the fresh request saw P2
    assert cases["b2-control"]["chain"]["publication"]["head"]["publication_id"] == P1
    b = next(st for st in s["steps"] if st["step"] == "historical_barrier")
    assert b["fired"] and b["head_at_resolution"] == P1 and b["switch"]["state"] == "SWITCHED" and b["head_after_switch"] == P2
    assert cases["historical-inflight"]["chain"]["publication"]["head"]["publication_id"] == P1
    assert cases["historical-fresh"]["chain"]["publication"]["head"]["publication_id"] == P2 and cases["historical-fresh"]["chain"]["graph_publication"] == P1
    # stale / wrong pins refused at publication with typed reasons, no cases, then restored
    assert cases["fail-stale-withdrawn"]["chain"]["publication"]["reasons"] == ["PUBLICATION_NOT_READY:WITHDRAWN"] and cases["fail-stale-withdrawn"]["chain"]["cases"] == {}
    assert next(st for st in s["steps"] if st["step"] == "restore_p1")["state"] == "RESTORED"
    assert cases["wrong-publication-pin"]["chain"]["publication"]["reasons"][0] == "PUBLICATION_MISSING"
    assert cases["wrong-seed-pin"]["chain"]["publication"]["reasons"] == ["SEED_MISSING"]
    assert cases["missing-runtime-aspect"]["chain"]["seed_status"] == "ASPECT_MISSING"
    rm = next(st for st in s["steps"] if st["step"] == "remove_runtime_aspect")
    assert rm["runtime_aspect_present"] is False and sorted(rm["authored_aspects"]) == ["201486563047.us-central1.okf", "655216118709.global.overview"]
    # injection: raw live results retained before mutation, both mutations recorded, chain refused before the SDK
    inj = cases["mixed-payload-injection"]["injection"]
    assert [len(c["mutations"]) for c in inj["calls"]] == [1, 1, 0] and inj["calls"][2]["seed_origin"] == "injected-fixture-seed"
    assert all(Path(c["raw_retained"]["path"]).is_file() for c in inj["calls"]) and inj["calls"][0]["mutations"][0]["after"].split("|")[1] == P2
    ch = cases["mixed-payload-injection"]["chain"]
    assert ch["verdict"] == "CHAIN_BROKEN" and ch["cases"]["approved"]["receipt_invoked"] is False and ch["cases"]["declaration-mismatch"]["payload"] == "CONSISTENT"
    # cleanup: originals unchanged, owned resources gone, nothing else touched, derived tree pruned to the changed file
    cl = cases["cleanup"]
    assert cl["originals"]["status"] == "UNCHANGED" and cl["cleanup_status"] == "COMPLETE" and cl["unresolved_jobs"] == 0
    assert CFG.dataset not in cloud.datasets and not any(n.startswith(CFG.entry_prefix) for n in cloud.entries) and CFG.original_entry in cloud.entries
    assert all(o["target"].startswith(CFG.dataset) or o["target"].startswith(CFG.entry_prefix) for o in cloud.mutations())
    assert not (exp.run_dir / "derived" / "acme_retail").exists() and (exp.run_dir / "derived" / "changed_files" / "policies" / "margin-standard.md").is_file()
    assert (exp.run_dir / "b2_summary.json").is_file() and "| cleanup |" in (exp.run_dir / "b2_summary.md").read_text()
    assert json.loads((exp.run_dir / "b2_summary.json").read_text())["verdict"] == "B2_ALL_MET"
    assert mod.governed is real_governed and mod.resolve_publication is PUB.resolve_publication      # hooks were removed


def test_control_failure_blocks_the_adversaries_but_cleanup_still_runs(tmp_path, sample_root):
    cloud = FakeCloud()
    mod = SimpleNamespace(resolve_publication=PUB.resolve_publication, governed=real_governed)
    base = stub_chain_factory(cloud, mod, [])

    def incomplete(**kw):
        out = base(**kw)
        out.update(verdict="CHAIN_INCOMPLETE", broken_at="same_requester")
        return out
    exp = LV.B2Experiment(str(tmp_path / "ev"), CFG, cloud, object(), lambda: SimpleNamespace(mode="catalog"), "/sdk", sample_root, incomplete, chain_module=mod, clock=Clock())
    s = exp.run()
    cases = {c["case"]: c for c in s["cases"]}
    assert cases["b2-control"]["status"] == "NOT_REACHED" and s["verdict"] == "B2_INCOMPLETE"
    assert all(cases[n]["status"] == "BLOCKED" for n in ("historical-inflight", "fail-stale-withdrawn", "mixed-payload-injection", "recovery-control"))
    assert cases["cleanup"]["status"] == "MET" and CFG.dataset not in cloud.datasets and not any(n.startswith(CFG.entry_prefix) for n in cloud.entries)


def test_wall_cap_stops_new_chains_but_not_cleanup(tmp_path, sample_root):
    cloud = FakeCloud()
    mod = SimpleNamespace(resolve_publication=PUB.resolve_publication, governed=real_governed)
    clock = Clock()
    log = []
    base = stub_chain_factory(cloud, mod, log)

    def slow(**kw):
        clock.advance(700)
        return base(**kw)
    exp = LV.B2Experiment(str(tmp_path / "ev"), CFG, cloud, object(), lambda: SimpleNamespace(mode="catalog"), "/sdk", sample_root, slow, chain_module=mod,
                          wall_cap_s=1000, clock=clock)
    s = exp.run()
    cases = {c["case"]: c for c in s["cases"]}
    assert cases["b2-control"]["status"] == "MET" and cases["historical-inflight"]["status"] == "MET"          # 700 s, then 1400 s > cap
    assert cases["historical-fresh"]["status"] == "NOT_REACHED" and "wall cap" in cases["historical-fresh"]["error"]
    assert len(log) == 2 and cases["cleanup"]["status"] == "MET" and s["verdict"] == "B2_INCOMPLETE"


def test_graders_refuse_label_only_success():
    cfg = CFG.catalog_config("metrics/gross-margin")
    good = {"verdict": "CHAIN_CONNECTED", "seed": {"mode": "catalog", "entry": cfg.entry}, "store": {"dataset": cfg.runtime_dataset},
            "publication": {"status": "OK", "publication_id": "pub_1", "head": {"publication_id": "pub_1"}}, "graph_publication": {"publication_id": "pub_1"},
            "cases": [{"case": n, "acceptance": {"status": "MET"}, "payload": {"status": "CONSISTENT"}} for n in ("approved", "sql-substitution", "declaration-mismatch")]}
    assert LV.B2Experiment.grade_connected(good, cfg, "pub_1", "pub_1") == ("MET", [])
    mock = copy.deepcopy(good); mock["seed"]["mode"] = "catalog-mock"
    assert LV.B2Experiment.grade_connected(mock, cfg, "pub_1", "pub_1")[0] == "WRONG"
    other = copy.deepcopy(good); other["store"]["dataset"] = "okf_graph_spike_20260905"
    assert "store dataset" in LV.B2Experiment.grade_connected(other, cfg, "pub_1", "pub_1")[1][0]
    incomplete = copy.deepcopy(good); incomplete["verdict"] = "CHAIN_INCOMPLETE"
    assert LV.B2Experiment.grade_connected(incomplete, cfg, "pub_1", "pub_1")[0] == "NOT_REACHED"
    refused = {"verdict": "CHAIN_BROKEN", "broken_at": "publication", "publication": {"status": "FAIL_STALE", "reasons": ["PUBLICATION_NOT_READY:WITHDRAWN"]}, "cases": []}
    assert LV.B2Experiment.grade_refusal(refused, "publication", "FAIL_STALE", "PUBLICATION_NOT_READY") == ("MET", [])
    leaked = dict(refused, cases=[{"case": "approved", "receipt": {"invoked": True}}])
    st, failed = LV.B2Experiment.grade_refusal(leaked, "publication", "FAIL_STALE")
    assert st == "WRONG" and any("case(s) ran" in f for f in failed) and any("receipt was invoked" in f for f in failed)
    errored = {"verdict": "CHAIN_BROKEN", "broken_at": "publication", "publication": {"status": "ERROR"}, "cases": []}
    assert LV.B2Experiment.grade_refusal(errored, "publication", "FAIL_STALE")[0] == "NOT_REACHED"
    torn = {"verdict": "CHAIN_BROKEN", "cases": [{"case": "approved", "payload": {"status": "INCONSISTENT"}, "bind": {"status": "NOT_BOUND"}, "receipt": {"invoked": False}, "consume": {"decision": "REFUSED"}},
                                                  {"case": "sql-substitution", "payload": {"status": "INCONSISTENT"}, "bind": {"status": "NOT_BOUND"}, "receipt": {"invoked": False}, "consume": {"decision": "REFUSED"}},
                                                  {"case": "declaration-mismatch", "payload": {"status": "CONSISTENT"}}]}
    assert LV.B2Experiment.grade_injection(torn) == ("MET", [])
    executed = copy.deepcopy(torn); executed["cases"][0]["receipt"] = {"invoked": True}
    assert "receipt invoked" in LV.B2Experiment.grade_injection(executed)[1][0]
