import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import "@xyflow/react/dist/style.css";
import "../src/style.css";
import { ForceGraph } from "../src/ForceGraph";
import { GraphLegend, graphNodeKinds } from "../src/graphAppearance";
import type { components } from "../../../packages/contracts/generated";
type Graph = components["schemas"]["GraphProjection"];
type Layout = components["schemas"]["LayoutView"];
const graph = {
  project_id: "synthetic",
  graph_revision: 1,
  nodes: Array.from({ length: 12 }, (_, i) => ({
    id: `n${i}`,
    kind: i ? "Claim" : "Paper",
    label_zh: `合成节点 ${i}`,
    label_en: `Synthetic ${i}`,
  })),
  edges: Array.from({ length: 11 }, (_, i) => ({
    id: `e${i}`,
    source: "n0",
    target: `n${i + 1}`,
    relation: "REPORTS",
    label_zh: "报告",
    is_dashed: false,
  })),
} as Graph;
const palette = {
  ...graph,
  nodes: graph.nodes.map((node, i) => ({
    ...node,
    kind: [...Object.keys(graphNodeKinds), "UnsupportedKind"][i],
  })),
} as Graph;
const initial = {
  version: 1,
  zoom: 1,
  pan_x: 130,
  pan_y: 100,
  positions: graph.nodes.map((n, i) => ({
    node_id: n.id,
    x: (i % 4) * 130,
    y: Math.floor(i / 4) * 110,
    pinned: false,
  })),
} as Layout;
function Harness() {
  const [layout, setLayout] = useState(initial);
  const [selected, setSelected] = useState("");
  const [reading, setReading] = useState(false);
  const [typePreview, setTypePreview] = useState(false);
  const [paperScope, setPaperScope] = useState(false);
  const [fitRequest, setFitRequest] = useState(0);
  const [collapsed, setCollapsed] = useState<string[]>([]);
  const [poll, setPoll] = useState(0);
  const ids = new Set([
    "n0",
    "n1",
    "n2",
    ...(!collapsed.includes("a") ? ["n3", "n4"] : []),
    ...(!collapsed.includes("b") ? ["n3", "n5"] : []),
  ]);
  const layered = {
    ...graph,
    nodes: graph.nodes
      .filter((n) => ids.has(n.id))
      .map((n) => ({
        ...n,
        kind:
          n.id === "n3"
            ? ("Method" as const)
            : n.id === "n4"
              ? ("Condition" as const)
              : n.id === "n5"
                ? ("Experiment" as const)
                : n.kind,
      })),
    edges: [
      ...graph.edges.slice(0, 2),
      ...([
        ...["a", "b"]
          .filter((x) => !collapsed.includes(x))
          .flatMap((x) => [
            {
              id: `${x}-shared`,
              source: x === "a" ? "n1" : "n2",
              target: "n3",
              relation: "UNIT_MEMBER",
              label_zh: "共享方法",
              is_dashed: false,
            },
            {
              id: `${x}-member`,
              source: x === "a" ? "n1" : "n2",
              target: x === "a" ? "n4" : "n5",
              relation: "UNIT_MEMBER",
              label_zh: "条件",
              is_dashed: false,
            },
          ]),
      ] as Graph["edges"]),
    ],
  };
  const scoped = {
    ...graph,
    nodes: graph.nodes.slice(0, 6),
    edges: graph.edges.slice(0, 5),
  };
  return (
    <>
      <button onClick={() => setPoll(poll + 1)}>模拟轮询</button>
      <button onClick={() => setReading(!reading)}>分层模式</button>
      <button onClick={() => setTypePreview(!typePreview)}>类型颜色示例</button>
      <button onClick={() => setPaperScope(!paperScope)}>切换论文范围</button>
      <button onClick={() => setFitRequest((value) => value + 1)}>
        适应图谱
      </button>
      {["a", "b"].map((x) => (
        <button
          key={x}
          onClick={() =>
            setCollapsed((old) =>
              old.includes(x) ? old.filter((i) => i !== x) : [...old, x],
            )
          }
        >
          切换支撑 {x}
        </button>
      ))}
      <output data-testid="layout" hidden>
        {JSON.stringify(layout)}
      </output>
      <div className="projection-canvas" style={{ height: 650, width: 1000 }}>
        <ForceGraph
          graph={{
            ...(typePreview
              ? palette
              : reading
                ? layered
                : paperScope
                  ? scoped
                  : graph),
            graph_revision: 1 + poll,
          }}
          layout={layout}
          selected={selected}
          language="zh"
          reset={0}
          pinRequest={null}
          viewKey={paperScope ? "paper" : "all"}
          fitRequest={fitRequest}
          onSelect={setSelected}
          onEdge={() => {}}
          onPositions={(positions) =>
            setLayout((p) => ({ ...p, positions, version: p.version + 1 }))
          }
          onViewport={(v) =>
            setLayout((p) => ({ ...p, pan_x: v.x, pan_y: v.y, zoom: v.zoom }))
          }
        />
      </div>
      <GraphLegend />
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Harness />
  </StrictMode>,
);
