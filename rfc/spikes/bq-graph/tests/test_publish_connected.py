"""Publish in BigQuery, then consume (okf_bq_graph.publish_connected, 2026-09-15): the §05 state order, the Catalog pin
generated from READY rows after the head advanced, a consumer built only from what the publish wrote, and the honest
failure modes (never READY, head not switched, pin scope refused, served another publication, author identity,
incomplete cleanup). No cloud. Tests that need the pinned Acme checkout or the SDK checkout skip when absent."""
import copy
import datetime as dt
import os
import re
import subprocess
from pathlib import Path

import pytest

import okf_bq_graph.chain as CH
import okf_bq_graph.connected as E2E
import okf_bq_graph.principal as PR
import okf_bq_graph.publish_connected as PC
from okf_bq_graph import DATASET
from okf_bq_graph.authz import RLS_DS
from okf_bq_graph.catalog import DEFAULT_ENTRY
from okf_bq_graph.catalog_lifecycle import LifecycleConfig

TODAY = dt.date(2026, 9, 14)
AS_OF = "2026-09-14T00:00:00Z"


@pytest.fixture(scope="module")
def sdk_root():
    root = CH.sdk_root()
    if not os.path.isfile(os.path.join(root, CH.EXAMPLE_REL, "run.py")):
        pytest.skip("SDK receipt spike checkout not present")
    return root


@pytest.fixture(scope="module")
def full(sdk_root, sample_root, tmp_path_factory):
    """One real hermetic full-path run (SDK SYNTHETIC emulation as a subprocess); launches kept for replay."""
    out_dir = tmp_path_factory.mktemp("kp")
    launches, events = [], []

    def runner(argv, **kw):
        r = subprocess.run(argv, **kw)
        inv = Path(argv[argv.index("--evidence-dir") + 1])
        case = argv[argv.index("--case") + 1]
        launches.append({"case": case, "stdout": r.stdout, "returncode": r.returncode, "diag": (inv / f"case_{case}_hermetic.json").read_bytes()})
        return r

    cloud = PC.HermeticCloud()
    rec = PC.run_publish_connected(cloud, PC.hermetic_env_factory(sdk_root, runner=runner), sdk_root, sample_root, out_dir=out_dir,
                                   identity_client=cloud, expected_author=cloud.principal, as_of=AS_OF, today=TODAY,
                                   progress=lambda ev, **kw: events.append((ev, kw)))
    return rec, cloud, out_dir, launches, events


def _replay(launches):
    by = {l["case"]: l for l in launches}

    def run(argv, **kw):
        case = argv[argv.index("--case") + 1]
        (Path(argv[argv.index("--evidence-dir") + 1]) / f"case_{case}_hermetic.json").write_bytes(by[case]["diag"])
        return subprocess.CompletedProcess(argv, by[case]["returncode"], by[case]["stdout"], "")
    return run


def _run(sdk_root, sample_root, tmp_path, launches, cloud=None, **kw):
    cloud = cloud or PC.HermeticCloud()
    rec = PC.run_publish_connected(cloud, PC.hermetic_env_factory(sdk_root, runner=_replay(launches)), sdk_root, sample_root,
                                   out_dir=tmp_path, identity_client=cloud, expected_author=kw.pop("expected_author", cloud.principal),
                                   as_of=AS_OF, today=TODAY, **kw)
    return rec, cloud


