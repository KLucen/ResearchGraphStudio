import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { QueryPanel } from "./QueryPanel";
import { api, type Job } from "./api";
import {
  queryApi,
  type QueryAnswerView,
  type QueryPreparation,
  type QueryRetrieval,
  type SavedReading,
} from "./queryApi";

vi.mock("./api", () => ({
  api: {
    papers: vi.fn(),
    jobAction: vi.fn(),
    paper: vi.fn(),
    preview: vi.fn(),
  },
}));
vi.mock("./queryApi", () => ({
  queryApi: {
    models: vi.fn(),
    search: vi.fn(),
    browse: vi.fn(),
    prepare: vi.fn(),
    run: vi.fn(),
    generate: vi.fn(),
    answer: vi.fn(),
    history: vi.fn(),
    documents: vi.fn(),
    saved: vi.fn(),
    savedDetail: vi.fn(),
    save: vi.fn(),
    annotate: vi.fn(),
    remove: vi.fn(),
    derived: vi.fn(),
  },
}));
vi.mock("./QueryDerivedGraph", () => ({
  QueryDerivedGraph: () => <div>独立衍生图测试入口</div>,
}));
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

const source = {
  ref: "S00001",
  type: "evidence",
  id: "evidence",
  quote: "Synthetic result under 20 C.",
  paper_id: "paper",
  document_version_id: "version",
  page_index: 1,
  start: 0,
  end: 28,
  current_file_status: "not_checked",
};
const found: QueryRetrieval = {
  status: "matched",
  hits: [
    {
      entry_id: "hit",
      source_kind: "knowledge",
      object_id: "claim",
      text: "在20 C条件下有效",
      reasons: ["exact_term"],
      data: {},
    },
  ],
  graph: { nodes: [{ id: "claim", kind: "claim", text: "有效" }], paths: [] },
  independent_sources: ["paper:version"],
  presentation: {
    hits: {
      hit: {
        title: "合成论文一",
        original: "The method works at 20 C.",
        summary_zh: "在20 C条件下有效",
        summary_origin: "extracted_translation",
        paper_id: "paper",
        page_index: 1,
        section_path: ["Results"],
      },
    },
    references: {},
  },
};
const prepared: QueryPreparation = {
  query_id: "query",
  status: "prepared",
  input_hash: "a".repeat(64),
  error: null,
  presentation: {
    hits: found.presentation!.hits,
    references: {
      S00001: {
        title: "合成论文一",
        original: source.quote,
        summary_zh: "已有中文要点：实验温度为20 C。",
        summary_origin: "extracted_translation",
        paper_id: "paper",
        page_index: 1,
        section_path: ["Results"],
      },
    },
  },
  snapshot: {
    request: {
      project_id: "p",
      question: "条件是什么",
      paper_ids: [],
      include_personal: false,
      purpose: "model",
      limit: 20,
    },
    retrieval: found,
    context: {
      references: [source],
      coverage_gaps: ["仅覆盖已解析原文"],
      status: "ready",
    },
    model: { model: "synthetic-configured" },
  },
};
const answered: QueryAnswerView = {
  query_id: "query",
  status: "succeeded",
  job_id: "job",
  can_continue: false,
  error_code: null,
  error: null,
  request_count: 1,
  request_limit: 2,
  model_runs: [
    {
      id: "run",
      sequence: 1,
      status: "succeeded",
      usage: { prompt_tokens: 100, completion_tokens: 20, total_tokens: 120 },
      duration_seconds: 2,
      finish_reason: "stop",
      error_code: null,
      error: null,
      cost_known: false,
    },
  ],
  answer: {
    answer_version_id: "answer",
    query_run_id: "query",
    revision: 1,
    input_hash: "a".repeat(64),
    status: "validated",
    knowledge_status: "source_grounded",
    passages: [
      {
        local_ref: "p1",
        text: "作者报告：该方法在20 C条件下有效。",
        attribution: "paper_author",
        source_refs: ["S00001"],
        caveats: ["不能外推到其他温度"],
      },
    ],
    limitations: ["未找到第二个温度条件"],
  },
};
const job: Job = {
  id: "job",
  project_id: "p",
  kind: "query_answer",
  status: "queued",
  stage: "starting",
  attempt: 1,
  error: null,
  result: null,
  resume_adapter_available: false,
  created_at: "2026-11-04T00:00:00Z",
  updated_at: "2026-11-04T00:00:00Z",
};
const savedRecord: SavedReading = {
  saved_id: "saved",
  kind: "synthesis",
  title: "已保存综合",
  document_id: "doc",
  version_id: "dv",
  revision: 1,
  created_at: "2026-11-04T00:00:00Z",
  source_query_id: "query",
  answer_version_id: "answer",
  content_state: "valid",
  file_state: "not_exported",
  annotation: "",
  metadata_revision: 0,
  removed_at: null,
  passages: [],
};

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  vi.mocked(api.papers).mockResolvedValue({
    items: [
      {
        id: "paper",
        project_id: "p",
        title: "合成论文一",
        created_at: "2026-11-04T00:00:00Z",
      },
    ],
    next_cursor: null,
  });
  vi.mocked(api.jobAction).mockResolvedValue({ ...job, status: "cancelled" });
  vi.mocked(api.paper).mockResolvedValue({
    paper: {
      id: "paper",
      project_id: "p",
      title: "合成论文一",
      created_at: "2026-11-04T00:00:00Z",
    },
    revisions: [],
    sources: [],
    zotero_links: [],
  });
  vi.mocked(api.preview).mockRejectedValue(new Error("附件暂时离线"));
  vi.mocked(queryApi.models).mockResolvedValue({
    profiles: [],
    roles: { extraction: "model", reasoning: "model" },
  });
  vi.mocked(queryApi.history).mockResolvedValue({
    items: [],
    next_cursor: null,
  });
  vi.mocked(queryApi.documents).mockResolvedValue({ items: [] });
  vi.mocked(queryApi.saved).mockResolvedValue({ items: [] });
  vi.mocked(queryApi.search).mockResolvedValue(found);
  vi.mocked(queryApi.browse).mockResolvedValue({
    status: found.status,
    hits: found.hits,
    independent_sources: found.independent_sources,
    presentation: found.presentation!,
    total: found.hits.length,
    page: 1,
    page_size: 10,
    total_pages: 1,
    result_hash: "b".repeat(64),
    graph_node_count: found.graph.nodes.length,
  });
  vi.mocked(queryApi.prepare).mockResolvedValue(prepared);
  vi.mocked(queryApi.run).mockResolvedValue(prepared);
  vi.mocked(queryApi.generate).mockResolvedValue(job);
  vi.mocked(queryApi.answer).mockResolvedValue(answered);
  vi.mocked(queryApi.save).mockResolvedValue({
    saved_id: "saved",
    kind: "synthesis",
    document_id: "doc",
    version_id: "dv",
    revision: 1,
  });
  vi.mocked(queryApi.savedDetail).mockResolvedValue(savedRecord);
});
function mount(active = false) {
  if (active) localStorage.setItem("researchgraph.query.active.p", "query");
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const onGraph = vi.fn();
  const onSettings = vi.fn();
  return {
    ...render(
      <QueryClientProvider client={client}>
        <QueryPanel
          projectId="p"
          connected
          onGraphNode={onGraph}
          onSettings={onSettings}
        />
      </QueryClientProvider>,
    ),
    client,
    onGraph,
    onSettings,
  };
}
async function generateAnswer(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("研究问题"), "条件是什么");
  await user.click(
    screen.getByLabelText(
      "允许本次将问题与必要来源资料发送给全局 Reasoning 模型",
    ),
  );
  await user.click(screen.getByRole("button", { name: "生成有据回答" }));
  await screen.findByText("作者报告：该方法在20 C条件下有效。");
}

