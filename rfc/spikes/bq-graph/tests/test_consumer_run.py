"""`okf_bq_graph.consumer_run` (FS-1): the hermetic sampled request-to-consumer runner.

Contract: rfc/board-pack/spec-sqlchain-consumer-fs1.md. Dry-run and hermetic modes only; refuses unless the fact
version is SELECTED; every attempt retained; a hermetic pass proves orchestration and refusals, never a latency, a
job or data equivalence. SDK- and Acme-dependent tests skip when a checkout is absent."""
import copy
import re
import datetime as _dt
import decimal
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import okf_bq_graph.chain as CH
import okf_bq_graph.consumer_run as cr
from okf_bq_graph import fact_content, sql_baseline as sb

D = decimal.Decimal
AS_OF = "2026-09-09T12:00:00Z"
EVAL = _dt.date(2026, 9, 9)


@pytest.fixture(scope="module")
def plan():
    return sb.load_plan()


@pytest.fixture(scope="module")
def manifest():
    return json.loads((sb.ROOT / "fixtures" / "facts" / "content.json").read_text())


@pytest.fixture(scope="module")
def sdk_root():
    root = CH.sdk_root()
    if not os.path.isfile(os.path.join(root, CH.EXAMPLE_REL, "run.py")):
        pytest.skip("SDK receipt spike checkout not present")
    return root


@pytest.fixture
def no_client(monkeypatch):
    """Any BigQuery client construction is a defect in this slice."""
    from google.cloud import bigquery
    monkeypatch.setattr(bigquery, "Client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("BigQuery client constructed")))


@pytest.fixture
def short_plan(plan, tmp_path):
    """The committed plan with the consumer cells shortened to 1 warmup + 2 measured (C=1) and 1 + 5 (C=5)."""
    p = copy.deepcopy(plan)
    for cell in p["consumer_cells"]:
        cell["warmups"] = 1
        cell["measured"] = 2 if cell["concurrency"] == 1 else 5
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(p, indent=2, ensure_ascii=False) + "\n")
    return path


def _mutate_feb(manifest: dict) -> dict:
    m = copy.deepcopy(manifest)
    rows = m["tables"]["orders"]["rows"]
    idx = next(i for i, r in enumerate(rows) if r[0] == "ord-2026-02-delivered")
    rows[idx][6] = "201.000000000"   # net_amount
    return m


# ---- command line
def test_parser_has_no_live_flag_and_needs_exactly_one_mode():
    with pytest.raises(SystemExit):
        cr.build_parser().parse_args(["--live"])
    with pytest.raises(SystemExit):
        cr.build_parser().parse_args(["--dry-run", "--hermetic"])
    with pytest.raises(SystemExit):
        cr.build_parser().parse_args([])
    assert "--live" not in cr.build_parser().format_help()


def test_the_module_never_names_a_live_mode_or_a_bigquery_client():
    src = (sb.ROOT / "okf_bq_graph" / "consumer_run.py").read_text()
    assert "bigquery.Client" not in src and '"--live"' not in src


# ---- the row-based oracle
def test_row_oracle_reproduces_the_expected_january_and_january_february_results(manifest):
    assert cr.gross_margin_from_manifest(manifest, _dt.date(2026, 1, 1), _dt.date(2026, 1, 31), EVAL) == D("400")
    assert cr.gross_margin_from_manifest(manifest, _dt.date(2026, 1, 1), _dt.date(2026, 2, 28), EVAL) == D("515")


def test_row_oracle_is_none_when_no_order_is_recognised(manifest):
    assert cr.gross_margin_from_manifest(manifest, _dt.date(2025, 1, 1), _dt.date(2025, 1, 31), EVAL) is None
    # the 30-day recognition clause: on 2026-03-11 the February order is 29 days old and is not recognised
    assert cr.gross_margin_from_manifest(manifest, _dt.date(2026, 1, 1), _dt.date(2026, 2, 28), _dt.date(2026, 3, 11)) == D("400")
    assert cr.gross_margin_from_manifest(manifest, _dt.date(2026, 1, 1), _dt.date(2026, 2, 28), _dt.date(2026, 3, 12)) == D("515")


def test_row_oracle_reads_rows_a_february_mutation_changes_jan_feb_only(manifest):
    m = _mutate_feb(manifest)
    assert fact_content.row_counts(m) == fact_content.row_counts(manifest)
    assert cr.gross_margin_from_manifest(m, _dt.date(2026, 1, 1), _dt.date(2026, 1, 31), EVAL) == D("400")
    assert cr.gross_margin_from_manifest(m, _dt.date(2026, 1, 1), _dt.date(2026, 2, 28), EVAL) == D("516")


def test_row_oracle_follows_the_fx_join_for_non_usd_orders(manifest):
    m = copy.deepcopy(manifest)
    orders = m["tables"]["orders"]["rows"]
    idx = next(i for i, r in enumerate(orders) if r[0] == "ord-2026-01-delivered")
    orders[idx][9] = "EUR"
    # no rate -> every revenue NULL -> SUM(revenue) is NULL -> the whole expression is NULL (GoogleSQL SUM over all NULLs)
    assert cr.gross_margin_from_manifest(m, _dt.date(2026, 1, 1), _dt.date(2026, 1, 31), EVAL) is None
    m["tables"]["fx_daily_rates"]["rows"].append(["EUR", "2026-01-10", "2.000000000"])
    assert cr.gross_margin_from_manifest(m, _dt.date(2026, 1, 1), _dt.date(2026, 1, 31), EVAL) == D("1400")


