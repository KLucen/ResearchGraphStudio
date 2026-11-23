import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { ArchiveWorkspace } from "./ArchiveWorkspace";
import { archiveApi, type ArchiveItem } from "./archiveApi";

vi.mock("./archiveApi", async (original) => ({
  ...(await original<typeof import("./archiveApi")>()),
  archiveApi: {
    list: vi.fn(),
    stage: vi.fn(),
    restore: vi.fn(),
    purge: vi.fn(),
  },
}));

beforeEach(() => vi.clearAllMocks());

async function openPurge(
  user: ReturnType<typeof userEvent.setup>,
  row: HTMLElement,
) {
  await user.click(within(row).getByRole("button", { name: "更多操作" }));
  await user.click(screen.getByRole("menuitem", { name: "彻底清除" }));
  return screen.getByRole("dialog", { name: "彻底清除归档" });
}

test("archive filters records, restores by archive ID, and confirms permanent removal", async () => {
  const original: ArchiveItem[] = [
    {
      id: "archive-paper",
      kind: "paper",
      target_id: "paper-1",
      title: "示例论文",
      archived_at: "2026-11-22T00:00:00Z",
      project_id: "p",
      status: "archived",
    },
    {
      id: "archive-job",
      kind: "job",
      target_id: "job-1",
      title: "论文卡片集生成",
      archived_at: "2026-11-22T00:00:00Z",
      project_id: "p",
      status: "archived",
    },
  ];
  let items = original;
  vi.mocked(archiveApi.list).mockImplementation(async (kind) => {
    const matches = items.filter((item) => !kind || item.kind === kind);
    return { items: matches, total: matches.length };
  });
  vi.mocked(archiveApi.restore).mockImplementation(async (id) => {
    items = items.filter((item) => item.id !== id);
    return { ok: true };
  });
  vi.mocked(archiveApi.purge).mockImplementation(async (id) => {
    items = items.filter((item) => item.id !== id);
    return { ok: true };
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ArchiveWorkspace connected projectNames={{ p: "合成归属项目" }} />
    </QueryClientProvider>,
  );
  const user = userEvent.setup();
  expect(await screen.findByText("示例论文")).toBeVisible();
  await user.selectOptions(screen.getByLabelText("内容类型"), "job");
  const job = (await screen.findByText("论文卡片集生成")).closest("li")!;
  expect(screen.queryByText("示例论文")).toBeNull();
  const dialog = await openPurge(user, job);
  expect(within(dialog).getByText("合成归属项目")).toBeVisible();
  const cancel = within(dialog).getByRole("button", { name: "取消" });
  expect(cancel).toHaveFocus();
  await user.click(cancel);
  expect(archiveApi.purge).not.toHaveBeenCalled();
  expect(within(job).getByRole("button", { name: "更多操作" })).toHaveFocus();
  await user.click(
    within(await openPurge(user, job)).getByRole("button", {
      name: "彻底清除",
    }),
  );
  await waitFor(() =>
    expect(archiveApi.purge).toHaveBeenCalledExactlyOnceWith("archive-job"),
  );
  await screen.findByText("此范围暂无归档内容。");

  await user.selectOptions(screen.getByLabelText("内容类型"), "");
  const paper = (await screen.findByText("示例论文")).closest("li")!;
  paper.focus();
  await user.keyboard("{Shift>}{F10}{/Shift}");
  await user.click(await screen.findByRole("menuitem", { name: "恢复" }));
  await waitFor(() =>
    expect(archiveApi.restore).toHaveBeenCalledExactlyOnceWith("archive-paper"),
  );
  expect(await screen.findByText("已恢复「示例论文」。")).toBeVisible();
  expect(archiveApi.stage).not.toHaveBeenCalled();
});

test("pending file cleanup stays actionable and cannot be restored mid-purge", async () => {
  const paper: ArchiveItem = {
    id: "pending-archive",
    kind: "paper",
    target_id: "paper-2",
    title: "示例托管论文",
    archived_at: "2026-11-22T00:00:00Z",
    project_id: "p",
    status: "archived",
  };
  let items: ArchiveItem[] = [paper];
  vi.mocked(archiveApi.list).mockImplementation(async () => ({
    items,
    total: items.length,
  }));
  vi.mocked(archiveApi.purge)
    .mockImplementationOnce(async () => {
      items = [{ ...paper, status: "purging" }];
      return { ok: false, status: "purging", pending_managed_files: 1 };
    })
    .mockImplementationOnce(async () => {
      items = [];
      return { ok: true, status: "purged" };
    });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ArchiveWorkspace connected />
    </QueryClientProvider>,
  );
  const user = userEvent.setup();
  const row = (await screen.findByText(paper.title)).closest("li")!;
  await user.click(
    within(await openPurge(user, row)).getByRole("button", {
      name: "彻底清除",
    }),
  );
  expect(await screen.findByText(/1 个本机文件待清理/)).toBeVisible();
  const resume = await screen.findByRole("button", { name: "继续清除" });
  expect(screen.getByRole("button", { name: "恢复" })).toBeDisabled();
  expect(screen.queryByText(/已彻底清除/)).toBeNull();
  await user.click(resume);
  await user.click(
    within(screen.getByRole("dialog", { name: "继续清除归档" })).getByRole(
      "button",
      { name: "继续清除" },
    ),
  );
  expect(await screen.findByText("已彻底清除「示例托管论文」。")).toBeVisible();
  expect(archiveApi.purge).toHaveBeenCalledTimes(2);
  expect(archiveApi.purge).toHaveBeenLastCalledWith("pending-archive");
});
