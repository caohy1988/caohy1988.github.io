# Spec — MUST edits to `rfc/index.html` from the Knowledge Catalog alignment

Source of truth: `rfc/kc-blog-analysis.md` (Sections C, D, E). Blog cited
throughout as **the post**: "Using OKF with Knowledge Catalog to serve context
for agents", Google Cloud blog, 2026-08-26,
https://cloud.google.com/blog/products/data-analytics/scale-okf-bundles-across-an-organization-with-knowledge-catalog

Line numbers refer to `rfc/index.html` at `cc38d7a` before edits.

## MUST edits (Section C, all 14 accepted)

1. **Cite the post and the sample as the shipped baseline.** Sources note
   (L193), §04 Catalog types (L451), §06 Catalog ownership (L657), §09 Phase 2
   (L733). Name the post with title, date, authors, URL, and name
   `toolbox/mdcode/demo/okf/` as the reference the Catalog leg builds on.

2. **Correct L440 (§04 Implementation).** Remove "as
   `toolbox/mdcode/demo/okf/push.ts` already does: Documents-Layout staging,
   custom-aspect passthrough, delete-only-what-you-created reconciliation."
   State what is verified: `push.ts` stages the bundle into Documents Layout with
   the signal on a `catalogEntry` passthrough and then executes the `kcmd`
   binary; generic `kcmd push` creates or patches and does not delete
   (`sync.ts` carries "TODO: Handle creates and deletes"); owned-prefix deletion
   exists only in the semantic-model deploy path.

3. **Adopt the shipped `okf-bundle` EntryType.** Replace `okf-concept` in the
   §03 diagram (L318), §04 (L451), §06 (L657), the phase table (L705), and Phase
   2 (L733). State that it is the shipped type (display name "OKF Document"),
   and that entry type is fixed at creation, so a sample-pushed EntryGroup is
   reusable rather than migrated. Decision: adopt, do not fork.

4. **Define the `okf` aspect as the shipped 13-field template plus appended
   fields.** `publication_id` and `published_snapshot_id` are top-level string
   fields appended with fresh indices 14 and 15 through the additive
   template-update path `setup.ts` already uses. They are never written into
   `extra`, which `pull.ts` round-trips into authored frontmatter. Decision:
   append 14/15, not a separate aspect.

5. **Reconcile `okf-computation` with shipped fields 8 to 12.** The authored §10
   contract (`runtime`, `parameters`, `computation`, `executor`, `attester`)
   stays on the shipped `okf` fields. `okf-computation` is runtime-derived only:
   `computation_version_id`, artifact hashes, attester identity, last verdict
   summary. §03 diagram (L320), §04 (L451), §06 (L657).

6. **Fix "nothing here targets it" (L193).** Keep "frozen snapshot" (the
   `okf/README.md` banner since 2026-08-21, PR #324). Add that the shipped
   sample and the post's quickstart push `knowledge-catalog/okf/bundles/acme_retail`
   by default (`okf.ts` `DEFAULT_BUNDLE`), that the two Acme copies differ today
   only in `attesters/sql_equality.py`, and that the compiler accepts a bundle
   root from either repository.

7. **Reserved-file rule for `index.md` and `log.md`.** §06 identity (after
   `concept_key`, L514), §06 snapshot membership, Phase 2 gate (L734). Reserved
   files (OKF §8, §9) are bundle content for `source_manifest_hash` but are not
   concepts: no `concept_key`, no version rows, no edges. Phase 2 projects index
   entries for parity with the Documents Layout, owns them in the ledger, and
   sets `parentEntry` the same way the Documents Layout does; `log.md` is
   projected only if the sample projects it, and never as a concept.

8. **Reword the Phase 2 pin gate (L734) and §05 pinning (L498).** The pin is
   read from the entry via `entries.get` with `view=ALL` (the post says
   LookupContext does not carry custom aspects; that is a post claim, unverified
   against Dataplex docs) and presented to the runtime, which serves that
   retained publication or fails stale. Search predicates on `publication_id`
   filter only and never enforce. `publication_id` stays a top-level scalar so it
   is searchable at all.

9. **Second adversary in the Phase 2 coexistence gate (L734) and the risk table
   (L764).** Alongside a `kcmd` semantic-model push, test a `kcmd`
   Documents-Layout push of the same bundle (the shipped sample) into the same
   EntryGroup: same path-derived entry names, no deletes from the sample side,
   both projections intact.

10. **Reword the Phase 2b `semantic-*` reuse gate (§04 L451, Phase 2 Out L735).**
    Cite actual kcmd behavior: semantic-model reconciliation deletes only under
    `<model>.entities.` / `<model>.metrics.` prefixes and the model anchor,
    `--force-remove` deletes whole models, and "An entry group holds exactly one
    semantic model." Reuse is allowed only if `okf-context` entries never sit
    under a model's owned prefixes and never in an EntryGroup that holds a
    semantic model.

11. **State the Catalog projection's enforcement unit (§06 Policy authority
    L586; L585).** On the Catalog side the unit is the EntryGroup (IAM cascade
    per the post) and the `overview` aspect exposes full bodies, so mixed-policy
    bundles fail closed at projection time too. Scope the #209 sub-concept
    enforcement claim to the BigQuery runtime.

