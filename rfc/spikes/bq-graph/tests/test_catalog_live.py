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

from test_catalog_lifecycle import PRINCIPAL, FakeCloud, Clock


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
    assert cloud.job_state("okf_cc_j", 4) == {"state": "RUNNING", "error": None, "user_email": "op@example.test",
                                              "project": "test-project-0728-467323", "location": "US"}
    # a child chain's job is read under ITS OWN reference, not the adapter's defaults
    assert cloud.job_state("okf_cc_j", 4, project="other-project", location="EU")["project"] == "other-project"
    assert bq.calls[-1][:4] == ("get_job", "okf_cc_j", "other-project", "EU")
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


# ---------------------------------------------------------------------------- deadline INSIDE a composite adapter call
def test_a_composite_op_rechecks_the_deadline_before_the_write_after_the_schema_read(bq):
    """Astra PR42 re-review P2 #2. `BudgetedCloud` can only check on METHOD entry, but `load_rows` and `insert_row`
    are two network dispatches: read the table schema, then submit a mutating job. A schema read that consumes the
    whole budget must not be followed by a write issued anyway with the original timeout. An atomic FakeCloud cap
    test cannot see this — it needs the real adapter over a fake transport."""
    for op in ("load_rows", "insert_row"):
        clock = Clock()
        live = LV.LiveCloud(bq)
        wrapped = LV.BudgetedCloud(live, clock, 1.0)
        seen = []
        real_get, real_load, real_query = bq.get_table, bq.load_table_from_json, bq.query

        def schema(*a, **kw):
            seen.append(("get_table", kw["timeout"]))
            clock.advance(kw["timeout"])          # the read finishes exactly at the deadline
            return real_get(*a, **kw)

        def load(*a, **kw):
            seen.append(("load_table_from_json", kw["timeout"])); return real_load(*a, **kw)

        def query(*a, **kw):
            seen.append(("query", kw.get("timeout"))); return real_query(*a, **kw)
        bq.get_table, bq.load_table_from_json, bq.query = schema, load, query
        try:
            with pytest.raises(LV.BudgetExceeded) as e:
                if op == "load_rows":
                    wrapped.load_rows("okf_catalog_chain_x", "publications", [{"publication_id": "pub_1"}], job_id="j_load", timeout=5)
                else:
                    wrapped.insert_row("okf_catalog_chain_x", "publications", {"publication_id": "pub_1"}, job_id="j_insert", timeout=5)
        finally:
            bq.get_table, bq.load_table_from_json, bq.query = real_get, real_load, real_query
        assert [x[0] for x in seen] == ["get_table"], f"{op} dispatched a write past the deadline: {seen}"
        assert "was not dispatched" in str(e.value) and wrapped.remaining() == 0
        assert [r["where"] for r in wrapped.refused] == ["mid-call"]     # entry was inside budget; the WRITE was refused


def test_the_entry_check_still_clamps_and_a_dispatch_inside_budget_is_not_refused(bq):
    """The complement: the recheck must not make ordinary in-budget work fail, and the entry check still clamps a
    caller timeout down to the time actually left."""
    clock = Clock()
    wrapped = LV.BudgetedCloud(LV.LiveCloud(bq), clock, 3.0)
    wrapped.load_rows("okf_catalog_chain_x", "publications", [{"publication_id": "pub_1"}], job_id="j_ok", timeout=99)
    assert wrapped.refused == [] and bq.loads[-1]["job_id"] == "j_ok"
    assert bq.loads[-1]["timeout"] == 3.0                     # clamped to the remaining budget, not the requested 99
    assert bq.calls[-1][-1] == 3.0 if bq.calls[-1][0] == "get_table" else True


