-- Never-emit scan over every agent-facing tool payload (TOOL_COMPLETED.content).
-- Expected: 0 hits for every key. Read-only; runs today as any dataViewer.
--   bq query --use_legacy_sql=false --project_id=test-project-0728-467323 < never_emit_scan.sql
WITH tool_rows AS (
  SELECT session_id, content
  FROM `test-project-0728-467323.okf_rfc_demo.agent_events`
  WHERE event_type = 'TOOL_COMPLETED'
), keys AS (
  SELECT k FROM UNNEST(['concept_version_id','bundle_path','source_path','principal',
                        'query_text','sql','parameter_values','destination_table']) AS k
)
SELECT
  keys.k                                                                 AS never_emit_key,
  COUNTIF(REGEXP_CONTAINS(TO_JSON_STRING(tool_rows.content), CONCAT('"', keys.k, '"')))  AS hits,
  (SELECT COUNT(*) FROM tool_rows)                                       AS tool_rows_scanned,
  (SELECT COUNTIF(JSON_VALUE(content, '$.result.context_ref') IS NOT NULL) FROM tool_rows) AS rows_with_context_ref
FROM keys CROSS JOIN tool_rows
GROUP BY keys.k
ORDER BY keys.k;
