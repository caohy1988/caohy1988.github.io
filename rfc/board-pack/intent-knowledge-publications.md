# Intent — PROPOSED BigQuery Knowledge Publications

Status: a proposed product definition, written down so it can be scoped and argued with. It is not a roadmap
commitment. No BigQuery team has been staffed to build it and no customer demand has been established for it. Every
product name, resource, operation and field in this document and its companions
(`spec-knowledge-publications.md`, `plan-knowledge-publications.md`) is **PROPOSED**. Sketches describe contracts, not
supported syntax.

Source: the 2026-09-08 product consult on whether "BigQuery as the runtime for OKF and Knowledge Catalog" is a
shippable BigQuery feature. Two independent analyses reached the same boundary: the runtime is an integration
*pattern*, and the smallest BigQuery-owned feature inside it is a managed publication and retrieval surface. The board
pack already carries the resulting callout; this slice writes the intent, surface and next slices behind it.

## Problem

An analytical agent that is about to release a number needs a connected set of context, not a single hit: the approved
metric definition, the rules it links to (the board-pack story's starting-cohort rule), and the calculation Finance
declared for it. Today that context exists as an OKF bundle (Open Knowledge Format) discovered through Knowledge
Catalog. Discovery ranks candidates by similarity; it does not pin the linked context, fix a version for the length of
a request, or check at read time that this requester may see each part. Assembling the context is left to whichever
retriever the customer writes.

The board pack's near-miss is the consequence. The agent found the retention definition, missed the cohort rule beside
it, reused a total-ARR query, and nobody could say afterwards which definition it had been given or why it could read
that asset. The recorded experiments show the missing behaviour is buildable on what BigQuery already offers: an OKF
bundle compiled into an immutable projection; pinned retrieval that returns the definition together with its linked
rules and declared computation; access enforced against a separate restricted identity on the SQL path; a consumer
that releases nothing unless a receipt check passes. All of it ran as spike code and an SDK example on ordinary
tables, row policies, authorized views, property graphs and vector search. None of it is a supported BigQuery
resource. A customer who wants the behaviour today must build and operate the publication and retrieval service
themselves, which is exactly what the spike is.

## Why BigQuery should own it

- **The value is in the guarantees, and only the service can enforce them.** Immutable publication identity, atomic
  activation, a pin that holds for the whole request, current permission checks on the managed read path, a retained
  context record, and documented refusal and expiry behaviour. A client-side convention can promise these; it cannot
  enforce them. The test is whether a customer can delete the example runner and still have the capability. Today
  they cannot.
- **The facts already live in BigQuery for the agents this is for.** Keeping knowledge retrieval in the same engine as
  the fact data keeps access policy, audit and billing in one place, and lets a later execution feature bind approved
  calculations to results without crossing a service boundary.
- **Knowledge Catalog already serves basic OKF context; what is missing is versioned lifecycle.** Catalog discovery
  and context APIs cover finding a bundle and reading it. They do not offer an immutable compiled version with atomic
  activation, pin-or-refuse retrieval, and a read path that enforces access along the links it discloses. That is a
  runtime job, and BigQuery is the runtime the facts already sit in.
- **Graph stays optional.** Native graph queries are generally available but edition-gated. A SQL-first design keeps
  the first release on on-demand capacity and makes graph traversal a later engine choice inside the service, not a
  customer-visible prerequisite.
- **The honest fallback is named.** If no BigQuery team will own the managed contract, the same capability ships as an
  Analytics SDK integration and BigQuery is described as its execution backend. That is an integration, not a
  feature, and the board pack must say which one it is.

## Non-goals

- **Not "BigQuery is the runtime of Knowledge Catalog".** Catalog keeps discovery and catalog governance; OKF authors
  keep the source and its meaning. The publication is a projection with a pointer back, never the authority.
- **Not the verified job receipt.** Binding an approved calculation and its fact versions to a BigQuery result is a
  separate execution feature (proposed as Knowledge-Bound Jobs / a verified job receipt). It is the follow-on, not
  part of this MVP. The first release ships pinned context, not a checked retention number.
- **Not fact-version pinning.** A publication pins definitions. It does not freeze fact rows, SQL dependencies or
  policy. The consumer path in the ordinary-SQL comparison stays blocked on fact-version selection, and this proposal
  does not unblock it.
- **Not a managed OKF import into BigQuery Graph as a product of its own.** The graph projection is an internal engine
  choice. Import alone leaves the consistency and evidence contracts unresolved.
- **Not the Finance pilot, and not a demand claim.** A pilot is a customer-learning exercise that would supply
  validation data and demand evidence. It is not the product and it is not evidence that the product is wanted.
- **Not general graph queries on on-demand capacity.** The temporary allowlist exception is not a launch basis.
- **Not a change to OKF.** The supported runtime profile adds no new format requirements.

## Constraints

- **Pattern is not roadmap.** No sentence in these documents or on the board pack may imply a staffed BigQuery
  roadmap, a release date, an edition promise or a customer commitment. Sequencing boundaries are proposed.
- **Catalog metadata visibility is not data permission.** The read path enforces current access for the authenticated
  requester at retrieval time. A historical pin cannot preserve revoked access; a later request against an old pin is
  refused, not served from history.
- **The pin is a pointer with a digest, never a copy.** Catalog holds a runtime reference to the ready publication;
  the service refuses when the digest does not match the projection. Who may activate, withdraw and delete, and how a
  republish preserves authored aspects, is part of the contract.
- **Evidence limits carry forward unchanged.** Every recorded experiment used invented Acme gross-margin data. Catalog
  discovery, a separate restricted identity and graph queries have never been combined in one run. Access denial has
  been shown on the SQL path only, not inside a graph walk. On the BigQuery engines a cached result was replayed after
  a link revocation; the service contract must close that gap rather than inherit it. The graph benchmark is
  unfinished. Combining these descriptions does not produce stronger validation.
- **Edition gates are stated where they apply.** Graph queries need Enterprise or Enterprise Plus reservations;
  graph search and graph measures are Preview; fine-grained security has its own edition distinctions.
- **This slice is documents only.** No live cloud run, no spike measurement change, no board-pack rewrite. The only
  reader-facing change is a link from the existing Knowledge Publications callout to these documents.

## Success for this slice

Three companion documents under `rfc/board-pack/` state the intent, the proposed surface and contract, and the next
engineering slices; the board pack's existing Knowledge Publications callout links to them; nothing on the board pack
reads stronger than it did before.
