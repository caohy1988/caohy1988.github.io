-- Impact analysis (spec §4): incoming dependency paths into @target over the pinned relation set,
-- 1..6 edges, ACYCLIC paths, distinct non-stub Concepts with minimum hops. Scoped at every step.
SELECT impacted, impacted_type, impacted_status, MIN(hops) AS hops,
       ANY_VALUE(path_locals HAVING MIN hops) AS path
FROM GRAPH_TABLE(`{ds}.okf_graph`
  MATCH p = ACYCLIC (up:Node WHERE up.publication_id = @publication_id AND up.kind = 'Concept' AND NOT up.stub)
        -[e:Edge WHERE e.publication_id = @publication_id
                   AND e.relation IN ('LINKS_TO', 'EXECUTED_BY', 'DERIVES_FROM', 'RESOLVES_TO', 'HAS_SECTION', 'MENTIONS')]->{1,6}
        (t:Node WHERE t.node_id = @target AND t.publication_id = @publication_id)
  WHERE up.node_id <> t.node_id
  COLUMNS (up.local_id AS impacted, up.type AS impacted_type, up.status AS impacted_status,
           ARRAY_LENGTH(e) AS hops, ARRAY(SELECT n.local_id FROM UNNEST(NODES(p)) AS n) AS path_locals)
)
GROUP BY impacted, impacted_type, impacted_status
ORDER BY hops, impacted
