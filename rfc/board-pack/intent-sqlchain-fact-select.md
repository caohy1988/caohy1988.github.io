# Intent — select the fact-data version for the ordinary-SQL comparison (synthetic fixture digest)

Status: an owner-authorized selection, implemented offline. It changes one predeclared field of the ordinary-SQL
comparison (`facts.state`) from `UNSELECTED` to `SELECTED` and records exactly what was selected. It runs nothing
live, measures nothing, and moves no threshold out of PROPOSED. Companions: `spec-sqlchain-fact-select.md` (the
record, the gates, the wording) and `plan-sqlchain-fact-select.md` (what comes next).

Source: the 2026-09-09 fact-data consult. Two independent analyses (an implementer lens and a reviewer/honesty lens)
were asked which fact-data version the request-to-consumer comparison should pin and whether to pin one now. Both
recommended selecting now, as the **digest of the synthetic fixture the receipt example loads**, rather than waiting
for a customer cohort, a Finance owner, or snapshot tooling. The owner authorized the implementation. The two memos
differ in record shape (flat fields versus a nested content manifest); this slice takes the flat, renderer-compatible
record and adds the reviewer lens's honesty fields.

## Problem

The comparison's task releases a computed number, so comparing two runs of it needs the version of the fact rows the
number came from. Since the September 19 pack was scaffolded, that field has read `UNSELECTED`: the retained chain
named seven fact tables in the receipt example's dataset but pinned no snapshot, no as-of and no row version for
them. That gap blocked the two request-to-consumer cells with a second reason (`FACTS_UNSELECTED`) beside the real
one (no sampled runner exists). Every board-pack surface repeated "no runner and no selected version of the fact
data", and the plan's own advice was to "name the fact dataset together with a reproducible version for it".

Nothing anyone could wait for changes the answer. Customer (Alder) cohort data is a customer's to give and nobody
outside this project has been asked. BigQuery time travel lasts days, not the weeks between runs, so a snapshot
decorator cannot be the version. The fixture is already fully deterministic: a script of literal `CREATE OR
REPLACE` and `INSERT … VALUES` statements at a pinned SDK commit. Its digest identifies the rows offline and can be
re-checked live by reloading the script.

## What this slice selects, and what it does not

It selects **the synthetic fixture's content**, identified by the SHA-256 of the fixture script at the SDK pin the
retained chain already names, with the load job, the expiry, the validity window and the expected January result
recorded beside it. It vendors the fixture script, the expected results and a canonical content manifest into this
repository so the digest can be recomputed without the SDK checkout.

It does not select customer data. The Alder cohort stays **NOT SELECTED** as its own row on every surface, not as a
clause inside the synthetic row. It does not claim the live dataset's rows were verified against the digest (they
were not read in this slice), nor that the September 7 chain proved byte-equivalence with the fixture (the load job
is retained as a 600-byte query prefix, so it proves a fixture load at that time, not byte identity). Both stay
recorded as `UNVERIFIED` and `UNPROVEN`. It does not build the sampled runner, so both request-to-consumer cells
stay `INCOMPLETE` with `NOT_IMPLEMENTED` as their only reason, and every cost cell stays `UNMEASURED`.

## Why it is worth doing on its own

Selecting clears one of the two blockers on the consumer cells and makes the remaining one honest: the next slice
is a runner, and a runner can now be specified against a named fact version with a live precheck (a full-schema,
full-row readback of the seven tables matched to the content digest, the digest of the rows and columns rather than
of the loading script; row counts and the expected result are smoke checks only) instead of an unnamed one. It also stops four surfaces from repeating a gap that the project
had the power to close.

## Out of scope

Live BigQuery reads, reloads or snapshot creation; the sampled request-to-consumer runner; any change to the SDK or
to the retained chain records; any change to the receipt fixture's SQL (its `CURRENT_DATE()` clause is recorded as a
validity window, not fixed, because fixing it would change the computation digest the retained chain bound to).
