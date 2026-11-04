import type { components } from "../../../packages/contracts/generated";
import "./graphAppearance.css";

export type VisualKind = components["schemas"]["ProjectionNode"]["kind"];

/** One palette for the rendered nodes, filters, details and explanatory legend. */
export const graphNodeKinds: Record<
  VisualKind,
  { label: string; color: string }
> = {
  Paper: { label: "论文", color: "#537b98" },
  Concept: { label: "概念", color: "#927fba" },
  Method: { label: "方法", color: "#508e80" },
  Claim: { label: "主张", color: "#b38e54" },
  ResearchQuestion: { label: "研究问题", color: "#ad7c91" },
  Experiment: { label: "实验", color: "#6f8f9c" },
  Condition: { label: "条件", color: "#8c9966" },
  Finding: { label: "结果", color: "#ba8265" },
  Metric: { label: "指标", color: "#708cae" },
  Argument: { label: "论证", color: "#9c8880" },
  Limitation: { label: "限制", color: "#a47575" },
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
        {Object.entries(graphNodeKinds).map(([kind, appearance]) => (
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