test("local preview is private by default and never starts a model or save", async () => {
  const user = userEvent.setup();
  const { onGraph } = mount();
  await user.type(screen.getByLabelText("研究问题"), "条件");
  expect(screen.getByRole("button", { name: "生成有据回答" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "本地预览来源" }));
  expect(await screen.findByText("在20 C条件下有效")).toBeVisible();
  expect(queryApi.browse).toHaveBeenCalledWith(
    "p",
    expect.objectContaining({
      request: expect.objectContaining({
        purpose: "local",
        include_personal: false,
        paper_ids: [],
      }),
    }),
  );
  expect(queryApi.prepare).not.toHaveBeenCalled();
  expect(queryApi.generate).not.toHaveBeenCalled();
  expect(queryApi.save).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "在图谱中定位" }));
  expect(onGraph).toHaveBeenCalledWith("claim");
});

test("loads all paper pages and passes explicit paper and personal scope", async () => {
  const user = userEvent.setup();
  vi.mocked(api.papers).mockImplementation(async (_id, cursor) =>
    cursor === 2
      ? {
          items: [
            {
              id: "paper2",
              project_id: "p",
              title: "合成论文二",
              created_at: "2026-11-04T00:00:00Z",
            },
          ],
          next_cursor: null,
        }
      : {
          items: [
            {
              id: "paper",
              project_id: "p",
              title: "合成论文一",
              created_at: "2026-11-04T00:00:00Z",
            },
          ],
          next_cursor: 2,
        },
  );
  mount();
  await user.click(screen.getByText("论文范围 · 全部论文"));
  await user.click(await screen.findByRole("checkbox", { name: "合成论文二" }));
  await user.click(
    screen.getByLabelText(
      "同时检索已授权的个人资料（笔记、批注评论与外部材料）及个人综合",
    ),
  );
  await user.type(screen.getByLabelText("研究问题"), "比较");
  await user.click(screen.getByRole("button", { name: "本地预览来源" }));
  await waitFor(() =>
    expect(queryApi.browse).toHaveBeenCalledWith(
      "p",
      expect.objectContaining({
        request: expect.objectContaining({
          paper_ids: ["paper2"],
          include_personal: true,
        }),
      }),
    ),
  );
  expect(api.papers).toHaveBeenCalledWith("p", 2);
});

test("generation binds model scope and shows attribution, limitations and actual usage without auto saving", async () => {
  const user = userEvent.setup();
  mount();
  await generateAnswer(user);
  expect(queryApi.prepare).toHaveBeenCalledWith(
    "p",
    expect.objectContaining({ purpose: "model", include_personal: false }),
    expect.any(String),
  );
  expect(queryApi.generate).toHaveBeenCalledWith(
    "p",
    "query",
    false,
    expect.any(String),
  );
  expect(screen.getByText("选择此段保存 · 论文作者主张")).toBeVisible();
  expect(screen.getByText("不能外推到其他温度")).toBeVisible();
  expect(screen.getByText("未找到第二个温度条件")).toBeVisible();
  expect(
    screen.getByText(/本次模型请求 1\/2 · Token 120 · 费用未知/),
  ).toBeVisible();
  expect(screen.getByRole("button", { name: "保存所选 0 段" })).toBeDisabled();
  expect(queryApi.save).not.toHaveBeenCalled();
});

