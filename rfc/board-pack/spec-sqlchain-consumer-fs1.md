# Spec — `okf_bq_graph.consumer_run`, the hermetic sampled request-to-consumer runner (FS-1)

Files: `rfc/spikes/bq-graph/okf_bq_graph/consumer_run.py` (new), `okf_bq_graph/{sql_baseline.py,sql_baseline_run.py}`
(consumer-cell honesty, budget block), `fixtures/sql_baseline.json` (budget block, `live_precheck` wording),
`evidence/sql-baseline/{plan.json,baseline.md}` (regenerated), `evidence/consumer/` (retained hermetic runs, new),
tests, and the wording on `rfc/board-pack/{STORY.md,spec-sep19-pack.md,plan-knowledge-publications.md}`,
`rfc/index.html`, `rfc/detailed-rfc/index.html`, `rfc/spikes/bq-graph/README.md`. Intent in
`intent-sqlchain-consumer-fs1.md`; what comes next in `plan-sqlchain-consumer-fs1.md`.

## 1. Modes and the command line

`python3 -m okf_bq_graph.consumer_run (--dry-run | --hermetic) [--cells CELL ...] [--plan] [--cases] [--out-dir]
[--run-id] [--sdk-root] [--acme-root] [--as-of]`. Exactly one mode is required. **There is no `--live` flag**: the
parser rejects it as an unknown argument, and no code path in the module constructs a BigQuery client, opens a
reservation, or passes `--live` to the SDK example. Default cells: the plan's two consumer cells. A retrieval cell
name is refused (`NOT_A_CONSUMER_CELL`), never silently measured as something else.

- `--dry-run` loads and validates the plan, runs every gate in §3 that needs no subprocess (plan, state, cells,
  run id, validity window, vendored precheck, row oracle), prints the campaign — cells, the predeclared question and
  the refusal probe, the gates and their outcomes, the declared-but-unspent budget — and exits 0 without launching the
  SDK. A gate refusal prints `REFUSED: <code>` and exits 2.
- `--hermetic` runs the gates, then the campaign: the oracle engine on the graph leg (`engine: oracle`, the
  compiled projection of the pinned Acme bundle, no cache key in the clients so the disclosure cache is off) and the
  SDK example's hermetic runner on the receipt leg (`run.py --case approved --evidence-dir <private dir>`, no
  `--live`). Exit 0 on `RUNNER_HERMETIC_OK`, 1 otherwise, 2 on a gate refusal. Every outcome is retained.

Run ids are `consumer-hermetic-<utc>-<hex8>`; a supplied id must carry that label and must not name a retained
record (`RUN_ID_REUSED`). The id never begins with `live_`.

## 2. The predeclared question and the refusal probe

One requester question per cell, read from the plan's `questions.forced_seed_ids` and `fixtures/cases.json`:
`f_current` = `forced:metrics/gross-margin.md`, one hop to `computations/gross-margin-period.md`, with the receipt
example's fixed January parameters (`2026-01-01` to `2026-01-31`). Expected decision: `RELEASED`, declared in the
record before any attempt runs.

One refusal probe per cell, run once after the sampled attempts: `f_revenue` = `forced:metrics/revenue.md`, one hop to
`computations/revenue-ytd.md`, a computation the receipt publication does not carry. Expected decision: `REFUSED`,
declared in advance, at the **bind** stage with the `file_sha256` and `sql_text` checks failing and the SDK never
invoked. A probe that reached bind and released is `WRONG`; a probe that never reached retrieval is `NOT_REACHED`; a
probe that refused for any other reason (the CLI invoked, a different failed check) is `WRONG`. No substituted margin
answer, no "closest computation", nothing executed.

The probe is retained beside the attempts, flagged `kind: probe`, counted in `attempts_total` and in the cost-per-
success numerator, and excluded from the orchestration-time percentiles, which describe the question's path.

## 3. Gates, in order, each a typed refusal retained in the run record

