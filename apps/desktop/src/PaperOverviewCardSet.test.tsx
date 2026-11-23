import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { api, type OverviewView } from "./api";
import { PaperOverview } from "./PaperOverview";
import type { PaperCardSet } from "./paperCardSetTypes";

vi.mock("./api", () => ({
  api: {
    overview: vi.fn(),
    modelOverview: vi.fn(),
    generateOverview: vi.fn(),
    generateModelOverview: vi.fn(),
    recoverModelDocumentOutput: vi.fn(),
    overviewLayout: vi.fn(),
    modelOverviewLayout: vi.fn(),
    saveOverviewLayout: vi.fn(),
    saveModelOverviewLayout: vi.fn(),
    resetOverviewLayout: vi.fn(),
    resetModelOverviewLayout: vi.fn(),
    conceptUnderstanding: vi.fn(),
  },
}));

const cardSet: PaperCardSet = {
  schema_version: "paper-card-set-2",
  prompt_version: "paper-card-set-extract-1",
  article_overview_zh: "带逐条来源的新版文章总览。",
  overview_card_ids: ["card-1"],
  card_set_intro_zh: "本篇论文的合成卡片介绍。",
  coverage_notes: [],
  source_kind: "local_revision",
  source_id: "revision-1",
  source_fingerprint: "fingerprint-1",
  source_warnings: [],
  semantic_accuracy: "unverified",
  cards: [
    {
      id: "card-1",
      kind: "core_contribution",
      attribution: "AUTHOR",
      title_zh: "独立贡献卡片",
      title_en: null,
      body_zh: "作者报告的方法贡献。",
      reading_guide_zh: "核对方法的实际适用范围。",
      evidence: [
        {
          source_id: "s1",
          quote_en: "The paper proposes a synthetic method.",
          occurrence_index: 0,
          translation_zh: "本文提出一种合成方法。",
          translation_status: "auxiliary",
          position: {
            source_id: "s1",
            chapter_ref: "methods",
            chapter_title: "Methods",
            page_start: 3,
            page_end: 3,
            source_offset_start: 0,
            source_offset_end: 39,
            local_offsets: [],
            source_hash: "hash-1",
          },
        },
      ],
    },
  ],
};

const completed = {
  id: "result-1",
  paper_id: "paper-1",
  document_version_id: "revision-1",
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
  card_set: cardSet,
  usage: null,
  generated_at: "2026-11-21T08:00:00Z",
  cache_hit: false,
  job_id: "job-1",
  error_code: null,
  error: null,
} as OverviewView & { card_set: PaperCardSet };

function mount(source: "local" | "model" = "local") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PaperOverview
        paperId="paper-1"
        revisionId="revision-1"
        projectId="project-1"
        source={source}
        connected
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  vi.mocked(api.overview).mockResolvedValue(completed);
  vi.mocked(api.modelOverview).mockResolvedValue(completed);
});

test.each(["local", "model"] as const)(
  "%s overview reads the detailed card set without graph layout, concept or generation requests",
  async (source) => {
    mount(source);
    expect(await screen.findByText("带逐条来源的新版文章总览。")).toBeVisible();
    expect(screen.getByText("本篇论文的合成卡片介绍。")).toBeVisible();
    expect(
      screen.getByText("The paper proposes a synthetic method."),
    ).toBeVisible();
    expect(screen.queryByText(/LightGraph|轻量图谱/)).toBeNull();
    expect(api.overviewLayout).not.toHaveBeenCalled();
    expect(api.modelOverviewLayout).not.toHaveBeenCalled();
    expect(api.conceptUnderstanding).not.toHaveBeenCalled();
    expect(api.generateOverview).not.toHaveBeenCalled();
    expect(api.generateModelOverview).not.toHaveBeenCalled();
  },
);

