import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { components } from "../../../packages/contracts/generated";
import { ForceGraph } from "./ForceGraph";

const renderer = vi.hoisted(() => ({ props: {} as Record<string, unknown> }));
vi.mock("@xyflow/react", () => ({
  ReactFlow: (props: Record<string, unknown>) => {
    renderer.props = props;
    return <div />;
  },
  Controls: () => null,
}));

const graph = {
  graph_revision: 1,
  nodes: [{ id: "paper", kind: "Paper", label_zh: "论文", label_en: "Paper" }],
  edges: [],
} as unknown as components["schemas"]["GraphProjection"];
const layout = {
  version: 5,
  zoom: 0.6,
  pan_x: -450,
  pan_y: 250,
  positions: [{ node_id: "paper", x: 200, y: 300, pinned: true }],
} as components["schemas"]["LayoutView"];
const positions = vi.fn();
const viewport = vi.fn();
const fitView = vi.fn().mockResolvedValue(true);
let frames: FrameRequestCallback[] = [];

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

function props(viewKey = "all", fitRequest = 0) {
  return {
    graph,
    layout,
    selected: "",
    language: "zh",
    reset: 0,
    pinRequest: null,
    viewKey,
    fitRequest,
    onSelect: vi.fn(),
    onEdge: vi.fn(),
    onPositions: positions,
    onViewport: viewport,
  };
}
function initialize() {
  act(() => {
    (renderer.props.onInit as (instance: { fitView: typeof fitView }) => void)({
      fitView,
    });
  });
}
function flushFrame() {
  act(() => {
    frames.splice(0).forEach((callback) => callback(performance.now()));
  });
}

test("saved camera and pinned coordinates survive initial mount, polling and resize", () => {
  const { rerender } = render(<ForceGraph {...props()} />);
  initialize();
  expect(renderer.props.defaultViewport).toEqual({
    x: -450,
    y: 250,
    zoom: 0.6,
  });
  expect(renderer.props.fitView).toBe(false);
  rerender(<ForceGraph {...props()} graph={{ ...graph, graph_revision: 2 }} />);
  act(() => window.dispatchEvent(new Event("resize")));
  flushFrame();
  expect(fitView).not.toHaveBeenCalled();
  expect(positions).not.toHaveBeenCalled();
  expect(renderer.props.nodes).toEqual([
    expect.objectContaining({ position: { x: 200, y: 300 }, type: "default" }),
  ]);
});

test("scope changes fit once after initialization and preserve fixed node positions", () => {
  const { rerender } = render(<ForceGraph {...props()} />);
  rerender(<ForceGraph {...props("paper-a")} />);
  flushFrame();
  expect(fitView).not.toHaveBeenCalled();
  initialize();
  flushFrame();
  expect(fitView).toHaveBeenCalledExactlyOnceWith({
    duration: 0,
    padding: 0.18,
  });
  rerender(
    <ForceGraph
      {...props("paper-a")}
      graph={{ ...graph, graph_revision: 9 }}
    />,
  );
  flushFrame();
  expect(fitView).toHaveBeenCalledTimes(1);
  expect(positions).not.toHaveBeenCalled();
});

test("explicit fit requests work without scope change and zero is not a request", () => {
  const { rerender } = render(<ForceGraph {...props()} />);
  initialize();
  rerender(<ForceGraph {...props("all", 1)} />);
  flushFrame();
  expect(fitView).toHaveBeenCalledTimes(1);
  rerender(<ForceGraph {...props("all", 1)} />);
  flushFrame();
  expect(fitView).toHaveBeenCalledTimes(1);
  rerender(<ForceGraph {...props("all", 0)} />);
  flushFrame();
  expect(fitView).toHaveBeenCalledTimes(1);
});
