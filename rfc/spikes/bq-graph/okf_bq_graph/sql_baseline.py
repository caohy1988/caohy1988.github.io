"""Bounded ordinary-SQL baseline scaffold for the 2026-09-19 checkpoint (Slice A).

This module predeclares a measurement and refuses to pretend one happened. It reads the
predeclared plan (`fixtures/sql_baseline.json`), reads the *recorded* prior SQL observations out
of the retained evidence files, projects the declared samples against the declared budget, and
writes a card in which every cell is INCOMPLETE with the exact command that would fill it.

Three rules the code enforces rather than documents:

* A prior observation never fills a cell. Each one is n=1 or n=2 at C=1 from a different run, and
  `fills_cell` is False for all of them: `assert_no_cell_is_filled` fails the build if that changes.
* Retrieval latency and full request-to-consumer latency are separate cells with separate runners.
  The consumer runner does not exist yet, so those cells carry NOT_IMPLEMENTED and say what is missing.
* Every number that was not measured is named. `UNMEASURED` cost cells are part of the card, not
  omitted from it, because an absent row reads as zero.
* A workload field that has not been chosen says so, and the card reports whichever state the plan is
  actually in. The corpus pin fixes the authored definitions and the graph projection but identifies no
  fact data; until 2026-09-09 the committed plan was `UNSELECTED` and the cells it blocked carried that reason
  rather than looking merely unrun. Since then it is `SELECTED`: the version is the digest of the receipt
  example's *synthetic* fixture script at the pinned SDK commit (`facts.selected_version`, flat so it renders
  field by field), vendored under `fixtures/facts/` with its expected results and a canonical content manifest
  that `_validate_facts` re-hashes and re-derives on every build. Selecting clears `FACTS_UNSELECTED` only: the
  consumer cells stay `NOT_IMPLEMENTED`, the live rows are recorded `UNVERIFIED` against the digest, customer
  (Alder) data stays `NOT SELECTED` as its own block, and `_render_facts` branches on the state either way.

Since Pass 2 (2026-09-09) the card also reads the retained campaign records the driver writes
(`evidence/sql-baseline/run_<run_id>.json`, see `sql_baseline_run.py`). A retrieval cell is filled from the
latest campaign that carried it, and only with what that campaign's `benchmark.measure` summary says: its
sample count, its state, its stop reason, its nearest-rank percentiles over ALL attempts (failures included).
A cell whose latest campaign never measured it stays INCOMPLETE with that campaign's reason; a campaign
record fills nothing it did not measure. `assert_filled_cells_trace_to_records` fails the build if a cell
carries a number no record carries. Consumer cells and cost cells are never filled from records.

Nothing here opens a BigQuery client or spends anything. `python3 -m okf_bq_graph.sql_baseline`
regenerates `evidence/sql-baseline/{plan.json,baseline.md}` offline.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from typing import Any

from okf_bq_graph import fact_content

ROOT = Path(__file__).resolve().parent.parent
FACTS_DIR = ROOT / "fixtures" / "facts"
PLAN = ROOT / "fixtures" / "sql_baseline.json"
OUT_DIR = ROOT / "evidence" / "sql-baseline"
REQUESTS = ROOT / "evidence" / "requests.jsonl"
RECORD_GLOB = "run_sqlbase-*.json"

GIB = 1024 ** 3
TIB = 1024 ** 4

#: Retained records that already measured ordinary SQL retrieval on this corpus. Each entry names
#: the file and the shape; every other field is read out of the file, never restated here.
PRIOR_SOURCES = [
    {"source": "evidence/landmine_forced_fallback.json", "at": None, "shape": "forced",
     "query": "forced:metrics/gross-margin-legacy.md"},
    {"source": "evidence/all_all-0017.json", "at": ["fallback_forced"], "shape": "forced",
     "query": "forced:metrics/gross-margin-legacy.md"},
    {"source": "evidence/natural_question_fallback.json", "at": None, "shape": "natural",
     "query": "one natural question (see the record's own scope)"},
]

WHY_NOT_A_CELL = (
    "n=1 at C=1 from an integration run, not a sample from this cell: no warmups, no declared "
    "sample size, no failure denominator, and not comparable with the other shape."
)


def load_plan(path: Path | str = PLAN) -> dict:
    return json.loads(Path(path).read_text())


def validate_plan(plan: dict) -> None:
    """Structural gates. A plan that cannot be compared to an envelope is not a plan."""
    for key in ("version", "engine", "corpus", "questions", "facts", "warmup_and_cache", "budget", "metrics",
                "retrieval_cells", "consumer_cells", "cost_cells"):
        if key not in plan:
            raise ValueError(f"sql_baseline plan is missing {key!r}")
    for group in ("retrieval_cells", "consumer_cells"):
        if not plan[group]:
            raise ValueError(f"{group} is empty")
        for cell in plan[group]:
            for key in ("name", "shape", "concurrency", "warmups", "measured", "timeout_s"):
                if key not in cell:
                    raise ValueError(f"{group} cell {cell.get('name')!r} does not predeclare {key!r}")
            if cell["measured"] < 1 or cell["warmups"] < 0:
                raise ValueError(f"{cell['name']}: sample counts must be predeclared and positive")
    names = [c["name"] for c in plan["retrieval_cells"] + plan["consumer_cells"]]
    if len(names) != len(set(names)):
        raise ValueError("cell names must be unique")
    concurrencies = {c["concurrency"] for c in plan["retrieval_cells"]}
    if 1 not in concurrencies:
        raise ValueError("a C=1 retrieval cell is required: it is the only concurrency any prior observation covers")
    if len(concurrencies) < 2:
        raise ValueError("declare one proposed concurrency beside C=1, or the cells cannot answer a concurrency question")
    for key in ("retrieval_ms", "request_to_consumer_ms", "separation_rule"):
        if key not in plan["metrics"]:
            raise ValueError(f"metrics must define {key!r} so the two latencies are not substituted for each other")
    for key in ("max_wall_seconds_per_cell", "max_wall_seconds_total", "max_bytes_billed_gib",
                "max_usd_ondemand_list", "ondemand_usd_per_tib", "stop_rule"):
        if key not in plan["budget"]:
            raise ValueError(f"budget must predeclare {key!r}")
    _validate_facts(plan)
    for cell in plan["cost_cells"]:
        if cell["name"] == "cost_per_success" and "formula" not in cell:
            raise ValueError("cost_per_success must state its formula: the denominator is contested and easy to invert")


_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_ABOUT_DATE = re.compile(r"^about (\d{4}-\d{2}-\d{2})\b")
SELECTED_VERSION_REQUIRED = (
    "kind", "synthetic", "customer_data", "dataset", "location", "tables", "sdk_pin", "fixture_path",
    "fixture_sha256", "expected_results_sha256", "publication_manifest_sha256", "computation_sha256",
    "content_manifest_sha256", "row_counts",
    "row_count_total", "live_materialization", "historical_chain_equivalence", "valid_for_runs_on_or_after",
    "materialization_expires_utc",
)


def _validate_facts(plan: dict) -> None:
    """The corpus pin fixes definitions, not facts. An unchosen fact version has to say so."""
    facts = plan["facts"]
    if facts.get("state") not in ("SELECTED", "UNSELECTED"):
        raise ValueError("facts.state must be SELECTED or UNSELECTED; a missing state reads as chosen")
    if facts["state"] == "SELECTED":
        if not facts.get("selected_version"):
            raise ValueError("facts.state is SELECTED but no selected_version is recorded")
        if facts.get("blocks"):
            raise ValueError("facts.state is SELECTED but it still blocks cells: clear `blocks` or keep the state UNSELECTED")
        _validate_selected_version(facts)
        return
    for key in ("why_it_matters", "what_is_missing", "blocks", "how_to_select"):
        if not facts.get(key):
            raise ValueError(f"an UNSELECTED fact version must record {key!r}")
    names = {c["name"] for c in plan["retrieval_cells"] + plan["consumer_cells"]}
    unknown = [n for n in facts["blocks"] if n not in names]
    if unknown:
        raise ValueError(f"facts.blocks names cells that do not exist: {unknown}")


def _validate_selected_version(facts: dict) -> None:
    """A selection is a record whose digests recompute from vendored artifacts, not a label.

    Reviewer gate (2026-09-09 consult): `SELECTED` used to require only a truthy version and no blocks, so
    `selected_version: "x"` validated. Now the record must name the content, the vendored script, expected
    results and canonical manifest must hash to the recorded digests, the manifest must re-derive from the
    script with the recorded row counts, and the record must name what the retained chain used. Whether the
    live rows match is a separate field that stays UNVERIFIED until something reads them.
    """
    version = facts["selected_version"]
    if not isinstance(version, dict):
        raise ValueError("facts.selected_version must be a record, not a bare label: a string identifies nothing recomputable")
    missing = [k for k in SELECTED_VERSION_REQUIRED if k not in version]
    if missing:
        raise ValueError(f"facts.selected_version is missing {missing}")
    if version["synthetic"] is not True:
        raise ValueError("facts.selected_version.synthetic must be the boolean true: this record kind supports the synthetic "
                         "fixture digest only; a non-synthetic selection needs its own evidence and owner record, which no "
                         "schema defines yet")
    for key in ("fixture_sha256", "expected_results_sha256", "publication_manifest_sha256", "computation_sha256",
                "content_manifest_sha256"):
        if not _HEX64.match(str(version[key])):
            raise ValueError(f"facts.selected_version.{key} is not a full lowercase SHA-256")
    if not _HEX40.match(str(version["sdk_pin"])):
        raise ValueError("facts.selected_version.sdk_pin is not a full commit hash")
    _calendar_date("valid_for_runs_on_or_after", version["valid_for_runs_on_or_after"])
    if "selected_utc" in version:
        _calendar_date("selected_utc", version["selected_utc"])
    _validate_expiry(version["materialization_expires_utc"])
    tables = version["tables"]
    if not isinstance(tables, list) or not tables or tables != sorted(set(tables)):
        raise ValueError("facts.selected_version.tables must be a sorted list of distinct table names")
    counts = version["row_counts"]
    if not isinstance(counts, dict) or set(counts) != set(tables) or any(not isinstance(v, int) or v < 0 for v in counts.values()):
        raise ValueError("facts.selected_version.row_counts must give one non-negative count per selected table")
    if sum(counts.values()) != version["row_count_total"]:
        raise ValueError("facts.selected_version.row_count_total does not equal the sum of row_counts")
    # Promotions this record cannot carry. Nothing in this slice reads the live tables or re-derives the 2026-09-07
    # chain's rows, so VERIFIED / PROVEN would need a separately validated readback or evidence record with its own
    # schema. Until one exists the only supported states are the unverified ones; a bare word is not evidence.
    if not str(version["live_materialization"]).startswith("UNVERIFIED"):
        raise ValueError("facts.selected_version.live_materialization must start with UNVERIFIED: promoting it to VERIFIED "
                         "requires a full-schema, full-row readback record bound to the content digest, which no schema "
                         "defines yet")
    if not str(version["historical_chain_equivalence"]).startswith("UNPROVEN"):
        raise ValueError("facts.selected_version.historical_chain_equivalence must start with UNPROVEN: the retained chain "
                         "kept no row-level evidence, and a matching number is not byte-equivalence")
    customer = facts.get("customer_data")
    if not isinstance(customer, dict) or customer.get("state") != "NOT SELECTED":
        raise ValueError("a SELECTED synthetic fact version must carry facts.customer_data with state NOT SELECTED: a "
                         "customer selection is its own record with its own owner and acceptance, which no schema defines yet")
    observed = facts.get("observed_in_the_retained_chain")
    if observed:
        for key in ("dataset", "sdk_pin"):
            if version[key] != observed[key]:
                raise ValueError(f"facts.selected_version.{key} differs from what the retained chain used")
        if tables != sorted(observed["tables"]):
            raise ValueError("facts.selected_version.tables differ from what the retained chain used")
    _verify_selected_artifacts(version)


_YMD = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _calendar_date(key: str, value: Any) -> _dt.date:
    """A string of the form YYYY-MM-DD that is a real date; fromisoformat alone would also take 20260312."""
    try:
        if not isinstance(value, str) or not _YMD.match(value):
            raise ValueError(value)
        return _dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"facts.selected_version.{key} must be a real calendar date (YYYY-MM-DD), got {value!r}") from None


def _validate_expiry(value: Any) -> None:
    """The expiry is approximate by construction: a 30-day table expiration set at provisioning, never read back.

    Accepted: `about YYYY-MM-DD …` (a real date) or `unknown …`. Refused: null, non-strings, malformed dates, and a
    bare exact timestamp, because an exact expiry would need a readback of each table's expirationTime that this
    record does not carry.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("facts.selected_version.materialization_expires_utc must be a string: 'about YYYY-MM-DD …' or 'unknown …'")
    if value.startswith("unknown"):
        return
    match = _ABOUT_DATE.match(value)
    if not match:
        raise ValueError("facts.selected_version.materialization_expires_utc must read 'about YYYY-MM-DD …' or 'unknown …'; "
                         "an exact expiry needs a table expirationTime readback this record does not carry")
    _calendar_date("materialization_expires_utc", match.group(1))