test("the old overview is treated as ungenerated and never displayed as a new source-backed card set", async () => {
  vi.mocked(api.overview).mockResolvedValue({
    ...completed,
    schema_version: "paper_overview_graph.v1",
    card_set: undefined,
    paper_card: {
      research_question: "PRIVATE_OLD_OVERVIEW",
      motivation: "old",
      method_summary: "old",
      contributions: [],
      main_findings: [],
      limitations: [],
    },
  } as OverviewView);
  mount();
  expect(await screen.findByText(/尚未生成新版论文卡片集/)).toBeVisible();
  expect(screen.queryByText("PRIVATE_OLD_OVERVIEW")).toBeNull();
  expect(screen.queryByRole("heading", { name: "文章总览" })).toBeNull();
  expect(screen.getByRole("button", { name: "生成论文卡片集" })).toBeDisabled();
  expect(api.generateOverview).not.toHaveBeenCalled();
});

test("new generation requires explicit consent and uses the selected parser route exactly once", async () => {
  vi.mocked(api.modelOverview).mockResolvedValue(null);
  vi.mocked(api.generateModelOverview).mockResolvedValue({
    ...completed,
    status: "PENDING",
    card_set: null,
  } as OverviewView);
  mount("model");
  const button = await screen.findByRole("button", { name: "生成论文卡片集" });
  expect(button).toBeDisabled();
  await userEvent.click(
    screen.getByRole("checkbox", { name: /允许向已配置模型发送本篇论文内容/ }),
  );
  await userEvent.click(button);
  await waitFor(() =>
    expect(api.generateModelOverview).toHaveBeenCalledExactlyOnceWith(
      "paper-1",
      "revision-1",
      true,
      false,
      false,
    ),
  );
  expect(api.generateOverview).not.toHaveBeenCalled();
  expect(await screen.findByText("任务进行中：论文卡片集生成")).toBeVisible();
});

test("failed new output shows its failure without resurrecting an earlier card set", async () => {
  vi.mocked(api.modelOverview).mockResolvedValue({
    ...completed,
    status: "FAILED",
    card_set: null,
    display_result_id: "old-result",
    error: "来源已变化",
  } as OverviewView);
  mount("model");
  expect(await screen.findByText("卡片集生成失败")).toBeVisible();
  expect(screen.getByText("来源已变化")).toBeVisible();
  expect(screen.queryByText("带逐条来源的新版文章总览。")).toBeNull();
  expect(screen.queryByText(/上一次成功/)).toBeNull();
  expect(api.generateModelOverview).not.toHaveBeenCalled();
});

test("model card recovery is explicit, local and displayed as partial", async () => {
  const user = userEvent.setup();
  const recoverySummary = {
    original_cards: 3,
    retained_cards: 1,
    excluded_cards: 2,
    invalid_evidence: 2,
  };
  const failed: OverviewView = {
    ...completed,
    status: "FAILED",
    card_set: null,
    local_recovery_available: true,
    recovery_summary: recoverySummary,
  };
  vi.mocked(api.modelOverview).mockResolvedValue(failed);
  vi.mocked(api.recoverModelDocumentOutput).mockImplementation(async () => {
    vi.mocked(api.modelOverview).mockResolvedValue({
      ...failed,
      status: "PARTIAL",
      card_set: cardSet,
      local_recovery_available: false,
    });
    return {
      id: "result-1",
      import_session_id: "import-1",
      parse_id: "revision-1",
      item_kind: "paper_overview",
      status: "partial",
      output_json: null,
      error: null,
      error_code: null,
    };
  });
  mount("model");

  const recover = await screen.findByRole("button", {
    name: "本机恢复已校验卡片",
  });
  expect(screen.getByText(/本机可恢复 1 \/ 3 张卡片/)).toBeVisible();
  expect(api.recoverModelDocumentOutput).not.toHaveBeenCalled();
  await user.click(recover);

  expect(await screen.findByText(/本机部分恢复 · 已校验 1 \/ 3/)).toBeVisible();
  expect(screen.getByRole("heading", { name: "独立贡献卡片" })).toBeVisible();
  expect(api.recoverModelDocumentOutput).toHaveBeenCalledExactlyOnceWith(
    "paper-1",
    "result-1",
  );
  expect(api.generateModelOverview).not.toHaveBeenCalled();
});
