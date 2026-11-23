import {
  act,
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import App from "./App";
import { archiveApi } from "./archiveApi";
import {
  api,
  request,
  type OverviewView,
  type LiteUsage,
  type KeywordView,
  type QAView,
  type PaperDetail,
  type Structure,
  type SearchResult,
} from "./api";
import { KnowledgeReading } from "./KnowledgeReading";
import { PaperOverview } from "./PaperOverview";
import { syntheticCardSet } from "./paperCardSetFixtures";
import { Papers } from "./Papers";
import { JobHistory } from "./JobHistory";
import { ZoteroImport } from "./ZoteroImport";
import {
  readingSource,
  readingComplete,
  readingState,
  readingConcept,
} from "./closeReadingFixtures";
import {
  paperReadingDocument,
  paperReadingComplete,
} from "./paperReadingFixtures";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("./archiveApi", async (original) => ({
  ...(await original<typeof import("./archiveApi")>()),
  archiveApi: { stage: vi.fn() },
}));
vi.mock("./api", () => ({
  request: vi.fn(),
  defaultPostImportPlan: () => ({
    parse: false,
    overview: true,
    reading: false,
    translation_mode: "none",
    modality: "auto",
    extract_formulas: true,
    extract_tables: true,
    allow_network: false,
  }),
  api: {
    host: vi.fn(),
    health: vi.fn(),
    projects: vi.fn(),
    papers: vi.fn(),
    paper: vi.fn(),
    importSessions: vi.fn(),
    modelDocumentParse: vi.fn(),
    modelDocumentOutputs: vi.fn(),
    importSession: vi.fn(),
    job: vi.fn(),
    retryImportItem: vi.fn(),
    modelChapterReadingStates: vi.fn(),
    saveModelChapterReadingState: vi.fn(),
    updateModelDocumentSegment: vi.fn(),
    updateModelDocumentOutput: vi.fn(),
    updatePaper: vi.fn(),
    parsePaper: vi.fn(),
    clearPaperLegacyContent: vi.fn(),
    deletePaper: vi.fn(),
    projectJobs: vi.fn(),
    jobs: vi.fn(),
    jobsPage: vi.fn(),
    jobAction: vi.fn(),
    sections: vi.fn(),
    readingDocument: vi.fn(),
    refreshReadingDocument: vi.fn(),
    paperReadingNotes: vi.fn(),
    generatePaperReadingNotes: vi.fn(),
    sectionGuide: vi.fn(),
    sectionGuides: vi.fn(),
    generateSectionGuide: vi.fn(),
    conceptUnderstanding: vi.fn(),
    saveConceptUnderstanding: vi.fn(),
    sectionParagraphs: vi.fn(),
    closeReading: vi.fn(),
    generateCloseReading: vi.fn(),
    readingState: vi.fn(),
    saveReadingState: vi.fn(),
    saveReadingProgress: vi.fn(),
    understandingCheck: vi.fn(),
    generateUnderstandingCheck: vi.fn(),
    qa: vi.fn(),
    askQA: vi.fn(),
    search: vi.fn(),
    expandSearchKeywords: vi.fn(),
    keyword: vi.fn(),
    overview: vi.fn(),
    modelOverview: vi.fn(),
    overviewLayout: vi.fn(),
    generateOverview: vi.fn(),
    saveOverviewLayout: vi.fn(),
    resetOverviewLayout: vi.fn(),
    liteUsage: vi.fn(),
    chunks: vi.fn(),
    selectPdfImport: vi.fn(),
    submitPdfImport: vi.fn(),
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
  schema_version: "paper-card-set-2",
  prompt_version: "paper-card-set-extract-1",
  paper_card: null,
  graph: null,
  card_set: {
    ...syntheticCardSet(),
    cards: syntheticCardSet().cards.map((card) =>
      card.kind === "key_concept" ? { ...card, id: "n1" } : card,
    ),
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
  vi.mocked(api.importSessions).mockResolvedValue([]);
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [],
    next_cursor: null,
  });
  vi.mocked(api.jobs).mockResolvedValue([]);
  vi.mocked(api.jobsPage).mockImplementation(async () => ({
    items: await api.jobs(),
    next_cursor: null,
  }));
  vi.mocked(api.liteUsage).mockResolvedValue(usage);
  vi.mocked(api.overview).mockResolvedValue(emptyOverview);
  vi.mocked(api.modelOverview).mockResolvedValue(null);
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
  vi.mocked(api.readingDocument).mockResolvedValue(paperReadingDocument);
  vi.mocked(api.paperReadingNotes).mockResolvedValue(paperReadingComplete);
  vi.mocked(api.importSession).mockRejectedValue(
    new Error("No active fixture import"),
  );
  vi.mocked(api.modelChapterReadingStates).mockResolvedValue({
    parse_id: "model-parse",
    items: [],
  });
  vi.mocked(api.conceptUnderstanding).mockResolvedValue([]);
  vi.mocked(api.sectionParagraphs).mockResolvedValue(readingSource);
  vi.mocked(api.closeReading).mockResolvedValue(readingComplete);
  vi.mocked(api.readingState).mockResolvedValue(readingState);
  vi.mocked(api.understandingCheck).mockResolvedValue(null);
  vi.mocked(api.saveConceptUnderstanding).mockImplementation(
    async (_paper, _node, body) => ({ ...readingConcept, ...body }),
  );
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

test("project creation dialog is modal and closes on Escape", async () => {
  const user = userEvent.setup();
  const showModal = vi.spyOn(HTMLDialogElement.prototype, "showModal");
  mount(<App />);

  await user.click(await screen.findByTitle("新建研究项目"));
  const dialog = await screen.findByRole("dialog", { name: "新建研究项目" });
  await waitFor(() => expect(showModal).toHaveBeenCalledExactlyOnceWith());
  expect(dialog).toHaveAttribute("open");

  fireEvent(dialog, new Event("cancel", { cancelable: true }));
  expect(
    screen.queryByRole("dialog", { name: "新建研究项目" }),
  ).not.toBeInTheDocument();
});

test("paper import dialog is modal and closes on Escape", async () => {
  const user = userEvent.setup();
  const showModal = vi.spyOn(HTMLDialogElement.prototype, "showModal");
  mount(<App />);

  await user.click(await screen.findByRole("button", { name: "Lite project" }));
  await user.click(
    await screen.findByRole("button", { name: "向Lite project导入论文" }),
  );
  const dialog = await screen.findByRole("dialog", { name: "导入论文" });
  await waitFor(() => expect(showModal).toHaveBeenCalledExactlyOnceWith());
  expect(dialog).toHaveAttribute("open");
  expect(dialog).toHaveClass("import-dialog");

  fireEvent(dialog, new Event("cancel", { cancelable: true }));
  expect(
    screen.queryByRole("dialog", { name: "导入论文" }),
  ).not.toBeInTheDocument();
});

test("sidebar refreshes papers after an import worker commits the new row", async () => {
  const first = {
    id: "paper-1",
    project_id: "p",
    title: "First paper",
    created_at: "2026-11-09T00:00:00Z",
  };
  const second = {
    id: "paper-2",
    project_id: "p",
    title: "Second paper",
    created_at: "2026-11-10T00:00:00Z",
  };
  let published = false;
  vi.mocked(api.papers).mockImplementation(async () => ({
    items: published ? [first, second] : [first],
    next_cursor: null,
  }));
  const mounted = mount(<App />);
  expect(await screen.findByTitle("First paper")).toBeVisible();
  expect(screen.queryByTitle("Second paper")).not.toBeInTheDocument();

  published = true;
  await act(async () => {
    mounted.client.setQueryData(
      ["jobs", "global"],
      [
        {
          id: "job-import",
          kind: "pdf_import",
          project_id: "p",
          status: "succeeded",
          stage: "published",
          attempt: 1,
          error: null,
          result: { paper_id: second.id },
          created_at: "2026-11-10T00:00:00Z",
          updated_at: "2026-11-10T00:00:01Z",
        },
      ],
    );
  });
  expect(await screen.findByTitle("Second paper")).toBeVisible();
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
test("section guide and separate understanding screens are absent from normal reading", async () => {
  const user = userEvent.setup();
  mount(<KnowledgeReading versionId="v" paperId="paper" connected />);
  await user.click(await screen.findByRole("button", { name: "Results" }));
  expect(
    screen.queryByRole("region", { name: "章节导读" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "小节导读 A01" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "理解状态与旧笔记" }),
  ).not.toBeInTheDocument();
  expect(api.sectionGuide).not.toHaveBeenCalled();
  expect(api.generateSectionGuide).not.toHaveBeenCalled();
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

test("directory replacement clears a missing selected chapter and all consent before a stale form can send", async () => {
  const user = userEvent.setup();
  const onSectionChange = vi.fn();
  vi.mocked(api.search).mockResolvedValue({ query: "old memory", items: [] });
  const mounted = mount(
    <KnowledgeReading
      versionId="v"
      paperId="paper"
      connected
      initialSectionId="s"
      onSectionChange={onSectionChange}
    />,
  );
  const qa = await screen.findByRole("region", { name: "局部证据问答" });
  await user.type(
    within(qa).getByLabelText("你的问题"),
    "Explain the old section.",
  );
  await user.click(
    within(qa).getByRole("checkbox", {
      name: "允许本次把检索片段发送给已配置模型",
    }),
  );
  await user.type(screen.getByLabelText("搜索论文原文"), "old memory");
  await user.click(screen.getByRole("button", { name: "本地搜索" }));
  const helper = await screen.findByRole("region", { name: "英文关键词辅助" });
  await user.click(
    within(helper).getByRole("checkbox", { name: "允许本次生成英文关键词" }),
  );
  const submit = within(qa).getByRole("button", { name: "提交问题" });
  expect(submit).toBeEnabled();
  const replacement = structuredClone(
    mounted.client.getQueryData<Structure>(["sections", "v"])!,
  );
  replacement.sections[0].id = "s-new";
  replacement.sections[0].title = "Updated Methods";
  vi.mocked(api.sections).mockResolvedValue(replacement);
  // The cache changes before React has committed its new directory. A stale
  // DOM form still cannot send the old id because mutation entry rechecks it.
  act(() => {
    mounted.client.setQueryData(["sections", "v"], replacement);
    fireEvent.submit(submit.closest("form")!);
  });
  expect(
    await screen.findByText(/章节目录已更新，原先选择的章节/),
  ).toBeVisible();
  expect(screen.getByLabelText("选择章节")).toHaveValue("");
  expect(screen.getByLabelText("搜索论文原文")).toHaveValue("");
  expect(
    screen.queryByRole("region", { name: "局部证据问答" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("region", { name: "英文关键词辅助" }),
  ).not.toBeInTheDocument();
  expect(onSectionChange).toHaveBeenCalledWith("");
  expect(api.askQA).not.toHaveBeenCalled();
  expect(api.generateSectionGuide).not.toHaveBeenCalled();
  expect(api.expandSearchKeywords).not.toHaveBeenCalled();
  await user.selectOptions(screen.getByLabelText("选择章节"), "s-new");
  expect(
    screen.queryByText(/章节目录已更新，原先选择的章节/),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("checkbox", {
      name: "允许本次把检索片段发送给已配置模型",
    }),
  ).not.toBeChecked();
  expect(screen.getByRole("button", { name: "提交问题" })).toBeDisabled();
});

test("an obsolete graph chapter does not fetch current QA or reuse old selected spans, and its notice survives remount", async () => {
  const user = userEvent.setup();
  const mounted = mount(
    <KnowledgeReading
      versionId="v"
      paperId="paper"
      connected
      panel="qa"
      initialSectionId="historical-section"
      selectedSpanIds={["old-span"]}
    />,
  );
  expect(await screen.findByText(/历史图谱或链接可能指向旧解析/)).toBeVisible();
  expect(screen.getByLabelText("选择章节")).toHaveValue("");
  expect(api.qa).not.toHaveBeenCalled();
  expect(api.askQA).not.toHaveBeenCalled();
  mounted.rerender(
    <QueryClientProvider client={mounted.client}>
      <KnowledgeReading
        key="remounted-reader"
        versionId="v"
        paperId="paper"
        connected
        panel="qa"
        selectedSpanIds={["old-span"]}
      />
    </QueryClientProvider>,
  );
  expect(screen.getByText(/历史图谱或链接可能指向旧解析/)).toBeVisible();
  await user.selectOptions(screen.getByLabelText("选择章节"), "s");
  const qa = await screen.findByRole("region", { name: "局部证据问答" });
  expect(within(qa).getByLabelText("作用范围")).toHaveValue("section");
  expect(
    within(qa).getByRole("option", { name: /已选原文片段/ }),
  ).toBeDisabled();
  expect(
    screen.queryByText(/历史图谱或链接可能指向旧解析/),
  ).not.toBeInTheDocument();
  expect(api.askQA).not.toHaveBeenCalled();
});

test("a keyword result arriving after its chapter disappears cannot restore old helper state or run more searches", async () => {
  const user = userEvent.setup();
  let finishExpansion!: (value: KeywordView) => void;
  const pending = new Promise<KeywordView>((resolve) => {
    finishExpansion = resolve;
  });
  vi.mocked(api.search).mockResolvedValue({ query: "old memory", items: [] });
  vi.mocked(api.expandSearchKeywords).mockReturnValue(pending);
  const mounted = mount(
    <KnowledgeReading
      versionId="v"
      paperId="paper"
      connected
      initialSectionId="s"
    />,
  );
  await screen.findByText("本地索引已就绪：1 个章节。");
  await user.type(screen.getByLabelText("搜索论文原文"), "old memory");
  await user.click(screen.getByRole("button", { name: "本地搜索" }));
  const helper = await screen.findByRole("region", { name: "英文关键词辅助" });
  await user.click(
    within(helper).getByRole("checkbox", { name: "允许本次生成英文关键词" }),
  );
  await user.click(
    within(helper).getByRole("button", { name: "使用英文关键词辅助" }),
  );
  expect(api.expandSearchKeywords).toHaveBeenCalledTimes(1);
  const replacement = structuredClone(
    mounted.client.getQueryData<Structure>(["sections", "v"])!,
  );
  replacement.sections[0].id = "replacement";
  act(() => {
    mounted.client.setQueryData(["sections", "v"], replacement);
  });
  await screen.findByText(/章节目录已更新，原先选择的章节/);
  await act(async () => {
    finishExpansion({
      id: "late-keywords",
      paper_id: "paper",
      document_version_id: "v",
      section_id: "s",
      question: "old memory",
      local_hit_count: 0,
      source_hash: "source",
      input_hash: "input",
      schema_version: "search_keywords.v1",
      prompt_version: "d02_search_keywords_v1",
      provider_id: "synthetic",
      model_id: "synthetic",
      status: "COMPLETED",
      keywords: { english_queries: ["obsolete expansion"] },
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
    });
    await pending;
  });
  expect(api.search).toHaveBeenCalledTimes(1);
  expect(api.keyword).not.toHaveBeenCalled();
  expect(
    screen.queryByRole("region", { name: "英文关键词辅助" }),
  ).not.toBeInTheDocument();
  expect(api.askQA).not.toHaveBeenCalled();
});

test("a late QA response remains under its original section after the directory and selection change", async () => {
  const user = userEvent.setup();
  let finishQA!: (value: QAView) => void;
  const pending = new Promise<QAView>((resolve) => {
    finishQA = resolve;
  });
  vi.mocked(api.askQA).mockReturnValue(pending);
  const mounted = mount(
    <KnowledgeReading
      versionId="v"
      paperId="paper"
      connected
      initialSectionId="s"
    />,
  );
  const qa = await screen.findByRole("region", { name: "局部证据问答" });
  await user.type(
    within(qa).getByLabelText("你的问题"),
    "Explain the old section.",
  );
  await user.click(
    within(qa).getByRole("checkbox", {
      name: "允许本次把检索片段发送给已配置模型",
    }),
  );
  await user.click(within(qa).getByRole("button", { name: "提交问题" }));
  expect(api.askQA).toHaveBeenCalledTimes(1);
  const replacement = structuredClone(
    mounted.client.getQueryData<Structure>(["sections", "v"])!,
  );
  replacement.sections[0].id = "new-current";
  act(() => {
    mounted.client.setQueryData(["sections", "v"], replacement);
  });
  await screen.findByText(/章节目录已更新，原先选择的章节/);
  await user.selectOptions(screen.getByLabelText("选择章节"), "new-current");
  const response: QAView = {
    id: "late-answer",
    paper_id: "paper",
    document_version_id: "v",
    section_id: "s",
    scope: "section",
    question: "Explain the old section.",
    status: "COMPLETED",
    answer: {
      answer_zh: "仅属于旧章节的回答",
      evidence_citations: [],
      insufficient_evidence: true,
      uncertainty_zh: "synthetic",
      suggest_expand_scope: false,
    },
    usage: {
      input_tokens: 0,
      output_tokens: 0,
      total_tokens: 0,
      calls: 0,
      retry_count: 0,
      cost: null,
      usage_source: "unknown",
    },
    source_hash: "old-source",
    input_hash: "old-input",
    prompt_version: "d01_grounded_qa_v1",
    schema_version: "qa_answer.v1",
    provider_id: "synthetic",
    model_id: "synthetic",
    job_id: null,
    error_code: null,
    error: null,
    retrieval_spans: [],
    cache_hit: false,
  };
  await act(async () => {
    finishQA(response);
    await pending;
  });
  expect(
    mounted.client.getQueryData<QAView[]>([
      "paper-qa",
      "paper",
      "v",
      "s",
      "section",
      "",
    ]),
  ).toEqual([response]);
  expect(
    mounted.client.getQueryData<QAView[]>([
      "paper-qa",
      "paper",
      "v",
      "new-current",
      "section",
      "",
    ]),
  ).toEqual([]);
  expect(screen.queryByText("仅属于旧章节的回答")).not.toBeInTheDocument();
  expect(api.askQA).toHaveBeenCalledTimes(1);
});

function addSecondValidSection(client: QueryClient) {
  const structure = structuredClone(
    client.getQueryData<Structure>(["sections", "v"])!,
  );
  structure.sections.push({
    ...structure.sections[0],
    id: "s2",
    title: "Methods",
    ordinal: 1,
  });
  act(() => {
    client.setQueryData(["sections", "v"], structure);
  });
}

test("an old expanded search cannot publish into another still-valid section", async () => {
  const user = userEvent.setup();
  let finishExpanded!: (value: SearchResult) => void;
  const pending = new Promise<SearchResult>((resolve) => {
    finishExpanded = resolve;
  });
  vi.mocked(api.search)
    .mockResolvedValueOnce({ query: "memory", items: [] })
    .mockReturnValueOnce(pending)
    .mockResolvedValue({ query: "memory", items: [] });
  vi.mocked(api.expandSearchKeywords).mockResolvedValue({
    id: "old-keywords",
    paper_id: "paper",
    document_version_id: "v",
    section_id: "s",
    question: "memory",
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
  });
  const mounted = mount(
    <KnowledgeReading
      versionId="v"
      paperId="paper"
      connected
      initialSectionId="s"
    />,
  );
  await screen.findByText("本地索引已就绪：1 个章节。");
  addSecondValidSection(mounted.client);
  await user.type(screen.getByLabelText("搜索论文原文"), "memory");
  await user.click(screen.getByRole("button", { name: "本地搜索" }));
  const oldHelper = await screen.findByRole("region", {
    name: "英文关键词辅助",
  });
  await user.click(
    within(oldHelper).getByRole("checkbox", { name: "允许本次生成英文关键词" }),
  );
  await user.click(
    within(oldHelper).getByRole("button", { name: "使用英文关键词辅助" }),
  );
  await waitFor(() => expect(api.search).toHaveBeenCalledTimes(2));
  await user.selectOptions(screen.getByLabelText("选择章节"), "s2");
  await user.click(screen.getByRole("button", { name: "本地搜索" }));
  const newHelper = await screen.findByRole("region", {
    name: "英文关键词辅助",
  });
  await user.click(
    within(newHelper).getByRole("checkbox", { name: "允许本次生成英文关键词" }),
  );
  await act(async () => {
    finishExpanded({
      query: "shared memory",
      items: [
        {
          chunk_id: "old-result",
          section_id: "s",
          document_version_id: "v",
          paper_id: "paper",
          text: "Old section expanded result",
          page_index: 0,
          page_label: "1",
          score: 1,
        },
      ],
    });
    await pending;
  });
  expect(
    mounted.client
      .getQueryData<Structure>(["sections", "v"])!
      .sections.some((section) => section.id === "s"),
  ).toBe(true);
  expect(
    screen.queryByText("Old section expanded result"),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("region", { name: "英文关键词检索结果" }),
  ).not.toBeInTheDocument();
  expect(
    within(newHelper).getByRole("checkbox", { name: "允许本次生成英文关键词" }),
  ).toBeChecked();
  expect(api.search).toHaveBeenCalledTimes(3);
  expect(api.expandSearchKeywords).toHaveBeenCalledTimes(1);
});

test("a late ordinary search does not replace new local results or withdraw the new section's helper consent", async () => {
  const user = userEvent.setup();
  let finishSearch!: (value: SearchResult) => void;
  const pending = new Promise<SearchResult>((resolve) => {
    finishSearch = resolve;
  });
  vi.mocked(api.search)
    .mockReturnValueOnce(pending)
    .mockResolvedValue({ query: "memory", items: [] });
  const mounted = mount(
    <KnowledgeReading
      versionId="v"
      paperId="paper"
      connected
      initialSectionId="s"
    />,
  );
  await screen.findByText("本地索引已就绪：1 个章节。");
  addSecondValidSection(mounted.client);
  await user.type(screen.getByLabelText("搜索论文原文"), "memory");
  await user.click(screen.getByRole("button", { name: "本地搜索" }));
  expect(api.search).toHaveBeenCalledTimes(1);
  await user.selectOptions(screen.getByLabelText("选择章节"), "s2");
  await user.click(screen.getByRole("button", { name: "本地搜索" }));
  const helper = await screen.findByRole("region", { name: "英文关键词辅助" });
  await user.click(
    within(helper).getByRole("checkbox", { name: "允许本次生成英文关键词" }),
  );
  await act(async () => {
    finishSearch({
      query: "memory",
      items: [
        {
          chunk_id: "old-local",
          section_id: "s",
          document_version_id: "v",
          paper_id: "paper",
          text: "Late old local result",
          page_index: 0,
          page_label: "1",
          score: 1,
        },
      ],
    });
    await pending;
  });
  expect(screen.queryByText("Late old local result")).not.toBeInTheDocument();
  expect(
    within(helper).getByRole("checkbox", { name: "允许本次生成英文关键词" }),
  ).toBeChecked();
  expect(api.expandSearchKeywords).not.toHaveBeenCalled();
  expect(api.search).toHaveBeenCalledTimes(2);
});
test("pending overview completion refreshes usage and jobs immediately", async () => {
  vi.mocked(api.overview).mockResolvedValue({
    ...emptyOverview,
    id: "overview",
    schema_version: "paper-card-set-2",
    status: "PENDING",
  });
  const mounted = mount(
    <PaperOverview paperId="paper" revisionId="v" projectId="p" connected />,
  );
  await screen.findByText("任务进行中：论文卡片集生成");
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
    schema_version: "paper-card-set-2",
    status: "PENDING",
    job_id: "job",
  });
  mount(
    <PaperOverview paperId="paper" revisionId="v" projectId="p" connected />,
  );
  const button = await screen.findByRole("button", { name: "生成论文卡片集" });
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
  expect(await screen.findByText("任务进行中：论文卡片集生成")).toBeVisible();
});
test("failed overview remains visible and does not automatically retry", async () => {
  vi.mocked(api.overview).mockResolvedValue({
    ...emptyOverview,
    id: "failed",
    schema_version: "paper-card-set-2",
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
    name: "重新生成卡片集",
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
  expect(await screen.findByText("任务进行中：论文卡片集生成")).toBeVisible();
});
test("PDF import defaults to local parsing without model consent or plan", async () => {
  const user = userEvent.setup();
  vi.mocked(api.selectPdfImport).mockResolvedValue({
    selection_id: "selection-1",
    file_name: "paper.pdf",
  });
  vi.mocked(api.submitPdfImport).mockResolvedValue(null);
  mount(<Papers projectId="p" connected />);
  await user.selectOptions(screen.getByLabelText("保存方式"), "managed");
  await user.click(screen.getByRole("button", { name: "选择 PDF 导入" }));
  expect(api.selectPdfImport).toHaveBeenCalledExactlyOnceWith();
  expect(api.submitPdfImport).toHaveBeenCalledExactlyOnceWith(
    "p",
    "managed",
    "selection-1",
    undefined,
  );
  expect(api.generateOverview).not.toHaveBeenCalled();
});
test("cancelling the native PDF picker does not submit an import job", async () => {
  const user = userEvent.setup();
  vi.mocked(api.selectPdfImport).mockResolvedValue(null);
  mount(<Papers projectId="p" connected />);
  await user.click(screen.getByRole("button", { name: "选择 PDF 导入" }));
  expect(api.selectPdfImport).toHaveBeenCalledExactlyOnceWith();
  expect(api.submitPdfImport).not.toHaveBeenCalled();
});
test("import plan can select reading translation and require multimodal without generating early", async () => {
  const user = userEvent.setup();
  vi.mocked(api.selectPdfImport).mockResolvedValue({
    selection_id: "selection-1",
    file_name: "paper.pdf",
  });
  vi.mocked(api.submitPdfImport).mockResolvedValue(null);
  mount(<Papers projectId="p" connected />);
  await user.click(screen.getByRole("radio", { name: "模型解析 PDF" }));
  expect(
    screen.queryByRole("radio", { name: "生成逐段中文翻译" }),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("checkbox", { name: "生成论文概览" }));
  await user.click(screen.getByRole("checkbox", { name: "生成论文精读" }));
  await user.click(screen.getByRole("radio", { name: "生成逐段中文翻译" }));
  await user.selectOptions(screen.getByLabelText("多模态策略"), "required");
  await user.click(
    screen.getByRole("checkbox", {
      name: "允许将所选 PDF 发送给已配置的论文解析模型",
    }),
  );
  expect(screen.getByText(/当前模型能力会在提交前检查/)).toBeVisible();
  expect(api.importPdf).not.toHaveBeenCalled();
  expect(api.generateOverview).not.toHaveBeenCalled();
  expect(api.generatePaperReadingNotes).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "选择 PDF 导入" }));
  expect(api.submitPdfImport).toHaveBeenCalledExactlyOnceWith(
    "p",
    "reference",
    "selection-1",
    {
      parse: true,
      overview: false,
      reading: true,
      translation_mode: "full",
      modality: "required",
      extract_formulas: true,
      extract_tables: true,
      allow_network: true,
    },
  );
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

test("paper title editing refreshes the visible paper detail", async () => {
  const user = userEvent.setup();
  let current = metadataPaper();
  vi.mocked(api.paper).mockImplementation(async () => current);
  vi.mocked(api.updatePaper).mockImplementation(async (_paperId, body) => {
    current = {
      ...current,
      paper: { ...current.paper, title: body.title },
    };
    return {
      ok: true,
      paper_id: current.paper.id,
      backup_file: null,
      removed: {},
      retained_personal_metadata: 0,
      retained_managed_files: 0,
    };
  });
  mount(<Papers projectId="p" connected initialPaperId="paper" />);

  await user.click(await screen.findByRole("button", { name: "编辑题名" }));
  const title = screen.getByRole("textbox", { name: "编辑论文题名" });
  await user.clear(title);
  await user.type(title, "Revised synthetic paper");
  await user.click(screen.getByRole("button", { name: "保存论文题名" }));

  await waitFor(() =>
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "Revised synthetic paper",
      }),
    ).toBeVisible(),
  );
  expect(api.updatePaper).toHaveBeenCalledWith("paper", {
    title: "Revised synthetic paper",
  });
});

test("paper legacy cleanup is staged in archive management and keeps the paper readable", async () => {
  const user = userEvent.setup();
  vi.mocked(api.paper).mockResolvedValue(metadataPaper());
  vi.mocked(archiveApi.stage).mockResolvedValue({
    id: "archive-parse",
    kind: "paper_legacy_content",
    target_id: "paper",
    title: "Synthetic reading paper",
    archived_at: "2026-11-22",
    project_id: "p",
    status: "archived",
  });
  mount(<Papers projectId="p" connected initialPaperId="paper" />);

  await user.click(await screen.findByRole("button", { name: "归档旧解析" }));

  expect(await screen.findByText("旧解析清理已移至归档管理。")).toBeVisible();
  expect(archiveApi.stage).toHaveBeenCalledExactlyOnceWith(
    "paper_legacy_content",
    "paper",
  );
  expect(api.clearPaperLegacyContent).not.toHaveBeenCalled();
  expect(
    await screen.findByRole("region", { name: "论文阅读工作区" }),
  ).toBeVisible();
});

test("paper archive returns to project paper selection", async () => {
  const user = userEvent.setup();
  const onPaperDeleted = vi.fn();
  vi.mocked(api.paper).mockResolvedValue(metadataPaper());
  vi.mocked(archiveApi.stage).mockResolvedValue({
    id: "archive-paper",
    kind: "paper",
    target_id: "paper",
    title: "Synthetic reading paper",
    archived_at: "2026-11-22",
    project_id: "p",
    status: "archived",
  });
  mount(
    <Papers
      projectId="p"
      connected
      initialPaperId="paper"
      onPaperDeleted={onPaperDeleted}
    />,
  );

  await user.click(await screen.findByRole("button", { name: "归档论文" }));

  await waitFor(() => expect(onPaperDeleted).toHaveBeenCalledOnce());
  expect(archiveApi.stage).toHaveBeenCalledExactlyOnceWith("paper", "paper");
  expect(api.deletePaper).not.toHaveBeenCalled();
});

test.each([true, false])(
  "model paper uses unified tabs and source menu with local source %s",
  async (hasLocal) => {
    const user = userEvent.setup();
    vi.mocked(api.paper).mockResolvedValue({
      ...metadataPaper(),
      revisions: hasLocal ? metadataPaper().revisions : [],
    });
    vi.mocked(api.importSessions).mockResolvedValue([
      {
        id: "model-session",
        project_id: "p",
        source_kind: "pdf",
        selection_id: "selection",
        source_snapshot: { paper_id: "paper", file_name: "synthetic.pdf" },
        plan: {
          overview: true,
          reading: true,
          translation_mode: "none",
          modality: "pdf",
          require_multimodal: false,
          allow_network: false,
        },
        status: "succeeded",
        error: null,
        created_at: "2026-11-18T00:00:00Z",
        updated_at: "2026-11-18T00:00:01Z",
        items: [],
      },
    ]);
    vi.mocked(api.modelDocumentParse).mockResolvedValue({
      id: "model-parse",
      import_session_id: "model-session",
      parse_version: "synthetic-v1",
      modality: "pdf",
      status: "succeeded",
      warnings: [],
      error_code: null,
      error: null,
      segments: [
        {
          id: "model-paragraph",
          chapter_ref: "intro",
          chapter_title: "Introduction",
          chapter_level: 1,
          chapter_order: 0,
          kind: "paragraph",
          ordinal: 0,
          text: "Model-first source paragraph",
          latex: null,
          mathml: null,
          raw_table_text: null,
          table_data: null,
          locator: null,
          status: "ok",
          warnings: [],
        },
      ],
    });
    vi.mocked(api.modelDocumentOutputs).mockResolvedValue([
      {
        id: "model-overview",
        import_session_id: "model-session",
        parse_id: "model-parse",
        item_kind: "paper_overview",
        status: "succeeded",
        output_json: { summary: "Model-first overview content" },
        error_code: null,
        error: null,
      },
    ]);
    mount(<Papers projectId="p" connected initialPaperId="paper" />);

    expect(
      await screen.findByRole("region", { name: "模型文档解析结果" }),
    ).toBeVisible();
    expect(screen.queryByText("查看旧版概览摘要")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Model-first overview content"),
    ).not.toBeInTheDocument();
    for (const name of ["论文概览", "论文精读", "论文回答"])
      expect(screen.getByRole("button", { name })).toBeEnabled();
    expect(
      screen.queryByRole("button", { name: "章节材料" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("分类与来源文件")).toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: "附件修订" }),
    ).not.toBeInTheDocument();
    expect(api.chunks).not.toHaveBeenCalled();
    expect(api.overview).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "论文精读" }));
    expect(
      await screen.findByText("Model-first source paragraph"),
    ).toBeVisible();
    await user.click(screen.getByText("查看/编辑本次模型解析章节材料"));
    expect(
      await screen.findByRole("button", { name: "编辑paragraph内容" }),
    ).toBeVisible();
    expect(
      await screen.findByRole("group", { name: "Introduction 阅读状态" }),
    ).toBeVisible();
    expect(api.sections).not.toHaveBeenCalled();
    expect(api.paperReadingNotes).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "论文回答" }));
    if (hasLocal) {
      await user.click(await screen.findByRole("button", { name: "Results" }));
      expect(
        await screen.findByRole("region", { name: "局部证据问答" }),
      ).toBeVisible();
      expect(
        screen.getByText("论文回答使用这篇论文的本地解析原文作为引用来源。"),
      ).toBeVisible();
      await waitFor(() =>
        expect(api.sections).toHaveBeenCalledWith("v", { includeText: false }),
      );
    } else {
      expect(
        screen.getByText(/论文回答需要本地解析建立原文索引/),
      ).toBeVisible();
      expect(api.sections).not.toHaveBeenCalled();
      expect(api.qa).not.toHaveBeenCalled();
    }
    const source = within(screen.getByRole("group", { name: "论文阅读来源" }));
    if (hasLocal) {
      expect(source.getByRole("combobox", { name: "查看来源" })).toHaveValue(
        "model",
      );
    } else {
      expect(source.getByText("模型解析", { exact: true })).toBeVisible();
      expect(source.queryByRole("combobox")).toBeNull();
    }
    expect(api.parsePaper).not.toHaveBeenCalled();
    expect(api.generatePaperReadingNotes).not.toHaveBeenCalled();
    expect(api.askQA).not.toHaveBeenCalled();
  },
);

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
  const title = await screen.findByRole("heading", {
    level: 2,
    name: "Synthetic reading paper",
  });
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
  for (const name of ["论文概览", "论文精读", "论文回答"])
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
  await user.click(screen.getByRole("button", { name: "论文精读" }));
  await waitFor(() =>
    expect(api.readingDocument).toHaveBeenCalledWith("paper", "v-old"),
  );
  rerender(
    <QueryClientProvider client={client}>
      <Papers projectId="p" connected initialPaperId="second" />
    </QueryClientProvider>,
  );
  await screen.findByRole("heading", {
    level: 2,
    name: "Second reading paper",
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
    if (["queued", "running"].includes(status)) {
      expect(history.queryByRole("button")).not.toBeInTheDocument();
    } else {
      expect(history.getAllByRole("button")).toEqual([
        history.getByRole("button", { name: "归档任务" }),
      ]);
    }
    expect(history.queryByRole("status")).not.toBeInTheDocument();
    expect(api.jobAction).not.toHaveBeenCalled();
  },
);

