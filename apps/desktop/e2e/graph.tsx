import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import "@xyflow/react/dist/style.css";
import "../src/style.css";
import { ForceGraph } from "../src/ForceGraph";
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
  const [poll, setPoll] = useState(0);
  return (
    <>
      <button onClick={() => setPoll(poll + 1)}>模拟轮询</button>
      <output data-testid="layout" hidden>
        {JSON.stringify(layout)}
      </output>
      <div className="projection-canvas" style={{ height: 650, width: 1000 }}>
        <ForceGraph
          graph={{ ...graph, graph_revision: 1 + poll }}
          layout={layout}
          selected={selected}
          language="zh"
          reset={0}
          pinRequest={null}
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
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Harness />
  </StrictMode>,
);