def test_two_patches_in_one_entry_update_are_two_dispatches(bq):
    """`patch_entry` issues an upsert PATCH and then a delete PATCH: the second is its own dispatch."""
    clock = Clock()
    sess = FakeSession([FakeResp(200, {})])
    live = LV.LiveCloud(bq, session=sess)
    wrapped = LV.BudgetedCloud(live, clock, 2.0)
    real = sess.request

    def timed(*a, **kw):
        clock.advance(2.0)                                     # the first PATCH uses the whole budget
        return real(*a, **kw)
    sess.request = timed
    with pytest.raises(LV.BudgetExceeded):
        wrapped.patch_entry("g/entries/e", {"aspects": {"k": {"data": {}}}}, ["k", "gone"], timeout=2)
    assert len(sess.calls) == 1                                # only the upsert went out; the delete PATCH was refused


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


def stub_chain_factory(cloud, mod, log, register_jobs=True, ref=(CFG.project, CFG.location)):
    """A chain runner with the same outward record shape as `chain.run_chain` for the fields the driver grades: seed
    parsed by the real parser from the FakeCloud entry, pin resolved by the real `resolve_publication` (looked up on
    `mod` so the barrier hook applies), retrieval through `mod.governed` (so the injection hook applies), and a
    payload guard that refuses a section id outside the pinned publication or altered SQL bytes.

    It also models the job side the driver now audits: every chain submits graph jobs (even one that refuses before any
    case) and registers them in the same fake BigQuery registry the driver reads back, publishing full `(project,
    location)` references in `job_inventory.refs`. `register_jobs=False` / a foreign `ref` model the two ways the
    identity gate must fail: a job that cannot be read back, and one whose reference is not ours."""
    def run(engine, live, sdk_root, out_dir, clients, acme_root, seed_mode, catalog_reader, catalog_cfg, **kw):
        cfg = catalog_cfg
        out = {"run_dir": out_dir, "seed": {"mode": getattr(catalog_reader, "mode", None), "entry": cfg.entry}, "catalog": {"entry": cfg.entry},
               "store": {"dataset": clients["ds"]}, "cases": [], "engine": engine, "mode": "live" if live else "hermetic"}
        log.append({"entry": cfg.entry, "ds": clients["ds"]})
        graph_jobs, receipt_jobs = [], []

        def submit(kind):
            """One job the chain submitted, registered server-side exactly as a real chain's would be."""
            jid = f"okf_{kind}_{cfg.entry[-8:]}_{len(cloud.jobs)}_{len(graph_jobs) + len(receipt_jobs)}"
            if register_jobs:
                cloud.jobs[jid] = {"state": "DONE", "error": None, "user_email": PRINCIPAL}
            (graph_jobs if kind == "cc" else receipt_jobs).append(jid)
            return jid

        def finish(verdict, broken_at=None):
            out["job_inventory"] = {"graph": list(graph_jobs), "receipt": list(receipt_jobs),
                                    "refs": {j: {"project": ref[0], "location": ref[1]} for j in graph_jobs}, "unresolved": []}
            out.update(verdict=verdict, broken_at=broken_at, evidence={"unresolved_jobs": 0})
            # the real `same_requester` gives up when either leg is empty: an early or graph-only refusal is UNKNOWN/NOT_RUN
            out["same_requester"] = {"status": "SAME"} if graph_jobs and receipt_jobs else \
                {"status": "UNKNOWN" if graph_jobs else "NOT_RUN", "reason": f"nothing to compare: graph={len(graph_jobs)} receipt={len(receipt_jobs)}"}
            return out
        entry = cloud.entries.get(cfg.entry)
        if entry is None:
            out["seed"].update(status="ENTRY_NOT_FOUND"); return finish("CHAIN_BROKEN", "seed")
        if cfg.aspect_key not in (entry.get("aspects") or {}):
            out["seed"].update(status="ASPECT_MISSING"); return finish("CHAIN_BROKEN", "seed")   # refused before any job
        pin = parse_pin(entry, cfg)
        if not isinstance(pin, CatalogPin):
            out["seed"].update(status=pin.status); return finish("CHAIN_BROKEN", "seed")
        out["seed"]["status"] = "OK"
        submit("cc")                                          # pin resolution reads the retained rows: a real job
        res = mod.resolve_publication(FakeStore(cloud, clients["ds"]), pin)
        out["publication"] = {"status": res["status"], "publication_id": pin.publication_id, "reasons": res.get("reasons"), "head": res.get("head")}
        if res["status"] != "OK":
            return finish("CHAIN_BROKEN", "publication")      # graph jobs, no receipt: same_requester cannot speak
        pub = pin.publication_id
        out["graph_publication"] = {"publication_id": pub}
        for case in ("approved", "sql-substitution", "declaration-mismatch"):
            seed = ConceptSeed(f"{pin.bundle_id}|{pub}|Concept|metrics/revenue", origin="injected-fixture-seed") if case == "declaration-mismatch" else pin.seed("catalog")
            submit("cc")                                      # retrieval + declaration jobs for this case
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
                rjid = submit("rcpt")
                c.update(bind={"status": "BOUND"},
                         receipt={"invoked": True, "output": {"verdict": verdict},
                                  "receipt": {"job": {"job_id": rjid, "project": ref[0], "location": ref[1]}}},
                         consume={"decision": "RELEASED" if case == "approved" else "REFUSED"}, acceptance={"status": "MET"})
            out["cases"].append(c)
        wrong = [c["case"] for c in out["cases"] if c["acceptance"]["status"] != "MET"]
        return finish("CHAIN_BROKEN" if wrong else "CHAIN_CONNECTED", wrong[0] if wrong else None)
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
                                               "wrong-publication-pin", "wrong-seed-pin", "mixed-payload-injection", "recovery-control", "cleanup",
                                               "job-identity"]
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
    assert cl["originals"]["status"] == "UNCHANGED" and cl["cleanup_status"] == "COMPLETE" and cl["unresolved_operations"] == 0
    # operations are counted separately from BigQuery jobs: conflating them is what mis-stated the run's job count
    assert cl["counts"] == {"lifecycle_operations": 78, "lifecycle_bigquery_jobs": 48}
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


