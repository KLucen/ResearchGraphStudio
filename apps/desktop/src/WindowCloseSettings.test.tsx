import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { beforeEach, expect, test, vi } from "vitest";
import { WindowCloseSettings } from "./WindowCloseSettings";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), isTauri: vi.fn() }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <WindowCloseSettings />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(listen).mockResolvedValue(() => {});
});

test("the first native close choice updates Settings and can be switched to exit", async () => {
  let behavior: "hide_to_tray" | "exit" | null = null;
  vi.mocked(invoke).mockImplementation(async (command, args) => {
    if (command === "set_desktop_close_behavior" && args) {
      behavior = (args as { behavior: typeof behavior }).behavior;
    }
    return behavior;
  });
  const view = mount();
  const control = screen.getByRole("combobox", { name: "关闭窗口时" });
  await waitFor(() => expect(control).toBeEnabled());
  expect(control).toHaveDisplayValue("首次关闭时询问");

  const nativeListener = vi.mocked(listen).mock.calls[0]?.[1];
  behavior = "hide_to_tray";
  act(() =>
    nativeListener?.({
      event: "desktop-close-behavior-changed",
      id: 1,
      payload: behavior,
    }),
  );
  await waitFor(() => expect(control).toHaveDisplayValue("隐藏到任务栏托盘"));

  await userEvent.selectOptions(control, "exit");
  await waitFor(() => expect(control).toHaveDisplayValue("退出主程序"));
  expect(invoke).toHaveBeenCalledWith("set_desktop_close_behavior", {
    behavior: "exit",
  });
  view.unmount();
  mount();
  await waitFor(() => {
    expect(
      screen.getByRole("combobox", { name: "关闭窗口时" }),
    ).toHaveDisplayValue("退出主程序");
  });
});

test("keeps the saved behavior visible when changing it fails", async () => {
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === "set_desktop_close_behavior") throw new Error("fixture");
    return "exit";
  });
  mount();
  const control = screen.getByRole("combobox", { name: "关闭窗口时" });
  await waitFor(() => expect(control).toBeEnabled());
  await userEvent.selectOptions(control, "hide_to_tray");
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "无法保存窗口关闭设置",
  );
  expect(control).toHaveDisplayValue("退出主程序");
});
