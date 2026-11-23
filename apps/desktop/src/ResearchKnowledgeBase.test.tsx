import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { archiveApi } from "./archiveApi";
import { ResearchKnowledgeBase } from "./ResearchKnowledgeBase";
import { knowledgeApi } from "./knowledgeApi";
import {
  detailedKnowledgeReport,
  knowledgePapers,
  knowledgeReport,
  knowledgeSettings,
} from "./knowledgeFixtures";
import type { GraphData } from "./graphTypes";

vi.mock("./archiveApi", () => ({
  archiveApi: { stage: vi.fn(), purge: vi.fn() },
}));
vi.mock("./knowledgeApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./knowledgeApi")>()),
  knowledgeApi: Object.fromEntries(
    [
      "library",
      "saveSettings",
      "papers",
      "paper",
      "updatePaper",
      "deletePaper",
      "collect",
      "sources",
      "extract",
      "connect",
      "collections",
      "createCollection",
      "setCollection",
      "reports",
      "report",
      "updateReport",
      "runs",
      "localRecovery",
      "recoverLocal",
      "retryRun",
      "layout",
      "saveLayout",
      "export",
      "usage",
    ].map((key) => [key, vi.fn()]),
  ),
}));
vi.mock("./ForceGraph", () => ({
  ForceGraph: ({
    graph,
    onSelect,
    onEdge,
  }: {
    graph: GraphData;
    onSelect: (id: string) => void;
    onEdge: (id: string) => void;
  }) => (
    <div data-testid="knowledge-renderer">
      {graph.nodes.map((node) => (
        <button key={node.id} onClick={() => onSelect(node.id)}>
          {node.label_zh}
        </button>
      ))}
      {graph.edges.map((edge) => (
        <button key={edge.id} onClick={() => onEdge(edge.id)}>
          {edge.is_dashed ? "跨论文联系" : "论文内组织"}
        </button>
      ))}
    </div>
  ),
}));
const openPaper = vi.fn();
let papers = knowledgePapers();
let report = knowledgeReport();
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  papers = knowledgePapers();
  report = knowledgeReport();
  vi.mocked(knowledgeApi.library).mockResolvedValue({
    id: "personal",
    name: "个人研究知识库",
    settings: knowledgeSettings,
    created_at: "2026-11-20",
    updated_at: "2026-11-20",
  });
  vi.mocked(knowledgeApi.papers).mockImplementation(
    async ({ include_archived } = {}) => {
      const visible = include_archived
        ? papers
        : papers.filter((paper) => !paper.archived);
      return { items: visible, total: visible.length };
    },
  );
  vi.mocked(archiveApi.stage).mockImplementation(async (kind, targetId) => {
    const paper = papers.find((item) => item.id === targetId)!;
    papers = papers.map((item) =>
      item.id === targetId ? { ...item, archived: true } : item,
    );
    return {
      id: `archive-${targetId}`,
      kind,
      target_id: targetId,
      title: paper.title,
      archived_at: "2026-11-22T11:00:00Z",
      project_id: null,
      status: "archived",
    };
  });
  vi.mocked(knowledgeApi.paper).mockImplementation(async (id) =>
    papers.find((p) => p.id === id)!,
  );
  vi.mocked(knowledgeApi.reports).mockImplementation(async () => ({
    items: [report],
    total: 1,
  }));
  vi.mocked(knowledgeApi.report).mockImplementation(async () => report);
  vi.mocked(knowledgeApi.updateReport).mockImplementation(async (_id, body) => {
    report = { ...report, ...body };
    return report;
  });
  vi.mocked(knowledgeApi.collections).mockResolvedValue({
    items: [
      {
        id: "collection-1",
        name: "合成专题",
        description: "",
        created_at: "2026-11-20",
      },
    ],
  });
  vi.mocked(knowledgeApi.runs).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(knowledgeApi.localRecovery).mockResolvedValue({
    version: "knowledge-local-recovery-1",
    available: true,
    preview_fingerprint: "synthetic-recovery-fingerprint",
    original_nodes: 19,
    original_edges: 20,
    kept_nodes: 19,
    kept_edges: 9,
    excluded_edges: [
      {
        index: 9,
        path: "graph.edges[9].type",
        code: "invalid_relation_types",
        relation_type: "USES",
        source_type: "METHOD",
        target_type: "CONCEPT",
        reason:
          "USES 仅允许 RESEARCH_QUESTION → METHOD；当前为 METHOD → CONCEPT。",
      },
    ],
  });
  vi.mocked(knowledgeApi.recoverLocal).mockResolvedValue({
    version_id: "version-recovered",
    library_paper_id: "library-A",
    status: "partial",
    local_recovery: {
      version: "knowledge-local-recovery-1",
      available: false,
      preview_fingerprint: "synthetic-recovery-fingerprint",
      original_nodes: 19,
      original_edges: 20,
      kept_nodes: 19,
      kept_edges: 9,
      excluded_edges: [
        {
          index: 9,
          path: "graph.edges[9].type",
          code: "invalid_relation_types",
          relation_type: "USES",
          source_type: "METHOD",
          target_type: "CONCEPT",
          reason:
            "USES 仅允许 RESEARCH_QUESTION → METHOD；当前为 METHOD → CONCEPT。",
        },
      ],
      published_version_id: "version-recovered",
    },
  });
  vi.mocked(knowledgeApi.usage).mockResolvedValue({
    calls: 0,
    input_tokens: 0,
    output_tokens: 0,
    cost_known: false,
    cost_estimate: null,
  } as never);
  vi.mocked(knowledgeApi.layout).mockResolvedValue({
    view_key: "all",
    layout: { positions: [], viewport: null },
  });
  vi.mocked(knowledgeApi.sources).mockResolvedValue({
    items: [
      {
        paper_id: "paper-A",
        project_id: "project-1",
        title: "合成论文 A",
        sources: [
          {
            source_kind: "local_revision",
            source_id: "local-A",
            label: "本地解析 A",
            overview_result_id: "overview-A",
            has_overview: true,
          },
          {
            source_kind: "model_parse",
            source_id: "model-A",
            label: "模型解析 A",
            has_overview: false,
          },
        ],
      },
    ],
  });
  vi.mocked(knowledgeApi.collect).mockResolvedValue(papers[0]);
  vi.mocked(knowledgeApi.extract).mockResolvedValue({
    id: "run-1",
    status: "queued",
    created_at: "2026-11-20",
  });
  vi.mocked(knowledgeApi.saveSettings).mockResolvedValue({
    id: "personal",
    name: "个人研究知识库",
    settings: knowledgeSettings,
    created_at: "2026-11-20",
    updated_at: "2026-11-20",
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
      <ResearchKnowledgeBase
        connected
        projects={[]}
        onOpenPaper={openPaper}
        onOpenTasks={vi.fn()}
      />
    </QueryClientProvider>,
  );
}
async function chooseSource(source: string) {
  await userEvent.click(
    screen.getAllByRole("button", { name: "加入论文知识" })[0],
  );
  await screen.findByRole("option", { name: "合成论文 A" });
  await userEvent.selectOptions(
    screen.getByLabelText("选择入库论文"),
    "paper-A",
  );
  await userEvent.selectOptions(screen.getByLabelText("选择知识来源"), source);
}

