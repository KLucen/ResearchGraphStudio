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
  RESEARCH_QUESTION: {
    label: "研究问题",
    color: "var(--rgs-graph-research-question)",
  },
  CONCEPT: { label: "概念", color: "var(--rgs-graph-concept)" },
  METHOD: { label: "方法", color: "var(--rgs-graph-method)" },
  CONTRIBUTION: { label: "贡献", color: "var(--rgs-graph-contribution)" },
  FINDING: { label: "结果", color: "var(--rgs-graph-finding)" },
  UNKNOWN: { label: "其他", color: "var(--rgs-graph-unknown)" },
};

export const graphKindLabels = Object.fromEntries(
  Object.entries(graphNodeKinds).map(([kind, { label }]) => [kind, label]),
) as Record<VisualKind, string>;

export function getGraphAppearance(kind: string) {
  if (kind === "PAPER")
    return { label: "论文", color: "var(--rgs-graph-paper)" };
  return Object.hasOwn(graphNodeKinds, kind)
    ? graphNodeKinds[kind as VisualKind]
    : graphNodeKinds.UNKNOWN;
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