def test_full_path_publishes_in_bigquery_then_consumes_exactly_that_publication(full):
    rec, cloud, out_dir, launches, events = full
    assert rec["verdict"] == "E2E_PUBLISH_CONNECTED", (rec["broken_at"], rec["checks"])
    assert [s["state"] for s in rec["state_trace"]] == list(PC.SEC05_STATES)
    pub = rec["publish"]
    assert pub["ready"]["state"] == "READY" and pub["ready"]["row"]["validation_status"] == "READY"
    assert pub["head"]["state"] == "SWITCHED" and pub["head"]["from"] is None and pub["head"]["to"] == pub["ready"]["publication_id"]
    assert pub["head"]["merge_job_id"].startswith("okf_cc_")
    by_state = {s["state"]: s for s in rec["state_trace"]}
    assert by_state["BQ_COMMITTED"]["jobs"][-2:] and pub["head"]["merge_job_id"] in by_state["BQ_COMMITTED"]["jobs"]
    staged_roles = {j["role"] for j in pub["jobs"] if j["job_id"] in by_state["BQ_STAGED"]["jobs"]}
    assert {"load_nodes", "load_edges", "readback_nodes", "readback_edges", "insert_publication"} <= staged_roles
    assert pub["catalog_pin"]["readback_status"] == "OK" and pub["catalog_pin"]["entry"].startswith(rec["owned"]["entry_prefix"])
    assert all(j["state"] == "DONE" for j in pub["jobs"]) and pub["unresolved_jobs"] == 0
    assert pub["author_identity"]["status"] == "BOUND" and pub["author_identity"]["roles"]["author"]["jobs"] == len(pub["jobs"])
    assert rec["consumed"]["status"] == "MATCH" and rec["consumed"]["dataset"].startswith("okf_kp_publish_")
    assert rec["connected"]["verdict"] == "E2E_CONNECTED" and [l["case"] for l in launches] == ["approved", "sql-substitution"]
    assert pub["cleanup"]["status"] == "COMPLETE" and pub["originals_recheck"]["status"] == "UNCHANGED"
    assert not [d for d in cloud.datasets if d.startswith("okf_kp_publish_")] and set(cloud.entries) == {DEFAULT_ENTRY}
    # publish is narrated before any consume event, with the job ids
    kinds = [ev for ev, _ in events]
    assert kinds.index("ready") < kinds.index("head") < kinds.index("catalog_pin") < kinds.index("consume") < kinds.index("grant")
    assert any(ev == "bq_job" and kw["role"] == "merge_head" and kw["job"] == pub["head"]["merge_job_id"] for ev, kw in events)


def test_record_is_hygienic_and_the_summary_carries_the_publish_beat(full):
    rec, _cloud, out_dir, _l, _e = full
    text = (Path(out_dir) / rec["run_id"] / "publish_connected_hermetic.json").read_text()
    assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text), "e-mail survived redaction"
    assert (Path(out_dir) / "publish_connected_hermetic.json").read_text() == text
    s = PC.summary(rec)
    assert s["publish"]["authority"] == "BigQuery" and s["publish"]["ready"] == "READY" and s["publish"]["states"][-1] == "COMPLETE"
    assert s["connected"]["verdict"] == "E2E_CONNECTED" and s["connected"]["answer"]


def test_the_consumer_only_sees_what_the_publish_wrote(sdk_root, sample_root):
    cloud = PC.HermeticCloud()
    cfg = PC.lifecycle_config("kp-20260915t000000z-ab12").catalog_config(PC.ENTRY_LOCAL)
    from okf_bq_graph.compile import compile_bundle
    env = PC.hermetic_env_factory(sdk_root)(cfg, cloud, compile_bundle(sample_root, "acme_retail", E2E.SOURCE_PIN))
    assert env.projection["nodes"] == [] and env.head is None                     # nothing published: no rows, no head
    assert cfg.entry not in env.reader.entries                                    # and no Catalog entry to discover


def test_a_publication_that_fails_readback_is_never_ready_and_nothing_is_consumed(full, sdk_root, sample_root, tmp_path):
    cloud = PC.HermeticCloud()

    def tamper(table, rows):
        if table == "nodes" and rows:
            rows[0] = dict(rows[0], text=(rows[0].get("text") or "") + " tampered")
        return rows
    cloud.tamper = tamper
    rec, cloud = _run(sdk_root, sample_root, tmp_path, full[3], cloud=cloud)
    assert rec["publish"]["ready"]["state"] == "INVALID_READBACK" and rec["connected"] is None
    assert rec["verdict"] == "E2E_INCOMPLETE" and rec["stopped_at"] == "publish"
    assert [s["state"] for s in rec["state_trace"]] == ["PLANNED", "PREPARING"]
    assert rec["publish"]["cleanup"]["status"] == "COMPLETE"


def test_an_interruption_before_the_head_switch_consumes_nothing(full, sdk_root, sample_root, tmp_path):
    rec, cloud = _run(sdk_root, sample_root, tmp_path, full[3], inject={"head": "before_head"})
    assert rec["publish"]["ready"]["state"] == "READY" and "head" not in rec["publish"] and rec["connected"] is None
    assert rec["verdict"] == "E2E_INCOMPLETE" and rec["stopped_at"] == "head"
    assert "BQ_COMMITTED" not in [s["state"] for s in rec["state_trace"]]
    assert cloud.datasets[DATASET]["active_publication"][0]["publication_id"] == "pub_190192147fd7fd78"
    assert rec["publish"]["cleanup"]["status"] == "COMPLETE"