test("opening and browsing the library does not generate, compare or alter read status", async () => {
  mount();
  await screen.findByText("合成论文 B 与已有研究的联系");
  await userEvent.click(screen.getByRole("button", { name: "论文知识" }));
  await screen.findByRole("button", { name: /合成论文 A/ });
  expect(knowledgeApi.collect).not.toHaveBeenCalled();
  expect(knowledgeApi.extract).not.toHaveBeenCalled();
  expect(knowledgeApi.connect).not.toHaveBeenCalled();
  expect(knowledgeApi.updateReport).not.toHaveBeenCalled();
});
test("collect binds the selected existing local overview and makes no model call", async () => {
  mount();
  await chooseSource("local_revision:local-A");
  await userEvent.click(
    screen.getByRole("button", { name: "零模型收藏已有概览" }),
  );
  await waitFor(() =>
    expect(knowledgeApi.collect).toHaveBeenCalledExactlyOnceWith({
      paper_id: "paper-A",
      source_kind: "local_revision",
      source_id: "local-A",
      overview_result_id: "overview-A",
    }),
  );
  expect(knowledgeApi.extract).not.toHaveBeenCalled();
  await screen.findByText(/已有概览已收藏/);
});
test("model source extraction requires explicit consent and source switching clears it", async () => {
  mount();
  await chooseSource("model_parse:model-A");
  const generate = screen.getByRole("button", { name: "生成带来源知识" });
  expect(generate).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "此来源尚无可收藏概览" }),
  ).toBeDisabled();
  await userEvent.click(
    screen.getByRole("checkbox", { name: /允许向已配置模型发送此来源版本/ }),
  );
  await userEvent.selectOptions(
    screen.getByLabelText("选择知识来源"),
    "local_revision:local-A",
  );
  expect(generate).toBeDisabled();
  await userEvent.selectOptions(
    screen.getByLabelText("选择知识来源"),
    "model_parse:model-A",
  );
  await userEvent.click(
    screen.getByRole("checkbox", { name: /允许向已配置模型发送此来源版本/ }),
  );
  await userEvent.click(generate);
  await waitFor(() =>
    expect(knowledgeApi.extract).toHaveBeenCalledExactlyOnceWith({
      paper_id: "paper-A",
      source_kind: "model_parse",
      source_id: "model-A",
      allow_network: true,
    }),
  );
});
test("the map opens with all five types, filters individual types, and resolves actual sources", async () => {
  mount();
  await userEvent.click(screen.getByRole("button", { name: "知识地图" }));
  const graph = await screen.findByTestId("knowledge-renderer");
  expect(screen.getByLabelText("展开论文")).toHaveValue("all");
  expect(
    within(graph).getAllByRole("button", { name: "论文内组织" }),
  ).toHaveLength(10);
  for (const label of ["研究问题", "概念", "方法", "贡献", "结果"])
    expect(
      screen.getByRole("checkbox", { name: `显示${label}` }),
    ).toBeChecked();
  const methods = screen.getByRole("checkbox", { name: "显示方法" });
  await userEvent.click(methods);
  expect(
    within(graph).queryByRole("button", { name: "A 合成方法" }),
  ).toBeNull();
  expect(
    within(graph).queryByRole("button", { name: "B 合成方法" }),
  ).toBeNull();
  expect(
    within(graph).getByRole("button", { name: "合成论文 A" }),
  ).toBeVisible();
  expect(
    within(graph).getByRole("button", { name: "跨论文联系" }),
  ).toBeVisible();
  await userEvent.click(
    within(graph).getByRole("button", { name: "合成论文 A" }),
  );
  expect(
    within(graph).getAllByRole("button", { name: "论文内组织" }),
  ).toHaveLength(8);
  await userEvent.click(methods);
  expect(
    within(graph).getByRole("button", { name: "B 合成方法" }),
  ).toBeVisible();
  await userEvent.click(
    within(graph).getByRole("button", { name: "A 作者贡献" }),
  );
  expect(screen.getByText(/作者宣称的贡献/)).toBeVisible();
  const refs = screen.getByText(/本地解析材料 · 第 2 页 · 章节 合成方法章节/);
  await userEvent.click(refs);
  expect(screen.getByText("A synthetic source text.")).toBeVisible();
});
test("the default expanded map requests at most 12 papers per page", async () => {
  const roots = Array.from({ length: 13 }, (_, index) => ({
    ...papers[0],
    id: `library-page-${index + 1}`,
    title: `分页论文 ${index + 1}`,
    current_version: null,
    versions: [],
  }));
  vi.mocked(knowledgeApi.papers).mockImplementation(
    async ({ offset = 0, limit = 50 } = {}) => ({
      items: roots.slice(offset, offset + limit),
      total: roots.length,
    }),
  );
  mount();
  await userEvent.click(screen.getByRole("button", { name: "知识地图" }));
  const firstMap = await screen.findByTestId("knowledge-renderer");
  expect(
    within(firstMap).getAllByRole("button", { name: /分页论文 / }),
  ).toHaveLength(12);
  await userEvent.click(screen.getByRole("button", { name: "下一页" }));
  expect(
    await screen.findByRole("button", { name: "分页论文 13" }),
  ).toBeVisible();
  expect(knowledgeApi.papers).toHaveBeenLastCalledWith(
    expect.objectContaining({ limit: 12, offset: 12 }),
  );
  expect(knowledgeApi.connect).not.toHaveBeenCalled();
});
test("cross-paper graph edge opens its persisted report and both evidence chains", async () => {
  mount();
  await userEvent.click(screen.getByRole("button", { name: "知识地图" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "跨论文联系" }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: /打开对应联系汇报/ }),
  );
  const dialog = await screen.findByRole("dialog", { name: "联系汇报" });
  expect(within(dialog).getByText("新增论文依据")).toBeVisible();
  expect(within(dialog).getByText("已有论文依据")).toBeVisible();
  expect(within(dialog).getByText(/任务条件不同/)).toBeVisible();
});
test("detailed relationships stay in the report and the map can locate either saved version", async () => {
  const older = { ...report, pinned: true };
  const detailed = detailedKnowledgeReport();
  const newer = {
    ...detailed,
    library_paper_id: "library-A",
    version_id: "version-A",
    relations: detailed.relations!.map((relation) => ({
      ...relation,
      id: older.relations![0].id,
      explanation_zh: older.relations![0].explanation_zh,
    })),
    summary: detailed.summary?.map((summary) => ({
      ...summary,
      relation_ids: [older.relations![0].id],
    })),
  };
  const relation = newer.relations![0];
  vi.mocked(knowledgeApi.reports).mockResolvedValue({
    items: [older, newer],
    total: 2,
  });
  vi.mocked(knowledgeApi.report).mockImplementation(async (id) =>
    id === older.id ? older : newer,
  );
  mount();
  await userEvent.click(screen.getByRole("button", { name: "知识地图" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "跨论文联系" }),
  );
  const mapDetail = screen.getByRole("complementary", { name: "知识地图详情" });
  expect(within(mapDetail).getByText(relation.explanation_zh!)).toBeVisible();
  expect(
    within(mapDetail).queryByText(relation.detail!.comparison_zh),
  ).toBeNull();
  await userEvent.click(
    within(mapDetail).getByRole("button", { name: /打开对应联系汇报/ }),
  );
  const dialog = await screen.findByRole("dialog", { name: "联系汇报" });
  const detail = await within(dialog).findByLabelText("详细关系总结");
  expect(detail).toHaveTextContent(relation.detail!.source_zh);
  expect(detail).toHaveTextContent(relation.detail!.target_zh);
  expect(
    within(dialog).getByText(relation.detail!.comparison_zh),
  ).toBeVisible();
  expect(
    within(dialog).getByText(relation.detail!.conditions_zh),
  ).toBeVisible();
  expect(within(dialog).getByText("合成论文 B的原文依据")).toBeVisible();
  expect(within(dialog).getByText("合成论文 A的原文依据")).toBeVisible();
  await userEvent.click(
    within(dialog).getByRole("button", { name: /在知识地图中定位这条联系/ }),
  );
  expect(await screen.findByLabelText("展开论文")).toHaveValue("all");

  await userEvent.click(screen.getByRole("button", { name: /^联系汇报/ }));
  await userEvent.click(
    await screen.findByRole("button", { name: /合成论文 B 与已有研究的联系/ }),
  );
  const historical = await screen.findByRole("dialog", { name: "联系汇报" });
  expect(within(historical).queryByLabelText("详细关系总结")).toBeNull();
  await userEvent.click(
    await within(historical).findByRole("button", {
      name: /在知识地图中定位这条联系/,
    }),
  );
  expect(
    await screen.findByText(older.relations![0].explanation_zh!),
  ).toBeVisible();
  expect(screen.getAllByRole("button", { name: "跨论文联系" })).toHaveLength(1);
  await userEvent.click(
    screen.getByRole("button", { name: /打开对应联系汇报/ }),
  );
  const reopened = await screen.findByRole("dialog", { name: "联系汇报" });
  expect(
    await within(reopened).findByRole("heading", { name: older.title }),
  ).toBeVisible();
  expect(knowledgeApi.connect).not.toHaveBeenCalled();
});

