# Walkthrough: the CLI tape (live-adapter proof)

The walkthrough media on `/rfc/demo/` is the recorded SDK CLI run:

- `okf-bqaa-cli.mp4` (terminal clip, embedded first on the page)
- `cli/okf-bqaa-cli.cast` (asciinema v2, same commands)
- `cli/okf-bqaa-cli.gif` (agg render of the cast)
- `cli/okf-bqaa-cli-transcript.txt` (plaintext, the durable proof)

Recorded 2026-09-02 PT from a checkout of
`GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK` PR 474 at HEAD
`476d37dc9d4210a335c2f77e78003f6a5ebe2878`, `examples/okf_bqaa_adapter`.
Stdlib only, no GCP, nothing re-run: the CLI reads the committed export of
observe session `f21ee192-d989-4c38-894f-66b6b82eaf18` (180 rows,
`okf_rfc_observe_agent`, `gemini-3.8-flash`). Label throughout: derived / demo,
observer-only, nothing attested. Do not merge PR 474.

`okf-bqaa-e2e.mp4` is a **prior fixture clip**, recorded before the observe run
and before the CLI path existed. It stays on the page only inside a collapsed
section labelled "prior fixture clip, not this run".

## What the tape shows

A ~24s pedagogical recut (H.264 1280×720). Poster (`okf-bqaa-cli-poster.png`) is
the successful lookup JSON, not an empty header and not FAIL_CLOSED. Junk-ref
exit 2 is labelled on screen as expected fail-closed, not a crash.

### 1 · OBSERVE

On-screen: `# 180 live BQAA agent_events from okf_rfc_observe_agent`, then a
one-liner against the committed export that prints `180 events` and session
`f21ee192-d989-4c38-894f-66b6b82eaf18`. Reader sees: this is a real trace.

### 2 · ADAPT (main beat)

`# one command projects that trace into a derived OKF bundle`, then
`python3 examples/okf_bqaa_adapter/run.py`. After SESSION / CONTEXT_REF /
PUBLICATION_ID: `# useful OKF: 8 stubs (metric, computation, policy, tables) + identity chain`,
`find …/out/bundle`, and the titles:

```
title: Active-customer revenue by region and quarter
title: Active customer
title: Active-customer revenue
…
```

plus the frontmatter of `metrics/active-customer-revenue.md`. Reader sees titles
they can use, not just hashes. On the page: beat 2 highlights the same pinned
values, labelled "pinned from CLI".

### 3 · LOOKUP (poster frame)

`# an agent later resolves context_ref to that publication`, then
`run.py --lookup 'okf:env-observe#674153c572f6'` → three-key JSON
(`context_ref`, `publication_id` `sha256:53bd1651…`, `label: derived/demo`),
exit 0. This frame is the video poster. On the page: beat 4, tape 1.

### 4 · FAIL-CLOSED (last, labelled)

`# junk refs fail closed (expected exit 2, not a crash)`, then
`run.py --lookup 'okf:env-junk#deadbeef'` → `FAIL_CLOSED` and
`# expected FAIL_CLOSED exit 2 — not a crashed demo`. On the page: beat 4, tape 2.

## Beats on the page, if presenting live

1. **Observe.** Live strip: agent `okf_rfc_observe_agent`, session `f21ee192-…`,
   180 events, table, model. Beat 1: histogram Σ 180, six sample rows, PR 474
   link for the full export, never-emit scan. Expand the collapsed prior consume
   experiment and Germany sections only to show that they are labelled.
2. **Adapt.** Beat 2: the transcript, then the 8-file bundle listing (CLI
   `out/bundle/`), then the identity chain and cross-checks, all ✓.
3. **Project.** Beat 3: identity chips; Catalog pane says no write on this path;
   BigQuery pane shows the live source table above the derived projection
   tables; seam note "one publication everywhere on this page ✓".
4. **Consume.** Beat 4: tape 1 resolves, tape 2 fails closed; type any other ref
   into "try a ref" and see it fail closed against the committed
   `mapping.json`; receipt tile `UNVERIFIABLE · rcpt-observe-noexec`.

## Before presenting

- `python3 rfc/demo/tools/check_cli_viewer.py` exits 0.
- Serve from the repo root: `python3 -m http.server 8000`, open
  `http://localhost:8000/rfc/demo/`; no console errors on any beat.
- Do not re-record. Do not run `--live`. Do not pad events.