| # | Code | Condition | Mode |
| --- | --- | --- | --- |
| 1 | `PLAN_INVALID` | `validate_plan` raises (which already re-hashes the vendored artifacts and re-derives the manifest) | both |
| 2 | `FACTS_UNSELECTED` | `facts.state != "SELECTED"` | both |
| 3 | `NOT_A_CONSUMER_CELL` / `UNKNOWN_CELL` | a requested name is a retrieval cell or not a cell | both |
| 4 | `RUN_ID_UNLABELLED` / `RUN_ID_REUSED` | id lacks the `consumer-hermetic-` label, or a record with that id is retained | both |
| 5 | `VALIDITY_WINDOW` | the evaluation date (the date of `--as-of`, default now UTC) is before `valid_for_runs_on_or_after` — the sanctioned SQL's 30-day recognition clause would not recognise the February order, so the expected results do not hold | both |
| 6 | `VENDORED_FACTS_DRIFTED` | the hermetic stand-in for the precheck: `fact_content.extract(fixtures/facts/fixture.sql)` canonicalised does not hash to `content_manifest_sha256`, or the vendored `content.json` bytes do not | both |
| 7 | `ORACLE_DISAGREES` | the row-based oracle (§4) over the vendored manifest at the evaluation date does not return `expected_gross_margin_usd_2026_01` for January, or `expected.json`'s `approved_january_february` value for January–February | both |
| 8 | `SDK_UNAVAILABLE` / `SDK_PROVENANCE` | no `run.py` at `<sdk-root>/examples/okf_attested_computation`; or the checkout's HEAD is not `sdk_pin`, or the repository is dirty or its Git state unknown (the chain's rule) | hermetic |
| 9 | `PUBLICATION_PIN` | the compiled projection's publication id is not `pub_190192147fd7fd78` | hermetic |

**Live admission** (`admit_live(selected_version, readback_manifest, today)`) exists as a pure function and is the
behaviour FS-2 must call before any attempt: `MATERIALIZATION_EXPIRED` when `today` is on or after the date in
`materialization_expires_utc` (`about YYYY-MM-DD …`), `FACTS_DRIFTED` when the readback manifest's canonical bytes
do not hash to `content_manifest_sha256` (per-table digests name which tables differ; row counts and the January
result are reported as smoke checks beside it and decide nothing), `OK` otherwise with the verified digest to bind
to every attempt. In this slice it is exercised only by tests against the vendored manifest, a mutated copy, a
manifest with a table removed, and dates on either side of the expiry. The hermetic run record carries
`live_admission: {status: NOT_RUN, reason: hermetic mode reads no live table}` and an `expiry` block (the recorded
date, the evaluation date, whether a live admission today would refuse). Hermetic mode does not refuse on expiry,
because it touches no materialization; it says so.

## 4. The row-based oracle check

`gross_margin_from_manifest(manifest, period_start, period_end, evaluation_date) -> Decimal | None`, a bounded
re-implementation of the sanctioned SQL's semantics over `okf-fact-content/1` rows: recognised orders are
`order_status = 'delivered'`, `DATE(order_ts)` at least 30 days before the evaluation date and inside the period;
revenue is `net_amount` for USD and `net_amount × rate_to_usd` from `fx_daily_rates` on (currency, `DATE(order_ts)`)
otherwise (no rate → NULL, dropped by SUM); COGS per order is the SQL's join graph reproduced row for row
(`order_lines` inner-join `products`, left-join `fulfillment_cost`, `shipment_cost`, `payment_fees`, summed per
order, so a duplicated join row duplicates its cost exactly as the SQL would); the result is
`SUM(revenue) − SUM(COALESCE(each COGS component, 0))` over recognised orders left-joined to COGS, `None` when no
order is recognised. NUMERIC arithmetic is `decimal.Decimal`.

What it establishes: that the vendored rows are consistent with `expected.json` under the sanctioned SQL's semantics as
re-implemented here, and that the runner reads rows (a test mutates one February amount: January stays `400`,
January–February leaves `515`, and the oracle reports it). What it does not establish: GoogleSQL execution, BigQuery's
NUMERIC or join behaviour, or that the live tables hold these rows. The record labels it
`row_oracle: {engine: python-decimal, not: googlesql}`.

