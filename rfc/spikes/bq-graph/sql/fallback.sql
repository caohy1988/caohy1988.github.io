-- GA-only relational fallback (works on-demand, no reservation): the same two-hop walk with plain joins.
-- Labelled FALLBACK in evidence; it is not a BigQuery Graph result.
WITH e AS (
  SELECT src_id, dst_id FROM `{ds}.edges`
  WHERE publication_id = @publication_id AND relation = 'LINKS_TO'
),
c AS (SELECT node_id, status FROM `{ds}.nodes` WHERE node_id IN UNNEST(@seeds) AND publication_id = @publication_id),
hop1 AS (SELECT c.node_id AS seed, c.status AS seed_status, e.dst_id AS n1 FROM c JOIN e ON e.src_id = c.node_id),
hop2 AS (SELECT h.seed, h.seed_status, h.n1, e.dst_id AS n2 FROM hop1 h JOIN e ON e.src_id = h.n1),
cand AS (
  SELECT seed, n1 AS computation_id, [seed, n1] AS hop_ids, 1 AS concept_hops FROM hop1
  UNION ALL
  SELECT seed, n2, [seed, n1, n2], 2 FROM hop2 WHERE seed_status = 'deprecated'
)
SELECT cand.seed AS seed_id, cand.concept_hops, cand.hop_ids, ac.node_id AS computation_id, ac.path AS computation_path, ac.status AS computation_status
FROM cand JOIN `{ds}.nodes` ac ON ac.node_id = cand.computation_id
WHERE ac.publication_id = @publication_id AND ac.kind = 'Concept' AND ac.type = 'Attested Computation'
  AND NOT ac.stub AND COALESCE(ac.status, 'stable') <> 'deprecated'
ORDER BY seed_id, concept_hops, computation_id
