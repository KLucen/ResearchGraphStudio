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