def _timestamped(cloud, clock):
    """Stamp every recorded cloud op with the elapsed time, so a test can ask *when* a mutation was issued."""
    rec = cloud._rec

    def timed(*a, **kw):
        rec(*a, **kw)
        cloud.ops[-1]["at"] = clock.t - 1_000_000
    cloud._rec = timed
    return cloud


def test_wall_cap_refuses_new_mutations_and_leaves_cleanup_its_own_budget(tmp_path, sample_root):
    """Astra PR42 P2 #1. The old cap only skipped the next *chain*: the experiment kept advancing the head, withdrawing
    and restoring P1 and patching the entry long after expiry. Now the budget bounds the operations themselves."""
    cloud = FakeCloud()
    mod = SimpleNamespace(resolve_publication=PUB.resolve_publication, governed=real_governed)
    clock = Clock()
    log = []
    _timestamped(cloud, clock)
    base = stub_chain_factory(cloud, mod, log)

    def slow(**kw):
        clock.advance(700)
        return base(**kw)
    exp = LV.B2Experiment(str(tmp_path / "ev"), CFG, cloud, object(), lambda: SimpleNamespace(mode="catalog"), "/sdk", sample_root, slow, chain_module=mod,
                          wall_cap_s=1000, clock=clock, cleanup_cap_s=300)
    s = exp.run()
    cases = {c["case"]: c for c in s["cases"]}
    assert cases["b2-control"]["status"] == "MET"                       # ran inside the cap (0 s -> 700 s)
    # the second chain pushed elapsed to 1400 s; the in-flight head switch that follows it is refused, not performed
    assert cases["historical-inflight"]["status"] in ("NOT_REACHED", "BLOCKED")
    assert s["verdict"] == "B2_INCOMPLETE"
    assert "budget exhausted" in next(st for st in s["steps"] if st["step"] == "experiment_budget_exhausted")["error"]
    refused = s["budget"]["refused_after_cap"]
    assert refused and all(r["phase"] == "experiment" for r in refused)     # the teardown phase refuses nothing
    # NOTHING experimental mutated the cloud after the cap: the only post-cap mutations are the teardown's
    post_cap = [o for o in cloud.mutations() if o["at"] > 1000]
    assert {o["op"] for o in post_cap} <= {"delete_entry", "delete_dataset"}, post_cap
    # ... and teardown still completed, on its own separately opened budget
    assert cases["cleanup"]["status"] == "MET" and CFG.dataset not in cloud.datasets
    assert not any(n.startswith(CFG.entry_prefix) for n in cloud.entries)
    phase = next(st for st in s["steps"] if st["step"] == "cleanup_phase_opened")
    assert phase["phase"] == "cleanup" and phase["budget_s"] == 300


