# Intent — the full-version OKF demo (KC → BQ sync, KC gaps, real customer stories)

Status: plan only, from Haiyuan's ask of 2026-09-03. No syncer code, no re-recording, no
SDK change in this PR. Haiyuan merges; Codex + Kimi review on GitHub after the PR URL exists.

## Problem

The live demo at <https://caohy1988.github.io/rfc/demo/> proves one seam: a BQAA-observed agent
session becomes derived OKF that the next agent can look up by `context_ref`. It stops there. Three
questions a cold customer asks after watching it are still answered only in RFC prose:

1. **"My bundles are already in Knowledge Catalog via `kcmd push`. How do they get into BigQuery?"**
   Is that a built-in Dataplex / BigQuery service, or something I run? The answer this plan gives,
   once and consistently: an external CLI in v1, direction bundle → BigQuery commit → Catalog stamp;
   a Catalog → BigQuery import is not v1.
2. **"What does the BigQuery deployment give me that Catalog does not?"** The RFC lists it (§05, §06,
   §09) but nothing on screen fails in Catalog and then succeeds in BigQuery.
3. **"Who is this for, with what evidence?"** The value proposition today is a Cymbal finance
   fixture. We now have four real ADK sessions in `okf_rfc_demo.agent_events` and one real Catalog
   entry, and one of those sessions shows an agent overclaiming trust from a Catalog-shaped lookup.

## Why now

- Google's 2026-08-26 post ships the distribution half (`okf-bundle` EntryType, 13-field `okf`
  AspectType, `kcmd push`, `searchEntries`, `LookupContext`, EntryGroup IAM). It stops at push,
  search, lookup. The window to position the RFC as **the runtime profile on that distribution**,
  and to show the gap on a screen, is open now and narrows as readers assume Catalog is the runtime.
- SDK PR 474 merged (`4f54b5c`), so the adapter is on `main` and the observe/adapt/lookup path is
  reproducible by anyone. The next demo can build on that instead of a fixture.
- Live evidence exists today and is not going to get cleaner: session `f21ee192-…` (180 events, 12
  real questions, verdict honoured), session `04fa3d56-…` (14 events, trust overclaimed), and Catalog
  entry `okf-derived-germany` pinned to the oldest of three publications.

## Constraints (do not break)

- OKF v0.2 core unchanged. The profile stays optional. Shipped `okf-bundle` + `okf` types are the
  Catalog baseline; profile pins live on the profile-owned `okf-context-runtime` aspect (post-PR13).
- BQAA is observer-only. Traces are never a source of truth. Never emit `concept_version_id`, bundle
  paths, principal, query text, parameter values, or raw destination table names on agent payloads.
- The ask remains: hard-path agent context → derived OKF for discovery. **Not** trust-BQAA-as-truth.
  **Not** human-in-the-loop or sentiment promotion. The number stays unproven until an attester runs.
- Do not touch SDK PR 474, do not start the #435 clock, do not re-run the observe agent or pad the
  180-row export, do not re-record `okf-bqaa-cli.mp4` in this PR.
- Honesty labels on every pane: live GCP vs recorded vs stubbed vs `RFC text only`.
- The bridge runs under least-privilege identities scoped to one dataset and one EntryGroup
  (`spec.md` §1.3); nothing relies on a Dataplex built-in or an unannounced roadmap item.

## Non-goals

- Implementing the syncer. This PR specifies it; the build is Phase A of `plan.md`.
- A managed Dataplex or BigQuery feature. We say what one would need to be; we do not pretend it exists.
- A Catalog → BigQuery importer (`sync --from-catalog`). Future, lossy, out of v1.
- Fortune-500 stories. Every story cites a session id, a table, and concept titles we can query.
- A second finance narrative. Germany active-customer revenue stays the spine.

## Success

A visitor who has read only the Google post can, in under five minutes on `/rfc/full-demo/`, say
back: "sync is an external CLI I run (or schedule) that commits the bundle to BigQuery and stamps
the Catalog entry with the publication it committed; Catalog finds, BigQuery serves; here are three
things I saw shipped OKF-in-Catalog stop at and BigQuery answer with a SQL query, and here is what the
page marked as RFC text only." Every number on the page traces to
`test-project-0728-467323.okf_rfc_demo.agent_events` or to a Catalog entry we can `gcloud` today.
