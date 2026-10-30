import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { SourceFiles } from "./SourceFiles";
import { api, type Source } from "./api";

vi.mock("./api", () => ({
  api: { checkSource: vi.fn(), relocateSource: vi.fn() },
}));
const source: Source = {
  id: "s",
  revision_id: "r",
  mode: "managed",
  path: "C:/paper.pdf",
  generation: 3,
  last_check: null,
};
beforeEach(() => vi.clearAllMocks());
function mount(item = source, connected = true) {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { mutations: { retry: false } } })
      }
    >
      <SourceFiles
        sources={[item]}
        paperId="p"
        selectedRevisionId="r"
        connected={connected}
      />
    </QueryClientProvider>,
  );
}
test("original missing and managed available stay separate with an observation time", () => {
  mount({
    ...source,
    last_check: {
      checked_at: "2026-10-30T00:00:00Z",
      original: { state: "missing", observed_sha256: null },
      managed: { state: "available", observed_sha256: "a".repeat(64) },
    },
  });
  expect(screen.getByText(/原文件：文件丢失/)).toHaveTextContent(
    "托管副本：内容一致",
  );
  expect(screen.getByText(/检查时间/)).toBeVisible();
});
test("check uses source identity and generation, with errors visible", async () => {
  vi.mocked(api.checkSource).mockRejectedValue(new Error("来源已更新"));
  mount();
  await userEvent
    .setup()
    .click(screen.getByRole("button", { name: "检查文件" }));
  expect(api.checkSource).toHaveBeenCalledWith(source);
  expect(await screen.findByRole("alert")).toHaveTextContent("来源已更新");
});
test("relocation cancellation leaves the existing source and no success notice", async () => {
  vi.mocked(api.relocateSource).mockResolvedValue(null);
  mount();
  await userEvent
    .setup()
    .click(screen.getByRole("button", { name: "重新定位…" }));
  expect(api.relocateSource).toHaveBeenCalledWith(source);
  expect(screen.getByText(/C:\/paper.pdf/)).toBeVisible();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});
test("offline mode disables source actions and keeps the saved observation visible", () => {
  mount(source, false);
  expect(screen.getByRole("button", { name: "检查文件" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "重新定位…" })).toBeDisabled();
  expect(screen.getByText("尚未检查当前文件")).toBeVisible();
});

test("a current source is not presented as matching the selected historical revision", () => {
  mount({ ...source, revision_id: "newer-revision" });
  expect(screen.getByText(/此来源当前指向其他修订/)).toBeVisible();
});