def test_a_chain_is_not_started_without_enough_budget_left_to_finish(tmp_path, sample_root):
    """`run_chain` takes no deadline, so the driver cannot interrupt one already running; it refuses to start one that
    cannot fit in what is left of the cap, and says so."""
    cloud = FakeCloud()
    mod = SimpleNamespace(resolve_publication=PUB.resolve_publication, governed=real_governed)
    clock = Clock()
    log = []
    base = stub_chain_factory(cloud, mod, log)

    def slow(**kw):
        clock.advance(400)
        return base(**kw)
    exp = LV.B2Experiment(str(tmp_path / "ev"), CFG, cloud, object(), lambda: SimpleNamespace(mode="catalog"), "/sdk", sample_root, slow, chain_module=mod,
                          wall_cap_s=1000, chain_min_s=700, clock=clock)
    s = exp.run()
    cases = {c["case"]: c for c in s["cases"]}
    assert cases["b2-control"]["status"] == "MET" and len(log) == 1               # one chain ran; 600 s left < 700 s needed
    assert cases["historical-inflight"]["status"] == "NOT_REACHED"
    assert "a chain needs at least 700s" in cases["historical-inflight"]["error"]
    assert cases["cleanup"]["status"] == "MET" and s["verdict"] == "B2_INCOMPLETE"


def test_a_correct_refusal_with_unknown_job_identity_is_not_met(tmp_path, sample_root):
    """Astra PR42 P1. The mixed-payload and early-refusal chains are exactly the ones the chain's own
    `same_requester` cannot speak for (it needs BOTH legs non-empty), so the strongest negatives had the weakest
    identity evidence. Here their jobs cannot be read back: the BEHAVIOUR is still graded correct, but the case is
    no longer allowed to claim MET."""
    cloud = FakeCloud()
    mod = SimpleNamespace(resolve_publication=PUB.resolve_publication, governed=real_governed)
    # register_jobs=False: the chains submit jobs whose server state this run can never establish
    exp = LV.B2Experiment(str(tmp_path / "ev"), CFG, cloud, object(), lambda: SimpleNamespace(mode="catalog"), "/sdk", sample_root,
                          stub_chain_factory(cloud, mod, [], register_jobs=False), chain_module=mod, clock=Clock())
    s = exp.run()
    cases = {c["case"]: c for c in s["cases"]}
    for name in ("b2-control", "fail-stale-withdrawn", "wrong-publication-pin", "mixed-payload-injection"):
        assert cases[name]["behaviour"] == "MET", (name, cases[name].get("failed"))     # the boundary still did the right thing
        assert cases[name]["status"] == "NOT_REACHED"                                    # ... but the evidence is incomplete
        assert cases[name]["identity"]["status"] == "INCOMPLETE"
        assert any("not read back" in r for r in cases[name]["identity"]["reasons"])
    assert cases["job-identity"]["status"] == "NOT_REACHED" and s["verdict"] == "B2_INCOMPLETE"
    # the missing-aspect chain submits no job at all: nothing unidentified, so its evidence is complete
    assert cases["missing-runtime-aspect"]["identity"]["status"] == "COMPLETE" and cases["missing-runtime-aspect"]["identity"]["jobs"] == 0


