-- Phase A setup, run ONCE as okf-setup (impersonated by the bootstrap operator).
-- Owns every DDL statement and every seed MERGE for the demo. Never touches agent_events.
-- The reader file sql/attribution_two_key.sql contains SELECTs only.
--
-- bq has no impersonation flag (bq 2.1.28: "Unknown command line flag"). Impersonation is
-- set on gcloud (bq reads it): use an ISOLATED gcloud configuration so the default config
-- is never left pointing at a service account.
--
--   gcloud config configurations create okf-setup --no-activate
--   export CLOUDSDK_ACTIVE_CONFIG_NAME=okf-setup
--   gcloud config set account   <bootstrap-operator@…>            # the human Owner
--   gcloud config set project   test-project-0728-467323
--   gcloud config set auth/impersonate_service_account okf-setup@test-project-0728-467323.iam.gserviceaccount.com
--   gcloud auth print-identity-token --impersonate-service-account=okf-setup@test-project-0728-467323.iam.gserviceaccount.com >/dev/null   # proves the SA is the caller
--   bq query --use_legacy_sql=false --project_id=test-project-0728-467323 < setup_runtime_tables.sql
--   unset CLOUDSDK_ACTIVE_CONFIG_NAME                                # back to the default config
--   gcloud config configurations delete okf-setup --quiet             # after cleanup, when okf-setup is retired
--
-- The tape shows the configuration name and the impersonated account in the bq job's
-- user_email (INFORMATION_SCHEMA.JOBS) so the DDL is demonstrably run as okf-setup.
--
-- Not runnable until Phase A; committed so the schema and seed contract are concrete.

