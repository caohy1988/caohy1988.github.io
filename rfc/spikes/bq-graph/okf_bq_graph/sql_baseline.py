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
  fact data, so the committed plan is `UNSELECTED` and the cells it blocks carry that reason rather than
  looking merely unrun. A later `SELECTED` plan prints its version and blocks nothing, in the JSON and in
  the Markdown alike — `_render_facts` branches on the state instead of assuming one.

Nothing here opens a BigQuery client or spends anything. `python3 -m okf_bq_graph.sql_baseline`
regenerates `evidence/sql-baseline/{plan.json,baseline.md}` offline.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "fixtures" / "sql_baseline.json"
OUT_DIR = ROOT / "evidence" / "sql-baseline"

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
        return
    for key in ("why_it_matters", "what_is_missing", "blocks", "how_to_select"):
        if not facts.get(key):
            raise ValueError(f"an UNSELECTED fact version must record {key!r}")
    names = {c["name"] for c in plan["retrieval_cells"] + plan["consumer_cells"]}
    unknown = [n for n in facts["blocks"] if n not in names]
    if unknown:
        raise ValueError(f"facts.blocks names cells that do not exist: {unknown}")


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
            "Haiyuan's paid authorization). It has not been run: this cell is NOT_RUN, not measured."
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
             "anything. ") if blocked else ""
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


def build_card(plan: dict, priors: list[dict] | None = None, root: Path | str = ROOT) -> dict:
    validate_plan(plan)
    priors = prior_observations(root) if priors is None else priors
    card = {
        "version": plan["version"],
        "declared_utc": plan["declared_utc"],
        "state": "SCAFFOLD_ONLY",
        "state_note": "No baseline cell has been run. Every cell below is INCOMPLETE or UNMEASURED by construction.",
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
        "cells": ([_retrieval_cell(c, plan, priors) for c in plan["retrieval_cells"]]
                  + [_consumer_cell(c, plan) for c in plan["consumer_cells"]]),
        "cost_cells": [_cost_cell(c) for c in plan["cost_cells"]],
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
    return card


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


def _render_selected_version(version: Any) -> list[str]:
    if isinstance(version, dict):
        return [f"* **{key}:** {value}" for key, value in version.items()]
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
    if selected:
        lines += ["**Cells this blocks.** None: a selected fact version blocks nothing. The request-to-consumer cells "
                  "stay INCOMPLETE for their own reason, which the cell table gives.", ""]
    else:
        lines += [f"**Cells this blocks.** {', '.join('`' + b + '`' for b in facts['blocks'])} — the full "
                  "request-to-consumer comparison. The retrieval cells are unaffected: retrieval selects context, and "
                  "returns the sanctioned SQL without executing it.", ""]
    if facts.get("how_to_select"):
        lines += [f"**How {'it was selected' if selected else 'to select one'}.** {facts['how_to_select']}", ""]
    return lines


def render_markdown(card: dict) -> str:
    p = card["budget_projection"]
    lines = [
        "# Ordinary-SQL baseline — predeclared, not measured",
        "",
        f"`{card['version']}` · declared {card['declared_utc']} · **{card['state']}**",
        "",
        card["state_note"],
        "",
        "Generated by `python3 -m okf_bq_graph.sql_baseline` from `fixtures/sql_baseline.json`. It opens no client and",
        "spends nothing. Regenerate it rather than editing it.",
        "",
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
        "| Cell | Metric | Shape | C | Measured | State | p50 ms | p95 ms | Why it is empty |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for cell in card["cells"]:
        lines.append(
            f"| `{cell['cell']}` | {cell['metric']} | {cell['shape']} | {cell['concurrency']} | "
            f"{cell['measured_n']} / {cell['measured_target']} | **{cell['state']}** | {_ms(cell['p50_ms'])} | "
            f"{_ms(cell['p95_ms'])} | {cell['stopped_reason']}"
            f"{' + FACTS_UNSELECTED' if cell['fact_version_blocked'] else ''} |"
        )
    lines += ["", "How each cell would be filled:", ""]
    for cell in card["cells"]:
        blocked = f" *(blocked: {cell['blocked_by']})*" if cell["blocked_by"] else ""
        lines.append(f"* **`{cell['cell']}`** — {cell['how_to_fill']}{blocked}")
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
    print(f"{written['state']}: {len(written['cells'])} cells, {len(written['cost_cells'])} cost cells, "
          f"{len(written['prior_observations'])} prior observations, none filling a cell")
