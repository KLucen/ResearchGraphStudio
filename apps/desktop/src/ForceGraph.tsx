import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Controls, ReactFlow, type Node, type Viewport } from "@xyflow/react";
import type { components } from "../../../packages/contracts/generated";
import { ForceSimulation } from "./forceSimulation";
import { placeNodes } from "./graphLayout";

type Graph = components["schemas"]["GraphProjection"];
type Layout = components["schemas"]["LayoutView"];
const colors: Record<string, string> = {
  Paper: "#537b98",
  Concept: "#927fba",
  Method: "#508e80",
  Claim: "#b38e54",
  ResearchQuestion: "#ad7c91",
};

export function ForceGraph({
  graph,
  layout,
  selected,
  language,
  onSelect,
  onEdge,
  onPositions,
  onViewport,
  reset,
  pinRequest,
}: {
  graph: Graph;
  layout: Layout;
  selected: string;
  language: string;
  reset: number;
  pinRequest: { id: string; seq: number } | null;
  onSelect: (id: string) => void;
  onEdge: (id: string) => void;
  onPositions: (positions: Layout["positions"]) => void;
  onViewport: (v: Viewport) => void;
}) {
  const [hover, setHover] = useState("");
  const [positions, setPositions] = useState(() =>
    placeNodes(graph, layout.positions ?? []),
  );
  const sim = useRef<ForceSimulation | null>(null);
  const frame = useRef(0);
  const persist = useRef(onPositions);
  const layoutRef = useRef(layout);
  const graphRef = useRef(graph);
  useLayoutEffect(() => {
    persist.current = onPositions;
    layoutRef.current = layout;
    graphRef.current = graph;
  });
  const previousReset = useRef(reset);
  const topology = JSON.stringify([
    graph.nodes.map((n) => n.id),
    graph.edges.map((e) => [e.source, e.target]),
  ]);
  const animate = () => {
    if (frame.current) return;
    const reduced = window.matchMedia?.(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    const step = () => {
      frame.current = 0;
      const engine = sim.current;
      if (!engine) return;
      if (reduced) {
        if (!engine.dragging) {
          for (let i = 0; i < 160; i++) engine.tick();
        }
        setPositions(engine.snapshot());
        if (!engine.dragging) persist.current(engine.snapshot());
        return;
      }
      if (engine.tick()) {
        setPositions(engine.snapshot());
        frame.current = requestAnimationFrame(step);
      } else persist.current(engine.snapshot());
    };
    frame.current = requestAnimationFrame(step);
  };
  useEffect(() => {
    const g = graphRef.current,
      saved = layoutRef.current.positions ?? [];
    const rearrange = previousReset.current !== reset;
    previousReset.current = reset;
    const old = [
      ...new Map(
        [...saved, ...(sim.current?.snapshot() ?? [])].map((p) => [
          p.node_id,
          p,
        ]),
      ).values(),
    ];
    const positions = placeNodes(
      g,
      rearrange ? old.filter((p) => p.pinned) : old,
    );
    const engine = new ForceSimulation(positions, g.edges);
    sim.current = engine;
    setPositions(positions);
    if (
      rearrange ||
      g.nodes.some((n) => !old.some((p) => p.node_id === n.id))
    ) {
      engine.wake();
      animate();
    }
    // Topology changes only; polling and language changes must not restart physics.
  }, [topology, reset]);
  useEffect(() => {
    if (!pinRequest || !sim.current) return;
    sim.current.pin(pinRequest.id);
    setPositions(sim.current.snapshot());
    persist.current(sim.current.snapshot());
    animate();
  }, [pinRequest]);
  useEffect(
    () => () => {
      if (frame.current) {
        cancelAnimationFrame(frame.current);
        frame.current = 0;
      }
    },
    [],
  );
  const active = hover || selected;
  const neighbors = new Set([
    active,
    ...graph.edges.flatMap((e) =>
      e.source === active ? [e.target] : e.target === active ? [e.source] : [],
    ),
  ]);
  const byId = new Map(positions.map((p) => [p.node_id, p]));
  const nodes: Node[] = graph.nodes.map((n) => {
    const p = byId.get(n.id);
    return {
      id: n.id,
      position: { x: p?.x ?? 0, y: p?.y ?? 0 },
      // Controlled nodes are recreated as physics/highlighting changes. Without
      // dimensions React Flow clears its measurement and hides them each frame.
      width: 18,
      height: 18,
      measured: { width: 18, height: 18 },
      selected: n.id === selected,
      className: `graph-dot${p?.pinned ? " pinned" : ""}`,
      ariaLabel: `${n.label_zh || n.label_en}${p?.pinned ? "，已固定" : ""}`,
      data: {
        label: (
          <span className="dot-label" title={n.label_en}>
            {language === "en" ? n.label_en : n.label_zh || n.label_en}
            {language === "both" && n.label_zh && <small>{n.label_en}</small>}
          </span>
        ),
      },
      style: {
        background: colors[n.kind],
        opacity: !active || neighbors.has(n.id) ? 1 : 0.2,
      },
    };
  });
  return (
    <ReactFlow
      nodes={nodes}
      edges={graph.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        type: "straight",
        label:
          hover && (e.source === hover || e.target === hover)
            ? language === "en"
              ? e.relation
              : e.label_zh
            : undefined,
        style: {
          stroke: "#81958c",
          strokeWidth:
            active && (e.source === active || e.target === active) ? 1.8 : 1,
          opacity: !active
            ? 0.38
            : e.source === active || e.target === active
              ? 0.75
              : 0.1,
          strokeDasharray: e.is_dashed ? "4 5" : undefined,
        },
      }))}
      onNodesChange={(changes) => {
        const engine = sim.current;
        if (!engine) return;
        let moved = false;
        for (const change of changes) {
          if (change.type !== "position" || !change.position) continue;
          const p = engine.points.get(change.id);
          if (!p || (p.x === change.position.x && p.y === change.position.y))
            continue;
          engine.move(change.id, change.position.x, change.position.y);
          moved = true;
          if (change.dragging === false) engine.dragging = null;
        }
        if (moved) {
          setPositions(engine.snapshot());
          animate();
        }
      }}
      onNodeDragStop={(_, n) => {
        const engine = sim.current,
          p = engine?.points.get(n.id);
        if (!engine || !p) return;
        if (engine.dragging || p.x !== n.position.x || p.y !== n.position.y) {
          // Controlled React Flow callbacks may still hold the pre-render user node.
          // Position changes above are authoritative while the pointer is dragging.
          if (!engine.dragging) engine.move(n.id, n.position.x, n.position.y);
          engine.dragging = null;
          setPositions(engine.snapshot());
          persist.current(engine.snapshot());
          animate();
        }
      }}
      onNodeDoubleClick={(_, n) => {
        const engine = sim.current;
        if (!engine) return;
        engine.pin(n.id);
        setPositions(engine.snapshot());
        persist.current(engine.snapshot());
        animate();
      }}
      onNodeClick={(_, n) => onSelect(n.id)}
      onNodeMouseEnter={(_, n) => setHover(n.id)}
      onNodeMouseLeave={() => setHover("")}
      onPaneClick={() => onSelect("")}
      onEdgeClick={(_, e) => onEdge(e.id)}
      defaultViewport={{ x: layout.pan_x, y: layout.pan_y, zoom: layout.zoom }}
      onMoveEnd={(_, v) => onViewport(v)}
      fitView={layout.version === 0}
      zoomOnDoubleClick={false}
      minZoom={0.1}
      maxZoom={4}
      nodesConnectable={false}
      nodeDragThreshold={0}
      deleteKeyCode={null}
    >
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}
