import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { JobHistory } from "./JobHistory";
import { api, type Job, type JobList } from "./api";

vi.mock("./api", () => ({ api: { projectJobs: vi.fn(), jobAction: vi.fn() } }));
beforeEach(() => vi.resetAllMocks());
function job(id: string, extra: Partial<Job> = {}): Job {
  return {
    id,
    project_id: "p",
    kind: "pdf_import",
    status: "succeeded",
    stage: "saving",
    attempt: 1,
    error: null,
    result: null,
    resume_adapter_available: false,
    created_at: "2026-10-30T00:00:00Z",
    updated_at: "2026-10-30T00:00:00Z",
    ...extra,
  };
}
function mount(connected = true, cached?: JobList) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  if (cached)
    client.setQueryData(["jobs", "p"], { pages: [cached], pageParams: [null] });
  return render(
    <QueryClientProvider client={client}>
      <JobHistory projectId="p" connected={connected} />
    </QueryClientProvider>,
  );
}

test("loads older jobs and can retry beyond the first page", async () => {
  const user = userEvent.setup();
  vi.mocked(api.projectJobs).mockImplementation(async (_project, cursor) =>
    cursor
      ? {
          items: [job("old", { status: "interrupted", error: "上次运行中断" })],
          next_cursor: null,
        }
      : {
          items: Array.from({ length: 10 }, (_, i) => job(String(i))),
          next_cursor: "9",
        },
  );
  vi.mocked(api.jobAction).mockResolvedValue(
    job("old", { status: "queued", stage: null }),
  );
  mount();
  await user.click(await screen.findByRole("button", { name: "加载更早任务" }));
  expect(await screen.findByText("上次运行中断")).toBeVisible();
  expect(screen.getByText("任务记录 · 已加载 11 项")).toBeVisible();
  expect(api.projectJobs).toHaveBeenCalledWith("p", "9");
  await user.click(screen.getByRole("button", { name: "重试" }));
  expect(api.jobAction).toHaveBeenCalledWith(
    "old",
    "retry",
    expect.any(String),
  );
  expect(
    screen.queryByRole("button", { name: "加载更早任务" }),
  ).not.toBeInTheDocument();
});

test("shows observed progress only while running and no fabricated percentages", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [
      job("running", { status: "running", stage: "parsing" }),
      job("complete"),
    ],
    next_cursor: null,
  });
  mount();
  expect(await screen.findByText("解析原文…")).toBeVisible();
  expect(screen.queryByText("保存结果…")).not.toBeInTheDocument();
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
});

test("saved split children do not imply the full extraction has finished", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [
      job("split", {
        kind: "knowledge_extract",
        status: "running",
        stage: "extracting",
        result: {
          completed_batches: "1",
          total_batches: "2",
          batches: [
            { index: 0, status: "succeeded", split_reason: "timeout" },
            { index: 1, status: "running", split_reason: "timeout" },
          ],
        },
      }),
    ],
    next_cursor: null,
  });
  mount();
  expect(await screen.findByText("知识抽取 · 处理中")).toBeVisible();
  expect(screen.getByText("已保存 1 / 2 个抽取批次")).toBeVisible();
  await userEvent.click(screen.getByText("批次详情（含拆分恢复）"));
  expect(screen.getByText("1:已保存（超时拆分后）")).toBeVisible();
  expect(screen.getByText("2:处理中（超时拆分后）")).toBeVisible();
  expect(screen.queryByText("知识抽取 · 已完成")).not.toBeInTheDocument();
});

test("offline cached history remains readable with actions and pagination disabled", () => {
  mount(false, {
    items: [
      job("failed", { status: "failed", error: "文件不可读" }),
      job("running", { status: "running" }),
    ],
    next_cursor: "running",
  });
  expect(screen.getByText("文件不可读")).toBeVisible();
  for (const name of ["重试", "取消", "加载更早任务"])
    expect(screen.getByRole("button", { name })).toBeDisabled();
  expect(api.projectJobs).not.toHaveBeenCalled();
});

test("pagination failure keeps loaded jobs and permits retry", async () => {
  const user = userEvent.setup();
  vi.mocked(api.projectJobs)
    .mockResolvedValueOnce({ items: [job("first")], next_cursor: "first" })
    .mockRejectedValueOnce(new Error("任务记录读取失败"))
    .mockResolvedValueOnce({ items: [job("older")], next_cursor: null });
  mount();
  await user.click(await screen.findByRole("button", { name: "加载更早任务" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "任务记录读取失败",
  );
  expect(
    within(screen.getByRole("region", { name: "任务列表" })).getByText(
      "PDF 导入 · 已完成",
    ),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "加载更早任务" }));
  expect(await screen.findByText("任务记录 · 已加载 2 项")).toBeVisible();
});

test("stream activity describes actual waiting and generation without claiming completion", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [
      job("thinking", {
        kind: "knowledge_extract",
        status: "running",
        result: {
          model_activity: {
            elapsed_seconds: 12,
            reasoning_characters: 45,
            content_characters: 0,
          },
        },
      }),
      job("receiving", {
        kind: "knowledge_extract",
        status: "running",
        result: {
          model_activity: {
            elapsed_seconds: 20,
            reasoning_characters: 45,
            content_characters: 100,
          },
        },
      }),
      job("stopped", {
        kind: "knowledge_extract",
        status: "failed",
        result: {
          model_activity: { elapsed_seconds: 90, content_characters: 999 },
        },
      }),
    ],
    next_cursor: null,
  });
  mount();
  expect(await screen.findByText("模型正在思考 · 已等待 12 秒")).toBeVisible();
  expect(
    screen.getByText("正在接收结构化结果（100 字符） · 已等待 20 秒"),
  ).toBeVisible();
  expect(screen.queryByText(/999 字符/)).not.toBeInTheDocument();
  expect(screen.queryByText("知识抽取 · 已完成")).not.toBeInTheDocument();
});

test("one ordinary continue action recovers an eligible old task without vendor-specific UI", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [
      job("old", {
        kind: "knowledge_extract",
        status: "failed",
        attempt: 3,
        resume_adapter_available: true,
      }),
    ],
    next_cursor: null,
  });
  vi.mocked(api.jobAction).mockResolvedValue(
    job("successor", { status: "queued" }),
  );
  mount();
  await userEvent.click(
    await screen.findByRole("button", { name: "继续未完成批次" }),
  );
  expect(api.jobAction).toHaveBeenCalledWith(
    "old",
    "retry",
    expect.any(String),
  );
  expect(screen.queryByText(/腾讯云/)).not.toBeInTheDocument();
});

test("history distinguishes a superseded failure from its current schema continuation", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [
      job("successor", {
        status: "queued",
        result: { resumed_from: "old", schema_upgrade: true },
      }),
      job("old", { status: "failed", error: "Historical timeout" }),
    ],
    next_cursor: null,
  });
  mount();
  expect(await screen.findByText(/历史任务，已创建续接任务/)).toBeVisible();
  expect(screen.getByText(/已切换新版抽取/)).toBeVisible();
  expect(screen.getByText("Historical timeout")).toBeVisible();
});