def test_row_oracle_keeps_the_fx_join_multiplicity_for_usd_orders(manifest):
    """The SQL joins fx_daily_rates BEFORE the CASE picks USD revenue: two matching USD rate rows duplicate the order."""
    m = copy.deepcopy(manifest)
    m["tables"]["fx_daily_rates"]["rows"] += [["USD", "2026-01-10", "1.000000000"], ["USD", "2026-01-10", "1.000000000"]]
    assert cr.gross_margin_from_manifest(m, _dt.date(2026, 1, 1), _dt.date(2026, 1, 31), EVAL) == D("800")


def test_row_oracle_check_against_the_plan_passes_and_a_changed_expectation_is_disagreement(plan, manifest):
    ok = cr.row_oracle_check(plan["facts"]["selected_version"], manifest, EVAL)
    assert ok["status"] == "OK" and ok["january"] == "400" and ok["january_february"] == "515"
    assert ok["engine"] == "python-decimal" and ok["not"] == "googlesql"
    changed = dict(plan["facts"]["selected_version"], expected_gross_margin_usd_2026_01=401)
    bad = cr.row_oracle_check(changed, manifest, EVAL)
    assert bad["status"] == "ORACLE_DISAGREES" and "january" in bad["reason"]


# ---- live admission (a pure function in this slice)
def test_admit_live_ok_before_expiry_binds_the_content_digest(plan, manifest):
    v = plan["facts"]["selected_version"]
    out = cr.admit_live(v, manifest, _dt.date(2026, 10, 4), EVAL)
    assert out["status"] == "OK" and out["bound_content_digest"] == v["content_manifest_sha256"]
    assert out["smoke"]["row_counts_match"] is True and out["smoke"]["january_matches"] is True


@pytest.mark.parametrize("today", [_dt.date(2026, 10, 5), _dt.date(2026, 10, 6)])
def test_admit_live_refuses_on_and_after_the_recorded_expiry(plan, manifest, today):
    out = cr.admit_live(plan["facts"]["selected_version"], manifest, today, EVAL)
    assert out["status"] == "MATERIALIZATION_EXPIRED" and "2026-10-05" in out["reason"]


def test_admit_live_refuses_a_drifted_readback_even_when_smoke_checks_pass(plan, manifest):
    out = cr.admit_live(plan["facts"]["selected_version"], _mutate_feb(manifest), _dt.date(2026, 9, 10), EVAL)
    assert out["status"] == "FACTS_DRIFTED" and out["differing_tables"] == ["orders"]
    assert out["smoke"]["row_counts_match"] is True and out["smoke"]["january_matches"] is True


def test_admit_live_refuses_a_readback_missing_a_table(plan, manifest):
    m = copy.deepcopy(manifest)
    del m["tables"]["fx_daily_rates"]
    out = cr.admit_live(plan["facts"]["selected_version"], m, _dt.date(2026, 9, 10), EVAL)
    assert out["status"] == "FACTS_DRIFTED" and "fx_daily_rates" in out["differing_tables"]


# ---- gates (no subprocess)
def test_unselected_plan_is_refused_before_anything_else(plan, tmp_path, no_client):
    p = copy.deepcopy(plan)
    p["facts"] = {"state": "UNSELECTED", "why_it_matters": "x", "what_is_missing": "y", "blocks": ["sqlchain_forced_c1"],
                  "how_to_select": "z", "customer_data": p["facts"]["customer_data"]}
    del p["facts"]["customer_data"]
    path = tmp_path / "plan.json"; path.write_text(json.dumps(p))
    out = io.StringIO()
    rc = cr.main(["--dry-run", "--plan", str(path), "--out-dir", str(tmp_path / "ev")], stdout=out)
    assert rc == 2 and out.getvalue().startswith("REFUSED: FACTS_UNSELECTED")


def test_a_retrieval_cell_is_refused_not_measured(tmp_path, no_client):
    out = io.StringIO()
    rc = cr.main(["--dry-run", "--cells", "sqlbase_forced_c1", "--out-dir", str(tmp_path)], stdout=out)
    assert rc == 2 and out.getvalue().startswith("REFUSED: NOT_A_CONSUMER_CELL")


def test_unlabelled_and_reused_run_ids_are_refused(tmp_path, no_client):
    out = io.StringIO()
    assert cr.main(["--dry-run", "--run-id", "sqlbase-20260909-000000-deadbeef", "--out-dir", str(tmp_path)], stdout=out) == 2
    assert out.getvalue().startswith("REFUSED: RUN_ID_UNLABELLED")
    used = "consumer-hermetic-20260909T000000Z-deadbeef"
    (tmp_path / f"run_{used}.json").write_text("{}")
    out = io.StringIO()
    assert cr.main(["--dry-run", "--run-id", used, "--out-dir", str(tmp_path)], stdout=out) == 2
    assert out.getvalue().startswith("REFUSED: RUN_ID_REUSED")


def test_an_evaluation_date_before_the_validity_window_is_refused(tmp_path, no_client):
    out = io.StringIO()
    rc = cr.main(["--dry-run", "--as-of", "2026-03-11T00:00:00Z", "--out-dir", str(tmp_path)], stdout=out)
    assert rc == 2 and out.getvalue().startswith("REFUSED: VALIDITY_WINDOW")
    out = io.StringIO()
    assert cr.main(["--dry-run", "--as-of", "2026-03-12T00:00:00Z", "--out-dir", str(tmp_path)], stdout=out) == 0


