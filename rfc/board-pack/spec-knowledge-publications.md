# Spec — PROPOSED BigQuery Knowledge Publications

Status: **PROPOSED.** Every resource, operation, field, state, refusal code and function name in this document is a
proposed contract, not supported syntax and not a shipping or committed surface. Sketches are written so a product
owner can argue with them; they are not an API reference. Intent in `intent-knowledge-publications.md`; next slices
in `plan-knowledge-publications.md`.

One-sentence definition, as already carried on the board pack: managed, versioned execution of knowledge-retrieval
queries over OKF bundles linked from Knowledge Catalog. Customer job: every analytical agent gets the same approved
definition and the rules it links to for a request, without the customer running its own publication and retrieval
service.

## 1. Customer surface (PROPOSED)

### 1.1 Resources

**Knowledge publication.** A project- and location-scoped resource naming one immutable compiled projection of one OKF
source revision.

| Field (proposed) | Meaning |
| --- | --- |
| `publication_id` | Service-assigned, immutable; derived from the source revision digest and the runtime profile, so the same source under the same profile republishes to the same identity |
| `source_revision` | Where the OKF bundle came from and its content digest; the bundle stays the authored authority |
| `catalog_entry` | The Knowledge Catalog entry this publication is bound to |
| `runtime_profile` | Version of the supported runtime profile the source passed at publish time; adds no OKF format requirement |
| `access_boundary` | The single access boundary (dataset-equivalent) the projection lives in for the MVP |
| `state` | `PENDING` → `READY` → `ACTIVE` → `WITHDRAWN` → `DELETED`; `FAILED` from `PENDING` |
| `diagnostics` | Publish-time validation results the customer can inspect: unresolved references, unsupported constructs, rejected policy mappings |
| `created`, `activated`, `withdrawn` | Timestamps; retention horizon counts from `withdrawn` |

**Activation pointer.** For each bound catalog entry, which publication is current. Switching it is atomic; no request
observes a half-activated publication.

### 1.2 Operations

| Operation (proposed) | Contract |
| --- | --- |
| `publish(source_revision, catalog_entry, runtime_profile, access_boundary)` | Long-running. Compiles, validates references, stores the projection, reads it back, and lands in `READY` or `FAILED`. Never activates by itself in the MVP. |
| `activate(publication_id)` | Atomic pointer switch. Refused unless `READY` and the Catalog binding digest matches. |
| `withdraw(publication_id)` | Pointer cleared or moved; existing pins to it are refused from now on; its records stay readable for the retention horizon. |
| `delete(publication_id)` | Explicit; refused while `ACTIVE`. |
| `get`, `list`, `diagnostics` | Read-only. |
| `query(target, seed, traversal)` | See 1.3. |

### 1.3 Query contract

`target` names either a `publication_id` or a `catalog_entry` plus a pin. A request that names a pin gets exactly that
publication or a refusal; the service never substitutes a newer version silently. A request that names only the entry
gets the active publication and the result records which one that was.

`seed` in the MVP is an exact concept reference inside the publication. A natural-language seed is a later addition:
it needs an embedding model callable under the requester's own identity, and in the recorded experiments that model
was unusable under the restricted identity, so the request failed closed.

`traversal` bounds the walk: maximum hops, maximum nodes, an allowed set of link types, and deterministic ordering.

The result carries the selected nodes, the links that connected them, the declarations reached (including an
attested-computation declaration and its sanctioned SQL as text, where the bundle declares one), and a
service-generated **context record**.

```text
PROPOSED contract sketch. Illustrative only; not supported syntax.

publish
  source_revision : { uri, digest }
  catalog_entry   : "projects/…/locations/…/entryGroups/…/entries/…"
  runtime_profile : "v0"
  access_boundary : { dataset: "…" }
  → publication { publication_id, state: READY | FAILED, diagnostics }

query
  target    : { publication_id } | { catalog_entry, pin }
  seed      : { concept_ref }
  traversal : { max_hops: 2, max_nodes: 200, link_types: [ … ] }
  → { nodes[], links[], declarations[], context_record }

context_record
  publication_id, seed, traversal, requester, retrieval_job,
  returned_node_ids[], returned_link_ids[], served_at, refusal: null | code
```

