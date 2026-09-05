# Spec — KC + OKF versus a BigQuery runtime

## Page contract

- Static HTML and page-local CSS at `/rfc/board-pack/`. No JavaScript, external assets, build dependencies or cloud calls.
- Preserve the full hero and arithmetic figure byte-for-byte. Keep Maya, Alder, 8:55 a.m., the five-minute deadline, $4 million decision, 118% and 96% in the hero.
- Preserve the short near-miss paragraph: the agent missed the accompanying cohort rule; Maya cannot trace why this agent could use the total-ARR asset; no execution receipt binds its query and result to the declared retention calculation. Do not turn this into another comparison or assert a permissions violation.
- Keep the invented $10m opening ARR, $9.6m same-customer closing ARR and erroneous $2.2m new-customer addition.
- One coherent technical section: three paired comparisons, one optional Technical design disclosure, one punchline, one Finance pilot ask. No stepper, nested disclosures or second comparison table.
- With details closed, target approximately 500–550 visible words and around two-and-a-half desktop viewports at 1280 × 720. These are editorial/geometry checks, not measured comprehension.
- Use neutral customer/runtime framing in the title, pilot eyebrow, RFC index link and local docs. Keep the product masthead and Why BigQuery thesis. Maya's Finance job title remains part of the story.

## Three paired comparisons

- Labels are **KC + OKF** and **+ BQ runtime**, repeated for each point so the pair stays clear on mobile. Side-by-side at desktop/tablet widths; each labeled pair stacks together on narrow screens.
- Briefly define Knowledge Catalog (KC) and Open Knowledge Format (OKF). KC discovers/governs; OKF authors the graph. Do not turn the comparison into another three-role essay.
- **Replayable context:** KC discovers, OKF authors, and the retriever assembles linked context. BigQuery hosts the OKF projection; pinned publication + explicit SQL/bounded walks select repeatable context. Name fixed query, parameters, fact versions, access scope and ordering. Story takeaway: same retention definition, cohort rule and declared computation.
- State next to retrieval that vector search can be deterministic and replayable context does not promise identical LLM answers. Similarity ranking does not itself pin linked context. Do not imply a publication freezes mutable facts or access policies.
- **Explainable access:** qualify the EntryGroup boundary as custom-entry access today. The right side joins identity ↔ policy ↔ projected assets, binds the requesting user/agent to the execution identity, enforces the retrieval path and records nodes returned to whom under which policy. Story takeaway: Maya can trace access to the total-ARR asset.
- State next to access that metadata needs enforcement, source permissions stay current, and metadata access does not grant file access. Do not imply universal KC EntryGroup-only IAM or automatic native per-node ACLs in BigQuery Graph.
- **Verifiable execution:** discovering the declaration does not prove execution. Run retention and validate the separate job ↔ context ↔ result receipt against the declared computation. A substituted query or missing evidence leaves the number unproven. Story takeaway: Maya can check whether the board number used the retention calculation.
- Keep retrieval selection, authorization and computation evidence distinct. A retrieval receipt does not prove the metric ran; a job ID alone does not validate the computation.

## Foldable technical design

- One native `<details>` / `<summary>` after the three comparisons and first-workload line, before the punchline. Closed by default; summary reads Technical design with an RFC proposal label. No scripted state or dependency.
- The body describes the proposed mechanism in three sections: bounded retrieval from Finance's definition to its linked cohort rule and computation declaration; authenticated requester binding and current policy enforcement; separate job ↔ context ↔ result validation against the declared calculation.
- State the retrieval inputs, explicit bounds, stable tie-breaking/schema/ordering, and returned-node evidence. Distinguish a retrieval receipt from evidence of computation. Record query/parameters, input versions, context and result with the computation job; a substituted query or missing evidence remains unproven.
- Explain authored-bundle authority and the initial node/edge projection. Publication pins never bypass current permissions; shared service accounts alone do not identify the requester. The integration remains proposed, including per-node enforcement and validated receipts.
- Match the existing brief's typography/colors. Provide a visible focus ring and a decorative disclosure indicator excluded from the accessible name. Native Enter/Space toggles must work. Print includes the design even when closed on screen; allow sensible page breaks within it.

## Honesty and ask

- Keep the hero's illustrative-scenario label, the runtime's proposed/RFC and unbuilt label, and all comparison notes, including the job-ID caveat and UNVERIFIABLE demo receipts. The page ends with the pilot ask; no footer or evidence deep-dive link is required.
- No ATTESTED, BQ_COMMITTED, Graph-over-OKF completion, implemented import or invented execution identifiers.
- Short first-workload line: land the OKF projection and version needed facts; an existing revenue warehouse is not required. Preserve authored-bundle authority.
- Extended punchline: **BigQuery turns the OKF graph into replayable context for agents—with explainable access and evidence that the declared computation ran.**
- One Finance pilot tests repeated retrieval, access boundaries and retention execution. Missing execution evidence leaves the number unproven. Do not impose illustrative Alder's 96% on real pilot data.
- Leave `/rfc/full-demo/` content and artifacts unchanged.

## Usability and delivery

- Semantic heading order, labeled comparison sections, visible keyboard focus, working skip link and valid local links.
- No horizontal overflow at 1280, 768, 375 or 320 px with details closed or open. Inspect desktop/mobile screenshots, readable contrast and print layout. Keep each comparison pair together in print.
- Move all page files to `rfc/board-pack/`. Update its canonical and the `rfc/index.html` href; keep Board-pack near-miss → as the visible label. `/rfc/bq-vp/index.html` is redirect-only: immediate meta refresh, new canonical and a usable fallback link. No other files remain in that legacy directory.
- Full-demo, including its audience-specific show notes, stays untouched unless an old brief href needs updating. Search the repo for stale path references and audience labels; references documenting the legacy redirect are intentional.
- Commit and push `feat/rfc-retention-runtime-details`; create a new PR against main. Save session and QA artifacts under `/tmp/okf-vp-details/`, report PR URL and HEAD, and do not merge. Opus + Kimi are the requested review gate.