#: Which vendored file each recorded digest must equal. The declaration and publication manifest are vendored too,
#: so `computation_sha256` and `publication_manifest_sha256` are bound to bytes, not accepted as syntax.
ARTIFACT_DIGESTS = (
    ("fixture.sql", "fixture_sha256"), ("expected.json", "expected_results_sha256"),
    ("publication.json", "publication_manifest_sha256"), ("gross-margin-period.md", "computation_sha256"),
    ("content.json", "content_manifest_sha256"),
)


def _verify_selected_artifacts(version: dict, facts_dir: Path = FACTS_DIR) -> None:
    """The vendored artifacts must hash to the record, agree with the provenance pin, and the manifest must re-derive."""
    source_path = facts_dir / "source.json"
    if not source_path.is_file():
        raise ValueError(f"{source_path.name} is not vendored under {facts_dir.name}/: the selection has no offline provenance pin")
    source = json.loads(source_path.read_text())
    if version["sdk_pin"] != source["sdk_pin"]:
        raise ValueError("facts.selected_version.sdk_pin differs from the vendored provenance pin (source.json)")
    for name, key in ARTIFACT_DIGESTS:
        path = facts_dir / name
        if not path.is_file():
            raise ValueError(f"facts.selected_version names {key} but {path.name} is not vendored under {facts_dir.name}/")
        digest = fact_content.sha256(path.read_bytes())
        if digest != version[key]:
            raise ValueError(f"vendored {path.name} hashes to {digest[:12]}…, not the recorded {key} {version[key][:12]}…")
        pinned = source["artifacts"].get(name, {})
        if pinned.get("sha256") != digest:
            raise ValueError(f"vendored {path.name} hashes to {digest[:12]}…, not what source.json pins for it")
    for key, name in (("fixture_path", "fixture.sql"), ("expected_results_path", "expected.json")):
        if key in version and version[key] != source["artifacts"][name]["path"]:
            raise ValueError(f"facts.selected_version.{key} {version[key]!r} is not the pinned SDK path source.json records")
    publication = json.loads((facts_dir / "publication.json").read_text())
    if version["dataset"] != f"{publication['project']}.{publication['dataset']}" or version["location"] != publication["location"]:
        raise ValueError("facts.selected_version.dataset/location differ from the vendored publication manifest")
    if version["tables"] != sorted(publication["table_map"].values()):
        raise ValueError("facts.selected_version.tables differ from the vendored publication manifest's table_map")
    if version["computation_sha256"] != publication["computation_sha256"]:
        raise ValueError("facts.selected_version.computation_sha256 differs from the vendored publication manifest")
    if publication.get("synthetic") is not True:
        raise ValueError("the vendored publication manifest does not declare the fixture synthetic")
    manifest = fact_content.extract((facts_dir / "fixture.sql").read_text())
    if fact_content.canonical_bytes(manifest) != (facts_dir / "content.json").read_bytes():
        raise ValueError("fixtures/facts/content.json is not the canonical manifest derived from fixtures/facts/fixture.sql")
    derived = fact_content.row_counts(manifest)
    if derived != version["row_counts"]:
        raise ValueError(f"facts.selected_version.row_counts {version['row_counts']} differ from the script's {derived}")
    if "expected_gross_margin_usd_2026_01" in version:
        expected = json.loads((facts_dir / "expected.json").read_text())
        if str(version["expected_gross_margin_usd_2026_01"]) != str(expected["approved_january"]["gross_margin_usd"]):
            raise ValueError("facts.selected_version.expected_gross_margin_usd_2026_01 differs from expected.json approved_january")


