import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api, type Job } from "./api";
import { archiveApi } from "./archiveApi";
import { JobHistory } from "./JobHistory";
import { knowledgeApi } from "./knowledgeApi";

vi.mock("./api", () => ({
  api: {
    jobs: vi.fn(),
    jobsPage: vi.fn(),
    projectJobs: vi.fn(),
    jobAction: vi.fn(),
  },
}));
vi.mock("./archiveApi", () => ({ archiveApi: { stage: vi.fn() } }));
vi.mock("./knowledgeApi", () => ({
  knowledgeApi: {
    runs: vi.fn(),
    localRecovery: vi.fn(),
    recoverLocal: vi.fn(),
  },
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

beforeEach(() => {
  vi.mocked(api.jobsPage).mockImplementation(async () => ({
    items: await api.jobs(),
    next_cursor: null,
  }));
  vi.mocked(knowledgeApi.runs).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(knowledgeApi.localRecovery).mockResolvedValue(recoveryPreview);
  vi.mocked(knowledgeApi.recoverLocal).mockResolvedValue({
    version_id: "recovered-version",
    library_paper_id: "library-paper",
    status: "partial",
    local_recovery: {
      ...recoveryPreview,
      available: false,
      published_version_id: "recovered-version",
    },
  });
});

const recoveryPreview = {
  version: "knowledge-local-recovery-1" as const,
  available: true,
  preview_fingerprint: "synthetic-preview-fingerprint",
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
};

const diagnosticJob = (
  result: Job["result"],
  kind = "knowledge_extract",
): Job => ({
  id: "knowledge-invalid",
  kind,
  project_id: "synthetic-project",
  status: "failed",
  stage: "failed",
  attempt: 1,
  error: "KNOWLEDGE_RESPONSE_INVALID",
  result,
  created_at: "2026-11-20T00:00:00Z",
  updated_at: "2026-11-20T00:00:01Z",
});

test("a terminal task can be archived through the menu while an active task cannot", async () => {
  const complete = {
    ...diagnosticJob(null, "pdf_import"),
    id: "complete-import",
    status: "succeeded" as const,
  };
  const active = {
    ...diagnosticJob(null, "pdf_import"),
    id: "active-import",
    status: "running" as const,
  };
  vi.mocked(api.jobs).mockResolvedValue([complete, active]);
  vi.mocked(archiveApi.stage).mockImplementation(async () => {
    vi.mocked(api.jobs).mockResolvedValue([active]);
    return {
      id: "job-archive",
      kind: "job",
      target_id: complete.id,
      title: "导入论文",
      archived_at: "2026-11-22",
      project_id: null,
      status: "archived",
    };
  });
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <JobHistory connected />
    </QueryClientProvider>,
  );
  const finishedRow = (await screen.findByText(/PDF 导入 · 已完成/)).closest(
    "article",
  )!;
  const activeRow = (await screen.findByText(/PDF 导入 · 正在处理/)).closest(
    "article",
  )!;
  expect(
    within(activeRow).queryByRole("button", { name: "归档任务" }),
  ).toBeNull();
  finishedRow.focus();
  await userEvent.keyboard("{Shift>}{F10}{/Shift}");
  await userEvent.click(
    await screen.findByRole("menuitem", { name: "归档任务" }),
  );
  expect(await screen.findByText("任务已移至归档管理。")).toBeVisible();
  expect(archiveApi.stage).toHaveBeenCalledExactlyOnceWith("job", complete.id);
  await waitFor(() => expect(finishedRow).not.toBeInTheDocument());
  expect(activeRow).toBeInTheDocument();
});

const diagnostic = {
  version: "knowledge-diagnostic-1",
  code: "KNOWLEDGE_RESPONSE_INVALID",
  category: "schema",
  summary: "返回内容缺少必需字段，知识版本未保存。",
  issues: [
    { path: "$.nodes[0].type", code: "missing", message: "缺少必需字段。" },
  ],
  request_sent: true,
  raw_available: true,
  action: "原始响应已保留，请检查字段结构后决定是否显式继续。",
};

test("reading jobs display distinct names from their frozen task subtypes", async () => {
  const tasks = [
    "paper_card_set",
    "paper_reading",
    "translation",
    "paper_overview",
  ] as const;
  vi.mocked(api.jobs).mockResolvedValue(
    tasks.map((reading_task) => ({
      ...diagnosticJob(null, "llm_document_postprocess"),
      id: reading_task,
      reading_task,
      error: null,
    })),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <JobHistory connected />
    </QueryClientProvider>,
  );
  expect(await screen.findByText("论文卡片集生成 · 失败")).toBeVisible();
  expect(screen.getByText("全文精读笔记生成 · 失败")).toBeVisible();
  expect(screen.getByText("逐段中文翻译 · 失败")).toBeVisible();
  expect(screen.getByText("论文概览生成 · 失败")).toBeVisible();
  expect(screen.queryByText(/模型阅读内容生成/)).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "重试本地处理" }),
  ).not.toBeInTheDocument();
});

