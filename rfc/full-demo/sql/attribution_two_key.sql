-- Beat 6 (Phase B): two-key attribution, SELECT ONLY.
-- Runs as okf-runtime-reader (dataset dataViewer + project jobUser). No DDL here:
-- tables, the context_ref_resolution view and the seed MERGEs live in the
-- setup-owned sql/setup_runtime_tables.sql, run once as okf-setup.
-- Not runnable until Phase A setup has run. Committed so the contract is concrete.
--
-- Two statements, run as TWO invocations so each result set is captured on its own:
--   bq query --use_legacy_sql=false --project_id=test-project-0728-467323 \
--     --impersonate_service_account=okf-runtime-reader@test-project-0728-467323.iam.gserviceaccount.com \
--     "$(sed -n '/^-- STATEMENT 1/,/^-- END STATEMENT 1/p' attribution_two_key.sql)"
--   … same with STATEMENT 2.
--
-- Relations read (all in okf_rfc_demo):
--   publications                 (publication_id, …, source)   -- owns NO context_ref column
--   context_ref_resolution       VIEW = context_ref_bindings (phase_a) ∪ legacy_context_ref_bindings (legacy)
--   demo_evidence                (source, context_ref, publication_id, note)
--   agent_events                 (BQAA, observer-only)
--
-- STATEMENT 1 — Table (a): event-sourced attribution.
-- Band 1: retrieve/lookup rows carry an event publication_id → two-key match, then publications by id.
-- Band 2: the 13 okf_run_attested_computation rows carry context_ref but NULL publication →
--         kept, attributed by handle only, labelled 'receipt_only'; never merged into band 1.
WITH ev AS (
  SELECT
    session_id,
    agent,
    JSON_VALUE(content, '$.tool')                                AS tool,
    JSON_VALUE(content, '$.result.context_ref')                  AS event_context_ref,
    COALESCE(JSON_VALUE(content, '$.result.publication_id'),
             JSON_VALUE(content, '$.result.okf.publication_id')) AS event_publication_id,
    JSON_VALUE(content, '$.result.okf.verdict')                  AS verdict
  FROM `test-project-0728-467323.okf_rfc_demo.agent_events`
  WHERE event_type = 'TOOL_COMPLETED'
)
SELECT
  'attributed' AS band,
  ev.session_id, ev.agent, ev.tool, ev.event_context_ref AS context_ref,
  p.publication_id, p.source AS publication_source, r.binding_source,
  COUNT(*) AS n
FROM ev
JOIN `test-project-0728-467323.okf_rfc_demo.context_ref_resolution` r
  ON r.context_ref = ev.event_context_ref
 AND r.publication_id = ev.event_publication_id            -- both keys
JOIN `test-project-0728-467323.okf_rfc_demo.publications` p
  ON p.publication_id = r.publication_id                   -- publications joined by id only
WHERE ev.event_publication_id IS NOT NULL
GROUP BY 1,2,3,4,5,6,7,8
UNION ALL
SELECT
  'receipt_only' AS band,
  ev.session_id, ev.agent, ev.tool, ev.event_context_ref,
  CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING),
  COUNT(*)
FROM ev
WHERE ev.event_publication_id IS NULL                      -- expected: 13 rows, verdict UNVERIFIABLE
GROUP BY 1,2,3,4,5
ORDER BY band, session_id, tool;
-- END STATEMENT 1

-- STATEMENT 2 — Table (b): separately sourced evidence (not agent_events rows).
-- Seeded by okf-setup in sql/setup_runtime_tables.sql.
SELECT source, context_ref, publication_id, note
FROM `test-project-0728-467323.okf_rfc_demo.demo_evidence`
ORDER BY source;
-- END STATEMENT 2
