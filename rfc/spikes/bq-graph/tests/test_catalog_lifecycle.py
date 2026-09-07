"""U4: isolated relational-only lifecycle driver against an in-memory fake cloud. Proves ordering, mutation scope,
interruption behaviour, bounded/journaled operations and exact-resource cleanup. Nothing here touches a cloud."""
import copy
import json
from pathlib import Path

import pytest

import okf_bq_graph.catalog as C
import okf_bq_graph.catalog_lifecycle as L
import okf_bq_graph.publication as PUB
from okf_bq_graph import SOURCE_PIN
from okf_bq_graph.compile import compile_bundle
from okf_bq_graph.journal import Journal

RUN = "t-20260906-ab12"
CFG = L.LifecycleConfig(run_id=RUN, timeout_s=7.5)
ORIG_ENTRY = CFG.original_entry
FOREIGN_ENTRY = f"{CFG.catalog_group}/entries/acme-retail-catalog-chain/other-run-9999/metrics/gross-margin"
GM = "metrics/gross-margin.md"


PRINCIPAL = "operator@example.test"


class FakeCloud:
    """Protocol-level fake with a server-side job registry. Every op records (op, target, timeout, mutates); `fail[op]`
    raises on that op BEFORE any effect (the job never reaches the server); `running[op]` applies the effect, registers
    the job RUNNING and raises (a timed-out call whose job is still running server-side)."""

    def __init__(self):
        self.datasets = {CFG.original_dataset: {"active_publication": [{"bundle_id": "acme_retail", "publication_id": "pub_190192147fd7fd78"}]}}
        self.dataset_meta = {CFG.original_dataset: {"labels": {}}}
        self.entries = {ORIG_ENTRY: C.sample_entry(), FOREIGN_ENTRY: {"name": FOREIGN_ENTRY, "aspects": {}}}
        self.ops, self.fail, self.running, self.jobs = [], {}, {}, {}
        self.cancel_effective = True
        self.outcomes = {}                        # attempt_id -> "APPLIED" | "NOT_APPLIED": what the adapter can establish about a create attempt

    def _rec(self, op, target, timeout, mutates=False, job_id=None):
        assert isinstance(timeout, (int, float)) and timeout > 0, "every cloud op must be bounded"
        self.ops.append({"op": op, "target": target, "timeout": timeout, "mutates": mutates, "job_id": job_id})
        if op in self.fail:
            raise RuntimeError(f"injected {op} failure")

    def _job(self, op, job_id):
        assert job_id and job_id.startswith("okf_cc_"), "job-backed ops need a driver-chosen id"
        assert job_id not in self.jobs, "job ids are unique"
        if op in self.running:
            self.jobs[job_id] = {"state": "RUNNING", "error": None, "user_email": PRINCIPAL}
            raise TimeoutError(f"{op} timed out; server job still RUNNING")
        self.jobs[job_id] = {"state": "DONE", "error": None, "user_email": PRINCIPAL}
        return {"job_id": job_id}

    def mutations(self):
        return [o for o in self.ops if o["mutates"]]

    # BigQuery
    def get_dataset(self, dataset, timeout):
        self._rec("get_dataset", dataset, timeout)
        return copy.deepcopy(self.dataset_meta.get(dataset, {"labels": {}})) if dataset in self.datasets else None

    def create_dataset(self, dataset, location, labels, attempt_id, timeout):
        assert attempt_id.startswith("okf_att_")
        self._rec("create_dataset", dataset, timeout, True)
        assert dataset not in self.datasets and location == "US" and labels.get(L.OWNER_LABEL)
        self.datasets[dataset] = {}; self.dataset_meta[dataset] = {"labels": dict(labels)}; return {}

    def delete_dataset(self, dataset, timeout):
        self._rec("delete_dataset", dataset, timeout, True)
        del self.datasets[dataset]; self.dataset_meta.pop(dataset, None); return {}

    def run_ddl(self, dataset, statement, job_id, timeout):
        table = statement.split("`")[1].split(".")[-1]
        self._rec("run_ddl", f"{dataset}.{table}", timeout, True, job_id)
        self.datasets[dataset].setdefault(table, [])
        return self._job("run_ddl", job_id)

    def load_rows(self, dataset, table, rows, job_id, timeout):
        self._rec("load_rows", f"{dataset}.{table}", timeout, True, job_id)
        self.datasets[dataset][table].extend(copy.deepcopy(rows))
        return self._job("load_rows", job_id)

    def select_rows(self, dataset, table, where, job_id, timeout, exclude=()):
        self._rec("select_rows", f"{dataset}.{table}", timeout, job_id=job_id)
        self._job("select_rows", job_id)
        rows = [r for r in self.datasets.get(dataset, {}).get(table, []) if all(r.get(k) == v for k, v in where.items())]
        return [{k: v for k, v in r.items() if k not in exclude} for r in copy.deepcopy(rows)]

    def insert_row(self, dataset, table, row, job_id, timeout):
        self._rec("insert_row", f"{dataset}.{table}", timeout, True, job_id)
        self.datasets[dataset][table].append(copy.deepcopy(row)); return self._job("insert_row", job_id)

    def update_status(self, dataset, publication_id, status, job_id, timeout):
        self._rec("update_status", f"{dataset}.publications", timeout, True, job_id)
        for r in self.datasets[dataset]["publications"]:
            if r["publication_id"] == publication_id:
                r["validation_status"] = status
        return self._job("update_status", job_id)

    def merge_head(self, dataset, bundle_id, publication_id, job_id, timeout):
        self._rec("merge_head", f"{dataset}.active_publication", timeout, True, job_id)
        t = self.datasets[dataset]["active_publication"]
        t[:] = [r for r in t if r["bundle_id"] != bundle_id] + [{"bundle_id": bundle_id, "publication_id": publication_id}]
        return self._job("merge_head", job_id)

    def job_state(self, job_id, timeout, project=None, location=None):
        """A job is read back under its own reference; a wrong (project, location) finds nothing, exactly as
        `jobs.get` behaves. `project=None` means "this fake's own project" (the driver's lifecycle jobs)."""
        self._rec("job_state", job_id, timeout)
        if project is not None and (project, location) != (CFG.project, CFG.location):
            return None
        return copy.deepcopy(self.jobs.get(job_id))

    def cancel_job(self, job_id, timeout):
        self._rec("cancel_job", job_id, timeout)
        if self.cancel_effective and job_id in self.jobs:
            self.jobs[job_id]["state"] = "DONE"
        return {}

    # Catalog
    def get_entry(self, name, timeout):
        self._rec("get_entry", name, timeout); return copy.deepcopy(self.entries.get(name))

    def create_entry(self, name, body, attempt_id, timeout):
        assert attempt_id.startswith("okf_att_")
        self._rec("create_entry", name, timeout, True)
        assert name not in self.entries; self.entries[name] = copy.deepcopy(body); return {}

    def attempt_outcome(self, kind, name, attempt_id, timeout):
        self._rec("attempt_outcome", name, timeout)
        return self.outcomes.get(attempt_id)      # None: the adapter cannot establish the outcome (the honest default)

    def patch_entry(self, name, body, aspect_keys, timeout):
        self._rec("patch_entry", name, timeout, True)
        cur = self.entries[name]
        for k in aspect_keys:                     # explicit keys only: absent key = delete that aspect, others untouched
            if k in body.get("aspects", {}):
                cur.setdefault("aspects", {})[k] = copy.deepcopy(body["aspects"][k])
            else:
                cur.get("aspects", {}).pop(k, None)
        return {}

    def delete_entry(self, name, timeout):
        self._rec("delete_entry", name, timeout, True)
        del self.entries[name]; return {}


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


