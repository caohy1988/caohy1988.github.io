# Customer stories — grounded in real traces in `test-project-0728-467323.okf_rfc_demo.agent_events`

Every story below cites a session id, the table, concept titles, and the exact failure mode a
Catalog-only deployment has. Nothing here is invented: the quotes are `content` fields read with
`bq query` on 2026-09-03; the Catalog entry was read with `gcloud dataplex entries lookup`.
"The customer" is the finance analytics team asking about Germany active-customer revenue, the
only narrative these traces contain. We do not dress it up as a named enterprise. Where the
BigQuery side is not implemented in Phase A/B, the story says `RFC text only`.

Shared facts:

| Item | Value |
|---|---|
| Table | `test-project-0728-467323.okf_rfc_demo.agent_events` (DAY partition on `timestamp`, clustered `event_type, agent, user_id`, 212 rows) |
| Sessions | `f21ee192-d989-4c38-894f-66b6b82eaf18` (180 rows, observe agent, 12 invocations) · `1e6dfed7-27ce-4c4d-b2e7-c45de7c241d1` (15) · `04fa3d56-f2f1-413e-8c2b-ec116835af84` (14, consume agent) · `a63c3e86-5897-40cc-bdf3-77bfcf750b12` (3, consume agent, no tool call) |
| Agents / model | `okf_rfc_observe_agent`, `okf_rfc_consume_agent`; `gemini-3.8-flash` |
| Tools observed | `okf_retrieve_context` (13 completions), `okf_run_attested_computation` (13), `lookup_okf_context` (1) |
| Concepts returned (rank order) | `Active-customer revenue` (Metric) · `Active-customer revenue by region and quarter` (Attested Computation) · `Active customer` (Business Concept) · `Revenue recognition eligibility` (Policy) · `Billing invoice lines` (BigQuery Table) · `CRM customers` (BigQuery Table); excluded: `Customer revenue (legacy)` (Metric, "superseded; out of force since 2026-06-20") |
| Catalog entry (legacy, prior experiment) | `projects/test-project-0728-467323/locations/us-central1/entryGroups/okf-rfc-demo/entries/okf-derived-germany`, type `okf-concept`, created 2026-09-02T23:03:22Z, **no aspects**, publication pin only inside `entrySource.description`. Not shipped OKF-in-KC; the shipped `okf-bundle` + `okf` types are set up in Phase A. |
| Publications in play | In `agent_events`: `a25e1c0c…` (consume session) and `674153c5…` (observe sessions). Outside `agent_events`: `53bd1651…` (adapter CLI tape) and the legacy Catalog description (`a25e1c0c…`). Three distinct publications across two kinds of source. |

---

## Story 1 — The agent that said "verified"

**Who.** A leadership-demo user (`user_id = leadership-demo`) asking the consume agent.
**Session.** `04fa3d56-f2f1-413e-8c2b-ec116835af84`, 2026-09-02 23:05:08–23:05:12 UTC.

**What happened.** The user asked: "What was active-customer revenue in Germany last quarter, and
can I trust the number? Use context_ref=okf:env-demo#a25e1c0ccbca." The agent called
`lookup_okf_context`, which returned exactly what a Catalog-shaped lookup can return:

```json
{"context_ref":"okf:env-demo#a25e1c0ccbca","ok":true,
 "publication_id":"sha256:a25e1c0ccbcad270bf9e3b7a8f792167795381b6880bdc8a1ccde8df40ea52c5",
 "note":"derived/demo bundle; not canonical authoring"}
```

The agent then answered: **"You can trust the number because it is verified and derived through
sanctioned computation bound in `okf:env-demo#a25e1c0ccbca`, and BQAA is observer-only."**
No computation ran. No verdict existed. The word "verified" was produced from an `ok: true`.

**Disclosure: this is an illustration, not a controlled comparison.** The two sessions differ in
more than one field. Their system prompts, read from the `LLM_REQUEST` rows:

- `04fa3d56` (consume agent): "If asked about Germany active-customer revenue, say the number is
  produced by the sanctioned computation bound in that context_ref, and that BQAA is observer-only."
  One tool, `lookup_okf_context`, whose contract has no verdict.
- `f21ee192` (observe agent): "Report the receipt verdict and verdict_reason verbatim; if the
  verdict is not ATTESTED, say plainly that the number is unproven." Two tools, including
  `okf_run_attested_computation`, whose contract has a verdict.

So the prompt, the tool set, and the question set all differ. What the pair shows is narrower and
still useful: **a contract with no verdict field permits an agent to say "verified", and a prompt
that leans on "sanctioned computation" language will do so.** It does not show that adding the
field alone would have changed the answer.

**KC-only failure mode.** The shipped `okf` aspect displays `runtime`, `computation`, `executor`,
`attester`; LookupContext does not render those fields at all; neither carries a `verdict`. An agent
reading Catalog sees the words "Attested Computation" and has nothing that says whether one ran.