-- ---------- runtime tables (sync writer holds table-level dataEditor on these nine) ----------
CREATE TABLE IF NOT EXISTS `test-project-0728-467323.okf_rfc_demo.publications` (
  publication_id  STRING NOT NULL,          -- sha256:…  (PK by convention; owns NO context_ref column)
  snapshot_id     STRING,
  observation_id  STRING,
  committed_at    TIMESTAMP,
  source          STRING NOT NULL,          -- 'sync' | 'seeded_pre_phase_a'
  seeded_at       TIMESTAMP,                -- preserved when a seeded row is later matched by sync
  origin          STRING                    -- free text for seeded rows
);
CREATE TABLE IF NOT EXISTS `test-project-0728-467323.okf_rfc_demo.deployments` (
  deployment_key STRING NOT NULL, entry_group STRING, dataset STRING, created_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS `test-project-0728-467323.okf_rfc_demo.deployment_heads` (
  deployment_key STRING NOT NULL, publication_id STRING NOT NULL, snapshot_id STRING, committed_at TIMESTAMP, sync_id STRING);
CREATE TABLE IF NOT EXISTS `test-project-0728-467323.okf_rfc_demo.deployment_heads_history` (
  deployment_key STRING NOT NULL, publication_id STRING NOT NULL, snapshot_id STRING, committed_at TIMESTAMP, sync_id STRING);
CREATE TABLE IF NOT EXISTS `test-project-0728-467323.okf_rfc_demo.concept_versions` (
  concept_key STRING NOT NULL, concept_version_id STRING NOT NULL, snapshot_id STRING, title STRING, okf_type STRING, status STRING);
CREATE TABLE IF NOT EXISTS `test-project-0728-467323.okf_rfc_demo.snapshot_membership` (
  snapshot_id STRING NOT NULL, concept_version_id STRING NOT NULL, lifecycle STRING);
CREATE TABLE IF NOT EXISTS `test-project-0728-467323.okf_rfc_demo.relationship_assertions` (
  snapshot_id STRING NOT NULL, from_concept_key STRING, rel STRING, target_ref STRING, assertion_mode STRING);
CREATE TABLE IF NOT EXISTS `test-project-0728-467323.okf_rfc_demo.context_ref_bindings` (
  context_ref STRING NOT NULL,             -- unique by contract; append-only; never rebound (Phase A on)
  publication_id STRING NOT NULL,
  bound_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS `test-project-0728-467323.okf_rfc_demo.catalog_ownership` (
  deployment_key STRING NOT NULL, entry_name STRING NOT NULL, managed_by_sync_id STRING, stamped_at TIMESTAMP);

-- ---------- legacy + evidence tables (reader only; sync writer has NO grant on these) ----------
CREATE TABLE IF NOT EXISTS `test-project-0728-467323.okf_rfc_demo.legacy_context_ref_bindings` (
  context_ref STRING NOT NULL,             -- may repeat a handle: pre-Phase-A double binding on record
  publication_id STRING NOT NULL,
  origin STRING);
CREATE TABLE IF NOT EXISTS `test-project-0728-467323.okf_rfc_demo.demo_evidence` (
  source STRING NOT NULL, context_ref STRING, publication_id STRING, note STRING);

-- ---------- the one resolution view ----------
CREATE OR REPLACE VIEW `test-project-0728-467323.okf_rfc_demo.context_ref_resolution` AS
SELECT context_ref, publication_id, 'phase_a' AS binding_source, CAST(NULL AS STRING) AS origin
FROM `test-project-0728-467323.okf_rfc_demo.context_ref_bindings`
UNION ALL
SELECT context_ref, publication_id, 'legacy' AS binding_source, origin
FROM `test-project-0728-467323.okf_rfc_demo.legacy_context_ref_bindings`;

-- ---------- seeds (idempotent) ----------
-- publications: MERGE on publication_id. Re-running setup inserts nothing twice.
-- First-sync contract: the sync writer also MERGEs on publication_id; when it reproduces
-- 53bd1651… the seeded row is MATCHED (source -> 'sync', seeded_at kept), never duplicated,
-- and the head still advances because deployment_heads has no row for okf-rfc-demo yet.
MERGE `test-project-0728-467323.okf_rfc_demo.publications` t
USING (
  SELECT 'sha256:a25e1c0ccbcad270bf9e3b7a8f792167795381b6880bdc8a1ccde8df40ea52c5' AS publication_id,
         'consume session 04fa3d56 / legacy Catalog description' AS origin UNION ALL
  SELECT 'sha256:674153c572f6be57618a8d769a1a2b21a3e20d98406b3d1e58dd00027bc45905',
         'in-process pin, observe sessions f21ee192 / 1e6dfed7' UNION ALL
  SELECT 'sha256:53bd1651c43f69d53f591e4f91e3ccdda4640d8b36cb1dce1ac97328ffa39a77',
         'adapter CLI tape, SDK PR 474 @ 476d37dc'
) s
ON t.publication_id = s.publication_id
WHEN NOT MATCHED THEN
  INSERT (publication_id, source, seeded_at, origin)
  VALUES (s.publication_id, 'seeded_pre_phase_a', CURRENT_TIMESTAMP(), s.origin);

MERGE `test-project-0728-467323.okf_rfc_demo.legacy_context_ref_bindings` t
USING (
  SELECT 'okf:env-demo#a25e1c0ccbca'    AS context_ref, 'sha256:a25e1c0ccbcad270bf9e3b7a8f792167795381b6880bdc8a1ccde8df40ea52c5' AS publication_id, 'consume session 04fa3d56' AS origin UNION ALL
  SELECT 'okf:env-observe#674153c572f6',               'sha256:674153c572f6be57618a8d769a1a2b21a3e20d98406b3d1e58dd00027bc45905',               'observe sessions f21ee192 / 1e6dfed7' UNION ALL
  SELECT 'okf:env-observe#674153c572f6',               'sha256:53bd1651c43f69d53f591e4f91e3ccdda4640d8b36cb1dce1ac97328ffa39a77',               'adapter CLI tape (same handle, different publication)'
) s
ON t.context_ref = s.context_ref AND t.publication_id = s.publication_id
WHEN NOT MATCHED THEN INSERT (context_ref, publication_id, origin) VALUES (s.context_ref, s.publication_id, s.origin);

MERGE `test-project-0728-467323.okf_rfc_demo.demo_evidence` t
USING (
  SELECT 'adapter_tape_pr474_476d37dc' AS source, 'okf:env-observe#674153c572f6' AS context_ref,
         'sha256:53bd1651c43f69d53f591e4f91e3ccdda4640d8b36cb1dce1ac97328ffa39a77' AS publication_id,
         'same handle as observe sessions, different publication' AS note UNION ALL
  SELECT 'legacy_catalog_description', 'okf:env-demo#a25e1c0ccbca',
         'sha256:a25e1c0ccbcad270bf9e3b7a8f792167795381b6880bdc8a1ccde8df40ea52c5',
         'okf-derived-germany entrySource.description; entry has no aspect'
) s
ON t.source = s.source
WHEN NOT MATCHED THEN INSERT (source, context_ref, publication_id, note) VALUES (s.source, s.context_ref, s.publication_id, s.note);