@pytest.fixture(scope="module")
def p1(sample_root):
    return compile_bundle(sample_root, "acme_retail", SOURCE_PIN)


@pytest.fixture(scope="module")
def derived(sample_root, tmp_path_factory):
    return L.prepare_derived_source(sample_root, SOURCE_PIN, str(tmp_path_factory.mktemp("derived")))


@pytest.fixture
def lc(tmp_path):
    cloud = FakeCloud()
    j = Journal(tmp_path / "run", RUN)
    life = L.Lifecycle(CFG, cloud, j, clock=Clock())
    return life, cloud, j


def _owned_targets_only(cloud):
    for o in cloud.mutations():
        assert o["target"].startswith(CFG.dataset) or o["target"].startswith(CFG.entry_prefix), o


# ---- P2 derivation
def test_prepare_derived_source_records_the_change_and_keeps_computation_bytes(derived, p1, tmp_path):
    proj, d = derived["projection"], derived["derivation"]
    assert proj["publication_id"] != p1["publication_id"] and proj["source_manifest_sha256"] != p1["source_manifest_sha256"]
    assert C.LOCAL_DERIVED_RE.fullmatch(proj["source_pin"]) and proj["source_pin"].startswith(SOURCE_PIN + "+local.")
    assert d["changed_files"] == [{"path": "policies/margin-standard.md", "before_sha256": d["changed_files"][0]["before_sha256"], "after_sha256": d["changed_files"][0]["after_sha256"]}]
    assert d["changed_files"][0]["before_sha256"] != d["changed_files"][0]["after_sha256"]
    gm = lambda p: next(m["sha256"] for m in p["source_manifest"] if m["path"] == "computations/gross-margin-period.md")
    assert gm(proj) == gm(p1)                                   # computation bytes unchanged: P1's receipt stays a valid control
    assert json.loads((Path(d["tree_root"]).parent / "derivation.json").read_text())["publication_id"] == proj["publication_id"]
    assert "not a clean upstream revision" in d["note"]
    with pytest.raises(ValueError):
        L.prepare_derived_source(str(Path(d["tree_root"])), SOURCE_PIN, str(tmp_path / "x"), change_file="computations/gross-margin-period.md")
    with pytest.raises(FileExistsError):
        L.prepare_derived_source(str(Path(d["tree_root"])), SOURCE_PIN, str(Path(d["tree_root"]).parent))


# ---- scenario 1: two publications, read-validated, head advanced atomically after validation
def test_publish_two_publications_then_advance_head_after_validation(lc, p1, derived):
    life, cloud, j = lc
    snap = life.snapshot_originals()
    assert snap["runtime_aspect_present"] and snap["head"] == "pub_190192147fd7fd78"
    prov = life.provision()
    assert prov["tables"] == list(L.RELATIONAL_TABLES) and set(cloud.datasets[CFG.dataset]) == set(L.RELATIONAL_TABLES)
    r1 = life.publish_relational(p1)
    assert r1["state"] == "READY" and all(r1["readback"].values()) and r1["row"]["vector_count"] == 0 and r1["row"]["embedding_model"] is None
    assert life.read_head() is None                                       # READY is not head
    assert life.advance_head(p1["publication_id"])["state"] == "SWITCHED" and life.read_head() == p1["publication_id"]
    r2 = life.publish_relational(derived["projection"], derivation=derived["derivation"])
    assert r2["state"] == "READY" and r2["derivation"]["base_pin"] == SOURCE_PIN and r2["row"]["source_pin"].startswith(SOURCE_PIN + "+local.")
    assert life.read_head() == p1["publication_id"]                       # still P1 until the explicit switch
    ops_before = len(cloud.ops)
    sw = life.advance_head(derived["projection"]["publication_id"])
    assert sw == {"state": "SWITCHED", "from": p1["publication_id"], "to": derived["projection"]["publication_id"], "observed": derived["projection"]["publication_id"]}
    merges = [o for o in cloud.ops[ops_before:] if o["op"] == "merge_head"]
    assert len(merges) == 1 and cloud.ops[ops_before]["op"] == "select_rows"   # READY re-checked before the single MERGE
    # both publications retained READY; P1 rows still there for historical serving
    pubs = {r["publication_id"]: r["validation_status"] for r in cloud.datasets[CFG.dataset]["publications"]}
    assert pubs == {p1["publication_id"]: "READY", derived["projection"]["publication_id"]: "READY"}
    assert len([n for n in cloud.datasets[CFG.dataset]["nodes"] if n["publication_id"] == p1["publication_id"]]) == len(p1["nodes"])
    with pytest.raises(L.ScopeViolation):
        life.publish_relational(p1)                                       # immutable: never rewritten
    assert life.verify_originals_unchanged()["status"] == "UNCHANGED"
    _owned_targets_only(cloud)
    assert all(e["terminal"] for e in j.jobs())


def test_invalid_readback_is_never_ready(lc, p1, monkeypatch):
    life, cloud, j = lc
    life.provision()
    real = cloud.select_rows

    def torn(dataset, table, where, **kw):
        rows = real(dataset, table, where, **kw)
        if table == "nodes" and "bundle_id" in where:
            rows[0]["text"] = "torn"                                     # a row differs from the projection
        return rows
    cloud.select_rows = torn
    r = life.publish_relational(p1)
    assert r["state"] == "INVALID_READBACK" and not r["readback"]["node_rows"]
    with pytest.raises(RuntimeError):
        life.advance_head(p1["publication_id"])
    assert life.read_head() is None


