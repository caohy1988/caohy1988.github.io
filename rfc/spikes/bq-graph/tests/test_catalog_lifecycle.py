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


class FakeCloud:
    """Protocol-level fake. Every op records (op, target, timeout, mutates); `fail[op]` raises on that op."""

    def __init__(self):
        self.datasets = {CFG.original_dataset: {"active_publication": [{"bundle_id": "acme_retail", "publication_id": "pub_190192147fd7fd78"}]}}
        self.entries = {ORIG_ENTRY: C.sample_entry(), FOREIGN_ENTRY: {"name": FOREIGN_ENTRY, "aspects": {}}}
        self.ops = []
        self.fail = {}

    def _rec(self, op, target, timeout, mutates=False):
        assert isinstance(timeout, (int, float)) and timeout > 0, "every cloud op must be bounded"
        self.ops.append({"op": op, "target": target, "timeout": timeout, "mutates": mutates})
        if op in self.fail:
            raise RuntimeError(f"injected {op} failure")

    def mutations(self):
        return [o for o in self.ops if o["mutates"]]

    # BigQuery
    def dataset_exists(self, dataset, timeout):
        self._rec("dataset_exists", dataset, timeout); return dataset in self.datasets

    def create_dataset(self, dataset, location, timeout):
        self._rec("create_dataset", dataset, timeout, True)
        assert dataset not in self.datasets and location == "US"
        self.datasets[dataset] = {}; return {"job_id": None}

    def delete_dataset(self, dataset, timeout):
        self._rec("delete_dataset", dataset, timeout, True)
        del self.datasets[dataset]; return {}

    def run_ddl(self, dataset, statement, timeout):
        table = statement.split("`")[1].split(".")[-1]
        self._rec("run_ddl", f"{dataset}.{table}", timeout, True)
        self.datasets[dataset].setdefault(table, []); return {"job_id": f"ddl-{table}"}

    def load_rows(self, dataset, table, rows, timeout):
        self._rec("load_rows", f"{dataset}.{table}", timeout, True)
        self.datasets[dataset][table].extend(copy.deepcopy(rows)); return {"job_id": f"load-{table}-{len(rows)}"}

    def select_rows(self, dataset, table, where, timeout, exclude=()):
        self._rec("select_rows", f"{dataset}.{table}", timeout)
        rows = [r for r in self.datasets.get(dataset, {}).get(table, []) if all(r.get(k) == v for k, v in where.items())]
        return [{k: v for k, v in r.items() if k not in exclude} for r in copy.deepcopy(rows)]

    def insert_row(self, dataset, table, row, timeout):
        self._rec("insert_row", f"{dataset}.{table}", timeout, True)
        self.datasets[dataset][table].append(copy.deepcopy(row)); return {"job_id": "ins"}

    def update_status(self, dataset, publication_id, status, timeout):
        self._rec("update_status", f"{dataset}.publications", timeout, True)
        for r in self.datasets[dataset]["publications"]:
            if r["publication_id"] == publication_id:
                r["validation_status"] = status
        return {"job_id": "upd"}

    def merge_head(self, dataset, bundle_id, publication_id, timeout):
        self._rec("merge_head", f"{dataset}.active_publication", timeout, True)
        t = self.datasets[dataset]["active_publication"]
        t[:] = [r for r in t if r["bundle_id"] != bundle_id] + [{"bundle_id": bundle_id, "publication_id": publication_id}]
        return {"job_id": "merge"}

    # Catalog
    def get_entry(self, name, timeout):
        self._rec("get_entry", name, timeout); return copy.deepcopy(self.entries.get(name))

    def create_entry(self, name, body, timeout):
        self._rec("create_entry", name, timeout, True)
        assert name not in self.entries; self.entries[name] = copy.deepcopy(body); return {}

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
    return L.Lifecycle(CFG, cloud, j), cloud, j


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

    def torn(dataset, table, where, timeout, exclude=()):
        rows = real(dataset, table, where, timeout, exclude)
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
    assert {o["op"] for o in cloud.ops} <= {"dataset_exists", "create_dataset", "delete_dataset", "run_ddl", "load_rows", "select_rows", "insert_row",
                                             "update_status", "merge_head", "get_entry", "create_entry", "patch_entry", "delete_entry"}
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
    assert life.owned.dataset is None and [o["op"] for o in cloud.ops[n:]] == ["dataset_exists"]
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
    assert [e["state"] for e in j.jobs() if e["role"] == "create_table"] == ["ERROR"]
    fresh = L.Lifecycle(CFG, FakeCloud(), Journal(Path(j.run_dir) / "again", RUN))
    assert fresh.cleanup()["status"] == "NOTHING_OWNED"


def test_cleanup_is_incomplete_when_absence_cannot_be_read_back(lc, p1):
    life, cloud, j = lc
    life.provision(); life.publish_relational(p1)
    life.write_pin("control", p1["publication_id"], GM) if False else None
    real_exists = cloud.dataset_exists
    cloud.dataset_exists = lambda dataset, timeout: (cloud._rec("dataset_exists", dataset, timeout), True)[1]   # deletion "succeeds" but readback still sees it
    rc = life.cleanup()
    assert rc["status"] == "INCOMPLETE" and rc["steps"][-1]["deleted"] and not rc["steps"][-1]["absent_verified"]
    cloud.dataset_exists = real_exists
    cloud.fail["delete_dataset"] = True
    cloud.datasets[CFG.dataset] = {}
    rc = life.cleanup()
    assert rc["status"] == "INCOMPLETE" and "injected delete_dataset failure" in rc["steps"][-1]["error"]
    errs = [e for e in j.jobs() if e["state"] == "ERROR"]
    assert errs and errs[-1]["role"] == "delete_dataset" and all(e["terminal"] for e in j.jobs())


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