test("citation opens immutable quote even if PDF is offline and closes with Escape", async () => {
  const user = userEvent.setup();
  mount(true);
  await user.click(await screen.findByRole("button", { name: "展开所有引用" }));
  await user.click(
    await screen.findByRole("button", { name: /查看完整证据 · 合成论文一/ }),
  );
  const dialog = screen.getByRole("dialog", { name: "回答证据" });
  expect(
    within(dialog).getByText("Synthetic result under 20 C."),
  ).toBeVisible();
  expect(within(dialog).getByText(/PDF 第 2 页/)).toBeVisible();
  expect(
    await within(dialog).findByText(/当前无法打开 PDF 预览/),
  ).toBeVisible();
  await user.click(within(dialog).getByRole("button", { name: "关闭证据" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("explicit save sends only chosen passages and no document target by default; retry keeps key", async () => {
  const user = userEvent.setup();
  vi.mocked(queryApi.save)
    .mockRejectedValueOnce(new Error("保存连接中断"))
    .mockResolvedValueOnce({
      saved_id: "saved",
      kind: "synthesis",
      document_id: "doc",
      version_id: "dv",
      revision: 1,
    });
  mount(true);
  await user.click(await screen.findByLabelText("选择此段保存 · 论文作者主张"));
  await user.click(screen.getByRole("button", { name: "保存所选 1 段" }));
  await screen.findByText("保存连接中断");
  await user.click(screen.getByRole("button", { name: "保存所选 1 段" }));
  expect(
    await screen.findByText("阅读知识已保存，可在下方查看，退出重开仍可读取。"),
  ).toBeVisible();
  expect(queryApi.save).toHaveBeenCalledWith(
    "p",
    "query",
    expect.objectContaining({
      selected_passage_refs: ["p1"],
      target_document_id: null,
      base_version_id: null,
      kind: "synthesis",
      expected_input_hash: "a".repeat(64),
    }),
    expect.any(String),
  );
  expect(vi.mocked(queryApi.save).mock.calls[0][3]).toBe(
    vi.mocked(queryApi.save).mock.calls[1][3],
  );
});

test("updating a document requires selecting its exact baseline", async () => {
  const user = userEvent.setup();
  vi.mocked(queryApi.documents).mockResolvedValue({
    items: [
      {
        id: "passage",
        document_id: "wiki",
        version_id: "baseline",
        title: "方法阅读页",
        kind: "wiki",
        content_state: "valid",
      },
    ],
  });
  mount(true);
  await user.click(await screen.findByLabelText("选择此段保存 · 论文作者主张"));
  await user.selectOptions(screen.getByLabelText("保存目标文档"), "wiki");
  await user.selectOptions(screen.getByLabelText("保存知识类型"), "insight");
  await user.click(screen.getByRole("button", { name: "保存所选 1 段" }));
  await waitFor(() =>
    expect(queryApi.save).toHaveBeenCalledWith(
      "p",
      "query",
      expect.objectContaining({
        target_document_id: "wiki",
        base_version_id: "baseline",
        kind: "insight",
      }),
      expect.any(String),
    ),
  );
});

test("failed answer requires fresh consent to continue and does not re-prepare", async () => {
  const user = userEvent.setup();
  vi.mocked(queryApi.answer).mockResolvedValue({
    ...answered,
    status: "failed",
    answer: null,
    can_continue: true,
    error: "模型调用超时，供应商费用未知",
    error_code: "MODEL_TIMEOUT",
  });
  mount(true);
  const button = await screen.findByRole("button", { name: "继续未完成问答" });
  expect(button).toBeDisabled();
  await user.click(
    screen.getByLabelText(
      "允许本次将问题与必要来源资料发送给全局 Reasoning 模型",
    ),
  );
  await user.click(button);
  await waitFor(() =>
    expect(queryApi.generate).toHaveBeenCalledWith(
      "p",
      "query",
      true,
      expect.any(String),
    ),
  );
  expect(queryApi.prepare).not.toHaveBeenCalled();
  expect(
    screen.queryByRole("button", { name: /保存所选/ }),
  ).not.toBeInTheDocument();
});

test("current answer can cancel through unified jobs without duplicating task list", async () => {
  const user = userEvent.setup();
  vi.mocked(queryApi.answer).mockResolvedValue({
    ...answered,
    status: "running",
    answer: null,
  });
  mount(true);
  await user.click(await screen.findByRole("button", { name: "取消本次生成" }));
  expect(api.jobAction).toHaveBeenCalledWith(
    "job",
    "cancel",
    expect.any(String),
  );
  expect(screen.getByText(/完整任务记录集中在/)).toBeVisible();
  expect(screen.queryByText(/任务记录 · 已加载/)).not.toBeInTheDocument();
});

test("unconfigured model leaves local preview usable and links global settings", async () => {
  const user = userEvent.setup();
  vi.mocked(queryApi.models).mockResolvedValue({
    profiles: [],
    roles: { extraction: null, reasoning: null },
  });
  const { onSettings } = mount();
  await user.type(screen.getByLabelText("研究问题"), "方法");
  await user.click(
    await screen.findByRole("button", { name: "打开设置与诊断" }),
  );
  expect(onSettings).toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "生成有据回答" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "本地预览来源" })).toBeEnabled();
});

test("history reads older pages and restores active result on remount with no model calls", async () => {
  const user = userEvent.setup();
  vi.mocked(queryApi.history).mockImplementation(async (_id, cursor) =>
    cursor
      ? {
          items: [
            {
              query_id: "query",
              question: "旧问答",
              status: "succeeded",
              created_at: "2026-11-03T00:00:00Z",
              job_id: "job",
            },
          ],
          next_cursor: null,
        }
      : { items: [], next_cursor: "older" },
  );
  const first = mount();
  await waitFor(() =>
    expect(queryApi.history).toHaveBeenCalledWith("p", "older"),
  );
  await user.click(await screen.findByRole("button", { name: /旧问答/ }));
  await screen.findByText("作者报告：该方法在20 C条件下有效。");
  first.unmount();
  mount();
  expect(
    await screen.findByText("作者报告：该方法在20 C条件下有效。"),
  ).toBeVisible();
  expect(queryApi.generate).not.toHaveBeenCalled();
  expect(queryApi.save).not.toHaveBeenCalled();
});

test("permission or source failure hides cached answer and its citations", async () => {
  const { client } = mount(true);
  await screen.findByText("作者报告：该方法在20 C条件下有效。");
  vi.mocked(queryApi.run).mockRejectedValue(new Error("来源授权已撤销"));
  await act(async () => {
    await client.invalidateQueries({ queryKey: ["query-run", "p", "query"] });
  });
  expect(await screen.findByText("来源授权已撤销")).toBeVisible();
  expect(
    screen.queryByText("作者报告：该方法在20 C条件下有效。"),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /查看完整证据/ }),
  ).not.toBeInTheDocument();
});

