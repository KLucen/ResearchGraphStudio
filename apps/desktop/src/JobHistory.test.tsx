import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { JobHistory } from "./JobHistory";
import { api, type Job, type JobList } from "./api";

vi.mock("./api", () => ({
  api: { projectJobs: vi.fn(), jobAction: vi.fn(), job: vi.fn() },
}));
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.job).mockImplementation(() => new Promise(() => {}));
});
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
function mount(connected = true, cached?: JobList, single?: Job) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  if (cached)
    client.setQueryData(["jobs", "p"], { pages: [cached], pageParams: [null] });
  if (single) client.setQueryData(["job", single.id], single);
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

test("continue shows submission feedback before the returned continuation is available", async () => {
  let complete!: (value: Job) => void;
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [
      job("old", {
        kind: "knowledge_extract",
        status: "failed",
        error:
          "Schema 校验失败：items.1.Claim.kind_note_unused (extra_forbidden)",
      }),
    ],
    next_cursor: null,
  });
  vi.mocked(api.jobAction).mockImplementation(
    () => new Promise((resolve) => (complete = resolve)),
  );
  mount();
  await userEvent.click(
    await screen.findByRole("button", { name: "继续未完成批次" }),
  );
  expect(screen.getByRole("button", { name: "正在提交续接…" })).toBeDisabled();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  complete(
    job("successor", {
      kind: "knowledge_extract",
      status: "queued",
      result: { resumed_from: "old" },
    }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "续接任务已响应 · 等待处理",
  );
  expect(screen.getByText("知识抽取 · 等待处理")).toBeVisible();
  expect(screen.getByRole("link", { name: "查看续接结果" })).toHaveAttribute(
    "href",
    "#job-successor",
  );
});

test("an older completed successor is shown even when the current history pages omit it", async () => {
  vi.mocked(api.projectJobs).mockImplementation(async (_project, cursor) =>
    cursor
      ? {
          items: [
            job("old", {
              kind: "knowledge_extract",
              status: "failed",
              error: "历史 Schema 失败",
              attempt: 3,
              resume_adapter_available: true,
            }),
          ],
          next_cursor: null,
        }
      : { items: [job("recent")], next_cursor: "recent" },
  );
  vi.mocked(api.jobAction).mockResolvedValue(
    job("older-successor", {
      kind: "knowledge_extract",
      status: "succeeded",
      result: {
        resumed_from: "old",
        completed_batches: "34",
        total_batches: "34",
      },
    }),
  );
  mount();
  await userEvent.click(
    await screen.findByRole("button", { name: "加载更早任务" }),
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "继续未完成批次" }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "此前的续接任务已完成，无需重复抽取。",
  );
  expect(screen.getByText("历史 Schema 失败")).toBeVisible();
  expect(screen.getByText("知识抽取 · 已完成")).toBeVisible();
  expect(screen.getByText("已保存 34 / 34 个抽取批次")).toBeVisible();
  expect(screen.getByRole("link", { name: "查看续接结果" })).toHaveAttribute(
    "href",
    "#job-older-successor",
  );
  expect(document.getElementById("job-older-successor")).toBeInTheDocument();
  expect(api.jobAction).toHaveBeenCalledTimes(1);
  expect(
    screen.queryByRole("button", { name: "继续未完成批次" }),
  ).not.toBeInTheDocument();
});

test("a previously failed successor is visible and is not presented as newly queued", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [job("old", { kind: "knowledge_extract", status: "failed" })],
    next_cursor: null,
  });
  vi.mocked(api.jobAction).mockResolvedValue(
    job("failed-successor", {
      kind: "knowledge_extract",
      status: "failed",
      error: "续接任务证据发生变化",
      result: { resumed_from: "old" },
    }),
  );
  mount();
  await userEvent.click(
    await screen.findByRole("button", { name: "继续未完成批次" }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "续接任务已响应 · 失败；请查看续接任务的错误信息。",
  );
  expect(screen.getByText("续接任务证据发生变化")).toBeVisible();
  expect(screen.queryByText("知识抽取 · 等待处理")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "查看续接结果" })).toHaveAttribute(
    "href",
    "#job-failed-successor",
  );
});