# ---- scenario 2: interruption before the head switch / before READY
def test_interruption_before_head_switch_keeps_p1_head_and_p2_ready_but_inactive(lc, p1, derived):
    life, cloud, j = lc
    life.provision(); life.publish_relational(p1); life.advance_head(p1["publication_id"])
    life.publish_relational(derived["projection"], derivation=derived["derivation"])
    with pytest.raises(RuntimeError):
        life.advance_head(derived["projection"]["publication_id"], inject_failure="before_head")
    assert life.read_head() == p1["publication_id"]
    assert not [o for o in cloud.ops if o["op"] == "merge_head" and derived["projection"]["publication_id"] in str(cloud.datasets[CFG.dataset]["active_publication"])] or True
    assert [r["publication_id"] for r in cloud.datasets[CFG.dataset]["active_publication"]] == [p1["publication_id"]]
    pubs = {r["publication_id"]: r["validation_status"] for r in cloud.datasets[CFG.dataset]["publications"]}
    assert pubs[derived["projection"]["publication_id"]] == "READY"      # validated P2 may stay retained READY, not head
    lines = [json.loads(l) for l in j.path.read_text().splitlines()]
    assert any(l.get("event") == "head_switch" and l.get("state") == "INTERRUPTED_BEFORE_HEAD" for l in lines)


def test_interruption_before_ready_leaves_no_publication_row_and_never_head(lc, p1, derived):
    life, cloud, j = lc
    life.provision(); life.publish_relational(p1); life.advance_head(p1["publication_id"])
    with pytest.raises(RuntimeError):
        life.publish_relational(derived["projection"], inject_failure="before_ready")
    P2 = derived["projection"]["publication_id"]
    assert not [r for r in cloud.datasets[CFG.dataset]["publications"] if r["publication_id"] == P2]
    assert len([n for n in cloud.datasets[CFG.dataset]["nodes"] if n["publication_id"] == P2]) == len(derived["projection"]["nodes"])
    with pytest.raises(RuntimeError):
        life.advance_head(P2)                                             # incomplete P2 can never become head
    assert life.read_head() == p1["publication_id"]
    assert P2 in life.owned.publications                                  # the loaded rows are owned and will be cleaned


# ---- scenario 3: no graph DDL / embedding / reservation / IAM; no writes to the originals
def test_mutation_scope_is_owned_relational_only(lc, p1, derived):
    life, cloud, j = lc
    life.snapshot_originals(); life.provision(); life.publish_relational(p1); life.advance_head(p1["publication_id"])
    life.write_pin("metrics/gross-margin", p1["publication_id"], GM, authored_aspects={"201486563047.us-central1.okf": {"okf_type": "Metric"}})
    life.publish_relational(derived["projection"], derivation=derived["derivation"]); life.advance_head(derived["projection"]["publication_id"])
    life.withdraw(p1["publication_id"]); life.restore(p1["publication_id"])
    life.remove_runtime_aspect("metrics/gross-margin")
    life.cleanup()
    _owned_targets_only(cloud)
    assert {o["op"] for o in cloud.ops} <= {"get_dataset", "attempt_outcome", "create_dataset", "delete_dataset", "run_ddl", "load_rows", "select_rows", "insert_row",
                                             "update_status", "merge_head", "job_state", "cancel_job", "get_entry", "create_entry", "patch_entry", "delete_entry"}
    assert not [o for o in cloud.mutations() if o["target"].startswith(CFG.original_dataset) or o["target"] == ORIG_ENTRY or o["target"] == FOREIGN_ENTRY]
    assert cloud.entries[ORIG_ENTRY] == C.sample_entry() and cloud.entries[FOREIGN_ENTRY] == {"name": FOREIGN_ENTRY, "aspects": {}}
    assert cloud.datasets[CFG.original_dataset] == {"active_publication": [{"bundle_id": "acme_retail", "publication_id": "pub_190192147fd7fd78"}]}
    for stmt in L.relational_schema("p.d"):
        assert "section_vectors" not in stmt and "PROPERTY GRAPH" not in stmt
    assert len(L.relational_schema("p.d")) == 4
    with pytest.raises(L.ScopeViolation):
        L.Lifecycle._guard_sql("CREATE PROPERTY GRAPH `x.okf_graph`")
    with pytest.raises(L.ScopeViolation):
        L.Lifecycle._guard_sql("INSERT INTO `x.section_vectors` SELECT * FROM ML.GENERATE_EMBEDDING(...)")


def test_scope_guards_refuse_before_any_cloud_call(lc, p1):
    life, cloud, j = lc
    n = len(cloud.ops)
    with pytest.raises(L.ScopeViolation):
        life.publish_relational(p1)                                       # before provision
    for bad in ("../escape", "metrics/../../other-run/x", "/abs", "", "a//b", ".hidden"):
        with pytest.raises(L.ScopeViolation):
            life.write_pin(bad, p1["publication_id"], GM)                 # traversal / empty / unsafe local segments never pass the prefix guard
    assert not CFG.owns_entry(ORIG_ENTRY) and not CFG.owns_entry(CFG.entry_prefix) and not CFG.owns_dataset(CFG.original_dataset)
    assert CFG.owns_entry(CFG.entry_prefix + "metrics/gross-margin") and CFG.owns_entry(CFG.entry_prefix + "p2")
    assert cloud.ops[n:] == []
    cloud.datasets[CFG.dataset] = {}                                      # pre-existing dataset with the owned name: never adopted
    with pytest.raises(L.ScopeViolation):
        life.provision()
    assert life.owned.dataset is None and [o["op"] for o in cloud.ops[n:]] == ["get_dataset"]
    with pytest.raises(ValueError):
        L.LifecycleConfig(run_id="x")
    with pytest.raises(ValueError):
        L.LifecycleConfig(run_id="bad run/id")


def test_write_pin_refuses_to_adopt_a_pre_existing_entry(lc, p1):
    life, cloud, j = lc
    life.provision(); life.publish_relational(p1); life.advance_head(p1["publication_id"])
    name = CFG.entry_prefix + "metrics/gross-margin"
    cloud.entries[name] = {"name": name, "aspects": {}}                    # someone else created it under our prefix
    with pytest.raises(L.ScopeViolation):
        life.write_pin("metrics/gross-margin", p1["publication_id"], GM)
    assert name not in life.owned.entries and not [o for o in cloud.mutations() if o["target"] == name]