test("a fresh detailed report requires an explicit regeneration action and fresh consent", async () => {
  vi.mocked(knowledgeApi.connect).mockResolvedValue({
    id: "run-connect",
    status: "queued",
    created_at: "2026-11-21",
  });
  mount();
  await userEvent.click(screen.getByRole("button", { name: "论文知识" }));
  await userEvent.click(
    await screen.findByRole("button", { name: /合成论文 B/ }),
  );
  const dialog = await screen.findByRole("dialog", { name: "论文知识" });
  const consent = await within(dialog).findByRole("checkbox", {
    name: /允许发送本版本及候选论文知识/,
  });
  const ordinary = within(dialog).getByRole("button", { name: "分析论文联系" });
  const regenerate = within(dialog).getByRole("button", {
    name: "重新分析并生成详细汇报",
  });
  expect(ordinary).toBeDisabled();
  expect(regenerate).toBeDisabled();
  await userEvent.click(consent);
  await userEvent.click(ordinary);
  await waitFor(() =>
    expect(knowledgeApi.connect).toHaveBeenNthCalledWith(1, "version-B", {
      allow_network: true,
    }),
  );
  await waitFor(() => expect(consent).not.toBeChecked());
  expect(regenerate).toBeDisabled();
  await userEvent.click(consent);
  await userEvent.click(regenerate);
  await waitFor(() =>
    expect(knowledgeApi.connect).toHaveBeenNthCalledWith(2, "version-B", {
      allow_network: true,
      force_regenerate: true,
    }),
  );
});
test("report read, pin and personal note persist independently without model calls", async () => {
  mount();
  await userEvent.click(
    await screen.findByRole("button", { name: /合成论文 B 与已有研究的联系/ }),
  );
  await waitFor(() =>
    expect(knowledgeApi.updateReport).toHaveBeenCalledWith("report-1", {
      read: true,
    }),
  );
  await userEvent.click(screen.getByRole("button", { name: "置顶汇报" }));
  await waitFor(() =>
    expect(knowledgeApi.updateReport).toHaveBeenCalledWith("report-1", {
      pinned: true,
    }),
  );
  await userEvent.type(screen.getByLabelText("汇报个人备注"), "核查条件");
  await userEvent.click(screen.getByRole("button", { name: "保存汇报备注" }));
  await waitFor(() =>
    expect(knowledgeApi.updateReport).toHaveBeenCalledWith("report-1", {
      note: "核查条件",
    }),
  );
  expect(knowledgeApi.connect).not.toHaveBeenCalled();
});
test("a source link returns to the real project paper and archive preserves the snapshot", async () => {
  mount();
  await userEvent.click(screen.getByRole("button", { name: "论文知识" }));
  await userEvent.click(
    await screen.findByRole("button", { name: /合成论文 A/ }),
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "返回论文阅读" }),
  );
  expect(openPaper).toHaveBeenCalledWith("project-1", "paper-A");
  await userEvent.click(screen.getByRole("button", { name: "归档论文知识" }));
  await waitFor(() =>
    expect(archiveApi.stage).toHaveBeenCalledExactlyOnceWith(
      "knowledge_paper",
      "library-A",
    ),
  );
  expect(archiveApi.purge).not.toHaveBeenCalled();
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: /合成论文 A/ }),
    ).not.toBeInTheDocument(),
  );
});
test("strategy settings save explicit network authorization, scope and cumulative budget", async () => {
  mount();
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "自动分析设置" })).toBeEnabled(),
  );
  await userEvent.click(screen.getByRole("button", { name: "自动分析设置" }));
  await userEvent.click(
    screen.getByRole("checkbox", { name: /新解析完成后自动构建论文知识/ }),
  );
  await userEvent.click(
    screen.getByRole("checkbox", { name: /新知识版本入库后自动分析联系/ }),
  );
  await userEvent.click(
    screen.getByRole("checkbox", { name: /授权在以下范围与预算内/ }),
  );
  await userEvent.selectOptions(
    screen.getByLabelText("自动比较范围"),
    "collection",
  );
  await userEvent.selectOptions(
    screen.getByLabelText("自动比较专题"),
    "collection-1",
  );
  fireEvent.change(screen.getByLabelText("知识库累计请求上限"), {
    target: { value: "12" },
  });
  await userEvent.click(screen.getByRole("button", { name: "保存分析策略" }));
  await waitFor(() =>
    expect(knowledgeApi.saveSettings).toHaveBeenCalledWith({
      ...knowledgeSettings,
      auto_collect: true,
      auto_connect: true,
      allow_network: true,
      scope: "collection",
      collection_id: "collection-1",
      total_request_limit: 12,
    }),
  );
  expect(knowledgeApi.extract).not.toHaveBeenCalled();
  expect(knowledgeApi.connect).not.toHaveBeenCalled();
});

