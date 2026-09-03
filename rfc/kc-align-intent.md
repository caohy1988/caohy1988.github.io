# Intent — align the RFC's Catalog leg with the shipped Knowledge Catalog OKF post

Status: accepted by Haiyuan (2026-09-03) from the source-grounded analysis in
`rfc/kc-blog-analysis.md`. Codex and Kimi review on the GitHub PR; Haiyuan merges.

## Problem

The published RFC at https://caohy1988.github.io/rfc/ (consolidated 2026-08-30)
proposes a Knowledge Catalog projection for OKF v0.2 bundles without citing the
Google Cloud post that shipped one four days earlier:

> "Using OKF with Knowledge Catalog to serve context for agents", Google Cloud
> blog, 2026-08-26, Firat Elbey and Sam McVeety.
> https://cloud.google.com/blog/products/data-analytics/scale-okf-bundles-across-an-organization-with-knowledge-catalog

That post and the sample it describes (`toolbox/mdcode/demo/okf/` in
`GoogleCloudPlatform/knowledge-catalog`) register an `okf-bundle` EntryType and a
13-field `okf` AspectType and push every markdown file in a bundle, including
`index.md` and `log.md`, as an Entry. The RFC instead names a new `okf-concept`
EntryType, a second `okf-computation` aspect that duplicates shipped fields 8 to
12, and two pin fields the shipped template does not have. It also states
(L440) that `push.ts` "already does" delete-only-what-you-created
reconciliation, which the kcmd source does not support, and it says the frozen
`knowledge-catalog/okf/` tree is targeted by nothing, when the post's own
quickstart pushes that tree by default.

## Why it matters

A reviewer at either repository will read the RFC as a parallel projection that
ignores the shipped one. The RFC's real contribution is everything the post is
silent on: BigQuery relational serving authority, the observation / snapshot /
publication identity chain, `deployment_heads` history, the Context Envelope,
attested execution with verdicts, and the `context_ref` seam for BigQuery Agent
Analytics. Those survive only if the Catalog leg is presented honestly as a
delta on the shipped mechanism.

## What this slice does

Land the 14 Section C edits and the Section E positioning paragraph from
`rfc/kc-blog-analysis.md` in `rfc/index.html`, with `rfc/kc-align-spec.md` as
the MUST list and `rfc/kc-align-plan.md` as the file-level plan.

## Constraints (do not break)

- No OKF v0.2 core change. The profile still reads only core keys and tolerated
  producer extensions.
- Do not merge or touch BigQuery Agent Analytics SDK PR 474, glance-mcp-report,
  or appealwright.
- github.io only: edits land in this repository's `rfc/` tree. No writes to
  `knowledge-catalog` or `open-knowledge-format`.
- Keep the RFC's voice and structure; do not restyle.
- Do not invent unverified claims. Anything on the analysis's UNVERIFIED list
  stays labeled as a post claim or as unverified where mentioned.
- Do not drop the RFC's unique contributions (BigQuery serving authority,
  identity chain, envelope, attestation, `context_ref`).
- Prefer not touching `rfc/demo/`; change it only where a string claims a
  Catalog type name that now contradicts the RFC.

## Out of scope

Implementing `toolbox/okf-context`, changing `okf-aspect.json` upstream,
re-running any live agent, new Catalog or BigQuery writes, and the Phase 0
closure items (`PROFILE.md`, `okf-rfc-roadmap.md`) that are not on this site.

## Success

The published RFC cites the post, adopts `okf-bundle`, describes the `okf`
aspect as the shipped 13 fields plus appended pin fields, states the reserved-file
rule for `index.md` and `log.md`, has a Phase 2 pin gate that reads the pin via
`entries.get` and enforces pin-or-fail-stale in the runtime, and no longer claims
that `push.ts` reconciles deletes.
