# VP show notes · BigQuery is the runtime of Knowledge Catalog + OKF

Audience: VP of BigQuery. Target: 6½ minutes, with room for one question before 8 minutes.

## Set the stage

Open `/rfc/full-demo/` at the masthead. Keep the evidence drawers, capability matrix, and customer stories closed. Click **Start the six-beat show** after the opening. Use **Next**, the arrow keys, or **1–6** to move between beats. Each beat has a timed **Show note** and a compact evidence view; open the full evidence only when useful.

This is a static viewer of checked-in GCP captures from September 3, 2026. It does not issue live cloud queries. The existing agents were not re-run; `agent_events` received no DML. A **live** label identifies a captured GCP read or trace, not a production-ready runtime. Keep **seeded**, **recorded**, **stubbed**, **prior**, and **RFC text only** labels in view.

## Opening · 0:00–0:30

**Show:** The Germany question, then the two quotes in the VP strip.

**Say:** “Finance asks for active-customer revenue in Germany: can I trust the number? One agent read a Catalog-shaped lookup and said ‘verified’, although nothing computed the number. Another had a verdict field and said ‘No. The number is unproven.’ That is the opportunity: BigQuery is the runtime of Knowledge Catalog + OKF. Catalog makes context discoverable; the runtime would make its use accountable.”

**Boundary:** These are different prompts, tools, and questions, not a controlled comparison. Both paths used local tools. The verdict path used a stubbed attester with no execution.

## Beat 1 — Ask · 0:30–1:15

**Click:** Start the six-beat show, or **1**. Read the actual customer question and the two captured answers.

**Say:** “The customer needs permission to act on a number. There are two ways to go wrong: use an obsolete revenue metric, or treat a successful lookup as proof of computation. Twelve questions in the observe session keep testing that boundary. We will follow this one Germany question all the way through.”

**Evidence:** [Catalog-shaped session `04fa3d56`](live/session_04fa3d56.json); [observe session `f21ee192`](live/session_f21ee192.json). All 12 final answers in the latter contain “unproven”; only one contains the exact sentence quoted in the strip. Do not describe all 12 as identical answers.

**Transition:** “The evidence of that interaction is already in BigQuery.”

## Beat 2 — Observe · 1:15–2:00

**Click:** Next, or **2**. Point to 180 events and 24 tool completions.

**Say:** “The agent already did the work of finding context. BigQuery Agent Analytics captured the questions, tool results, and context references. We can inspect that work and use it as input to reusable context. BQAA observes what happened; it does not certify that the revenue is correct.”

**Boundary:** The [never-emit scan](live/never_emit_scan.json) found zero hits for eight specified keys in 27 tool payloads across four sessions. This is a scoped payload check, not a general security guarantee. The receipt tool remains a local stub.

**Transition:** “What happens when we make that context discoverable?”

## Beat 3 — Catalog path · 2:00–3:00

**Click:** **3**. Point to eight shipped entries, the 13-field template, and zero verdict fields. If asked, open **Evidence** for the Catalog responses and both prompts.

**Say:** “Catalog does useful work: it distributes the concepts and makes them discoverable. But this template has no computation verdict. The local Catalog-shaped tool returned ‘ok’, and its agent turned that into ‘verified’. The runtime opportunity is a contract that distinguishes finding context from proving an answer.”

**Add:** “IAM should also be explainable. The captured EntryGroup policy is real. The proposed deployment boundary still needs its own implementation and access checks.”

**Boundary:** The actual [Catalog lookup](live/lookup_context_shipped_metric.json) and the local agent transcript are separate evidence. Do not claim the agent called the shipped REST endpoint or that every Catalog client would give the same answer.

## Beat 4 — Sync · 3:00–3:45

**Click:** **4**. Trace the three boxes once: bundle → BigQuery publication → Catalog stamp.

**Say:** “This is the proposed bridge: an external CLI publishes the bundle to BigQuery, then stamps Catalog with the publication reference. The intended result is one publication that discovery can point to and serving can identify. A person or scheduler would run it.”

**Boundary:** Sync is not built; Phase A has not run. The [operator transcript](live/catalog_push_transcript.txt) records an adapter reproduction and Catalog push. The runtime rows are operator-seeded. Sync has not run. The proposed service accounts and grants are not in place; the negative IAM checks have not run.

**Transition:** “Here is what we can already inspect on the serving side.”

## Beat 5 — Serve · 3:45–5:00

**Click:** **5**. Point first to **UNVERIFIABLE**, then to the three resolution results and the empty head.

**Say:** “An honest ‘unproven’ is a useful answer. The receipt gives the agent a limit it must report. The BigQuery probes also expose uncertainty: an unbound handle fails closed, a double-bound legacy handle is ambiguous, and the bound handle has no head. The runtime we want should identify the publication, enforce its boundary, and return a computation receipt we can defend.”

**Boundary:** The [resolution probes](live/beat5_serve_stmt3.json) are real query results over seeded bindings. The receipt is from a local stub, with reason `no-execution; observer-only demo, nothing attested`. The demo pin is in-process. `deployment_heads` and its history are empty; pinning to a head and stale-pin rejection remain RFC text only. No revenue computation is proven here.

## Beat 6 — Attribution and close · 5:00–6:30

**Click:** **6**. Point to **14 attributed** and **13 receipt-only** separately.

**Say:** “BigQuery can answer which context a run used. Fourteen tool events match on both context reference and publication id through legacy bindings to seeded publications. Thirteen receipt events have no publication id; we keep that uncertainty visible. Attribution is evidence of context use, not proof that the revenue is right.”

**Close:** “The next step is one governed Germany deployment: a pinned publication, a computation receipt, access checks, and attribution. That gives us three outcomes to prove: trust you can defend, one pinned answer, and IAM you can explain.”

**Optional, within the final 30 seconds:** “BigQuery Graph could make the OKF chain easier to retrieve: observation → snapshot → publication. Here that is an RFC extension; the evidence is relational and adapter-based. There is no Graph execution or Graph job id to show.”

## Adjust to the room

- **Five minutes:** Keep every beat; take 30 seconds each on Ask, Observe, and Sync, 45 on Catalog, 60 on Serve, and 75 for the opening and close. Leave all evidence drawers closed.
- **Eight minutes:** Use the extra time for one evidence drawer: both prompts on beat 3, the receipt and probes on beat 5, or the two-key SQL on beat 6. The matrix and five customer stories are Q&A backup for this same finance scenario.
- **If asked whether this is shipped:** The Catalog projection and captures are real. The runtime has seeded tables and query evidence; sync, deployment IAM, serving from a head, and Graph remain proposed. Nothing is ATTESTED; no BQ_COMMITTED outcome or Phase A completion is claimed.
- **Terminology:** Use “Knowledge Catalog + OKF runtime”. The normative basis is OKF v0.2 core plus an optional runtime profile; “OKF 2.0” is not a published core change.