test("a report can locate its target paper outside the loaded list page", async () => {
  const target = papers[0];
  vi.mocked(knowledgeApi.papers).mockResolvedValue({
    items: [papers[1]],
    total: 2,
  });
  vi.mocked(knowledgeApi.paper).mockImplementation(async (id) =>
    id === target.id ? target : papers[1],
  );
  mount();
  await userEvent.click(
    await screen.findByRole("button", { name: /合成论文 B 与已有研究的联系/ }),
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "在知识地图中打开合成论文 A" }),
  );
  await waitFor(() =>
    expect(knowledgeApi.paper).toHaveBeenCalledWith("library-A"),
  );
  await screen.findByRole("button", { name: "A 合成方法" });
  expect(screen.getByLabelText("展开论文")).toHaveValue("all");
});

test("each optional budget can be unlimited without changing the cumulative limit or sending a model request", async () => {
  mount();
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "自动分析设置" })).toBeEnabled(),
  );
  await userEvent.click(screen.getByRole("button", { name: "自动分析设置" }));
  for (const [label, finite] of [
    ["单次输入 Token 预算", 96000],
    ["单次输出 Token 预算", 12000],
    ["每次分析最多请求数", 4],
  ] as const) {
    const input = screen.getByRole("spinbutton", { name: label });
    fireEvent.change(input, { target: { value: String(finite) } });
    const unlimited = screen.getByRole("checkbox", { name: `${label}无上限` });
    await userEvent.click(unlimited);
    expect(input).toBeDisabled();
    expect(input).toHaveValue(null);
    await userEvent.click(unlimited);
    expect(input).toBeEnabled();
    expect(input).toHaveValue(finite);
    await userEvent.click(unlimited);
  }
  expect(screen.getAllByRole("checkbox", { name: /无上限/ })).toHaveLength(3);
  expect(screen.getByLabelText("知识库累计请求上限")).toHaveValue(
    knowledgeSettings.total_request_limit,
  );
  await userEvent.click(screen.getByRole("button", { name: "保存分析策略" }));
  await waitFor(() =>
    expect(knowledgeApi.saveSettings).toHaveBeenCalledExactlyOnceWith({
      ...knowledgeSettings,
      max_input_tokens: null,
      max_output_tokens: null,
      max_requests_per_run: null,
    }),
  );
  expect(knowledgeApi.extract).not.toHaveBeenCalled();
  expect(knowledgeApi.connect).not.toHaveBeenCalled();
});

