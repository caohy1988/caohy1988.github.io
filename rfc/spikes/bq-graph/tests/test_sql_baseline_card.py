"""Hermetic gates on the card built from retained campaign records (Slice B Pass 2, 2026-09-09).

No client, no network. Records here are synthetic and shaped like `sql_baseline_run.live` output; the tests stop
the card from inventing a number, from letting an older campaign hide a newer one's outcome, and from letting a
retrieval campaign fill a consumer or cost cell.
"""
import copy
import json

import pytest

from okf_bq_graph import sql_baseline as sb

CELLS = ["sqlbase_forced_c1", "sqlbase_forced_c5", "sqlbase_natural_c1", "sqlbase_natural_c5"]


@pytest.fixture(scope="module")
def plan():
    return sb.load_plan()


def _cell(name, state="COMPLETE", n=100, reason=None, p50=200.0, p95=400.0, ok=1.0, errors=0):
    return {"cell": name, "state": state, "measured_n": n, "measured_target": 100, "warmups_done": 20 if n else 0,
            "stopped_reason": reason, "p50_ms_all": p50 if n else None, "p95_ms_all": p95 if n else None,
            "max_ms_all": p95 if n else None, "p50_ms_ok": p50 if n else None, "p95_ms_ok": p95 if n else None,
            "success_rate": ok if n else None, "errors": errors, "timeouts": 0, "jobs_total": 3 * n}


def _record(run_id, started, cells, *, state=None, preflight=None, charged=0, liability=0, edition="on-demand", error=None):
    verified = edition == "on-demand"
    rec = {"run_id": run_id, "_file": f"evidence/sql-baseline/run_{run_id}.json", "started_utc": started,
           "wall_seconds": 12.3, "cells": cells, "sdk": {"google-cloud-bigquery": "3.45.0"},
           "state": state or ("COMPLETE" if cells and all(c["state"] == "COMPLETE" for c in cells) else "INCOMPLETE"),
           "billing": {"bytes_billed_charged": charged, "usd_list_charged": round(charged / sb.TIB * 6.25, 4),
                       "unresolved_liability_bytes": liability, "unresolved_jobs": [{"job_id": "x"}] if liability else [],
                       "stop_reason": None},
           "routing": {"jobs_observed": 3 * sum(c["measured_n"] for c in cells), "jobs_verified_on_demand": 3 * sum(c["measured_n"] for c in cells),
                       "verified_on_demand": verified and bool(cells)},
           "edition": edition if cells else None, "edition_note": "synthetic"}
    if preflight is not None:
        rec["preflight"] = preflight
    if error:
        rec["error"] = error
    return rec


def _denied():
    return {"state": "DENIED", "reason": "ON_DEMAND_OVERRIDE_DENIED", "creates_job": False, "bills": False,
            "server_message": "400 Override to 'none' is not enabled. The option 'reservation_override_mode' is set to 'RESERVATION_OVERRIDE_MODE_UNSPECIFIED'.",
            "requires": {"option": "reservation_override_mode", "value": "ALLOW_ANY_OVERRIDE", "scope": "project or organization", "docs": "https://example.invalid"},
            "remedy": "set reservation_override_mode = 'ALLOW_ANY_OVERRIDE'"}


def _card(plan, records, tmp_path):
    return sb.build_card(copy.deepcopy(plan), records=records, requests_path=tmp_path / "no-requests.jsonl")


def _retrieval(card):
    return {c["cell"]: c for c in card["cells"] if c["metric"] == "retrieval_ms"}


def test_no_records_is_the_scaffold(plan, tmp_path):
    card = _card(plan, [], tmp_path)
    assert card["state"] == "SCAFFOLD_ONLY" and card["campaigns"] == [] and card["blocker"] is None
    assert all(c["campaign"] is None and c["measured_n"] == 0 for c in _retrieval(card).values())


