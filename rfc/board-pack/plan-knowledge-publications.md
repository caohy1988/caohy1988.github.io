# Plan — PROPOSED BigQuery Knowledge Publications: next engineering slices

Status: proposed sequencing only. No dates, no release train, no staffing claim. Each slice is small enough to review
on its own and is ordered by what it depends on. The intent is in `intent-knowledge-publications.md`; the surface and
contract in `spec-knowledge-publications.md`. Nothing below changes a spike measurement or claims the feature exists.

## What stays demo evidence and what would be product

| Today's artifact | Status now | Would become |
| --- | --- | --- |
| Spike compile, publish, retrieve, authorization, catalog, seed and publication modules | Feasibility evidence on invented Acme data; spike code in this repository | The reference behaviour a conformance suite checks the proposed contract against. Never the product. |
| SDK receipt example (broker, executor, verifier, consumer) | Example-only; locally held key; same principal executes and verifies | The consumer side of the separate verified-receipt feature. Not part of the publications MVP. |
| Catalog runtime aspect (`okf-context-runtime`), separate from the shipped authored `okf` aspect | Separately owned runtime pin read live once by the spike; the authored aspect is preserved and never used as runtime input | The Catalog side of the binding contract, co-owned with Catalog. |
| Ordinary-SQL retrieval measurements and the graph benchmark | Four retrieval cells measured on-demand; the two request-to-consumer cells unfilled because their runner is hermetic-only, never run live (their fact data is a selected synthetic fixture since 2026-09-09, not customer data); the five cost cells unmeasured; graph benchmark unfinished; thresholds proposed | Inputs to the operating limits the product would document. Not acceptance of any threshold. |
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

### KP-2 — one cache-contract conformance case across every engine

The spec says every node returned and every link that authorized its disclosure is re-checked at disclosure,
including when the result comes from a cache. Three facts to keep apart. Historically, a link-only revocation once
slipped through the BigQuery cached path, and later the reference engine's own re-check lagged behind the BigQuery
one; both were review findings on earlier slices. As implemented now, the BigQuery retrieval module re-checks the
disclosed node set and the authorizing link set together on every cached replay, and the hermetic link-only
revocation cases deny the replay. Still unproven: that behaviour under a real restricted identity live, and inside a
graph walk at all.

So KP-2 is conformance, not repair. Express the re-check-at-disclosure contract as one KP-1 case that runs unchanged
against the reference, relational and graph engines, covering node revocation, link-only revocation, a stale cache
entry from an older dependency version, and a seed that disables the cache; the output is a per-engine table of
passed, failed and not-runnable. Then, only on an explicit owner go, run the link-only revocation case live under the
restricted identity on the SQL path. Depends on KP-1. Graph-engine rows stay not-runnable until the graph gate opens.

### KP-3 — Catalog binding as pointer plus digest

Define the runtime reference the catalog entry would hold (publication id, projection digest, profile version,
activation state) as fields on the separately owned Catalog runtime aspect the spike already reads, leaving the
shipped authored `okf` aspect untouched as the spec requires, and make the spike's catalog-seeded resolution refuse on
a digest mismatch and on a withdrawn state. Write down who may activate, withdraw and delete, and what a republish preserves.
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

- **Verified job receipt / Knowledge-Bound Jobs.** Needs a fact-version manifest, a receipt trust model, protected
  evidence, canonical result encoding, replay rules and a retention horizon well past ordinary time travel. The
  recorded request-to-consumer cells stay unfilled because their runner is hermetic-only, never run live (their fact data is a selected synthetic
  fixture since 2026-09-09; selecting facts alone did not fill them); the five cost cells stay unmeasured. All of it is
  outside every slice above.
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

### Review fix pass (2026-09-09 PT, same branch)

- **KP-2 rebased on the implemented cache contract.** The plan had scheduled a node-only cache repair on the BigQuery
  engines. At this branch the spike's retrieval module already re-checks disclosed nodes and authorizing links
  together on cached replay, and the hermetic link-only revocation cases deny it; the earlier gaps were a historical
  link-only slip on the BigQuery path and a later reference-engine parity lag, both closed on earlier slices. KP-2 now
  defines cross-engine conformance for that contract and names the still-unproven live and graph-walk coverage. The
  matching evidence sentences in the intent and spec were corrected the same way.
- **Catalog binding location.** The plan's evidence row and KP-3 now name the separately owned Catalog runtime aspect
  the spike reads, and leave the shipped authored aspect untouched, matching the spec.
- **Consult attribution.** The intent now says the two analyses agreed the runtime is a pattern and not a feature,
  and chose different wedges; the board pack adopted the publications recommendation.
- **Consumer and cost qualifications.** Every retrieval summary in the three documents names the consumer blocker
  (no live runner, hermetic-only since 2026-09-09; the fact-data version was a second blocker until its 2026-09-09 synthetic selection) and keeps the five
  unmeasured cost cells beside it.
- **Checks.** Link, cache and restricted-chain tests: 71 passed offline, bytecode writes off. Stale-phrase and
  banned-token scans over the three documents clean. Reader-facing files unchanged since the first push: one line
  each in the page and story document against the base, stylesheet untouched. `git diff --check` clean.
