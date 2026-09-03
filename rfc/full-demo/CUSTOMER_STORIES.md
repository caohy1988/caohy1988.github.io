# Customer stories — grounded in real traces in `test-project-0728-467323.okf_rfc_demo.agent_events`

Every story below cites a session id, the table, concept titles, and the exact failure mode a
Catalog-only deployment has. Nothing here is invented: the quotes are `content` fields read with
`bq query` on 2026-09-03; the Catalog entry was read with `gcloud dataplex entries lookup`.
"The customer" is the finance analytics team asking about Germany active-customer revenue, the
only narrative these traces contain. We do not dress it up as a named enterprise.

Shared facts:

| Item | Value |
|---|---|
| Table | `test-project-0728-467323.okf_rfc_demo.agent_events` (DAY partition on `timestamp`, clustered `event_type, agent, user_id`, 212 rows) |
| Sessions | `f21ee192-d989-4c38-894f-66b6b82eaf18` (180 rows, observe agent, 12 invocations) · `1e6dfed7-27ce-4c4d-b2e7-c45de7c241d1` (15) · `04fa3d56-f2f1-413e-8c2b-ec116835af84` (14, consume agent) · `a63c3e86-5897-40cc-bdf3-77bfcf750b12` (3, consume agent, no tool call) |
| Agents / model | `okf_rfc_observe_agent`, `okf_rfc_consume_agent`; `gemini-3.8-flash` |
| Tools observed | `okf_retrieve_context` (13 completions), `okf_run_attested_computation` (13), `lookup_okf_context` (1) |
| Concepts returned (rank order) | `Active-customer revenue` (Metric) · `Active-customer revenue by region and quarter` (Attested Computation) · `Active customer` (Business Concept) · `Revenue recognition eligibility` (Policy) · `Billing invoice lines` (BigQuery Table) · `CRM customers` (BigQuery Table); excluded: `Customer revenue (legacy)` (Metric, "superseded; out of force since 2026-06-20") |
| Catalog entry | `projects/test-project-0728-467323/locations/us-central1/entryGroups/okf-rfc-demo/entries/okf-derived-germany`, type `okf-concept`, created 2026-09-02T23:03:22Z, **no aspects**, publication pin only inside `entrySource.description` |
| Publications in play | `a25e1c0c…` (Catalog entry + consume sessions) · `674153c5…` (in-process pin, observe sessions) · `53bd1651…` (adapter CLI on record) |

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

**KC-only failure mode.** The shipped `okf` aspect displays `runtime`, `computation`, `executor`,
`attester`; LookupContext returns a YAML block with none of them; neither has a `verdict` field.
An agent reading Catalog sees the words "Attested Computation" and has nothing that says whether
one ran. The entry we actually have has no aspect at all: the pin lives in the description string.

**What BigQuery deployment changes.** In session `f21ee192` the same question, with
`okf_run_attested_computation` returning `verdict: UNVERIFIABLE`, `verdict_reason: "no-execution;
observer-only demo, nothing attested"`, `receipt_id: rcpt-observe-noexec`, got this answer twelve
times out of twelve: **"No. The number is unproven."** The difference between the two sessions is
one field on the tool result, and that field only exists on the runtime side.

**Value proposition.** A finance answer carries its receipt or says it has none. The demo shows the
overclaim and the correction as two real transcripts side by side (beat 3 vs beat 5).

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
`item_count: 6`, `excluded_count: 1`, `publication_id: 674153c5…`. Question 4 (prior quarter),
question 10 (roll-up), and question 11 (what would attest it) are answerable only with history,
parameters, and execution.

**KC-only failure mode.** Catalog has one mutable state per entry with `createTime` / `updateTime`.
"What was current last quarter" is not a question it can hold. `parameters[]` is an array field and
is not server-side searchable. Nothing executes.

**What BigQuery deployment changes.** `deployment_heads_history (deployment_key, publication_id,
snapshot_id, committed_at, sync_id)` answers question 4 directly. The declared `parameter_schema`
on record (`region STRING`, `quarter_start DATE`, `quarter_end DATE`) is what
`run_attested_computation` binds for question 10. Question 11's answer is the RFC's `ATTESTED`
requirement list, and the agent recited it correctly from the receipt fields.

**Value proposition.** The runtime turns a static pack into something that can be pinned to a
point in time and executed with bound parameters; Catalog can only be searched.

