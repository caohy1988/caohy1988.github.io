# Plan — connected end-to-end run

Implements `spec-connected-e2e.md`. Branch `rfc/connected-e2e` (worktree `~/caohy1988.github.io-connected-e2e`), new repo
`caohy1988/okf-connected-e2e` (branch `feat/connected-e2e`). Hermetic first, then one foreground live pass.

| Unit | Change | Verification |
|---|---|---|
| U0 | commit intent / spec / plan (this) | docs only |
| U1 | `chain.run_receipt(..., python=None)` — optional interpreter; `OKF_SDK_PYTHON` default | existing chain tests unchanged; new test: argv[0] honours `python` |
| U2 | `okf_bq_graph/catalog_access.py` — snapshot / grant / revoke / restore / observe / wait with injected transport | hermetic tests: pre-existing binding untouched, restore readback mismatch → UNVERIFIED, 403 → DENIED, 5xx → UNKNOWN, never ALLOWED without aspect data |
| U3 | `okf_bq_graph/connected.py` — facts read-back (`readback_manifest`), case functions, acceptance, verdict, record writer, CLI (`--hermetic` / `--live`) | hermetic end-to-end with fakes (FakeBigQuery-style store, mock Catalog with policy-controlled status, HermeticBroker-like live-shaped fake broker, fake SDK runner): E2E_CONNECTED; regressions: Catalog grant ignored on revocation → WRONG; payload tamper → WRONG; facts drift → approved REFUSED + WRONG; revocation not observed → NOT_REACHED; teardown readback mismatch → E2E_INCOMPLETE; e-mail never in record |
| U4 | full spike suite green (`env -u OKF_LIVE_ENGINE python3.13 -m pytest tests -q -p no:cacheprovider`) | suite output retained in PR body |
| U5 | new repo `okf-connected-e2e`: `pyproject.toml`, `okf_connected_e2e/{cli,agent,payload}.py`, tests, README | `pytest` green in the venv; `okf-e2e agent --hermetic` runs the agent tool against the hermetic runner without a model call |
| U6 | **live pass** (foreground, `test-project-0728-467323`): `okf-e2e agent --live` under asciinema, `DEMO_MODEL_ID=gemini-3.8-flash`, `OKF_SDK_PYTHON=/usr/local/opt/python@3.13/bin/python3.13` | record verdict read from `connected_live.json`; follow-up `jobs.get` audit over the retained inventory; Catalog policy and dataset ACLs read back equal to pre-run |
| U7 | evidence pack + `evidence/report-connected-e2e.md`; README section | scan for e-mails / `concept_id` / SQL text in the tool-payload transcript |
| U8 | asciinema → agg → ffmpeg `rfc/demo/okf-connected-e2e.mp4` (+ poster); `/rfc/demo/` section; `/rfc/` still-open copy | `tools/check_site_nav.mjs` (pre-existing `research/usage` failures excluded); visual check of both pages |
| U9 | PRs: site PR + code-repo PR; request Astra; merge only after Astra APPROVE | PR URLs in notes |
| U10 | vault notes (`Ship/builds/`, `Ship/rfc/`) + `/tmp/okf-connected-e2e/OPUS_CONNECTED_E2E_NOTES.md` | files exist |

## Stop rules

- If the Catalog grant is not observed within `--wait-s`, the run is E2E_INCOMPLETE; restore still runs; report honestly,
  do not re-label.
- If a live pass fails for an environment reason (propagation, quota), at most one more foreground attempt with a fresh
  run id; both records are retained.
- Budget: the run's SELECTs are capped at 100 MiB billed each (store) and the fact read-back reads seven tiny tables;
  expected spend is cents.
- Any restore UNVERIFIED stops the session's further live work until the ACL / policy is repaired by read-back.

## Honesty labels to carry everywhere

synthetic data / live GCP APIs · relational fallback engine (not GQL) · requester = restricted SA via impersonation ·
harness-granted catalogViewer on one entry group · SDK's own verifier with a requester-held key (no independent
attester) · denied-intermediate seed injected on the `_rls` copy · no cached replay under Catalog seeds · n = 1.