def test_a_mutated_vendored_fixture_is_refused_as_drift(plan, tmp_path, no_client, monkeypatch):
    facts_dir = tmp_path / "facts"; facts_dir.mkdir()
    for name in ("fixture.sql", "expected.json", "content.json", "publication.json", "gross-margin-period.md", "source.json"):
        (facts_dir / name).write_bytes((sb.ROOT / "fixtures" / "facts" / name).read_bytes())
    sql = (facts_dir / "fixture.sql").read_text().replace("NUMERIC '200.00'", "NUMERIC '201.00'", 1)
    assert "NUMERIC '201.00'" in sql
    (facts_dir / "fixture.sql").write_text(sql)
    monkeypatch.setattr(cr, "FACTS_DIR", facts_dir)
    gates = cr.run_gates(plan, ["sqlchain_forced_c1"], "consumer-hermetic-20260909T000000Z-00000001", tmp_path, EVAL)
    codes = [g["code"] for g in gates if g["status"] == "REFUSED"]
    assert codes and codes[0] in ("PLAN_INVALID", "VENDORED_FACTS_DRIFTED")


def test_a_changed_expected_result_is_refused_as_oracle_disagreement(plan, tmp_path, no_client, monkeypatch):
    """validate_plan already binds the January expectation to expected.json (PLAN_INVALID first); the January–February
    expectation is the oracle's own, so a disagreement there reaches the ORACLE_DISAGREES gate through the CLI."""
    monkeypatch.setattr(cr, "_expected_jan_feb", lambda: "516")
    out = io.StringIO()
    rc = cr.main(["--dry-run", "--out-dir", str(tmp_path / "ev")], stdout=out)
    assert rc == 2 and out.getvalue().startswith("REFUSED: ORACLE_DISAGREES") and "515 != expected 516" in out.getvalue()


def test_dry_run_opens_nothing_prints_the_gates_and_the_unspent_budget(tmp_path, no_client):
    out = io.StringIO()
    rc = cr.main(["--dry-run", "--out-dir", str(tmp_path)], stdout=out)
    text = out.getvalue()
    assert rc == 0
    for needle in ("sqlchain_forced_c1", "sqlchain_forced_c5", "f_current", "f_revenue", "expected REFUSED",
                   "VALIDITY_WINDOW: OK", "ORACLE_DISAGREES: OK", "DECLARED_NOT_SPENT", "dry run: nothing launched"):
        assert needle in text, needle
    assert not list(tmp_path.glob("run_*.json")), "a dry run retains no run record"


# ---- hermetic end to end
@pytest.fixture(scope="module")
def hermetic_c1(sdk_root, sample_root, tmp_path_factory):
    plan = sb.load_plan()
    p = copy.deepcopy(plan)
    for cell in p["consumer_cells"]:
        cell["warmups"] = 1
        cell["measured"] = 2
    d = tmp_path_factory.mktemp("c1")
    path = d / "plan.json"; path.write_text(json.dumps(p, indent=2, ensure_ascii=False) + "\n")
    out = io.StringIO()
    rc = cr.main(["--hermetic", "--cells", "sqlchain_forced_c1", "--plan", str(path), "--out-dir", str(d / "ev"),
                  "--sdk-root", sdk_root, "--acme-root", sample_root, "--as-of", AS_OF], stdout=out)
    records = list((d / "ev").glob("run_consumer-hermetic-*.json"))
    assert len(records) == 1, out.getvalue()
    return rc, out.getvalue(), json.loads(records[0].read_text()), d / "ev"


def test_hermetic_c1_retains_every_attempt_and_releases_the_predeclared_question(hermetic_c1, plan):
    rc, text, rec, ev = hermetic_c1
    assert rc == 0, text
    assert rec["verdict"] == "RUNNER_HERMETIC_OK" and rec["mode"] == "hermetic" and rec["engine"] == "oracle"
    assert rec["run_id"].startswith("consumer-hermetic-") and not rec["run_id"].startswith("live")
    cell = rec["cells"][0]
    assert cell["cell"] == "sqlchain_forced_c1" and cell["attempts_total"] == 4 and cell["measured_n"] == 2 and cell["warmups"] == 1
    assert cell["fills_cell"] is False and cell["state"] == "HERMETIC_COMPLETE"
    assert cell["released"] == 3 and cell["refused"] == 1
    kinds = [a["kind"] for a in rec["attempts"]]
    assert kinds == ["warmup", "measured", "measured", "probe"]
    digest = plan["facts"]["selected_version"]["content_manifest_sha256"]
    for a in rec["attempts"]:
        assert a["selected_content_digest"] == digest and a["evaluation_date"] == "2026-09-09"
        assert a["request_to_consumer_ms"] > 0 and a["acceptance"]["status"] == "MET", a
    for a in rec["attempts"][:3]:
        assert a["question_id"] == "f_current" and a["expected_decision"] == "RELEASED"
        assert a["consume"]["decision"] == "RELEASED" and a["bind"]["status"] == "BOUND"
        r = a["receipt"]
        assert r["invoked"] and r["exit_code"] == 0 and r["verdict"] == "VERIFIED" and r["execution_match"] == "MATCH"
        assert r["elapsed_ms"] > 0 and r["job"]["job_id"].startswith("okf_rcpt_") and r["diag_sha256"]
        assert r["job_times"]["submitted_at"] is None and "no timestamps" in r["job_times"]["note"]
        assert a["retrieval"]["status"] == "OK" and a["retrieval"]["reached"] and a["retrieval"]["elapsed_ms"] >= 0
        assert Path(r["diag_path"]).is_file()
    # the jsonl retention agrees with the record
    lines = [json.loads(l) for l in (ev / rec["run_id"] / "attempts.jsonl").read_text().splitlines()]
    assert [l["index"] for l in lines] == [a["index"] for a in rec["attempts"]]
    assert cell["hermetic_orchestration_ms"]["n"] == 2 and "not request_to_consumer_ms" in cell["hermetic_orchestration_ms"]["note"]
    assert "does_not_establish" in rec["claims"] and "latency" in " ".join(rec["claims"]["does_not_establish"])


