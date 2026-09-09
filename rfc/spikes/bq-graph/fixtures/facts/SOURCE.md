# Vendored fact-data artifacts (synthetic)

These files identify the fact-data version the ordinary-SQL comparison selected on 2026-09-09
(`fixtures/sql_baseline.json` → `facts.selected_version`). They are **synthetic**: the receipt example's invented
Acme fixture, 7 tables and 14 rows, USD only (`fx_daily_rates` is created empty). No customer data.

| File | Origin | SHA-256 |
| --- | --- | --- |
| `fixture.sql` | `git show 6719eb535667963fa640dd4535e508b550eb6cb1:examples/okf_attested_computation/fixtures/fixture.sql` in `BigQuery-Agent-Analytics-SDK` (branch `spike/okf-result-bound-receipt-20260905`) | `940aacdc125a64c7ef88fdfb6eb16677b072b4b77d19443632b4308c4fe5f124` (3,375 bytes) |
| `expected.json` | same commit, `…/fixtures/expected.json` | `281981f07495d77172e0fd4dc081643454a8be5d1210c2d04df20919fb6dc25f` (471 bytes) |
| `publication.json` | same commit, `…/fixtures/publication.json` | `305d6ecdb542ee095d657ec8408d519423edfcacffd5a457b8e7f745f84961ab` (1,221 bytes) |
| `gross-margin-period.md` | same commit, `…/fixtures/acme_retail/gross-margin-period.md` (the declaration whose bytes the chain bound) | `5e96ae11835ad328ccc94d29ae4bc7cc40176758cbcbad63231d0461c1f8f0e7` (3,307 bytes) |
| `source.json` | this table, machine-readable; `validate_plan` binds `facts.selected_version` to it | — |
| `content.json` | derived: `python3 -m okf_bq_graph.fact_content fixtures/facts/fixture.sql > fixtures/facts/content.json` | `7264e7df6276463dc4ec7a6b179b87bff08aaa105660ea37611398fc197454f0` (2,617 bytes) |

The four SDK files are byte-equal copies of the pinned Git objects (verified with `shasum -a 256`
on 2026-09-09 against a local clone holding the pin). `content.json` is the canonical `okf-fact-content/1`
manifest (schemas and rows, sorted keys, compact separators, ASCII, trailing newline; see
`okf_bq_graph/fact_content.py` for the value encodings). `validate_plan` re-hashes all of them, binds every recorded digest and path to `source.json` and to the
publication manifest's own dataset, tables and computation digest, and re-derives the manifest from the script every
time the card is built.

What these files do **not** establish: that the live dataset `test-project-0728-467323.okf_receipt_spike_20260905`
holds these rows today (`live_materialization: UNVERIFIED`; only a full-schema, full-row readback matched to the content
digest could, and row counts plus a matching January answer cannot), or that the 2026-09-07 chain ran on byte-identical
rows (`historical_chain_equivalence: UNPROVEN`; the load job is retained as a 600-byte query prefix). The live
tables were provisioned with a 30-day expiration and lapse about 2026-10-05; re-loading the same script yields the
same content digest but a new load job, which must then be recorded on the selection.
