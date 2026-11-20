import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import type { Job } from "./api";
import { DocumentRequestStatus } from "./DocumentRequestStatus";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function job(status: Job["status"], details: Record<string, unknown>): Job {
  return {
    id: "fixture",
    project_id: "fixture",
    kind: "llm_document_parse",
    status,
    stage: "document_waiting",
    attempt: 1,
    error: null,
    result: { document_request: details },
    created_at: "2026-11-18T00:00:00Z",
    updated_at: "2026-11-18T00:00:00Z",
  };
}

test("shows real rendered page count and elapsed wait without claiming model completion", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-18T00:00:12Z"));
  render(
    <DocumentRequestStatus
      job={job("running", {
        started_at: "2026-11-18T00:00:00Z",
        rendered_pages: 2,
        page_count: 5,
        read_timeout_seconds: 600,
        total_timeout_seconds: 1800,
      })}
    />,
  );
  expect(screen.getByLabelText("文档请求状态")).toHaveTextContent(
    "已运行 12 秒 · 页面准备 2 / 5 页 · 单请求响应等待上限 600 秒 · 单请求总时限 1800 秒",
  );
  act(() => vi.advanceTimersByTime(2000));
  expect(screen.getByLabelText("文档请求状态")).toHaveTextContent(
    "已运行 14 秒",
  );
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
});

test("terminal tasks use recorded elapsed time and ignore unknown diagnostic content", () => {
  render(
    <DocumentRequestStatus
      job={job("failed", {
        started_at: "2026-11-18T00:00:00Z",
        elapsed_seconds: 90.19,
        read_timeout_seconds: 90,
        raw_body: "private fixture content",
        page_count: "invalid",
      })}
    />,
  );
  expect(screen.getByLabelText("文档请求状态")).toHaveTextContent(
    "请求用时 90 秒 · 单请求响应等待上限 90 秒",
  );
  expect(screen.queryByText(/private fixture/)).not.toBeInTheDocument();
});

test("shows batch progress even before individual request metadata exists", () => {
  const task = job("running", {});
  task.result = {
    document_batches: {
      total: 4,
      completed: 1,
      current: 2,
      page_start: 5,
      page_end: 9,
      requests_sent: 3,
      request_budget: 11,
      repairs_used: 1,
      boundaries_completed: 0,
      boundaries_total: 3,
      phase: "repairing",
    },
  };
  render(<DocumentRequestStatus job={task} />);
  expect(screen.getByLabelText("文档批次状态")).toHaveTextContent(
    "第 2 / 4 批 · 原始第 5–9 页 · 已校验 1 / 4 批 · 已发送 3 / 11 次请求 · 格式修复已用 1 次 · 边界复核 0 / 3 · 修复当前批次格式",
  );
  expect(screen.queryByLabelText("文档请求状态")).not.toBeInTheDocument();
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
});

test("shows only safe validation locations and fixed phase labels", () => {
  const task = job("failed", {});
  task.result = {
    document_batches: {
      total: 2,
      current: 1,
      phase: "private model response body",
      validation_errors: [
        {
          path: "segments[3].kind",
          code: "literal_error",
          input: "secret text",
        },
        { path: "segments.2.latex", code: "missing" },
        { path: "$", code: "value_error" },
        { path: "private response body with spaces", code: "missing" },
        { path: "segments[1].text", code: "private response with spaces" },
      ],
      raw_body: "secret text",
    },
  };
  render(<DocumentRequestStatus job={task} />);
  expect(screen.getByLabelText("文档校验位置")).toHaveTextContent(
    "segments[3].kind（literal_error）；segments.2.latex（missing）；$（value_error）",
  );
  expect(screen.queryByText(/private|secret/)).not.toBeInTheDocument();
});

test("ignores invalid batch metadata without rendering raw content", () => {
  const task = job("failed", {});
  task.result = {
    document_request: ["private"],
    document_batches: {
      total: "private",
      current: Number.POSITIVE_INFINITY,
      completed: -1,
      page_start: 1.2,
      page_end: 4,
      repairs_used: {},
      phase: "private",
      validation_errors: [{ path: "segments[0]\nprivate", code: "missing" }],
    },
  };
  const { container } = render(<DocumentRequestStatus job={task} />);
  expect(container).toBeEmptyDOMElement();
});

test("caps the displayed validation error count", () => {
  const task = job("failed", {});
  task.result = {
    document_batches: {
      validation_errors: Array.from({ length: 12 }, (_, index) => ({
        path: `segments[${index}].text`,
        code: "missing",
      })),
    },
  };
  render(<DocumentRequestStatus job={task} />);
  expect(screen.getByLabelText("文档校验位置")).toHaveTextContent(
    "segments[7].text",
  );
  expect(screen.getByLabelText("文档校验位置")).not.toHaveTextContent(
    "segments[8].text",
  );
});

test("distinguishes a rejected boundary review from completed body batches", () => {
  const task = job("failed", {
    http_status: 400,
    response_body: "private provider response",
  });
  task.result = {
    ...task.result,
    document_batches: {
      total: 3,
      completed: 3,
      current: 1,
      current_kind: "boundary",
      boundaries_total: 2,
      boundaries_completed: 0,
      page_start: 5,
      page_end: 6,
      phase: "failed",
    },
  };
  render(<DocumentRequestStatus job={task} />);
  const status = screen.getByLabelText("文档批次状态");
  expect(status).toHaveTextContent("第 1 / 2 个边界");
  expect(status).toHaveTextContent("正文批次已完成 · 边界复核失败");
  expect(status).toHaveTextContent("HTTP 状态 400");
  expect(status).not.toHaveTextContent("第 1 / 3 批");
  expect(screen.getByLabelText("文档请求拒绝提示")).toHaveTextContent(
    "服务拒绝请求，重复继续通常不能解决，请检查请求参数或安装修复版",
  );
  expect(screen.queryByText(/private provider/)).not.toBeInTheDocument();
});

test("shows publication failure instead of stale boundary and page details", () => {
  const task = job("failed", {});
  task.result = {
    document_batches: {
      total: 3,
      completed: 3,
      current: 1,
      current_kind: "publication",
      boundaries_total: 2,
      boundaries_completed: 2,
      page_start: 5,
      page_end: 6,
      phase: "publication_failed",
      publication_retry_available: true,
    },
  };
  render(<DocumentRequestStatus job={task} />);
  const status = screen.getByLabelText("文档批次状态");
  expect(status).toHaveTextContent("章节发布失败");
  expect(status).toHaveTextContent("已校验 3 / 3 批");
  expect(status).not.toHaveTextContent("边界复核失败");
  expect(status).not.toHaveTextContent("个边界");
  expect(status).not.toHaveTextContent("原始第");
});

test.each([
  ["queued", "等待重新发布章节"],
  ["running", "正在重新发布章节"],
] as const)("shows publication recovery status while %s", (state, label) => {
  const task = job(state, {});
  task.result = {
    document_batches: {
      total: 3,
      completed: 3,
      current_kind: "publication",
      phase: "publication_failed",
      publication_retry_available: true,
    },
  };
  render(<DocumentRequestStatus job={task} />);
  const status = screen.getByLabelText("文档批次状态");
  expect(status).toHaveTextContent(label);
  expect(status).not.toHaveTextContent("边界复核失败");
});

test.each(["400", 400.5, 99, 600, Infinity])(
  "does not render invalid HTTP status %s",
  (httpStatus) => {
    const { container } = render(
      <DocumentRequestStatus
        job={job("failed", { http_status: httpStatus })}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  },
);
