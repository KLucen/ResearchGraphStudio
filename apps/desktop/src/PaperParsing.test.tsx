import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "./api";
import { PaperParsing } from "./PaperParsing";
vi.mock("./api", () => ({
  request: vi.fn(async () => ({ profiles: [], roles: {} })),
  defaultPostImportPlan: () => ({
    parse: false,
    overview: true,
    reading: false,
    translation_mode: "none",
    modality: "auto",
    extract_formulas: true,
    extract_tables: true,
    allow_network: false,
  }),
  api: { parsePaper: vi.fn(), job: vi.fn() },
}));
beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value() {
      this.setAttribute("open", "");
    },
  });
});
function mount({ hasLocal = true, hasModel = true } = {}) {
  const onQueued = vi.fn();
  const onViewSource = vi.fn();
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <PaperParsing
        paperId="paper"
        projectId="p"
        connected
        hasLocal={hasLocal}
        hasModel={hasModel}
        source="local"
        onViewSource={onViewSource}
        onQueued={onQueued}
      />
    </QueryClientProvider>,
  );
  return { onQueued, onViewSource };
}
async function openActions(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "论文解析操作" }));
}
test("local parse failure can be retried without a model plan", async () => {
  const user = userEvent.setup();
  vi.mocked(api.parsePaper).mockResolvedValue({
    id: "local-job",
    status: "queued",
  } as never);
  vi.mocked(api.job).mockResolvedValue({
    id: "local-job",
    status: "failed",
    error: "synthetic read failure",
  } as never);
  const { onQueued } = mount();
  await openActions(user);
  await user.click(screen.getByRole("button", { name: "本地解析 / 重试" }));
  await screen.findByText(/synthetic read failure/);
  expect(api.parsePaper).toHaveBeenCalledWith("paper", { mode: "local" });
  expect(onQueued).toHaveBeenCalledWith("local");
  await openActions(user);
  await user.click(screen.getByRole("button", { name: "本地解析 / 重试" }));
  await waitFor(() => expect(api.parsePaper).toHaveBeenCalledTimes(2));
});
test("later model parsing requires explicit consent and clears it on reopening", async () => {
  const user = userEvent.setup();
  mount();
  await openActions(user);
  await user.click(screen.getByRole("button", { name: "使用模型重新解析" }));
  expect(screen.getByRole("button", { name: "确认模型解析" })).toBeDisabled();
  await user.click(
    screen.getByRole("checkbox", {
      name: "允许将所选 PDF 发送给已配置的论文解析模型",
    }),
  );
  expect(api.parsePaper).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "取消" }));
  await openActions(user);
  await user.click(screen.getByRole("button", { name: "使用模型重新解析" }));
  expect(screen.getByRole("button", { name: "确认模型解析" })).toBeDisabled();
});

test("all papers expose the same circular disclosure with unavailable source explained", async () => {
  const user = userEvent.setup();
  const { onViewSource } = mount({ hasLocal: true, hasModel: false });
  const trigger = screen.getByRole("button", { name: "论文解析操作" });
  expect(trigger).toHaveClass("paper-parsing-toggle");
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("button", { name: "本地解析 / 重试" })).toBeNull();
  await openActions(user);
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("button", { name: "本地解析 / 重试" })).toBeEnabled();
  expect(
    screen.getByRole("button", { name: "使用模型重新解析" }),
  ).toBeEnabled();
  expect(
    screen.getByRole("button", { name: "查看模型解析内容" }),
  ).toBeDisabled();
  expect(screen.getByText("尚无模型解析记录")).toBeVisible();
  const local = screen.getByRole("button", { name: "查看本地解析内容" });
  expect(local).toHaveAttribute("aria-pressed", "true");
  await user.click(local);
  expect(onViewSource).toHaveBeenCalledWith("local");
  expect(api.parsePaper).not.toHaveBeenCalled();
  expect(trigger).toHaveFocus();
  expect(trigger).toHaveAttribute("aria-expanded", "false");
});

test("source menu supports keyboard dismissal and outside dismissal without generating", async () => {
  const user = userEvent.setup();
  const { onViewSource } = mount({ hasLocal: false, hasModel: true });
  await openActions(user);
  expect(
    screen.getByRole("button", { name: "查看本地解析内容" }),
  ).toBeDisabled();
  expect(screen.getByText("尚未完成本地解析")).toBeVisible();
  await user.tab();
  await user.keyboard("{Escape}");
  const trigger = screen.getByRole("button", { name: "论文解析操作" });
  expect(trigger).toHaveFocus();
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  await openActions(user);
  await user.click(document.body);
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  await openActions(user);
  await user.click(screen.getByRole("button", { name: "查看模型解析内容" }));
  expect(onViewSource).toHaveBeenCalledWith("model");
  expect(api.parsePaper).not.toHaveBeenCalled();
});