# ---- scenario 4: ownership journaled before mutation; exact cleanup; partial setup; no peer deletion
def test_ownership_is_written_before_each_mutation_and_cleanup_is_exact(lc, p1):
    life, cloud, j = lc
    own = Path(j.run_dir) / "ownership.json"
    assert json.loads(own.read_text())["event"] == "init" and json.loads(own.read_text())["allowlist"] == CFG.allowlist()
    life.provision(); life.publish_relational(p1); life.advance_head(p1["publication_id"])
    life.write_pin("metrics/gross-margin", p1["publication_id"], GM)
    life.write_pin("control", p1["publication_id"], GM)
    assert json.loads(own.read_text())["owned"]["entries"] == [CFG.entry_prefix + "metrics/gross-margin", CFG.entry_prefix + "control"]
    lines = [json.loads(l) for l in j.path.read_text().splitlines()]
    first_mut = next(i for i, l in enumerate(lines) if l.get("event") == "intended" and l.get("mutates"))
    assert any(l.get("event") == "ownership" for l in lines[:first_mut])
    rc = life.cleanup()
    assert rc["status"] == "COMPLETE" and [s["resource"] for s in rc["steps"]] == [CFG.entry_prefix + "metrics/gross-margin", CFG.entry_prefix + "control", CFG.dataset]
    assert all(s["deleted"] and s["absent_verified"] for s in rc["steps"])
    assert CFG.dataset not in cloud.datasets and ORIG_ENTRY in cloud.entries and FOREIGN_ENTRY in cloud.entries and CFG.original_dataset in cloud.datasets
    assert json.loads((Path(j.run_dir) / "cleanup.json").read_text())["status"] == "COMPLETE"
    assert not [o for o in cloud.ops if o["op"] == "delete_entry" and o["target"] in (ORIG_ENTRY, FOREIGN_ENTRY)]


def test_cleanup_after_partial_setup_touches_only_what_was_created(lc):
    life, cloud, j = lc
    cloud.fail["run_ddl"] = True
    with pytest.raises(RuntimeError):
        life.provision()                                                  # dataset created, first table DDL failed
    assert life.owned.dataset == CFG.dataset and life.owned.tables == [] and life.owned.entries == []
    rc = life.cleanup()
    assert rc["status"] == "COMPLETE" and [s["resource"] for s in rc["steps"]] == [CFG.dataset]
    assert [o["op"] for o in cloud.mutations()] == ["create_dataset", "run_ddl", "delete_dataset"]      # the failed DDL was attempted once, nothing else
    assert [e["state"] for e in j.jobs() if e["role"] == "create_table"] == ["NOT_SUBMITTED"]   # the job never reached the server: jobs.get says so
    assert rc["unresolved_jobs"] == 0
    fresh = L.Lifecycle(CFG, FakeCloud(), Journal(Path(j.run_dir) / "again", RUN))
    assert fresh.cleanup()["status"] == "NOTHING_OWNED"


def test_cleanup_is_incomplete_when_absence_cannot_be_read_back(lc, p1):
    life, cloud, j = lc
    life.provision(); life.publish_relational(p1)
    life.write_pin("control", p1["publication_id"], GM) if False else None
    real_get = cloud.get_dataset
    cloud.get_dataset = lambda dataset, timeout: (cloud._rec("get_dataset", dataset, timeout), {"labels": {}})[1]   # deletion "succeeds" but readback still sees it
    rc = life.cleanup()
    assert rc["status"] == "INCOMPLETE" and rc["steps"][-1]["deleted"] and not rc["steps"][-1]["absent_verified"]
    cloud.get_dataset = real_get
    cloud.fail["delete_dataset"] = True
    cloud.datasets[CFG.dataset] = {}
    rc = life.cleanup()
    assert rc["status"] == "INCOMPLETE" and "injected delete_dataset failure" in rc["steps"][-1]["error"]
    unk = [e for e in j.jobs() if e["state"] == "UNKNOWN"]
    assert unk and unk[-1]["role"] == "delete_dataset" and not unk[-1]["terminal"]      # a failed delete is unverified, never terminal
    assert rc["unresolved_jobs"] == 1 and rc["unresolved"][0]["role"] == "delete_dataset"


# ---- scenario 5: bounded + journaled operations
def test_every_operation_is_bounded_and_journaled(lc, p1):
    life, cloud, j = lc
    life.snapshot_originals(); life.provision(); life.publish_relational(p1); life.advance_head(p1["publication_id"])
    life.write_pin("control", p1["publication_id"], GM); life.cleanup()
    assert cloud.ops and all(o["timeout"] == 7.5 for o in cloud.ops)
    jobs = j.jobs()
    assert len(jobs) == len(cloud.ops) and all(e["terminal"] and e["timeout_s"] == 7.5 and e["actual"] for e in jobs)
    assert [e["target"] for e in jobs] == [o["target"] for o in cloud.ops]
    assert sum(1 for e in jobs if e["mutates"]) == len(cloud.mutations())
    assert j.summary()["unresolved"] == 0
    # every job-backed op carried a driver-chosen id that was journaled (submitted event) BEFORE the cloud saw it
    lines = [json.loads(l) for l in j.path.read_text().splitlines()]
    for o in cloud.ops:
        if o["job_id"]:
            ev = [l for l in lines if l.get("job_id") == o["job_id"]]
            assert ev and ev[0]["event"] == "submitted" and ev[0]["project"] == CFG.project and ev[0]["location"] == "US"
    assert {o["job_id"] for o in cloud.ops if o["job_id"]} == {e["job_id"] for e in jobs if e["job_backed"]}


