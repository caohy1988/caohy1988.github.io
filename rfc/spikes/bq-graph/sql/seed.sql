-- GA SQL VECTOR_SEARCH seed (spec §4). The base table is prefiltered to the authorized
-- (bundle, publication) scope BEFORE top-k, so a denied bundle can never enter or displace top-k.
-- Query embedding is produced by the same pinned model with task_type RETRIEVAL_QUERY.
WITH q AS (
  SELECT ml_generate_embedding_result AS embedding
  FROM ML.GENERATE_EMBEDDING(MODEL `{ds}.text_embedding`,
       (SELECT @query AS content), STRUCT(TRUE AS flatten_json_output, 'RETRIEVAL_QUERY' AS task_type))
)
SELECT base.node_id AS section_id, base.concept_id, base.heading, distance
FROM VECTOR_SEARCH(
  (SELECT node_id, concept_id, heading, embedding FROM `{ds}.section_vectors`
   WHERE bundle_id = @bundle_id AND publication_id = @publication_id),
  'embedding', (SELECT embedding FROM q), 'embedding',
  top_k => @top_k, distance_type => 'COSINE')
ORDER BY distance
