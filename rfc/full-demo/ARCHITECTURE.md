# Architecture — KC → BQ sync recommendation and the Observe → Adapt → Project → Consume flow

Recommendation: **hybrid (option C)**. Knowledge Catalog is the distribution and discovery
projection written by `kcmd push`. BigQuery is the serving authority. The sync leg is an
**external CLI** (`okf-context sync`) in v1, scheduled or CI-triggered in production, with an
honest path to a managed job later. Decisions and evidence are in `spec.md` §1.

## One diagram

```mermaid
flowchart LR
  subgraph OBSERVE["1 · Observe  (real: okf_rfc_demo.agent_events, 212 rows)"]
    A1["ADK agent<br/>okf_rfc_observe_agent<br/>gemini-3.8-flash"] -->|BQAA plugin| A2[("agent_events<br/>DAY partition<br/>clustered event_type, agent, user_id")]
  end

  subgraph ADAPT["2 · Adapt  (real: SDK examples/okf_bqaa_adapter, PR 474 merged 4f54b5c)"]
    A2 -->|"run.py (observer-only, one-way)"| B1["derived OKF bundle<br/>8 stubs · label derived/demo<br/>observation → snapshot → publication"]
  end

  subgraph PROJECT["3 · Project"]
    direction TB
    B1 -->|"kcmd push (shipped, Catalog side only)"| C1["Knowledge Catalog<br/>EntryGroup okf-rfc-demo<br/>okf-bundle entries + okf aspect<br/>overview bodies · IAM cascade"]
    B1 -->|"okf-context sync  ← NEW, external CLI"| C2[("BigQuery runtime<br/>publications · deployments<br/>deployment_heads(+history)<br/>concept_versions · membership<br/>catalog_ownership ledger")]
    C2 -->|"stamp after BQ_COMMITTED<br/>okf-context-runtime aspect<br/>{publication_id, published_snapshot_id, managed_by_*}"| C1
    C1 -.->|"sync --from-catalog<br/>(lossy fallback, labelled)"| C2
  end

  subgraph CONSUME["4 · Consume"]
    direction TB
    D1["Human / console<br/>searchEntries · LookupContext<br/>entries.get view=ALL"] --> C1
    D2["Next agent (ADK)<br/>okf_retrieve_context<br/>okf_run_attested_computation"] -->|"pin-or-fail-stale<br/>current / historical / all"| C2
    C2 -->|"Context Envelope<br/>context_ref only on results"| D2
    D2 -->|BQAA| A2
  end

  A2 -->|"SQL join on context_ref<br/>(beat 6)"| C2

  classDef tel fill:#EFE7FA,stroke:#7B5EA7,color:#2B1E45
  classDef cat fill:#E6F1FB,stroke:#3A6EA5,color:#16233B
  classDef run fill:#FDF1E1,stroke:#B4690E,color:#3B2A0E
  class A1,A2 tel
  class C1,D1 cat
  class C2,D2,B1 run
```

Colour key matches the RFC tokens: telemetry (purple), catalog (blue), runtime (amber).

## The sync leg, step by step

| Step | Actor | Writes | State after |
|---|---|---|---|
| validate · observe · snapshot | `okf-context sync` (local) | nothing | identities computed |
| plan | CLI | nothing | diff vs `deployment_heads` printed; absence = delete |
| commit | CLI → BigQuery | staged rows under `sync_id`, then `publications`, `deployment_heads`, `deployment_heads_history`, ledger | `BQ_COMMITTED` |
| stamp | CLI → Knowledge Catalog | `okf-context-runtime` aspect on owned entries; delete ledger-owned entries for removed concepts | `CATALOG_STAMPED` (or `CATALOG_PENDING` on partial failure; rerun completes without a new publication) |
| status | CLI | nothing | lag = publications committed − publications stamped |

Trigger options, in order of what the demo shows: manual CLI (demo), Cloud Run Job on Cloud
Scheduler polling the EntryGroup `updateTime` (production default), CI step after `kcmd push`.

## Why not a built-in service, and what "managed" would need

- BigQuery cannot read Catalog entries or custom aspects (no connector, no INFORMATION_SCHEMA view).
- Dataplex cannot materialize an EntryGroup into a dataset and does not own the profile's hashing
  rules, republish semantics, or `deployment_heads`.
- No cross-service transaction exists, so explicit `BQ_COMMITTED` / `CATALOG_STAMPED` states are
  required either way; a managed job would still expose them.
- A managed version would be: the same CLI packaged as a Dataplex-triggered job, with the
  `okf-context-runtime` aspect template owned by the service, and the ledger held in a
  service-managed dataset. If Dataplex metadata export jobs cover custom aspects, the read leg of
  `sync --from-catalog` could become a BigQuery load from that export; this is **UNVERIFIED** and
  not part of v1.

## What the two stores are each allowed to answer

| Question | Catalog | BigQuery |
|---|---|---|
| Does concept X exist, who owns it, what does it say? | yes | yes |
| Which publication is current for deployment D? | display only (stamped pin) | authoritative |
| What was current at time t? | no | `deployment_heads_history` |
| Is this `context_ref` stale? | no | pin-or-fail-stale |
| Was the number attested? | no | `verdict` + `receipt_id` |
| Which sessions used which publication? | no | SQL join to `agent_events` |
| Who may read the policy body? | EntryGroup IAM (coarse) | caller-delegated per deployment |