test("persisted unlimited budgets reopen with explicit checked controls and finite fallback values", async () => {
  vi.mocked(knowledgeApi.library).mockResolvedValue({
    id: "personal",
    name: "个人研究知识库",
    settings: {
      ...knowledgeSettings,
      max_input_tokens: null,
      max_output_tokens: null,
      max_requests_per_run: null,
    },
    created_at: "2026-11-20",
    updated_at: "2026-11-20",
  });
  mount();
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "自动分析设置" })).toBeEnabled(),
  );
  await userEvent.click(screen.getByRole("button", { name: "自动分析设置" }));
  for (const [label, fallback] of [
    ["单次输入 Token 预算", 48000],
    ["单次输出 Token 预算", 6000],
    ["每次分析最多请求数", 2],
  ] as const) {
    const input = screen.getByRole("spinbutton", { name: label });
    const unlimited = screen.getByRole("checkbox", { name: `${label}无上限` });
    expect(unlimited).toBeChecked();
    expect(input).toBeDisabled();
    await userEvent.click(unlimited);
    expect(input).toHaveValue(fallback);
  }
});

test.each([
  [null, "无上限"],
  [undefined, "未知"],
] as const)("run budget %s is displayed as %s", async (max_requests, label) => {
  vi.mocked(knowledgeApi.runs).mockResolvedValue({
    items: [
      {
        id: "budget-run",
        kind: "extract",
        status: "succeeded",
        request_count: 1,
        max_requests,
        created_at: "2026-11-20",
      },
    ],
    total: 1,
  });
  mount();
  await userEvent.click(await screen.findByText("最近知识任务"));
  expect(
    screen.getByText(`论文知识建模 · 已完成 · 已发送 1 / 预算 ${label} 次请求`),
  ).toBeVisible();
});

