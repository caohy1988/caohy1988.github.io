-- Beat 6 (v0): which session used which context_ref / publication.
-- Event-sourced only. Runs today against agent_events. The Phase B version is
-- attribution_two_key.sql: events matched on BOTH event-carried context_ref and
-- event-carried publication_id against the context_ref_resolution view (legacy ∪
-- Phase-A bindings), then publications joined by publication_id only; the 13
-- attested-computation rows (NULL publication) kept as a receipt-only band;
-- adapter-tape / legacy-Catalog evidence read from demo_evidence.
--
--   bq query --use_legacy_sql=false --project_id=test-project-0728-467323 < sessions_by_context_ref.sql
--
-- Result on 2026-09-03 (5 rows, 7 columns):
--   session_id  agent                  tool                          context_ref                   publication_id    verdict       n
--   04fa3d56…   okf_rfc_consume_agent  lookup_okf_context            okf:env-demo#a25e1c0ccbca     sha256:a25e1c0c…  NULL          1
--   1e6dfed7…   okf_rfc_observe_agent  okf_retrieve_context          okf:env-observe#674153c572f6  sha256:674153c5…  NULL          1
--   1e6dfed7…   okf_rfc_observe_agent  okf_run_attested_computation  okf:env-observe#674153c572f6  NULL              UNVERIFIABLE  1
--   f21ee192…   okf_rfc_observe_agent  okf_retrieve_context          okf:env-observe#674153c572f6  sha256:674153c5…  NULL          12
--   f21ee192…   okf_rfc_observe_agent  okf_run_attested_computation  okf:env-observe#674153c572f6  NULL              UNVERIFIABLE  12
SELECT
  session_id,
  agent,
  JSON_VALUE(content, '$.tool')                    AS tool,
  JSON_VALUE(content, '$.result.context_ref')      AS context_ref,
  COALESCE(JSON_VALUE(content, '$.result.publication_id'),
           JSON_VALUE(content, '$.result.okf.publication_id')) AS publication_id,
  JSON_VALUE(content, '$.result.okf.verdict')      AS verdict,
  COUNT(*)                                         AS n
FROM `test-project-0728-467323.okf_rfc_demo.agent_events`
WHERE event_type = 'TOOL_COMPLETED'
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY session_id, tool;