test("local recovery review and explicit publish are attached to the failed task record", async () => {
  const job = {
    ...diagnosticJob({ knowledge_diagnostic: diagnostic }),
    id: "schema-failed-job",
    error: "KNOWLEDGE_RESPONSE_SCHEMA_INVALID",
  };
  vi.mocked(api.jobs).mockResolvedValue([job]);
  vi.mocked(knowledgeApi.runs).mockResolvedValue({
    items: [
      {
        id: "schema-failed-run",
        job_id: job.id,
        kind: "extract",
        status: "failed",
        local_recovery: recoveryPreview,
        created_at: job.created_at,
      },
    ],
    total: 1,
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <JobHistory connected />
    </QueryClientProvider>,
  );

  await userEvent.click(
    await screen.findByRole("button", { name: "预览本机恢复" }),
  );
  const dialog = await screen.findByRole("dialog", { name: "本机恢复预览" });
  await waitFor(() =>
    expect(knowledgeApi.localRecovery).toHaveBeenCalledExactlyOnceWith(
      "schema-failed-run",
    ),
  );
  expect(within(dialog).getByText("USES · METHOD → CONCEPT")).toBeVisible();
  expect(
    within(dialog).getByText(
      "USES 仅允许 RESEARCH_QUESTION → METHOD；当前为 METHOD → CONCEPT。",
    ),
  ).toBeVisible();
  expect(knowledgeApi.recoverLocal).not.toHaveBeenCalled();
  expect(api.jobAction).not.toHaveBeenCalled();

  await userEvent.click(
    within(dialog).getByRole("button", { name: "确认保存为部分知识" }),
  );
  await waitFor(() =>
    expect(knowledgeApi.recoverLocal).toHaveBeenCalledExactlyOnceWith(
      "schema-failed-run",
      recoveryPreview.preview_fingerprint,
    ),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "已保存为部分知识：保留 19 个知识节点和 9 条关系，隔离 1 条关系；未调用模型。",
  );
  expect(api.jobAction).not.toHaveBeenCalled();
  view.unmount();
  client.clear();
});

test("quote recovery previews excluded nodes and dependent relations before a local save", async () => {
  const job = { ...diagnosticJob(null), error: "KNOWLEDGE_QUOTE_MISMATCH" };
  const quotePreview = {
    version: "knowledge-local-recovery-2" as const,
    available: true,
    preview_fingerprint: "synthetic-quote-fingerprint",
    original_nodes: 18,
    original_edges: 18,
    kept_nodes: 17,
    kept_edges: 17,
    excluded_nodes: [
      {
        index: 1,
        path: "graph.nodes[1]",
        code: "invalid_quote",
        node_type: "FINDING",
        reason: "该节点的引文无法在指定原文中定位。",
      },
    ],
    excluded_edges: [
      {
        index: 2,
        path: "graph.edges[2]",
        code: "excluded_endpoint",
        relation_type: "EVALUATES",
        source_type: "METHOD",
        target_type: "FINDING",
        reason: "该关系依赖未通过引文校验的节点。",
      },
    ],
  };
  vi.mocked(api.jobs).mockResolvedValue([job]);
  vi.mocked(knowledgeApi.runs).mockResolvedValue({
    items: [
      {
        id: "quote-failed-run",
        job_id: job.id,
        kind: "extract",
        status: "failed",
        local_recovery: quotePreview,
        created_at: job.created_at,
      },
    ],
    total: 1,
  });
  vi.mocked(knowledgeApi.localRecovery).mockResolvedValue(quotePreview);
  vi.mocked(knowledgeApi.recoverLocal).mockResolvedValue({
    version_id: "quote-recovered-version",
    library_paper_id: "library-paper",
    status: "partial",
    local_recovery: {
      ...quotePreview,
      available: false,
      published_version_id: "quote-recovered-version",
    },
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <JobHistory connected />
    </QueryClientProvider>,
  );

  await userEvent.click(
    await screen.findByRole("button", { name: "预览本机恢复" }),
  );
  const dialog = await screen.findByRole("dialog", { name: "本机恢复预览" });
  expect(
    await within(dialog).findByRole("heading", {
      name: "将隔离的知识节点（1）",
    }),
  ).toBeVisible();
  expect(within(dialog).getByText("节点 2 · 结果")).toBeVisible();
  expect(
    within(dialog).getByText("该节点的引文无法在指定原文中定位。"),
  ).toBeVisible();
  expect(
    within(dialog).getByText("该关系依赖未通过引文校验的节点。"),
  ).toBeVisible();
  expect(within(dialog).getByText(/模型请求为 0 次/)).toBeVisible();
  expect(knowledgeApi.recoverLocal).not.toHaveBeenCalled();

  await userEvent.click(
    within(dialog).getByRole("button", { name: "确认保存为部分知识" }),
  );
  expect(
    await screen.findByText(
      "已保存为部分知识。保留 17 个知识节点和 17 条关系，隔离 1 个知识节点和 1 条关系。模型请求为 0 次。",
    ),
  ).toBeVisible();
  expect(knowledgeApi.recoverLocal).toHaveBeenCalledExactlyOnceWith(
    "quote-failed-run",
    quotePreview.preview_fingerprint,
  );
  expect(api.jobAction).not.toHaveBeenCalled();
  view.unmount();
  client.clear();
});

test.each([
  "等待首段正文或公开推理超过 90 秒，未观测到生成活动。",
  "距上次正文或公开推理增量已超过 180 秒，触发无生成活动超时。",
])(
  "transport timeout details remain visible without resending: %s",
  async (summary) => {
    vi.mocked(api.jobs).mockResolvedValue([
      {
        ...diagnosticJob({
          knowledge_diagnostic: {
            ...diagnostic,
            code: "KNOWLEDGE_PROVIDER_TIMEOUT",
            category: "transport",
            summary,
            issues: [],
            raw_available: false,
            action:
              "确认等待策略后再显式继续；公开推理增量也算生成活动，纯心跳不算。",
          },
        }),
        error: "KNOWLEDGE_PROVIDER_TIMEOUT",
      },
    ]);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const view = render(
      <QueryClientProvider client={client}>
        <JobHistory connected />
      </QueryClientProvider>,
    );
    const details = await screen.findByRole("region", {
      name: "知识任务错误详情",
    });
    expect(within(details).getByText("失败原因 · 请求与连接")).toBeVisible();
    expect(within(details).getByText(summary)).toBeVisible();
    expect(
      within(details).getByText(/公开推理增量也算生成活动，纯心跳不算/),
    ).toBeVisible();
    expect(
      within(details).getByText(/发送记录：已标记；费用未知/),
    ).toHaveTextContent("原始响应：没有可检查的响应");
    expect(screen.queryByRole("button", { name: /重试|继续/ })).toBeNull();
    expect(api.jobAction).not.toHaveBeenCalled();
    view.unmount();
    client.clear();
  },
);

test.each(["knowledge_extract", "knowledge_connect"])(
  "shows safe diagnostic summary, exact issue and recovery guidance directly on %s task",
  async (kind) => {
    vi.mocked(api.jobs).mockResolvedValue([
      diagnosticJob(
        {
          knowledge_diagnostic: {
            ...diagnostic,
            raw_response: "PRIVATE_RAW_RESPONSE",
            source_quote: "PRIVATE_PAPER_SOURCE",
            traceback: "PRIVATE_TRACEBACK",
          },
          raw_response: "PRIVATE_TOP_LEVEL_RAW",
        },
        kind,
      ),
    ]);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const view = render(
      <QueryClientProvider client={client}>
        <JobHistory
          connected
          projectNames={{ "synthetic-project": "合成项目" }}
        />
      </QueryClientProvider>,
    );
    const details = await screen.findByRole("region", {
      name: "知识任务错误详情",
    });
    expect(within(details).getByText(diagnostic.summary)).toBeVisible();
    expect(within(details).getByText("失败原因 · 字段结构")).toBeVisible();
    expect(within(details).getByText("$.nodes[0].type")).not.toBeVisible();
    await userEvent.click(within(details).getByText("诊断详情"));
    expect(within(details).getByText("$.nodes[0].type")).toBeVisible();
    expect(
      within(details).getByRole("list", { name: "知识任务校验问题" }),
    ).toHaveTextContent("（missing）：缺少必需字段。");
    expect(
      within(details).getByText(/发送记录：已标记；费用未知/),
    ).toHaveTextContent("原始响应：已在本机保留");
    expect(
      within(details).getByText(`处理建议：${diagnostic.action}`),
    ).toBeVisible();
    expect(screen.queryByText(/错误详情在本条任务记录中显示/)).toBeNull();
    expect(screen.queryByText(/PRIVATE_/)).toBeNull();
    expect(screen.queryByText(/到研究内容知识库查看原因/)).toBeNull();
    expect(
      screen.queryByRole("button", { name: /重试本地处理|格式修复/ }),
    ).toBeNull();
    expect(api.jobAction).not.toHaveBeenCalled();
    view.unmount();
    client.clear();
  },
);

test("legacy unknown diagnostics do not claim a format error or an available raw response", async () => {
  vi.mocked(api.jobs).mockResolvedValue([
    diagnosticJob({
      knowledge_diagnostic: {
        ...diagnostic,
        category: "unknown",
        summary: "旧任务没有保留失败细节，无法判定具体原因。",
        issues: [],
        raw_available: false,
        action: "保留失败记录；决定继续前请确认模型配置和请求预算。",
      },
    }),
  ]);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <JobHistory connected />
    </QueryClientProvider>,
  );
  const details = await screen.findByRole("region", {
    name: "知识任务错误详情",
  });
  expect(within(details).getByText("失败原因 · 原因未确定")).toBeVisible();
  expect(within(details).getByText(/旧任务没有保留失败细节/)).toBeVisible();
  await userEvent.click(within(details).getByText("诊断详情"));
  expect(within(details).getByText(/原始响应：没有可检查的响应/)).toBeVisible();
  expect(
    within(details).queryByText(/字段结构|来源校验|已在本机保留/),
  ).toBeNull();
  expect(within(details).queryByRole("list")).toBeNull();
  expect(api.jobAction).not.toHaveBeenCalled();
  view.unmount();
  client.clear();
});

test("project task history displays source diagnostics without fetching or rendering raw content", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [
      diagnosticJob({
        knowledge_diagnostic: {
          ...diagnostic,
          category: "source",
          summary: "模型引用的来源编号不属于本次冻结材料。",
          issues: [
            {
              path: "$.nodes[1].source_refs[0]",
              code: "source_not_allowed",
              message: "来源编号不在允许范围内。",
            },
          ],
        },
      }),
    ],
    next_cursor: null,
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <JobHistory connected projectId="synthetic-project" />
    </QueryClientProvider>,
  );
  const details = await screen.findByRole("region", {
    name: "知识任务错误详情",
  });
  expect(within(details).getByText("失败原因 · 来源校验")).toBeVisible();
  await userEvent.click(within(details).getByText("诊断详情"));
  expect(within(details).getByText("$.nodes[1].source_refs[0]")).toBeVisible();
  expect(api.jobs).not.toHaveBeenCalled();
  expect(api.jobAction).not.toHaveBeenCalled();
  view.unmount();
  client.clear();
});