---

## Story 3 — One handle, three publications, and the Catalog entry points at the oldest

**Who.** Whoever audits the demo after the fact.
**Evidence.** All four sessions plus the Catalog entry and the adapter output on record.

**What happened.** Group tool completions by session and `context_ref`:

| session | tool | `context_ref` | publication seen by the agent |
|---|---|---|---|
| `04fa3d56` | `lookup_okf_context` | `okf:env-demo#a25e1c0ccbca` | `a25e1c0c…` |
| `1e6dfed7` | `okf_retrieve_context` | `okf:env-observe#674153c572f6` | `674153c5…` (in-process pin) |
| `f21ee192` | `okf_retrieve_context` ×12 | `okf:env-observe#674153c572f6` | `674153c5…` |
| adapter CLI (PR 474 tape) | `run.py --lookup` | `okf:env-observe#674153c572f6` | `53bd1651…` |

The Catalog entry `okf-derived-germany` says `publication_id=sha256:a25e1c0c…` in its description
and has no aspect. So Catalog names the oldest publication, the observe sessions used a second,
and the CLI on record binds the same `context_ref` to a third.

**KC-only failure mode.** Catalog cannot say which publication an agent read, whether two agents
read the same one, or whether the entry is stale relative to what is being served. A search
predicate on the pin filters entries; it cannot refuse a stale request. And because this entry has
no aspect, there is nothing to predicate on at all.

**What BigQuery deployment changes.** `publications` plus the `context_ref` mapping table make the
binding a ledger with one row per publication. A request that presents `a25e1c0c…` to a runtime
whose head is `53bd1651…` fails stale. Beat 6 is the SQL that produces the table above from
`agent_events` joined to `publications`.

**Value proposition.** "Which version did the agent use" becomes a query, not an incident review.
The demo is honest that today the same `context_ref` is bound to two publications; the syncer's
job is to make that impossible going forward.

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

**What BigQuery deployment changes.** Retirement is a property of the data: snapshot membership,
`current` / `historical` / `all` modes, "exclusion follows affirmation", and delete-as-absence in
the ledger so the syncer removes only what it owns. The legacy metric is still in `historical`
mode for audit and absent from `current`.

**Value proposition.** The dead metric cannot be picked by accident, and the reason it died is one
row away.

---

## Story 5 — Who may read the policy

**Who.** The finance user asking question 7; the Catalog administrator granting `catalogViewer`.
**Session.** `f21ee192`, invocation `e-68d2e6b9-…`.

**What happened.** Retrieval returned `Revenue recognition eligibility` (Policy) at rank 4 and one
edge: `Active-customer revenue —governed_by→ Revenue recognition eligibility`. In the Catalog
projection that policy is one `okf-bundle` entry with its full body in the `overview` aspect,
sitting in the same EntryGroup as `Billing invoice lines` and `CRM customers`.

**KC-only failure mode.** The enforcement unit is the EntryGroup and IAM cascades to every entry
in it. Anyone with `roles/dataplex.catalogViewer` on `okf-rfc-demo` can read the policy body via
`entries.get`. OKF frontmatter is not an ACL, and the post's multi-team answer is one EntryGroup
per team, which does not separate concepts inside one bundle.

**What BigQuery deployment changes.** One security domain per deployment with caller-delegated
BigQuery authorization; the Context Envelope carries a `policy_context_commitment`; mixed-policy
bundles fail closed at projection time rather than leaking through `overview`.

**Value proposition.** Policy text reaches the agent through an authorized runtime path, not
through whoever can browse the catalog. This story is grounded in the real question and the real
Catalog structure, not in an observed leak; the page labels it "structure, not incident".

---

## How the stories map to the beats

| Story | Beat where it lands | Evidence shown |
|---|---|---|
| 1 Verified | 3 (Catalog dies) and 5 (BQ serves) | two transcripts, `04fa3d56` vs `f21ee192` |
| 2 Twelve questions | 1 (Ask) and 5 | the 12 `USER_MESSAGE_RECEIVED` rows; `deployment_heads_history` query |
| 3 Three publications | 6 (Join) | `agent_events` ⋈ `publications` |
| 4 Dead metric | 5 | retrieve `current` result; ledger row for absence |
| 5 Policy | 3 and 5 | `entries.get view=ALL` on the policy entry; envelope commitment |
