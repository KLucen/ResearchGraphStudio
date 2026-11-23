import { useEffect, useLayoutEffect, useRef, useState } from "react";
import "@xyflow/react/dist/style.css";
import {
  Controls,
  ReactFlow,
  type Node,
  type ReactFlowInstance,
  type Viewport,
} from "@xyflow/react";
import { ForceSimulation } from "./forceSimulation";
import { placeNodes } from "./graphLayout";
import { getGraphAppearance } from "./graphAppearance";
import { useResolvedAppearance } from "./appearance";
import {
  graphEdgeType,
  graphNodeKind,
  type GraphData,
  type GraphLayout,
  type GraphPosition,
} from "./graphTypes";
import {
  knowledgeNodeSize,
  knowledgeNodeText,
  placeKnowledgeLabels,
} from "./knowledgeGraphLabels";
import { isContextMenuKey, type ContextMenuEvent } from "./ContextMenu";
import "./forceGraph.css";

export type GraphContextTarget =
  | { kind: "node"; id: string; pinned: boolean }
  | { kind: "edge"; id: string }
  | { kind: "canvas" };

type GraphPreview = { kind: "node" | "edge"; id: string };

function graphPreviewAt(target: EventTarget | null): GraphPreview | null {
  if (!(target instanceof Element)) return null;
  const nodeId = target
    .closest(".react-flow__node[data-id]")
    ?.getAttribute("data-id");
  if (nodeId) return { kind: "node", id: nodeId };
  const edgeId = target
    .closest(".react-flow__edge[data-id]")
    ?.getAttribute("data-id");
  return edgeId ? { kind: "edge", id: edgeId } : null;
}

