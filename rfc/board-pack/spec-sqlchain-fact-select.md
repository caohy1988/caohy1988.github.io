# Spec — fact-data version SELECTED for the ordinary-SQL comparison (synthetic fixture digest)

Files: `rfc/spikes/bq-graph/fixtures/sql_baseline.json` (the `facts` block), `rfc/spikes/bq-graph/fixtures/facts/*`
(vendored artifacts), `rfc/spikes/bq-graph/okf_bq_graph/{sql_baseline.py,fact_content.py}`,
`rfc/spikes/bq-graph/evidence/sql-baseline/{plan.json,baseline.md}` (regenerated), tests, and the wording on
`rfc/board-pack/{index.html,STORY.md,spec-sep19-pack.md}`, `rfc/index.html`, `rfc/spikes/bq-graph/README.md`.
Intent in `intent-sqlchain-fact-select.md`; next slices in `plan-sqlchain-fact-select.md`.

## 1. The selection record

`facts.state` becomes `SELECTED`; `facts.blocks` becomes `[]`; `facts.what_is_missing` is dropped (nothing is
missing from the selection); `why_it_matters` and `observed_in_the_retained_chain` stay, and the latter is still read
back from the chain record by test; `how_to_select` now says how it was selected and which alternatives were
rejected. Two blocks are added.

**`facts.selected_version`** — flat, so the existing renderer prints it field by field. Every value is a string, a
number, a boolean, a list of strings or a name→count map; no nested records.

