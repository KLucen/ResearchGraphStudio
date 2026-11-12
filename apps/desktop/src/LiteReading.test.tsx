import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import App from "./App";
import {
  api,
  request,
  type OverviewView,
  type LiteUsage,
  type KeywordView,
  type QAView,
  type SectionGuide,
  type PaperDetail,
} from "./api";
import { KnowledgeReading } from "./KnowledgeReading";
import { PaperOverview } from "./PaperOverview";
import { Papers } from "./Papers";
import { JobHistory } from "./JobHistory";
import { ZoteroImport } from "./ZoteroImport";

const renderer = vi.hoisted(() => ({ props: {} as Record<string, unknown> }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("./ForceGraph", () => ({
  ForceGraph: (props: Record<string, unknown>) => {
    renderer.props = props;
    return (
      <div data-testid="overview-graph">
        <button onClick={() => (props.onSelect as (id: string) => void)("n1")}>
          查看节点
        </button>
        <button onClick={() => (props.onEdge as (id: string) => void)("e1")}>
          查看关系
        </button>
        <button
          onClick={() =>
            (props.onPositions as (p: unknown) => void)([
              { node_id: "n1", x: 150, y: 220, pinned: true },
            ])
          }
        >
          移动节点
        </button>
      </div>
    );
  },
}));
vi.mock("./api", () => ({
  request: vi.fn(),
  api: {
    host: vi.fn(),
    health: vi.fn(),
    projects: vi.fn(),
    papers: vi.fn(),
    paper: vi.fn(),
    projectJobs: vi.fn(),
    jobs: vi.fn(),
    jobAction: vi.fn(),
    sections: vi.fn(),
    sectionGuide: vi.fn(),
    sectionGuides: vi.fn(),
    generateSectionGuide: vi.fn(),
    qa: vi.fn(),
    askQA: vi.fn(),
    search: vi.fn(),
    expandSearchKeywords: vi.fn(),
    keyword: vi.fn(),
    overview: vi.fn(),
    overviewLayout: vi.fn(),
    generateOverview: vi.fn(),
    saveOverviewLayout: vi.fn(),
    resetOverviewLayout: vi.fn(),
    liteUsage: vi.fn(),
    chunks: vi.fn(),
    importPdf: vi.fn(),
    restart: vi.fn(),
  },
}));

const usage: LiteUsage = {
  project_id: "p",
  paper_id: null,
  calls: 0,
  retry_count: 0,
  cache_hits: 0,
  input_tokens: 0,
  output_tokens: 0,
  total_tokens: 0,
  unknown_usage_calls: 0,
  calls_known: true,
  unrecorded_runs: 0,
  unattributed_runs: 0,
  estimated_usage_calls: 0,
  cost_estimate: 0,
  cost_known: true,
  by_kind: [],
};
const emptyOverview: OverviewView = {
  id: null,
  paper_id: "paper",
  document_version_id: "v",
  status: null,
  pdf_hash: null,
  input_hash: null,
  schema_version: null,
  prompt_version: null,
  provider_id: null,
  model_id: null,
  generated_at: null,
  cache_hit: false,
  graph_status: null,
  paper_card: null,
  graph: null,
  usage: null,
  job_id: null,
  error_code: null,
  error: null,
};
const completedOverview: OverviewView = {
  ...emptyOverview,
  id: "overview",
  status: "COMPLETED",
  cache_hit: true,
  paper_card: {
    research_question: "研究问题",
    motivation: "研究动机",
    method_summary: "方法概述",
    contributions: ["合成贡献"],
    main_findings: ["合成发现"],
    limitations: [],
  },
  graph: {
    nodes: [
      {
        id: "n1",
        type: "METHOD",
        label_zh: "合成方法",
        label_en: "Synthetic Method",
        description_zh: "简短方法描述",
        basis: "EXPLICIT",
      },
      {
        id: "n2",
        type: "FINDING",
        label_zh: "合成发现",
        label_en: null,
        description_zh: "简短发现描述",
        basis: "INFERRED",
      },
    ],
    edges: [
      {
        id: "e1",
        source: "n1",
        target: "n2",
        type: "YIELDS",
        basis: "EXPLICIT",
      },
    ],
  },
  usage: {
    input_tokens: 100,
    output_tokens: 40,
    total_tokens: 140,
    calls: 1,
    retry_count: 0,
    cost: null,
    usage_source: "provider",
  },
};

function mount(element: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>{element}</QueryClientProvider>,
    ),
  };
}
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(invoke).mockResolvedValue(undefined);
  localStorage.clear();
  vi.mocked(api.host).mockResolvedValue({
    running: true,
    data_dir: "lite-data",
    error: null,
  });
  vi.mocked(api.health).mockResolvedValue({
    status: "ok",
    version: "0.1.0",
    protocol_version: 1,
    schema_version: "lite0002",
    database: "ready",
    fts5: true,
  });
  vi.mocked(api.projects).mockResolvedValue({
    items: [
      {
        id: "p",
        name: "Lite project",
        description: "",
        experience_mode: "lite",
        created_at: "2026-11-09T00:00:00Z",
      },
    ],
    next_cursor: null,
  });
  vi.mocked(api.papers).mockResolvedValue({ items: [], next_cursor: null });
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [],
    next_cursor: null,
  });
  vi.mocked(api.jobs).mockResolvedValue([]);
  vi.mocked(api.liteUsage).mockResolvedValue(usage);
  vi.mocked(api.overview).mockResolvedValue(emptyOverview);
  vi.mocked(api.overviewLayout).mockResolvedValue({
    overview_result_id: "overview",
    positions: [{ node_id: "n1", x: 10, y: 20, pinned: true }],
    viewport: { x: -70, y: 45, zoom: 0.7 },
  });
  vi.mocked(api.saveOverviewLayout).mockImplementation(
    async (_paperId, value) => value,
  );
  vi.mocked(api.sections).mockResolvedValue({
    document_version_id: "v",
    sections: [
      {
        id: "s",
        title: "Results",
        ordinal: 0,
        role: "results",
        parent_id: null,
        level: 1,
        start_page: 1,
        end_page: 2,
        excluded: false,
        text: "Synthetic result paragraph",
        chunk_ids: ["c"],
      },
    ],
  });
  vi.mocked(api.sectionGuide).mockResolvedValue(null);
  vi.mocked(api.qa).mockResolvedValue([]);
  vi.mocked(api.askQA).mockResolvedValue({
    id: "qa-1",
    paper_id: "paper",
    document_version_id: "v",
    section_id: "s",
    scope: "section",
    question: "What is the method?",
    status: "PENDING",
    answer: null,
    usage: {
      input_tokens: null,
      output_tokens: null,
      total_tokens: null,
      calls: 0,
      retry_count: 0,
      cost: null,
      usage_source: "unknown",
    },
    source_hash: "source",
    input_hash: "input",
    prompt_version: "d01_grounded_qa_v1",
    schema_version: "qa_answer.v1",
    provider_id: "configured",
    model_id: "model",
    job_id: "job-qa",
    error_code: null,
    error: null,
    retrieval_spans: [],
    cache_hit: false,
  } satisfies QAView);
  vi.mocked(api.generateSectionGuide).mockResolvedValue({
    id: "guide",
    paper_id: "paper",
    document_version_id: "v",
    section_id: "s",
    depth: "standard",
    source_hash: "source",
    input_hash: "input",
    schema_version: "reading_guide.v1",
    prompt_version: "a01_section_guide_v1",
    provider_id: "configured",
    model_id: "model",
    status: "COMPLETED",
    guide: {
      section_id: "s",
      overview_zh: "本节概览",
      key_points: ["重点"],
      reading_questions: ["问题一", "问题二"],
      difficult_terms: [],
      evidence_span_ids: ["sp-1"],
      needs_more_context: false,
      caveats: [],
    },
    usage: {
      input_tokens: 20,
      output_tokens: 10,
      total_tokens: 30,
      calls: 1,
      retry_count: 0,
      cost: null,
      usage_source: "provider",
    },
    generated_at: "2026-11-09T00:00:00Z",
    cache_hit: false,
    job_id: null,
    error_code: null,
    error: null,
    stale_reason: null,
    evidence: [],
  });
  vi.mocked(request).mockResolvedValue([]);
});