test("failed extraction can be explicitly continued and reports its request budget", async () => {
  vi.mocked(knowledgeApi.runs).mockResolvedValue({
    items: [
      {
        id: "failed-run",
        kind: "extract",
        status: "failed",
        request_count: 1,
        max_requests: 2,
        error: "合成失败",
        created_at: "2026-11-20",
      },
    ],
    total: 1,
  });
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.mocked(knowledgeApi.retryRun).mockResolvedValue({
    id: "new-job",
    status: "queued",
    created_at: "2026-11-20",
  });
  mount();
  await userEvent.click(await screen.findByText("最近知识任务"));
  expect(screen.getByText(/已发送 1 \/ 预算 2 次请求/)).toBeVisible();
  await userEvent.click(
    screen.getByRole("button", { name: "确认继续知识任务" }),
  );
  await waitFor(() =>
    expect(knowledgeApi.retryRun).toHaveBeenCalledWith("failed-run"),
  );
  confirm.mockRestore();
});

test("input budget settings remain available while failure detail points to task history", async () => {
  vi.mocked(knowledgeApi.runs).mockResolvedValue({
    items: [
      {
        id: "input-budget-run",
        kind: "extract",
        status: "failed",
        request_count: 0,
        max_requests: 2,
        error: "KNOWLEDGE_INPUT_BUDGET_EXCEEDED",
        created_at: "2026-11-20",
      },
    ],
    total: 1,
  });
  mount();
  await userEvent.click(await screen.findByText("最近知识任务"));
  expect(
    screen.getByRole("button", { name: "查看任务记录中的错误原因" }),
  ).toBeVisible();
  expect(screen.queryByText(/完整输入超过当前单次输入 Token 预算/)).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "调整知识库预算" }));
  await userEvent.click(
    screen.getByRole("checkbox", { name: "单次输入 Token 预算无上限" }),
  );
  await userEvent.click(screen.getByRole("button", { name: "保存分析策略" }));
  await waitFor(() => expect(knowledgeApi.saveSettings).toHaveBeenCalledOnce());
  expect(knowledgeApi.retryRun).not.toHaveBeenCalled();
  expect(knowledgeApi.extract).not.toHaveBeenCalled();
  expect(knowledgeApi.connect).not.toHaveBeenCalled();
  expect(
    screen.getByRole("button", { name: "确认继续知识任务" }),
  ).toBeEnabled();
});

