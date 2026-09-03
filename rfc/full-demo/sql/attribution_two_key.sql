-- Beat 6 (Phase B): two-key attribution that can be implemented.
-- NOT runnable today: the runtime tables are created by okf-context setup in
-- Phase A. Committed now so the contract is concrete. Runs as okf-runtime-reader.
--
-- Relations (all in okf_rfc_demo):
--   publications                 (publication_id PK, snapshot_id, observation_id, committed_at, source)
--                                 source ∈ {'sync','seeded_pre_phase_a'}; owns NO context_ref column
--   context_ref_bindings         (context_ref PK, publication_id, bound_at)    -- Phase A on; never rebound
--   legacy_context_ref_bindings  (context_ref, publication_id, origin)          -- pre-Phase-A handles; may repeat a context_ref
--   demo_evidence                (source, context_ref, publication_id, note)    -- adapter tape, legacy Catalog description
--
-- One view over both binding tables. Legacy rows may bind one handle to several
-- publications; that is why events are matched on BOTH keys below.
CREATE OR REPLACE VIEW `test-project-0728-467323.okf_rfc_demo.context_ref_resolution` AS
SELECT context_ref, publication_id, 'phase_a' AS binding_source, CAST(NULL AS STRING) AS origin
FROM `test-project-0728-467323.okf_rfc_demo.context_ref_bindings`
UNION ALL
SELECT context_ref, publication_id, 'legacy' AS binding_source, origin
FROM `test-project-0728-467323.okf_rfc_demo.legacy_context_ref_bindings`;

-- Table (a): event-sourced attribution.
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

-- Table (b): separately sourced evidence (not agent_events rows).
-- Seeded by okf-setup in Phase A:
--   ('adapter_tape_pr474_476d37dc', 'okf:env-observe#674153c572f6', 'sha256:53bd1651…', 'same handle as observe sessions, different publication')
--   ('legacy_catalog_description',  'okf:env-demo#a25e1c0ccbca',    'sha256:a25e1c0c…', 'okf-derived-germany entrySource.description; no aspect')
SELECT source, context_ref, publication_id, note
FROM `test-project-0728-467323.okf_rfc_demo.demo_evidence`
ORDER BY source;