test("an authoritative completed retry result replaces an older single-job queued cache", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [job("old", { kind: "knowledge_extract", status: "failed" })],
    next_cursor: null,
  });
  const queued = job("offpage", {
    kind: "knowledge_extract",
    status: "queued",
    result: { resumed_from: "old" },
  });
  vi.mocked(api.jobAction).mockResolvedValue({
    ...queued,
    status: "succeeded",
  });
  mount(true, undefined, queued);
  await userEvent.click(
    await screen.findByRole("button", { name: "继续未完成批次" }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "此前的续接任务已完成，无需重复抽取。",
  );
  expect(screen.getByText("知识抽取 · 已完成")).toBeVisible();
  expect(screen.queryByText("知识抽取 · 等待处理")).not.toBeInTheDocument();
  expect(api.job).not.toHaveBeenCalled();
});

test("a continuation outside loaded history pages polls its own actual status", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [job("old", { kind: "knowledge_extract", status: "failed" })],
    next_cursor: null,
  });
  const queued = job("offpage", {
    kind: "knowledge_extract",
    status: "queued",
    result: { resumed_from: "old" },
  });
  vi.mocked(api.jobAction).mockResolvedValue(queued);
  vi.mocked(api.job)
    .mockResolvedValueOnce(queued)
    .mockResolvedValue({ ...queued, status: "succeeded" });
  mount();
  await userEvent.click(
    await screen.findByRole("button", { name: "继续未完成批次" }),
  );
  expect(await screen.findByText("知识抽取 · 等待处理")).toBeVisible();
  expect(
    await screen.findByText("知识抽取 · 已完成", {}, { timeout: 3500 }),
  ).toBeVisible();
  expect(screen.getByRole("status")).toHaveTextContent(
    "此前的续接任务已完成，无需重复抽取。",
  );
  expect(api.job).toHaveBeenCalledWith("offpage");
  expect(api.jobAction).toHaveBeenCalledTimes(1);
  const completedReads = vi.mocked(api.job).mock.calls.length;
  await new Promise((resolve) => setTimeout(resolve, 1700));
  expect(api.job).toHaveBeenCalledTimes(completedReads);
});

test("a queued continuation that later fails shows its actual failure without claiming it never ran", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [
      job("old", {
        kind: "knowledge_extract",
        status: "failed",
        error: "原任务Schema失败",
      }),
    ],
    next_cursor: null,
  });
  const queued = job("offpage", {
    kind: "knowledge_extract",
    status: "queued",
    result: { resumed_from: "old" },
  });
  vi.mocked(api.jobAction).mockResolvedValue(queued);
  vi.mocked(api.job)
    .mockResolvedValueOnce(queued)
    .mockResolvedValue({
      ...queued,
      status: "failed",
      error: "续接模型响应未通过证据校验",
    });
  mount();
  await userEvent.click(
    await screen.findByRole("button", { name: "继续未完成批次" }),
  );
  expect(
    await screen.findByText(
      "续接模型响应未通过证据校验",
      {},
      { timeout: 3500 },
    ),
  ).toBeVisible();
  expect(screen.getByRole("status")).toHaveTextContent(
    "续接任务已响应 · 失败；请查看续接任务的错误信息。",
  );
  expect(screen.getByText("原任务Schema失败")).toBeVisible();
  expect(screen.queryByText(/未进入处理/)).not.toBeInTheDocument();
});

test("a completed cancel response cannot be overwritten by an older in-flight continuation read", async () => {
  let finishRead!: (value: Job) => void;
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [
      job("old", {
        kind: "knowledge_extract",
        status: "failed",
        error: "原任务失败",
      }),
    ],
    next_cursor: null,
  });
  const running = job("offpage", {
    kind: "knowledge_extract",
    status: "running",
    result: { resumed_from: "old" },
  });
  vi.mocked(api.jobAction)
    .mockResolvedValueOnce(running)
    .mockResolvedValueOnce({ ...running, status: "cancelled" });
  vi.mocked(api.job).mockImplementation(
    () => new Promise((resolve) => (finishRead = resolve)),
  );
  mount();
  await userEvent.click(
    await screen.findByRole("button", { name: "继续未完成批次" }),
  );
  await userEvent.click(await screen.findByRole("button", { name: "取消" }));
  expect(await screen.findByText("知识抽取 · 已取消")).toBeVisible();
  await act(async () => finishRead(running));
  expect(screen.getByText("知识抽取 · 已取消")).toBeVisible();
  expect(screen.queryByText("知识抽取 · 处理中")).not.toBeInTheDocument();
  expect(screen.getByText("原任务失败")).toBeVisible();
  expect(api.jobAction).toHaveBeenNthCalledWith(
    2,
    "offpage",
    "cancel",
    expect.any(String),
  );
});