test("Lite app separates projects, tasks and reading workspace", async () => {
  const user = userEvent.setup();
  mount(<App />);
  const projectButtons = await screen.findAllByRole("button", {
    name: "Lite project",
  });
  await user.click(projectButtons[0]);
  expect(
    await screen.findByRole("region", { name: "论文阅读工作区" }),
  ).toBeVisible();
  expect(screen.getByRole("button", { name: "任务记录" })).toBeVisible();
  expect(
    screen.queryByRole("button", {
      name: /Lint|Wiki|图谱与比较|笔记来源|问答与阅读知识/,
    }),
  ).not.toBeInTheDocument();
  expect(api.generateOverview).not.toHaveBeenCalled();
});
test("workspace task route shows jobs across projects", async () => {
  const user = userEvent.setup();
  vi.mocked(api.jobs).mockResolvedValue([
    {
      id: "job-global",
      kind: "pdf_import",
      project_id: "p",
      status: "running",
      stage: "parsing",
      attempt: 1,
      error: null,
      result: null,
      created_at: "2026-11-09T00:00:00Z",
      updated_at: "2026-11-09T00:00:00Z",
    },
  ]);
  mount(<App />);
  await user.click(await screen.findByRole("button", { name: "任务记录" }));
  expect(
    await screen.findByRole("heading", { name: "任务记录" }),
  ).toBeVisible();
  expect(screen.getAllByText(/Lite project/).length).toBeGreaterThanOrEqual(2);
  expect(screen.getByRole("article")).toHaveTextContent("正在处理");
});
test("local sections and explicit keyword search cause no model request", async () => {
  const user = userEvent.setup();
  vi.mocked(api.search).mockResolvedValue({
    query: "result",
    items: [
      {
        chunk_id: "c",
        section_id: "s",
        document_version_id: "v",
        paper_id: "paper",
        text: "Synthetic result paragraph",
        page_index: 1,
        page_label: "S-2",
        score: 1,
      },
    ],
  });
  mount(<KnowledgeReading versionId="v" paperId="paper" connected />);
  expect(await screen.findByText("本地索引已就绪：1 个章节。")).toBeVisible();
  expect(api.search).not.toHaveBeenCalled();
  await user.selectOptions(screen.getByLabelText("选择章节"), "s");
  await user.type(screen.getByLabelText("搜索论文原文"), "result");
  await user.click(screen.getByRole("button", { name: "本地搜索" }));
  expect(await screen.findByLabelText("本地检索结果")).toHaveTextContent(
    "Synthetic result paragraph",
  );
  expect(api.search).toHaveBeenCalledWith("paper", "result", "v", "s");
  expect(api.generateOverview).not.toHaveBeenCalled();
});
test("D02 keyword helper requires consent and reruns local search", async () => {
  const user = userEvent.setup();
  vi.mocked(api.search)
    .mockResolvedValueOnce({ query: "memory sharing", items: [] })
    .mockResolvedValueOnce({
      query: "shared memory",
      items: [
        {
          chunk_id: "c2",
          section_id: "s",
          document_version_id: "v",
          paper_id: "paper",
          text: "Shared memory improves coordination.",
          page_index: 2,
          page_label: "S-3",
          score: 1,
        },
      ],
    });
  vi.mocked(api.expandSearchKeywords).mockResolvedValue({
    id: "kw-1",
    paper_id: "paper",
    document_version_id: "v",
    section_id: "s",
    question: "memory sharing",
    local_hit_count: 0,
    source_hash: "source",
    input_hash: "input",
    schema_version: "search_keywords.v1",
    prompt_version: "d02_search_keywords_v1",
    provider_id: "synthetic",
    model_id: "synthetic",
    status: "COMPLETED",
    keywords: { english_queries: ["shared memory"] },
    usage: {
      input_tokens: 0,
      output_tokens: 0,
      total_tokens: 0,
      calls: 0,
      retry_count: 0,
      cost: null,
      usage_source: "unknown",
    },
    generated_at: null,
    cache_hit: false,
    job_id: null,
    error_code: null,
    error: null,
    stale_reason: null,
  } satisfies KeywordView);
  mount(<KnowledgeReading versionId="v" paperId="paper" connected />);
  await user.click(await screen.findByRole("button", { name: "Results" }));
  await user.type(screen.getByLabelText("搜索论文原文"), "memory sharing");
  await user.click(screen.getByRole("button", { name: "本地搜索" }));
  const helper = await screen.findByRole("region", {
    name: "英文关键词辅助",
  });
  const expand = within(helper).getByRole("button", {
    name: "使用英文关键词辅助",
  });
  expect(expand).toBeDisabled();
  await user.click(
    within(helper).getByRole("checkbox", {
      name: "允许本次生成英文关键词",
    }),
  );
  await user.click(expand);
  expect(api.expandSearchKeywords).toHaveBeenCalledExactlyOnceWith("paper", {
    document_version_id: "v",
    section_id: "s",
    question: "memory sharing",
    allow_network: true,
  });
  expect(
    await screen.findByRole("region", { name: "英文关键词检索结果" }),
  ).toHaveTextContent("Shared memory improves coordination.");
});
test("section guide requires an explicit click and keeps depth-specific status", async () => {
  const user = userEvent.setup();
  vi.mocked(api.sectionGuide).mockResolvedValue(null);
  const guide: SectionGuide = {
    id: "guide",
    paper_id: "paper",
    document_version_id: "v",
    section_id: "s",
    depth: "standard",
    source_hash: "source",
    input_hash: "input",
    schema_version: "reading_guide.v1",
    prompt_version: "a01_section_guide_v1",
    provider_id: "configured",
    model_id: "model",
    status: "COMPLETED",
    guide: {
      section_id: "s",
      overview_zh: "本节概览",
      key_points: ["重点"],
      reading_questions: ["问题一", "问题二"],
      difficult_terms: [],
      evidence_span_ids: ["sp-1"],
      needs_more_context: false,
      caveats: [],
    },
    usage: {
      input_tokens: 20,
      output_tokens: 10,
      total_tokens: 30,
      calls: 1,
      retry_count: 0,
      cost: null,
      usage_source: "provider",
    },
    generated_at: "2026-11-09T00:00:00Z",
    cache_hit: false,
    job_id: null,
    error_code: null,
    error: null,
    stale_reason: null,
    evidence: [],
  };
  vi.mocked(api.generateSectionGuide).mockResolvedValue(guide);
  mount(<KnowledgeReading versionId="v" paperId="paper" connected />);
  expect(await screen.findByText("本地索引已就绪：1 个章节。")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Results" }));
  expect(await screen.findByRole("region", { name: "章节导读" })).toBeVisible();
  expect(api.generateSectionGuide).not.toHaveBeenCalled();
  expect(api.sectionGuide).toHaveBeenCalledWith("paper", "s", "v", "standard");
  await user.click(screen.getByRole("checkbox"));
  await user.click(screen.getByRole("button", { name: "生成导读" }));
  expect(api.generateSectionGuide).toHaveBeenCalledWith(
    "paper",
    "s",
    "v",
    "standard",
    true,
    false,
    false,
  );
});
test("local QA requires a question and explicit model consent", async () => {
  const user = userEvent.setup();
  mount(<KnowledgeReading versionId="v" paperId="paper" connected />);
  await user.click(await screen.findByRole("button", { name: "Results" }));
  const panel = await screen.findByRole("region", { name: "局部证据问答" });
  const submit = within(panel).getByRole("button", { name: "提交问题" });
  expect(submit).toBeDisabled();
  await user.type(
    within(panel).getByLabelText("你的问题"),
    "What is the method?",
  );
  expect(submit).toBeDisabled();
  await user.click(
    within(panel).getByRole("checkbox", {
      name: "允许本次把检索片段发送给已配置模型",
    }),
  );
  await user.click(submit);
  expect(api.askQA).toHaveBeenCalledExactlyOnceWith("paper", {
    document_version_id: "v",
    section_id: "s",
    scope: "section",
    question: "What is the method?",
    allow_network: true,
  });
  expect(api.qa).toHaveBeenCalledWith("paper", "v", "s", "section");
});
test("offline local reader does not read or search", () => {
  mount(<KnowledgeReading versionId="v" paperId="paper" connected={false} />);
  expect(screen.getByRole("button", { name: "本地搜索" })).toBeDisabled();
  expect(api.sections).not.toHaveBeenCalled();
});
test("overview reads cache and saved layout without generating or rewriting it", async () => {
  vi.mocked(api.overview).mockResolvedValue(completedOverview);
  mount(
    <PaperOverview paperId="paper" revisionId="v" projectId="p" connected />,
  );
  expect(await screen.findByTestId("overview-graph")).toBeVisible();
  expect(renderer.props.layout).toMatchObject({
    zoom: 0.7,
    pan_x: -70,
    pan_y: 45,
    positions: [{ node_id: "n1", x: 10, y: 20, pinned: true }],
  });
  await new Promise((resolve) => setTimeout(resolve, 650));
  expect(api.generateOverview).not.toHaveBeenCalled();
  expect(api.saveOverviewLayout).not.toHaveBeenCalled();
});
test("overview layout is isolated by paper, revision and result", async () => {
  const user = userEvent.setup();
  const first = { ...completedOverview, id: "overview-a", paper_id: "paper-a" };
  const second = {
    ...completedOverview,
    id: "overview-b",
    paper_id: "paper-b",
  };
  vi.mocked(api.overview).mockImplementation(async (paperId) =>
    paperId === "paper-a" ? first : second,
  );
  vi.mocked(api.overviewLayout).mockImplementation(
    async (paperId, resultId) => ({
      overview_result_id: resultId,
      positions: [
        {
          node_id: "n1",
          x: paperId === "paper-a" ? 10 : 90,
          y: 20,
          pinned: true,
        },
      ],
      viewport: { x: paperId === "paper-a" ? -10 : -90, y: 5, zoom: 0.8 },
    }),
  );
  const mounted = mount(
    <PaperOverview
      paperId="paper-a"
      revisionId="v-a"
      projectId="p"
      connected
    />,
  );
  expect(await screen.findByTestId("overview-graph")).toBeVisible();
  expect(renderer.props.layout).toMatchObject({
    positions: [{ node_id: "n1", x: 10, y: 20, pinned: true }],
    pan_x: -10,
  });
  await user.click(screen.getByRole("button", { name: "移动节点" }));
  mounted.rerender(
    <QueryClientProvider client={mounted.client}>
      <PaperOverview
        paperId="paper-b"
        revisionId="v-b"
        projectId="p"
        connected
      />
    </QueryClientProvider>,
  );
  await waitFor(() =>
    expect(api.overviewLayout).toHaveBeenLastCalledWith(
      "paper-b",
      "overview-b",
    ),
  );
  await waitFor(() =>
    expect(renderer.props.layout).toMatchObject({
      positions: [{ node_id: "n1", x: 90, y: 20, pinned: true }],
      pan_x: -90,
    }),
  );
  await waitFor(() =>
    expect(api.saveOverviewLayout).toHaveBeenCalledExactlyOnceWith("paper-a", {
      overview_result_id: "overview-a",
      positions: [{ node_id: "n1", x: 150, y: 220, pinned: true }],
      viewport: { x: -10, y: 5, zoom: 0.8 },
    }),
  );
});
test("overview resets saved coordinates and camera only after successful local reset", async () => {
  const user = userEvent.setup();
  vi.mocked(api.overview).mockResolvedValue(completedOverview);
  vi.mocked(api.resetOverviewLayout).mockResolvedValue({
    overview_result_id: "overview",
    positions: [],
    viewport: null,
  });
  mount(
    <PaperOverview paperId="paper" revisionId="v" projectId="p" connected />,
  );
  expect(await screen.findByTestId("overview-graph")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "重置布局" }));
  await waitFor(() =>
    expect(renderer.props.layout).toEqual({
      version: 0,
      pan_x: 0,
      pan_y: 0,
      zoom: 1,
      positions: [],
    }),
  );
  expect(api.generateOverview).not.toHaveBeenCalled();
  expect(api.saveOverviewLayout).not.toHaveBeenCalled();
});
test("a new overview result loads its own camera and flushes only the previous result draft", async () => {
  const user = userEvent.setup();
  vi.mocked(api.overview).mockResolvedValue(completedOverview);
  vi.mocked(api.overviewLayout).mockImplementation(
    async (_paperId, resultId) => ({
      overview_result_id: resultId,
      positions: [
        {
          node_id: "n1",
          x: resultId === "overview" ? 10 : 80,
          y: 20,
          pinned: true,
        },
      ],
      viewport: { x: resultId === "overview" ? -70 : 250, y: 45, zoom: 0.7 },
    }),
  );
  const mounted = mount(
    <PaperOverview paperId="paper" revisionId="v" projectId="p" connected />,
  );
  await user.click(await screen.findByRole("button", { name: "移动节点" }));
  mounted.client.setQueryData(["overview", "paper", "v"], {
    ...completedOverview,
    id: "overview-next",
  });
  await waitFor(() =>
    expect(renderer.props.layout).toMatchObject({
      pan_x: 250,
      positions: [{ node_id: "n1", x: 80, y: 20, pinned: true }],
    }),
  );
  await waitFor(() =>
    expect(api.saveOverviewLayout).toHaveBeenCalledExactlyOnceWith("paper", {
      overview_result_id: "overview",
      positions: [{ node_id: "n1", x: 150, y: 220, pinned: true }],
      viewport: { x: -70, y: 45, zoom: 0.7 },
    }),
  );
});
test("pending overview completion refreshes usage and jobs immediately", async () => {
  vi.mocked(api.overview).mockResolvedValue({
    ...emptyOverview,
    id: "overview",
    status: "PENDING",
  });
  const mounted = mount(
    <PaperOverview paperId="paper" revisionId="v" projectId="p" connected />,
  );
  await screen.findByText(/正在生成概览…/);
  const invalidate = vi.spyOn(mounted.client, "invalidateQueries");
  mounted.client.setQueryData(["overview", "paper", "v"], completedOverview);
  await waitFor(() =>
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["lite-usage", "p"] }),
  );
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["jobs", "p"] });
  expect(api.generateOverview).not.toHaveBeenCalled();
});
test("overview requires explicit model consent and sends one generation request", async () => {
  const user = userEvent.setup();
  vi.mocked(api.generateOverview).mockResolvedValue({
    ...emptyOverview,
    id: "pending",
    status: "PENDING",
    job_id: "job",
  });
  mount(
    <PaperOverview paperId="paper" revisionId="v" projectId="p" connected />,
  );
  const button = await screen.findByRole("button", { name: "生成论文概览" });
  expect(button).toBeDisabled();
  await user.click(screen.getByRole("checkbox"));
  await user.click(button);
  expect(api.generateOverview).toHaveBeenCalledExactlyOnceWith(
    "paper",
    "v",
    true,
    false,
    false,
  );
  expect(await screen.findByText(/正在生成概览…/)).toBeVisible();
});
test("overview graph exposes bilingual details, relation and debounced layout save", async () => {
  const user = userEvent.setup();
  vi.mocked(api.overview).mockResolvedValue(completedOverview);
  mount(
    <PaperOverview paperId="paper" revisionId="v" projectId="p" connected />,
  );
  await user.click(await screen.findByRole("button", { name: "查看节点" }));
  const details = screen.getByLabelText("图谱详情");
  expect(details).toHaveTextContent("合成方法");
  expect(details).toHaveTextContent("Synthetic Method");
  expect(details).toHaveTextContent("简短方法描述");
  await user.click(screen.getByRole("button", { name: "查看关系" }));
  expect(details).toHaveTextContent("YIELDS");
  await user.click(screen.getByRole("button", { name: "移动节点" }));
  await waitFor(() => expect(api.saveOverviewLayout).toHaveBeenCalledTimes(1));
  expect(api.saveOverviewLayout).toHaveBeenLastCalledWith("paper", {
    overview_result_id: "overview",
    positions: [{ node_id: "n1", x: 150, y: 220, pinned: true }],
    viewport: { x: -70, y: 45, zoom: 0.7 },
  });
});
test("failed overview remains visible and does not automatically retry", async () => {
  vi.mocked(api.overview).mockResolvedValue({
    ...emptyOverview,
    id: "failed",
    status: "FAILED",
    error: "响应未通过校验",
  });
  mount(
    <PaperOverview paperId="paper" revisionId="v" projectId="p" connected />,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("响应未通过校验");
  expect(api.generateOverview).not.toHaveBeenCalled();
});
test("completed overview only regenerates after consent and sends force flag", async () => {
  const user = userEvent.setup();
  vi.mocked(api.overview).mockResolvedValue(completedOverview);
  vi.mocked(api.generateOverview).mockResolvedValue({
    ...completedOverview,
    id: "pending-regeneration",
    status: "PENDING",
    cache_hit: false,
    job_id: "job-regeneration",
  });
  const mounted = mount(
    <PaperOverview paperId="paper" revisionId="v" projectId="p" connected />,
  );
  const invalidate = vi.spyOn(mounted.client, "invalidateQueries");
  const regenerate = await screen.findByRole("button", {
    name: "重新生成概览",
  });
  expect(regenerate).toBeDisabled();
  expect(api.generateOverview).not.toHaveBeenCalled();
  await user.click(screen.getByRole("checkbox"));
  await user.click(regenerate);
  expect(api.generateOverview).toHaveBeenCalledExactlyOnceWith(
    "paper",
    "v",
    true,
    false,
    true,
  );
  await waitFor(() =>
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: ["lite-usage", "p"],
    }),
  );
  expect(await screen.findByText(/正在生成概览…/)).toBeVisible();
});
test("PDF selection remains an explicit native local action", async () => {
  const user = userEvent.setup();
  vi.mocked(api.importPdf).mockResolvedValue(null);
  mount(<Papers projectId="p" connected />);
  await user.selectOptions(screen.getByLabelText("保存方式"), "managed");
  await user.click(screen.getByRole("button", { name: "选择 PDF 导入" }));
  expect(api.importPdf).toHaveBeenCalledExactlyOnceWith("p", "managed");
  expect(api.generateOverview).not.toHaveBeenCalled();
});
test("paper classification is a local project preference", async () => {
  const user = userEvent.setup();
  vi.mocked(api.papers).mockResolvedValue({
    items: [
      {
        id: "paper",
        project_id: "p",
        title: "Synthetic paper",
        created_at: "2026-11-09T00:00:00Z",
      },
    ],
    next_cursor: null,
  });
  vi.mocked(api.paper).mockResolvedValue({
    paper: {
      id: "paper",
      project_id: "p",
      title: "Synthetic paper",
      created_at: "2026-11-09T00:00:00Z",
    },
    revisions: [],
    sources: [],
  });
  mount(<Papers projectId="p" connected initialPaperId="paper" />);
  await user.click(
    await screen.findByText("论文信息", { selector: "summary strong" }),
  );
  const category = await screen.findByRole("combobox", {
    name: "论文分类",
  });
  await user.selectOptions(category, "important");
  expect(localStorage.getItem("rgs.paper-categories.p")).toContain(
    '"paper":"important"',
  );
});
test("paper Zotero link uses the validated native command", async () => {
  const user = userEvent.setup();
  vi.mocked(api.papers).mockResolvedValue({
    items: [
      {
        id: "paper",
        project_id: "p",
        title: "Synthetic paper",
        created_at: "2026-11-09T00:00:00Z",
      },
    ],
    next_cursor: null,
  });
  vi.mocked(api.paper).mockResolvedValue({
    paper: {
      id: "paper",
      project_id: "p",
      title: "Synthetic paper",
      created_at: "2026-11-09T00:00:00Z",
    },
    revisions: [],
    sources: [],
    zotero_links: [
      {
        url: "zotero://select/library/items/PAPER001",
        item_key: "PAPER001",
        attachment_key: "ATTACH01",
      },
    ],
  });
  mount(<Papers projectId="p" connected initialPaperId="paper" />);
  await user.click(
    await screen.findByText("论文信息", { selector: "summary strong" }),
  );
  await user.click(
    await screen.findByRole("button", { name: "在 Zotero 中打开" }),
  );
  expect(invoke).toHaveBeenCalledExactlyOnceWith("open_zotero", {
    url: "zotero://select/library/items/PAPER001",
  });
  expect(api.generateOverview).not.toHaveBeenCalled();
});