test.each([
  [
    "annotation",
    "个人批注评论",
    "此来源仅为个人评论，关联的论文位置不使评论成为论文原文证据。",
  ],
  [
    "external",
    "外部阅读材料（科学来源未核验）",
    "此来源为已登记的外部材料快照，科学来源仍未核验。",
  ],
])(
  "%s references keep their own attribution and disappear after purpose authorization fails",
  async (type, label, notice) => {
    const user = userEvent.setup();
    const reference = {
      ref: "S00001",
      type,
      id: "private-reference",
      text: "个人来源保留文本",
      ...(type === "annotation" ? { page_index: 2 } : {}),
    };
    vi.mocked(queryApi.run).mockResolvedValue({
      ...prepared,
      presentation: { hits: {}, references: {} },
      snapshot: {
        ...prepared.snapshot,
        request: { ...prepared.snapshot.request, include_personal: true },
        context: { ...prepared.snapshot.context, references: [reference] },
      },
    });
    vi.mocked(queryApi.answer).mockResolvedValue({
      ...answered,
      answer: {
        ...answered.answer!,
        knowledge_status: "mixed_sources",
        passages: [
          {
            ...answered.answer!.passages[0],
            text: "个人来源综合",
            attribution: "user_view",
          },
        ],
      },
    });
    const { client } = mount(true);
    await user.click(
      await screen.findByRole("button", { name: "展开所有引用" }),
    );
    const citation = await screen.findByRole("article", { name: "引用 1" });
    expect(
      within(citation).getByRole("heading", {
        name: new RegExp(label.replace(/[（）]/g, "\\$&")),
      }),
    ).toBeVisible();
    expect(within(citation).getByText(notice)).toBeVisible();
    expect(
      within(citation).queryByRole("button", { name: /查看完整证据/ }),
    ).not.toBeInTheDocument();
    await user.click(
      within(citation).getByRole("button", { name: /查看来源材料/ }),
    );
    const dialog = await screen.findByRole("dialog", { name: "回答来源材料" });
    expect(within(dialog).getByRole("heading", { name: label })).toBeVisible();
    expect(within(dialog).getByText("个人来源保留文本")).toBeVisible();
    expect(within(dialog).queryByText(/undefined/)).not.toBeInTheDocument();
    expect(api.preview).not.toHaveBeenCalled();
    vi.mocked(queryApi.run).mockRejectedValue(
      new Error("个人来源本次用途授权已撤销"),
    );
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["query-run", "p", "query"] });
    });
    expect(await screen.findByText("个人来源本次用途授权已撤销")).toBeVisible();
    expect(screen.queryByText("个人来源综合")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /查看来源材料/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("dialog", { name: "回答来源材料" }),
    ).not.toBeInTheDocument();
    expect(queryApi.generate).not.toHaveBeenCalled();
  },
);

test("local source preview labels personal comments and unverified external material without changing Query scope", async () => {
  const user = userEvent.setup();
  vi.mocked(queryApi.browse).mockResolvedValue({
    status: "matched",
    hits: [
      {
        entry_id: "comment-hit",
        source_kind: "annotation",
        object_id: "comment",
        text: "个人评论内容",
        reasons: ["exact_term"],
        data: {},
      },
      {
        entry_id: "external-hit",
        source_kind: "external",
        object_id: "external",
        text: "外部材料内容",
        reasons: ["exact_term"],
        data: {},
      },
    ],
    presentation: { hits: {}, references: {} },
    total: 2,
    page: 1,
    page_size: 10,
    total_pages: 1,
    result_hash: "p",
    graph_node_count: 0,
    independent_sources: [],
  });
  mount();
  await user.click(
    screen.getByLabelText(
      "同时检索已授权的个人资料（笔记、批注评论与外部材料）及个人综合",
    ),
  );
  await user.type(screen.getByLabelText("研究问题"), "个人阅读");
  await user.click(screen.getByRole("button", { name: "本地预览来源" }));
  expect(await screen.findByText("个人评论内容")).toBeVisible();
  expect(
    screen.getByText(
      "此来源仅为个人评论，关联的论文位置不使评论成为论文原文证据。",
    ),
  ).toBeVisible();
  expect(
    screen.getByText("此来源为已登记的外部材料快照，科学来源仍未核验。"),
  ).toBeVisible();
  expect(vi.mocked(queryApi.browse).mock.calls[0][1].request).toEqual({
    project_id: "p",
    question: "个人阅读",
    paper_ids: [],
    include_personal: true,
    purpose: "local",
    limit: 20,
  });
  expect(queryApi.prepare).not.toHaveBeenCalled();
  expect(queryApi.generate).not.toHaveBeenCalled();
});