test.each([
  null,
  {
    knowledge_diagnostic: {
      ...diagnostic,
      version: "unsupported-version",
      raw_response: "PRIVATE_RAW_RESPONSE",
    },
  },
])(
  "missing or unsupported legacy projection reports uncertainty without inventing details",
  async (result) => {
    vi.mocked(api.jobs).mockResolvedValue([diagnosticJob(result)]);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const view = render(
      <QueryClientProvider client={client}>
        <JobHistory connected />
      </QueryClientProvider>,
    );
    expect(
      await screen.findByText(/此历史任务没有可用的细分诊断/),
    ).toBeVisible();
    expect(screen.queryByText(/PRIVATE_|发送记录：|原始响应：/)).toBeNull();
    expect(api.jobAction).not.toHaveBeenCalled();
    view.unmount();
    client.clear();
  },
);

test.each(["knowledge_extract", "knowledge_connect"])(
  "directs budget failure %s to explicit knowledge continuation",
  async (kind) => {
    const job: Job = {
      id: "knowledge-budget-failed",
      kind,
      project_id: null,
      status: "failed",
      stage: "failed",
      attempt: 1,
      error: "KNOWLEDGE_INPUT_BUDGET_EXCEEDED",
      result: null,
      created_at: "2026-11-20T00:00:00Z",
      updated_at: "2026-11-20T00:00:01Z",
    };
    vi.mocked(api.jobs).mockResolvedValue([job]);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const view = render(
      <QueryClientProvider client={client}>
        <JobHistory connected />
      </QueryClientProvider>,
    );
    expect(
      await screen.findByText(/完整输入超过知识库单次预算/),
    ).toHaveTextContent("本次检查未发送模型请求");
    expect(screen.queryByRole("button", { name: "重试本地处理" })).toBeNull();
    expect(api.jobAction).not.toHaveBeenCalled();
    view.unmount();
    client.clear();
  },
);