def test_a_complete_campaign_fills_every_retrieval_cell_from_its_summary(plan, tmp_path):
    rec = _record("sqlbase-20260919-100000-aaaaaaaa", "2026-09-19T10:00:00+00:00",
                  [_cell(n, p50=100 + i, p95=300 + i) for i, n in enumerate(CELLS)], charged=30 * sb.GIB)
    card = _card(plan, [rec], tmp_path)
    assert card["state"] == "RETRIEVAL_MEASURED"
    cells = _retrieval(card)
    for i, name in enumerate(CELLS):
        c = cells[name]
        assert c["state"] == "COMPLETE" and c["measured_n"] == 100 and c["stopped_reason"] is None
        assert c["p50_ms"] == 100 + i and c["p95_ms"] == 300 + i and c["success_rate"] == 1.0
        assert c["campaign"] == rec["run_id"] and c["edition"] == "on-demand"
        assert c["bytes_billed"] is None and c["jobs_in_attempts"] == 0   # no attempts file: bytes are not invented
    assert len(card["campaigns"]) == 1 and card["campaigns"][0]["bytes_billed_charged"] == 30 * sb.GIB
    assert card["campaigns"][0]["usd_list_charged"] == round(30 * sb.GIB / sb.TIB * 6.25, 4)
    # consumer and cost cells are untouched by a retrieval campaign
    for c in card["cells"]:
        if c["metric"] != "retrieval_ms":
            assert c["state"] == "INCOMPLETE" and c["measured_n"] == 0 and c["p50_ms"] is None
    assert all(c["state"] == "UNMEASURED" and c["value"] is None for c in card["cost_cells"])


def test_a_partial_campaign_leaves_the_card_incomplete_with_reasons(plan, tmp_path):
    rec = _record("sqlbase-20260919-100000-aaaaaaaa", "2026-09-19T10:00:00+00:00",
                  [_cell(CELLS[0]), _cell(CELLS[1], state="INCOMPLETE", n=37, reason="CELL_TIME_BUDGET", ok=0.9, errors=4),
                   _cell(CELLS[2], state="NOT_RUN_BUDGET", n=0, reason="TOTAL_TIME_BUDGET"),
                   _cell(CELLS[3], state="NOT_RUN_BUDGET", n=0, reason="TOTAL_TIME_BUDGET")])
    card = _card(plan, [rec], tmp_path)
    assert card["state"] == "INCOMPLETE" and "1 of 4 retrieval cells COMPLETE" in card["state_note"]
    cells = _retrieval(card)
    assert cells[CELLS[1]]["state"] == "INCOMPLETE" and cells[CELLS[1]]["measured_n"] == 37 and cells[CELLS[1]]["stopped_reason"] == "CELL_TIME_BUDGET"
    assert cells[CELLS[1]]["success_rate"] == 0.9 and cells[CELLS[1]]["errors"] == 4
    assert cells[CELLS[2]]["state"] == "NOT_RUN_BUDGET" and cells[CELLS[2]]["p50_ms"] is None and cells[CELLS[2]]["campaign"] == rec["run_id"]


def test_the_newest_measured_campaign_wins_and_an_unmeasured_newer_one_does_not_hide_it(plan, tmp_path):
    older = _record("sqlbase-20260919-100000-aaaaaaaa", "2026-09-19T10:00:00+00:00", [_cell(CELLS[0], p50=111)])
    newer_measured = _record("sqlbase-20260919-110000-bbbbbbbb", "2026-09-19T11:00:00+00:00",
                             [_cell(CELLS[0], state="INCOMPLETE", n=44, reason="BYTES_BUDGET_UNRESOLVED", p50=138.7, p95=185.0, ok=0.0, errors=44)],
                             liability=64 * sb.GIB, edition=None)
    newest_unmeasured = _record("sqlbase-20260919-120000-cccccccc", "2026-09-19T12:00:00+00:00",
                                [_cell(n, state="NOT_RUN_PREFLIGHT", n=0, reason="ON_DEMAND_OVERRIDE_DENIED") for n in CELLS],
                                preflight=_denied(), edition=None)
    # records are sorted by the card, whatever order they arrive in
    card = _card(plan, [newest_unmeasured, older, newer_measured], tmp_path)
    cells = _retrieval(card)
    c1 = cells[CELLS[0]]
    assert c1["campaign"] == newer_measured["run_id"] and c1["measured_n"] == 44 and c1["p50_ms"] == 138.7
    assert c1["state"] == "INCOMPLETE" and c1["stopped_reason"] == "BYTES_BUDGET_UNRESOLVED" and c1["success_rate"] == 0.0
    assert c1["edition"] is None
    for name in CELLS[1:]:
        assert cells[name]["campaign"] == newest_unmeasured["run_id"] and cells[name]["state"] == "NOT_RUN_PREFLIGHT"
        assert cells[name]["stopped_reason"] == "ON_DEMAND_OVERRIDE_DENIED" and cells[name]["p50_ms"] is None
    assert [c["run_id"] for c in card["campaigns"]] == [older["run_id"], newer_measured["run_id"], newest_unmeasured["run_id"]]
    assert card["campaigns"][1]["unresolved_liability_bytes"] == 64 * sb.GIB and card["campaigns"][1]["edition"] is None
    assert card["state"] == "INCOMPLETE"


