---
type: Attester
title: BigQuery job-metadata attester
description: Verifies an execution against BigQuery job metadata, read under an independent constrained identity.
status: stable
tags: [attester, bigquery]
---

# BigQuery job-metadata attester

**Phase 0 status: non-executable contract stub.** This document specifies the
checks a Phase 4 attester implementation must perform. No attester code
exists or has been executed in Phase 0; its hash enters
`computation_version_id` as the contract artifact, nothing more.

The attester runs under its **own constrained service identity**, never the caller's. It
re-reads the job **by job id** from BigQuery job metadata; nothing is taken
from the agent's text.

Checks, all required for `ATTESTED`:

1. The job's query text is byte-identical to the sanctioned template
   (compare literally; no re-rendering) and its SHA-256 equals the declared
   `executed_artifact_hash`.
2. The job's named parameters match the declared parameter list exactly —
   names, types, and count.
3. The job ran under the expected caller principal and wrote to the declared
   destination table.
4. Job metadata was readable and complete.

Any check that cannot be evaluated returns `UNVERIFIABLE`; a failed check
returns `REJECTED`. Missing evidence never degrades to success.

The attester holds job-metadata read only. It has no read access to table
data and no write access to any dataset.
