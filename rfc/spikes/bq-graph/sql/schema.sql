-- Spike dataset: okf_graph_spike_20260905 (US). Tables are append-only per publication.
-- All rows are scoped by (bundle_id, publication_id); node_id/edge_id embed that scope.
CREATE TABLE IF NOT EXISTS `{ds}.nodes` (
  node_id STRING NOT NULL, bundle_id STRING NOT NULL, publication_id STRING NOT NULL,
  kind STRING NOT NULL, local_id STRING NOT NULL, path STRING, title STRING, type STRING,
  status STRING, stale_after STRING, stale_after_ts TIMESTAMP, stub BOOL NOT NULL,
  actor_kind STRING, heading STRING, section_order INT64, text STRING, text_sha256 STRING,
  resource STRING, description STRING, tags ARRAY<STRING>, runtime STRING, entry_date STRING,
  extra_frontmatter STRING, file_sha256 STRING, attrs STRING
) CLUSTER BY bundle_id, publication_id, kind;

CREATE TABLE IF NOT EXISTS `{ds}.edges` (
  edge_id STRING NOT NULL, bundle_id STRING NOT NULL, publication_id STRING NOT NULL,
  src_id STRING NOT NULL, dst_id STRING NOT NULL, relation STRING NOT NULL, declaration STRING NOT NULL,
  section_id STRING, authored_at STRING, resolution STRING, inferred BOOL NOT NULL, attrs STRING
) CLUSTER BY bundle_id, publication_id, relation;

CREATE TABLE IF NOT EXISTS `{ds}.section_vectors` (
  node_id STRING NOT NULL, bundle_id STRING NOT NULL, publication_id STRING NOT NULL,
  concept_id STRING NOT NULL, heading STRING, embedding_model STRING NOT NULL, embedding_model_version STRING,
  task_type STRING, text_sha256 STRING NOT NULL, dims INT64 NOT NULL, embedding ARRAY<FLOAT64>,
  created_at TIMESTAMP NOT NULL
) CLUSTER BY bundle_id, publication_id;

CREATE TABLE IF NOT EXISTS `{ds}.publications` (
  publication_id STRING NOT NULL, bundle_id STRING NOT NULL, source_pin STRING, compiler_version STRING,
  source_manifest_sha256 STRING, nodes_sha256 STRING, edges_sha256 STRING,
  node_count INT64, edge_count INT64, section_count INT64, vector_count INT64, embedding_model STRING,
  validation_status STRING NOT NULL, validation_reasons ARRAY<STRING>, created_at TIMESTAMP NOT NULL, ready_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS `{ds}.active_publication` (
  bundle_id STRING NOT NULL, publication_id STRING NOT NULL, switched_at TIMESTAMP NOT NULL, previous_publication_id STRING
);