test.each(["llm_document_parse", "pdf_import", "zotero_import"])(
  "requires an explicit paid continuation for failed model job %s",
  async (kind) => {
    const user = userEvent.setup();
    const job: Job = {
      id: "failed-model-job",
      kind,
      project_id: "synthetic-project",
      status: "failed",
      stage: "failed",
      attempt: 1,
      error: "Synthetic bounded failure",
      result: {
        document_batches: { total: 3, completed: 1, requests_sent: 2 },
      },
      created_at: "2026-11-18T00:00:00Z",
      updated_at: "2026-11-18T00:00:01Z",
    };
    vi.mocked(api.jobs).mockResolvedValue([job]);
    vi.mocked(api.jobAction).mockResolvedValue({ ...job, status: "queued" });
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const view = render(
      <QueryClientProvider client={client}>
        <JobHistory connected />
      </QueryClientProvider>,
    );
    const resume = await screen.findByRole("button", {
      name: "确认继续未完成解析（可能收费）",
    });
    expect(screen.getByText(/若请求已发送但结果不确定/)).toHaveTextContent(
      "点击继续即确认再次请求，可能再次收费；系统不会自动重发",
    );
    expect(
      screen.queryByRole("button", { name: "重试本地处理" }),
    ).not.toBeInTheDocument();
    expect(api.jobAction).not.toHaveBeenCalled();
    await user.click(resume);
    await waitFor(() => expect(api.jobAction).toHaveBeenCalledTimes(1));
    expect(api.jobAction).toHaveBeenCalledWith(
      job.id,
      "retry",
      expect.any(String),
    );
    view.unmount();
    client.clear();
  },
);