test("an answer that loads before its frozen references waits for the query record before grouping or showing citations", async () => {
  let resolveRun!: (value: QueryPreparation) => void;
  vi.mocked(queryApi.run).mockReturnValue(
    new Promise<QueryPreparation>((resolve) => {
      resolveRun = resolve;
    }),
  );
  const { client } = mount(true);
  await waitFor(() =>
    expect(client.getQueryData(["query-answer", "p", "query"])).toEqual(
      answered,
    ),
  );
  expect(screen.getByText("正在读取问题、来源与回答…")).toBeVisible();
  expect(screen.getByRole("heading", { name: "正在读取问答" })).toBeVisible();
  expect(
    screen.queryByText("作者报告：该方法在20 C条件下有效。"),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("region", { name: "回答分组：个人资料与未归属来源" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText("引用来源当前不可用，请重新核对来源授权。"),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText("本次尚无通过终验的回答；未验证文本不能保存为知识。"),
  ).not.toBeInTheDocument();
  await act(async () => {
    resolveRun(prepared);
  });
  expect(
    await screen.findByRole("region", { name: "回答分组：合成论文一" }),
  ).toBeVisible();
  expect(screen.getByText("作者报告：该方法在20 C条件下有效。")).toBeVisible();
  expect(
    screen.queryByRole("region", { name: "回答分组：个人资料与未归属来源" }),
  ).not.toBeInTheDocument();
  expect(queryApi.generate).not.toHaveBeenCalled();
  expect(queryApi.save).not.toHaveBeenCalled();
});

test("a completed query groups its question, Chinese source summary, original citations and saving without showing short codes", async () => {
  const user = userEvent.setup();
  mount(true);
  await user.click(await screen.findByRole("button", { name: "展开所有引用" }));
  const record = await screen.findByRole("region", { name: "本次问答记录" });
  expect(
    await within(record).findByRole("heading", { name: "条件是什么" }),
  ).toBeVisible();
  expect(
    await within(record).findByText("已有中文要点：实验温度为20 C。"),
  ).toBeVisible();
  expect(
    within(record).getByText("Synthetic result under 20 C."),
  ).toBeVisible();
  expect(within(record).getByText("The method works at 20 C.")).toBeVisible();
  expect(
    within(record).getByRole("button", { name: "保存所选 0 段" }),
  ).toBeVisible();
  expect(within(record).queryByText(/S00001/)).not.toBeInTheDocument();
  expect(queryApi.generate).not.toHaveBeenCalled();
});

test("source layout warnings stay visible beside frozen original citations without generating", async () => {
  const warning = "原文含上下标版式歧义，数值待核对 PDF。";
  vi.mocked(queryApi.run).mockResolvedValue({
    ...prepared,
    presentation: {
      hits: {},
      references: {
        S00001: {
          ...prepared.presentation!.references.S00001,
          layout_warnings: [warning],
        },
      },
    },
  });
  mount(true);
  await userEvent.click(
    await screen.findByRole("button", { name: "展开所有引用" }),
  );
  const citation = await screen.findByRole("article", { name: "引用 1" });
  expect(within(citation).getByText(warning)).toBeVisible();
  expect(within(citation).getByText(source.quote)).toBeVisible();
  expect(queryApi.generate).not.toHaveBeenCalled();
});

test("missing saved translation uses a clearly attributed answer summary and never requests a translation", async () => {
  vi.mocked(queryApi.run).mockResolvedValue({
    ...prepared,
    presentation: {
      hits: {},
      references: {
        S00001: {
          ...prepared.presentation!.references.S00001,
          summary_zh: null,
          summary_origin: null,
        },
      },
    },
  });
  mount(true);
  await userEvent.click(
    await screen.findByRole("button", { name: "展开所有引用" }),
  );
  const citation = await screen.findByRole("article", { name: "引用 1" });
  expect(within(citation).getByText("本次回答中文要点")).toBeVisible();
  expect(
    within(citation).getByText("作者报告：该方法在20 C条件下有效。"),
  ).toBeVisible();
  expect(within(citation).getByText(/不是原文逐句翻译/)).toBeVisible();
  expect(queryApi.generate).not.toHaveBeenCalled();
});

test("a display source with an unresolved page never invents a first page", async () => {
  vi.mocked(queryApi.run).mockResolvedValue({
    ...prepared,
    presentation: {
      hits: {},
      references: {
        S00001: {
          ...prepared.presentation!.references.S00001,
          paper_id: null,
          page_index: null,
        },
      },
    },
  });
  mount(true);
  await userEvent.click(
    await screen.findByRole("button", { name: "展开所有引用" }),
  );
  const citation = await screen.findByRole("article", { name: "引用 1" });
  expect(
    within(citation).getByRole("heading", {
      name: "引用 1 · 合成论文一 · Results",
    }),
  ).toBeVisible();
  expect(within(citation).queryByText(/第 1 页/)).not.toBeInTheDocument();
});

test("saved knowledge opens, refreshes and focuses its original question with the matching sources", async () => {
  const user = userEvent.setup();
  vi.mocked(queryApi.saved).mockResolvedValue({ items: [savedRecord] });
  const { client } = mount();
  await user.type(screen.getByLabelText("研究问题"), "临时预览问题");
  await user.click(screen.getByRole("button", { name: "本地预览来源" }));
  await screen.findByText("在20 C条件下有效");
  await user.click(screen.getByRole("button", { name: /已保存综合 阅读综合/ }));
  await user.click(
    await screen.findByRole("button", { name: "查看原问答与引用" }),
  );
  const record = await screen.findByRole("region", { name: "本次问答记录" });
  await waitFor(() => expect(record).toHaveFocus());
  expect(
    within(record).getByRole("heading", { name: "条件是什么" }),
  ).toBeVisible();
  expect(within(record).queryByText("临时预览问题")).not.toBeInTheDocument();
  await within(record).findByText("作者报告：该方法在20 C条件下有效。");
  const previousReads = vi.mocked(queryApi.run).mock.calls.length;
  await user.click(screen.getByRole("button", { name: "查看原问答与引用" }));
  await waitFor(() =>
    expect(queryApi.run).toHaveBeenCalledTimes(previousReads + 1),
  );
  expect(client.getQueryData(["query-run", "p", "query"])).toEqual(prepared);
  expect(queryApi.generate).not.toHaveBeenCalled();
});

test("personal annotations save independently with revision protection and reuse their key on retry", async () => {
  const user = userEvent.setup();
  vi.mocked(queryApi.saved).mockResolvedValue({ items: [savedRecord] });
  vi.mocked(queryApi.annotate)
    .mockRejectedValueOnce(new Error("批注保存连接中断"))
    .mockResolvedValueOnce({
      ...savedRecord,
      annotation: "需核对温度适用范围",
      metadata_revision: 1,
    });
  mount();
  await user.click(
    await screen.findByRole("button", { name: /已保存综合 阅读综合/ }),
  );
  const annotation = await screen.findByLabelText("个人批注");
  expect(annotation).toHaveAttribute("maxlength", "12000");
  await user.type(annotation, "需核对温度适用范围");
  await user.click(screen.getByRole("button", { name: "保存个人批注" }));
  await screen.findByText("批注保存连接中断");
  await user.click(screen.getByRole("button", { name: "保存个人批注" }));
  expect(await screen.findByText("个人批注已保存。")).toBeVisible();
  expect(queryApi.annotate).toHaveBeenCalledWith(
    "p",
    "saved",
    { annotation: "需核对温度适用范围", expected_revision: 0 },
    expect.any(String),
    false,
  );
  expect(vi.mocked(queryApi.annotate).mock.calls[0][3]).toBe(
    vi.mocked(queryApi.annotate).mock.calls[1][3],
  );
  expect(queryApi.save).not.toHaveBeenCalled();
  expect(queryApi.generate).not.toHaveBeenCalled();
});

test("saved removal needs confirmation and leaves original question history available", async () => {
  const user = userEvent.setup();
  vi.mocked(queryApi.saved).mockResolvedValue({ items: [savedRecord] });
  vi.mocked(queryApi.history).mockResolvedValue({
    items: [
      {
        query_id: "query",
        question: "条件是什么",
        created_at: savedRecord.created_at,
        status: "succeeded",
        job_id: "job",
      },
    ],
    next_cursor: null,
  });
  vi.mocked(queryApi.remove).mockImplementation(async () => {
    vi.mocked(queryApi.saved).mockResolvedValue({ items: [] });
    return {
      saved_id: "saved",
      removed_at: "2026-11-04T10:00:00Z",
      metadata_revision: 1,
    };
  });
  mount();
  await user.click(
    await screen.findByRole("button", { name: /已保存综合 阅读综合/ }),
  );
  await user.click(await screen.findByRole("button", { name: "移除保存内容" }));
  const confirm = screen.getByRole("group", { name: "确认移除保存内容" });
  expect(
    within(confirm).getByText(/原问答、论文证据与模型历史仍保留/),
  ).toBeVisible();
  expect(queryApi.remove).not.toHaveBeenCalled();
  await user.click(within(confirm).getByRole("button", { name: "确认移除" }));
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: /已保存综合 阅读综合/ }),
    ).not.toBeInTheDocument(),
  );
  expect(
    await screen.findByText(
      "保存内容已移除；原问答、论文证据与模型历史仍保留。",
    ),
  ).toBeVisible();
  expect(queryApi.remove).toHaveBeenCalledWith(
    "p",
    "saved",
    { expected_revision: 0 },
    expect.any(String),
    false,
  );
  expect(
    screen.getByRole("button", { name: /条件是什么 回答完成/ }),
  ).toBeVisible();
  expect(queryApi.generate).not.toHaveBeenCalled();
});

