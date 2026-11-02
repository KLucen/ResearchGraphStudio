import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { GraphWorkspace } from "./GraphWorkspace";
import { request, api } from "./api";
import { placeNodes } from "./graphLayout";
import type { ReactNode } from "react";
import type { Node, NodeChange } from "@xyflow/react";

vi.mock("./api", () => ({
  request: vi.fn(),
  api: {
    papers: vi.fn(),
    paper: vi.fn(),
    projectJobs: vi.fn(),
    node: vi.fn(),
    preview: vi.fn(),
  },
}));
vi.mock("@xyflow/react", () => ({
  Background: () => null,
  Controls: () => null,
  applyNodeChanges: (_: unknown, n: Node[]) => n,
  ReactFlow: ({
    nodes,
    onNodeClick,
    onNodeDoubleClick,
    onNodeDragStop,
    onNodesChange,
    children,
  }: {
    nodes: Node[];
    onNodeClick: (_: unknown, n: Node) => void;
    onNodeDoubleClick: (_: unknown, n: Node) => void;
    onNodeDragStop: (_: unknown, n: Node) => void;
    onNodesChange: (changes: NodeChange[]) => void;
    children: ReactNode;
  }) => (
    <div>
      {nodes.map((n) => (
        <div key={n.id}>
          <button
            onClick={() => onNodeClick(null, n)}
            onDoubleClick={() => onNodeDoubleClick(null, n)}
          >
            {String(n.id)}
          </button>
          <button
            onClick={() => {
              onNodesChange([
                {
                  id: n.id,
                  type: "position",
                  position: { x: 321, y: 654 },
                  dragging: true,
                },
              ]);
              onNodeDragStop(null, n);
            }}
          >
            移动 {n.id}
          </button>
          <span data-testid={`position-${n.id}`}>
            {n.position.x},{n.position.y}
          </span>
          <button onClick={() => onNodeDragStop(null, n)}>
            原地点击 {n.id}
          </button>
        </div>
      ))}
      {children}
    </div>
  ),
}));
const graph = {
  contract_version: "reading-projection-2.0",
  build_state: "complete",
  project_id: "p",
  graph_revision: 2,
  nodes: [
    {
      id: "n",
      paper_id: "paper",
      kind: "Claim" as const,
      label_zh: "主张",
      label_en: "Claim",
      detail_ref: "/api/v1/projects/p/graph/nodes/n",
      source_status: "anchored",
      review_status: "unreviewed",
      knowledge_origin: "paper_author",
      badges: [],
      graph_role: "core",
    },
  ],
  edges: [],
  has_more: false,
  next_cursor: null,
};
let layout = {
  version: 1,
  positions: [{ node_id: "n", x: 12, y: 20, pinned: false }],
  zoom: 1,
  pan_x: 0,
  pan_y: 0,
};
beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  layout = {
    version: 1,
    positions: [{ node_id: "n", x: 12, y: 20, pinned: false }],
    zoom: 1,
    pan_x: 0,
    pan_y: 0,
  };
  vi.mocked(api.papers).mockResolvedValue({ items: [], next_cursor: null });
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [],
    next_cursor: null,
  });
  vi.mocked(request).mockImplementation(async (method, path, body) => {
    if (path.endsWith("/projection")) return graph;
    if (path.endsWith("/layout")) {
      if (method === "POST") {
        const b = body as { positions: typeof layout.positions };
        layout = {
          ...layout,
          version: layout.version + 1,
          positions: b.positions,
        };
      }
      return layout;
    }
    if (path.endsWith("/nodes/n"))
      return {
        id: "n",
        paper_id: "paper",
        title: "Source",
        node: null,
        display: { summary_en: "English source", summary_zh: "中文解释" },
        related: [],
        evidence: [],
        counts: {},
        document_version_ids: [],
        zotero_url: null,
        graph_revision: 2,
      };
    throw new Error(`unexpected ${path}`);
  });
});
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(["papers", "p"], {
    pages: [{ items: [], next_cursor: null }],
    pageParams: [0],
  });
  return render(
    <QueryClientProvider client={client}>
      <GraphWorkspace projectId="p" connected />
    </QueryClientProvider>,
  );
}

test("click loads full inspector and double-click pins; focus remains explicit", async () => {
  const user = userEvent.setup();
  mount();
  await user.click(await screen.findByRole("button", { name: "n" }));
  await screen.findByText("中文解释");
  await user.selectOptions(screen.getByLabelText("图谱语言"), "both");
  await screen.findByText("English source");
  await user.dblClick(screen.getByRole("button", { name: "n" }));
  await screen.findByRole("button", { name: "解除固定" });
  await user.click(screen.getByRole("button", { name: "聚焦邻域" }));
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "POST",
      "/api/v1/projects/p/graph/projection",
      expect.objectContaining({ focus_id: "n", depth: 1, limit: 60 }),
    ),
  );
});

