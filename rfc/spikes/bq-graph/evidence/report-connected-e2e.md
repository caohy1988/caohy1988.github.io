# Connected end-to-end run: report (2026-09-15)

**Result: `E2E_CONNECTED`** for run `e2e-20260915t070643z-9ddaf35f` (07:06:43–07:18:43 UTC, 12 min wall clock, most
of it stability waits).

It closes the RFC's still-open bar in one run on synthetic data. Every stage below ran against live GCP APIs in
`test-project-0728-467323`, and every access check held throughout. It is **not** readiness: one run, relational SQL
rather than BigQuery Graph, the SDK's own verifier, and no customer data. See "What this run does not establish".

- **Runner:** `okf_bq_graph.connected/0.1.0` at spike commit `9ace988`.
- **CLI and agent:** [`caohy1988/okf-connected-e2e`](https://github.com/caohy1988/okf-connected-e2e) `2dc3fd3`.
- **Model:** `gemini-3.8-flash` on Vertex AI (`global`).
- **Record:** [`connected-e2e/e2e-20260915t070643z-9ddaf35f/connected_live.json`](connected-e2e/e2e-20260915t070643z-9ddaf35f/connected_live.json).
- **Agent transcript:** [`agent_transcript.json`](connected-e2e/e2e-20260915t070643z-9ddaf35f/agent_transcript.json).
- **Terminal recording:** [`recording_transcript.txt`](connected-e2e/e2e-20260915t070643z-9ddaf35f/recording_transcript.txt),
  with its tape on `/rfc/demo/`.

## One requester, five cases

The requester is `sa:okf-receipt-restricted`, reached through IAM impersonation. It ran every execution leg:
- the Catalog read, confirmed by tokeninfo of the Catalog session's own token;
- every BigQuery read;
- the fact read-back;
- the receipt computation.

The operator only granted, revoked and restored access, and read jobs back.

| Case | Decision | Acceptance | What happened |
|---|---|---|---|
| `connected-approved` | **RELEASED** `[LIVE] Gross margin: $400.00 USD · VERIFIED` | MET | See the next section |
| `connected-sql-substitution` | REFUSED | MET | The same Catalog-seeded path bound and facts were admitted. The SDK then executed a substituted formula, so the receipt was REJECTED `sql_mismatch`, the CLI exited 2, and the consumer refused |
| `connected-denied-intermediate` | REFUSED | MET | The requester was added to the `_rls` row policies and saw 40 rows, 0 of them the hidden intermediate. The seed was visible but returned no path and no computation; the hidden id appeared on no surface and the CLI was never invoked |
| `connected-unauthorized-output` | REFUSED | MET | The read on the SDK fixture dataset was removed and stably observed DENIED (6/6 over 89 s, 0 flaps). The Catalog-seeded path still bound, but authorization was DENIED 7/7 at decision time and the CLI was never invoked |
| `connected-revocation` | REFUSED | MET | See "Access and revocation" |

## The approved path, stage by stage

1. **Catalog discovery.** Before the grant, the requester's `entries.get` returned HTTP 403. After the harness
   granted `roles/dataplex.catalogViewer` on the demo entry group, the first ALLOWED came at 83 s (9 polls), and it
   was stable 6/6 over 89 s. Discovery ran one `entries.list` page (11 entries, exactly one match), then
   `entries.get(view=ALL)`; the raw entry has SHA-256 `ad1115df…`. The pin was validated against trusted
   configuration.
2. **Pinned publication.** `pub_190192147fd7fd78` resolved to exactly one READY row and the exact seed row. The head
   was observed equal to the pin and not followed.
3. **Trusted source.** The clean pinned checkout (`31da799`) was compiled.
4. **Governed retrieval.** The relational `fallback` engine ran under the requester and reached the computation in
   one hop.
5. **Payload guard.** `CONSISTENT`: full retained rows, recomputed manifests, section hashes, paths, SQL and
   declaration bytes all matched the trusted compilation.
6. **Bind.** `BOUND` to the SDK receipt example's publication. File SHA-256 is `5e96ae11…` and
   `computation_digest` is `afe2afbd…`.
7. **Authorization.** ALLOWED under the requester, via a dry run on each of the 7 dependency tables.
8. **Fact read-back.** All 7 synthetic fact tables were read in full under the requester (14 rows) and
   canonicalised as `okf-fact-content/1`. They hash to the selected content digest `7264e7df…` (`admit_live` OK,
   expires about 2026-10-05). This closes the "live read-back of the synthetic fact rows against their digest" item,
   for this run.
9. **Caller-delegated computation.** `examples/okf_attested_computation/run.py --live` ran at SDK `6719eb5` (clean)
   under the requester's impersonated ADC. It produced job `okf_rcpt_e6fab1ac8adb4af45708cd7c_ba1740808c842003`, and
   the CLI wall time was 6.1 s.
10. **Result-bound receipt.** `rcpt-5b554572488b86d4c55f7577`, VERIFIED / MATCH. Its computation digest equals the
    bound digest, and its publication and context ref equal the bound ones. The diagnostic's SHA-256 is `598c34bc…`.
11. **Enforcing consumer.** RELEASED, because every binding held, authorization was ALLOWED and the facts were
    admitted.

## Access and revocation

- **Control.** Access was re-established and observed stable before revocation: Catalog, graph and authorization
  all ALLOWED 6/6 over 87 s.
- **Revocation.**
  - Catalog: the entry-group binding was removed, and the requester observed DENIED at the first poll.
  - Graph and fact access: the dataset reads were removed. The graph probe saw DENIED after 82 s and the SDK tables
    after 2 s. All three surfaces were then stable DENIED 6/6 over 89 s, with 0 flaps.
- **Fresh request.** Refused at Catalog discovery (`entries.list` HTTP 403). No publication, retrieval or bind stage
  ran.
- **Retained-pin bypass** (an agent that cached the pin skips Catalog):
  - the publication read failed with `403 Access Denied` (store ERROR);
  - retrieval returned `DENIED` and disclosed nothing;
  - authorization was DENIED 7/7.
- **Stored receipt.** The approved case's sealed receipt was re-decided under the post-revocation authorization and
  **REFUSED**, naming the authorization. It was never re-executed: **0** receipt launches after revocation.

## Identity, jobs, teardown

- **Identity: BOUND.** The operator's `jobs.get` read back all 58 jobs the run submitted, each against the role that
  submitted it:
  - 46 graph/store jobs under the requester: pin resolution 4, seed visibility 3, head 3, retrieval walk 5,
    context 4, nodes 4, declaration 3, payload rows 6, fact read-back 14;
  - 2 receipt jobs under the requester;
  - 1 requester row-count probe;
  - 9 row-policy DDL jobs under the operator.
  Journal entries unresolved: 0.
- **Catalog teardown: VERIFIED.** The entry group's IAM policy was written back to its snapshot and read back equal,
  with the requester not holding the role.
- **Broker teardown: VERIFIED.** ACLs on `okf_graph_spike_20260905`, `_rls` and `okf_receipt_spike_20260905` were
  restored and read back. The `_rls` row policies were restored, with the requester not among the grantees. The
  impersonated credential directory was removed.

## The agent

`okf-e2e agent --live` put the question to `gemini-3.8-flash`. The model called its one tool,
`governed_gross_margin({"period": "2026-01"})`, and that call performed this run. The tool payload is validated to
carry no e-mail, principal, scoped identifier, `pub_` id, `concept_version_id`, SQL, bundle path or local path.
It includes the answer only because the consumer released it **and** the run verdict was `E2E_CONNECTED`. The model
quoted the answer verbatim, and the leak check on its answer is empty.

## The first live attempt (retained, `E2E_BROKEN`)

Run `e2e-20260915t065449z-98e21004` (06:54:49 UTC) is kept as it ran:
[record](connected-e2e/e2e-20260915t065449z-98e21004/connected_live.json),
[recording](connected-e2e/e2e-20260915t065449z-98e21004/recording_transcript.txt).

- **What happened.** In `connected-unauthorized-output`, the removed SDK dataset read was observed DENIED 1 s after
  removal and ALLOWED 9 s later at decision time. The fact read-back also succeeded.
- **Grading.** The consumer still refused (this case launches no receipt), but acceptance graded the case WRONG, so
  the run was `E2E_BROKEN`. The other four cases were MET, identity was BOUND over 65 jobs, and both teardowns were
  VERIFIED.
- **Cause.** A single observation was taken as propagation.
- **Fix.** Commit `9ace988` requires six consecutive agreeing observations 15 s apart at every policy transition. A
  transition that never settles is `NOT_REACHED` and runs nothing, and ALLOWED after a stable DENIED is still `WRONG`.
  In the same change, the agent tool stopped handing over a released answer from a run that did not connect: run 1's
  agent had quoted the number without the broken verdict.

## What this run does not establish

- **Not BigQuery Graph.** Retrieval used the relational `fallback` engine. Access and revocation inside a GQL
  traversal on Enterprise capacity remain unproven, and job routing (on-demand vs reservation) is not asserted.
- **No independent attester.** The receipt is the SDK example's own verifier with a requester-held key. The
  computation ran on the SDK's synthetic fixture dataset, bound to the graph declaration by bytes.
- **Not every case starts at the Catalog.** `connected-denied-intermediate` used an injected legacy seed on the `_rls`
  governance copy of the pinned publication.
- **Harness-granted Catalog access.** The Catalog viewer binding was granted on one entry group by the harness.
  Catalog attests no principal; the caller is evidenced by tokeninfo and by 403 → 200 → 403.
- **No cached replay.** Catalog concept seeds disable the retrieval cache, so revocation was shown on a fresh request,
  a bypass and the stored receipt.
- **n = 1.** No latency, throughput or cost-per-answer measurement. The graph benchmark cells stay 0/9.
- **Synthetic Acme data only.** No customer cohort (Alder unselected). No pilot validation; Finance sponsorship remains
  a decision request.
- **Hygiene notes.**
  - `journal.jsonl` files are unredacted append-only logs. They carry local absolute paths but no e-mail or token.
  - Pre-existing, not changed here: the 2026-09-07 B1 raw `catalog/catalog_entry.json` contains an e-mail address in
    `managed_by_principal`.

## Reproduce

```bash
python3 -m okf_bq_graph.connected --hermetic                 # emulation, no cloud (tests: tests/test_connected.py)
OKF_SDK_PYTHON=/usr/local/opt/python@3.13/bin/python3.13 python3 -m okf_bq_graph.connected --live
# or, with the agent: https://github.com/caohy1988/okf-connected-e2e  →  okf-e2e agent --live
```