test("knowledge task status links to task history without repeating failure causes", async () => {
  vi.mocked(knowledgeApi.runs).mockResolvedValue({
    items: [
      {
        id: "schema-failed-run",
        kind: "extract",
        status: "failed",
        request_count: 1,
        max_requests: 2,
        error: "KNOWLEDGE_RESPONSE_SCHEMA_INVALID",
        created_at: "2026-11-21",
        local_recovery: {
          version: "knowledge-local-recovery-1",
          available: true,
          preview_fingerprint: "stale-list-fingerprint",
          original_nodes: 19,
          original_edges: 20,
          kept_nodes: 19,
          kept_edges: 9,
          excluded_edges: [],
        },
      },
    ],
    total: 1,
  });
  mount();
  await userEvent.click(await screen.findByText("最近知识任务"));
  const row = document.getElementById("knowledge-run-schema-failed-run");
  expect(row).not.toBeNull();
  expect(
    within(row!).getByRole("button", { name: "查看任务记录与本机恢复" }),
  ).toBeVisible();
  expect(screen.queryByText("USES · METHOD → CONCEPT")).toBeNull();
  expect(screen.queryByText(/当前为 METHOD → CONCEPT/)).toBeNull();
  expect(knowledgeApi.localRecovery).not.toHaveBeenCalled();
  expect(knowledgeApi.recoverLocal).not.toHaveBeenCalled();
});