def test_a_pin_naming_another_dataset_is_refused_before_any_consume(full, sdk_root, sample_root, tmp_path):
    rec, _cloud = _run(sdk_root, sample_root, tmp_path, full[3], inject={"pin_override": {"runtime_dataset": DATASET}})
    assert rec["publish"]["catalog_pin"]["readback_status"] == "SCOPE_REFUSED" and rec["connected"] is None
    assert rec["verdict"] == "E2E_INCOMPLETE" and rec["stopped_at"] == "catalog_pin"


def test_cleanup_that_cannot_read_back_absence_blocks_the_verdict(full, sdk_root, sample_root, tmp_path):
    cloud = PC.HermeticCloud()
    cloud.keep_on_delete = True
    rec, _ = _run(sdk_root, sample_root, tmp_path, full[3], cloud=cloud)
    assert rec["connected"]["verdict"] == "E2E_CONNECTED" and rec["consumed"]["status"] == "MATCH"
    assert rec["publish"]["cleanup"]["status"] == "INCOMPLETE" and rec["verdict"] == "E2E_INCOMPLETE" and rec["broken_at"] == "cleanup"


def test_author_jobs_under_another_identity_are_broken(full, sdk_root, sample_root, tmp_path):
    rec, _ = _run(sdk_root, sample_root, tmp_path, full[3], expected_author="someone-else@example.test")
    assert rec["publish"]["author_identity"]["status"] == "UNBOUND" and rec["verdict"] == "E2E_BROKEN" and rec["broken_at"] == "author_identity"


def test_consumed_check_and_verdict_rules(full):
    rec = full[0]
    P, ds, entry = rec["consumed"]["publication_id"], rec["consumed"]["dataset"], rec["consumed"]["entry"]
    approved = {"case": E2E.APPROVED, "catalog": {"status": "OK", "entry": entry, "pin": {"publication_id": P, "runtime_dataset": ds}},
                "publication": {"status": "OK", "head": {"publication_id": P, "matches_pin": True}}}
    assert PC.consumed_check({"cases": [approved]}, P, ds, entry, ds)["status"] == "MATCH"
    other = copy.deepcopy(approved); other["catalog"]["pin"]["runtime_dataset"] = DATASET
    assert PC.consumed_check({"cases": [other]}, P, ds, entry, ds)["status"] == "MISMATCH"
    moved = copy.deepcopy(approved); moved["publication"]["head"] = {"publication_id": "pub_0000000000000000", "matches_pin": False}
    assert PC.consumed_check({"cases": [moved]}, P, ds, entry, ds)["status"] == "MISMATCH"
    assert PC.consumed_check({"cases": [dict(approved, catalog={"status": "CATALOG_ERROR"})]}, P, ds, entry, ds)["status"] == "NOT_REACHED"
    r = copy.deepcopy(rec); r["consumed"]["status"] = "MISMATCH"
    assert PC.verdict(r)[:2] == ("E2E_BROKEN", "consumed")
    r = copy.deepcopy(rec); r["connected"]["verdict"] = "E2E_BROKEN"
    assert PC.verdict(r)[0] == "E2E_BROKEN"
    r = copy.deepcopy(rec); r["publish"]["originals_recheck"]["status"] = "CHANGED_EXTERNALLY_PRESERVED"
    assert PC.verdict(r)[0] == "E2E_INCOMPLETE"
    r = copy.deepcopy(rec); r["publish"]["unresolved_jobs"] = 1
    assert PC.verdict(r)[0] == "E2E_INCOMPLETE"


def test_defaults_are_unchanged_for_the_consume_only_path():
    cfg = LifecycleConfig(run_id="t-20260906-ab12")
    assert cfg.dataset == "okf_catalog_chain_t_20260906_ab12" and "/entries/acme-retail-catalog-chain/t-20260906-ab12/" in cfg.entry_prefix
    assert cfg.deployment == "acme-retail-catalog-chain-t-20260906-ab12"
    kp = PC.lifecycle_config("kp-20260915t000000z-ab12")
    assert kp.dataset == "okf_kp_publish_kp_20260915t000000z_ab12" and kp.profile == "okf-kp-publish/1"
    b = PR.RestrictedBroker("fallback", "sdk_ds", factory=lambda email: object(), owner=object(), sa_email="sa@example.test")
    assert b.graph_dataset == DATASET and b._graph_ds() == DATASET
    b2 = PR.RestrictedBroker("fallback", "sdk_ds", factory=lambda email: object(), owner=object(), sa_email="sa@example.test", graph_dataset=kp.dataset)
    assert b2._graph_ds() == kp.dataset and b2.graph_clients()["ds"] == kp.dataset
    b2.state["dataset"] = "rls"
    assert b2._graph_ds() == RLS_DS