test("derived layer is an explicit view preference and never saves or changes sources", async () => {
  const user = userEvent.setup();
  mount();
  expect(screen.queryByText("独立衍生图测试入口")).not.toBeInTheDocument();
  await user.click(screen.getByLabelText("显示独立衍生图层"));
  expect(screen.getByText("独立衍生图测试入口")).toBeVisible();
  await user.click(screen.getByLabelText("显示独立衍生图层"));
  expect(screen.queryByText("独立衍生图测试入口")).not.toBeInTheDocument();
  expect(queryApi.save).not.toHaveBeenCalled();
  expect(queryApi.generate).not.toHaveBeenCalled();
});

test("editing question or source scope clears transmission consent", async () => {
  const user = userEvent.setup();
  mount();
  const consent = screen.getByLabelText(
    "允许本次将问题与必要来源资料发送给全局 Reasoning 模型",
  );
  await user.type(screen.getByLabelText("研究问题"), "条件");
  await user.click(consent);
  expect(consent).toBeChecked();
  await user.type(screen.getByLabelText("研究问题"), "变化");
  expect(consent).not.toBeChecked();
  await user.click(consent);
  await user.click(
    screen.getByLabelText(
      "同时检索已授权的个人资料（笔记、批注评论与外部材料）及个人综合",
    ),
  );
  expect(consent).not.toBeChecked();
  expect(queryApi.generate).not.toHaveBeenCalled();
});

function twoPapers() {
  vi.mocked(api.papers).mockResolvedValue({
    items: [
      {
        id: "paper",
        project_id: "p",
        title: "合成论文一",
        created_at: job.created_at,
      },
      {
        id: "paper2",
        project_id: "p",
        title: "合成论文二",
        created_at: job.created_at,
      },
    ],
    next_cursor: null,
  });
}

test("all local matches remain accessible beyond20 with independent10-item paging and truthful graph labels", async () => {
  const user = userEvent.setup();
  twoPapers();
  vi.mocked(queryApi.browse).mockImplementation(async (_project, body) => {
    const rows = Array.from({ length: 25 }, (_, index) => ({
      ...found.hits[0],
      entry_id: `hit-${index + 1}`,
      object_id: `node-${index + 1}`,
      data: { paper_id: index < 20 ? "paper" : "paper2" },
    })).filter(
      (row) =>
        !body.display_paper_ids.length ||
        body.display_paper_ids.includes(row.data.paper_id),
    );
    const hits = rows.slice((body.page - 1) * 10, body.page * 10);
    return {
      status: "matched",
      hits,
      presentation: {
        references: {},
        hits: Object.fromEntries(
          hits.map((hit) => [
            hit.entry_id,
            {
              title:
                hit.data.paper_id === "paper" ? "合成论文一" : "合成论文二",
              original: `独立原文${hit.entry_id}`,
              summary_zh: `中文总结${hit.entry_id}`,
              summary_origin: "extracted_translation" as const,
              paper_id: hit.data.paper_id,
              section_path: [],
              graph_presence: {
                state:
                  hit.entry_id === "hit-1"
                    ? ("in_graph" as const)
                    : ("retrieval_only" as const),
                representation: "node" as const,
                node_ids: [],
                graph_roles: [],
                graph_revision: 1,
              },
            },
          ]),
        ),
      },
      total: rows.length,
      page: body.page,
      page_size: 10,
      total_pages: Math.ceil(rows.length / 10),
      result_hash: "d".repeat(64),
      graph_node_count: 25,
      independent_sources: ["paper", "paper2"],
    };
  });
  mount();
  await user.type(screen.getByLabelText("研究问题"), "结论");
  await user.click(screen.getByRole("button", { name: "本地预览来源" }));
  expect(await screen.findByText("中文总结hit-1")).toBeVisible();
  expect(screen.getAllByText(/中文总结hit-/)).toHaveLength(10);
  expect(screen.getByText("已在默认图谱中")).toBeVisible();
  expect(screen.getAllByText("未进入默认图谱 · 仍可检索")).toHaveLength(9);
  await user.selectOptions(screen.getByLabelText("来源预览页码"), "3");
  expect(await screen.findByText("中文总结hit-25")).toBeVisible();
  expect(screen.queryByText("中文总结hit-1")).not.toBeInTheDocument();
  await user.click(screen.getByText("来源论文筛选 · 全部论文"));
  await user.click(
    screen.getByRole("checkbox", { name: "来源论文筛选 · 合成论文二" }),
  );
  await waitFor(() =>
    expect(screen.getByLabelText("来源预览页码")).toHaveValue("1"),
  );
  expect(await screen.findByText("中文总结hit-25")).toBeVisible();
  expect(screen.getAllByText(/中文总结hit-/)).toHaveLength(5);
  expect(queryApi.browse).toHaveBeenLastCalledWith(
    "p",
    expect.objectContaining({
      request: expect.objectContaining({ paper_ids: [] }),
      display_paper_ids: ["paper2"],
      page: 1,
    }),
  );
  expect(queryApi.prepare).not.toHaveBeenCalled();
  expect(queryApi.generate).not.toHaveBeenCalled();
});

test("source changes stop page reuse until an explicit local refresh", async () => {
  const user = userEvent.setup();
  vi.mocked(queryApi.browse).mockImplementation(async (_project, body) => {
    if (body.page === 2) throw new Error("QUERY_RESULTS_CHANGED：来源已变化");
    return {
      status: "matched",
      hits: found.hits,
      presentation: found.presentation!,
      total: 11,
      page: 1,
      page_size: 10,
      total_pages: 2,
      result_hash: "f".repeat(64),
      graph_node_count: 1,
      independent_sources: [],
    };
  });
  mount();
  await user.type(screen.getByLabelText("研究问题"), "结论");
  await user.click(screen.getByRole("button", { name: "本地预览来源" }));
  await screen.findByText("在20 C条件下有效");
  await user.click(screen.getByRole("button", { name: "来源预览下一页" }));
  expect(await screen.findByText(/QUERY_RESULTS_CHANGED/)).toBeVisible();
  expect(screen.queryByText("在20 C条件下有效")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "刷新全部检索结果" }));
  expect(await screen.findByText("在20 C条件下有效")).toBeVisible();
  expect(queryApi.browse).toHaveBeenLastCalledWith(
    "p",
    expect.objectContaining({ page: 1, expected_result_hash: null }),
  );
  expect(queryApi.generate).not.toHaveBeenCalled();
});