test("a continuation status refresh failure preserves its last known result and explains it", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [job("old", { kind: "knowledge_extract", status: "failed" })],
    next_cursor: null,
  });
  vi.mocked(api.jobAction).mockResolvedValue(
    job("offpage", {
      kind: "knowledge_extract",
      status: "running",
      result: { resumed_from: "old" },
    }),
  );
  vi.mocked(api.job).mockRejectedValue(new Error("本地引擎连接暂时中断"));
  mount();
  await userEvent.click(
    await screen.findByRole("button", { name: "继续未完成批次" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "续接任务状态暂未刷新，保留上次结果：本地引擎连接暂时中断",
  );
  expect(screen.getByText("知识抽取 · 处理中")).toBeVisible();
  expect(screen.queryByText("知识抽取 · 已完成")).not.toBeInTheDocument();
});

test("a historical succeeded continuation with pending ranking is never described as complete", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [job("old", { kind: "knowledge_extract", status: "failed" })],
    next_cursor: null,
  });
  vi.mocked(api.jobAction).mockResolvedValue(
    job("pending-ranking", {
      kind: "knowledge_extract",
      status: "succeeded",
      result: { resumed_from: "old", ranking_status: "pending" },
    }),
  );
  mount();
  await userEvent.click(
    await screen.findByRole("button", { name: "继续未完成批次" }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "续接任务已响应 · 核心排序待完成",
  );
  expect(screen.getByText("知识抽取 · 核心排序待完成")).toBeVisible();
  expect(screen.queryByText(/此前的续接任务已完成/)).not.toBeInTheDocument();
  expect(screen.queryByText(/续接任务（已完成）/)).not.toBeInTheDocument();
});

test("a rejected continue request displays its error and preserves the historical failure", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [
      job("old", {
        kind: "knowledge_extract",
        status: "failed",
        error: "历史失败",
      }),
    ],
    next_cursor: null,
  });
  vi.mocked(api.jobAction).mockRejectedValue(
    new Error("来源已变动，请基于当前候选构建"),
  );
  mount();
  await userEvent.click(
    await screen.findByRole("button", { name: "继续未完成批次" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "来源已变动，请基于当前候选构建",
  );
  expect(screen.getByText("历史失败")).toBeVisible();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
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

test("provisional candidates remain distinct from completed core ranking and can continue", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [
      job("ranking-failed", {
        kind: "knowledge_extract",
        status: "failed",
        stage: "selecting",
        result: {
          completed_batches: "34",
          total_batches: "34",
          integrated_windows: 1,
          integration_windows: 1,
          selected_windows: 0,
          selection_windows: 1,
          published_units: 8,
          ranking_status: "pending",
          build_state: "complete",
          stage_failure: {
            stage: "selecting",
            category: "protocol",
            code: "INVALID_JSON",
            next_action: "继续未完成阶段；已保存知识和成功检查点保留",
          },
        },
      }),
    ],
    next_cursor: null,
  });
  vi.mocked(api.jobAction).mockResolvedValue(
    job("ranking-failed", { status: "queued" }),
  );
  mount();
  expect(
    await screen.findByText("结论候选与已有支撑；核心贡献排序未完成"),
  ).toBeVisible();
  expect(screen.getByText("已保存 34 / 34 个抽取批次")).toBeVisible();
  expect(screen.getByText("整合 1 / 1 个窗口")).toBeVisible();
  expect(screen.getByText("核心排序 0 / 1 个窗口")).toBeVisible();
  expect(screen.getByText("已保存 8 个结论候选单元")).toBeVisible();
  expect(screen.getByLabelText("任务阶段诊断")).toHaveTextContent(
    "排序核心贡献失败 · 模型响应格式错误（INVALID_JSON）",
  );
  expect(screen.getByText(/下一步：继续未完成阶段/)).toBeVisible();
  expect(screen.queryByText(/构建完成/)).not.toBeInTheDocument();
  expect(screen.queryByText(/已发布 8 个结论单元/)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "继续未完成批次" }));
  expect(api.jobAction).toHaveBeenCalledWith(
    "ranking-failed",
    "retry",
    expect.any(String),
  );
});

