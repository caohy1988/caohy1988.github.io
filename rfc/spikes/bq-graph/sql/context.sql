-- Governance context for a set of concept node_ids (GQL, single statement):
-- verifiers (trust derived at query time), provenance sources with resolution, replacement candidates.
SELECT concept_id, edge_id, relation, edge_declaration, edge_at, edge_resolution, edge_inferred,
       other_id, other_kind, other_local_id, other_title, other_type, other_status, other_actor_kind, other_stub
FROM GRAPH_TABLE(`{ds}.okf_graph`
  MATCH (c:Node WHERE c.node_id IN UNNEST(@concept_ids) AND c.publication_id = @publication_id)
        -[e:Edge WHERE e.publication_id = @publication_id
                   AND e.relation IN ('VERIFIED_BY', 'GENERATED_BY', 'DERIVES_FROM', 'LINKS_TO', 'HAS_SECTION')]->
        (o:Node WHERE o.publication_id = @publication_id)
  COLUMNS (c.node_id AS concept_id, e.edge_id AS edge_id, e.relation AS relation, e.declaration AS edge_declaration, e.authored_at AS edge_at,
           e.resolution AS edge_resolution, e.inferred AS edge_inferred,
           o.node_id AS other_id, o.kind AS other_kind, o.local_id AS other_local_id, o.title AS other_title,
           o.type AS other_type, o.status AS other_status, o.actor_kind AS other_actor_kind, o.stub AS other_stub)
)
ORDER BY concept_id, relation, other_id