def _dig(doc: Any, at: list[str] | None) -> Any:
    for step in at or []:
        doc = doc[step]
    return doc


def prior_observations(root: Path | str = ROOT) -> list[dict]:
    """Recorded ordinary-SQL retrieval observations, read out of the retained evidence.

    The engine label is taken from the jobs themselves. `evidence/report.md` calls both forced
    observations "on-demand"; one of them carries an ENTERPRISE reservation on every job, so the
    edition is reported per observation from the record rather than from that prose.
    """
    root = Path(root)
    out = []
    for spec in PRIOR_SOURCES:
        path = root / spec["source"]
        if not path.exists():
            continue
        record = _dig(json.loads(path.read_text()), spec["at"])
        timing = record["timing"]
        jobs = timing.get("jobs") or []
        editions = sorted({j.get("edition") or "on-demand" for j in jobs})
        reservations = sorted({j["reservation_id"] for j in jobs if j.get("reservation_id")})
        out.append({
            "source": spec["source"] + ("#" + ".".join(spec["at"]) if spec["at"] else ""),
            "shape": spec["shape"],
            "query": spec["query"],
            "metric": "retrieval_ms",
            "n": 1,
            "concurrency": 1,
            "retrieval_ms": timing["total_ms"],
            "stages_ms": timing.get("stages_ms"),
            "jobs": len(jobs),
            "bytes_billed": sum(j.get("bytes_billed") or 0 for j in jobs),
            "edition": editions[0] if len(editions) == 1 else editions,
            "reservation": reservations or None,
            "status": record.get("status"),
            "fills_cell": False,
            "why_not_a_cell": WHY_NOT_A_CELL,
        })
    return out


def project_budget(plan: dict, priors: list[dict]) -> dict:
    """Project the declared samples against the declared ceilings, using observed bytes per request.

    A projection is not a bill. It exists so a cell is not started against a budget nobody checked.
    """
    budget = plan["budget"]
    per_shape: dict[str, list[int]] = {}
    for p in priors:
        if p["bytes_billed"]:
            per_shape.setdefault(p["shape"], []).append(p["bytes_billed"])
    shapes = {s: round(sum(v) / len(v)) for s, v in per_shape.items()}
    cells = []
    total_bytes = 0
    unknown = []
    for cell in plan["retrieval_cells"]:
        observed = shapes.get(cell["shape"])
        requests = cell["warmups"] + cell["measured"]
        if observed is None:
            unknown.append(cell["name"])
            cells.append({"cell": cell["name"], "requests": requests, "bytes_billed_projected": None,
                          "basis": "NO_OBSERVED_BYTES_FOR_SHAPE"})
            continue
        projected = observed * requests
        total_bytes += projected
        cells.append({"cell": cell["name"], "requests": requests, "bytes_per_request_observed": observed,
                      "bytes_billed_projected": projected,
                      "basis": f"mean bytes_billed over {len(per_shape[cell['shape']])} recorded {cell['shape']} observation(s)"})
    usd = total_bytes / TIB * budget["ondemand_usd_per_tib"]
    within = (total_bytes <= budget["max_bytes_billed_gib"] * GIB) and (usd <= budget["max_usd_ondemand_list"])
    return {
        "cells": cells,
        "consumer_cells_projected": False,
        "consumer_cells_note": "Not projected: the request-to-consumer runner does not exist, so its per-request bytes are unknown.",
        "bytes_billed_projected_total": total_bytes,
        "usd_ondemand_list_projected": round(usd, 4),
        "usd_note": "List rate on projected bytes. The 1 TiB/month on-demand free tier is not applied, so the invoiced line may be lower. Embeddings, storage and publication upkeep are NOT in this projection.",
        "ceiling_bytes_billed_gib": budget["max_bytes_billed_gib"],
        "ceiling_usd_ondemand_list": budget["max_usd_ondemand_list"],
        "within_budget": bool(within and not unknown),
        "shapes_without_observed_bytes": unknown,
    }