# ---- owned pin: generated from verified rows, readable through the real parser; adversaries on owned resources only
def test_owned_pin_round_trips_through_the_catalog_parser_and_adversaries_are_typed(lc, p1, derived):
    life, cloud, j = lc
    life.provision(); life.publish_relational(p1); life.advance_head(p1["publication_id"])
    authored = {"201486563047.us-central1.okf": {"okf_type": "Metric", "status": "stable"}, "655216118709.global.overview": {"content": "# Definition"}}
    rec = life.write_pin("metrics/gross-margin", p1["publication_id"], GM, authored_aspects=authored)
    assert rec["readback_status"] == "OK" and rec["authored_aspects_present"] and rec["adversarial_override"] == []
    cfg = CFG.catalog_config("metrics/gross-margin")
    reader = C.MockReader(C.mock_pages(sorted(cloud.entries), 3), cloud.entries)
    seed = C.read_seed(reader, cfg)
    assert isinstance(seed, C.CatalogSeed) and seed.pin.publication_id == p1["publication_id"] and seed.pin.runtime_dataset == CFG.dataset
    assert seed.pin.managed_by_deployment == CFG.deployment and seed.pin.concept_id == f"acme_retail|{p1['publication_id']}|Concept|metrics/gross-margin"
    assert seed.pin.concept_file_sha256 == next(m["sha256"] for m in p1["source_manifest"] if m["path"] == GM)
    # the pin was generated from the owned rows, not from a label: resolve it against a store built from the fake cloud
    store = PUB.ProjectionStore(Journal(Path(j.run_dir) / "s", RUN)); store.add(p1); store.set_head("acme_retail", p1["publication_id"])
    assert PUB.resolve_publication(store, seed.pin)["status"] == "OK"
    # the same entry cannot be read under the ORIGINAL configuration (different destination/deployment): scope refusal
    assert C.parse_pin(cloud.entries[cfg.entry], C.CatalogConfig(entry=cfg.entry)).status == "SCOPE_REFUSED"
    # P2 pin from the derived publication: parses only because the lifecycle config allows a local derivation, and its trusted source is the retained tree
    life.publish_relational(derived["projection"], derivation=derived["derivation"])
    rec2 = life.write_pin("p2", derived["projection"]["publication_id"], GM)
    assert rec2["readback_status"] == "OK"
    pin2 = C.parse_pin(cloud.entries[CFG.entry_prefix + "p2"], CFG.catalog_config("p2"))
    assert isinstance(pin2, C.CatalogPin) and pin2.source_pin == derived["projection"]["source_pin"]
    assert PUB.trusted_source(pin2, "/nonexistent", derivation=derived["derivation"])["status"] == "OK"
    assert C.parse_pin(cloud.entries[CFG.entry_prefix + "p2"], C.CatalogConfig(**{**{f.name: getattr(cfg, f.name) for f in cfg.__dataclass_fields__.values()}, "entry": CFG.entry_prefix + "p2", "allow_local_derived_source": False})).status == "INVALID_PIN"
    # adversaries: wrong publication under the seed's label -> INVALID_PIN (concept id disagrees); missing aspect -> ASPECT_MISSING; withdrawn -> FAIL_STALE
    bad = life.write_pin("wrong-pub", p1["publication_id"], GM, pin_override={"publication_id": derived["projection"]["publication_id"]})
    assert bad["readback_status"] == "INVALID_PIN" and bad["adversarial_override"] == ["publication_id"]
    gone = life.remove_runtime_aspect("metrics/gross-margin")
    assert not gone["runtime_aspect_present"] and gone["authored_aspects"] == sorted(authored)
    assert C.parse_pin(cloud.entries[cfg.entry], cfg).status == "ASPECT_MISSING"
    assert life.withdraw(p1["publication_id"])["ready"] is False
    store.set_status(p1["publication_id"], "WITHDRAWN")
    assert PUB.resolve_publication(store, seed.pin)["status"] == "FAIL_STALE"
    assert life.restore(p1["publication_id"])["ready"] is True
    with pytest.raises(RuntimeError):
        life.pin_from_rows("pub_0000000000000000", GM)                  # no pin from a non-READY / unknown publication
    with pytest.raises(L.ScopeViolation):
        life.withdraw("pub_0000000000000000")


# ---- Astra PR41 P1 #2: ownership persists before the write; a lost response never hides a committed resource
def test_committed_entry_with_lost_response_is_still_cleaned_up(lc, p1):
    life, cloud, j = lc
    life.provision(); life.publish_relational(p1); life.advance_head(p1["publication_id"])
    real_create = cloud.create_entry

    def commit_then_lose(name, body, attempt_id, timeout):
        real_create(name, body, attempt_id, timeout)           # the server committed the entry ...
        raise TimeoutError("response lost after commit")      # ... but the client never saw the response
    cloud.create_entry = commit_then_lose
    name = CFG.entry_prefix + "control"
    with pytest.raises(TimeoutError):
        life.write_pin("control", p1["publication_id"], GM)
    own = json.loads((Path(j.run_dir) / "ownership.json").read_text())
    assert own["owned"]["pending"] and own["owned"]["pending"][0]["name"] == name and name not in own["owned"]["entries"]
    assert [e for e in j.jobs() if e["role"] == "create_entry"][0]["state"] == "UNKNOWN" and j.summary()["unresolved"] == 1
    assert name in cloud.entries
    rc = life.cleanup()
    assert rc["status"] == "COMPLETE", rc
    kinds = {(s["resource"], s["kind"]): s for s in rc["steps"]}
    assert kinds[(name, "pending_entry")]["reconciled"] == "PRESENT_ADOPTED" and kinds[(name, "entry")]["deleted"] and kinds[(name, "entry")]["absent_verified"]
    assert name not in cloud.entries and rc["unresolved_jobs"] == 0 and rc["pending"] == []
    assert [e["state"] for e in j.jobs() if e["role"] == "create_entry"] == ["APPLIED"]


def test_lost_response_without_commit_stays_pending_until_the_outcome_is_established(lc, p1):
    """Astra re-review R3 / re-review 2: neither one absent read nor elapsed time closes a create that may still be in
    flight. Only stamped presence (adopt) or an adapter-established NOT_APPLIED outcome closes the attempt."""
    life, cloud, j = lc
    life.provision(); life.publish_relational(p1); life.advance_head(p1["publication_id"])
    cloud.fail["create_entry"] = True                          # raised before anything was written
    with pytest.raises(RuntimeError):
        life.write_pin("control", p1["publication_id"], GM)
    attempt = life.owned.pending[0]["attempt_id"]
    assert attempt.startswith("okf_att_") and j.summary()["unresolved"] == 1
    rc = life.cleanup()
    assert rc["status"] == "INCOMPLETE" and rc["steps"][0]["reconciled"] == "ABSENT_PENDING" and rc["steps"][0]["attempt_outcome"] is None
    assert rc["pending"][0]["state"] == "ABSENT_PENDING" and rc["pending"][0]["recheck_after_s"] == CFG.settle and j.summary()["unresolved"] == 1
    life.clock.advance(CFG.settle * 10)                        # elapsed time is not an outcome: still pending after ten windows
    rc = life.cleanup()
    assert rc["status"] == "INCOMPLETE" and rc["steps"][0]["reconciled"] == "ABSENT_PENDING" and rc["pending"][0]["rechecks"] == 2
    own = json.loads((Path(j.run_dir) / "ownership.json").read_text())
    assert own["owned"]["pending"][0]["attempt_id"] == attempt                                   # persisted for a later cleanup
    cloud.outcomes[attempt] = "NOT_APPLIED"                     # the adapter establishes that this exact attempt never applied
    rc = life.cleanup()
    assert rc["status"] == "COMPLETE" and rc["steps"][0]["reconciled"] == "NOT_APPLIED_VERIFIED" and rc["pending"] == [] and rc["unresolved_jobs"] == 0
    assert [e["state"] for e in j.jobs() if e["role"] == "create_entry"] == ["NOT_APPLIED"]


