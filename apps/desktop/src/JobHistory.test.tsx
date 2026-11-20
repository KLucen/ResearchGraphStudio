import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { api, type Job } from "./api";
import { JobHistory } from "./JobHistory";

vi.mock("./api", () => ({
  api: { jobs: vi.fn(), projectJobs: vi.fn(), jobAction: vi.fn() },
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

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
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
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