def test_hermetic_probe_refuses_at_bind_with_the_sdk_never_invoked(hermetic_c1):
    _, _, rec, _ = hermetic_c1
    probe = rec["attempts"][-1]
    assert probe["kind"] == "probe" and probe["question_id"] == "f_revenue" and probe["expected_decision"] == "REFUSED"
    assert probe["computation"]["path"] == "computations/revenue-ytd.md"
    assert probe["bind"]["status"] == "MISMATCH" and {"file_sha256", "sql_text"} <= set(probe["bind"]["failed_checks"])
    assert probe["receipt"]["invoked"] is False and probe["consume"]["decision"] == "REFUSED"
    assert probe["acceptance"]["status"] == "MET"
    assert rec["cells"][0]["probe"]["decision"] == "REFUSED" and rec["cells"][0]["probe"]["acceptance"] == "MET"


def test_hermetic_record_carries_gates_oracle_admission_and_expiry(hermetic_c1):
    _, _, rec, _ = hermetic_c1
    assert all(g["status"] == "OK" for g in rec["gates"]), rec["gates"]
    assert {g["code"] for g in rec["gates"]} >= {"FACTS_UNSELECTED", "VALIDITY_WINDOW", "VENDORED_FACTS_DRIFTED",
                                                 "ORACLE_DISAGREES", "SDK_PROVENANCE", "PUBLICATION_PIN"}
    assert rec["row_oracle"]["status"] == "OK" and rec["row_oracle"]["january"] == "400"
    assert rec["live_admission"]["status"] == "NOT_RUN"
    assert rec["expiry"]["expires_about"] == "2026-10-05" and rec["expiry"]["live_admission_would_refuse"] is False
    assert rec["budget"]["consumer_sampling"]["state"] == "DECLARED_NOT_SPENT" and rec["budget"]["spent"] == "nothing"
    assert rec["sdk"]["head_matches_pin"] is True and rec["question"]["parameters"] == {"period_start": "2026-01-01", "period_end": "2026-01-31"}


def test_hermetic_c5_reaches_concurrency_and_keeps_one_diagnostic_per_attempt(sdk_root, sample_root, short_plan, tmp_path, no_client):
    out = io.StringIO()
    rc = cr.main(["--hermetic", "--cells", "sqlchain_forced_c5", "--plan", str(short_plan), "--out-dir", str(tmp_path / "ev"),
                  "--sdk-root", sdk_root, "--acme-root", sample_root, "--as-of", AS_OF], stdout=out)
    assert rc == 0, out.getvalue()
    rec = json.loads(next((tmp_path / "ev").glob("run_consumer-hermetic-*.json")).read_text())
    cell = rec["cells"][0]
    assert cell["concurrency"] == 5 and cell["concurrency_achieved"] > 1 and cell["attempts_total"] == 7
    paths = [a["receipt"]["diag_path"] for a in rec["attempts"] if a["receipt"]["invoked"]]
    assert len(paths) == 6 and len(set(paths)) == 6 and all(Path(p).is_file() for p in paths)
    assert rec["verdict"] == "RUNNER_HERMETIC_OK"


def test_a_dying_child_is_not_reached_and_the_run_is_incomplete(sdk_root, sample_root, short_plan, tmp_path):
    def dead(argv, **k):
        raise OSError("child died")
    rec = cr.run_hermetic(sb.load_plan(short_plan), ["sqlchain_forced_c1"], out_dir=tmp_path, sdk_root=sdk_root,
                          acme_root=sample_root, as_of=AS_OF, runner=dead)
    assert rec["verdict"] == "RUNNER_HERMETIC_INCOMPLETE"
    measured = [a for a in rec["attempts"] if a["kind"] == "measured"]
    assert all(a["acceptance"]["status"] == "NOT_REACHED" for a in measured)
    assert all(a["consume"]["decision"] == "REFUSED" for a in measured)
    assert rec["cells"][0]["state"] == "HERMETIC_INCOMPLETE"
    assert rec["attempts"][-1]["kind"] == "probe" and rec["attempts"][-1]["acceptance"]["status"] == "MET"


def test_a_released_probe_is_wrong_and_the_run_is_broken(sdk_root, sample_root, short_plan, tmp_path, monkeypatch):
    real = cr.consume

    def leaky(b, rec, *a, **k):
        out = real(b, rec, *a, **k)
        if b.get("status") == "MISMATCH":
            return {"decision": "RELEASED", "reasons": [], "display": "[HERMETIC] leaked"}
        return out
    monkeypatch.setattr(cr, "consume", leaky)
    rec = cr.run_hermetic(sb.load_plan(short_plan), ["sqlchain_forced_c1"], out_dir=tmp_path, sdk_root=sdk_root,
                          acme_root=sample_root, as_of=AS_OF)
    assert rec["verdict"] == "RUNNER_HERMETIC_BROKEN"
    assert rec["attempts"][-1]["acceptance"]["status"] == "WRONG"


def test_hermetic_refuses_an_sdk_checkout_that_is_not_at_the_pin(sample_root, short_plan, tmp_path, monkeypatch, no_client):
    monkeypatch.setattr(cr, "sdk_publication", lambda root: {**CH.sdk_publication(CH.sdk_root()), "sdk_head_matches_pin": False, "sdk_head": "0" * 40}
                        if os.path.isfile(os.path.join(CH.sdk_root(), CH.EXAMPLE_REL, "run.py")) else pytest.skip("SDK absent"))
    calls = []
    rec = cr.run_hermetic(sb.load_plan(short_plan), ["sqlchain_forced_c1"], out_dir=tmp_path, sdk_root=CH.sdk_root(),
                          acme_root=sample_root, as_of=AS_OF, runner=lambda argv, **k: calls.append(argv))
    assert rec["verdict"] == "REFUSED" and rec["refusal"]["code"] == "SDK_PROVENANCE" and not calls and rec["attempts"] == []