test("observed ranking progress is shown while running and successful ranking is explicit", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [
      job("running-ranking", {
        kind: "knowledge_extract",
        status: "running",
        stage: "selecting",
        result: {
          ranking_status: "pending",
          selected_windows: 0,
          selection_windows: 1,
        },
      }),
      job("complete-ranking", {
        kind: "knowledge_extract",
        result: {
          ranking_status: "complete",
          selected_windows: 1,
          selection_windows: 1,
          published_units: 3,
          build_state: "complete",
          stage_failure: null,
        },
      }),
    ],
    next_cursor: null,
  });
  mount();
  expect(await screen.findByText("排序核心贡献…")).toBeVisible();
  expect(screen.getByText("核心排序 0 / 1 个窗口")).toBeVisible();
  expect(screen.getByText("核心排序 1 / 1 个窗口")).toBeVisible();
  expect(screen.getByText("已发布 3 个结论单元 · 构建完成")).toBeVisible();
  expect(screen.queryByLabelText("任务阶段诊断")).not.toBeInTheDocument();
});

test.each([
  ["schema", "知识字段不符合规范", "继续未完成阶段"],
  ["context", "来源或任务快照不一致", "检查来源变动并刷新任务"],
  ["evidence", "证据引用未通过校验", "查看模型运行中的证据校验原因"],
  ["timeout", "模型请求超时", "继续未完成阶段"],
  [
    "structured_output_unsupported",
    "结构化输出模式不受支持",
    "检查模型与结构化输出能力后创建新任务",
  ],
  ["structured_output_refused", "模型拒绝生成结构化结果", "检查服务限制"],
])(
  "stage failure %s shows a category and useful next action",
  async (category, label, next) => {
    vi.mocked(api.projectJobs).mockResolvedValue({
      items: [
        job("diagnostic", {
          kind: "knowledge_extract",
          status: "failed",
          result: {
            stage_failure: {
              stage: "integrating",
              category,
              code: "SAFE_CODE",
            },
          },
        }),
      ],
      next_cursor: null,
    });
    mount();
    const diagnosis = await screen.findByLabelText("任务阶段诊断");
    expect(diagnosis).toHaveTextContent(
      `整合结论与支撑失败 · ${label}（SAFE_CODE）`,
    );
    expect(diagnosis).toHaveTextContent(next);
  },
);

test("pending ranking never claims completion and an earlier graph stays visible", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [
      job("pending", {
        kind: "knowledge_extract",
        result: {
          ranking_status: "pending",
          previous_graph_retained: true,
          selected_windows: 0,
          stage_failure: { stage: {}, category: {}, code: {}, next_action: {} },
        },
      }),
    ],
    next_cursor: null,
  });
  mount();
  expect(await screen.findByText("知识抽取 · 核心排序待完成")).toBeVisible();
  expect(screen.getByText("上次已发布的图谱保持可用。")).toBeVisible();
  expect(screen.getByText("核心排序 0 / 未知 个窗口")).toBeVisible();
  expect(screen.queryByText("知识抽取 · 已完成")).not.toBeInTheDocument();
  expect(
    screen.queryByText(/undefined|\[object Object\]/),
  ).not.toBeInTheDocument();
});

test("known request totals do not imply that historical model calls were free or absent", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [
      job("partial-accounting", {
        kind: "knowledge_extract",
        result: {
          model_calls: 0,
          model_calls_unrecorded_runs: 2,
          model_calls_status: "known_attempts_only",
          usage: {},
          cost: null,
        },
      }),
      job("recorded-accounting", {
        kind: "knowledge_extract",
        result: {
          model_calls: 3,
          model_calls_unrecorded_runs: 0,
          model_calls_status: "recorded",
          usage: { total_tokens: 90 },
          cost: null,
        },
      }),
    ],
    next_cursor: null,
  });
  mount();
  expect(
    await screen.findByText(/已记录模型调用 0 次；另 2条历史运行调用次数未知/),
  ).toHaveTextContent("Token 未提供");
  expect(screen.getByText(/^模型调用 3 次/)).toHaveTextContent("Token 90");
  expect(screen.queryByText(/^模型调用 0 次/)).not.toBeInTheDocument();
});

