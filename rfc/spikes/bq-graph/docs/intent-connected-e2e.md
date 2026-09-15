# Intent — connected end-to-end run (RFC "What is still open")

Author: Claude Opus (`claude-opus-5`), Mac implementer seat, 2026-09-14. Reviewer: Astra (Codex); Kimi dual LGTM if available.
Slice chosen by the parent (Grok Bot) after Haiyuan skipped the overnight picker. Not glance #10, not Phase A sync CLI,
and not a re-record of the existing four-beat UI.

## The bar (quoted from `/rfc/` → What is still open)

> One run doing all of it at once: catalog discovery, pinned publication, governed retrieval, caller-delegated
> computation, result-bound receipt and enforcing consumer, with access and revocation checks holding throughout.

Secondary, not allowed to stall the receipt path: live read-back of the synthetic fact rows against their digest;
graph cells and full-path cost benchmarks.

## What already exists (credited, not rewritten)

Prior spike runs proved **parts** on invented Acme data, and **each run proved a different part**:

| Retained run | Proved | Did not prove |
|---|---|---|
| Catalog-seeded B1 `live-20260907T153329Z-21d91539` | live Dataplex read → pin → retained READY publication → payload guard → receipt → enforcing consumer | operator ADC on both legs; no restricted identity, no revocation |
| Catalog lifecycle B2 `b2-20260907t162636z-cd45` | pin held while head moved; FAIL_STALE / ASPECT_MISSING / payload INCONSISTENT withheld | operator only |
| Restricted chain `online_restricted-20260907T224831Z-f32d6d1b` | SA on both legs; hidden intermediate, unauthorized output, revocation before cached replay; identity BOUND over 29 jobs | hand-pinned fixture seed; no Catalog |
| GQL chain Run E (2026-09-08) | graph query on Enterprise released after declaration + receipt | success case only; hand seed; one operator |
| `authz_cases.json` | five second-principal negatives on plain SQL | not inside a chain |
| SQL baseline `sqlbase-20260909-065734-c50d0411` | ordinary SQL retrieval latency | not full path, not cost per answer |

**Gap:** no single retained run has combined Catalog discovery, pinned publication, governed retrieval,
caller-delegated computation, result-bound receipt and enforcing consumer, with access and revocation checks holding
throughout.

## What this slice does

One invocation, one `run_id` and one requester (`sa:okf-receipt-restricted`, via IAM impersonation) run five
cases in order against live GCP in `test-project-0728-467323`. The Catalog, BigQuery, IAM and receipt APIs are live;
the data is synthetic.

1. **connected-approved.** The requester's own Catalog read yields the pin, then the pinned publication, the trusted
   source and governed retrieval. After that come the payload guard and bind. The requester reads the facts back
   against their digest, and an authorization probe runs under the requester. The receipt executes under the requester,
   and the enforcing consumer releases on VERIFIED.
2. **connected-sql-substitution.** The same pin and requester. The SDK's executed-SQL swap is REJECTED and the consumer
   REFUSES.
3. **connected-denied-intermediate.** A row policy hides the intermediate concept. The seed is visible but no path
   returns, so nothing binds and the consumer REFUSES.
4. **connected-unauthorized-output.** The pin and declaration are visible, but the requester lacks read access on the
   computation's tables. Authorization is DENIED before execution, and the consumer REFUSES.
5. **connected-revocation.** The harness first proves access present, then revokes Catalog, graph and fact access and
   observes each denial. A fresh request is refused at Catalog discovery. A bypass with the retained pin is refused at
   the publication, retrieval and authorization stages. The stored receipt from case 1 is re-decided and REFUSED, and
   nothing executes after revocation.

Each Catalog binding, dataset grant and row-policy grantee the harness adds is snapshotted, restored and read back.
Every BigQuery job the run submits is read back and bound to the role that submitted it.

## Binding steering (Haiyuan, 2026-09-14 ~23:23 PT): acknowledged

1. **Real code, not only static HTML.** The connected runner extends the spike package
   (`okf_bq_graph/connected.py`). A new repository, `caohy1988/okf-connected-e2e`, holds the checked-in CLI and ADK
   agent that run it. The site links to both; `rfc/demo/live/run_okf_agent.py`'s `lookup_okf_context` stub is **not**
   the proof.
2. **Real demo on `test-project-0728-467323`.** Live Catalog, BigQuery and IAM checks. The copy labels the data
   (synthetic) separately from the APIs (live). Hermetic tests sit beside the live proof; the recorded run is live.
3. **Model: `gemini-3.8-flash`** through `DEMO_MODEL_ID` / ADK `Gemini(model=...)`. The CLI refuses older model
   families and prints the model id in its banner.
4. **Recorded e2e demo** of that live run (asciinema → mp4), wired into `/rfc/demo/`.
5. **Opus implements → Astra reviews → merge after APPROVE.** A site PR on `caohy1988.github.io` plus a code PR on the
   new repository.

## Non-goals and constraints

- No OKF v0.2 core change and no customer data. Alder stays unselected; fixtures are synthetic Acme only.
- No `concept_version_id`, query text or principal e-mail in agent tool payloads or public copy. Evidence masks
  publication identifiers as `<id:sha256[:8]>` and principals by alias.
- No GQL / Enterprise window. The engine is the relational `fallback`, and access and revocation are checked on that
  same path. Access inside a GQL traversal stays open and is named as such.
- No readiness claim and no pilot validation. Finance sponsorship stays a decision request.
- Never run `okf_bq_graph.assemble`. `git add` explicit paths only.

## Success

The run's verdict is `E2E_CONNECTED` only if all of the following hold:
- all five cases are MET;
- the requester identity is BOUND over every job;
- no job is unresolved;
- the Catalog IAM and broker teardowns are VERIFIED.

The `/rfc/` still-open copy then says exactly what this run proved and names the residual gaps. Anything short of
that is reported as `E2E_INCOMPLETE` / `E2E_BROKEN`, with the bar left open in tighter wording.
