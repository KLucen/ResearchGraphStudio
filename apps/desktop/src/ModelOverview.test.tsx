import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { api, type OverviewView } from "./api";
import { PaperOverview } from "./PaperOverview";
import { syntheticCardSet } from "./paperCardSetFixtures";

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

const completed: OverviewView = {
  id: "model-overview-1",
  paper_id: "paper-1",
  document_version_id: "parse-1",
  pdf_hash: "",
  input_hash: "",
  schema_version: "paper-card-set-2",
  prompt_version: "paper-card-set-extract-1",
  provider_id: "synthetic",
  model_id: "synthetic",
  status: "COMPLETED",
  graph_status: "NOT_ENOUGH_INFO",
  paper_card: null,
  graph: null,
  card_set: { ...syntheticCardSet(), source_kind: "model_parse" },
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

test("model card set uses model parser reads and no graph, concept or model generation side effects", async () => {
  mount();
  expect(
    await screen.findByRole("heading", { name: "文章总览" }),
  ).toBeVisible();
  expect(
    screen.getByText("这篇合成文章研究共享记忆方法的运行效率。"),
  ).toBeVisible();
  expect(screen.getByText(/依据已保存的模型解析材料/)).toBeVisible();
  expect(api.modelOverview).toHaveBeenCalledWith("paper-1", "parse-1");
  expect(api.overview).not.toHaveBeenCalled();
  expect(api.conceptUnderstanding).not.toHaveBeenCalled();
  expect(api.modelOverviewLayout).not.toHaveBeenCalled();
  expect(api.generateModelOverview).not.toHaveBeenCalled();
});

test("unselected model cards remain ungenerated until explicit consent and action", async () => {
  vi.mocked(api.modelOverview).mockResolvedValue(null);
  vi.mocked(api.generateModelOverview).mockResolvedValue({
    ...completed,
    status: "PENDING",
    card_set: null,
  });
  mount();
  expect(await screen.findByText(/尚未生成新版论文卡片集/)).toBeVisible();
  const button = screen.getByRole("button", { name: "生成论文卡片集" });
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

test("failed regeneration reports its error without reviving old graph or cards", async () => {
  vi.mocked(api.modelOverview).mockResolvedValue({
    ...completed,
    id: "failed-model-overview-2",
    display_result_id: "model-overview-1",
    status: "FAILED",
    error: "本次结果格式无效",
  });
  mount();
  expect(await screen.findByText("卡片集生成失败")).toBeVisible();
  expect(screen.getByText("本次结果格式无效")).toBeVisible();
  expect(
    screen.queryByRole("heading", { name: "文章总览" }),
  ).not.toBeInTheDocument();
  expect(api.modelOverviewLayout).not.toHaveBeenCalled();
  expect(api.generateModelOverview).not.toHaveBeenCalled();
});

test("a failed retry can display only the earlier explicitly recovered partial", async () => {
  vi.mocked(api.modelOverview).mockResolvedValue({
    ...completed,
    id: "failed-model-overview-2",
    display_result_id: "recovered-model-overview-1",
    display_recovery_summary: {
      original_cards: 2,
      retained_cards: 1,
      excluded_cards: 1,
      invalid_evidence: 1,
    },
    status: "FAILED",
    error: "本次结果格式无效",
  });
  mount();
  expect(await screen.findByText("本次结果格式无效")).toBeVisible();
  expect(
    screen.getByText(/上一次在本机部分恢复的卡片，已校验 1 \/ 2 张/),
  ).toBeVisible();
  expect(screen.getByRole("heading", { name: "文章总览" })).toBeVisible();
  expect(api.generateModelOverview).not.toHaveBeenCalled();
});