test("local import retry keeps the local action label", async () => {
  const job: Job = {
    id: "failed-local-job",
    kind: "pdf_import",
    project_id: "synthetic-project",
    status: "failed",
    stage: "failed",
    attempt: 1,
    error: "Synthetic local read failure",
    result: null,
    created_at: "2026-11-18T00:00:00Z",
    updated_at: "2026-11-18T00:00:01Z",
  };
  vi.mocked(api.jobs).mockResolvedValue([job]);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <JobHistory connected />
    </QueryClientProvider>,
  );
  expect(
    await screen.findByRole("button", { name: "重试本地处理" }),
  ).toBeVisible();
  expect(screen.queryByText(/可能再次收费/)).not.toBeInTheDocument();
  view.unmount();
  client.clear();
});

test.each([true, false, "true", null, [true]])(
  "exhausted boundary continuation requires an explicit backend flag %s",
  async (available) => {
    const user = userEvent.setup();
    const job: Job = {
      id: "boundary-failed",
      kind: "llm_document_parse",
      project_id: "synthetic-project",
      status: "failed",
      stage: "failed",
      attempt: 3,
      error: "MODEL_DOCUMENT_PROVIDER_HTTP_ERROR",
      result: {
        document_request: { http_status: 400 },
        document_batches: {
          total: 3,
          completed: 3,
          current: 1,
          current_kind: "boundary",
          boundaries_total: 2,
          compatibility_retry_available: available,
        },
      },
      created_at: "2026-11-18T00:00:00Z",
      updated_at: "2026-11-18T00:00:01Z",
    };
    vi.mocked(api.jobs).mockResolvedValue([job]);
    vi.mocked(api.jobAction).mockResolvedValue({ ...job, status: "queued" });
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const view = render(
      <QueryClientProvider client={client}>
        <JobHistory connected />
      </QueryClientProvider>,
    );
    await screen.findByText("模型章节解析 · 失败");
    expect(api.jobAction).not.toHaveBeenCalled();
    if (available === true) {
      await user.click(
        screen.getByRole("button", {
          name: "确认继续边界复核（可能收费）",
        }),
      );
      await waitFor(() => expect(api.jobAction).toHaveBeenCalledTimes(1));
      expect(api.jobAction).toHaveBeenCalledWith(
        job.id,
        "retry",
        expect.any(String),
      );
    } else {
      expect(
        screen.queryByRole("button", { name: /确认继续|重试本地处理/ }),
      ).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "归档任务" })).toBeEnabled();
    }
    view.unmount();
    client.clear();
  },
);