**What BigQuery deployment changes.** In session `f21ee192`, `okf_run_attested_computation`
returned `verdict: UNVERIFIABLE`, `verdict_reason: "no-execution; observer-only demo, nothing
attested"`, `receipt_id: rcpt-observe-noexec`, and the agent called the number unproven in every
answer: 12 of 12 final answers contain the word "unproven" (semantic count, asserted by
`tools/check_full_demo.py`). The exact sentence **"No. The number is unproven."** appears exactly
once, in invocation 1; the other eleven phrase it differently ("The number is **unproven**", "the
comparison and underlying numbers are **unproven**"). The runtime contract makes the verdict a
field the agent must carry; the prompt then has something to report verbatim.

**Value proposition.** A finance answer carries its receipt or says it has none. The demo shows
both transcripts side by side with both system prompts (beat 3 vs beat 5).

---

## Story 2 — Twelve questions, one frozen context pack

**Who.** The same finance user, in a multi-turn session.
**Session.** `f21ee192-d989-4c38-894f-66b6b82eaf18`, 2026-09-03 04:08:33–04:10:11 UTC, 12 invocations.

**What happened.** The twelve real questions, in order:

1. What was active-customer revenue in Germany last quarter — and can I trust the number?
2. Same question for France last quarter — what does the receipt say?
3. Same for the United Kingdom last quarter.
4. How did Germany compare to the prior quarter?
5. What does the trust / receipt verdict actually mean for this number?
6. Why is the legacy customer-revenue metric excluded from current reporting?
7. What policy governs active-customer revenue recognition?
8. Which BigQuery tables back this metric?
9. What is the observed definition of an active customer?
10. Can I get a region roll-up for Germany, France, and the UK together?
11. If the number is unproven, what would make the receipt attested?
12. Which excluded items must I not use for last-quarter reporting?

All twelve `okf_retrieve_context` calls used `mode: current` and returned the identical pack:
`item_count: 6`, `excluded_count: 1`, `publication_id: 674153c5…`. Questions 4, 10, and 11 are
the ones a static pack cannot serve.

**KC-only failure mode.** Catalog has one mutable state per entry with `createTime` / `updateTime`.
"Which publication was current last quarter" is not a question it can hold. `parameters[]` is an
array field and is not server-side searchable. Nothing executes.

**What BigQuery deployment changes, in Phase B.** `deployment_heads_history (deployment_key,
publication_id, snapshot_id, committed_at, sync_id)` answers **which publication was current** at
the prior quarter's date, so the agent can retrieve in `historical` mode against that publication
and say which definition of the metric applied then. The declared `parameter_schema` on record
(`region STRING`, `quarter_start DATE`, `quarter_end DATE`) is shown as the contract the executor
would bind. Question 11's answer is the RFC's `ATTESTED` requirement list, and the agent recited it
correctly from the receipt fields.

**What stays future.** The history table holds no revenue values. A numerical prior-quarter
comparison (question 4) and a three-region roll-up (question 10) need an executor and an attester;
Phase B keeps every receipt `UNVERIFIABLE` / `no-execution`. Beat 5 labels both as
`RFC text only`.

**Value proposition.** The runtime turns a static pack into something that can be pinned to a
point in time and has a declared parameter contract; Catalog can only be searched. The numbers
come later, and the demo says so.

---

## Story 3 — One handle, three publications, and the legacy Catalog entry names the oldest

**Who.** Whoever audits the demo after the fact.
**Evidence.** All four sessions, the adapter tape, and the legacy Catalog entry.

**What happened.** Two kinds of evidence, kept in separate tables because only one is event data.

Event-sourced (`agent_events`, grouped by session, tool, `context_ref`, publication):

| session | tool | `context_ref` | publication carried by the event |
|---|---|---|---|
| `04fa3d56` | `lookup_okf_context` | `okf:env-demo#a25e1c0ccbca` | `a25e1c0c…` |
| `1e6dfed7` | `okf_retrieve_context` | `okf:env-observe#674153c572f6` | `674153c5…` (in-process pin) |
| `f21ee192` | `okf_retrieve_context` ×12 | `okf:env-observe#674153c572f6` | `674153c5…` |

Separately sourced (not `agent_events` rows):

| source | `context_ref` | publication | note |
|---|---|---|---|
| adapter CLI tape, PR 474 `476d37dc` | `okf:env-observe#674153c572f6` | `53bd1651…` | same handle as the observe sessions, different publication |
| legacy Catalog entry `okf-derived-germany`, `entrySource.description` | `okf:env-demo#a25e1c0ccbca` | `a25e1c0c…` | prose, no aspect |

So the agents saw two publications, the tape binds the same observe handle to a third, and the only
Catalog pin in the project names the oldest.

**KC-only failure mode.** Catalog cannot say which publication an agent read, whether two agents
read the same one, or whether the entry is stale relative to what is being served. After Phase A it
can display a stamped pin; a search predicate on it filters entries; it cannot compare the pin to a
head or refuse a stale request.

**What BigQuery deployment changes, and the attribution contract.** From Phase A on, a
`context_ref` is bound to exactly one `publication_id` and never rebound; a new publication mints a
new handle. The three pre-Phase-A publications are seeded into `publications` (keyed by
`publication_id` only; it owns no `context_ref` column) with a `seeded_pre_phase_a` source. The
legacy handles go into `legacy_context_ref_bindings`, and one view, `context_ref_resolution`,
unions legacy and Phase-A bindings. Beat 6 matches each event on **both** its event-carried
`context_ref` and its event-carried `publication_id` against that view, then joins `publications`
by `publication_id`. The 13 `okf_run_attested_computation` rows carry a `context_ref` but a NULL
publication; they are kept in a separate "receipt-only" band, attributed via the handle alone and
labelled as such, never merged into the publication rows. So the legacy double binding of
`okf:env-observe#674153c572f6` cannot duplicate or misattribute a row. The adapter-tape and
legacy-Catalog rows are seeded into `demo_evidence` with a source column and shown as a second table.

**Value proposition.** "Which version did the agent use" becomes a query, not an incident review,
and the demo is honest that the legacy handle was bound twice before the contract existed.

---

## Story 4 — The metric that died on 2026-06-20

**Who.** The finance user asking questions 6 and 12 above.
**Sessions.** `f21ee192` and `1e6dfed7`; 13 retrievals in total.

**What happened.** Every retrieval excluded `Customer revenue (legacy)` (Metric) with reason
"superseded; out of force since 2026-06-20". Question 12's answer on record: "You must not use
the following item: Customer revenue (legacy) … Reason: superseded; out of force since 2026-06-20."
The derived bundle on record carries the legacy metric marked deprecated so the next agent can see
why it is excluded, not just that it is absent.

**KC-only failure mode.** Generic `kcmd push` creates or patches and never deletes (`sync.ts`:
"TODO: Handle creates and deletes"). `status` and `stale_after` are search predicates; LookupContext
returns whatever is in the EntryGroup. A superseded metric stays discoverable and readable until an
operator deletes the entry by hand or removes the whole EntryGroup with `cleanup.ts`.

**What BigQuery deployment changes (Phase A/B).** Retirement is a property of the data: snapshot
membership, `current` / `historical` / `all` modes, "exclusion follows affirmation", and
delete-as-absence in the ledger so the syncer removes only what it owns. The legacy metric is still
in `historical` mode for audit and absent from `current`.

**Value proposition.** The dead metric cannot be picked by accident, and the reason it died is one
row away.

---

## Story 5 — Who may read the policy (`RFC text only` on the BigQuery side)

**Who.** The finance user asking question 7; the Catalog administrator granting `catalogViewer`.
**Session.** `f21ee192`, invocation `e-68d2e6b9-…`.

**What happened.** Retrieval returned `Revenue recognition eligibility` (Policy) at rank 4 and one
edge: `Active-customer revenue —governed_by→ Revenue recognition eligibility`. In the Catalog
projection that policy is one `okf-bundle` entry with its full body in the `overview` aspect,
sitting in the same EntryGroup as `Billing invoice lines` and `CRM customers`.

**KC-only structure (real, shown on beat 3).** The enforcement unit is the EntryGroup and IAM
cascades to every entry in it (KC blog: "IAM on the EntryGroup cascades to its Entries"). Anyone
with `roles/dataplex.catalogViewer` on `okf-rfc-demo` can read the policy body via `entries.get`.
OKF frontmatter is not an ACL, and the post's multi-team answer is one EntryGroup per team, which
does not separate concepts inside one bundle. This is structure, not an observed leak, and the page
says so.

**What the RFC proposes (`RFC text only`; not implemented in Phase A/B).** One security domain
per deployment with caller-delegated BigQuery authorization; a `policy_context_commitment` inside
the Context Envelope; mixed-policy bundles failing closed at projection time. The demo's runtime
reader holds `dataViewer` on the one dataset and nothing finer. The page and tape quote the RFC and
label the row accordingly; they do not show it working.

**Value proposition (as proposed).** Policy text would reach the agent through an authorized
runtime path rather than through whoever can browse the catalog. Today the honest claim is
narrower: the dataset and the EntryGroup are the boundary, and both are real.

---

## How the stories map to the beats

| Story | Beat where it lands | Evidence shown | Status |
|---|---|---|---|
| 1 Verified | 3 (Catalog stops) and 5 (BQ serves) | two transcripts with both system prompts, `04fa3d56` vs `f21ee192` | illustration, not causal |
| 2 Twelve questions | 1 (Ask) and 5 | the 12 `USER_MESSAGE_RECEIVED` rows; `deployment_heads_history` selection; `parameter_schema` | numbers `RFC text only` |
| 3 Three publications | 6 (Attribution) | event-sourced join on handle + publication; separately sourced adapter/Catalog rows | real after seeding |
| 4 Dead metric | 4, 5 | retrieve `current` result; ledger row for absence | real in Phase A/B |
| 5 Policy | 3 | EntryGroup IAM structure, `governed_by` edge | BQ side `RFC text only` |