# --- retained campaign records (Pass 2) -------------------------------------------------------------------

def campaign_records(out_dir: Path | str = OUT_DIR) -> list[dict]:
    """Every retained `run_sqlbase-*.json`, oldest first by `started_utc`. Nothing is filtered: an aborted or
    preflight-stopped campaign is part of the history the card reports."""
    out_dir = Path(out_dir)
    records = []
    for path in sorted(out_dir.glob(RECORD_GLOB)):
        rec = json.loads(path.read_text())
        rec["_file"] = f"evidence/sql-baseline/{path.name}"
        records.append(rec)
    records.sort(key=lambda r: (r.get("started_utc") or "", r["_file"]))
    return records


def attempts_for(run_id: str, requests_path: Path | str = REQUESTS) -> list[dict]:
    """The retained per-attempt rows of one campaign (warmups included), read from `evidence/requests.jsonl`."""
    path = Path(requests_path)
    if not path.exists():
        return []
    out = []
    with path.open() as fh:
        for line in fh:
            if run_id in line:
                rec = json.loads(line)
                if rec.get("run_id") == run_id:
                    out.append(rec)
    return out


def _attempt_bytes(attempts: list[dict]) -> dict:
    """Bytes the retained attempts' jobs report, and how many jobs report none. Warmups count: they were billed too."""
    billed, jobs, unknown = 0, 0, 0
    for a in attempts:
        for j in (a.get("timing") or {}).get("jobs") or []:
            jobs += 1
            if j.get("bytes_billed") is None:
                unknown += 1
            else:
                billed += int(j["bytes_billed"])
    return {"jobs": jobs, "bytes_billed": billed, "jobs_without_billing": unknown}


def _one_line(text: str | None, limit: int = 300) -> str | None:
    return None if text is None else " ".join(str(text).split())[:limit]


def _first_error(attempts: list[dict]) -> str | None:
    for a in attempts:
        if a.get("error"):
            return _one_line(a["error"])
    return None


def summarize_campaign(record: dict, attempts: list[dict] | None = None) -> dict:
    """One row of the card's campaign history, read from the record and its retained attempts only."""
    attempts = attempts or []
    billing = record.get("billing") or {}
    routing = record.get("routing") or {}
    pre = record.get("preflight")
    by_cell = _attempt_bytes(attempts)
    return {
        "run_id": record["run_id"],
        "file": record["_file"],
        "started_utc": record.get("started_utc"),
        "wall_seconds": record.get("wall_seconds"),
        "state": record.get("state"),
        "error": record.get("error"),
        "sdk": record.get("sdk"),
        "preflight": ({"state": pre.get("state"), "reason": pre.get("reason"), "server_message": _one_line(pre.get("server_message"), 600),
                       "requires": pre.get("requires"), "remedy": pre.get("remedy")} if pre else None),
        "cells": [{"cell": c["cell"], "state": c["state"], "measured_n": c.get("measured_n", 0),
                   "stopped_reason": c.get("stopped_reason")} for c in record.get("cells", [])],
        "attempts_retained": len(attempts),
        "attempts_ok": sum(1 for a in attempts if a.get("ok")),
        "attempts_first_error": _first_error(attempts),
        "jobs_in_attempts": by_cell["jobs"],
        "bytes_billed_charged": billing.get("bytes_billed_charged"),
        "usd_list_charged": billing.get("usd_list_charged"),
        "unresolved_liability_bytes": billing.get("unresolved_liability_bytes"),
        "unresolved_jobs": len(billing.get("unresolved_jobs") or []),
        "billing_stop_reason": billing.get("stop_reason"),
        "jobs_observed": routing.get("jobs_observed"),
        "jobs_verified_on_demand": routing.get("jobs_verified_on_demand"),
        "verified_on_demand": routing.get("verified_on_demand"),
        "edition": record.get("edition"),
        "edition_note": record.get("edition_note"),
    }


def latest_cell_result(records: list[dict], name: str) -> tuple[dict, dict] | None:
    """The newest campaign with any measured attempt of this cell; failing that, the newest campaign that carried it
    (NOT_RUN for its reason). An ABORTED campaign carries no cells, so it never fills one. Every campaign, chosen or
    not, is listed in the card's campaign history."""
    carried = None
    for record in reversed(records):
        for c in record.get("cells", []):
            if c.get("cell") == name:
                if c.get("measured_n"):
                    return record, c
                carried = carried or (record, c)
    return carried


def blocker_from(records: list[dict]) -> dict | None:
    """What stops the next campaign, read from the newest record: a preflight that did not pass names the project
    option the driver cannot set. Older campaigns that failed before the preflight existed are history, not the
    current blocker."""
    if not records:
        return None
    pre = records[-1].get("preflight")
    if not pre or pre.get("state") == "OK":
        return None
    req = pre.get("requires") or {}
    return {
        "campaign": records[-1]["run_id"],
        "stage": "preflight (dry run, no job, nothing billed)",
        "reason": pre.get("reason"),
        "server_message": _one_line(pre.get("server_message"), 600),
        "requires": req,
        "remedy": pre.get("remedy"),
        "who": "whoever holds bigquery.config.update on the project (or its organization); not this driver, not an agent",
        "why_not_worked_around": ("running the cells under the standing Enterprise assignment would be a different measurement "
                                  "(the plan's reservation line says so) and the routing guard would stop it as a violation; "
                                  "removing the assignment is out of scope for a baseline run"),
    }


def _filled_retrieval_cell(base: dict, record: dict, result: dict, attempts: list[dict]) -> dict:
    """Overlay one campaign's summary of this cell onto the predeclared cell. Only fields the record carries move."""
    mine = [a for a in attempts if a.get("cell") == base["cell"]]
    b = _attempt_bytes(mine)
    filled = dict(base)
    filled.update({
        "measured_n": result.get("measured_n", 0),
        "state": result["state"],
        "stopped_reason": result.get("stopped_reason"),
        "p50_ms": result.get("p50_ms_all"), "p95_ms": result.get("p95_ms_all"), "max_ms": result.get("max_ms_all"),
        "p50_ms_ok": result.get("p50_ms_ok"), "p95_ms_ok": result.get("p95_ms_ok"),
        "success_rate": result.get("success_rate"),
        "errors": result.get("errors"), "timeouts": result.get("timeouts"),
        "warmups_done": result.get("warmups_done", 0),
        "attempts_retained": len(mine),
        "jobs_in_attempts": b["jobs"],
        "bytes_billed": b["bytes_billed"] if b["jobs"] else None,
        "jobs_without_billing": b["jobs_without_billing"],
        "usd_ondemand_list": (round(b["bytes_billed"] / TIB * base["_usd_per_tib"], 4) if b["jobs"] else None),
        "edition": record.get("edition"),
        "campaign": record["run_id"],
        "campaign_state": record.get("state"),
        "campaign_file": record["_file"],
        "first_error": _first_error(mine),
        "filled_from": ("newest retained campaign with a measured attempt of this cell, else the newest that carried it; "
                        "percentiles are nearest-rank over all measured attempts, failures included"),
    })
    del filled["_usd_per_tib"]
    return filled


