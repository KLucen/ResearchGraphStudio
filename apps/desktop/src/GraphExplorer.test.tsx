import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { GraphExplorer } from "./GraphExplorer";
import { request } from "./api";
const viewport = vi.hoisted(() => ({
  width: 1200,
  height: 500,
  fitView: vi.fn(),
}));
vi.mock("./api", () => ({
  request: vi.fn(),
  api: {
    projectJobs: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
    preview: vi.fn().mockResolvedValue({
      data_url: "data:image/png;base64,fixture",
      page_index: 0,
    }),
  },
}));
vi.mock("@xyflow/react", () => ({
  MarkerType: { ArrowClosed: "arrowclosed" },
  Background: () => null,
  Controls: () => null,
  useReactFlow: () => ({ fitView: viewport.fitView }),
  useStore: (selector: (state: typeof viewport) => unknown) =>
    selector(viewport),
  ReactFlow: ({
    nodes,
    onNodeClick,
    children,
  }: {
    nodes: { id: string }[];
    onNodeClick: (e: unknown, n: { id: string }) => void;
    children: React.ReactNode;
  }) => (
    <div>
      {children}
      {nodes
        .filter((n) => !n.id.startsWith("paper:"))
        .map((n) => (
          <button key={n.id} onClick={() => onNodeClick({}, n)}>
            图谱节点 {n.id}
          </button>
        ))}
    </div>
  ),
}));
const node = (id: string) => ({
  id,
  paper_id: `paper-${id}`,
  kind: "claim",
  text: `Synthetic shared memory claim ${id}`,
  review_status: "needs_review",
  origin: "author_claim",
  source_status: "source_verified",
  revision: 1,
});
const evidence = (id: string) => ({
  id: `e-${id}`,
  page_index: 0,
  start_offset: 0,
  end_offset: 18,
  quote: `Original source ${id}`,
});
const context = (id: string) => ({
  root_id: id,
  nodes: [node(id)],
  dimensions: { metric: { known_state: "unknown", value: null, unit: null } },
  root_evidence_ids: [`e-${id}`],
  evidence: [evidence(id)],
});
let stale = false;
const proposal = () => ({
  id: "relation-1",
  source_id: "a",
  target_id: "b",
  relation_type: "RELATED",
  rationale: "Both discuss shared memory; this is a candidate.",
  review_status: "proposed",
  revision: 1,
  stale,
  attempt_id: "attempt-1",
});
beforeEach(() => {
  vi.clearAllMocks();
  stale = false;
  viewport.width = 1200;
  vi.mocked(request).mockImplementation(async (method, path) => {
    if (path.startsWith("/api/v1/graph/subgraph"))
      return {
        nodes: [node("a"), node("b")],
        relations: [],
        papers: { "paper-a": "Paper A", "paper-b": "Paper B" },
        graph_revision: 4,
        next_cursor: null,
      };
    if (path === "/api/v1/projects/p/reasoning")
      return { attempts: [], relations: [proposal()], alignments: [] };
    if (path.endsWith("/context"))
      return context(path.includes("/a/") ? "a" : "b");
    if (path === "/api/v1/knowledge/candidates")
      return { items: [node("b")], graph_revision: 4 };
    if (path === "/api/v1/knowledge/relations/infer")
      return { id: "job", status: "queued" };
    if (path === "/api/v1/knowledge/relations/relation-1")
      return {
        proposal: proposal(),
        attempt: {
          comparison: {
            overall: "limited",
            rationale: "Missing metric",
            dimensions: [],
          },
        },
        runs: [
          {
            id: "run",
            prompt_name: "P05",
            provider: "mock",
            model: "fixture",
            status: "succeeded",
            raw_output: "{}",
          },
        ],
        reviews: [],
      };
    if (path === "/api/v1/knowledge/semantic-reviews" && method === "POST")
      return { ...proposal(), review_status: "accepted" };
    throw new Error(`Unexpected test route ${path}`);
  });
});
function mount() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <GraphExplorer projectId="p" connected />
    </QueryClientProvider>,
  );
}
test("candidate selection shows current conditions and requires explicit real-model consent", async () => {
  const user = userEvent.setup();
  mount();
  await user.click(
    await screen.findByRole("button", {
      name: /Synthetic shared memory claim a/,
    }),
  );
  await user.click(screen.getByRole("button", { name: "检索跨论文候选" }));
  await user.click(
    await screen.findByRole("button", {
      name: /Synthetic shared memory claim b.*有限证据/,
    }),
  );
  expect(await screen.findByText("当前条件节点")).toBeInTheDocument();
  expect(
    (await screen.findAllByRole("cell", { name: /unknown/ })).length,
  ).toBeGreaterThan(0);

  expect(
    screen.getByRole("button", { name: "比较条件并推理关系" }),
  ).toBeDisabled();
  await user.click(
    screen.getByRole("checkbox", { name: /同意向全局 Reasoning/ }),
  );
  await user.click(screen.getByRole("button", { name: "比较条件并推理关系" }));
  await screen.findByText(/推理任务已排队/);
  expect(request).toHaveBeenCalledWith(
    "POST",
    "/api/v1/knowledge/relations/infer",
    {
      source_id: "a",
      target_id: "b",
      provider: "project",
      allow_network: true,
    },
    expect.any(String),
  );
});
test("stale proposal shows provenance without review controls", async () => {
  stale = true;
  const user = userEvent.setup();
  mount();
  await user.click(
    await screen.findByRole("button", { name: /RELATED.*Both discuss/ }),
  );
  await screen.findByText(/来源已变化，请重新推理/);
  expect(screen.queryByLabelText("审核理由")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "接受候选" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "驳回候选" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText(/P05.*mock/)).toBeInTheDocument();
});

test("comparison retains selected evidence while filtering candidates", async () => {
  const user = userEvent.setup();
  mount();
  await user.click(
    await screen.findByRole("button", {
      name: /Synthetic shared memory claim a/,
    }),
  );
  await screen.findByText("Original source a");
  await user.type(screen.getByLabelText("候选关键词"), "memory");
  expect(screen.queryByLabelText("知识图谱画布")).not.toBeInTheDocument();
  expect(screen.getByText("Original source a")).toBeInTheDocument();
});