def test_the_identity_audit_covers_graph_only_refusals_and_a_foreign_reference(tmp_path, sample_root):
    """Two things the chain's own identity check cannot do: speak for a refusal that submitted graph jobs and no
    receipt, and notice a job whose (project, location) is not ours."""
    cloud = FakeCloud()
    mod = SimpleNamespace(resolve_publication=PUB.resolve_publication, governed=real_governed)
    exp = LV.B2Experiment(str(tmp_path / "ev"), CFG, cloud, object(), lambda: SimpleNamespace(mode="catalog"), "/sdk", sample_root,
                          stub_chain_factory(cloud, mod, [], ref=("someone-elses-project", "EU")), chain_module=mod, clock=Clock())
    s = exp.run()
    cases = {c["case"]: c for c in s["cases"]}
    # every chain job carries a full reference, so nothing is "missing" -- but it resolves to no job we can read
    by_chain = s["job_identity"]["by_chain"]
    assert by_chain["fail-stale-withdrawn"]["status"] == "INCOMPLETE"
    assert by_chain["fail-stale-withdrawn"]["jobs"] > 0 and not by_chain["fail-stale-withdrawn"]["missing_reference"]
    assert cases["fail-stale-withdrawn"]["behaviour"] == "MET" and cases["fail-stale-withdrawn"]["status"] == "NOT_REACHED"
    # the driver's own lifecycle jobs are under our reference and stay complete
    assert s["job_identity"]["lifecycle"]["status"] == "COMPLETE"
    assert s["job_identity"]["lifecycle"]["principals"] == [PRINCIPAL]
    audit = json.loads((exp.run_dir / "job_identity.json").read_text())
    assert audit["counts"]["total_jobs"] == len(audit["jobs"]) and audit["counts"]["lifecycle_bigquery_jobs"] < audit["counts"]["lifecycle_operations"]
    assert {j["source"] for j in audit["jobs"]} >= {"lifecycle", "chain:b2-control", "chain:fail-stale-withdrawn"}


def test_the_identity_audit_is_bounded_by_the_cleanup_budget_and_keeps_unread_jobs(tmp_path, sample_root):
    """Astra PR42 re-review P2 #1. The audit is read-only but not free: one `jobs.get` per job at the per-operation
    timeout can outlast the whole teardown allowance. When the cleanup budget runs out it must stop dispatching and
    retain the rest as submitted-but-unread — which leaves the gate INCOMPLETE — and it must never relabel a job that
    WAS submitted as `NOT_SUBMITTED` just because nobody got to look at it."""
    cloud, clock = FakeCloud(), Clock()
    mod = SimpleNamespace(resolve_publication=PUB.resolve_publication, governed=real_governed)
    real_read, reads = cloud.job_state, []

    def slow_read(job_id, timeout, project=None, location=None):
        reads.append({"job_id": job_id, "at": clock.t - 1_000_000, "timeout": timeout})
        clock.advance(timeout)                       # each read takes exactly the timeout it was granted
        return real_read(job_id, timeout, project=project, location=location)
    cloud.job_state = slow_read
    exp = LV.B2Experiment(str(tmp_path / "ev"), CFG, cloud, object(), lambda: SimpleNamespace(mode="catalog"), "/sdk", sample_root,
                          stub_chain_factory(cloud, mod, []), chain_module=mod, wall_cap_s=1200, cleanup_cap_s=30, clock=clock)
    s = exp.run()
    phase = next(st for st in s["steps"] if st["step"] == "cleanup_phase_opened")
    deadline = phase["elapsed_s"] + phase["budget_s"]
    audit = json.loads((exp.run_dir / "job_identity.json").read_text())
    # nothing is dispatched at or after the cleanup deadline, and the run stops there rather than at 79 x 5 s
    assert reads and not [r for r in reads if r["at"] >= deadline], reads
    assert s["elapsed_s"] <= deadline and len(reads) < audit["counts"]["total_jobs"]
    # every job is still listed, with its full reference; the unread ones are unread, NOT "not submitted"
    unread = [j for j in audit["jobs"] if j["read"] == "NOT_READ_BUDGET"]
    assert unread and audit["counts"]["unread_budget"] == len(unread)
    assert all(j.get("project") and j.get("location") for j in unread)
    assert all(j["state"] is None and j["user_email"] is None for j in unread)
    assert not any(j["state"] == "NOT_SUBMITTED" for j in unread)
    # ... so the gate cannot claim completeness, and neither can the run
    assert audit["overall"]["status"] == "INCOMPLETE"
    assert any("submitted but unread" in r for r in audit["overall"]["reasons"])
    assert s["verdict"] != "B2_ALL_MET" and next(c for c in s["cases"] if c["case"] == "job-identity")["status"] == "NOT_REACHED"
    # the teardown itself still completed: the owned resources are gone
    assert CFG.dataset not in cloud.datasets and not any(n.startswith(CFG.entry_prefix) for n in cloud.entries)
    assert next(c for c in s["cases"] if c["case"] == "cleanup")["behaviour"] == "MET"


