import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ForceGraph } from "./ForceGraph";
import { ForceSimulation } from "./forceSimulation";
import { placeNodes } from "./graphLayout";
import type { GraphData, GraphLayout } from "./graphTypes";

/**
 * Executable design contract for the reusable LightGraph renderer.
 *
 * These assertions intentionally describe the engine boundary rather than a
 * particular page: semantic graph data is supplied by the caller, while
 * coordinates, interaction state, and viewport persistence belong to the
 * renderer.
 */

const renderer = vi.hoisted(() => ({ props: {} as Record<string, unknown> }));
type RenderedNode = {
  id: string;
  position: { x: number; y: number };
  data: {
    label: { props: { children: unknown } };
  } & Record<string, unknown>;
};
type RenderedEdge = {
  id: string;
  source: string;
  target: string;
  type: string;
  style: { strokeDasharray?: string };
  label?: string;
};
vi.mock("@xyflow/react", () => ({
  ReactFlow: (props: Record<string, unknown>) => {
    renderer.props = props;
    return <div />;
  },
  Controls: () => null,
}));

const graph: GraphData = {
  nodes: [
    {
      id: "n1",
      type: "METHOD",
      label_zh: "合成方法",
      label_en: "Synthetic method",
    },
    {
      id: "n2",
      type: "FINDING",
      label_zh: "主要结果",
      label_en: "Main finding",
    },
  ],
  edges: [
    {
      id: "e1",
      source: "n1",
      target: "n2",
      type: "YIELDS",
      basis: "INFERRED",
      is_dashed: true,
    },
  ],
};

const layout: GraphLayout = {
  version: 1,
  pan_x: -70,
  pan_y: 45,
  zoom: 0.7,
  positions: [{ node_id: "n1", x: 150, y: 220, pinned: true }],
};

let frames: FrameRequestCallback[] = [];
const positions = vi.fn();
const viewport = vi.fn();

beforeEach(() => {
  frames = [];
  vi.clearAllMocks();
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    frames.push(callback);
    return frames.length;
  });
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
});

afterEach(() => vi.unstubAllGlobals());

function renderGraph() {
  const props = {
    graph,
    layout,
    selected: "",
    language: "both",
    reset: 0,
    pinRequest: null,
    viewKey: "paper-version-1",
    onSelect: vi.fn(),
    onEdge: vi.fn(),
    onPositions: positions,
    onViewport: viewport,
  };
  const result = render(<ForceGraph {...props} />);
  return { ...result, props };
}

test("layout seeding is deterministic, stable by node ID, and ignores stale entries", () => {
  const first = placeNodes(graph, []);
  const second = placeNodes(graph, []);
  expect(second).toEqual(first);

  const restored = placeNodes(graph, [
    { node_id: "n1", x: 99, y: -12, pinned: true },
    { node_id: "stale-node", x: 1, y: 2, pinned: false },
  ]);
  expect(restored).toEqual([
    { node_id: "n1", x: 99, y: -12, pinned: true },
    expect.objectContaining({ node_id: "n2" }),
  ]);
  expect(restored.map((point) => point.node_id)).toEqual(["n1", "n2"]);
});

test("force simulation keeps pinned nodes fixed, moves connected nodes, and cools to rest", () => {
  const sim = new ForceSimulation(
    [
      { node_id: "a", x: 0, y: 0, pinned: false },
      { node_id: "b", x: 110, y: 0, pinned: false },
      { node_id: "fixed", x: 200, y: 90, pinned: true },
    ],
    [
      { source: "a", target: "b" },
      { source: "b", target: "fixed" },
    ],
  );
  sim.move("a", -200, 80);
  const before = sim.points.get("b")!;
  const beforeB = { x: before.x, y: before.y };
  for (let i = 0; i < 25; i++) sim.tick();
  expect(sim.points.get("a")).toMatchObject({ x: -200, y: 80 });
  expect(sim.points.get("b")).not.toMatchObject(beforeB);
  expect(sim.points.get("fixed")).toMatchObject({ x: 200, y: 90 });

  sim.dragging = null;
  for (let i = 0; i < 400 && sim.tick(); i++) {
    // bounded settling loop: the renderer must never run an unbounded physics
    // task on the UI thread.
  }
  expect(sim.tick()).toBe(false);
  expect(sim.snapshot()).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        node_id: "fixed",
        x: 200,
        y: 90,
        pinned: true,
      }),
    ]),
  );
  expect(
    sim
      .snapshot()
      .every((point) => Number.isFinite(point.x) && Number.isFinite(point.y)),
  ).toBe(true);
});

