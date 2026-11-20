import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { api, type OverviewView } from "./api";
import { PaperOverview } from "./PaperOverview";

vi.mock("./api", () => ({
  api: {
    modelOverview: vi.fn(),
    generateModelOverview: vi.fn(),
    modelOverviewLayout: vi.fn(),
    saveModelOverviewLayout: vi.fn(),
    resetModelOverviewLayout: vi.fn(),
    overview: vi.fn(),
    generateOverview: vi.fn(),
    overviewLayout: vi.fn(),
    conceptUnderstanding: vi.fn(),
  },
}));

vi.mock("./ForceGraph", () => ({
  ForceGraph: ({
    graph,
    onPositions,
  }: {
    graph: { nodes: { label_zh: string }[] };
    onPositions: (positions: unknown) => void;
  }) => (
    <div data-testid="shared-overview-graph">
      {graph.nodes.map((node) => node.label_zh).join("；")}
      <button
        onClick={() =>
          onPositions([{ node_id: "n1", x: 10, y: 20, pinned: true }])
        }
      >
        保存节点位置
      </button>
    </div>
  ),
}));

const completed: OverviewView = {
  id: "model-overview-1",
  paper_id: "paper-1",
  document_version_id: "parse-1",
  pdf_hash: "",
  input_hash: "",
  schema_version: "paper_overview_graph.v1",
  prompt_version: "paper_overview_with_light_graph_v1",
  provider_id: "synthetic",
  model_id: "synthetic",
  status: "COMPLETED",
  graph_status: "READY",
  paper_card: {
    research_question: "合成研究问题",
    motivation: "合成动机",
    method_summary: "合成方法概述",
    contributions: ["合成贡献"],
    main_findings: ["合成主要发现"],
    limitations: ["合成局限"],
  },
  graph: {
    nodes: [
      {
        id: "n1",
        type: "METHOD",
        label_zh: "合成图谱节点",
        label_en: null,
        description_zh: "合成方法说明",
        basis: "EXPLICIT",
      },
    ],
    edges: [],
  },
  usage: null,
  generated_at: "2026-11-19T00:00:00Z",
  cache_hit: false,
  job_id: "job-1",
  error_code: null,
  error: null,
};

function mount(source: "local" | "model" = "model") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PaperOverview
        source={source}
        paperId="paper-1"
        revisionId="parse-1"
        projectId="project-1"
        connected
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.modelOverview).mockResolvedValue(completed);
  vi.mocked(api.overview).mockResolvedValue(completed);
  const layout = { overview_result_id: "model-overview-1", positions: [] };
  vi.mocked(api.modelOverviewLayout).mockResolvedValue(layout);
  vi.mocked(api.overviewLayout).mockResolvedValue(layout);
  vi.mocked(api.saveModelOverviewLayout).mockImplementation(
    async (_id, value) => value,
  );
});

test("model-derived overview uses the shared card, graph and separate layout persistence", async () => {
  mount();
  expect(await screen.findByText("知识卡片 · PaperCard")).toBeInTheDocument();
  for (const text of [
    "合成研究问题",
    "合成动机",
    "合成方法概述",
    "合成贡献",
    "合成主要发现",
    "合成局限",
  ]) {
    expect(screen.getByText(text)).toBeInTheDocument();
  }
  expect(await screen.findByTestId("shared-overview-graph")).toHaveTextContent(
    "合成图谱节点",
  );
  expect(api.modelOverview).toHaveBeenCalledWith("paper-1", "parse-1");
  expect(api.conceptUnderstanding).not.toHaveBeenCalled();
  expect(api.overview).not.toHaveBeenCalled();
  expect(api.generateModelOverview).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "保存节点位置" }));
  await waitFor(() =>
    expect(api.saveModelOverviewLayout).toHaveBeenCalledWith(
      "paper-1",
      expect.objectContaining({
        overview_result_id: "model-overview-1",
        positions: [{ node_id: "n1", x: 10, y: 20, pinned: true }],
      }),
    ),
  );
});

test("unselected and legacy overviews remain ungenerated until explicit consent and action", async () => {
  vi.mocked(api.modelOverview).mockResolvedValue(null);
  vi.mocked(api.generateModelOverview).mockResolvedValue({
    ...completed,
    status: "PENDING",
    paper_card: null,
    graph: null,
  });
  mount();
  expect(
    await screen.findByText(/尚未生成知识卡片和轻量图谱/),
  ).toBeInTheDocument();
  const button = screen.getByRole("button", { name: "生成论文概览" });
  expect(button).toBeDisabled();
  expect(api.generateModelOverview).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole("checkbox", { name: /允许向已配置模型发送本篇论文内容/ }),
  );
  fireEvent.click(button);
  await waitFor(() =>
    expect(api.generateModelOverview).toHaveBeenCalledTimes(1),
  );
  expect(api.generateModelOverview).toHaveBeenCalledWith(
    "paper-1",
    "parse-1",
    true,
    false,
    false,
  );
  expect(api.generateOverview).not.toHaveBeenCalled();
});

test("local source retains the existing overview and understanding adapters", async () => {
  vi.mocked(api.conceptUnderstanding).mockResolvedValue([]);
  mount("local");
  expect(await screen.findByText("知识卡片 · PaperCard")).toBeInTheDocument();
  expect(api.overview).toHaveBeenCalledWith("paper-1", "parse-1");
  await waitFor(() => expect(api.conceptUnderstanding).toHaveBeenCalled());
  expect(api.modelOverview).not.toHaveBeenCalled();
});

test("failed regeneration retains the last valid card and its own layout without claiming completion", async () => {
  vi.mocked(api.modelOverview).mockResolvedValue({
    ...completed,
    id: "failed-model-overview-2",
    display_result_id: "model-overview-1",
    status: "FAILED",
    error: "本次结果格式无效",
  });
  mount();
  expect(await screen.findByText("合成研究问题")).toBeInTheDocument();
  expect(screen.getByText("概览生成失败")).toBeInTheDocument();
  expect(screen.getByText("本次结果格式无效")).toBeInTheDocument();
  expect(
    screen.getByText(/以下显示上一次成功的知识卡片与图谱/),
  ).toBeInTheDocument();
  expect(
    await screen.findByTestId("shared-overview-graph"),
  ).toBeInTheDocument();
  expect(api.modelOverviewLayout).toHaveBeenCalledWith(
    "paper-1",
    "model-overview-1",
  );
  expect(api.generateModelOverview).not.toHaveBeenCalled();
});