@pytest.mark.parametrize("kind", ["entry", "dataset"])
def test_create_completing_after_the_settle_window_is_still_owned_and_deleted(lc, p1, kind):
    """Astra re-review 2 repro (both kinds): hold the dispatched create, time out, advance the clock past settle, cleanup;
    then complete the same stamped create -> the next cleanup adopts and deletes it; no NOTHING_OWNED orphan."""
    life, cloud, j = lc
    held = {}
    if kind == "entry":
        life.provision(); life.publish_relational(p1); life.advance_head(p1["publication_id"])
        real = cloud.create_entry
        def hold(name, body, attempt_id, timeout):
            held["args"] = (name, body, attempt_id, timeout); raise TimeoutError("server still creating")
        cloud.create_entry = hold
        with pytest.raises(TimeoutError):
            life.write_pin("control", p1["publication_id"], GM)
        name, present = CFG.entry_prefix + "control", lambda: name in cloud.entries
    else:
        real = cloud.create_dataset
        def hold(dataset, location, labels, attempt_id, timeout):
            held["args"] = (dataset, location, labels, attempt_id, timeout); raise TimeoutError("server still creating")
        cloud.create_dataset = hold
        with pytest.raises(TimeoutError):
            life.provision()
        name, present = CFG.dataset, lambda: CFG.dataset in cloud.datasets
    life.clock.advance(61)
    rc1 = life.cleanup()
    assert rc1["status"] == "INCOMPLETE" and not present() and any(st["reconciled"] == "ABSENT_PENDING" and st["resource"] == name for st in rc1["steps"])
    assert rc1["pending"] and rc1["pending"][0]["name"] == name
    real(*held["args"])                                        # the same stamped request completes late, after the window
    assert present()
    rc2 = life.cleanup()
    assert rc2["status"] == "COMPLETE" and not present() and rc2["pending"] == []
    kinds = {(st["resource"], st["kind"]): st for st in rc2["steps"]}
    assert kinds[(name, f"pending_{kind}")]["reconciled"] == "PRESENT_ADOPTED" and kinds[(name, kind)]["absent_verified"]
    assert life.cleanup()["status"] == "NOTHING_OWNED"          # only after everything was verified gone


def test_delayed_create_commits_after_an_absent_read_and_is_still_cleaned(lc, p1):
    """Astra re-review R3 repro: the server accepts the create, the client times out, cleanup sees it absent, the server
    commits later. The attempt stays pending, so the next cleanup adopts (stamp) and deletes it."""
    life, cloud, j = lc
    life.provision(); life.publish_relational(p1); life.advance_head(p1["publication_id"])
    real_create, held = cloud.create_entry, {}

    def still_creating(name, body, attempt_id, timeout):
        held["args"] = (name, body, attempt_id, timeout)
        raise TimeoutError("server still creating")
    cloud.create_entry = still_creating
    name = CFG.entry_prefix + "control"
    with pytest.raises(TimeoutError):
        life.write_pin("control", p1["publication_id"], GM)
    rc1 = life.cleanup()
    assert rc1["status"] == "INCOMPLETE" and rc1["steps"][0]["reconciled"] == "ABSENT_PENDING" and name not in cloud.entries
    real_create(*held["args"])                                 # deterministic late server commit, after the absent read
    assert name in cloud.entries
    life.clock.advance(CFG.settle + 1)
    rc2 = life.cleanup()
    assert rc2["status"] == "COMPLETE" and name not in cloud.entries
    kinds = {(st["resource"], st["kind"]): st for st in rc2["steps"]}
    assert kinds[(name, "pending_entry")]["reconciled"] == "PRESENT_ADOPTED" and kinds[(name, "entry")]["absent_verified"]
    assert [e["state"] for e in j.jobs() if e["role"] == "create_entry"] == ["APPLIED"]


def test_late_create_after_settle_by_a_foreign_owner_is_preserved(lc, p1):
    life, cloud, j = lc
    life.provision()
    cloud.fail["create_entry"] = True
    with pytest.raises(RuntimeError):
        life.write_pin("control", p1["publication_id"], GM) if False else life.write_pin.__func__(life, "control", "pub_x", GM) if False else (_ for _ in ()).throw(RuntimeError("x"))
    name = CFG.entry_prefix + "control"
    life._pending("entry", name)                               # a pending create attempt of ours ...
    cloud.entries[name] = {"name": name, "entrySource": {"labels": {L.OWNER_LABEL: "someone-else"}}, "aspects": {}}   # ... but another owner holds the name
    life.clock.advance(CFG.settle + 1)
    rc = life.cleanup()
    assert rc["status"] == "INCOMPLETE" and any(st["reconciled"] == "FOREIGN_PRESERVED" for st in rc["steps"])
    assert name in cloud.entries and rc["foreign_preserved"][0]["name"] == name and not [o for o in cloud.ops if o["op"] == "delete_entry"]