## 5. The attempt record

One line per attempt in `evidence/consumer/<run_id>/attempts.jsonl`, appended as each attempt finishes (a crash
retains everything before it), and the same list inside the run record. Fields:

`cell`, `index`, `kind` (`warmup` | `measured` | `probe`), `question_id`, `seed`, `expected_decision`,
`started_utc`, `finished_utc`, `request_to_consumer_ms` (whole attempt wall time, labelled
`hermetic_orchestration_ms` in every summary), `retrieval` (`status`, `reached`, `cache`, `elapsed_ms`, the
engine's stage times), `computation` (`path`, `concept_hops`), `declaration` (`status`), `bind` (`status`,
`failed_checks`), `receipt` (`invoked`, `sdk_case`, `exit_code`, `elapsed_ms` — the SDK subprocess's own wall time,
`request_id`, `receipt_id`, `verdict`, `execution_match`, `job` = the emulation's `{job_id, project, location}`,
`job_times` = `{submitted_at: null, done_at: null, note}` because the hermetic emulation reports no timestamps and
submits no job, `issued_at`, `diag_path`, `diag_sha256`), `consume` (`decision`, `reasons`), `acceptance`
(`MET` | `WRONG` | `NOT_REACHED`, with the failed checks), `selected_content_digest` (= `content_manifest_sha256`),
`evaluation_date`, `error` (a stage exception, retained rather than raised).

Acceptance per attempt follows the chain's rule for `approved` (must reach retrieval, declaration, `BOUND`, an
invoked and completed child, exit 0, `RELEASED`; an unreached stage is `NOT_REACHED`, a reached stage that
contradicts is `WRONG`) and for `declaration-mismatch` (the probe, §2).

Concurrency: a cell at C=N runs its warmups and measured attempts through a pool of N workers in submission order
and records `concurrency_achieved` (the largest number in flight at once); the probe runs alone afterwards. Each
attempt gets its own SDK invocation directory; retained diagnostics are named `case_<cell>_<index>_hermetic.json`
under `evidence/consumer/<run_id>/receipt/`, so no two attempts share a path.

## 6. The run record and its verdict

`evidence/consumer/run_<run_id>.json` (redacted like the chain record): `runner` (`okf_bq_graph.consumer_run/0.1.0`),
`run_id`, `mode: hermetic`, `engine: oracle`, `as_of`, `evaluation_date`, `plan` (version, the selected version's
identity fields), `question`, `probe`, `gates` (every code from §3 with its outcome), `row_oracle`,
`live_admission`, `expiry`, `sdk` (root, head, pin, clean), `budget` (the declared consumer block, `spent: nothing`),
`cells` (per cell: `attempts_total`, `warmups`, `measured_n`, `released`, `refused`, `errors`, `acceptance` counts,
`concurrency`, `concurrency_achieved`, `hermetic_orchestration_ms` = nearest-rank p50/p95/max over measured attempts
with the sentence that it is not `request_to_consumer_ms`, `probe` outcome, `state` `HERMETIC_COMPLETE` |
`HERMETIC_INCOMPLETE`, `fills_cell: false`), `attempts`, `verdict`, `claims`.

Verdict: `RUNNER_HERMETIC_OK` when every gate passed, every attempt was retained, every measured attempt is `MET`
and the probe is `MET`; `RUNNER_HERMETIC_INCOMPLETE` when any attempt or probe is `NOT_REACHED` (a child that died,
a stage exception); `RUNNER_HERMETIC_BROKEN` when any is `WRONG` (a probe released, a measured attempt refused or
released without its bindings). `claims.establishes` = orchestration order, retention, predeclared refusal at the
declared stage, gate behaviour. `claims.does_not_establish` = data equivalence, GoogleSQL execution, a job identity,
a latency, a cost, a filled cell.

