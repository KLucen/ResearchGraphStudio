/** Small, UI-only graph contracts shared by the reusable LightGraph renderer. */
export type GraphNode = {
  id: string;
  /** LightGraph uses `type`; `kind` keeps the renderer compatible with old fixtures. */
  type?: string;
  kind?: string;
  label_zh?: string | null;
  label_en?: string | null;
  description_zh?: string | null;
  basis?: string;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  type?: string;
  relation?: string;
  label_zh?: string | null;
  is_dashed?: boolean;
  basis?: string;
};

export type GraphData = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  [key: string]: unknown;
};

export type GraphPosition = {
  node_id: string;
  x: number;
  y: number;
  pinned: boolean;
};

export type GraphLayout = {
  version?: number;
  zoom: number;
  pan_x: number;
  pan_y: number;
  positions?: GraphPosition[];
};

export function graphNodeKind(node: GraphNode): string {
  return node.type || node.kind || "UNKNOWN";
}

export function graphEdgeType(edge: GraphEdge): string {
  return edge.type || edge.relation || "RELATED_TO";
}