def test_a_never_dispatched_job_is_distinguished_from_one_the_audit_could_not_reach(tmp_path, sample_root):
    """Two different unknowns that must not be conflated: `NOT_SUBMITTED` is established locally (the job was refused
    before the send), while `NOT_READ_BUDGET` means the job exists and we ran out of time to look."""
    cloud, clock = FakeCloud(), Clock()
    mod = SimpleNamespace(resolve_publication=PUB.resolve_publication, governed=real_governed)
    exp = LV.B2Experiment(str(tmp_path / "ev"), CFG, cloud, object(), lambda: SimpleNamespace(mode="catalog"), "/sdk", sample_root,
                          stub_chain_factory(cloud, mod, []), chain_module=mod, clock=clock)
    exp._setup()
    # one journal entry that never reached the server, one that did
    e = exp.journal.intend("refused_write", "a write the budget refused", "cloud", actual=True)
    exp.journal.submitted(e, job_id="okf_cc_never_sent", project=CFG.project, location=CFG.location)
    exp.journal.terminal(e, "NOT_SUBMITTED", error="BudgetExceeded: not dispatched")
    audit = exp._job_audit()
    never = next(j for j in audit["jobs"] if j["job_id"] == "okf_cc_never_sent")
    assert never["read"] == "NOT_DISPATCHED" and never["state"] == "NOT_SUBMITTED"
    # a never-dispatched id carries no identity requirement, so the lifecycle gate is unaffected by it
    assert audit["lifecycle"]["status"] == "COMPLETE" and "okf_cc_never_sent" in audit["lifecycle"]["not_dispatched"]
    assert "okf_cc_never_sent" not in audit["lifecycle"]["not_read_back"]


def test_an_early_refusal_chain_hides_its_jobs_in_job_inventory_but_not_in_its_journal():
    """The sharpest form of Astra PR42 P1. A chain that refuses at `publication` returns through `_broken()`, which
    never builds `job_inventory` at all — yet it already submitted its pin-resolution, seed-visibility and
    head-observation jobs. Reading only `job_inventory` makes those jobs invisible, so the audit reads the chain's own
    journal as well. (In the committed live run this is exactly 9 jobs across three refusal chains.)"""
    early_refusal = {                      # the shape `chain._broken()` actually produces
        "verdict": "CHAIN_BROKEN", "broken_at": "publication", "cases": [],
        "publication": {"status": "FAIL_STALE", "reasons": ["PUBLICATION_NOT_READY:WITHDRAWN"]},
        "same_requester": {"status": "NOT_RUN", "reason": "refused at publication before any case executed"},
        "journal": {"jobs": [{"role": r, "job_id": f"okf_cc_x_{r}", "project": "p", "location": "US", "state": "DONE", "terminal": True}
                             for r in ("pin_resolution", "seed_visibility", "observed_head")]}}
    refs = LV.B2Experiment._chain_job_refs("fail-stale-withdrawn", early_refusal)
    assert "job_inventory" not in early_refusal and len(refs) == 3
    assert {r["role"] for r in refs} == {"pin_resolution", "seed_visibility", "observed_head"}
    assert all(r["project"] == "p" and r["location"] == "US" and r["dispatched"] for r in refs)
    # ... and a chain that DOES publish an inventory is still read from it, receipt leg included, without duplication
    full = {"verdict": "CHAIN_CONNECTED",
            "job_inventory": {"graph": ["g1", "okf_cc_x_pin_resolution"], "receipt": ["r1"], "refs": {"g1": {"project": "p", "location": "US"}}},
            "journal": {"jobs": [{"role": "pin_resolution", "job_id": "okf_cc_x_pin_resolution", "project": "p", "location": "US", "state": "DONE"}]},
            "cases": [{"case": "approved", "receipt": {"invoked": True, "receipt": {"job": {"job_id": "r1", "project": "p", "location": "US"}}}}]}
    got = LV.B2Experiment._chain_job_refs("b2-control", full)
    assert [r["job_id"] for r in got] == ["okf_cc_x_pin_resolution", "g1", "r1"]
    assert [r["leg"] for r in got] == ["graph", "graph", "receipt"]


