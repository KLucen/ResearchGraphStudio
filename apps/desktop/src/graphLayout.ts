import type { GraphData, GraphPosition } from "./graphTypes";

// Deterministic seeds only; the live simulation owns transient coordinates.
export function placeNodes(
  graph: GraphData,
  saved: GraphPosition[],
): GraphPosition[] {
  const known = new Map(
    saved
      .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y))
      .map((p) => [p.node_id, p]),
  );
  const points = graph.nodes.map(
    (node, i) =>
      known.get(node.id) ?? {
        node_id: node.id,
        x: Math.cos(i * 2.399) * (180 + i * 9),
        y: Math.sin(i * 2.399) * (180 + i * 9),
        pinned: false,
      },
  );
  return points.map((p) => ({ ...p }));
}