test("answers group single-paper and cross-paper prose once and citations have two independent collapsed levels", async () => {
  const user = userEvent.setup();
  twoPapers();
  const second = {
    ...source,
    ref: "S00002",
    id: "evidence2",
    paper_id: "paper2",
  };
  vi.mocked(queryApi.run).mockResolvedValue({
    ...prepared,
    snapshot: {
      ...prepared.snapshot,
      context: { ...prepared.snapshot.context, references: [source, second] },
    },
  });
  vi.mocked(queryApi.answer).mockResolvedValue({
    ...answered,
    answer: {
      ...answered.answer!,
      passages: [
        { ...answered.answer!.passages[0], text: "第一篇单独结论" },
        {
          ...answered.answer!.passages[0],
          local_ref: "p2",
          text: "第二篇单独结论",
          source_refs: ["S00002"],
        },
        {
          ...answered.answer!.passages[0],
          local_ref: "p3",
          text: "两篇共同但有条件的综合",
          source_refs: ["S00001", "S00002"],
          attribution: "model_synthesis",
        },
      ],
    },
  });
  mount(true);
  const group = await screen.findByRole("region", {
    name: "回答分组：合成论文一",
  });
  expect(
    screen.getByRole("region", { name: "回答分组：合成论文二" }),
  ).toBeVisible();
  expect(
    screen
      .getAllByText("两篇共同但有条件的综合")
      .filter((item) =>
        item.parentElement?.classList.contains("query-passage"),
      ),
  ).toHaveLength(1);
  expect(
    screen.getByRole("region", { name: "回答分组：跨论文综合" }),
  ).toBeVisible();
  const outer = group.querySelector<HTMLDetailsElement>(
    ".query-citation-list",
  )!;
  const inner = group.querySelector<HTMLDetailsElement>(
    ".query-citation-entry",
  )!;
  expect(outer.open).toBe(false);
  expect(inner.open).toBe(false);
  await user.click(within(group).getByText("引用 · 1 条"));
  expect(outer.open).toBe(true);
  expect(inner.open).toBe(false);
  await user.click(within(group).getByRole("button", { name: "展开所有引用" }));
  expect(inner.open).toBe(true);
  await user.click(inner.querySelector("summary")!);
  expect(inner.open).toBe(false);
  expect(outer.open).toBe(true);
  await user.click(outer.querySelector("summary")!);
  await user.click(outer.querySelector("summary")!);
  expect(inner.open).toBe(false);
  await user.click(screen.getByText("回答论文筛选 · 全部论文"));
  await user.click(
    screen.getByRole("checkbox", { name: "回答论文筛选 · 合成论文二" }),
  );
  expect(screen.queryByText("第一篇单独结论")).not.toBeInTheDocument();
  expect(
    screen
      .getAllByText("第二篇单独结论")
      .some((item) => item.parentElement?.classList.contains("query-passage")),
  ).toBe(true);
  expect(
    screen.getByRole("region", { name: "回答分组：跨论文综合" }),
  ).toBeVisible();
  expect(queryApi.generate).not.toHaveBeenCalled();
});

test("answer selections survive pagination and paper display filters and save all explicitly selected passages", async () => {
  const user = userEvent.setup();
  twoPapers();
  vi.mocked(queryApi.answer).mockResolvedValue({
    ...answered,
    answer: {
      ...answered.answer!,
      passages: Array.from({ length: 12 }, (_, index) => ({
        ...answered.answer!.passages[0],
        local_ref: `p${index + 1}`,
        text: `回答正文${index + 1}`,
      })),
    },
  });
  mount(true);
  await screen.findByText("回答正文1");
  const choices = screen.getAllByLabelText("选择此段保存 · 论文作者主张");
  expect(choices).toHaveLength(10);
  await user.click(choices[0]);
  await user.selectOptions(screen.getByLabelText("回答段落页码"), "2");
  await user.click(screen.getAllByLabelText("选择此段保存 · 论文作者主张")[0]);
  await user.click(screen.getByText("回答论文筛选 · 全部论文"));
  await user.click(
    screen.getByRole("checkbox", { name: "回答论文筛选 · 合成论文二" }),
  );
  expect(screen.getByText(/已选择 2 段保存/)).toBeVisible();
  expect(screen.queryByText("回答正文11")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "保存所选 2 段" }));
  await waitFor(() =>
    expect(queryApi.save).toHaveBeenCalledWith(
      "p",
      "query",
      expect.objectContaining({ selected_passage_refs: ["p1", "p11"] }),
      expect.any(String),
    ),
  );
});

test("history DATABASE_BUSY can be explicitly reread without model or write requests", async () => {
  const user = userEvent.setup();
  const busy = Object.assign(new Error("本地数据库繁忙，请稍后重试"), {
    code: "DATABASE_BUSY",
  });
  let finishReading!: (
    value: Awaited<ReturnType<typeof queryApi.history>>,
  ) => void;
  vi.mocked(queryApi.history)
    .mockRejectedValueOnce(busy)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishReading = resolve;
        }),
    );
  mount();
  expect(await screen.findByRole("alert")).toHaveTextContent(busy.message);
  const retry = screen.getByRole("button", { name: "重新读取问答历史" });
  expect(retry).toBeEnabled();
  expect(queryApi.history).toHaveBeenCalledTimes(1);
  await user.click(retry);
  await waitFor(() => expect(queryApi.history).toHaveBeenCalledTimes(2));
  expect(screen.getByText("正在读取完整问答历史…")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "重新读取问答历史" }),
  ).not.toBeInTheDocument();
  await act(async () => {
    finishReading({
      items: [
        {
          query_id: "history-restored",
          question: "恢复后可读的历史问题",
          created_at: job.created_at,
          status: "succeeded",
          job_id: "historical-job",
          paper_ids: ["paper"],
        },
      ],
      next_cursor: null,
    });
  });
  expect(
    await screen.findByRole("button", {
      name: /恢复后可读的历史问题 回答完成/,
    }),
  ).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "重新读取问答历史" }),
  ).not.toBeInTheDocument();
  expect(queryApi.history).toHaveBeenNthCalledWith(2, "p", null);
  for (const operation of [
    queryApi.search,
    queryApi.browse,
    queryApi.prepare,
    queryApi.generate,
    queryApi.save,
    queryApi.annotate,
    queryApi.remove,
    api.jobAction,
  ]) {
    expect(operation).not.toHaveBeenCalled();
  }
});