def test_the_blocker_is_read_from_the_newest_record_only(plan, tmp_path):
    denied = _record("sqlbase-20260919-100000-aaaaaaaa", "2026-09-19T10:00:00+00:00",
                     [_cell(n, state="NOT_RUN_PREFLIGHT", n=0, reason="ON_DEMAND_OVERRIDE_DENIED") for n in CELLS],
                     preflight=_denied(), edition=None)
    card = _card(plan, [denied], tmp_path)
    b = card["blocker"]
    assert b["campaign"] == denied["run_id"] and b["reason"] == "ON_DEMAND_OVERRIDE_DENIED"
    assert b["requires"]["option"] == "reservation_override_mode" and b["requires"]["value"] == "ALLOW_ANY_OVERRIDE"
    assert "bigquery.config.update" in b["who"] and "different measurement" in b["why_not_worked_around"]
    text = sb.render_markdown(card)
    assert "## Blocked" in text and "reservation_override_mode = ALLOW_ANY_OVERRIDE" in text and "**INCOMPLETE**" in text
    # a later campaign whose preflight passed clears the blocker even if it stopped for another reason
    later = _record("sqlbase-20260919-110000-bbbbbbbb", "2026-09-19T11:00:00+00:00",
                    [_cell(CELLS[0], state="INCOMPLETE", n=5, reason="CELL_TIME_BUDGET")],
                    preflight={"state": "OK", "reason": None, "creates_job": False, "bills": False})
    assert _card(plan, [denied, later], tmp_path)["blocker"] is None


def test_an_aborted_campaign_is_listed_and_fills_nothing(plan, tmp_path):
    aborted = _record("sqlbase-20260919-100000-aaaaaaaa", "2026-09-19T10:00:00+00:00", [], state="ABORTED",
                      error="KeyboardInterrupt: ", edition=None)
    card = _card(plan, [aborted], tmp_path)
    assert card["state"] == "INCOMPLETE" and card["campaigns"][0]["state"] == "ABORTED" and card["campaigns"][0]["error"]
    assert all(c["campaign"] is None and c["stopped_reason"] == "NOT_RUN" for c in _retrieval(card).values())
    assert "aborted: `KeyboardInterrupt" in sb.render_markdown(card)


def test_bytes_come_from_the_retained_attempts_of_that_cell_only(plan, tmp_path):
    rec = _record("sqlbase-20260919-100000-aaaaaaaa", "2026-09-19T10:00:00+00:00",
                  [_cell(CELLS[0], state="INCOMPLETE", n=2, reason="CELL_TIME_BUDGET"),
                   _cell(CELLS[1], state="INCOMPLETE", n=1, reason="CELL_TIME_BUDGET", ok=0.0, errors=1)])
    requests = tmp_path / "requests.jsonl"
    rows = [
        {"run_id": rec["run_id"], "cell": CELLS[0], "warmup": True, "ok": True, "timing": {"jobs": [{"bytes_billed": 10 * 1024 ** 2}]}},
        {"run_id": rec["run_id"], "cell": CELLS[0], "warmup": False, "ok": True, "timing": {"jobs": [{"bytes_billed": 20 * 1024 ** 2}, {"bytes_billed": None}]}},
        {"run_id": rec["run_id"], "cell": CELLS[1], "warmup": False, "ok": False, "error": "BadRequest: synthetic", "timing": {"jobs": [{"bytes_billed": 5 * 1024 ** 2}]}},
        {"run_id": "sqlbase-20260919-000000-other000", "cell": CELLS[0], "warmup": False, "ok": True, "timing": {"jobs": [{"bytes_billed": 999 * 1024 ** 2}]}},
    ]
    requests.write_text("".join(json.dumps(r) + "\n" for r in rows))
    card = sb.build_card(copy.deepcopy(plan), records=[rec], requests_path=requests)
    cells = _retrieval(card)
    assert cells[CELLS[0]]["bytes_billed"] == 30 * 1024 ** 2 and cells[CELLS[0]]["jobs_in_attempts"] == 3 and cells[CELLS[0]]["jobs_without_billing"] == 1
    assert cells[CELLS[0]]["attempts_retained"] == 2 and cells[CELLS[0]]["usd_ondemand_list"] == round(30 * 1024 ** 2 / sb.TIB * 6.25, 4)
    assert cells[CELLS[1]]["bytes_billed"] == 5 * 1024 ** 2 and cells[CELLS[1]]["first_error"] == "BadRequest: synthetic"
    camp = card["campaigns"][0]
    assert camp["attempts_retained"] == 3 and camp["attempts_ok"] == 2 and camp["attempts_first_error"] == "BadRequest: synthetic"