# ---- the committed evidence
def test_committed_hermetic_runs_validate():
    records = cr.consumer_records()
    assert records, "at least one hermetic run is retained under evidence/consumer/"
    for rec in records:
        assert rec["run_id"].startswith("consumer-hermetic-") and rec["mode"] == "hermetic"
        assert rec["verdict"] == "RUNNER_HERMETIC_OK"
        for a in rec["attempts"]:
            assert a["consume"]["decision"] in ("RELEASED", "REFUSED") and a["acceptance"]["status"] == "MET"
            if a["kind"] == "probe":
                assert a["bind"]["status"] == "MISMATCH" and a["receipt"]["invoked"] is False
            else:
                assert a["receipt"]["diag_sha256"] and a["consume"]["decision"] == "RELEASED"
        for cell in rec["cells"]:
            assert cell["fills_cell"] is False and cell["attempts_total"] == cell["warmups"] + cell["measured_n"] + 1
    names = {c["cell"] for r in records for c in r["cells"]}
    assert names == {"sqlchain_forced_c1", "sqlchain_forced_c5"}


# ---- plan: the declared, unspent consumer budget
def test_plan_declares_an_unspent_consumer_budget_inside_the_campaign_ceilings(plan):
    b = plan["budget"]["consumer_sampling"]
    assert b["state"] == "DECLARED_NOT_SPENT"
    assert b["consumer_max_bytes_billed_gib"] <= plan["budget"]["max_bytes_billed_gib"]
    assert b["consumer_max_usd"] <= plan["budget"]["max_usd_ondemand_list"]
    assert b["consumer_max_wall_seconds_per_cell"] <= plan["budget"]["max_wall_seconds_per_cell"]
    assert b["consumer_max_wall_seconds_total"] <= plan["budget"]["max_wall_seconds_total"]
    assert "not spent" in b["note"].lower() or "spends none" in b["note"].lower()


@pytest.mark.parametrize("mutate, match", [
    (lambda b: b.pop("consumer_sampling"), "consumer_sampling"),
    (lambda b: b["consumer_sampling"].pop("consumer_max_usd"), "consumer_max_usd"),
    (lambda b: b["consumer_sampling"].__setitem__("consumer_max_bytes_billed_gib", 65), "campaign ceiling"),
    (lambda b: b["consumer_sampling"].__setitem__("consumer_max_wall_seconds_total", 3601), "campaign ceiling"),
    (lambda b: b["consumer_sampling"].__setitem__("state", "SPENT"), "DECLARED_NOT_SPENT"),
])
def test_validate_plan_refuses_a_missing_oversized_or_spent_consumer_budget(plan, mutate, match):
    p = copy.deepcopy(plan)
    mutate(p["budget"])
    with pytest.raises(ValueError, match=match):
        sb.validate_plan(p)


# ---- card and driver honesty: RUNNER_HERMETIC_ONLY, nothing filled, hermetic runs listed without numbers
@pytest.fixture(scope="module")
def card(plan):
    return sb.build_card(plan)


def test_consumer_cells_read_runner_hermetic_only_and_carry_no_number(card):
    consumer = [c for c in card["cells"] if c["metric"] == "request_to_consumer_ms"]
    assert len(consumer) == 2
    for cell in consumer:
        assert cell["state"] == "INCOMPLETE" and cell["stopped_reason"] == "RUNNER_HERMETIC_ONLY"
        assert cell["measured_n"] == 0 and cell["fact_version_blocked"] is False and cell["blocked_by"] is None
        for field in ("p50_ms", "p95_ms", "max_ms", "success_rate", "bytes_billed", "usd_ondemand_list"):
            assert cell[field] is None
        assert "okf_bq_graph.consumer_run" in cell["how_to_fill"] and "--hermetic" in cell["how_to_fill"] and "--dry-run" in cell["how_to_fill"]
        assert "no live mode" in cell["how_to_fill"] and "FS-2" in cell["how_to_fill"]
        assert "No runner exists" not in cell["how_to_fill"]
        runs = cell["hermetic_runs"]
        assert runs, f"{cell['cell']} lists no retained hermetic run"
        for run in runs:
            assert set(run) == {"run_id", "verdict", "attempts_retained", "released", "refused", "probe", "file"}
            assert run["verdict"] == "RUNNER_HERMETIC_OK" and run["probe"] == "REFUSED" and run["run_id"].startswith("consumer-hermetic-")
    sb.assert_no_cell_is_filled(card)


def test_a_consumer_cell_that_acquires_a_metric_fails_the_build(card):
    tampered = copy.deepcopy(card)
    cell = next(c for c in tampered["cells"] if c["metric"] == "request_to_consumer_ms")
    cell["p50_ms"] = 1234.0
    with pytest.raises(ValueError, match="p50_ms"):
        sb.assert_no_cell_is_filled(tampered)


def test_rendered_card_names_hermetic_runs_by_id_and_prints_no_millisecond_for_them(card):
    text = sb.render_markdown(card)
    assert "| RUNNER_HERMETIC_ONLY |" in text and "| NOT_IMPLEMENTED |" not in text
    assert "because the runner has no live mode" in text
    for line in text.splitlines():
        if line.startswith("* **`sqlchain_forced_c"):
            assert "consumer-hermetic-" in line and "RUNNER_HERMETIC_OK" in line
            assert not re.search(r"\d+(\.\d+)?\s*ms", line), line
            assert "p50" not in line and "p95" not in line
    assert "the request-to-consumer runner does not exist" not in text
    assert "DECLARED_NOT_SPENT" in text