function metadataPaper(id = "paper", revisionId = "v"): PaperDetail {
  return {
    paper: {
      id,
      project_id: "p",
      title:
        id === "paper" ? "Synthetic reading paper" : "Second reading paper",
      created_at: "2026-11-09T00:00:00Z",
    },
    revisions: [
      {
        id: revisionId,
        paper_id: id,
        sha256: "abcdef0123456789",
        parser_version: "fixture-parser",
        page_count: 4,
        warnings: ["Synthetic parsing warning"],
        created_at: "2026-11-09T00:00:00Z",
      },
      {
        id: `${revisionId}-old`,
        paper_id: id,
        sha256: "0123456789abcdef",
        parser_version: "fixture-parser",
        page_count: 3,
        warnings: [],
        created_at: "2026-11-08T00:00:00Z",
      },
    ],
    sources: [
      {
        id: `source-${id}`,
        revision_id: revisionId,
        path: "fixture/source.pdf",
        mode: "reference",
        generation: 1,
        last_check: null,
      },
    ],
    zotero_links: [
      {
        url: "zotero://select/library/items/PAPER001",
        item_key: "PAPER001",
        attachment_key: "ATTACH01",
      },
    ],
  };
}

test("reading workspace starts with three reading actions and ends with collapsed paper metadata", async () => {
  const user = userEvent.setup();
  vi.mocked(api.paper).mockResolvedValue(metadataPaper());
  mount(
    <Papers
      projectId="p"
      projectName="Fixture project"
      connected
      initialPaperId="paper"
    />,
  );
  const title = await screen.findByRole("heading", { name: "论文阅读工作区" });
  const reading = title.closest(".paper-reading")!;
  const header = title.closest("header")!;
  const metadata = screen
    .getByText("论文信息", { selector: "summary strong" })
    .closest("details")!;
  expect(reading.firstElementChild).toBe(header);
  expect(reading.lastElementChild).toBe(metadata);
  expect(metadata).not.toHaveAttribute("open");
  expect(within(header).getByText("Synthetic reading paper")).toBeVisible();
  expect(
    within(header).getByRole("navigation", { name: "论文阅读板块" }),
  ).toBeVisible();
  for (const name of ["论文概览", "章节精读", "论文问答"])
    expect(within(header).getByRole("button", { name })).toBeEnabled();
  expect(
    within(header).queryByRole("button", { name: "文献翻译" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText("Synthetic parsing warning")).not.toBeVisible();
  expect(screen.queryByText("CURRENT PROJECT")).not.toBeInTheDocument();
  expect(api.chunks).not.toHaveBeenCalled();
  await user.click(
    within(metadata).getByText("论文信息", { selector: "summary strong" }),
  );
  expect(screen.getByRole("combobox", { name: "论文分类" })).toBeVisible();
  expect(
    screen.getByRole("button", { name: "在 Zotero 中打开" }),
  ).toBeVisible();
  expect(screen.getByRole("combobox", { name: "附件修订" })).toBeVisible();
  expect(screen.getByRole("button", { name: "检查文件" })).toBeVisible();
  expect(screen.getByText("Synthetic parsing warning")).toBeVisible();
  expect(api.generateOverview).not.toHaveBeenCalled();
});

test("revision selection still drives reading and switching papers resets the collapsed metadata", async () => {
  const user = userEvent.setup();
  vi.mocked(api.paper).mockImplementation(async (id) =>
    metadataPaper(id, id === "paper" ? "v" : "v-second"),
  );
  const { client, rerender } = mount(
    <Papers projectId="p" connected initialPaperId="paper" />,
  );
  await user.click(
    await screen.findByText("论文信息", { selector: "summary strong" }),
  );
  await user.selectOptions(
    screen.getByRole("combobox", { name: "附件修订" }),
    "v-old",
  );
  await waitFor(() =>
    expect(api.overview).toHaveBeenCalledWith("paper", "v-old"),
  );
  await user.click(screen.getByRole("button", { name: "章节精读" }));
  await waitFor(() => expect(api.sections).toHaveBeenCalledWith("v-old"));
  rerender(
    <QueryClientProvider client={client}>
      <Papers projectId="p" connected initialPaperId="second" />
    </QueryClientProvider>,
  );
  await screen.findByText("Second reading paper", {
    selector: ".paper-workspace-paper",
  });
  expect(
    screen
      .getByText("论文信息", { selector: "summary strong" })
      .closest("details"),
  ).not.toHaveAttribute("open");
  expect(screen.getByRole("button", { name: "论文概览" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await waitFor(() =>
    expect(api.overview).toHaveBeenCalledWith("second", "v-second"),
  );
  expect(api.generateOverview).not.toHaveBeenCalled();
});

test("parsed original text stays local and loads only after opening both metadata and text", async () => {
  const user = userEvent.setup();
  vi.mocked(api.paper).mockResolvedValue(metadataPaper());
  vi.mocked(api.chunks).mockResolvedValue({
    items: [
      {
        id: "fixture-chunk",
        revision_id: "v",
        page_index: 0,
        page_label: "1",
        block_index: 0,
        text: "Synthetic original text",
        bbox: [],
      },
    ],
    next_cursor: null,
  });
  mount(<Papers projectId="p" connected initialPaperId="paper" />);
  await user.click(
    await screen.findByText("论文信息", { selector: "summary strong" }),
  );
  expect(api.chunks).not.toHaveBeenCalled();
  await user.click(
    screen.getByText("解析原文（按需查看）", { selector: "summary" }),
  );
  expect(await screen.findByText("Synthetic original text")).toBeVisible();
  expect(api.chunks).toHaveBeenCalledWith("v", 0);
  expect(api.generateOverview).not.toHaveBeenCalled();
});
test("local task retry keeps failed overview out of automatic model actions", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [
      {
        id: "local",
        kind: "pdf_import",
        project_id: "p",
        status: "failed",
        stage: "parsing",
        attempt: 1,
        error: "无可提取文本",
        result: null,
        created_at: "2026-11-09T00:00:00Z",
        updated_at: "2026-11-09T00:00:00Z",
      },
      {
        id: "overview",
        kind: "paper_overview",
        project_id: "p",
        status: "failed",
        stage: "generating",
        attempt: 1,
        error: "失败",
        result: null,
        created_at: "2026-11-09T00:00:00Z",
        updated_at: "2026-11-09T00:00:00Z",
      },
    ],
    next_cursor: null,
  });
  mount(<JobHistory projectId="p" connected />);
  expect(
    await screen.findAllByRole("button", { name: "重试本地处理" }),
  ).toHaveLength(1);
  expect(screen.getByText(/概览未自动重发/)).toBeVisible();
});
test.each([
  "queued",
  "running",
  "succeeded",
  "failed",
  "cancelled",
  "interrupted",
] as const)(
  "retired translation job stays read-only when %s",
  async (status) => {
    vi.mocked(api.jobs).mockResolvedValue([
      {
        id: "retired-translation",
        kind: "pdf_translation",
        project_id: "p",
        status,
        stage: "translating",
        attempt: 1,
        error: status === "failed" ? "Synthetic translation failure" : null,
        result: null,
        created_at: "2026-11-09T00:00:00Z",
        updated_at: "2026-11-09T00:00:00Z",
      },
    ]);
    mount(<JobHistory connected />);
    const label = await screen.findByText(/文献翻译（已停用）/);
    const history = within(label.closest("article")!);
    expect(
      history.getByText(
        "文献翻译功能已移除，此记录仅保留为历史，不会重新执行。",
      ),
    ).toBeVisible();
    expect(history.queryByRole("button")).not.toBeInTheDocument();
    expect(history.queryByRole("status")).not.toBeInTheDocument();
    expect(api.jobAction).not.toHaveBeenCalled();
  },
);

test("Zotero batch body contains local parsing choices only", async () => {
  const user = userEvent.setup();
  vi.mocked(request).mockImplementation(async (_method, path) =>
    path.includes("collections")
      ? [
          {
            key: "COLL0001",
            data: { name: "Synthetic Collection", parentCollection: false },
          },
        ]
      : path.endsWith("browse")
        ? {
            items: [
              {
                key: "PAPER001",
                title: "Synthetic paper",
                attachments: [
                  {
                    key: "ATTACH01",
                    title: "PDF",
                    filename: "synthetic.pdf",
                    available: true,
                  },
                ],
              },
            ],
            next_start: null,
          }
        : [],
  );
  mount(<ZoteroImport projectId="p" connected />);
  await user.click(screen.getByRole("button", { name: "连接并读取分类" }));
  await user.selectOptions(
    await screen.findByLabelText("Collection"),
    "COLL0001",
  );
  await user.click(
    await screen.findByRole("checkbox", { name: "选择附件 ATTACH01" }),
  );
  await user.click(
    screen.getByRole("button", { name: "仅解析 · 已选 1 个附件" }),
  );
  const call = vi
    .mocked(request)
    .mock.calls.find(
      (args) =>
        args[0] === "POST" && args[1] === "/api/v1/projects/p/zotero-imports",
    )!;
  expect(call[2]).toEqual({
    library: "users/0",
    collection_key: "COLL0001",
    selections: [{ item_key: "PAPER001", attachment_key: "ATTACH01" }],
    mode: "reference",
  });
  expect(request).toHaveBeenCalledWith(
    "POST",
    "/api/v1/integrations/zotero/browse",
    { library: "users/0", collection_key: "COLL0001", search: "", start: 0 },
  );
  expect(
    within(screen.getByRole("region", { name: "Zotero 批量导入" })).queryByText(
      /解析后直接建图|同意向已配置模型/,
    ),
  ).not.toBeInTheDocument();
});