Later, a SQL table function (working name `KNOWLEDGE_CONTEXT(target, seed, traversal)`) would make the same result
composable with ordinary analytics. That is a later addition, also proposed, and it is not a promise of any syntax.

## 2. Service contract (what the service enforces)

- **Immutability.** A publication id names one projection for its whole life. Content is fixed by the source digest
  and the profile; nothing edits a publication in place.
- **Atomic activation and recoverable publish.** A failed publish leaves no partially visible projection and reports
  why in `diagnostics`. Republishing the same source under the same profile is idempotent.
- **Pin or refuse.** A pinned request is served from that publication or refused with `WITHDRAWN` or `NOT_FOUND`.
  Refusals return no content.
- **Current access on the managed read path.** The authenticated requester is bound to the retrieval job. Permission
  is checked at read time for every node returned and for every link that authorized its disclosure, including when a
  result is served from a cache. The recorded experiments showed a cached result replayed after a link revocation on
  the BigQuery engines while the reference engine re-checked links; the service contract adopts the reference
  behaviour. Historical pins do not preserve revoked access.
- **Reject, do not downgrade.** A source whose policy needs a mapping the MVP does not support (mixed policy inside one
  publication, per-node or per-link rules, cross-boundary links) is refused at publish time with a named diagnostic.
  The MVP never silently widens or narrows access to make a publish succeed.
- **Named refusals, no content.** `NO_SEED`, `NO_ACCESS`, `WITHDRAWN`, `NOT_FOUND`, `PROFILE_UNSUPPORTED`,
  `BOUNDS_EXCEEDED`. The distinction between "nothing matched" and "you may not see it" is a documented product
  decision, not an accident of implementation.
- **Determinism.** The same publication, seed, traversal and requester scope return the same node and link set in the
  same order.
- **Context record.** Service-generated, retained for a stated horizon, readable later only with permission. It says
  what context was served to whom from which publication. It is not an execution receipt and attests nothing about
  any number computed afterwards.
- **Catalog binding.** The runtime reference held in the catalog entry is a pointer plus digest. Activation is
  refused on a digest mismatch. Withdrawal clears the reference. Who may activate, withdraw and delete is an explicit
  role in the contract, co-owned with Catalog.
- **Documented limits.** Bundle size, nodes and links per publication, hops and nodes per query, concurrent queries,
  retention horizon, supported regions.

## 3. Inside BigQuery, outside BigQuery

| Inside BigQuery (the feature) | Outside BigQuery (unchanged owners) |
| --- | --- |
| Managed compilation of an OKF source revision into the projection | OKF authors own the source bundle and its meaning; no format change |
| Reference validation, runtime-profile check, publish diagnostics | Knowledge Catalog owns discovery, the entry, and catalog governance |
| Immutable publication identity, atomic activation, withdrawal, deletion, retention | A separately owned Catalog runtime aspect points at the ready publication |
| Pin-or-refuse retrieval with bounded traversal | Analytics SDK supplies convenience bindings and telemetry, not the serving guarantee |
| Access enforcement on the read path, including cached results | Applications own faithful display of what they receive |
| The context record and its retention | Business approval of definitions stays with the business owner |
| Query diagnostics and documented limits | Calculation execution and result attestation: a separate proposed feature |

## 4. MVP versus later

**MVP (proposed first managed Preview).**

- One region.
- One team-owned bundle per publication, inside one access boundary.
- Explicit `publish`, explicit `activate`; no automatic refresh.
- Exact concept seed only.
- Bounded retrieval over the relational projection using SQL, on on-demand capacity.
- Named refusals and a documented retention horizon.
- Unsupported policy mappings rejected at publish time.
- Context record on every served or refused request.

**Later (proposed, each its own decision).**

- Managed refresh driven from Catalog changes, with the authored-aspect preservation rules made explicit.
- Broader policy mappings: per-node and per-link rules, mixed-policy publications, cross-boundary links, with
  enforcement on both endpoints of every disclosed link.
- SQL composition through the table function.
- An optional graph-traversal engine behind the same contract, on Enterprise or Enterprise Plus capacity.
- Natural-language seed under the requester's identity.
- Additional regions.

**Separate features, not later scope of this one.**

