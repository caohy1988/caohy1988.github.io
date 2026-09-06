-- One property graph over the scoped node/edge tables. Uniform labels; kind/relation are properties.
-- Publication scoping is enforced by predicates in every query, never by the graph definition.
CREATE OR REPLACE PROPERTY GRAPH `{ds}.okf_graph`
  NODE TABLES (
    `{ds}.nodes` AS Node
      KEY (node_id)
      LABEL Node PROPERTIES (node_id, bundle_id, publication_id, kind, local_id, path, title, type, status,
                             stale_after, stale_after_ts, stub, actor_kind, heading, section_order, runtime)
  )
  EDGE TABLES (
    `{ds}.edges` AS Edge
      KEY (edge_id)
      SOURCE KEY (src_id) REFERENCES Node (node_id)
      DESTINATION KEY (dst_id) REFERENCES Node (node_id)
      LABEL Edge PROPERTIES (edge_id, bundle_id, publication_id, relation, declaration, section_id, authored_at, resolution, inferred)
  );
