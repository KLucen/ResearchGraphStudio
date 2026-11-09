import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import "@xyflow/react/dist/style.css";
import "../src/style.css";
import { ForceGraph } from "../src/ForceGraph";
import { GraphLegend } from "../src/graphAppearance";
import type { GraphData, GraphLayout } from "../src/graphTypes";
const types = [
  "RESEARCH_QUESTION",
  "CONCEPT",
  "METHOD",
  "CONTRIBUTION",
  "FINDING",
];
const graph: GraphData = {
  nodes: Array.from({ length: 12 }, (_, i) => ({
    id: `n${i}`,
    type: types[i % types.length],
    label_zh: `合成节点 ${i}`,
    label_en: `Synthetic ${i}`,
  })),
  edges: Array.from({ length: 11 }, (_, i) => ({
    id: `e${i}`,
    source: "n0",
    target: `n${i + 1}`,
    type: "RELATED_TO",
    label_zh: "相关",
  })),
};
const initial: GraphLayout = {
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
};
function Harness() {
  const [layout, setLayout] = useState<GraphLayout>(
    () =>
      JSON.parse(localStorage.getItem("lite.graph.layout") || "null") ||
      initial,
  );
  const [selected, setSelected] = useState("");
  const [selectedEdge, setSelectedEdge] = useState("");
  const [poll, setPoll] = useState(0);
  function save(next: GraphLayout) {
    setLayout(next);
    localStorage.setItem("lite.graph.layout", JSON.stringify(next));
  }
  return (
    <>
      <button onClick={() => setPoll(poll + 1)}>模拟轮询</button>
      <output data-testid="layout" hidden>
        {JSON.stringify(layout)}
      </output>
      <output data-testid="selection">{selected || selectedEdge}</output>
      <div className="projection-canvas" style={{ height: 650, width: 1000 }}>
        <ForceGraph
          graph={{ ...graph, render_revision: poll }}
          layout={layout}
          selected={selected}
          language="both"
          reset={0}
          pinRequest={null}
          viewKey="synthetic-overview"
          onSelect={(id) => {
            setSelected(id);
            setSelectedEdge("");
          }}
          onEdge={(id) => {
            setSelectedEdge(id);
            setSelected("");
          }}
          onPositions={(positions) =>
            save({ ...layout, positions, version: (layout.version ?? 0) + 1 })
          }
          onViewport={(v) =>
            save({ ...layout, pan_x: v.x, pan_y: v.y, zoom: v.zoom })
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