def _retrieval_cell(cell: dict, plan: dict, priors: list[dict]) -> dict:
    return {
        "cell": cell["name"],
        "metric": "retrieval_ms",
        "engine": plan["engine"],
        "shape": cell["shape"],
        "concurrency": cell["concurrency"],
        "measured_n": 0,
        "measured_target": cell["measured"],
        "warmups_target": cell["warmups"],
        "state": "INCOMPLETE",
        "stopped_reason": "NOT_RUN",
        "p50_ms": None, "p95_ms": None, "max_ms": None,
        "success_rate": None, "errors": None, "timeouts": None,
        "bytes_billed": None, "usd_ondemand_list": None,
        "edition": None, "campaign": None,
        "_usd_per_tib": plan["budget"]["ondemand_usd_per_tib"],
        "prior_observations": [p for p in priors if p["shape"] == cell["shape"] and p["concurrency"] == cell["concurrency"]],
        "fact_version_blocked": False,
        "blocked_by": None,
        "how_to_fill": (
            f"Predeclared: {cell['warmups']} warmups + {cell['measured']} measured at C={cell['concurrency']}, "
            f"timeout {cell['timeout_s']}s, result cache off, engine `fallback`. `okf_bq_graph.benchmark.measure` "
            "does the sampling, retains every attempt in evidence/requests.jsonl before aggregating, and keeps a "
            "stopped cell INCOMPLETE. The driver that reaches it is `okf_bq_graph.sql_baseline_run` (Slice B, Pass 1): "
            "it reads this plan rather than fixtures/scale.json, passes only this cell's shape as the query list, runs "
            "on-demand by job-level override (`reservation = none`, verified from every job's statistics; a reservation "
            "or edition on any job stops the campaign unlabelled), with a submission gate per cell so the cell/total "
            "deadline stops in-flight jobs, a running billed-byte / USD ledger with per-job `maximum_bytes_billed`, and "
            "a fresh `sqlbase-*` run_id that is checked against the retained GQL summary before any client exists. "
            f"`python3 -m okf_bq_graph.sql_baseline_run --dry-run --cells {cell['name']}`; "
            f"fill: `python3 -m okf_bq_graph.sql_baseline_run --live --cells {cell['name']}` (Pass 2, foreground, "
            "Haiyuan's paid authorization)."
        ),
    }


def _consumer_cell(cell: dict, plan: dict) -> dict:
    facts = plan["facts"]
    blocked = facts["state"] == "UNSELECTED" and cell["name"] in facts["blocks"]
    return {
        "cell": cell["name"],
        "metric": "request_to_consumer_ms",
        "engine": plan["engine"],
        "shape": cell["shape"],
        "concurrency": cell["concurrency"],
        "measured_n": 0,
        "measured_target": cell["measured"],
        "warmups_target": cell["warmups"],
        "state": "INCOMPLETE",
        "stopped_reason": "NOT_IMPLEMENTED",
        "p50_ms": None, "p95_ms": None, "max_ms": None,
        "success_rate": None, "errors": None, "timeouts": None,
        "bytes_billed": None, "usd_ondemand_list": None,
        "prior_observations": [],
        "fact_version_blocked": blocked,
        "blocked_by": ("facts.state = UNSELECTED: no fact-data version is chosen, so two runs of this cell are not "
                       "comparable to each other and neither is comparable to an ordinary-SQL alternative") if blocked else None,
        "how_to_fill": (
            ("Select a fact-data version first (see `facts` above); until then this cell cannot be compared to "
             "anything. ") if blocked else
            (f"Fact version: SELECTED, {facts['selected_version']['kind']} (see `facts` above): synthetic fixture-scale "
             "rows, live materialization unverified against the digest. Before it samples, the runner must read the live "
             "tables back in full and match them to the content digest, then bind that verified set to every attempt; row "
             "counts and the January result are smoke checks, not identity. None of that exists yet, and its numbers must be "
             "labelled fixture-scale. ") if facts["state"] == "SELECTED" else ""
        ) + (
            "No runner exists. okf_bq_graph.chain runs the whole chain once per case and reports one "
            "wall time for the pass; okf_bq_graph.benchmark stops at retrieval. Filling this cell needs a "
            "sampled driver that repeats one requester question through bind, the caller-delegated job, "
            "independent verification and the consumer decision, retaining every attempt including refusals. "
            "Sizing it against a real SDK subprocess per request is part of that work, not an afterthought."
        ),
    }


def _cost_cell(cell: dict) -> dict:
    return {
        "cell": cell["name"],
        "metric": cell["name"],
        "question": cell["question"],
        "unit": cell["unit"],
        "formula": cell.get("formula"),
        "value": None,
        "state": "UNMEASURED",
        "how_to_fill": {
            "publication_visibility": (
                "Publish repeatedly and time first visibility to a new request. One observation exists "
                "(21.3 s for the single Acme publish, n=1, evidence/publish_log.jsonl) and it is not a distribution."
            ),
            "publication_upkeep": "Not modelled. Needs a republish cadence nobody has agreed yet.",
            "embedding_cost": (
                "Not quantified. The corpus embedded 22 + 6 + 2x7 sections once; natural-question cells add one "
                "query embedding per request. Both need the model's own price, which this spike never recorded."
            ),
            "storage_cost": "Not quantified: projection, section vectors and retained evidence, at the dataset's storage rate.",
            "cost_per_success": (
                "Not computable until the cells above have a numerator. Total cost of all attempts divided by released, "
                "receipt-verified answers: a failed or refused attempt costs money, so it belongs in the numerator, and "
                "it answered nothing, so it must not appear in the denominator."
            ),
        }[cell["name"]],
    }


def card_state(retrieval_cells: list[dict], records: list[dict]) -> tuple[str, str]:
    if not records:
        return "SCAFFOLD_ONLY", "No baseline cell has been run. Every cell below is INCOMPLETE or UNMEASURED by construction."
    complete = [c["cell"] for c in retrieval_cells if c["state"] == "COMPLETE"]
    measured = [c["cell"] for c in retrieval_cells if c["measured_n"]]
    n = len(records)
    if len(complete) == len(retrieval_cells):
        filling = sorted({c["campaign"] for c in retrieval_cells})
        return "RETRIEVAL_MEASURED", (f"Every retrieval cell is COMPLETE, filled from campaign(s) {', '.join('`' + f + '`' for f in filling)}; "
                                      f"{n} campaign(s) are retained and listed below, earlier ones included. The consumer cells and "
                                      "the cost cells are not measured; the table says why.")
    return "INCOMPLETE", (f"{n} campaign(s) retained; {len(complete)} of {len(retrieval_cells)} retrieval cells COMPLETE, "
                          f"{len(measured)} with any measured attempt. Every other cell is INCOMPLETE or UNMEASURED with its reason. "
                          "No number below is invented: a cell shows only what its latest campaign's summary carries.")