def test_an_absent_sdk_is_not_reached_with_the_blocker_named(tmp_path, sample_root):
    """Astra PR42 P2 #2. An outage at a prerequisite stage is not a boundary that behaved incorrectly: the control is
    NOT_REACHED with the SDK named, the later cases are BLOCKED, and nothing is graded WRONG."""
    cloud = FakeCloud()
    mod = SimpleNamespace(resolve_publication=PUB.resolve_publication, governed=real_governed)

    def sdk_missing(**kw):
        return {"run_dir": kw["out_dir"], "seed": {"mode": "catalog", "status": "PENDING"}, "cases": [],
                "sdk": {"status": "ERROR", "error": "FileNotFoundError: no such SDK checkout"},
                "verdict": "CHAIN_BROKEN", "broken_at": "sdk", "same_requester": {"status": "NOT_RUN"},
                "job_inventory": {"graph": [], "receipt": [], "refs": {}, "unresolved": []}}
    exp = LV.B2Experiment(str(tmp_path / "ev"), CFG, cloud, object(), lambda: SimpleNamespace(mode="catalog"), "/sdk", sample_root,
                          sdk_missing, chain_module=mod, clock=Clock())
    s = exp.run()
    cases = {c["case"]: c for c in s["cases"]}
    assert cases["b2-control"]["status"] == "NOT_REACHED" and cases["b2-control"]["behaviour"] == "NOT_REACHED"
    assert any("BLOCKER sdk unavailable" in f for f in cases["b2-control"]["failed"])
    assert all(cases[n]["status"] == "BLOCKED" for n in ("historical-inflight", "fail-stale-withdrawn", "mixed-payload-injection", "recovery-control"))
    assert not any(c["status"] == "WRONG" for c in s["cases"]) and s["verdict"] == "B2_INCOMPLETE"
    assert "sdk unavailable" in (next(st for st in s["steps"] if st["step"] == "experiment_aborted")["error"] or "")
    assert cases["cleanup"]["status"] == "MET" and CFG.dataset not in cloud.datasets


def test_a_reached_boundary_that_answers_wrongly_is_still_wrong(tmp_path, sample_root):
    """The complement: `WRONG` must not become unreachable. A control that reaches every stage and serves the wrong
    publication has no stage error, so it stays WRONG."""
    cloud = FakeCloud()
    mod = SimpleNamespace(resolve_publication=PUB.resolve_publication, governed=real_governed)
    base = stub_chain_factory(cloud, mod, [])

    def wrong_pub(**kw):
        out = base(**kw)
        out["graph_publication"] = {"publication_id": "pub_something_else"}
        return out
    exp = LV.B2Experiment(str(tmp_path / "ev"), CFG, cloud, object(), lambda: SimpleNamespace(mode="catalog"), "/sdk", sample_root,
                          wrong_pub, chain_module=mod, clock=Clock())
    s = exp.run()
    cases = {c["case"]: c for c in s["cases"]}
    assert cases["b2-control"]["status"] == "WRONG" and s["verdict"] == "B2_WRONG"
    assert not any("BLOCKER" in f for f in cases["b2-control"]["failed"])


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