test("keyed contribution progress distinguishes output correction from extraction batches", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [
      job("repairing", {
        kind: "knowledge_extract",
        status: "running",
        stage: "selecting",
        result: {
          ranking_protocol: "reading-ranking-keyed-1",
          ranking_completed_claims: 36,
          ranking_total_claims: 38,
          ranking_request: 2,
          ranking_request_limit: 2,
          ranking_repairing: true,
          ranking_status: "pending",
          completed_batches: "6",
          total_batches: "6",
        },
      }),
    ],
    next_cursor: null,
  });
  mount();
  const progress = await screen.findByLabelText("贡献评估进度");
  expect(progress).toHaveTextContent("贡献评估输出已校验 36 / 38 个结论");
  expect(progress).toHaveTextContent(
    "正在自动修复未完成的输出字段 · 第 2 / 2 次请求（含首次请求）",
  );
  expect(screen.getByText("已保存 6 / 6 个抽取批次")).toBeVisible();
  expect(screen.queryByText(/构建完成/)).not.toBeInTheDocument();
});

test("exhausted correction retains candidates and graph without promising a repeated request", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [
      job("exhausted", {
        kind: "knowledge_extract",
        status: "failed",
        stage: "selecting",
        result: {
          ranking_protocol: "reading-ranking-keyed-1",
          ranking_completed_claims: 36,
          ranking_total_claims: 38,
          ranking_request: 2,
          ranking_request_limit: 2,
          ranking_repairing: true,
          ranking_status: "pending",
          previous_graph_retained: true,
          stage_failure: {
            stage: "selecting",
            category: "protocol",
            code: "RANKING_PROTOCOL_EXHAUSTED",
            next_action: "继续未完成阶段；已保存知识和成功检查点保留",
          },
        },
      }),
    ],
    next_cursor: null,
  });
  mount();
  const diagnosis = await screen.findByLabelText("任务阶段诊断");
  expect(diagnosis).toHaveTextContent("自动格式修复已达上限");
  expect(diagnosis).toHaveTextContent("已保存候选和旧图保留，继续不会重复请求");
  expect(diagnosis).not.toHaveTextContent("下一步：继续未完成阶段");
  expect(screen.getByText("上次已发布的图谱保持可用。")).toBeVisible();
  expect(screen.queryByText(/正在自动修复/)).not.toBeInTheDocument();
  expect(screen.queryByText(/更换模型/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "继续未完成批次" })).toBeVisible();
});

test("successful keyed evaluation is historical progress and never displays an active correction", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [
      job("complete", {
        kind: "knowledge_extract",
        result: {
          ranking_protocol: "reading-ranking-keyed-1",
          ranking_completed_claims: 38,
          ranking_total_claims: 38,
          ranking_request: 2,
          ranking_request_limit: 2,
          ranking_repairing: true,
          ranking_status: "complete",
        },
      }),
    ],
    next_cursor: null,
  });
  mount();
  expect(await screen.findByLabelText("贡献评估进度")).toHaveTextContent(
    "贡献评估输出已校验 38 / 38 个结论",
  );
  expect(screen.queryByText(/正在自动修复/)).not.toBeInTheDocument();
});

test("malformed keyed progress does not invent a count or stringify invalid values", async () => {
  vi.mocked(api.projectJobs).mockResolvedValue({
    items: [
      job("invalid", {
        kind: "knowledge_extract",
        result: {
          ranking_protocol: "reading-ranking-keyed-1",
          ranking_completed_claims: 39,
          ranking_total_claims: 38,
          ranking_request: {},
          ranking_request_limit: "two",
          ranking_repairing: true,
        },
      }),
    ],
    next_cursor: null,
  });
  mount();
  await screen.findByText("知识抽取 · 已完成");
  expect(screen.queryByLabelText("贡献评估进度")).not.toBeInTheDocument();
  expect(
    screen.queryByText(/undefined|\[object Object\]/),
  ).not.toBeInTheDocument();
});