test("drag persists coordinates without implicitly pinning", async () => {
  const user = userEvent.setup();
  const view = mount();
  await user.click(await screen.findByRole("button", { name: "移动 n" }));
  expect(screen.getByTestId("position-n")).toHaveTextContent("321,654");
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "POST",
      "/api/v1/projects/p/graph/layout",
      expect.objectContaining({
        expected_version: 1,
        positions: [{ node_id: "n", x: 321, y: 654, pinned: false }],
      }),
    ),
  );
  view.unmount();
  mount();
  await waitFor(() =>
    expect(screen.getByTestId("position-n")).toHaveTextContent("321,654"),
  );
});

test("navigation before autosave recovers pending layout without overwriting it", async () => {
  const user = userEvent.setup();
  const view = mount();
  await user.click(await screen.findByRole("button", { name: "移动 n" }));
  view.unmount();
  mount();
  await waitFor(() =>
    expect(screen.getByTestId("position-n")).toHaveTextContent("321,654"),
  );
  await waitFor(() => expect(layout.positions[0].pinned).toBe(false));
});

test("a pointer release without movement does not pin or save the node", async () => {
  const user = userEvent.setup();
  mount();
  await user.click(await screen.findByRole("button", { name: "原地点击 n" }));
  expect(screen.getByTestId("position-n")).toHaveTextContent("12,20");
  expect(localStorage.getItem("researchgraph.layout-draft.p")).toBeNull();
  expect(request).not.toHaveBeenCalledWith(
    "POST",
    "/api/v1/projects/p/graph/layout",
    expect.anything(),
  );
});

test("reloading a conflicted layout replaces canvas positions and pending draft", async () => {
  const user = userEvent.setup();
  const original = vi.mocked(request).getMockImplementation()!;
  vi.mocked(request).mockImplementation(async (method, path, body) => {
    if (method === "POST" && path.endsWith("/layout")) {
      layout = {
        ...layout,
        version: 8,
        positions: [{ node_id: "n", x: 78, y: 90, pinned: true }],
      };
      throw new Error("layout conflict");
    }
    return original(method, path, body);
  });
  mount();
  await user.click(await screen.findByRole("button", { name: "移动 n" }));
  await user.click(
    await screen.findByRole("button", {
      name: "重新加载服务器布局（放弃未保存位置）",
    }),
  );
  await waitFor(() =>
    expect(screen.getByTestId("position-n")).toHaveTextContent("78,90"),
  );
  expect(localStorage.getItem("researchgraph.layout-draft.p")).toBeNull();
});

test("force pass preserves saved nodes while bounding the new layout", () => {
  const result = placeNodes(graph, [
    { node_id: "n", x: 980, y: -200, pinned: true },
  ]);
  expect(result[0]).toEqual({ node_id: "n", x: 980, y: -200, pinned: true });
  const fresh = placeNodes(graph, []);
  expect(fresh.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y))).toBe(
    true,
  );
});

test("an unpublished paper graph explains saved candidates and opens recovery controls", async () => {
  const original = vi.mocked(request).getMockImplementation()!;
  vi.mocked(api.paper).mockResolvedValue({ revisions: [{ id: "v" }] } as never);
  vi.mocked(request).mockImplementation(async (method, path, ...args) => {
    if (path.endsWith("/projection"))
      return {
        ...graph,
        nodes: [],
        paper_builds: [
          {
            paper_id: "paper",
            title: "Preserved paper",
            candidate_count: 206,
            published_units: 0,
            completed_batches: 6,
            total_batches: 12,
          },
        ],
      };
    if (path.endsWith("/graph-selection"))
      return { selection_revision: 0, build_state: "not_built" };
    if (path.includes("/candidates?")) return { items: [], next_cursor: null };
    return original(method, path, ...args);
  });
  mount();
  expect(await screen.findByText(/已保存 206 条新版候选/)).toBeVisible();
  await userEvent.click(
    screen.getByRole("button", { name: "查看已保存候选与建图选项" }),
  );
  expect(await screen.findByLabelText("搜索全部候选")).toBeVisible();
  expect(
    vi
      .mocked(request)
      .mock.calls.some((c) => c[1].includes("knowledge/extract")),
  ).toBe(false);
});
