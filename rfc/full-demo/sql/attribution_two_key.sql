-- Beat 6 (Phase B): two-key attribution, SELECT ONLY.
-- Runs as okf-runtime-reader (dataset dataViewer + project jobUser). No DDL here:
-- tables, the context_ref_resolution view and the seed MERGEs live in the
-- setup-owned sql/setup_runtime_tables.sql, run once as okf-setup.
-- Runnable since 2026-09-03: setup_runtime_tables.sql was run once as the operator (Phase A re-runs
-- it as okf-setup). Both statements were captured as live/beat6_attribution.json and
-- live/beat6_demo_evidence.json with their bq job ids (attributed Σ 14, receipt_only Σ 13).
--
-- bq has no impersonation flag; impersonation is set on gcloud in an ISOLATED configuration
-- (same pattern as setup_runtime_tables.sql), and each marked SELECT is piped over stdin
-- as its own invocation. Never pass the extracted text as a positional argument: it begins
-- with "-- STATEMENT 1" and bq would parse it as a flag.
--
--   gcloud config configurations create okf-reader --no-activate
--   export CLOUDSDK_ACTIVE_CONFIG_NAME=okf-reader
--   gcloud config set account   <bootstrap-operator@…>
--   gcloud config set project   test-project-0728-467323
--   gcloud config set auth/impersonate_service_account okf-runtime-reader@test-project-0728-467323.iam.gserviceaccount.com
--   sed -n '/^-- STATEMENT 1 /,/^-- END STATEMENT 1/p' attribution_two_key.sql \
--     | bq query --use_legacy_sql=false --project_id=test-project-0728-467323 --format=prettyjson > beat6_attribution.json
--   sed -n '/^-- STATEMENT 2 /,/^-- END STATEMENT 2/p' attribution_two_key.sql \
--     | bq query --use_legacy_sql=false --project_id=test-project-0728-467323 --format=prettyjson > beat6_demo_evidence.json
--   unset CLOUDSDK_ACTIVE_CONFIG_NAME
--
-- Verified 2026-09-03: with this configuration bq attempts the impersonation (it fails
-- only because the SA does not exist yet), and each piped statement reaches query
-- validation. The tape shows user_email = okf-runtime-reader@… in INFORMATION_SCHEMA.JOBS.
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
