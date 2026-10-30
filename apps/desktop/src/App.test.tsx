import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import App from "./App";
import { api } from "./api";

vi.mock("./api", () => ({
  api: {
    host: vi.fn(),
    health: vi.fn(),
    projects: vi.fn(),
    createProject: vi.fn(),
    jobs: vi.fn(),
    projectJobs: vi.fn().mockResolvedValue([]),
    restart: vi.fn(),
    papers: vi.fn(),
  },
}));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.host).mockResolvedValue({
    running: true,
    data_dir: "test-data",
    error: null,
  });
  vi.mocked(api.health).mockResolvedValue({
    status: "ok",
    version: "0.0.1",
    schema_version: "0001",
    protocol_version: 1,
    database: "ready",
    fts5: true,
  });
  vi.mocked(api.projects).mockResolvedValue({ items: [], next_cursor: null });
  vi.mocked(api.papers).mockResolvedValue({ items: [], next_cursor: null });
  vi.mocked(api.jobs).mockResolvedValue([]);
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
      <App />
    </QueryClientProvider>,
  );
}
test("create project persists via API and shows saved project", async () => {
  const user = userEvent.setup();
  vi.mocked(api.createProject).mockResolvedValue({
    id: "project-1",
    name: "研究一",
    description: "",
    created_at: "2026-10-27T00:00:00Z",
  });
  mount();
  await screen.findByText("你的第一个研究项目");
  await user.click(screen.getByRole("button", { name: "新建研究项目" }));
  await user.type(screen.getByLabelText("项目名称"), "研究一");
  await user.click(
    within(screen.getByRole("dialog")).getByRole("button", {
      name: "创建项目",
    }),
  );
  await screen.findByText("项目已保存");
  expect(api.createProject).toHaveBeenCalledWith(
    { name: "研究一", description: "" },
    expect.any(String),
  );
});
test("failed creation keeps the dialog and reuses idempotency key when retried", async () => {
  const user = userEvent.setup();
  vi.mocked(api.createProject)
    .mockRejectedValueOnce(new Error("连接中断"))
    .mockResolvedValueOnce({
      id: "p",
      name: "A",
      description: "",
      created_at: "2026-10-27T00:00:00Z",
    });
  mount();
  await screen.findByText("你的第一个研究项目");
  await user.click(screen.getByRole("button", { name: "新建研究项目" }));
  await user.type(screen.getByLabelText("项目名称"), "A");
  await user.click(
    within(screen.getByRole("dialog")).getByRole("button", {
      name: "创建项目",
    }),
  );
  await screen.findByRole("alert");
  await user.click(
    within(screen.getByRole("dialog")).getByRole("button", {
      name: "创建项目",
    }),
  );
  await screen.findByText("项目已保存");
  expect(vi.mocked(api.createProject).mock.calls[0][1]).toBe(
    vi.mocked(api.createProject).mock.calls[1][1],
  );
});
test("offline engine displays failure rather than fabricated projects", async () => {
  vi.mocked(api.health).mockRejectedValue(new Error("引擎未启动"));
  mount();
  await screen.findByRole("alert");
  expect(screen.getByRole("button", { name: "新建研究项目" })).toBeDisabled();
  expect(api.projects).not.toHaveBeenCalled();
});
