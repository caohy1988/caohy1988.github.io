"""Driver for the predeclared ordinary-SQL baseline cells (2026-09-19 checkpoint, Slice B).

Slice A (`sql_baseline.py`) predeclared four retrieval cells on the `fallback` engine and left every one
of them INCOMPLETE because no driver reached `benchmark.measure` with the right shape. This module is
that driver. It reads the committed plan (`fixtures/sql_baseline.json`, the file
`evidence/sql-baseline/plan.json` is rendered from), builds one `benchmark.measure` cell per retrieval
cell, and hands each cell **only its own shape's queries**: the forced cells see the three forced seeds,
the natural cells see the six natural questions, never both. Sampling, per-attempt retention in
`evidence/requests.jsonl` and nearest-rank aggregation stay in `benchmark.measure`; nothing here
re-implements them.

What the driver refuses to do, by construction rather than by comment:

* Run a consumer cell (`sqlchain_*`). Those need a request-to-consumer runner that does not exist
  (`NOT_IMPLEMENTED`) and, while `facts.state` is UNSELECTED, a fact-data version nobody has chosen
  (`FACTS_UNSELECTED`). Asking for one raises `RefusedCell` naming both reasons.
* Reuse a `run_id`. Every campaign gets a fresh `sqlbase-<utc>-<hex>` id and `assert_run_id_is_fresh`
  checks the retained summary before any client exists; `benchmark.measure` checks again.
* Open a reservation window. Baseline cells run on-demand: the budget carries `cell_seconds` and a
  total deadline, never a `window`, and the module does not import `reservation` or `lifecycle`.
* Open a client in `--dry-run`. The BigQuery client is constructed lazily inside the per-thread factory
  that only `--live` builds, so a dry run prints the campaign and touches nothing.

`--live` (Pass 2) runs the campaign foreground, writes `evidence/sql-baseline/run_<run_id>.json` with the
cell summaries beside the plan, and leaves the card regeneration to a separate, reviewed step: a stopped
cell stays INCOMPLETE with its attempts retained, and no percentile is invented for it.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import secrets
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from google.cloud import bigquery

from . import PROJECT, LOCATION
from . import benchmark
from . import sql_baseline as sb

ROOT = sb.ROOT
CASES = ROOT / "fixtures" / "cases.json"
OUT_DIR = sb.OUT_DIR
ENGINE = "fallback"
EMBEDDING_MODEL = "text-embedding-005"   # the natural shape embeds the question; the forced shape does not
SEED = 20260919                           # deterministic query order per cell; the checkpoint date, not a measurement
FORCED_PREFIX = "forced:"
RUN_ID_PREFIX = "sqlbase"
TOTAL_DEADLINE_REASON = "TOTAL_TIME_BUDGET"


class RefusedCell(ValueError):
    """A cell this driver must not pretend to fill."""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


# --- plan → cells ----------------------------------------------------------------------------------

def load_cases(path: Path | str = CASES) -> dict:
    return json.loads(Path(path).read_text())


def retrieval_cell_names(plan: dict) -> list[str]:
    return [c["name"] for c in plan["retrieval_cells"]]


def consumer_cell_names(plan: dict) -> list[str]:
    return [c["name"] for c in plan["consumer_cells"]]


def refusal_reasons(plan: dict, name: str) -> list[str]:
    """Why a consumer cell cannot be run here. Always NOT_IMPLEMENTED; FACTS_UNSELECTED while it applies."""
    reasons = ["NOT_IMPLEMENTED"]
    facts = plan["facts"]
    if facts["state"] == "UNSELECTED" and name in facts.get("blocks", []):
        reasons.insert(0, "FACTS_UNSELECTED")
    return reasons


def select_cells(plan: dict, names: list[str] | None = None) -> list[dict]:
    """The retrieval cells to run, in plan order. A consumer cell name is refused, not skipped."""
    retrieval = {c["name"]: c for c in plan["retrieval_cells"]}
    consumer = set(consumer_cell_names(plan))
    if not names:
        return list(retrieval.values())
    chosen = []
    for name in names:
        if name in consumer:
            reasons = refusal_reasons(plan, name)
            raise RefusedCell(
                f"{name}: this driver measures retrieval_ms only and refuses to pretend to fill a "
                f"request_to_consumer_ms cell ({' + '.join(reasons)}). "
                + ("No fact-data version is selected, so two runs of it would not be comparable. " if "FACTS_UNSELECTED" in reasons else "")
                + "No sampled request-to-consumer runner exists; okf_bq_graph.chain runs each case once.")
        if name not in retrieval:
            raise ValueError(f"{name}: not a cell in the sql-baseline plan (retrieval cells: {sorted(retrieval)})")
        if name in {c["name"] for c in chosen}:
            raise ValueError(f"{name}: listed twice")
        chosen.append(retrieval[name])
    return chosen


def queries_for_shape(plan: dict, cases: dict, shape: str) -> list[dict]:
    """Only the pinned questions of one shape, each bound to the plan's corpus.

    The plan pins question ids; the texts come from `fixtures/cases.json` at the plan's `as_of`. A forced
    seed must carry the `forced:` prefix and a natural question must not: a text that violates its shape
    is a fixture defect, and it fails here rather than being measured under the wrong label.
    """
    q = plan["questions"]
    if cases.get("as_of") != q["as_of"]:
        raise ValueError(f"cases.json as_of {cases.get('as_of')!r} != plan questions.as_of {q['as_of']!r}")
    if shape == "forced":
        wanted, pool = q["forced_seed_ids"], cases["forced_seeds"]
    elif shape == "natural":
        wanted, pool = q["natural_query_ids"], cases["natural_queries"]
    else:
        raise ValueError(f"unknown shape {shape!r}")
    by_id = {x["id"]: x for x in pool}
    missing = [i for i in wanted if i not in by_id]
    if missing:
        raise ValueError(f"{shape}: plan pins question ids absent from cases.json: {missing}")
    out = []
    for qid in wanted:
        text = by_id[qid]["text"]
        forced = text.startswith(FORCED_PREFIX)
        if forced != (shape == "forced"):
            raise ValueError(f"{qid}: text {text!r} is not a {shape} question")
        out.append({"id": qid, "text": text, "shape": shape,
                    "bundle_id": plan["corpus"]["bundle_id"], "publication_id": plan["corpus"]["publication_id"]})
    if not out:
        raise ValueError(f"{shape}: the plan pins no questions of this shape")
    return out


def cell_config(plan: dict, cell: dict, cases: dict) -> dict:
    """One `benchmark.measure` cell: engine, corpus, sample sizes and timeout from the plan, queries of one shape."""
    if plan["engine"] != ENGINE:
        raise ValueError(f"plan engine is {plan['engine']!r}; this driver is the {ENGINE!r} comparator only")
    if cell["name"] not in retrieval_cell_names(plan):
        raise RefusedCell(f"{cell['name']}: not a retrieval cell")
    corpus = plan["corpus"]
    return {
        "name": cell["name"],
        "engine": ENGINE,
        "corpus": corpus["bundle_id"],
        "ds": corpus["dataset"],
        "publication_id": corpus["publication_id"],
        "bundles": None,
        "shape": cell["shape"],
        "concurrency": cell["concurrency"],
        "warmups": cell["warmups"],
        "measured": cell["measured"],
        "timeout_s": cell["timeout_s"],
        "as_of": plan["questions"]["as_of"],
        "seed": SEED,
        "top_k": 5,
        "model": EMBEDDING_MODEL if cell["shape"] == "natural" else None,
        "queries": queries_for_shape(plan, cases, cell["shape"]),
    }


# --- run_id -----------------------------------------------------------------------------------------

def fresh_run_id(now: _dt.datetime | None = None, token: str | None = None) -> str:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    return f"{RUN_ID_PREFIX}-{now.strftime('%Y%m%dT%H%M%SZ')}-{token or secrets.token_hex(4)}"


def assert_run_id_is_fresh(run_id: str, summary_path: Path | str | None = None, out_dir: Path | str | None = None) -> None:
    """Refuse a run_id that any retained summary already carries. Runs before a client exists.

    `benchmark.measure` raises on the same collision; this gate exists so a `--dry-run` reports it and a
    `--live` run never reaches the client constructor with a doomed id.
    """
    if not run_id or not run_id.startswith(RUN_ID_PREFIX + "-"):
        raise ValueError(f"run_id {run_id!r} must start with {RUN_ID_PREFIX + '-'!r}: baseline campaigns are labelled")
    summary = Path(summary_path or benchmark.SUMMARY)
    if summary.exists():
        retained = json.loads(summary.read_text()).get("cells", [])
        clashes = sorted({c["cell"] for c in retained if c.get("run_id") == run_id})
        if clashes:
            raise ValueError(f"run_id {run_id!r} already has a retained summary for {clashes}; a new campaign needs a new run_id")
    record = Path(out_dir or OUT_DIR) / f"run_{run_id}.json"
    if record.exists():
        raise ValueError(f"run_id {run_id!r} already has a campaign record at {record}")


# --- campaign ---------------------------------------------------------------------------------------

def build_campaign(plan: dict, cases: dict, names: list[str] | None = None, run_id: str | None = None) -> dict:
    """Everything `--live` will hand to `benchmark.measure`, computed without a client."""
    sb.validate_plan(plan)
    cells = [cell_config(plan, c, cases) for c in select_cells(plan, names)]
    budget = plan["budget"]
    projection = sb.project_budget(plan, sb.prior_observations(ROOT))
    return {
        "run_id": run_id or fresh_run_id(),
        "plan_version": plan["version"],
        "engine": ENGINE,
        "edition": "on-demand",
        "reservation": None,
        "project": PROJECT,
        "location": LOCATION,
        "dataset": plan["corpus"]["dataset"],
        "cells": cells,
        "budget": {
            "cell_seconds": budget["max_wall_seconds_per_cell"],
            "total_seconds": budget["max_wall_seconds_total"],
            "max_bytes_billed_gib": budget["max_bytes_billed_gib"],
            "max_usd_ondemand_list": budget["max_usd_ondemand_list"],
            "deadline_reason": TOTAL_DEADLINE_REASON,
            "stop_rule": budget["stop_rule"],
        },
        "budget_projection": {k: projection[k] for k in ("bytes_billed_projected_total", "usd_ondemand_list_projected", "within_budget",
                                                          "shapes_without_observed_bytes")},
        "cache": {"bigquery_result_cache": False, "retrieval_cache": False},
        "refused": {name: refusal_reasons(plan, name) for name in consumer_cell_names(plan)},
    }


def assert_campaign_is_runnable(campaign: dict) -> None:
    """Gates that must hold before a paid request is sent; all evaluable offline."""
    if not campaign["cells"]:
        raise ValueError("no retrieval cells selected")
    if campaign["reservation"] is not None or "window" in campaign["budget"]:
        raise ValueError("baseline cells run on-demand: no reservation window may be attached")
    if not campaign["budget_projection"]["within_budget"]:
        raise ValueError(f"projected bytes/usd exceed the declared ceiling: {campaign['budget_projection']}")
    if sum(campaign["budget"]["cell_seconds"] for _ in campaign["cells"]) > campaign["budget"]["total_seconds"]:
        raise ValueError("per-cell ceilings sum past the total ceiling; the total deadline would cut the last cell short by construction")
    for cell in campaign["cells"]:
        shapes = {q["shape"] for q in cell["queries"]}
        prefixes = {q["text"].startswith(FORCED_PREFIX) for q in cell["queries"]}
        if shapes != {cell["shape"]} or prefixes != {cell["shape"] == "forced"}:
            raise ValueError(f"{cell['name']}: query list mixes shapes ({sorted(shapes)})")
        if cell["engine"] != ENGINE:
            raise ValueError(f"{cell['name']}: engine {cell['engine']!r} is not the ordinary-SQL comparator")


def measure_config(campaign: dict, started_monotonic: float | None = None) -> dict:
    """The `benchmark.measure` config: one shared run_id, per-cell query lists, total deadline, no window."""
    started = time.monotonic() if started_monotonic is None else started_monotonic
    return {
        "run_id": campaign["run_id"],
        "cells": [dict(c) for c in campaign["cells"]],
        "queries": [],   # every cell carries its own shape; nothing is pooled here
        "budget": {
            "cell_seconds": campaign["budget"]["cell_seconds"],
            "deadline_monotonic": started + campaign["budget"]["total_seconds"],
            "deadline_reason": campaign["budget"]["deadline_reason"],
        },
    }


def client_factory(dataset: str, make_client: Callable[[], Any] | None = None) -> Callable[[], dict]:
    """Per-thread `fallback` clients with both caches off. The client is built on first use, never at import
    or at campaign-build time, which is what keeps `--dry-run` client-free."""
    local = threading.local()
    make = make_client or (lambda: bigquery.Client(project=PROJECT, location=LOCATION))

    def get() -> dict:
        if not hasattr(local, "c"):
            local.c = make()
        return {"engine": ENGINE, "bq": local.c, "ds": dataset, "use_cache": False}
    return get


def describe(campaign: dict) -> str:
    b = campaign["budget"]
    p = campaign["budget_projection"]
    lines = [
        f"sql-baseline campaign {campaign['run_id']} — plan {campaign['plan_version']}, engine {campaign['engine']}, "
        f"{campaign['edition']}, reservation none, dataset {campaign['project']}.{campaign['dataset']}",
        f"budget: {b['cell_seconds']} s per cell, {b['total_seconds']} s total ({b['deadline_reason']} when reached), "
        f"{b['max_bytes_billed_gib']} GiB billed, ${b['max_usd_ondemand_list']:.2f} at list; projection "
        f"{p['bytes_billed_projected_total'] / sb.GIB:.1f} GiB → ${p['usd_ondemand_list_projected']:.2f} "
        f"({'within' if p['within_budget'] else 'NOT within'} ceiling)",
        "caches: bigquery result cache off, retrieval cache off",
    ]
    for c in campaign["cells"]:
        lines.append(f"  {c['name']}: shape={c['shape']} C={c['concurrency']} warmups={c['warmups']} measured={c['measured']} "
                     f"timeout={c['timeout_s']}s queries={[q['id'] for q in c['queries']]}")
    for name, reasons in campaign["refused"].items():
        lines.append(f"  {name}: REFUSED ({' + '.join(reasons)})")
    return "\n".join(lines)


# --- live ---------------------------------------------------------------------------------------------

def live(campaign: dict, out_dir: Path | str = OUT_DIR, make_client: Callable[[], Any] | None = None,
         measure: Callable[[dict, Callable[[], dict]], dict] | None = None) -> dict:
    """Run the campaign foreground and retain its record. Percentiles come from `benchmark.measure` only."""
    assert_campaign_is_runnable(campaign)
    assert_run_id_is_fresh(campaign["run_id"], out_dir=out_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    measure = measure or benchmark.measure
    started_utc, started = _now(), time.monotonic()
    record: dict[str, Any] = {k: v for k, v in campaign.items() if k != "cells"}
    record.update({
        "started_utc": started_utc,
        "cells_declared": [{k: v for k, v in c.items() if k != "queries"} | {"query_ids": [q["id"] for q in c["queries"]]}
                           for c in campaign["cells"]],
        "sdk": {"google-cloud-bigquery": getattr(bigquery, "__version__", None)},
        "requests_file": benchmark.REQUESTS,
        "summary_file": benchmark.SUMMARY,
        "note": ("retrieval_ms only; every attempt retained before aggregation; a cell stopped by its budget stays "
                 "INCOMPLETE / NOT_RUN_BUDGET and carries no invented percentile. The card under evidence/sql-baseline "
                 "is regenerated from this record in a separate reviewed step."),
    })
    try:
        result = measure(measure_config(campaign, started), client_factory(campaign["dataset"], make_client))
        record["cells"] = result["cells"]
        record["state"] = "COMPLETE" if all(c["state"] == "COMPLETE" for c in result["cells"]) else "INCOMPLETE"
    except BaseException as e:  # noqa: BLE001 - the record is retained with the failure named
        record["cells"] = []
        record["state"] = "ABORTED"
        record["error"] = f"{type(e).__name__}: {e}"[:500]
        raise
    finally:
        record["ended_utc"] = _now()
        record["wall_seconds"] = round(time.monotonic() - started, 1)
        (out_dir / f"run_{campaign['run_id']}.json").write_text(json.dumps(record, indent=2, default=str) + "\n")
    return record


# --- CLI ----------------------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python3 -m okf_bq_graph.sql_baseline_run",
                                 description="Run the predeclared ordinary-SQL baseline retrieval cells (fallback engine, on-demand).")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="print the campaign (cells, queries, budget, run_id); open no client")
    mode.add_argument("--live", action="store_true", help="run the campaign foreground against BigQuery on-demand")
    ap.add_argument("--cells", nargs="+", metavar="CELL", help="retrieval cells to run (default: all four); sqlchain_* are refused")
    ap.add_argument("--run-id", help="campaign run_id (default: fresh sqlbase-<utc>-<hex>); must be unused")
    ap.add_argument("--plan", default=str(sb.PLAN), help="sql-baseline plan JSON (default: fixtures/sql_baseline.json)")
    ap.add_argument("--cases", default=str(CASES), help="pinned question set (default: fixtures/cases.json)")
    ap.add_argument("--out-dir", default=str(OUT_DIR), help="where run_<run_id>.json is retained")
    return ap


def main(argv: list[str] | None = None, stdout=None) -> int:
    out = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    try:
        campaign = build_campaign(sb.load_plan(args.plan), load_cases(args.cases), args.cells, args.run_id)
        assert_campaign_is_runnable(campaign)
        assert_run_id_is_fresh(campaign["run_id"], out_dir=args.out_dir)
    except RefusedCell as e:
        print(f"REFUSED: {e}", file=out)
        return 2
    except ValueError as e:
        print(f"INVALID: {e}", file=out)
        return 2
    print(describe(campaign), file=out)
    if args.dry_run:
        print("dry run: no client opened, nothing submitted", file=out)
        return 0
    record = live(campaign, out_dir=args.out_dir)
    for c in record["cells"]:
        print(f"  {c['cell']}: {c['state']} n={c['measured_n']}/{c['measured_target']} "
              f"p50_all={c['p50_ms_all']} p95_all={c['p95_ms_all']} stopped={c['stopped_reason']}", file=out)
    print(f"{record['state']}: retained {Path(args.out_dir) / ('run_' + record['run_id'] + '.json')}", file=out)
    return 0 if record["state"] == "COMPLETE" else 1


if __name__ == "__main__":
    sys.exit(main())