12. **Per-entry write cost in the lag SLO (§05 KC_RECONCILING bullet, L497).**
    The post says every push writes every Entry and kcmd's spec says pushes are
    individual per entry, so lag scales with entry count; state the SLO per
    entry count.

13. **§04 agreements affected.** Scope: strengthened by the post (unchanged
    v0.2 bundles map to Catalog with zero new keys). Placement: add that the
    Catalog sample lives at `toolbox/mdcode/demo/okf/` beside the proposed
    `toolbox/okf-context/`; whether `open-knowledge-format` has Discussions
    enabled stays unverified. Implementation: the Catalog leg is a delta on a
    shipped mechanism (sample staging plus ownership ledger plus pins). Summary
    (L206) says the same in one clause.

14. **Dangling references (L438, L711).** `okf-rfc-roadmap.md` and
    `okf-phase0-mvp/PROFILE.md` are not on this site; mark them as off-site
    working files.

## MUST include: positioning paragraph (Section E)

Placed as a note in the header beside the Sources note, with the post linked.

> Google's 2026-08-26 post "Using OKF with Knowledge Catalog to serve context
> for agents" ships the org-scale distribution mechanism for OKF bundles: the
> `toolbox/mdcode/demo/okf` sample in `GoogleCloudPlatform/knowledge-catalog`
> registers an `okf-bundle` EntryType and a 13-field `okf` AspectType, and
> `kcmd push` publishes every markdown file in a bundle as a Knowledge Catalog
> Entry that inherits EntryGroup IAM and is reachable through `searchEntries`,
> `LookupContext`, and `entries.get`. This RFC does not replace that mechanism
> and does not change OKF v0.2; it is an optional runtime profile layered on it.
> It adopts the shipped Catalog types as the discovery projection, adds
> publication pins and an ownership ledger so a Catalog entry can name exactly
> which compiled state it describes, and puts everything the post leaves out
> into a BigQuery runtime: immutable observation/snapshot/publication history
> with per-deployment heads, authorized retrieval that returns a reproducible
> Context Envelope, attested execution of sanctioned computations with an
> independent attester and explicit verdicts, and an opaque `context_ref` so
> BigQuery Agent Analytics can observe use without becoming a source of truth.
> Where the post says a bundle is discoverable and governed, this profile says
> which version an agent used, whether the number it returned was attested, and
> how to reconstruct both.

## MUST keep: what stays uniquely the RFC's (Section D)

The post is silent on all of these; none may be weakened by the edits.

- BigQuery relational runtime as serving authority (the post's read path is
  Catalog only).
- Observation, snapshot, publication identity and republish semantics (the post
  has only `createTime`/`updateTime` and "every push writes every Entry").
- `deployment_heads` and `deployment_heads_history`.
- Context Envelope with opaque `envelope_id` and keyed policy-context
  commitment (LookupContext returns an unidentified YAML block).
- Attested Computation with an independent attester identity and
  complete-evidence verdicts (the post displays the contract, runs nothing).
- `context_ref` and the BQAA observer seam.
- Unresolved-link losslessness (`resolved:` / `unresolved:` namespaced targets).
- Assertion identity distinct from logical edge identity.
- Lifecycle-aware retrieval (`current` / `historical` / `all`).

Honest limit: the basic Catalog mapping (one entry per concept, `okf` aspect for
type and signal, `overview` for the body) is the post's, not the RFC's.

## MUST NOT

- Invent field names, API names, IAM roles, or repo paths beyond those verified
  in `rfc/kc-blog-analysis.md`.
- Assert any item on the analysis's UNVERIFIED list as fact.
- Change OKF v0.2 core, `rfc/demo/` data, or any other repository.

## Checks

- `grep -c okf-concept rfc/index.html` is 0.
- `rfc/index.html` contains the post URL, `okf-bundle`, "index 14", `index.md`,
  `log.md`, `entries.get`, and no longer contains
  "delete-only-what-you-created reconciliation" attributed to `push.ts`.
- `python3 rfc/demo/tools/check_cli_viewer.py` still exits 0 if the demo is
  touched at all.
