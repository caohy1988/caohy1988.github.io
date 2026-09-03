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

### 1 · `python examples/okf_bqaa_adapter/run.py`

Watch for these stdout lines, in order:

```
LABEL derived/demo, observer-only, nothing attested
ADAPTER okf-bqaa-adapter:v0
TABLE test-project-0728-467323.okf_rfc_demo.agent_events
SESSION f21ee192-d989-4c38-894f-66b6b82eaf18
TRACE e-c7214361-4017-43d7-af4e-cddfe51b09a4
MODEL gemini-3.8-flash
CONTEXT_REF okf:env-observe#674153c572f6
RECEIPT UNVERIFIABLE rcpt-observe-noexec
OBSERVATION_ID sha256:85ea62a9…
SNAPSHOT_ID sha256:f18befd0…
PUBLICATION_ID sha256:53bd1651…
FILES 8
```

On the page: beat 2 shows this block with the pinned values highlighted; the
identity strip's derived row carries the same triple, labelled "pinned from CLI".

### 2 · `run.py --lookup 'okf:env-observe#674153c572f6'`

Prints a three-key JSON object: `context_ref`, `publication_id`
(`sha256:53bd1651…`), `label: derived/demo`. Exit 0. On the page: beat 4, tape 1.

### 3 · `run.py --lookup 'okf:env-junk#deadbeef'`

Prints `FAIL_CLOSED context_ref not bound in mapping (fail closed): …` on stderr
and exits 2. On the page: beat 4, tape 2.

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