- Knowledge-Bound Jobs / verified job receipt: run an approved calculation version with its inputs and evidence bound
  to the result. Needs an enforceable fact-version manifest, a trust model for the receipt, protected evidence and a
  retention horizon longer than ordinary time travel. This is the feature the board-number story needs; the MVP above
  does not deliver it.
- Managed OKF import into BigQuery Graph as a standalone Graph-team extension.

## 5. Edition notes

- The MVP has no graph-query dependency. The SQL path runs on on-demand capacity; Enterprise and Enterprise Plus are
  also fine.
- A later graph engine needs Enterprise or Enterprise Plus reservations. The current allowlisted exception for some
  on-demand users is temporary and is not a launch basis. On-demand support for one graph-expansion function is not
  general on-demand graph querying.
- Graph-native semantic search and graph measures are Preview. They stay optional and outside the MVP; their existence
  establishes neither OKF compatibility nor authorization correctness.
- Fine-grained security has edition distinctions of its own. Do not infer universal Standard-edition support for the
  policy mappings the MVP relies on; the MVP rejects what it cannot enforce.

## 6. Ownership (recommendation, not commitment)

BigQuery product would own the feature and its operation. Knowledge Catalog would co-own the binding, activation and
withdrawal contract. The Analytics SDK would own adapters, conformance examples and telemetry. OKF authors keep the
source. These are recommended seats, not staffed ones.

## 7. What the recorded experiments are evidence for

Each row maps a part of the proposed contract to the spike code or SDK example that exercised the idea. Every row is
evidence that the part is buildable on existing BigQuery features. No row is the feature.

| Contract part | Exercised by | What it did and did not show |
| --- | --- | --- |
| Managed compilation, immutability, atomic activation | Spike compile and publish modules | Deterministic projection, readback validation, pointer switch, failure injection before the pointer. Local code, not a service. |
| Bounded retrieval, pin, refusals | Spike retrieve module with the relational engine | Governed two-hop retrieval, empty and ambiguous outcomes handled, fail-closed. Invented corpus; chosen seeds. |
| Current access on the read path | Spike authorization fixtures under an impersonated restricted identity | Five denial checks passed on the SQL path. Not inside a graph walk. Cached replay after a link revocation observed on the BigQuery engines. |
| Catalog binding as pointer plus digest | Spike catalog, seed and publication modules | Live catalog read resolved a retained publication; digest mismatch refused. Operator identity, relational path. |
| Consumer that releases only on a passing check | Spike chain module plus the SDK receipt example | Released on match, withheld on every substitution tested. Locally held key; same principal verifies and executes; example-only. Belongs to the follow-on feature. |
| Graph-traversal engine | Spike graph engine on Enterprise capacity | One connected run, chosen seed, single identity, success case only. Benchmark unfinished. |

## 8. Rules for these documents and the board pack

- **K1 — everything is PROPOSED.** Every new surface name carries the word on first use in each document and on the
  board pack.
- **K2 — no commitment language.** No sentence implies a staffed roadmap, a date, an edition promise or customer
  demand. "Proposed sequencing boundaries" is the strongest allowed phrasing.
- **K3 — sketches are contracts.** No code block or inline name is presented as supported syntax; each sketch carries
  the illustrative label.
- **K4 — evidence limits travel with the claim.** Any sentence that points at a recorded experiment carries its limit
  in the same or the next sentence, per the rows in section 7.
- **K5 — the receipt is the follow-on.** Nothing folds the verified job receipt or fact-version pinning into the MVP.
- **K6 — leadership tone on reader-facing surfaces.** The board pack and story document gain at most one linking
  sentence; no pull-request numbers, commit hashes, personal names or verdict labels in visible prose.

## Acceptance

- The three companion documents exist and the board pack's existing Knowledge Publications callout links to them.
- Grep over the three documents: every occurrence of `Knowledge Publications`, `Knowledge-Bound Jobs`, the table
  function name and each operation name sits in a document whose status line says PROPOSED; no "will ship",
  "committed", "roadmap" without a negation nearby.
- The board-pack relative-link test passes; the new relative link resolves on disk.
- Protected regions of the board pack unchanged: hero, later questions, capacity line, punchline, the ask, the bar
  paragraph, both SVGs, `styles.css`.