test.each([
  {
    label: "部分知识 · 已隔离 11 条关系",
    audit: { excluded_edge_indices: Array.from({ length: 11 }, (_, i) => i) },
  },
  {
    label: "部分知识 · 已隔离 1 个知识节点和 1 条关系",
    audit: { excluded_node_indices: [1], excluded_edge_indices: [2] },
  },
])(
  "partial recovery stays labeled in the paper list, version selector and detail: $label",
  async ({ label, audit }) => {
    const paper = papers[0];
    const recovered = {
      ...paper.current_version!,
      id: "recovered-version",
      content: {
        ...paper.current_version!.content,
        coverage: {
          status: "partial",
          relation_coverage: "partial",
          local_recovery: audit,
        },
      },
    };
    papers = [
      { ...paper, current_version: recovered, versions: [recovered] },
      papers[1],
    ];
    mount();
    await userEvent.click(screen.getByRole("button", { name: "论文知识" }));
    const row = await screen.findByRole("button", { name: /合成论文 A/ });
    expect(row).toHaveTextContent(label);
    await userEvent.click(row);
    const dialog = await screen.findByRole("dialog", { name: "论文知识" });
    expect(within(dialog).getByText(new RegExp(label))).toBeVisible();
    expect(within(dialog).getByRole("status")).toHaveTextContent(
      "此版本由本机恢复生成。联系分析会使用部分知识，请结合论文原文核对。",
    );
    expect(
      screen.getByRole("option", { name: /部分知识/ }),
    ).toBeInTheDocument();
  },
);

test("invalid knowledge results point to task record details and keep explicit continuation", async () => {
  vi.mocked(knowledgeApi.runs).mockResolvedValue({
    items: [
      {
        id: "invalid-run",
        kind: "extract",
        status: "failed",
        request_count: 1,
        max_requests: 2,
        error: "KNOWLEDGE_RESPONSE_INVALID",
        created_at: "2026-11-20",
      },
    ],
    total: 1,
  });
  mount();
  await userEvent.click(await screen.findByText("最近知识任务"));
  expect(
    screen.getByRole("button", { name: "查看任务记录中的错误原因" }),
  ).toBeVisible();
  expect(screen.getByRole("button", { name: "打开任务记录" })).toBeVisible();
  expect(
    screen.getByRole("button", { name: "确认继续知识任务" }),
  ).toBeEnabled();
  expect(screen.queryByRole("region", { name: "知识任务错误详情" })).toBeNull();
  expect(knowledgeApi.retryRun).not.toHaveBeenCalled();
  expect(knowledgeApi.extract).not.toHaveBeenCalled();
  expect(knowledgeApi.connect).not.toHaveBeenCalled();
});

test("automatic strategy cannot be saved while its model authorization is unchecked", async () => {
  mount();
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "自动分析设置" })).toBeEnabled(),
  );
  await userEvent.click(screen.getByRole("button", { name: "自动分析设置" }));
  await userEvent.click(
    screen.getByRole("checkbox", { name: /新解析完成后自动构建论文知识/ }),
  );
  expect(screen.getByRole("button", { name: "保存分析策略" })).toBeDisabled();
  expect(knowledgeApi.saveSettings).not.toHaveBeenCalled();
});

test("the library context menu stages a paper in the archive", async () => {
  mount();
  await userEvent.click(screen.getByRole("button", { name: "论文知识" }));
  const paper = await screen.findByRole("button", { name: /合成论文 A/ });
  fireEvent.contextMenu(paper);
  const menu = screen.getByRole("menu", { name: "论文知识操作" });
  await userEvent.click(
    within(menu).getByRole("menuitem", { name: "归档论文知识" }),
  );
  await waitFor(() =>
    expect(archiveApi.stage).toHaveBeenCalledExactlyOnceWith(
      "knowledge_paper",
      "library-A",
    ),
  );
  expect(archiveApi.purge).not.toHaveBeenCalled();
  expect(knowledgeApi.deletePaper).not.toHaveBeenCalled();
  expect(knowledgeApi.extract).not.toHaveBeenCalled();
  expect(knowledgeApi.updatePaper).not.toHaveBeenCalled();
});
