// Thin browser adapters for renderer-neutral LaclauGPT GraphViewModel payloads.
// The semantic graph contract comes from Python/Analysis; renderer state and
// coordinates must never become canonical analytical meaning.

export const SCIENTIFIC_SAFEGUARDS = [
  "graph degree != nodal point",
  "visual centrality != hegemony",
  "community/cluster != ideological formation",
  "actor agreement != Laclauian equivalence",
  "negative/conflict edge != antagonistic frontier by itself",
  "semantic proximity != equivalence",
  "topic prevalence != hegemony",
  "two clusters != polarization without an explicit operationalization",
  "decorative layout distance != semantic distance",
];

export function cytoscapeElements(view) {
  return {
    nodes: view.nodes.map((node) => ({
      data: {
        id: node.id,
        label: node.label,
        node_type: node.node_type,
        review_status: node.review_status ?? null,
        uncertainty: node.uncertainty ?? null,
        evidence: node.evidence ?? [],
        external_ids: node.external_ids ?? {},
      },
    })),
    edges: view.edges.map((edge) => ({
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        edge_type: edge.edge_type,
        weight: edge.weight ?? 1,
        review_status: edge.review_status ?? null,
        uncertainty: edge.uncertainty ?? null,
        evidence: edge.evidence ?? [],
      },
    })),
  };
}

export function graphologyData(view) {
  return {
    nodes: view.nodes.map((node) => ({
      key: node.id,
      attributes: {
        label: node.label,
        node_type: node.node_type,
        review_status: node.review_status ?? null,
        uncertainty: node.uncertainty ?? null,
      },
    })),
    edges: view.edges.map((edge) => ({
      key: edge.id,
      source: edge.source,
      target: edge.target,
      attributes: {
        edge_type: edge.edge_type,
        weight: edge.weight ?? 1,
        review_status: edge.review_status ?? null,
        uncertainty: edge.uncertainty ?? null,
      },
    })),
  };
}

export function semanticMetadata(view) {
  return {
    projection_id: view.projection_id,
    graph_type: view.graph_type,
    node_semantics: view.node_semantics,
    edge_semantics: view.edge_semantics,
    projection_method: view.projection_method,
    weighting_method: view.weighting_method,
    temporal_scope: view.temporal_scope ?? {},
    filters: view.filters ?? {},
    producer: view.producer ?? {},
    provenance_id: view.provenance_id ?? null,
    safeguards: view.safeguards ?? SCIENTIFIC_SAFEGUARDS,
  };
}

export function evidenceForSelection(view, elementId) {
  const node = view.nodes.find((item) => item.id === elementId);
  if (node) return node.evidence ?? [];
  const edge = view.edges.find((item) => item.id === elementId);
  return edge?.evidence ?? [];
}
