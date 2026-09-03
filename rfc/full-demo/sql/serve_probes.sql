-- Beat 5 serve-path probes, SELECT ONLY, runnable today against the Phase A tables
-- created by sql/setup_runtime_tables.sql. Each marked statement is piped to
-- `bq query` as its own invocation (see attribution_two_key.sql for the pattern).
-- Honest status on 2026-09-03: no `okf-context sync` has run, so deployment_heads and
-- deployment_heads_history are EMPTY. Statement 3 therefore returns NO_HEAD for a bound
-- handle (FAIL_STALE needs a head to compare against) and FAIL_CLOSED for an unbound one.

-- STATEMENT 1 — deployment_heads for the demo deployment (expected today: 0 rows).
SELECT deployment_key, publication_id, snapshot_id, committed_at, sync_id
FROM `test-project-0728-467323.okf_rfc_demo.deployment_heads`
WHERE deployment_key = 'okf-rfc-demo';
-- END STATEMENT 1

-- STATEMENT 2 — "which publication was current at T" (expected today: 0 rows; the table
-- holds no revenue values even after Phase A; numerical comparison is future work).
SELECT deployment_key, publication_id, snapshot_id, committed_at, sync_id
FROM `test-project-0728-467323.okf_rfc_demo.deployment_heads_history`
WHERE deployment_key = 'okf-rfc-demo'
  AND committed_at <= TIMESTAMP('2026-06-30 23:59:59+00')
ORDER BY committed_at DESC
LIMIT 1;
-- END STATEMENT 2

-- STATEMENT 3 — pin-or-fail-stale resolution for three handles through the one view.
-- FAIL_CLOSED: no binding. NO_HEAD: bound, but deployment_heads has no head yet (sync not run).
-- OK / FAIL_STALE appear only once a head exists. AMBIGUOUS_LEGACY: one legacy handle, two publications.
WITH probes AS (
  SELECT 'okf:env-demo#a25e1c0ccbca' AS context_ref UNION ALL
  SELECT 'okf:env-observe#674153c572f6' UNION ALL
  SELECT 'okf:env-junk#deadbeef'
), resolved AS (
  SELECT p.context_ref,
         ARRAY_AGG(STRUCT(r.publication_id, r.binding_source) ORDER BY r.publication_id) AS bindings,
         COUNT(r.publication_id) AS n_bindings
  FROM probes p
  LEFT JOIN `test-project-0728-467323.okf_rfc_demo.context_ref_resolution` r USING (context_ref)
  GROUP BY p.context_ref
), head AS (
  SELECT publication_id AS head_publication_id
  FROM `test-project-0728-467323.okf_rfc_demo.deployment_heads`
  WHERE deployment_key = 'okf-rfc-demo'
)
SELECT
  resolved.context_ref,
  resolved.n_bindings,
  resolved.bindings,
  head.head_publication_id,
  CASE
    WHEN resolved.n_bindings = 0 THEN 'FAIL_CLOSED'
    WHEN resolved.n_bindings > 1 THEN 'AMBIGUOUS_LEGACY'
    WHEN head.head_publication_id IS NULL THEN 'NO_HEAD'
    WHEN resolved.bindings[OFFSET(0)].publication_id = head.head_publication_id THEN 'OK'
    ELSE 'FAIL_STALE'
  END AS resolution
FROM resolved
LEFT JOIN head ON TRUE
ORDER BY resolved.context_ref;
-- END STATEMENT 3

-- STATEMENT 4 — the seeded publications (three, all seeded_pre_phase_a; none written by sync).
SELECT publication_id, source, origin, snapshot_id, observation_id, committed_at, seeded_at
FROM `test-project-0728-467323.okf_rfc_demo.publications`
ORDER BY publication_id;
-- END STATEMENT 4

-- STATEMENT 5 — the resolution view as seeded (three legacy rows, zero phase_a rows).
SELECT context_ref, publication_id, binding_source, origin
FROM `test-project-0728-467323.okf_rfc_demo.context_ref_resolution`
ORDER BY binding_source, context_ref, publication_id;
-- END STATEMENT 5
