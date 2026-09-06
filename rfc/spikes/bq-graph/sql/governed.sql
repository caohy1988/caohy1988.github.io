-- Governed two-hop walk in GQL (spec §4). Seed concept -> LINKS_TO{1,2} -> Attested Computation.
-- Hop 2 is only allowed when the anchor is deprecated (pinned Neo4j semantics).
-- Every element carries the publication predicate.
SELECT seed_id, seed, hop_concepts, concept_hops, computation_id, computation_path, computation_status, computation_runtime
FROM GRAPH_TABLE(`{ds}.okf_graph`
  MATCH p = (c:Node WHERE c.node_id IN UNNEST(@seeds) AND c.publication_id = @publication_id AND c.bundle_id = @bundle_id)
            -[e:Edge WHERE e.relation = 'LINKS_TO' AND e.publication_id = @publication_id]->{1,2}
            (ac:Node WHERE ac.publication_id = @publication_id AND ac.kind = 'Concept'
                       AND ac.type = 'Attested Computation' AND NOT ac.stub
                       AND COALESCE(ac.status, 'stable') <> 'deprecated')
  WHERE ARRAY_LENGTH(e) = 1 OR c.status = 'deprecated'
  COLUMNS (c.node_id AS seed_id, c.local_id AS seed,
           ARRAY(SELECT n.local_id FROM UNNEST(NODES(p)) AS n) AS hop_concepts,
           ARRAY_LENGTH(e) AS concept_hops,
           ac.node_id AS computation_id, ac.path AS computation_path,
           ac.status AS computation_status, ac.runtime AS computation_runtime)
)
ORDER BY seed_id, concept_hops, computation_id
