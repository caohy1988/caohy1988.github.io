# Intent — dedicated end-to-end demo page `/rfc/e2e/`

> **Superseded in part (2026-09-15, branch `rfc/e2e-viz`).** Haiyuan (~07:31 PT): the CLI-first demo was still too hard to understand. The page now follows [`VISUAL_PLAN.md`](VISUAL_PLAN.md): six reader-controlled steps (Publish → Catalog → Discover → Retrieve → Receipt → Revoke) with a synchronized panel, generated from the retained run files. The tape sits under Evidence.
>
> Still in force from this document: the problem, both planes, the Alder → Acme scenario, the honesty rules and the non-goals, including no new live run. The "page plus tape" five-minute outcome and acceptance (a)–(c) are replaced by VISUAL_PLAN's Verification Contract.

Owner ask (Haiyuan, 2026-09-15 ~06:51 PT, with 06:53 and 06:57 additions). Implementer: Claude Opus. Reviewer and overnight merge representative: Astra; second LGTM: Kimi.

## Problem

The full RFC path ran once live (`E2E_PUBLISH_CONNECTED`, run `kp-20260915t082018z-0387`, site PR #78). It is only visible in two places:

- a dense subsection at `/rfc/demo/#connected-e2e`, under an older BQAA four-beat demo that tells a different story;
- a report full of job ids.

A BigQuery or product reader who has not read the RFC cannot tell from either one:

- what broke;
- what Open Knowledge Format (OKF) and Knowledge Catalog do;
- what BigQuery Knowledge Publish adds;
- why the three together beat any one of them;
- what the run proved, and what is still open.

The tape is a raw 93-second terminal recording.

## Outcome wanted

One page, `/rfc/e2e/`, that is the canonical end-to-end demo and nothing else. A BigQuery/PM reader who spends five minutes on it (page plus tape) can explain the path back correctly.

1. **Both planes first-class.**
   - Plane A, OKF + Knowledge Catalog: authoring and discovery. The Catalog entry is a discovery projection that the requester reads; it is not the publish authority.
   - Plane B, BigQuery Knowledge Publish: an immutable projection is validated, marked `READY`, and the head pointer is switched atomically. BigQuery is the serving authority.
   - Then consume: discover → pin → governed retrieval → access and revocation → receipt → enforcing consumer.
2. **Why better (RFC-aligned thesis).** An explicit contrast of the ungoverned agent, OKF-only and Catalog-only paths against OKF + Knowledge Catalog + BigQuery Knowledge Publish, on the RFC's three outcomes:
   - replayable context;
   - explainable access;
   - verifiable execution.

   Today's failure modes are named: similarity without a pin, no publish authority, access not explained, no receipt.
3. **Five-minute human skim.**
   - Plain English first, with full product names.
   - Narrative arc: Problem → Author OKF → Publish in BigQuery → Discover in Knowledge Catalog → Agent consumes under access → Receipt verifies → Revoke → What we proved / still open.
   - Job ids, hashes and technical residuals sit in an Evidence disclosure.
4. **Tape a viewer can follow without the report.** Human setup, stage labels, and a closing verdict in plain words, carried by captions and a chapter list over the real recording.
5. **Real and honest.**
   - Retained live evidence on `test-project-0728-467323` only; nothing hermetic is labelled live.
   - Synthetic data, plain SQL, n = 1.
   - Residuals named; no readiness claim.

## Why a dedicated page, not a bigger `/rfc/demo/` section

- `/rfc/demo/` answers a different question: why a BQAA trace becomes derived OKF for the next agent. It uses four beats, is observer-only and attests nothing. Its JavaScript stepper and keyboard shortcuts belong to that story.
- Growing the connected section there would bury the canonical path under an unrelated narrative and push that page further past a skim.
- A dedicated page gets its own title, description and canonical URL, so it can be linked from `/rfc/` as "the demo".

`/rfc/demo/` stays as it is, apart from a one-line pointer.

## Scenario (Haiyuan ~07:07 PT steer)

The page uses the documented Acme gross-margin publish-connected path (`kp-20260915t082018z-0387`), not a new invented story.

It maps onto the `/rfc/` landing's framing:

- **Wrong number:** the Alder 118% slide on the landing. Here the analogue is the legacy product-cost-only gross-margin formula.
- **Right definition and its linked rule:** Gross Margin plus the margin standard and revenue policies it cites.
- **Access:** a restricted requester, with revocation.
- **Receipt:** the approved calculation is checked before release.

The landing already names this run under "The three as one path" and "The bar, shown once". The page says in its path lede that the retention slide is illustrative and that this run puts the same checks live on Acme.

The fixture is synthetic and labelled. Every call hit live GCP APIs on `test-project-0728-467323`.

## Non-goals

- No new live BigQuery run and no re-recording. The retained evidence and tape are reused; captions carry the story.
- No change to the code repo, the report, or the detailed RFC.
- No product-readiness claim. "BigQuery Knowledge Publish" names the publish step of the *proposed* BigQuery Knowledge Publications; this run is spike code.

## Acceptance (reviewer can fail P1 on any)

- (a) **Five-minute understandability.** Above the fold: the problem, what OKF + Knowledge Catalog do, what BigQuery Knowledge Publish does, what the run proved, and a still-open teaser plus the tape link. The rendered page is ≤ 5 minutes at 230 wpm.
- (b) **Why-better thesis.** It is clear, contrasted, and mapped to the three RFC outcomes. BigQuery is the serving authority; OKF + Knowledge Catalog do authoring and discovery.
- (c) **Quality and realness.**
  - Polished stage labels; no jargon wall above the Evidence fold.
  - Every claim traces to the retained report.
  - Job ids appear in Evidence.
  - Residuals are named.
