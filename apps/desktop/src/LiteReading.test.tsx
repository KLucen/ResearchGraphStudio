import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import App from "./App";
import { api, request, type OverviewView, type LiteUsage } from "./api";
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
    search: vi.fn(),
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
    schema_version: "lite0001",
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
  vi.mocked(request).mockResolvedValue([]);
});

test("Lite app has only projects, reading and settings routes", async () => {
  const user = userEvent.setup();
  mount(<App />);
  await user.click(await screen.findByRole("button", { name: /Lite project/ }));
  expect(
    await screen.findByRole("region", { name: "文献与阅读" }),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", {
      name: /Lint|Wiki|图谱与比较|笔记来源|问答与阅读知识/,
    }),
  ).not.toBeInTheDocument();
  expect(api.generateOverview).not.toHaveBeenCalled();
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
  mount(<Papers projectId="p" connected />);
  await user.click(
    await screen.findByRole("button", { name: "Synthetic paper" }),
  );
  await user.click(
    await screen.findByRole("button", { name: "在 Zotero 中打开" }),
  );
  expect(invoke).toHaveBeenCalledExactlyOnceWith("open_zotero", {
    url: "zotero://select/library/items/PAPER001",
  });
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
