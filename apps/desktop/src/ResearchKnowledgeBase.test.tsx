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
import { ResearchKnowledgeBase } from "./ResearchKnowledgeBase";
import { knowledgeApi } from "./knowledgeApi";
import {
  knowledgePapers,
  knowledgeReport,
  knowledgeSettings,
} from "./knowledgeFixtures";
import type { GraphData } from "./graphTypes";

vi.mock("./knowledgeApi", () => ({
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
  vi.mocked(knowledgeApi.papers).mockImplementation(async () => ({
    items: papers,
    total: papers.length,
  }));
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
test("paper root expands five distinct types and resolves each node to its actual source", async () => {
  mount();
  await userEvent.click(screen.getByRole("button", { name: "知识地图" }));
  const graph = await screen.findByTestId("knowledge-renderer");
  expect(within(graph).getAllByRole("button")).toHaveLength(3);
  await userEvent.click(
    within(graph).getByRole("button", { name: "合成论文 A" }),
  );
  expect(
    within(graph).getAllByRole("button", { name: "论文内组织" }),
  ).toHaveLength(5);
  await userEvent.click(
    within(graph).getByRole("button", { name: "A 作者贡献" }),
  );
  expect(screen.getByText(/作者宣称的贡献/)).toBeVisible();
  const refs = screen.getByText(/本地解析材料 · 第 2 页 · 章节 合成方法章节/);
  await userEvent.click(refs);
  expect(screen.getByText("A synthetic source text.")).toBeVisible();
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
  vi.mocked(knowledgeApi.updatePaper).mockResolvedValue({
    ...papers[0],
    archived: true,
  });
  await userEvent.click(screen.getByRole("button", { name: "归档论文知识" }));
  await waitFor(() =>
    expect(knowledgeApi.updatePaper).toHaveBeenCalledWith("library-A", {
      archived: true,
    }),
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
  expect(screen.getByLabelText("展开论文")).toHaveValue("library-A");
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

test("permanent library removal requires explicit confirmation and leaves the source paper alone", async () => {
  vi.mocked(knowledgeApi.deletePaper).mockResolvedValue({ ok: true });
  const confirm = vi
    .spyOn(window, "confirm")
    .mockReturnValueOnce(false)
    .mockReturnValueOnce(true);
  mount();
  await userEvent.click(screen.getByRole("button", { name: "论文知识" }));
  await userEvent.click(
    await screen.findByRole("button", { name: /合成论文 A/ }),
  );
  await userEvent.click(await screen.findByText("永久移除知识库条目"));
  await userEvent.click(
    screen.getByRole("button", { name: "永久移除此论文知识" }),
  );
  expect(knowledgeApi.deletePaper).not.toHaveBeenCalled();
  await userEvent.click(
    screen.getByRole("button", { name: "永久移除此论文知识" }),
  );
  await waitFor(() =>
    expect(knowledgeApi.deletePaper).toHaveBeenCalledExactlyOnceWith(
      "library-A",
    ),
  );
  expect(knowledgeApi.extract).not.toHaveBeenCalled();
  expect(knowledgeApi.updatePaper).not.toHaveBeenCalled();
  confirm.mockRestore();
});