def test_the_selection_says_the_precheck_is_implemented_offline_and_not_run_live(plan):
    text = plan["facts"]["selected_version"]["live_precheck"]
    assert text.startswith("IMPLEMENTED OFFLINE, NOT RUN LIVE") and "admit_live" in text
    assert "requires its digest to equal content_manifest_sha256" in text


def test_sql_baseline_driver_refuses_consumer_cells_naming_the_hermetic_only_runner(plan):
    from okf_bq_graph import sql_baseline_run as run
    for name in ("sqlchain_forced_c1", "sqlchain_forced_c5"):
        assert run.refusal_reasons(plan, name) == ["RUNNER_HERMETIC_ONLY"]
        with pytest.raises(run.RefusedCell) as e:
            run.select_cells(plan, [name])
        assert "RUNNER_HERMETIC_ONLY" in str(e.value) and "okf_bq_graph.consumer_run" in str(e.value) and "NOT_IMPLEMENTED" not in str(e.value)
    unselected = copy.deepcopy(plan)
    unselected["facts"] = {"state": "UNSELECTED", "why_it_matters": "x", "what_is_missing": "y", "blocks": ["sqlchain_forced_c1"], "how_to_select": "z"}
    assert run.refusal_reasons(unselected, "sqlchain_forced_c1") == ["FACTS_UNSELECTED", "RUNNER_HERMETIC_ONLY"]


def test_committed_card_artifacts_equal_the_generator(tmp_path):
    written = sb.main(tmp_path)
    for name in ("plan.json", "baseline.md"):
        assert (tmp_path / name).read_bytes() == (sb.OUT_DIR / name).read_bytes(), name


# ---- fix pass after the Kimi / Astra first reviews of 2358f47
def test_admit_live_reports_drift_even_when_the_smoke_check_cannot_evaluate(plan, manifest):
    """Astra #4: schema-and-row drift (order_ts NULLABLE with a null January timestamp) must be FACTS_DRIFTED naming
    `orders`, with the smoke check retained as a diagnostic error, never a crash."""
    m = copy.deepcopy(manifest)
    t = m["tables"]["orders"]
    ts = next(f for f in t["schema"] if f["name"] == "order_ts"); ts["mode"] = "NULLABLE"
    idx = next(i for i, r in enumerate(t["rows"]) if r[0] == "ord-2026-01-delivered"); t["rows"][idx][2] = None
    out = cr.admit_live(plan["facts"]["selected_version"], m, _dt.date(2026, 9, 10), EVAL)
    assert out["status"] == "FACTS_DRIFTED" and "orders" in out["differing_tables"]
    assert out["smoke"]["january_matches"] is False and out["smoke"].get("error")


def _stage_raises(monkeypatch, name, exc):
    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(cr, name, boom)


@pytest.mark.parametrize("stage, exc", [("bind", KeyError("manifest")), ("run_receipt", OSError(5, "EIO on diagnostic rename")),
                                        ("consume", RuntimeError("consumer crashed"))])
def test_a_stage_exception_is_retained_as_an_attempt_error_and_the_run_is_incomplete(sdk_root, sample_root, short_plan, tmp_path, monkeypatch, stage, exc):
    """Kimi P1 / Astra #2: a failure at any stage after retrieval is retained on the attempt (error, REFUSED,
    NOT_REACHED), the probe still runs, and the run record is written RUNNER_HERMETIC_INCOMPLETE."""
    _stage_raises(monkeypatch, stage, exc)
    rec = cr.run_hermetic(sb.load_plan(short_plan), ["sqlchain_forced_c1"], out_dir=tmp_path, sdk_root=sdk_root,
                          acme_root=sample_root, as_of=AS_OF)
    assert rec["verdict"] == "RUNNER_HERMETIC_INCOMPLETE"
    assert len(rec["attempts"]) == 4 and [a["kind"] for a in rec["attempts"]] == ["warmup", "measured", "measured", "probe"]
    failed = [a for a in rec["attempts"] if a["error"]]
    assert failed and all(a["consume"]["decision"] == "REFUSED" and a["acceptance"]["status"] == "NOT_REACHED" for a in failed)
    assert all(type(exc).__name__ in a["error"] for a in failed)
    written = json.loads((tmp_path / f"run_{rec['run_id']}.json").read_text())
    assert written["verdict"] == "RUNNER_HERMETIC_INCOMPLETE" and len(written["attempts"]) == 4
    lines = (tmp_path / rec["run_id"] / "attempts.jsonl").read_text().splitlines()
    assert len(lines) == 4