| Field | Value (verified offline from the pinned SDK Git objects on 2026-09-09) |
| --- | --- |
| `kind` | `loaded-fixture-digest (synthetic)` |
| `synthetic` | `true` |
| `customer_data` | `none` plus the sentence that the Alder cohort has never been selected and is a customer dependency |
| `scope` | engineering comparison only; 14 invented rows measure the chain's overhead, not fact-scan latency or cost at any customer scale; USD only, the FX table is empty |
| `dataset`, `location` | `test-project-0728-467323.okf_receipt_spike_20260905`, `US` |
| `tables` | the seven table names, sorted |
| `sdk_pin` | `6719eb535667963fa640dd4535e508b550eb6cb1` |
| `fixture_path`, `fixture_sha256`, `fixture_bytes` | `examples/okf_attested_computation/fixtures/fixture.sql`, `940aacdc125a64c7ef88fdfb6eb16677b072b4b77d19443632b4308c4fe5f124`, 3375 |
| `expected_results_path`, `expected_results_sha256` | `…/fixtures/expected.json`, `281981f07495d77172e0fd4dc081643454a8be5d1210c2d04df20919fb6dc25f` |
| `publication_manifest_sha256` | `305d6ecdb542ee095d657ec8408d519423edfcacffd5a457b8e7f745f84961ab` |
| `computation_sha256` | `5e96ae11835ad328ccc94d29ae4bc7cc40176758cbcbad63231d0461c1f8f0e7` (the chain's `sdk.computation_sha256`) |
| `content_manifest_format`, `content_manifest_sha256` | `okf-fact-content/1`, `7264e7df6276463dc4ec7a6b179b87bff08aaa105660ea37611398fc197454f0` — the canonical schema-and-rows manifest derived from the fixture script (§2) |
| `row_counts`, `row_count_total` | `fulfillment_cost 2, fx_daily_rates 0, order_lines 3, orders 3, payment_fees 2, products 2, shipment_cost 2`; 14 |
| `expected_gross_margin_usd_2026_01` | `400` (from `expected.json` `approved_january`) |
| `loaded_by_job`, `loaded_utc` | `test-project-0728-467323:US.bqjob_rb53f55e41faf967_000001a073eea67a_1` (13 child jobs, DONE); `2026-09-05T23:36:55Z` to `23:37:11Z` |
| `load_evidence` | the legacy-reconcile listing index keeps that job's query text as a 600-byte prefix only: it proves a fixture load at that time, not byte identity with `fixture_sha256` |
| `live_materialization` | `UNVERIFIED: …` — no live read was made by this selection |
| `historical_chain_equivalence` | `UNPROVEN: …` — the 2026-09-07 chain's released `$400.00 VERIFIED` equals `approved_january`, which is consistent with this content and proves no byte-equality |
| `conformance_observed` | the chain record path and display string that carried that `$400.00` |
| `valid_for_runs_on_or_after`, `validity_note` | `2026-03-12`; the compiled SQL's `CURRENT_DATE()` 30-day recognition window and the latest fixture order date (2026-02-10); the SQL is not changed because that would change `computation_sha256` |
| `materialization_expires_utc` | about `2026-10-05` (30-day table expiration set at provisioning); after that the same digest must be re-loaded and the new load job recorded |
| `live_precheck` | a contract for the runner slice, marked not implemented: the runner reads every selected table back in full (schema and rows), canonicalises the readback as `okf-fact-content/1` and requires its digest to equal `content_manifest_sha256`, then binds that verified immutable or protected table set to every attempt; otherwise the campaign stops `FACTS_DRIFTED` with no cell filled. Row counts and the January `400` are smoke checks only: changing one non-January amount leaves both unchanged while the content digest and the January–February result change |
| `selected_utc`, `selected_by` | `2026-09-09`; the project owner after the two-lens consult |

**`facts.customer_data`** — its own block and its own row on every surface: `state: NOT SELECTED`, the Alder cohort
named as the board-pack story's illustrative customer, and the sentence that it is a customer's to give, nobody
outside this project has been asked, and selecting the synthetic fixture changes nothing here.

## 2. Vendored artifacts and the content manifest

`rfc/spikes/bq-graph/fixtures/facts/`:

- `fixture.sql`, `expected.json`, `publication.json` and the declaration `gross-margin-period.md` — byte-equal
  copies of the pinned SDK Git objects (`git show <pin>:<path>`), so every digest recomputes without an SDK checkout.
  `source.json` is the machine-readable provenance pin (SDK path, digest and size per file, pin and branch);
  `SOURCE.md` says the same for a reader with the recompute commands.
- `content.json` — the canonical content manifest (`okf-fact-content/1`): a table map, each table's ordered
  schema fields (`name`, `type`, `mode`) and its rows in schema order; sorted object keys, compact separators,
  ASCII escaping, one trailing newline; rows sorted by their own compact encoding, duplicates retained; NUMERIC as
  nine-fractional-digit decimal strings, INT64 as decimal strings, TIMESTAMP as UTC with six fractional digits and
  `Z`, DATE as ISO dates. Its SHA-256 is `content_manifest_sha256`.
- `okf_bq_graph/fact_content.py` — the bounded literal-fixture extractor that derives the manifest from the script
  (`CREATE OR REPLACE TABLE` schemas and `INSERT … VALUES` tuples; it fails on any SQL it did not consume, so it is
  not a SQL interpreter). Regenerating `content.json` from the vendored `fixture.sql` must reproduce it byte for byte.

## 3. Validation gates (offline, in `validate_plan`)

When `facts.state == SELECTED`:

- `selected_version` must be a record, not a bare label; the fields in §1 marked as identity (`kind`, `synthetic`,
  `customer_data`, `dataset`, `location`, `tables`, `sdk_pin`, `fixture_path`, `fixture_sha256`,
  `expected_results_sha256`, `computation_sha256`, `content_manifest_sha256`, `row_counts`, `row_count_total`,
  `live_materialization`, `historical_chain_equivalence`, `valid_for_runs_on_or_after`, `materialization_expires_utc`)
  are required; SHA-256 fields are 64 lowercase hex characters, the pin is 40; `row_counts` names exactly the
  tables and sums to `row_count_total`; `live_materialization` starts with `UNVERIFIED` or `VERIFIED` and
  `historical_chain_equivalence` with `UNPROVEN` or `PROVEN`.
- The vendored `fixture.sql`, `expected.json` and `content.json` must hash to the recorded digests, and
  `fact_content.extract(fixture.sql)` must canonicalise to the vendored `content.json` bytes with the recorded
  per-table row counts. A wrong hash, a missing artifact or a drifted manifest fails the build.
- If `observed_in_the_retained_chain` is present, `dataset`, `tables` and `sdk_pin` must equal it: the selection
  names what the chain used.
- Source identity is bound to offline provenance, not accepted as syntax: `fixtures/facts/source.json` pins the SDK
  path, digest and size of every vendored file; `sdk_pin`, `fixture_path` and `expected_results_path` must equal it,
  `publication_manifest_sha256` must equal the vendored `publication.json` and `computation_sha256` the vendored
  declaration `gross-margin-period.md`, and `dataset`, `location`, `tables` and `computation_sha256` must equal what
  the vendored publication manifest declares.
- Unsupported promotions are refused: `synthetic` must be `true`, `live_materialization` must start with
  `UNVERIFIED`, `historical_chain_equivalence` with `UNPROVEN`, and `facts.customer_data.state` must be
  `NOT SELECTED`. A future VERIFIED readback, a PROVEN equivalence or a customer selection each needs its own
  separately validated evidence or owner record, which no schema defines yet; a bare word is not evidence.
- Dates are real calendar dates (`valid_for_runs_on_or_after`, `selected_utc`); `materialization_expires_utc` reads
  `about YYYY-MM-DD …` or `unknown …` and refuses null, malformed values and a bare exact timestamp, because an exact
  expiry would need a table `expirationTime` readback the record does not carry.
- `blocks` must be empty.
- `facts.customer_data`, when present in **either** state, must be a record with `state` `NOT SELECTED`; the legacy
  `UNSELECTED` shape without the block stays valid. `render_markdown` refuses a card whose customer block says
  anything else, so a false customer status cannot be printed from a tampered card either.

Unchanged for `UNSELECTED`: the four explanatory fields stay required and `blocks` must name real cells.

## 4. Card and runner behaviour

- `build_card`: both consumer cells carry `fact_version_blocked: false`, `blocked_by: null`, `stopped_reason`
  `NOT_IMPLEMENTED`, `measured_n` 0, null metrics; `how_to_fill` names the selected synthetic version and the live
  precheck the runner must run first. Every cost cell stays `UNMEASURED`. `assert_no_cell_is_filled` still passes.
- `render_markdown`: `## Fact data — **SELECTED**`; the version printed field by field (booleans as `true`/`false`,
  lists comma-joined, the row-count map as `name=count` pairs); a separate **Customer fact data (Alder cohort) — NOT
  SELECTED** paragraph; the "Cells this blocks" sentence says the selection clears `FACTS_UNSELECTED` only and that
  the consumer cells stay INCOMPLETE because no sampled runner exists; no `FACTS_UNSELECTED` anywhere on the card.
- `sql_baseline_run`: `refusal_reasons(plan, consumer cell) == ["NOT_IMPLEMENTED"]`; `select_cells` still raises
  `RefusedCell`; the campaign summary reads `REFUSED (NOT_IMPLEMENTED)`; `--cells sqlchain_forced_c1` still exits
  `REFUSED:` without opening a client. The `FACTS_UNSELECTED` path stays covered by a test that flips a copy of the
  plan back to `UNSELECTED`.
- `python3 -m okf_bq_graph.sql_baseline` regenerates `plan.json` and `baseline.md`; the committed copies are
  byte-identical to the generator (existing test).

## 5. Wording per surface

Rule: `SELECTED` never appears without `synthetic` in the same sentence, and the customer dependency is its own row
or sentence. Reader-facing board-pack prose carries no hashes, job ids, PR numbers or reviewer names; those live on
the baseline card, which the page links to.

- `spec-sep19-pack.md` and `STORY.md` envelope tables: the fact row splits in two — *Fact data and its version
  (comparison fixture)* → **SELECTED (synthetic)**, and *Customer fact data (Alder cohort)* → **NOT SELECTED —
  customer dependency**. The Slice A acceptance line and the scaffold bullet describe both states and the new gates.
- `STORY.md` "bar is unchanged" paragraph and `board-pack/index.html` still-open sentence and evidence bullet:
  "has no runner and no selected fact-data version" → the full path still has no runner; its fact data is a
  selected synthetic fixture, not customer data.
- `board-pack/index.html` envelope paragraph: "The fact data and its version. Chosen for the comparison, and
  synthetic." — the rows are the receipt example's own fourteen-row invented fixture, pinned two ways: by the
  digest of the script that loads them (`fixture_sha256`) and, separately, by the digest of the rows and columns
  themselves (`content_manifest_sha256`), with the load job on record. Before measuring, a future run must read every
  table back in full and match the rows and columns to the content digest, not the script digest; counts and a
  matching answer are not enough, and no runner does this yet. It is not customer data and Alder's cohort has never
  been selected. The two digests are never conflated on any surface: the readback target is always the content
  digest.
- `rfc/index.html` (phase table, review-row, footer): same substitution, plus a footer clause dated 2026-09-09.
- `README.md`: the two "still read `NOT_IMPLEMENTED + FACTS_UNSELECTED`" sentences become dated history with the
  current state beside them.
- Historical slice documents (`intent-pass2-honesty.md`, `spec-pass2-honesty.md`, `plan-sep19-pack.md`, the
  Slice B docs, `intent-knowledge-publications.md`, `plan-knowledge-publications.md`) describe the state at their
  own date and are left as written, except that the Knowledge Publications plan's "what stays demo evidence" row
  and its two consumer-cell clauses are updated because that plan is current guidance, not a dated record.

## 6. Tests

Existing SELECTED-path gates keep passing with a real record substituted for the placeholder label. New:

- the committed plan is `SELECTED`, `synthetic` true, `customer_data.state` `NOT SELECTED`, `blocks` empty, no
  `what_is_missing`;
- every recorded digest equals the SHA-256 of the vendored file; the extractor reproduces `content.json`; the
  derived row counts equal `row_counts` including `fx_daily_rates 0`;
- the selection names what the chain used (`dataset`, `tables`, `sdk_pin`, `computation_sha256`);
- the January expectation equals `expected.json` and the number in the chain's released display;
- the load job id is in the listing index with `DONE`, 13 child jobs, and a stored query prefix equal to the first
  600 bytes of the vendored script — the test name says it is a prefix;
- a bare-string version, a wrong hash, a mutated vendored row, a deleted table in the manifest and a `row_counts`
  that disagrees with the manifest are each refused;
- `refusal_reasons` is `["NOT_IMPLEMENTED"]` only; the dry-run CLI and the campaign summary agree; the
  `FACTS_UNSELECTED` path still works on a plan flipped back to `UNSELECTED`;
- the four current-tense surfaces no longer say "no selected fact-data version" or "not yet chosen", each says
  "synthetic" beside the selection, and each keeps the Alder cohort NOT SELECTED;
- committed `plan.json` / `baseline.md` equal the generator's output.

## 7. Not claimed

Customer data; a Finance-approved or representative dataset; that the live dataset's rows equal the digest today;
that the September 7 chain proved byte-equivalence; a durable materialization (the tables expire about 2026-10-05);
any consumer-cell measurement; any cost measurement; any threshold accepted.
