import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { Papers } from "./Papers";
import { api } from "./api";

vi.mock("./api", () => ({
  api: {
    papers: vi.fn(),
    jobs: vi.fn(),
    projectJobs: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
    importPdf: vi.fn(),
    paper: vi.fn(),
    chunks: vi.fn(),
  },
}));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.papers).mockResolvedValue({ items: [], next_cursor: null });
  vi.mocked(api.jobs).mockResolvedValue([]);
});
function mount(connected = true) {
  render(
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
      <Papers projectId="p" connected={connected} />
    </QueryClientProvider>,
  );
}
test("native selection receives explicit managed mode and cancellation creates no paper", async () => {
  const user = userEvent.setup();
  vi.mocked(api.importPdf).mockResolvedValue(null);
  mount();
  await user.selectOptions(screen.getByLabelText("保存方式"), "managed");
  await user.click(screen.getByRole("button", { name: "选择 PDF 导入" }));
  expect(api.importPdf).toHaveBeenCalledWith("p", "managed");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
test("offline import is disabled and picker error is visible", async () => {
  mount(false);
  expect(screen.getByRole("button", { name: "选择 PDF 导入" })).toBeDisabled();
});
test("selected paper shows version, page, raw text and parser limitation", async () => {
  const user = userEvent.setup();
  const paper = {
    id: "paper",
    project_id: "p",
    title: "Synthetic paper",
    created_at: "2026-10-29T00:00:00Z",
  };
  vi.mocked(api.papers).mockResolvedValue({
    items: [paper],
    next_cursor: null,
  });
  vi.mocked(api.paper).mockResolvedValue({
    paper,
    sources: [],
    revisions: [
      {
        id: "r",
        paper_id: "paper",
        sha256: "a".repeat(64),
        parser_version: "blocks-v1",
        page_count: 2,
        warnings: ["阅读顺序请对照原文核查"],
        created_at: paper.created_at,
      },
    ],
  });
  vi.mocked(api.chunks).mockResolvedValue({
    items: [
      {
        id: "c",
        revision_id: "r",
        page_index: 1,
        page_label: "S-2",
        block_index: 0,
        text: "No improvement was observed.",
        bbox: [40, 50, 200, 80],
      },
    ],
    next_cursor: null,
  });
  mount();
  await user.click(
    await screen.findByRole("button", { name: "Synthetic paper" }),
  );
  expect(await screen.findByText("No improvement was observed.")).toBeVisible();
  expect(screen.getByText(/PDF 第 2 页 · 块 1/)).toBeVisible();
  expect(screen.getByText("阅读顺序请对照原文核查")).toBeVisible();
});
test("native import rejection is shown without adding fake results", async () => {
  const user = userEvent.setup();
  vi.mocked(api.importPdf).mockRejectedValue("提交导入任务失败");
  mount();
  await user.click(screen.getByRole("button", { name: "选择 PDF 导入" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "提交导入任务失败",
  );
});