def build_card(plan: dict, priors: list[dict] | None = None, root: Path | str = ROOT, records: list[dict] | None = None,
               requests_path: Path | str | None = None) -> dict:
    validate_plan(plan)
    priors = prior_observations(root) if priors is None else priors
    root = Path(root)
    records = campaign_records(root / "evidence" / "sql-baseline") if records is None else records
    records = sorted(records, key=lambda r: (r.get("started_utc") or "", r["run_id"]))   # oldest first, whatever order arrived
    requests_path = (root / "evidence" / "requests.jsonl") if requests_path is None else Path(requests_path)
    attempts = {r["run_id"]: attempts_for(r["run_id"], requests_path) for r in records}
    retrieval = []
    for c in plan["retrieval_cells"]:
        base = _retrieval_cell(c, plan, priors)
        hit = latest_cell_result(records, c["name"])
        if hit is None:
            del base["_usd_per_tib"]
            retrieval.append(base)
        else:
            record, result = hit
            retrieval.append(_filled_retrieval_cell(base, record, result, attempts[record["run_id"]]))
    state, state_note = card_state(retrieval, records)
    card = {
        "version": plan["version"],
        "declared_utc": plan["declared_utc"],
        "state": state,
        "state_note": state_note,
        "engine": plan["engine"],
        "engine_note": plan["engine_note"],
        "corpus": plan["corpus"],
        "questions": plan["questions"],
        "facts": plan["facts"],
        "warmup_and_cache": plan["warmup_and_cache"],
        "metrics": plan["metrics"],
        "budget": plan["budget"],
        "budget_projection": project_budget(plan, priors),
        "concurrency_note": plan["concurrency_note"],
        "cells": retrieval + [_consumer_cell(c, plan) for c in plan["consumer_cells"]],
        "cost_cells": [_cost_cell(c) for c in plan["cost_cells"]],
        "campaigns": [summarize_campaign(r, attempts[r["run_id"]]) for r in records],
        "campaigns_note": ("Every retained campaign, oldest first, read from evidence/sql-baseline/run_<run_id>.json and its attempts "
                           "in evidence/requests.jsonl. Bytes and USD are what the campaign's ledger charged from terminal job "
                           "statistics; liability is room held for jobs whose billing was never established (Astra PR55 RR)."),
        "blocker": blocker_from(records),
        "prior_observations": priors,
        "prior_observations_note": (
            "Recorded before this plan existed, on the same corpus and engine. They are retained here so the "
            "cells start from evidence rather than from nothing. None of them fills a cell."
        ),
        "gql_comparison": {
            "state": "OPTIONAL_LATER",
            "rule": (
                "Any GQL comparison must match this seed shape, corpus, authorization and workload, and account for "
                "its Enterprise reservation cost separately. The recorded GQL C=1 cell is 28 of 100 attempts and is "
                "not a completed cell; it is not a comparator."
            ),
        },
    }
    assert_no_cell_is_filled(card)
    assert_filled_cells_trace_to_records(card, records)
    return card


def assert_filled_cells_trace_to_records(card: dict, records: list[dict]) -> None:
    """A number on the card must be a number some retained campaign carries for that cell. Consumer and cost cells
    are never filled from records, whatever the records say."""
    by_run = {r["run_id"]: r for r in records}
    for cell in card["cells"]:
        if cell["metric"] != "retrieval_ms":
            if cell["measured_n"] or cell["p50_ms"] is not None or cell["state"] != "INCOMPLETE":
                raise ValueError(f"{cell['cell']}: a {cell['metric']} cell cannot be filled by a retrieval campaign")
            continue
        if cell.get("campaign") is None:
            if cell["measured_n"] or cell["p50_ms"] is not None or cell["state"] != "INCOMPLETE":
                raise ValueError(f"{cell['cell']}: carries a measurement but names no campaign")
            continue
        record = by_run.get(cell["campaign"])
        if record is None:
            raise ValueError(f"{cell['cell']}: names campaign {cell['campaign']} which is not retained")
        result = next((c for c in record.get("cells", []) if c.get("cell") == cell["cell"]), None)
        if result is None:
            raise ValueError(f"{cell['cell']}: campaign {cell['campaign']} carries no summary of it")
        for mine, theirs in (("measured_n", "measured_n"), ("state", "state"), ("stopped_reason", "stopped_reason"),
                             ("p50_ms", "p50_ms_all"), ("p95_ms", "p95_ms_all"), ("success_rate", "success_rate")):
            if cell[mine] != result.get(theirs):
                raise ValueError(f"{cell['cell']}.{mine} = {cell[mine]!r} but campaign {cell['campaign']} says {result.get(theirs)!r}")
        if cell["state"] == "COMPLETE" and (cell["measured_n"] < cell["measured_target"] or cell["stopped_reason"] is not None):
            raise ValueError(f"{cell['cell']}: COMPLETE with n={cell['measured_n']}/{cell['measured_target']} or a stop reason")
    for cell in card["cost_cells"]:
        if cell["value"] is not None or cell["state"] != "UNMEASURED":
            raise ValueError(f"{cell['cell']}: a cost cell is not filled by a retrieval campaign")


def assert_no_cell_is_filled(card: dict) -> None:
    """A scaffold that quietly acquires numbers stops being a scaffold."""
    if card["state"] != "SCAFFOLD_ONLY":
        return
    for cell in card["cells"]:
        if cell["measured_n"] or cell["state"] not in ("INCOMPLETE",):
            raise ValueError(f"{cell['cell']}: a scaffold cell may not carry measurements")
        for field in ("p50_ms", "p95_ms", "max_ms", "success_rate", "bytes_billed", "usd_ondemand_list"):
            if cell[field] is not None:
                raise ValueError(f"{cell['cell']}: {field} is set in a scaffold-only card")
        for prior in cell["prior_observations"]:
            if prior.get("fills_cell"):
                raise ValueError(f"{cell['cell']}: a prior observation claims to fill the cell")
    for cell in card["cost_cells"]:
        if cell["value"] is not None or cell["state"] != "UNMEASURED":
            raise ValueError(f"{cell['cell']}: a scaffold cost cell may not carry a value")
    facts = card["facts"]
    if facts["state"] == "UNSELECTED":
        blocked = {c["cell"] for c in card["cells"] if c["fact_version_blocked"]}
        if blocked != set(facts["blocks"]):
            raise ValueError(f"facts.blocks says {sorted(facts['blocks'])} but the card blocks {sorted(blocked)}")
        for cell in card["cells"]:
            if cell["fact_version_blocked"] and not cell["blocked_by"]:
                raise ValueError(f"{cell['cell']}: blocked by an unselected fact version but gives no reason")