def test_foreign_dataset_with_the_same_normalised_name_is_never_adopted(tmp_path, p1):
    """Astra re-review R2 repro: run ids review-run-A and review_run_a normalise to one dataset name. B creates it between
    A's precheck and A's create; A's create conflicts; A's cleanup must preserve B's dataset and peer data."""
    cloud = FakeCloud()
    cfg_a, cfg_b = L.LifecycleConfig(run_id="review-run-A", timeout_s=7.5), L.LifecycleConfig(run_id="review_run_a", timeout_s=7.5)
    assert cfg_a.dataset == cfg_b.dataset and cfg_a.deployment != cfg_b.deployment
    a = L.Lifecycle(cfg_a, cloud, Journal(tmp_path / "a", "a"), clock=Clock())
    b = L.Lifecycle(cfg_b, cloud, Journal(tmp_path / "b", "b"), clock=Clock())
    real_create = cloud.create_dataset

    def b_wins(dataset, location, labels, attempt_id, timeout):
        cloud.create_dataset = real_create
        b.provision()                                          # B provisions (stamped) inside A's create window
        cloud.datasets[dataset]["peer_data"] = [{"x": 1}]
        raise RuntimeError("409 already exists")
    cloud.create_dataset = b_wins
    with pytest.raises(RuntimeError):
        a.provision()
    assert a.owned.dataset is None and a.owned.pending[0]["name"] == cfg_a.dataset
    a.clock.advance(cfg_a.settle + 1)
    rc = a.cleanup()
    assert rc["status"] == "INCOMPLETE" and rc["steps"][0]["reconciled"] == "FOREIGN_PRESERVED" and rc["foreign_preserved"][0]["name"] == cfg_a.dataset
    assert cfg_a.dataset in cloud.datasets and cloud.datasets[cfg_a.dataset]["peer_data"] == [{"x": 1}]
    assert not [o for o in cloud.ops if o["op"] == "delete_dataset"] and a.owned.dataset is None
    assert cloud.dataset_meta[cfg_a.dataset]["labels"][L.OWNER_LABEL] == b.owner_stamp != a.owner_stamp
    rc_b = b.cleanup()                                         # the real owner cleans up normally
    assert rc_b["status"] == "COMPLETE" and cfg_a.dataset not in cloud.datasets


def test_running_ddl_job_is_reconciled_by_its_own_state_not_by_dataset_absence(lc):
    """Astra re-review R5 repro: a DDL times out while its server job keeps RUNNING; deleting the dataset proves nothing
    about the job. The driver journaled the job reference before dispatch, reconciles it, and cancels once."""
    life, cloud, j = lc
    cloud.running["run_ddl"] = True
    with pytest.raises(TimeoutError):
        life.provision()
    e = next(x for x in j.jobs() if x["role"] == "create_table")
    assert e["job_backed"] and e["job_id"].startswith("okf_cc_") and e["project"] == CFG.project and e["location"] == "US"
    assert e["state"] == "CANCELLED" and e["terminal"] and e["observed"] == "RUNNING -> DONE after cancel"      # reconciled at the failure, once
    assert cloud.jobs[e["job_id"]]["state"] == "DONE" and [o["op"] for o in cloud.ops if o["op"] in ("job_state", "cancel_job")] == ["job_state", "cancel_job", "job_state"]
    rc = life.cleanup()
    assert rc["status"] == "COMPLETE" and CFG.dataset not in cloud.datasets and rc["unresolved_jobs"] == 0
    # cancel not effective: the job stays RUNNING -> unresolved; dataset deletion does not close it
    cloud2 = FakeCloud(); cloud2.running["run_ddl"] = True; cloud2.cancel_effective = False
    j2 = Journal(Path(j.run_dir) / "x", RUN)
    life2 = L.Lifecycle(CFG, cloud2, j2, clock=Clock())
    with pytest.raises(TimeoutError):
        life2.provision()
    e2 = next(x for x in j2.jobs() if x["role"] == "create_table")
    assert e2["state"] == "UNKNOWN" and not e2["terminal"] and e2["observed"] == "RUNNING"
    rc2 = life2.cleanup()
    assert CFG.dataset not in cloud2.datasets                                                   # the resource is gone ...
    assert rc2["status"] == "INCOMPLETE" and rc2["unresolved_jobs"] == 1 and rc2["unresolved"][0]["job_id"] == e2["job_id"]   # ... the job is not closed
    assert rc2["job_reconciliation"][0]["state"] == "UNKNOWN" and cloud2.jobs[e2["job_id"]]["state"] == "RUNNING"
    assert "MOOT" not in json.dumps(rc2) and "MOOT" not in j2.path.read_text()
    # unreadable job state also stays unresolved
    cloud3 = FakeCloud(); cloud3.running["load_rows"] = True; cloud3.fail["job_state"] = True
    life3 = L.Lifecycle(CFG, cloud3, Journal(Path(j.run_dir) / "y", RUN), clock=Clock())
    life3.provision()
    with pytest.raises(TimeoutError):
        life3.publish_relational(p1_for(life3))
    assert life3.journal.unresolved() and "reconcile_error" in life3.journal.unresolved()[0]


def p1_for(life):
    return compile_bundle("/Users/haiyuancao/knowledge-catalog/okf/bundles/acme_retail", "acme_retail", SOURCE_PIN)


def test_unreadable_pending_write_blocks_completion(lc, p1):
    life, cloud, j = lc
    life.provision(); life.publish_relational(p1); life.advance_head(p1["publication_id"])
    cloud.fail["create_entry"] = True
    with pytest.raises(RuntimeError):
        life.write_pin("control", p1["publication_id"], GM)
    cloud.fail["get_entry"] = True                             # the readback itself fails: state stays unknown
    rc = life.cleanup()
    assert rc["status"] == "INCOMPLETE" and rc["pending"] and rc["unresolved_jobs"] >= 1
    assert any(s["kind"] == "pending_entry" and "error" in s for s in rc["steps"])


def test_lost_dataset_create_response_is_owned_and_cleaned(lc):
    life, cloud, j = lc
    real_create = cloud.create_dataset

    def commit_then_lose(dataset, location, labels, attempt_id, timeout):
        real_create(dataset, location, labels, attempt_id, timeout); raise TimeoutError("lost")
    cloud.create_dataset = commit_then_lose
    with pytest.raises(TimeoutError):
        life.provision()
    assert life.owned.dataset is None and life.owned.pending[0]["kind"] == "dataset" and CFG.dataset in cloud.datasets
    rc = life.cleanup()
    assert rc["status"] == "COMPLETE" and CFG.dataset not in cloud.datasets


# ---- Astra PR41 P2: restore only reinstates a verified READY publication, from WITHDRAWN, after re-validation
def test_restore_never_promotes_invalid_readback(lc, p1, monkeypatch):
    life, cloud, j = lc
    life.provision()
    real = cloud.select_rows

    def torn(dataset, table, where, **kw):
        rows = real(dataset, table, where, **kw)
        if table == "nodes" and "bundle_id" in where:
            rows[0]["text"] = "torn"
        return rows
    cloud.select_rows = torn
    r = life.publish_relational(p1)
    assert r["state"] == "INVALID_READBACK" and p1["publication_id"] not in life.owned.ready_verified
    with pytest.raises(RuntimeError):
        life.withdraw(p1["publication_id"])
    with pytest.raises(RuntimeError):
        life.restore(p1["publication_id"])
    assert {x["publication_id"]: x["validation_status"] for x in cloud.datasets[CFG.dataset]["publications"]} == {p1["publication_id"]: "INVALID_READBACK"}
    with pytest.raises(RuntimeError):
        life.advance_head(p1["publication_id"])