test("Zotero batch keeps the paper title and defaults to local import", async () => {
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
    screen.getByRole("button", { name: "按计划导入 · 已选 1 个附件" }),
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
    selections: [
      {
        item_key: "PAPER001",
        attachment_key: "ATTACH01",
        title: "Synthetic paper",
      },
    ],
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

test("close reading routes one paragraph to D and a concept to its detailed card without model work", async () => {
  const user = userEvent.setup();
  vi.mocked(api.paper).mockResolvedValue(metadataPaper());
  vi.mocked(api.overview).mockResolvedValue(completedOverview);
  vi.mocked(api.conceptUnderstanding).mockResolvedValue([
    { ...readingConcept, has_unresolved_question: true },
  ]);
  vi.mocked(api.readingState).mockResolvedValue({
    ...readingState,
    progress: "READING",
    questions: [
      { paragraph_id: "p1", text: "方法条件是什么？", resolved: false },
    ],
  });
  mount(<Papers projectId="p" connected initialPaperId="paper" />);
  await user.click(await screen.findByRole("button", { name: "论文精读" }));
  const close = await screen.findByRole("region", { name: "全文精读笔记" });
  await within(close).findByText("缓存命中 · 新增调用 0");
  await user.click(
    within(close).getAllByRole("button", { name: "对这段提问" })[0],
  );
  const qa = await screen.findByRole("region", { name: "局部证据问答" });
  expect(within(qa).getByLabelText("作用范围")).toHaveValue("selection");
  await user.type(within(qa).getByLabelText("你的问题"), "方法条件是什么？");
  await user.click(
    within(qa).getByRole("checkbox", {
      name: "允许本次把检索片段发送给已配置模型",
    }),
  );
  await user.click(within(qa).getByRole("button", { name: "提交问题" }));
  expect(api.askQA).toHaveBeenCalledWith(
    "paper",
    expect.objectContaining({
      scope: "selection",
      section_id: "s",
      selection_span_ids: ["sp1"],
    }),
  );
  await user.click(screen.getByRole("button", { name: "论文精读" }));
  await user.click(
    await screen.findByRole("button", { name: "查看关联概念 1" }),
  );
  const detail = await screen.findByRole("article", {
    name: "关键概念卡片：共享记忆",
  });
  expect(
    within(detail).getByText("The method uses shared memory."),
  ).toBeVisible();
  expect(
    screen.queryByRole("complementary", { name: "图谱详情" }),
  ).not.toBeInTheDocument();
  expect(api.saveConceptUnderstanding).not.toHaveBeenCalled();
  expect(api.generateOverview).not.toHaveBeenCalled();
  expect(api.generateCloseReading).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "论文精读" }));
  const restored = await screen.findByRole("region", { name: "全文精读笔记" });
  expect(
    await within(restored).findByLabelText("正文第 1 段中文译文"),
  ).toBeVisible();
  expect(within(restored).getByLabelText("正文第 2 段中文译文")).toBeVisible();
  expect(api.generatePaperReadingNotes).not.toHaveBeenCalled();
});