def _ms(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f}"


def _render_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        return ", ".join(f"`{v}`" for v in value)
    if isinstance(value, dict):
        return ", ".join(f"{k}={v}" for k, v in value.items())
    return str(value)


def _render_selected_version(version: Any) -> list[str]:
    if isinstance(version, dict):
        return [f"* **{key}:** {_render_value(value)}" for key, value in version.items()]
    return [f"`{version}`"]


def _render_facts(card: dict) -> list[str]:
    """Render whichever fact state the plan is actually in.

    This used to hardcode UNSELECTED, so a plan that selected a version produced a card whose JSON
    said SELECTED with the cells unblocked while its Markdown still said UNSELECTED and never
    printed the version. Everything below is read from `facts`; optional sections appear only when
    the plan carries them.
    """
    facts = card["facts"]
    selected = facts["state"] == "SELECTED"
    lines = [f"## Fact data — **{facts['state']}**", ""]
    if selected:
        lines += ["**Selected version.**"] + _render_selected_version(facts["selected_version"]) + [""]
    for key, label in (("why_it_matters", None), ("what_is_missing", "**What is missing.** ")):
        if facts.get(key):
            lines += [f"{label or ''}{facts[key]}", ""]
    obs = facts.get("observed_in_the_retained_chain")
    if obs:
        lines += [
            "**What the retained chain identifies**"
            + ("" if selected else ", so the gap is a choice nobody has made rather than an unknown") + ":",
            "",
            f"* Publication `{obs['publication_id']}` — {obs['publication_note']}."
            f" Synthetic fixture: {str(obs['synthetic_fixture']).lower()}.",
            f"* SDK pin `{obs['sdk_pin']}`, dataset `{obs['dataset']}`, "
            f"{len(obs['tables'])} fact tables: {', '.join('`' + t + '`' for t in obs['tables'])}.",
            f"* Derived from {obs['derived_from']}.",
            f"* Read from `{obs['source']}`.",
            "",
        ]
    customer = facts.get("customer_data")
    if customer:
        lines += [f"**Customer fact data ({customer.get('cohort', 'customer cohort')}) — {customer['state']}.** "
                  f"{customer.get('note', '')}".rstrip(), ""]
    if selected:
        lines += ["**Cells this blocks.** None. Selecting a version clears `FACTS_UNSELECTED` only; the request-to-consumer "
                  "cells stay INCOMPLETE because no sampled runner exists (NOT_IMPLEMENTED, which the cell table gives), and "
                  "the live rows have not been verified against the selected digest (a full readback, not a count check, "
                  "which no runner does yet).", ""]
    else:
        lines += [f"**Cells this blocks.** {', '.join('`' + b + '`' for b in facts['blocks'])} — the full "
                  "request-to-consumer comparison. The retrieval cells are unaffected: retrieval selects context, and "
                  "returns the sanctioned SQL without executing it.", ""]
    if facts.get("how_to_select"):
        lines += [f"**How {'it was selected' if selected else 'to select one'}.** {facts['how_to_select']}", ""]
    return lines


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def _mib(value: int | None) -> str:
    return "—" if value is None else f"{value / (1024 ** 2):,.0f} MiB"


def _render_blocker(card: dict) -> list[str]:
    b = card.get("blocker")
    if not b:
        return []
    req = b.get("requires") or {}
    return [
        "## Blocked — what the next campaign needs",
        "",
        f"Campaign `{b['campaign']}` stopped at the {b['stage']}: **{b['reason']}**.",
        "",
        f"* Server: `{b['server_message']}`",
        f"* Requires: `{req.get('option')} = {req.get('value')}` on the {req.get('scope')} ({req.get('docs')}).",
        f"* Remedy: {b['remedy']}",
        f"* Who: {b['who']}",
        f"* Why it was not worked around: {b['why_not_worked_around']}",
        "",
    ]