def test_sequential_run_id_reuse_refuses_without_touching_the_existing_record(sdk_root, sample_root, short_plan, tmp_path):
    """Astra #1: a second run under an owned id is refused RUN_ID_REUSED and retains nothing; the first record is intact."""
    plan = sb.load_plan(short_plan)
    first = cr.run_hermetic(plan, ["sqlchain_forced_c1"], out_dir=tmp_path, sdk_root=sdk_root, acme_root=sample_root, as_of=AS_OF)
    path = tmp_path / f"run_{first['run_id']}.json"
    before = path.read_bytes()
    second = cr.run_hermetic(plan, ["sqlchain_forced_c1"], out_dir=tmp_path, sdk_root=sdk_root, acme_root=sample_root, as_of=AS_OF,
                             run_id=first["run_id"], runner=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not launch")))
    assert second["verdict"] == "REFUSED" and second["refusal"]["code"] == "RUN_ID_REUSED" and second["retained"] is False
    assert path.read_bytes() == before
    assert len((tmp_path / first["run_id"] / "attempts.jsonl").read_text().splitlines()) == 4


def test_concurrent_cli_invocations_with_one_run_id_yield_exactly_one_owner(sdk_root, sample_root, short_plan, tmp_path):
    """Astra #1: two processes racing for the same explicit --run-id: one owns it, the other is refused before any
    attempt; one record, one attempts.jsonl with no duplicate index."""
    rid = "consumer-hermetic-20260909T000000Z-0badcafe"
    argv = [sys.executable, "-m", "okf_bq_graph.consumer_run", "--hermetic", "--cells", "sqlchain_forced_c1", "--plan", str(short_plan),
            "--out-dir", str(tmp_path), "--run-id", rid, "--sdk-root", sdk_root, "--acme-root", sample_root, "--as-of", AS_OF]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    procs = [subprocess.Popen(argv, cwd=str(sb.ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    outs = [p.communicate(timeout=120) for p in procs]
    codes = sorted(p.returncode for p in procs)
    assert codes == [0, 2], [(p.returncode, o[0][-300:], o[1][-300:]) for p, o in zip(procs, outs)]
    refused = next(o[0] for p, o in zip(procs, outs) if p.returncode == 2)
    assert "REFUSED: RUN_ID_REUSED" in refused
    rec = json.loads((tmp_path / f"run_{rid}.json").read_text())
    assert rec["verdict"] == "RUNNER_HERMETIC_OK" and len(rec["attempts"]) == 4
    lines = [json.loads(l) for l in (tmp_path / rid / "attempts.jsonl").read_text().splitlines()]
    assert sorted(l["index"] for l in lines) == [0, 1, 2, 3]


def test_hermetic_cli_gate_refusal_is_retained_under_a_fresh_owned_record(plan, tmp_path, no_client):
    """Astra #5: a subprocess-free gate refusal in --hermetic leaves a REFUSED record; --dry-run stays write-free."""
    p = copy.deepcopy(plan)
    p["facts"] = {"state": "UNSELECTED", "why_it_matters": "x", "what_is_missing": "y", "blocks": ["sqlchain_forced_c1"], "how_to_select": "z"}
    path = tmp_path / "plan.json"; path.write_text(json.dumps(p, ensure_ascii=False))
    out = io.StringIO()
    rc = cr.main(["--hermetic", "--plan", str(path), "--out-dir", str(tmp_path / "ev")], stdout=out)
    assert rc == 2 and out.getvalue().startswith("REFUSED: FACTS_UNSELECTED")
    records = list((tmp_path / "ev").glob("run_consumer-hermetic-*.json"))
    assert len(records) == 1
    rec = json.loads(records[0].read_text())
    assert rec["verdict"] == "REFUSED" and rec["refusal"]["code"] == "FACTS_UNSELECTED" and rec["attempts"] == [] and rec["retained"] is True
    assert (tmp_path / "ev" / rec["run_id"]).is_dir()
    out = io.StringIO()
    assert cr.main(["--dry-run", "--plan", str(path), "--out-dir", str(tmp_path / "dry")], stdout=out) == 2
    assert not (tmp_path / "dry").exists()


def test_hermetic_cli_run_id_reuse_retains_nothing_new(tmp_path, no_client):
    used = "consumer-hermetic-20260909T000000Z-deadbeef"
    (tmp_path / f"run_{used}.json").write_text('{"kept": true}')
    out = io.StringIO()
    assert cr.main(["--hermetic", "--run-id", used, "--out-dir", str(tmp_path)], stdout=out) == 2
    assert out.getvalue().startswith("REFUSED: RUN_ID_REUSED")
    assert (tmp_path / f"run_{used}.json").read_text() == '{"kept": true}' and not (tmp_path / used).exists()


def test_readme_module_rows_attribute_live_campaigns_to_the_retrieval_driver_only():
    """Kimi P1 / Astra #6: the hermetic consumer row must not inherit the retrieval driver's Pass 2 history."""
    rows = {}
    for line in (sb.ROOT / "README.md").read_text().splitlines():
        if line.startswith("| `okf_bq_graph/sql_baseline_run.py` |") or line.startswith("| `okf_bq_graph/consumer_run.py` |"):
            rows[line.split("`")[1]] = line
    assert set(rows) == {"okf_bq_graph/sql_baseline_run.py", "okf_bq_graph/consumer_run.py"}
    consumer, baseline = rows["okf_bq_graph/consumer_run.py"], rows["okf_bq_graph/sql_baseline_run.py"]
    for token in ("live campaign", "1,678", "$0.17", "RETRIEVAL_MEASURED", "Pass 2", "sqlbase-2026"):
        assert token not in consumer, token
    for token in ("Four live campaigns are retained", "1,678 jobs", "Card: RETRIEVAL_MEASURED"):
        assert token in baseline, token
    assert "no BigQuery client" in consumer and "RUNNER_HERMETIC_ONLY" in consumer


def test_the_metric_definition_names_the_missing_capability_as_live_sampling(plan):
    text = plan["metrics"]["request_to_consumer_ms"]
    assert "No repeated-sample runner exists" not in text
    assert "hermetic" in text and "live" in text
    card = sb.render_markdown(sb.build_card(plan))
    assert "No repeated-sample runner exists for this today" not in card


# ---- residuals from Astra's re-review of a9d92a3
def test_receipt_invocation_evidence_survives_a_diagnostic_retention_failure(sdk_root, sample_root, short_plan, tmp_path, monkeypatch):
    """Astra RR #1: the SDK child completes, then the diagnostic rename fails (EIO). The attempt must say the child WAS
    invoked and completed, keep the private diagnostic's path, digest and request id, record the retention failure,
    and still be NOT_REACHED inside an INCOMPLETE run. Only the second real rename fails."""
    import okf_bq_graph.chain as chain_mod
    real_replace = os.replace
    calls = []

    def flaky_replace(src, dst, *a, **k):
        if Path(src).name == "case_approved_hermetic.json":
            calls.append(src)
            if len(calls) == 2:
                raise OSError(5, "Input/output error (injected on the second diagnostic rename)")
        return real_replace(src, dst, *a, **k)
    monkeypatch.setattr(chain_mod.os, "replace", flaky_replace)
    rec = cr.run_hermetic(sb.load_plan(short_plan), ["sqlchain_forced_c1"], out_dir=tmp_path, sdk_root=sdk_root,
                          acme_root=sample_root, as_of=AS_OF)
    assert rec["verdict"] == "RUNNER_HERMETIC_INCOMPLETE" and len(rec["attempts"]) == 4
    failed = [a for a in rec["attempts"] if a["error"]]
    assert len(failed) == 1 and failed[0]["index"] == 1 and "OSError" in failed[0]["error"] and failed[0]["stage_failed"] == "receipt"
    r = failed[0]["receipt"]
    assert r["invoked"] is True and r["child_completed"] is True and r["exit_code"] == 0
    assert r["diag_present"] is True and Path(r["diag_path"]).is_file() and r["diag_sha256"] and r["request_id"].startswith("req-")
    assert str(tmp_path) in r["diag_path"] and r["retention"].startswith("FAILED")
    assert r["verdict"] == "VERIFIED", "the child's own verdict is read from the diagnostic that survived"
    assert failed[0]["consume"]["decision"] == "REFUSED" and failed[0]["acceptance"]["status"] == "NOT_REACHED"
    ok = [a for a in rec["attempts"] if not a["error"]]
    assert len(ok) == 3 and all(a["acceptance"]["status"] == "MET" for a in ok)


def test_a_helper_that_raises_before_launching_says_never_invoked_and_after_launch_says_unknown(sdk_root, sample_root, short_plan, tmp_path, monkeypatch):
    """Invocation is asserted only from the runner call itself: no runner call -> invoked False; a runner that
    raised after being entered -> invoked UNKNOWN (retained as uncertainty, never as non-invocation)."""
    _stage_raises(monkeypatch, "run_receipt", RuntimeError("helper crashed before launching"))
    rec = cr.run_hermetic(sb.load_plan(short_plan), ["sqlchain_forced_c1"], out_dir=tmp_path, sdk_root=sdk_root, acme_root=sample_root, as_of=AS_OF)
    r = next(a for a in rec["attempts"] if a["error"])["receipt"]
    assert r["invoked"] is False and r["launch_attempted"] is False
    monkeypatch.undo()   # the real helper again; now the runner itself raises after being entered

    def exploding_runner(argv, **k):
        raise RuntimeError("runner died after being entered")
    rec = cr.run_hermetic(sb.load_plan(short_plan), ["sqlchain_forced_c1"], out_dir=tmp_path, sdk_root=sdk_root, acme_root=sample_root,
                          as_of=AS_OF, runner=exploding_runner)
    r = next(a for a in rec["attempts"] if a["error"])["receipt"]
    assert r["invoked"] == "UNKNOWN" and r["launch_attempted"] is True and r["child_completed"] is False
    assert rec["verdict"] == "RUNNER_HERMETIC_INCOMPLETE"


@pytest.mark.parametrize("shape, code, needle", [
    ("malformed_json", "PLAN_INVALID", "JSONDecodeError"),
    ("missing_cell_name", "PLAN_INVALID", "name"),
    ("missing_cases", "QUESTION_PINNED", "nonexistent-cases.json"),
])
def test_hermetic_cli_retains_preflight_input_failures(plan, tmp_path, no_client, shape, code, needle):
    """Astra RR #2: an unreadable/malformed plan, a plan that fails validation before cell names can be derived, or an
    absent --cases file each retain a REFUSED record under an owned directory in --hermetic; --dry-run stays write-free."""
    path = tmp_path / "plan.json"
    argv = ["--out-dir", str(tmp_path / "ev")]
    if shape == "malformed_json":
        path.write_text("{ not json"); argv += ["--plan", str(path)]
    elif shape == "missing_cell_name":
        p = copy.deepcopy(plan); del p["consumer_cells"][0]["name"]
        path.write_text(json.dumps(p, ensure_ascii=False)); argv += ["--plan", str(path)]
    else:
        argv += ["--cases", str(tmp_path / "nonexistent-cases.json")]
    out = io.StringIO()
    rc = cr.main(["--hermetic"] + argv, stdout=out)
    assert rc == 2 and out.getvalue().startswith(f"REFUSED: {code}") and needle in out.getvalue(), out.getvalue()
    records = list((tmp_path / "ev").glob("run_consumer-hermetic-*.json"))
    assert len(records) == 1, "the preflight refusal is retained"
    rec = json.loads(records[0].read_text())
    assert rec["verdict"] == "REFUSED" and rec["refusal"]["code"] == code and rec["retained"] is True and rec["attempts"] == []
    owned = tmp_path / "ev" / rec["run_id"]
    assert owned.is_dir() and any(owned.iterdir()), "no empty owned directory is left behind"
    out = io.StringIO()
    dry = [a.replace(str(tmp_path / "ev"), str(tmp_path / "dry")) for a in argv]
    assert cr.main(["--dry-run"] + dry, stdout=out) == 2 and out.getvalue().startswith(f"REFUSED: {code}")
    assert not (tmp_path / "dry").exists()
