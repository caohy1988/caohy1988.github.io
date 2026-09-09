# Intent — Sep 19 ordinary-SQL baseline Slice B

Fill the four predeclared **retrieval** cells on the ordinary-SQL (`fallback`) engine so the 2026-09-19 checkpoint has a real comparator, not an empty plan.

## Why
Slice A (PR 46) predeclared the baseline card. Without a driver and retained samples, Sep 19 cannot compare GQL/graph work to ordinary SQL on the same corpus and question shapes.

## In scope
- Driver that reads `fixtures/sql_baseline.json` / `evidence/sql-baseline/plan.json`
- Run cells: `sqlbase_forced_c1`, `sqlbase_forced_c5`, `sqlbase_natural_c1`, `sqlbase_natural_c5`
- Foreground live run on-demand (no reservation window), unique `run_id`, retain every attempt
- Hermetic tests for the driver wiring
- Honest card/README update after measurement (or still-INCOMPLETE if a cell stops)

## Out of scope
- Consumer cells (`sqlchain_*`) — blocked on `FACTS_UNSELECTED` + no runner
- Accepting PROPOSED envelope thresholds
- GQL comparison, Neo4j, new product scope
- Inventing a fact-data version or customer cohort
