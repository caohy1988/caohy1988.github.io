-- Unresolved-reference backlog (spec §4): stub concepts with their referrers and counts, in scope.
SELECT missing_concept, COUNT(*) AS reference_count,
       ARRAY_AGG(STRUCT(referrer, relation, section) ORDER BY referrer, relation, section) AS wanted_by
FROM (
  SELECT g.missing_concept, g.referrer, g.relation, s.heading AS section
  FROM GRAPH_TABLE(`{ds}.okf_graph`
    MATCH (c:Node WHERE c.publication_id = @publication_id AND c.bundle_id = @bundle_id)
          -[l:Edge WHERE l.publication_id = @publication_id AND l.relation IN ('LINKS_TO', 'EXECUTED_BY', 'RESOLVES_TO')]->
          (ghost:Node WHERE ghost.publication_id = @publication_id AND ghost.kind = 'Concept' AND ghost.stub)
    COLUMNS (ghost.local_id AS missing_concept, c.local_id AS referrer, l.relation AS relation, l.section_id AS section_id)
  ) g
  LEFT JOIN `{ds}.nodes` s ON s.node_id = g.section_id AND s.publication_id = @publication_id
)
GROUP BY missing_concept
ORDER BY missing_concept
