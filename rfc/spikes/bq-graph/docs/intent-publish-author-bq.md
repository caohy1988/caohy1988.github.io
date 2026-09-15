# Intent: publish in BigQuery, then consume through the connected path (RFC-aligned full path)

Slice owner: Claude Opus (implementer). Reviewers: Astra (primary, overnight merge representative), Kimi (second LGTM,
quota permitting). Date: 2026-09-15.

## Why

The connected run `e2e-20260915t070643z-9ddaf35f` (PR #77) started from a Catalog entry and a BigQuery publication that
already existed. Nothing in that run authored or published anything. The RFC's design begins one step earlier:

- **Authority (§04).** BigQuery's relational deployment head is the serving authority. Catalog is the governed
  discovery projection. A Catalog failure never rolls back a committed publication.
- **Cross-service consistency (§05).** Immutable rows are staged, then the head advances atomically to the new
  publication (`BQ_COMMITTED`). Catalog reconciliation follows (`KC_APPLIED`). The RFC says "No recorded run shows this
  protocol."
- **The three as one path (landing page).** A live catalog read pins the publication, governed retrieval supplies the
  declared calculation, and the receipt check verifies the job before release.

Haiyuan asked for the author/publish step "to happen in BQ as we have discussed", for the demo to be "as real as
possible", and for it to be "fully aligned with the RFC". A publish that is only a Dataplex `kcmd push` or
`create_entry` does not meet that. Neither does a consumer that reads a pin nobody published in the same run.

## What this slice delivers

One live invocation, in RFC order:

1. **Author / publish (BigQuery).** Compile the pinned synthetic Acme bundle into an immutable projection. Append it to
   a run-owned BigQuery dataset, read every row back and validate it against the compiled manifest. Mark the
   publication `READY`, then advance the head with one atomic `MERGE`. Every step is a real BigQuery job with a
   driver-chosen id, journaled before it is waited on.
2. **Catalog discovery projection.** Only after the head has advanced, write a run-owned Catalog entry whose runtime
   pin is generated from the `READY` BigQuery rows. Read it back through the Catalog parser.
3. **Discover.** The restricted requester reads that entry itself and gets a validated pin.
4. **Pin and retrieve a fixed context.** The requester resolves exactly that `READY` publication (the head is observed,
   never followed) and retrieves the definition, linked rule and declared calculation under current access.
5. **Evaluate current access.** Unauthorized output is denied. After revocation, a fresh request, a cached-pin bypass
   and the stored receipt are all refused.
6. **Validate the calculation.** The number is released only on a result-bound `VERIFIED` receipt. A substituted
   query is refused.
7. **Enforcing consumer.** Releases or refuses on the evidence above.
8. **Teardown.** Grants are restored and read back. The run-owned entry and dataset are deleted, and their absence is
   read back.

The verdict `E2E_PUBLISH_CONNECTED` requires all of these at once:

- the publication was `READY` and its head was observed switched;
- the Catalog pin was generated from those rows;
- the consumer resolved that exact publication in that dataset;
- the connected run is `E2E_CONNECTED`;
- every author job ran as the operator;
- cleanup is `COMPLETE`.

The ADK agent on `gemini-3.8-flash` drives the full path. The tape shows the publish beat (job ids, `READY`, head
before/after) ahead of the consume beats.

## RFC coverage this slice targets

| RFC section | Claim exercised | How |
|---|---|---|
| Detailed §04 Authority | BigQuery head is serving authority; Catalog is the discovery projection, written after commit | Lifecycle publish, then `write_pin` from `READY` rows |
| Detailed §05 sync states | `BQ_STAGED` → `BQ_COMMITTED` (atomic head) → `KC_APPLIED` → `COMPLETE`, recorded once | state trace in the publish record (simplified, see residuals) |
| Detailed §04 "What this profile adds" | a Catalog-discovered seed carries the publication it describes, and the runtime serves exactly that one | the consumer pins the freshly published id |
| Landing "Retrieve a fixed context" | definition, linked rule and declared calculation under fixed inputs | governed retrieval on the published tables |
| Landing "Evaluate current access" | restricted requester; denial; revocation holds | connected cases 3–5 |
| Landing "Validate the calculation" | result-bound receipt; release only on `VERIFIED` | connected cases 1–2 |
| Landing "The three as one path" | one path from live catalog read to enforcing consumer | same run, now starting from its own publish |

## Honest residuals (not closed by this slice)

- **Graph.** Plain SQL (relational fallback). Access has not been shown inside graph queries (GQL).
- **Attestation.** No independent attester: the SDK's own verifier with a requester-held key.
- **Sample.** n = 1, synthetic Acme data, and no cost or latency benchmark.
- **§05 protocol is simplified.**
  - One run-owned dataset with `active_publication`, not `deployment_heads` / `deployment_heads_history`.
  - No `sync_id` staging, no `*_current` views, no `published_snapshot_id`.
  - No `KC_RECONCILING` lag SLO. No `kcmd` / `okf-context` package.
- **Content-addressed publication.** The id is derived from the pinned source. The run publishes the same id that the
  long-lived spike dataset already holds, into a fresh dataset with fresh rows and jobs. It is a new deployment of an
  existing publication, not a new revision of the knowledge. A new revision would change the source pin, and the
  receipt fixture's lineage label binds the clean pin.
- **Harness-granted access.** The harness grants the requester Catalog viewer on the entry group.
- **Legacy seed.** The denied-intermediate case still uses the injected legacy seed on the long-lived `_rls` copy of the
  same publication id.
- **Teardown.** The run-owned dataset and entry are deleted at the end. Job metadata remains readable; the rows do not.

## Out of scope

- Graph DDL, embeddings or reservations on the publish path.
- Any write to the long-lived spike dataset or the original Catalog entries.
- Relabelling earlier runs: `e2e-20260915t065449z-98e21004` stays `E2E_BROKEN`, and `e2e-20260915t070643z-9ddaf35f`
  stays the consume-only evidence.
- Readiness claims.
