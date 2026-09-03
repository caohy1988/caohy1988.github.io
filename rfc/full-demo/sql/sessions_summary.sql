-- Row and tool-call count per session in agent_events (read-only aggregate, no row pull).
-- Substantiates "212 rows, 4 sessions" on the page; the page pulls three of the four sessions.
--   bq query --use_legacy_sql=false --project_id=test-project-0728-467323 < sessions_summary.sql
SELECT session_id, agent,
       COUNT(*)                                  AS rows_in_table,
       COUNTIF(event_type = 'TOOL_COMPLETED')    AS tool_completed,
       MIN(timestamp)                            AS t0,
       MAX(timestamp)                            AS t1
FROM `test-project-0728-467323.okf_rfc_demo.agent_events`
GROUP BY 1, 2
ORDER BY t0;