test("saved and complete cursor history each paginate10 and independently filter papers", async () => {
  const user = userEvent.setup();
  twoPapers();
  vi.mocked(queryApi.saved).mockResolvedValue({
    items: Array.from({ length: 21 }, (_, index) => ({
      ...savedRecord,
      saved_id: `saved${index + 1}`,
      title: `保存知识${index + 1}`,
      paper_ids: [index < 20 ? "paper" : "paper2"],
    })),
  });
  vi.mocked(queryApi.history).mockImplementation(async (_project, cursor) => ({
    items: Array.from({ length: cursor ? 1 : 20 }, (_, index) => ({
      query_id: `q${cursor ? 21 : index + 1}`,
      question: `历史问题${cursor ? 21 : index + 1}`,
      created_at: job.created_at,
      status: "succeeded",
      job_id: "job",
      paper_ids: [cursor ? "paper2" : "paper"],
    })),
    next_cursor: cursor ? null : "next20",
  }));
  mount();
  await screen.findByRole("button", { name: /保存知识1 阅读综合/ });
  expect(
    screen.getAllByRole("button", { name: /保存知识\d+ 阅读综合/ }),
  ).toHaveLength(10);
  await waitFor(() =>
    expect(queryApi.history).toHaveBeenCalledWith("p", "next20"),
  );
  await user.selectOptions(screen.getByLabelText("问答历史页码"), "3");
  expect(
    screen.getByRole("button", { name: /历史问题21 回答完成/ }),
  ).toBeVisible();
  await user.click(screen.getByText("保存内容论文筛选 · 全部论文"));
  await user.click(
    screen.getByRole("checkbox", { name: "保存内容论文筛选 · 合成论文二" }),
  );
  expect(
    screen.getByRole("button", { name: /保存知识21 阅读综合/ }),
  ).toBeVisible();
  expect(screen.getByLabelText("保存内容页码")).toHaveValue("1");
  expect(screen.getByLabelText("问答历史页码")).toHaveValue("3");
  await user.click(screen.getByText("历史论文筛选 · 全部论文"));
  await user.click(
    screen.getByRole("checkbox", { name: "历史论文筛选 · 合成论文一" }),
  );
  expect(screen.getByLabelText("问答历史页码")).toHaveValue("1");
  expect(
    screen.queryByRole("button", { name: /历史问题21 回答完成/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /保存知识21 阅读综合/ }),
  ).toBeVisible();
  expect(queryApi.generate).not.toHaveBeenCalled();
});

test("explicit expand-all retains expansion when paging more than10 citations", async () => {
  const user = userEvent.setup();
  const refs = Array.from({ length: 12 }, (_, index) => ({
    ...source,
    ref: `S${index + 1}`,
    id: `e${index + 1}`,
    quote: `引用原文${index + 1}`,
  }));
  vi.mocked(queryApi.run).mockResolvedValue({
    ...prepared,
    snapshot: {
      ...prepared.snapshot,
      context: { ...prepared.snapshot.context, references: refs },
    },
  });
  vi.mocked(queryApi.answer).mockResolvedValue({
    ...answered,
    answer: {
      ...answered.answer!,
      passages: [
        {
          ...answered.answer!.passages[0],
          source_refs: refs.map((ref) => ref.ref),
        },
      ],
    },
  });
  mount(true);
  await user.click(await screen.findByRole("button", { name: "展开所有引用" }));
  const answer = screen.getByRole("region", { name: "问答结果" });
  expect(
    within(answer).getAllByRole("article", { name: /^引用 \d+$/ }),
  ).toHaveLength(10);
  expect(
    within(answer).queryByRole("article", { name: "引用 11" }),
  ).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("段落p1引用页码"), "2");
  expect(
    within(answer).getAllByRole("article", { name: /^引用 \d+$/ }),
  ).toHaveLength(2);
  expect(within(answer).getByText("引用原文12")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "收起所有引用" }));
  expect(
    answer.querySelector<HTMLDetailsElement>(".query-citation-list")!.open,
  ).toBe(false);
  expect(within(answer).getByText("引用原文12")).not.toBeVisible();
});

test("saved detail paginates10 passages and its paper filter is independent of the library", async () => {
  const user = userEvent.setup();
  twoPapers();
  const item = {
    ...savedRecord,
    paper_ids: ["paper", "paper2"],
    passages: Array.from({ length: 21 }, (_, index) => ({
      attribution: "paper_author" as const,
      caveats: [],
      content_state: "valid",
      issues: [],
      id: `sp${index + 1}`,
      local_ref: `sp${index + 1}`,
      text: `保存正文${index + 1}`,
      paper_ids: [index < 20 ? "paper" : "paper2"],
    })),
  };
  vi.mocked(queryApi.saved).mockResolvedValue({ items: [item] });
  vi.mocked(queryApi.savedDetail).mockResolvedValue(item);
  mount();
  await user.click(
    await screen.findByRole("button", { name: /已保存综合 阅读综合/ }),
  );
  await screen.findByText("保存正文1");
  expect(screen.getAllByText(/^保存正文\d+$/)).toHaveLength(10);
  await user.selectOptions(screen.getByLabelText("保存详情页码"), "2");
  expect(screen.getByText("保存正文20")).toBeVisible();
  await user.click(screen.getByText("保存详情论文筛选 · 全部论文"));
  await user.click(
    screen.getByRole("checkbox", { name: "保存详情论文筛选 · 合成论文二" }),
  );
  expect(screen.getByText("保存正文21")).toBeVisible();
  expect(screen.getByLabelText("保存详情页码")).toHaveValue("1");
  expect(screen.getAllByText(/^保存正文\d+$/)).toHaveLength(1);
  expect(
    screen.getByRole("button", { name: /已保存综合 阅读综合/ }),
  ).toBeVisible();
  expect(queryApi.generate).not.toHaveBeenCalled();
});