test("exhausted publication recovery is clearly distinct from a paid retry", async () => {
  const user = userEvent.setup();
  const job: Job = {
    id: "publication-failed",
    kind: "pdf_import",
    project_id: "synthetic-project",
    status: "failed",
    stage: "failed",
    attempt: 4,
    error: "MODEL_DOCUMENT_PUBLISH_INTEGRITY_ERROR",
    result: {
      failure_diagnostics: {
        database_dialect: "sqlite",
        sqlite_errorcode: 2067,
        sqlite_errorname: "SQLITE_CONSTRAINT_UNIQUE",
        constraint_category: "unique",
      },
      document_batches: {
        total: 3,
        completed: 3,
        boundaries_completed: 2,
        publication_retry_available: true,
      },
    },
    created_at: "2026-11-18T00:00:00Z",
    updated_at: "2026-11-18T00:00:01Z",
  };
  vi.mocked(api.jobs).mockResolvedValue([job]);
  vi.mocked(api.jobAction).mockResolvedValue({ ...job, status: "queued" });
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <JobHistory connected />
    </QueryClientProvider>,
  );
  await user.click(
    await screen.findByRole("button", {
      name: "仅重新发布章节（不重发批次）",
    }),
  );
  await user.click(screen.getByText("诊断详情", { selector: "summary" }));
  expect(
    screen.getByText(/SQLITE · 唯一约束 · SQLITE_CONSTRAINT_UNIQUE \(2067\)/),
  ).toBeVisible();
  expect(
    screen.getByText(/原计划选中的概览或精读任务仍会继续，可能产生模型请求/),
  ).toBeVisible();
  await waitFor(() => expect(api.jobAction).toHaveBeenCalledTimes(1));
  expect(api.jobAction).toHaveBeenCalledWith(
    job.id,
    "retry",
    expect.any(String),
  );
  view.unmount();
  client.clear();
});

test.each([
  ["document_source", "读取 Zotero PDF 附件"],
  ["preparing_provider", "准备文档解析模型"],
  ["model_parsing", "模型正在解析 PDF，等待完整结果返回"],
  ["document_rendering", "正在准备 PDF 页面图片"],
  ["document_connecting", "正在连接文档解析服务"],
  ["document_uploading", "正在发送论文材料"],
  ["document_waiting", "论文材料已发送，等待模型响应"],
  ["document_receiving", "正在接收模型解析结果"],
  ["validating_document", "校验模型返回的章节、公式与表格"],
  ["saving_document", "保存章节正文、公式与表格"],
])("shows the actual document parse stage %s", async (stage, label) => {
  const job: Job = {
    id: "synthetic-job",
    kind: "llm_document_parse",
    project_id: "synthetic-project",
    status: "running",
    stage,
    attempt: 1,
    error: null,
    result: null,
    created_at: "2026-11-18T00:00:00Z",
    updated_at: "2026-11-18T00:00:00Z",
  };
  vi.mocked(api.jobs).mockResolvedValue([job]);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <JobHistory connected />
    </QueryClientProvider>,
  );
  expect(await screen.findByText(label)).toBeVisible();
  expect(screen.getByText("模型章节解析 · 正在处理")).toBeVisible();
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  expect(api.jobAction).not.toHaveBeenCalled();
  view.unmount();
  client.clear();
});
