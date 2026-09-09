# Plan — PROPOSED BigQuery Knowledge Publications: next engineering slices

Status: proposed sequencing only. No dates, no release train, no staffing claim. Each slice is small enough to review
on its own and is ordered by what it depends on. The intent is in `intent-knowledge-publications.md`; the surface and
contract in `spec-knowledge-publications.md`. Nothing below changes a spike measurement or claims the feature exists.

## What stays demo evidence and what would be product

| Today's artifact | Status now | Would become |
| --- | --- | --- |
| Spike compile, publish, retrieve, authorization, catalog, seed and publication modules | Feasibility evidence on invented Acme data; spike code in this repository | The reference behaviour a conformance suite checks the proposed contract against. Never the product. |
| SDK receipt example (broker, executor, verifier, consumer) | Example-only; locally held key; same principal executes and verifies | The consumer side of the separate verified-receipt feature. Not part of the publications MVP. |
| Catalog `okf` aspect plus appended pin fields | Shipped aspect with proposed pin fields, read live once by the spike | The Catalog side of the binding contract, co-owned with Catalog. |
| Ordinary-SQL retrieval measurements and the graph benchmark | Four retrieval cells measured on-demand; graph benchmark unfinished; thresholds proposed | Inputs to the operating limits the product would document. Not acceptance of any threshold. |
| The connected end-to-end path | One chain, chosen seed, single identity, plain SQL; one graph run, success case only | Evidence that the surfaces are buildable. None of it is a surface. |
| The Finance retention pilot | Proposed, unsponsored | Validation data and demand evidence for the product owner. Not the product. |

## Slices

### KP-0 — write it down (this slice)

Intent, spec and plan under the board pack; one link from the existing Knowledge Publications callout. Documents only.
Done when the pull request is open and the link test passes.

### KP-1 — make the contract falsifiable

Turn the service contract of the spec into executable conformance checks that run hermetically against the spike's
reference engine and relational engine: immutability of the publication id, pin-or-refuse, each named refusal
returning no content, determinism of node and link order, and the context-record shape. Any check the spike cannot
pass today is recorded as a known gap, not hidden. Offline only; no cloud run. Output: a conformance module and a
gap list in the spike's docs folder. Claims allowed afterwards: "the contract is testable"; not "the contract is met".

### KP-2 — close the cached-replay gap on the relational engine

The spec says every link that authorized a disclosure is re-checked at disclosure, including from cache. The reference
engine does this; the BigQuery engines re-check nodes only, and a cached result was replayed after a link revocation.
Bring the relational engine to the reference behaviour, prove it with the existing hermetic revocation cases, and only
then, on an explicit owner go, re-run the restricted-identity denial cases live on the SQL path. Depends on KP-1 so
the check exists before the fix. No graph-engine work here.

### KP-3 — Catalog binding as pointer plus digest

Define the runtime reference the catalog entry would hold (publication id, projection digest, profile version,
activation state) as fields on the shipped aspect, and make the spike's catalog-seeded resolution refuse on a digest
mismatch and on a withdrawn state. Write down who may activate, withdraw and delete, and what a republish preserves.
Read-only against Catalog; no writes outside run-owned test resources; live steps only on an explicit owner go.
Output: a binding note beside the Catalog alignment documents and a hermetic test. This is the piece that turns
"Catalog discovers, BigQuery serves" into a hand-off rather than a hand-typed seed.

### KP-4 — reference adapter and conformance examples for the Analytics SDK

A thin binding from the SDK to the proposed publish and query contract, with telemetry, plus the conformance examples
from KP-1 packaged so a customer or a product team can run them. Explicitly an SDK deliverable, not a BigQuery launch,
and it lives in the SDK repository under that repository's own review. Depends on KP-1. The adapter must be removable:
if deleting it removes the capability, the capability was never in BigQuery, and the documents say so.

### KP-5 — the product ask package

One page for a BigQuery product owner and a Knowledge Catalog counterpart: the customer job, the proposed surface,
the service contract, in and out of BigQuery, the MVP boundary, edition notes, the evidence table with its limits, and
the two open decisions below. Drawn entirely from these three documents; no new claims. Output: a note under the RFC
tree that the board pack's ask can point to.

## Follow-on features, not MVP

- **Verified job receipt / Knowledge-Bound Jobs.** Needs a fact-version manifest that the consumer path is still
  blocked on, a receipt trust model, protected evidence, canonical result encoding, replay rules and a retention
  horizon well past ordinary time travel. The recorded consumer cells stay unmeasured until that selection is made,
  and it is outside every slice above.
- **Graph-traversal engine behind the contract.** Blocked on measuring access denial inside a graph walk under a
  restricted identity and on the unfinished graph benchmark. Enterprise or Enterprise Plus capacity; owner-gated.
- **Natural-language seed.** Blocked on an embedding model callable under the requester's own identity.
- **Managed refresh, broader policy mappings, SQL composition, more regions.** Each a separate decision after the MVP
  boundary is accepted by an owner.

## Open decisions for the owner (no dates attached)

1. Whether a BigQuery team will own the managed publication contract. If not, the honest fallback is an Analytics SDK
   integration with BigQuery as its execution backend, and the board pack's product ask changes wording accordingly.
2. Whether the customer need is reusable knowledge retrieval or checked calculations. If the latter, fund the
   verified-receipt feature directly and treat publications as its prerequisite rather than the wedge.
3. Whether the Finance pilot is sponsored, and by whom. It supplies validation and demand evidence; it does not
   decide 1 or 2 by itself.

## Verification for this slice (offline only)

- The three documents exist; every proposed name is marked on first use per document (grep).
- Board-pack relative links resolve on disk; the spike's board-pack link test passes.
- The one visible sentence added to the board pack and the story document carries no pull-request number, commit
  hash, personal name or verdict label.
- Protected regions of the board pack are byte-identical to the branch base: hero, later questions, capacity line,
  punchline, the ask, the bar paragraph, both SVGs, `styles.css`.
- `git diff --check` clean; tree clean; branch pushed; pull request open against `main`; not merged.

## Validation record

Filled in after implementation (bottom of this file).

## Validation record (2026-09-09 PT, `feat/knowledge-publications-intent` from `origin/main` `b10417e`)

- **Documents.** `intent-knowledge-publications.md` (about 1,200 words), `spec-knowledge-publications.md` (about
  2,150), `plan-knowledge-publications.md` (about 1,100). Each status line carries PROPOSED; every backtick reference
  between them resolves on disk.
- **Pointer edits.** One sentence appended to the Knowledge Publications callout paragraph in `index.html` (21 visible
  words, one relative link to the intent document); one sentence appended to the matching paragraph in `STORY.md`; a
  dated addendum at the end of `spec.md`. `git diff --numstat` against the base shows one changed line in each of
  `index.html` and `STORY.md`.
- **Protected regions.** The single changed line in `index.html` is the callout paragraph; the hero, later questions,
  capacity line, punchline, the ask, the bar paragraph, all three SVGs and `styles.css` are byte-identical to the
  base by construction of the diff.
- **Scans.** Visible prose of `index.html` and all three documents: no pull-request number, commit hash, personal
  name, verdict label, campaign identifier or state label. "Committed" and "roadmap" occur only inside negations.
- **Links.** `tests/test_board_pack_links.py` in the spike: 4 passed, offline, bytecode writes off.
- **Hygiene.** `git diff --check` clean. Documents only: no cloud run, no spike measurement touched, no merge.
- **Not done.** No three-engine browser pass; the change is one linked sentence in an existing paragraph and the
  closed-state word count has no maintained ceiling (see the Pass 2 record).
