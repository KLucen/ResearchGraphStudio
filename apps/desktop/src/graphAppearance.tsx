import "./graphAppearance.css";

export type VisualKind =
  | "RESEARCH_QUESTION"
  | "CONCEPT"
  | "METHOD"
  | "CONTRIBUTION"
  | "FINDING"
  | "UNKNOWN";

/** One palette for the rendered nodes, filters, details and explanatory legend. */
export const graphNodeKinds: Record<
  VisualKind,
  { label: string; color: string }
> = {
  RESEARCH_QUESTION: { label: "研究问题", color: "#ad7c91" },
  CONCEPT: { label: "概念", color: "#927fba" },
  METHOD: { label: "方法", color: "#508e80" },
  CONTRIBUTION: { label: "贡献", color: "#b38e54" },
  FINDING: { label: "结果", color: "#ba8265" },
  UNKNOWN: { label: "其他", color: "#74847b" },
};

export const graphKindLabels = Object.fromEntries(
  Object.entries(graphNodeKinds).map(([kind, { label }]) => [kind, label]),
) as Record<VisualKind, string>;

const unknownAppearance = { label: "其他", color: "#74847b" };

export function getGraphAppearance(kind: string) {
  return Object.hasOwn(graphNodeKinds, kind)
    ? graphNodeKinds[kind as VisualKind]
    : unknownAppearance;
}

/** This is an explanation, deliberately independent from graph filtering. */
export function GraphLegend() {
  return (
    <aside className="graph-legend" aria-label="图谱节点类型说明">
      <h3>节点类型</h3>
      <ul>
        {Object.entries(graphNodeKinds)
          .filter(([kind]) => kind !== "UNKNOWN")
          .map(([kind, appearance]) => (
            <li key={kind} data-kind={kind}>
              <span
                className="graph-legend-swatch"
                style={{ backgroundColor: appearance.color }}
                aria-hidden="true"
              />
              <span>{appearance.label}</span>
            </li>
          ))}
      </ul>
    </aside>
  );
}