def _render_campaigns(card: dict) -> list[str]:
    if not card.get("campaigns"):
        return []
    lines = [
        "## Campaigns",
        "",
        card["campaigns_note"],
        "",
        "| Campaign | Started (UTC) | Wall s | State | Preflight | Cells (state / n / reason) | Attempts ok/retained | Jobs in attempts | Bytes charged | USD list | Liability | Routing verified | Edition |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in card["campaigns"]:
        pre = c["preflight"]
        pre_s = "—" if pre is None else (pre["state"] + (f" ({pre['reason']})" if pre.get("reason") else ""))
        cells = "; ".join(f"`{x['cell']}` {x['state']} n={x['measured_n']} {x['stopped_reason'] or ''}".rstrip() for x in c["cells"]) or "none (aborted)"
        liability = "—" if c["unresolved_liability_bytes"] is None else f"{c['unresolved_liability_bytes'] / GIB:.0f} GiB / {c['unresolved_jobs']} jobs"
        usd = "—" if c["usd_list_charged"] is None else f"${c['usd_list_charged']:.4f}"
        lines.append(
            f"| `{c['run_id']}` | {c['started_utc']} | {c['wall_seconds']} | **{c['state']}** | {pre_s} | {cells} | "
            f"{c['attempts_ok']}/{c['attempts_retained']} | {c['jobs_in_attempts']} | {_mib(c['bytes_billed_charged'])} | {usd} | {liability} | "
            f"{c['jobs_verified_on_demand']}/{c['jobs_observed']} | {c['edition'] or '—'} |"
        )
    lines.append("")
    for c in card["campaigns"]:
        if c["attempts_first_error"]:
            lines.append(f"* `{c['run_id']}` first retained error: `{c['attempts_first_error']}`")
        if c["preflight"] and c["preflight"].get("server_message"):
            lines.append(f"* `{c['run_id']}` preflight: `{c['preflight']['server_message']}`")
        if c["error"]:
            lines.append(f"* `{c['run_id']}` aborted: `{c['error']}`")
    lines.append("")
    return lines


def render_markdown(card: dict) -> str:
    p = card["budget_projection"]
    title = {"SCAFFOLD_ONLY": "predeclared, not measured",
             "RETRIEVAL_MEASURED": "retrieval cells measured"}.get(card["state"], "predeclared, campaigns retained, not measured")
    lines = [
        f"# Ordinary-SQL baseline — {title}",
        "",
        f"`{card['version']}` · declared {card['declared_utc']} · **{card['state']}**",
        "",
        card["state_note"],
        "",
        "Generated by `python3 -m okf_bq_graph.sql_baseline` from `fixtures/sql_baseline.json` and the retained campaign",
        "records under `evidence/sql-baseline/`. It opens no client and spends nothing. Regenerate it rather than editing it.",
        "",
    ] + _render_blocker(card) + [
        "## What is being measured, and against what",
        "",
        f"* **Engine.** `{card['engine']}` — {card['engine_note']}",
        f"* **Corpus.** `{card['corpus']['bundle_id']}` at publication `{card['corpus']['publication_id']}`, "
        f"compiled from source pin `{card['corpus']['source_pin']}`. {card['corpus']['note']}",
        f"* **Questions.** `{card['questions']['source']}` at `as_of` {card['questions']['as_of']}: "
        f"{len(card['questions']['forced_seed_ids'])} forced seeds, {len(card['questions']['natural_query_ids'])} natural questions. "
        f"{card['questions']['note']}",
        f"* **Concurrency.** {card['concurrency_note']}",
        "",
    ] + _render_facts(card) + [
        "## Two latencies, never substituted",
        "",
        f"* **`retrieval_ms`** — {card['metrics']['retrieval_ms']}",
        f"* **`request_to_consumer_ms`** — {card['metrics']['request_to_consumer_ms']}",
        f"* {card['metrics']['separation_rule']}",
        "",
        "## Cells",
        "",
        "p50 / p95 are nearest-rank over all measured attempts, failures and timeouts included; `ok` is the success rate",
        "over the same attempts. A cell shows the latest campaign that carried it and nothing older.",
        "",
        "| Cell | Metric | Shape | C | Measured | State | p50 ms | p95 ms | ok | Bytes | Edition | Campaign | Reason |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for cell in card["cells"]:
        lines.append(
            f"| `{cell['cell']}` | {cell['metric']} | {cell['shape']} | {cell['concurrency']} | "
            f"{cell['measured_n']} / {cell['measured_target']} | **{cell['state']}** | {_ms(cell['p50_ms'])} | "
            f"{_ms(cell['p95_ms'])} | {_pct(cell['success_rate'])} | {_mib(cell['bytes_billed'])} | {cell.get('edition') or '—'} | "
            f"{('`' + cell['campaign'] + '`') if cell.get('campaign') else '—'} | {cell['stopped_reason'] or '—'}"
            f"{' + FACTS_UNSELECTED' if cell['fact_version_blocked'] else ''} |"
        )
    lines += ["", "How each cell is filled, and what its latest campaign did:", ""]
    for cell in card["cells"]:
        blocked = f" *(blocked: {cell['blocked_by']})*" if cell["blocked_by"] else ""
        latest = ""
        if cell.get("campaign"):
            latest = (f" **Latest campaign `{cell['campaign']}` ({cell['campaign_state']}):** {cell['state']}, "
                      f"n={cell['measured_n']}/{cell['measured_target']}, {cell['attempts_retained']} attempts retained "
                      f"({cell['warmups_done']} warmups), {cell['errors']} errors, {cell['timeouts']} timeouts, "
                      f"{cell['jobs_in_attempts']} jobs, {_mib(cell['bytes_billed'])} billed, edition {cell.get('edition') or 'not established'}"
                      + (f"; stopped {cell['stopped_reason']}" if cell['stopped_reason'] else "")
                      + (f"; first error `{cell['first_error']}`" if cell.get("first_error") else "") + ".")
        lines.append(f"* **`{cell['cell']}`** — {cell['how_to_fill']}{blocked}{latest}")
    lines += [
        "",
        "## Cost cells",
        "",
        "Listed rather than omitted: an absent row reads as zero.",
        "",
        "| Cost | Unit | Formula | Value | State | How it would be filled |",
        "|---|---|---|---|---|---|",
    ]
    for cell in card["cost_cells"]:
        lines.append(f"| {cell['question']} | {cell['unit']} | {cell['formula'] or '—'} | — | "
                     f"**{cell['state']}** | {cell['how_to_fill']} |")
    lines += [
        "",
        "## Budget, and the projection against it",
        "",
        f"* Ceilings: {card['budget']['max_wall_seconds_per_cell']} s per cell, "
        f"{card['budget']['max_wall_seconds_total']} s total, {p['ceiling_bytes_billed_gib']} GiB billed, "
        f"${p['ceiling_usd_ondemand_list']:.2f} on-demand at list.",
        f"* Reservation: {card['budget']['reservation']}",
        f"* Stop rule: {card['budget']['stop_rule']}",
        f"* Projection for the four retrieval cells from observed bytes per request: "
        f"**{p['bytes_billed_projected_total'] / GIB:.1f} GiB → ${p['usd_ondemand_list_projected']:.2f}** at list — "
        f"{'within' if p['within_budget'] else 'NOT within'} the declared ceiling.",
        f"* {p['usd_note']}",
        f"* {p['consumer_cells_note']}",
        "",
    ] + _render_campaigns(card) + [
        "## Recorded prior observations",
        "",
        card["prior_observations_note"],
        "",
        "| Source | Shape | C | n | retrieval ms | Jobs | Bytes billed | Edition | Fills a cell? |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for prior in card["prior_observations"]:
        edition = prior["edition"] if isinstance(prior["edition"], str) else "/".join(prior["edition"])
        lines.append(
            f"| `{prior['source']}` | {prior['shape']} | {prior['concurrency']} | {prior['n']} | "
            f"{_ms(prior['retrieval_ms'])} | {prior['jobs']} | {prior['bytes_billed'] / (1024 ** 2):,.0f} MiB | "
            f"{edition} | **no** |"
        )
    lines += [
        "",
        f"Why none of them fills a cell: {WHY_NOT_A_CELL}",
        "",
        "One correction the card carries rather than repeats: `evidence/report.md` and `evidence/comparison.md` describe",
        "both forced observations as on-demand. Every job in `all_all-0017.json#fallback_forced` carries the spike's",
        "Enterprise reservation, so that observation ran on Enterprise capacity. The edition column above is read from",
        "the jobs in each record. The retained records are left as they are; this is the correction beside them.",
        "",
        "## Optional GQL comparison",
        "",
        f"**{card['gql_comparison']['state']}.** {card['gql_comparison']['rule']}",
        "",
    ]
    return "\n".join(lines)


def main(out_dir: Path | str = OUT_DIR) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    card = build_card(load_plan())
    (out_dir / "plan.json").write_text(json.dumps(card, indent=2) + "\n")
    (out_dir / "baseline.md").write_text(render_markdown(card))
    return card


if __name__ == "__main__":
    written = main()
    filled = [c["cell"] for c in written["cells"] if c.get("campaign")]
    print(f"{written['state']}: {len(written['cells'])} cells ({len(filled)} carrying a campaign result), "
          f"{len(written['cost_cells'])} cost cells, {len(written['prior_observations'])} prior observations (none filling a cell), "
          f"{len(written['campaigns'])} campaign records" + (f"; blocked: {written['blocker']['reason']}" if written.get("blocker") else ""))