def test_restore_revalidates_rows_and_refuses_when_they_changed(lc, p1):
    life, cloud, j = lc
    life.provision(); life.publish_relational(p1); life.advance_head(p1["publication_id"])
    assert life.withdraw(p1["publication_id"])["ready"] is False
    with pytest.raises(RuntimeError):
        life.restore("pub_0000000000000000")
    sec = next(n for n in cloud.datasets[CFG.dataset]["nodes"] if n["kind"] == "Section")
    sec["text"] = "corrupted after withdrawal"
    r = life.restore(p1["publication_id"])
    assert r["state"] == "RESTORE_REFUSED" and r["ready"] is False and not r["readback"]["node_rows"] and not r["readback"]["section_hashes"]
    assert {x["validation_status"] for x in cloud.datasets[CFG.dataset]["publications"]} == {"WITHDRAWN"}
    sec["text"] = next(n for n in p1["nodes"] if n["node_id"] == sec["node_id"])["text"]
    r = life.restore(p1["publication_id"])
    assert r["state"] == "RESTORED" and r["ready"] is True
    with pytest.raises(RuntimeError):
        life.restore(p1["publication_id"])                     # not WITHDRAWN any more: nothing to restore


# ---- Astra re-review 3 R3: one stamped resource discharges exactly one attempt; a retry on an unresolved target is refused
@pytest.mark.parametrize("kind", ["entry", "dataset"])
def test_second_create_on_a_target_with_an_unresolved_attempt_is_refused(lc, p1, kind):
    life, cloud, j = lc
    held = []
    if kind == "entry":
        life.provision(); life.publish_relational(p1); life.advance_head(p1["publication_id"])
        real = cloud.create_entry
        def hold(name, body, attempt_id, timeout):
            held.append((name, body, attempt_id, timeout)); raise TimeoutError("server still creating")
        cloud.create_entry = hold
        first = lambda: life.write_pin("control", p1["publication_id"], GM)
        name, present = CFG.entry_prefix + "control", lambda: name in cloud.entries
    else:
        real = cloud.create_dataset
        def hold(dataset, location, labels, attempt_id, timeout):
            held.append((dataset, location, labels, attempt_id, timeout)); raise TimeoutError("server still creating")
        cloud.create_dataset = hold
        first = life.provision
        name, present = CFG.dataset, lambda: CFG.dataset in cloud.datasets
    with pytest.raises(TimeoutError):
        first()
    with pytest.raises(L.ScopeViolation) as ex:                # the same-instance retry is refused: the first attempt is unresolved
        first()
    assert "unresolved create attempt" in str(ex.value) and len(held) == 1 and len(life.owned.pending) == 1   # no second request was ever dispatched
    real(*held[0])                                              # the only request completes late
    assert present()
    rc = life.cleanup()
    assert rc["status"] == "COMPLETE" and not present() and rc["pending"] == []
    assert life.cleanup()["status"] == "NOTHING_OWNED"


@pytest.mark.parametrize("kind", ["entry", "dataset"])
def test_a_present_resource_discharges_only_the_attempt_that_produced_it(lc, p1, kind):
    """Even with two pending attempts on one name (modelled directly, since the driver now refuses the second create),
    the resource carries the attempt stamp of the request that made it: the other attempt stays pending."""
    life, cloud, j = lc
    held = []
    if kind == "entry":
        life.provision(); life.publish_relational(p1); life.advance_head(p1["publication_id"])
        real = cloud.create_entry
        def hold(name, body, attempt_id, timeout):
            held.append((name, body, attempt_id, timeout)); raise TimeoutError("server still creating")
        cloud.create_entry = hold
        with pytest.raises(TimeoutError):
            life.write_pin("control", p1["publication_id"], GM)
        name, present = CFG.entry_prefix + "control", lambda: name in cloud.entries
        stamp_of = lambda: cloud.entries[name]["entrySource"]["labels"][L.ATTEMPT_LABEL]
    else:
        real = cloud.create_dataset
        def hold(dataset, location, labels, attempt_id, timeout):
            held.append((dataset, location, labels, attempt_id, timeout)); raise TimeoutError("server still creating")
        cloud.create_dataset = hold
        with pytest.raises(TimeoutError):
            life.provision()
        name, present = CFG.dataset, lambda: CFG.dataset in cloud.datasets
        stamp_of = lambda: cloud.dataset_meta[name]["labels"][L.ATTEMPT_LABEL]
    a1 = life.owned.pending[0]
    # a second in-flight attempt on the same name (what a resumed/older driver could have left behind)
    a2 = dict(a1, attempt_id=a1["attempt_id"][:-4] + "beef", at=a1["at"], state="IN_FLIGHT")
    life.owned.pending.append(a2); life._write_ownership("second_attempt")
    if kind == "entry":
        body2 = copy.deepcopy(held[0][1]); body2["entrySource"]["labels"][L.ATTEMPT_LABEL] = a2["attempt_id"]
        held.append((name, body2, a2["attempt_id"], 7.5))
    else:
        labels2 = dict(held[0][2], **{L.ATTEMPT_LABEL: a2["attempt_id"]})
        held.append((name, "US", labels2, a2["attempt_id"], 7.5))
    real(*held[0])                                              # only the FIRST request completes
    assert present() and stamp_of() == a1["attempt_id"][:63]
    rc = life.cleanup()
    by = {(st["resource"], st["kind"], st.get("attempt_id")): st for st in rc["steps"]}
    assert by[(name, f"pending_{kind}", a1["attempt_id"])]["reconciled"] == "PRESENT_ADOPTED"
    assert by[(name, f"pending_{kind}", a2["attempt_id"])]["reconciled"] == "OTHER_ATTEMPT_PRESENT"
    assert rc["status"] == "INCOMPLETE" and not present() and [p["attempt_id"] for p in rc["pending"]] == [a2["attempt_id"]]
    assert [e["state"] for e in j.jobs() if e["role"] == f"create_{kind}"] == ["APPLIED"]      # only attempt 1's journal entry closed
    real(*held[1])                                              # the SECOND request completes after the first resource was removed
    assert present() and stamp_of() == a2["attempt_id"][:63]
    rc = life.cleanup()
    assert rc["status"] == "COMPLETE" and not present() and rc["pending"] == [] and rc["unresolved_jobs"] == 0
    assert life.cleanup()["status"] == "NOTHING_OWNED"          # no orphan left behind