## 7. Plan, card and driver honesty

- `fixtures/sql_baseline.json`: `budget.consumer_sampling` is added — `state: DECLARED_NOT_SPENT`,
  `consumer_max_bytes_billed_gib: 8`, `consumer_max_usd: 0.05`, `consumer_max_wall_seconds_per_cell: 900`,
  `consumer_max_wall_seconds_total: 3600`, `ondemand_usd_per_tib` inherited, `basis` (the consult's ~5–6 GiB
  estimate for 2+20 at C=1 including the receipt leg's child jobs), and the sentence that it sits inside the
  existing 64 GiB / $0.50 ceilings and that hermetic mode spends none of it. `validate_plan` requires the block, its
  four ceilings, that each is at most the campaign ceiling, and that `state` is `DECLARED_NOT_SPENT` (a spent state
  would need a campaign record no schema defines yet). `facts.selected_version.live_precheck` now reads
  `IMPLEMENTED OFFLINE, NOT RUN LIVE: …` with the function named; the contract sentence is unchanged.
- `sql_baseline_run.refusal_reasons` returns `["RUNNER_HERMETIC_ONLY"]` (with `FACTS_UNSELECTED` first while it
  applies); `select_cells` still raises `RefusedCell`, naming `okf_bq_graph.consumer_run` as the driver and saying
  it has no live mode; the campaign summary reads `REFUSED (RUNNER_HERMETIC_ONLY)`; `--cells sqlchain_forced_c1`
  still exits `REFUSED:` without a client.
- `build_card`: consumer cells carry `stopped_reason: RUNNER_HERMETIC_ONLY`, `measured_n: 0`, null metrics,
  `fills_cell` absent (they are never filled), and a new `hermetic_runs` list read from
  `evidence/consumer/run_consumer-*.json`: per run `run_id`, `verdict`, `attempts_retained`, `released`, `refused`,
  `probe` decision, `file`. **No latency and no percentile from a hermetic run appears on the card**, in JSON or
  Markdown; `assert_no_cell_is_filled` also fails if a consumer cell carries any non-null metric. `how_to_fill` names
  the dry-run and hermetic commands and says the live mode is FS-2 under the owner's paid gate.
- `project_budget.consumer_cells_note`: not projected because the runner's hermetic mode submits no job; the declared
  consumer block is listed unspent.
- `render_markdown`: the "Cells this blocks" paragraph says the consumer cells stay INCOMPLETE because the runner has
  no live mode (`RUNNER_HERMETIC_ONLY`); each consumer cell's bullet lists its hermetic runs by id with attempt counts
  and decisions only.
- `python3 -m okf_bq_graph.sql_baseline` regenerates `plan.json` and `baseline.md`; committed copies stay
  byte-identical to the generator.

## 8. Retained evidence

Two hermetic runs are committed under `evidence/consumer/`: one campaign covering both cells at their predeclared
2 + 20 (C=1 then C=5) plus one probe each, with every diagnostic. They are cited by the card's `hermetic_runs`.
Their numbers are orchestration overhead of an in-process oracle plus a subprocess emulation on one laptop and are
labelled so in the record; they are not shown on the card and are not the cells' metric.

## 9. Wording per surface

Rule: every current-tense surface that said the full path "has no runner" now says it has a **hermetic-only runner**
(rehearsed offline; no live sampling has run; nothing timed live), keeps "synthetic" beside the selection and the
Alder cohort NOT SELECTED as its own statement, and reader-facing board-pack prose carries no run ids, digests or
job ids.

- `STORY.md` (bar-unchanged paragraph, matched-baseline paragraph) and `spec-sep19-pack.md` (consumer-cell bullet,
  acceptance line): "no runner" → "a hermetic-only runner; no live attempt has been sampled"; `NOT_IMPLEMENTED` →
  `RUNNER_HERMETIC_ONLY` in the acceptance line.
- `rfc/index.html` (still-open paragraph, evidence bullet): "because it has no runner" → "its runner has been
  rehearsed offline against an emulation and has not been run live"; the two question-to-number cells "still have
  no live runner".
- `rfc/detailed-rfc/index.html`: the same substitution where the consumer cells are described, plus a footer clause
  dated 2026-09-09.
- `plan-knowledge-publications.md` (current guidance): the three consumer clauses say hermetic-only runner, no live
  sampling.
- `README.md`: the module table gains `consumer_run.py`; the consumer-cell bullet and the two `NOT_IMPLEMENTED`
  history sentences gain the dated FS-1 state; a new paragraph describes the hermetic runs and what they do not
  establish.

## 10. Tests

New `tests/test_consumer_run.py` (SDK- and Acme-dependent tests skip when either checkout is absent):

- the parser has no `--live`; `--dry-run` and `--hermetic` are exclusive and one is required;
- an UNSELECTED plan is refused `FACTS_UNSELECTED` before anything else; a retrieval cell is refused
  `NOT_A_CONSUMER_CELL`; a reused or unlabelled run id is refused; a `--as-of` before 2026-03-12 is refused
  `VALIDITY_WINDOW`; a mutated vendored fixture is refused `VENDORED_FACTS_DRIFTED`; a plan whose expected January
  value is changed is refused `ORACLE_DISAGREES`;
- the row oracle returns `400` for January and `515` for January–February at 2026-09-09, `None` for a period with no
  recognised order, the FX path multiplies, and a mutated February amount changes January–February only;
- `admit_live`: `OK` with the digest on the vendored manifest before the expiry; `MATERIALIZATION_EXPIRED` on and
  after 2026-10-05; `FACTS_DRIFTED` naming the table for a mutated amount and for a removed table, even when row
  counts and the January result still match;
- dry-run opens nothing (a BigQuery client constructor that raises if called), prints the gates and the unspent
  budget, exits 0;
- hermetic end to end on a shortened copy of the plan (1 warmup, 2 measured): every attempt retained in
  `attempts.jsonl` and the record, `RELEASED` with `VERIFIED`/`MATCH`, the SDK elapsed and the receipt job present,
  `selected_content_digest` equal to the plan's, the probe `REFUSED` at bind with `file_sha256` and `sql_text`
  failed and `invoked: false`, verdict `RUNNER_HERMETIC_OK`, `fills_cell: false`;
- C=5 on the shortened plan reaches `concurrency_achieved > 1` and retains one diagnostic per attempt with distinct
  paths;
- a child that dies (a runner stub returning exit −1) gives `NOT_REACHED` and `RUNNER_HERMETIC_INCOMPLETE`; a
  consumer stub that releases the probe gives `WRONG` and `RUNNER_HERMETIC_BROKEN`; no BigQuery client is ever
  constructed in hermetic mode (the same raising constructor);
- `refusal_reasons` is `["RUNNER_HERMETIC_ONLY"]`; the sql-baseline dry-run and campaign summary agree; the
  `FACTS_UNSELECTED` path still works on a flipped copy;
- the card's consumer cells read `RUNNER_HERMETIC_ONLY`, `measured_n` 0, null metrics, list the committed hermetic
  runs, and the rendered Markdown carries no millisecond figure inside the consumer-cell lines; `validate_plan`
  refuses a missing consumer budget block, a ceiling above the campaign ceiling and a `SPENT` state;
- the committed run records validate (every attempt has a decision and a diagnostic digest; the probe refused at
  bind; run ids labelled); `plan.json` / `baseline.md` equal the generator's output;
- surfaces: no current-tense surface still says "no runner" without "hermetic", each says synthetic and keeps Alder
  unselected, reader-facing prose carries no run id or digest (existing test module extended).

## 11. Not claimed

A live attempt; a job identity; any `request_to_consumer_ms` value; any cost; a verified live materialization
(`live_materialization` stays `UNVERIFIED`); chain equivalence (`UNPROVEN`); GoogleSQL execution of the sanctioned
SQL; a filled consumer cell; any threshold accepted; any spend from the declared consumer budget.