def test_a_number_no_record_carries_fails_the_build(plan, tmp_path):
    rec = _record("sqlbase-20260919-100000-aaaaaaaa", "2026-09-19T10:00:00+00:00", [_cell(n) for n in CELLS])
    card = _card(plan, [rec], tmp_path)
    tampered = copy.deepcopy(card)
    next(c for c in tampered["cells"] if c["cell"] == CELLS[0])["p50_ms"] = 1.0
    with pytest.raises(ValueError, match="p50_ms"):
        sb.assert_filled_cells_trace_to_records(tampered, [rec])
    tampered = copy.deepcopy(card)
    next(c for c in tampered["cells"] if c["cell"] == CELLS[0])["campaign"] = "sqlbase-20260919-000000-missing0"
    with pytest.raises(ValueError, match="not retained"):
        sb.assert_filled_cells_trace_to_records(tampered, [rec])
    tampered = copy.deepcopy(card)
    consumer = next(c for c in tampered["cells"] if c["metric"] != "retrieval_ms")
    consumer["measured_n"] = 20
    with pytest.raises(ValueError, match="cannot be filled by a retrieval campaign"):
        sb.assert_filled_cells_trace_to_records(tampered, [rec])
    tampered = copy.deepcopy(card)
    next(c for c in tampered["cells"] if c["cell"] == CELLS[0])["campaign"] = None
    with pytest.raises(ValueError, match="names no campaign"):
        sb.assert_filled_cells_trace_to_records(tampered, [rec])


def test_a_complete_cell_short_of_its_target_fails_the_build(plan, tmp_path):
    rec = _record("sqlbase-20260919-100000-aaaaaaaa", "2026-09-19T10:00:00+00:00", [_cell(CELLS[0], n=99)])
    with pytest.raises(ValueError, match="COMPLETE with n=99/100"):
        _card(plan, [rec], tmp_path)


def test_rendered_card_names_campaigns_and_reasons(plan, tmp_path):
    rec = _record("sqlbase-20260919-100000-aaaaaaaa", "2026-09-19T10:00:00+00:00",
                  [_cell(CELLS[0]), _cell(CELLS[1], state="INCOMPLETE", n=44, reason="BYTES_BUDGET_UNRESOLVED", ok=0.0, errors=44)],
                  liability=64 * sb.GIB, edition=None)
    text = sb.render_markdown(_card(plan, [rec], tmp_path))
    assert "## Campaigns" in text and rec["run_id"] in text and "64 GiB / 1 jobs" in text
    assert "| 100 / 100 | **COMPLETE** | 200 | 400 | 100% |" in text
    assert "| 44 / 100 | **INCOMPLETE** | 200 | 400 | 0% |" in text and "BYTES_BUDGET_UNRESOLVED" in text
    assert "predeclared, campaigns retained, not measured" in text
    assert "## Blocked" not in text


def test_committed_records_build_the_committed_card(plan):
    """The committed card is built from the committed records; the driver's own records must satisfy the card's gates."""
    records = sb.campaign_records()
    card = sb.build_card(copy.deepcopy(plan))
    assert [c["run_id"] for c in card["campaigns"]] == [r["run_id"] for r in records]
    for c in _retrieval(card).values():
        if c["campaign"]:
            assert c["campaign"] in {r["run_id"] for r in records}
