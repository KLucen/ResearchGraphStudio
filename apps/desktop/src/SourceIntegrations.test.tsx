import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { SourceIntegrations } from "./SourceIntegrations";
import { api, type NoteRoot } from "./api";

vi.mock("./api", () => ({
  api: {
    noteRoots: vi.fn(),
    notePermissions: vi.fn(),
    authorizeNotes: vi.fn(),
    noteAction: vi.fn(),
    notes: vi.fn(),
  },
}));
const root: NoteRoot = {
  id: "root",
  path: "synthetic-notes",
  active: true,
  query_permissions: { allow_local: true, allow_model: false },
};
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.noteRoots).mockResolvedValue([root]);
  vi.mocked(api.notePermissions).mockResolvedValue({
    root_id: "root",
    allow_local: true,
    allow_model: true,
  });
});
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SourceIntegrations projectId="p" connected />
    </QueryClientProvider>,
  );
}
test("shows actual directory grants; changing a checkbox never grants model usage until explicit save", async () => {
  const user = userEvent.setup();
  mount();
  expect(await screen.findByLabelText("允许本地问答检索")).toBeChecked();
  const model = screen.getByLabelText("允许将必要笔记片段发送给问答模型");
  expect(model).not.toBeChecked();
  await user.click(model);
  expect(api.notePermissions).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "保存用途授权" }));
  await waitFor(() =>
    expect(api.notePermissions).toHaveBeenCalledWith("root", {
      allow_local: true,
      allow_model: true,
    }),
  );
  expect(api.notes).not.toHaveBeenCalled();
  expect(api.noteAction).not.toHaveBeenCalled();
});
test("unknown permissions cannot be overwritten by assumed defaults", async () => {
  vi.mocked(api.noteRoots).mockResolvedValue([
    { ...root, query_permissions: undefined },
  ]);
  mount();
  expect(await screen.findByText(/正在等待引擎提供当前用途授权/)).toBeVisible();
  expect(screen.getByRole("button", { name: "保存用途授权" })).toBeDisabled();
  expect(screen.getByLabelText("允许本地问答检索")).toBeDisabled();
  expect(api.notePermissions).not.toHaveBeenCalled();
});
test("revoked directory offers no query grant controls or note snapshot content", async () => {
  vi.mocked(api.noteRoots).mockResolvedValue([{ ...root, active: false }]);
  mount();
  await screen.findByText(/已撤销/);
  expect(
    screen.queryByRole("group", { name: "问答用途" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "查看快照" }),
  ).not.toBeInTheDocument();
  expect(api.notes).not.toHaveBeenCalled();
});
test("permission save errors stay visible without changing source notes", async () => {
  const user = userEvent.setup();
  vi.mocked(api.notePermissions).mockRejectedValue(
    new Error("用途授权保存失败"),
  );
  mount();
  await user.click(await screen.findByRole("button", { name: "保存用途授权" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "用途授权保存失败",
  );
  expect(api.noteAction).not.toHaveBeenCalled();
});