export function ForceGraph({
  graph,
  layout,
  selected,
  selectedEdge = "",
  language,
  onSelect,
  onEdge,
  onGraphContextMenu,
  onPositions,
  onViewport,
  reset,
  pinRequest,
  viewKey,
  fitRequest = 0,
  persistSettledPositions = true,
  appearance,
}: {
  graph: GraphData;
  layout: GraphLayout;
  selected: string;
  selectedEdge?: string;
  language: string;
  reset: number;
  pinRequest: { id: string; seq: number } | null;
  viewKey?: string;
  fitRequest?: number;
  persistSettledPositions?: boolean;
  appearance?: "knowledge";
  onSelect: (id: string) => void;
  onEdge: (id: string) => void;
  onGraphContextMenu?: (
    event: ContextMenuEvent,
    target: GraphContextTarget,
  ) => void;
  onPositions: (positions: GraphPosition[]) => void;
  onViewport: (v: Viewport) => void;
}) {
  const colorMode = useResolvedAppearance();
  const [pointerPreview, setPointerPreview] = useState<GraphPreview | null>(
    null,
  );
  const [focusPreview, setFocusPreview] = useState<GraphPreview | null>(null);
  const [dragging, setDragging] = useState(false);
  const [panning, setPanning] = useState(false);
  const [compactLabels, setCompactLabels] = useState(() => layout.zoom < 0.55);
  const knowledgeAppearance = appearance === "knowledge";
  const [positions, setPositions] = useState(() =>
    placeNodes(graph, layout.positions ?? []),
  );
  const sim = useRef<ForceSimulation | null>(null);
  const frame = useRef(0);
  const flow = useRef<Pick<ReactFlowInstance, "fitView"> | null>(null);
  const fitFrame = useRef(0);
  const pendingFit = useRef(false);
  const previousView = useRef(viewKey);
  const previousFit = useRef(fitRequest);
  const persist = useRef(onPositions);
  const persistAfterSettling = useRef(persistSettledPositions);
  const layoutRef = useRef(layout);
  const graphRef = useRef(graph);
  useLayoutEffect(() => {
    persist.current = onPositions;
    persistAfterSettling.current = persistSettledPositions;
    layoutRef.current = layout;
    graphRef.current = graph;
  });
  const previousReset = useRef(reset);
  const topology = JSON.stringify([
    graph.nodes.map((n) => n.id),
    graph.edges.map((e) => [e.source, e.target]),
  ]);
  const scheduleFit = () => {
    pendingFit.current = true;
    if (!flow.current || fitFrame.current) return;
    fitFrame.current = requestAnimationFrame(() => {
      fitFrame.current = 0;
      if (!pendingFit.current || !flow.current) return;
      pendingFit.current = false;
      void flow.current.fitView({ duration: 0, padding: 0.18 });
    });
  };
  useEffect(() => {
    if (previousView.current === viewKey) return;
    previousView.current = viewKey;
    scheduleFit();
  }, [viewKey]);
  useEffect(() => {
    if (previousFit.current === fitRequest) return;
    previousFit.current = fitRequest;
    if (fitRequest) scheduleFit();
  }, [fitRequest]);
  const animate = () => {
    if (frame.current) return;
    const mayPersistWhenSettled = persistAfterSettling.current;
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
        if (
          !engine.dragging &&
          mayPersistWhenSettled &&
          persistAfterSettling.current
        )
          persist.current(engine.snapshot());
        return;
      }
      if (engine.tick()) {
        setPositions(engine.snapshot());
        frame.current = requestAnimationFrame(step);
      } else if (mayPersistWhenSettled && persistAfterSettling.current)
        persist.current(engine.snapshot());
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
    if (frame.current) {
      cancelAnimationFrame(frame.current);
      frame.current = 0;
    }
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
      if (fitFrame.current) {
        cancelAnimationFrame(fitFrame.current);
        fitFrame.current = 0;
      }
    },
    [],
  );
  const preview = dragging || panning ? null : (pointerPreview ?? focusPreview);
  const activeNode = preview
    ? preview.kind === "node"
      ? preview.id
      : ""
    : selected;
  const activeEdgeId = preview
    ? preview.kind === "edge"
      ? preview.id
      : ""
    : selectedEdge;
  const activeEdge = graph.edges.find((edge) => edge.id === activeEdgeId);
  const neighbors = new Set([
    activeNode,
    ...(activeEdge ? [activeEdge.source, activeEdge.target] : []),
    ...graph.edges.flatMap((e) =>
      e.source === activeNode
        ? [e.target]
        : e.target === activeNode
          ? [e.source]
          : [],
    ),
  ]);
  const emphasized = !!(activeNode || activeEdge);
  const byId = new Map(positions.map((p) => [p.node_id, p]));
  const knowledgeLabels = knowledgeAppearance
    ? placeKnowledgeLabels(
        graph.nodes,
        byId,
        language,
        preview?.kind === "node" ? preview.id : (activeEdge?.source ?? ""),
        selected,
        compactLabels,
      )
    : null;
  const nodes: Node[] = graph.nodes.map((n) => {
    const p = byId.get(n.id);
    const outsideTopic = knowledgeAppearance && n.outside_topic;
    const kind = graphNodeKind(n);
    const nodeAppearance = getGraphAppearance(kind);
    const diameter = knowledgeAppearance ? knowledgeNodeSize(n) : 18;
    const knowledgeText = knowledgeAppearance
      ? knowledgeNodeText(n, language)
      : null;
    const knowledgeTitle = knowledgeText
      ? [knowledgeText.primary, knowledgeText.secondary]
          .filter(Boolean)
          .join(" / ") || nodeAppearance.label
      : "";
    const label = knowledgeLabels?.get(n.id);
    return {
      id: n.id,
      type: "default",
      position: { x: p?.x ?? 0, y: p?.y ?? 0 },
      // Controlled nodes are recreated as physics/highlighting changes. Without
      // dimensions React Flow clears its measurement and hides them each frame.
      width: diameter,
      height: diameter,
      measured: { width: diameter, height: diameter },
      selected: n.id === selected,
      draggable: outsideTopic ? false : undefined,
      className: `graph-dot${outsideTopic ? " outside-topic" : ""}${p?.pinned && !outsideTopic ? " pinned" : ""}${n.reading_level ? ` reading-${n.reading_level.toLowerCase()}` : ""}${n.reading_check === "MISCONCEPTION" || n.reading_unresolved ? " reading-misconception" : ""}`,
      ariaLabel: `${knowledgeTitle || n.label_en || n.label_zh || "节点"}${outsideTopic ? "，专题外论文" : p?.pinned ? "，已固定" : ""}${n.reading_unresolved ? "，有待解问题" : ""}`,
      domAttributes: knowledgeAppearance
        ? {
            title: outsideTopic
              ? `${knowledgeTitle} · 专题外论文`
              : knowledgeTitle,
            "aria-haspopup": onGraphContextMenu ? "menu" : undefined,
          }
        : undefined,
      data: {
        label: knowledgeText ? (
          label && (
            <span
              className="knowledge-dot-label"
              style={{ left: label.x, top: label.y, width: label.width }}
              aria-hidden="true"
            >
              <span>{knowledgeText.primary}</span>
              {knowledgeText.secondary && (
                <span className="knowledge-dot-label-secondary">
                  {knowledgeText.secondary}
                </span>
              )}
            </span>
          )
        ) : (
          <span
            className="dot-label"
            title={n.label_en || undefined}
            data-kind={n.kind}
          >
            {language === "en"
              ? n.label_en || n.label_zh || ""
              : n.label_zh || n.label_en || ""}
            {language === "both" && n.label_zh && n.label_en && (
              <small>{n.label_en}</small>
            )}
          </span>
        ),
      },
      style: {
        // The built-in default node is white without a background override.
        background: outsideTopic ? "var(--rgs-surface)" : nodeAppearance.color,
        opacity: !emphasized || neighbors.has(n.id) ? 1 : 0.5,
      },
    };
  });
  return (
    <ReactFlow
      colorMode={colorMode}
      className={
        knowledgeAppearance ? "force-graph force-graph--knowledge" : undefined
      }
      onInit={(instance) => {
        flow.current = instance;
        if (pendingFit.current) scheduleFit();
      }}
      nodes={nodes}
      edges={graph.edges.map((edge) => {
        const highlighted =
          edge.id === activeEdgeId ||
          (!!activeNode &&
            (edge.source === activeNode || edge.target === activeNode));
        const name =
          language === "en"
            ? graphEdgeType(edge)
            : edge.label_zh || graphEdgeType(edge);
        const outsideTopic = knowledgeAppearance && edge.outside_topic;
        const label = outsideTopic ? `${name} · 专题外联系` : name;
        const isSelected = edge.id === selectedEdge;
        return {
          id: edge.id,
          source: edge.source,
          target: edge.target,
          type: "straight",
          className: outsideTopic ? "outside-topic" : undefined,
          ariaLabel: label,
          selected: isSelected,
          domAttributes: onGraphContextMenu
            ? { "aria-haspopup": "menu" as const }
            : undefined,
          label: preview && highlighted ? label : undefined,
          style: {
            stroke:
              isSelected || highlighted
                ? "var(--rgs-graph-edge-active)"
                : outsideTopic
                  ? "var(--rgs-focus)"
                  : "var(--rgs-graph-edge)",
            strokeWidth: isSelected ? 2.8 : highlighted ? 2.2 : 1.15,
            opacity: highlighted || isSelected ? 1 : emphasized ? 0.28 : 0.74,
            strokeDasharray: outsideTopic
              ? "9 4 2 4"
              : edge.is_dashed
                ? "4 5"
                : undefined,
          },
        };
      })}
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
      onNodeDragStart={() => {
        setDragging(true);
        setPointerPreview(null);
      }}
      onNodeDragStop={(_, n) => {
        setDragging(false);
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
        if (!engine || n.draggable === false) return;
        engine.pin(n.id);
        setPositions(engine.snapshot());
        persist.current(engine.snapshot());
        animate();
      }}
      onNodeClick={(_, n) => onSelect(n.id)}
      onNodeMouseEnter={(_, n) => setPointerPreview({ kind: "node", id: n.id })}
      onNodeMouseLeave={() => setPointerPreview(null)}
      onEdgeMouseEnter={(_, e) => setPointerPreview({ kind: "edge", id: e.id })}
      onEdgeMouseLeave={() => setPointerPreview(null)}
      onFocusCapture={(event) =>
        setFocusPreview(
          event.target.matches(":focus-visible")
            ? graphPreviewAt(event.target)
            : null,
        )
      }
      onBlurCapture={() => setFocusPreview(null)}
      onPointerDownCapture={() => setFocusPreview(null)}
      onPaneClick={() => onSelect("")}
      onEdgeClick={(_, e) => onEdge(e.id)}
      onNodeContextMenu={
        onGraphContextMenu &&
        ((event, node) =>
          onGraphContextMenu(event, {
            kind: "node",
            id: node.id,
            pinned: !!byId.get(node.id)?.pinned,
          }))
      }
      onEdgeContextMenu={
        onGraphContextMenu &&
        ((event, edge) =>
          onGraphContextMenu(event, { kind: "edge", id: edge.id }))
      }
      onPaneContextMenu={
        onGraphContextMenu &&
        ((event) => onGraphContextMenu(event, { kind: "canvas" }))
      }
      onKeyDownCapture={(event) => {
        const target = graphPreviewAt(event.target);
        if (!target) return;
        if (onGraphContextMenu && isContextMenuKey(event)) {
          onGraphContextMenu(
            event,
            target.kind === "node"
              ? {
                  ...target,
                  kind: "node",
                  pinned: !!byId.get(target.id)?.pinned,
                }
              : { ...target, kind: "edge" },
          );
        } else if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          event.stopPropagation();
          if (target.kind === "node") onSelect(target.id);
          else onEdge(target.id);
        }
      }}
      defaultViewport={{ x: layout.pan_x, y: layout.pan_y, zoom: layout.zoom }}
      onMoveStart={(event) => {
        if (event) {
          setPanning(true);
          setPointerPreview(null);
        }
      }}
      onMoveEnd={(_, v) => {
        setPanning(false);
        if (knowledgeAppearance) setCompactLabels(v.zoom < 0.55);
        onViewport(v);
      }}
      fitView={layout.version === 0}
      autoPanOnNodeFocus={false}
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