test("invalid pointer coordinates are ignored instead of poisoning layout state", () => {
  const sim = new ForceSimulation(
    [{ node_id: "n1", x: 20, y: 30, pinned: false }],
    [],
  );
  sim.move("n1", Number.NaN, Number.POSITIVE_INFINITY);
  expect(sim.snapshot()).toEqual([
    { node_id: "n1", x: 20, y: 30, pinned: false },
  ]);
});

test("renderer treats graph semantics as input and never uses evidence fields or model coordinates", () => {
  const semanticGraph = {
    ...graph,
    nodes: graph.nodes.map((node) => ({
      ...node,
      x: 9999,
      y: -9999,
      evidence: [{ page: 4, quote: "must stay outside LightGraph" }],
    })),
  } as GraphData;
  const props = {
    graph: semanticGraph,
    layout: { version: 1, pan_x: 0, pan_y: 0, zoom: 1, positions: [] },
    selected: "",
    language: "zh",
    reset: 0,
    pinRequest: null,
    viewKey: "paper-version-1",
    onSelect: vi.fn(),
    onEdge: vi.fn(),
    onPositions: positions,
    onViewport: viewport,
  };
  render(<ForceGraph {...props} />);
  const nodes = renderer.props.nodes as RenderedNode[];
  expect(nodes).toHaveLength(2);
  expect(nodes.every((node) => !Object.hasOwn(node.data, "evidence"))).toBe(
    true,
  );
  expect(nodes.map((node) => node.position)).not.toContainEqual({
    x: 9999,
    y: -9999,
  });
});

test("renderer preserves saved camera, exposes bilingual nodes and relation semantics", () => {
  renderGraph();
  expect(renderer.props.defaultViewport).toEqual({
    x: -70,
    y: 45,
    zoom: 0.7,
  });
  const nodes = renderer.props.nodes as RenderedNode[];
  const edges = renderer.props.edges as RenderedEdge[];
  expect(nodes.map((node) => node.id)).toEqual(["n1", "n2"]);
  expect(nodes[0].position).toEqual({ x: 150, y: 220 });
  const bilingual = nodes[0].data.label.props.children as [
    string,
    { props: { children: string } },
  ];
  expect(bilingual[0]).toBe("合成方法");
  expect(bilingual[1].props.children).toBe("Synthetic method");
  expect(edges[0]).toMatchObject({
    id: "e1",
    source: "n1",
    target: "n2",
    type: "straight",
  });
  expect(edges[0].style.strokeDasharray).toBe("4 5");

  act(() => {
    (
      renderer.props.onNodeMouseEnter as (
        event: unknown,
        node: { id: string },
      ) => void
    )(null, { id: "n1" });
  });
  const hoveredEdges = renderer.props.edges as RenderedEdge[];
  expect(hoveredEdges[0].label).toBe("YIELDS");
});

test("drag, pin, edge selection, and viewport changes persist through renderer callbacks", () => {
  renderGraph();
  const nodeDragStop = renderer.props.onNodeDragStop as (
    event: unknown,
    node: { id: string; position: { x: number; y: number } },
  ) => void;
  act(() => nodeDragStop(null, { id: "n1", position: { x: 240, y: 260 } }));
  expect(positions).toHaveBeenCalledWith(
    expect.arrayContaining([
      expect.objectContaining({ node_id: "n1", x: 240, y: 260 }),
    ]),
  );

  const beforePin = positions.mock.calls.at(-1)?.[0];
  act(() =>
    (
      renderer.props.onNodeDoubleClick as (
        event: unknown,
        node: { id: string },
      ) => void
    )(null, { id: "n2" }),
  );
  const afterPin = positions.mock.calls.at(-1)?.[0];
  expect(afterPin).not.toEqual(beforePin);
  expect(afterPin).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ node_id: "n2", pinned: true }),
    ]),
  );

  act(() =>
    (
      renderer.props.onMoveEnd as (
        event: unknown,
        value: { x: number; y: number; zoom: number },
      ) => void
    )(null, { x: 12, y: -5, zoom: 1.25 }),
  );
  expect(viewport).toHaveBeenCalledWith({ x: 12, y: -5, zoom: 1.25 });
});
