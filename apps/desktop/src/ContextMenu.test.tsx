import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { useContextMenu, type ContextMenuAction } from "./ContextMenu";

function MenuFixture({
  actions,
  fullscreen = false,
}: {
  actions: ContextMenuAction[];
  fullscreen?: boolean;
}) {
  const { contextMenuProps, contextMenu } = useContextMenu();
  return (
    <div data-fullscreen={fullscreen ? "true" : undefined}>
      <div {...contextMenuProps("内容操作", actions)}>
        <button type="button">测试内容</button>
        <input aria-label="可编辑说明" />
      </div>
      <button type="button">外部按钮</button>
      {contextMenu}
    </div>
  );
}

test("right click focuses the first available action and keyboard navigation skips disabled entries", async () => {
  const open = vi.fn();
  const archive = vi.fn();
  render(
    <MenuFixture
      actions={[
        { label: "打开", action: open },
        { label: "暂不可用", action: vi.fn(), disabled: true },
        { label: "归档", action: archive },
      ]}
    />,
  );
  fireEvent.contextMenu(screen.getByRole("button", { name: "测试内容" }), {
    clientX: 20,
    clientY: 20,
  });
  const menu = screen.getByRole("menu", { name: "内容操作" });
  expect(within(menu).getByRole("menuitem", { name: "打开" })).toHaveFocus();
  await userEvent.keyboard("{ArrowDown}");
  expect(within(menu).getByRole("menuitem", { name: "归档" })).toHaveFocus();
  await userEvent.keyboard("{Enter}");
  expect(archive).toHaveBeenCalledOnce();
  expect(open).not.toHaveBeenCalled();
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
});

test("keyboard access restores focus after Escape and a click elsewhere dismisses the menu", async () => {
  render(<MenuFixture actions={[{ label: "打开", action: vi.fn() }]} />);
  const trigger = screen.getByRole("button", { name: "测试内容" });
  trigger.focus();
  await userEvent.keyboard("{Shift>}{F10}{/Shift}");
  expect(screen.getByRole("menu", { name: "内容操作" })).toBeVisible();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();

  fireEvent.contextMenu(trigger);
  await userEvent.click(screen.getByRole("button", { name: "外部按钮" }));
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "外部按钮" })).toHaveFocus();
});

test("editable fields retain their native context event and fullscreen menus remain inside the fullscreen surface", () => {
  render(
    <MenuFixture actions={[{ label: "打开", action: vi.fn() }]} fullscreen />,
  );
  expect(fireEvent.contextMenu(screen.getByRole("textbox"))).toBe(true);
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();

  fireEvent.contextMenu(screen.getByRole("button", { name: "测试内容" }));
  const menu = screen.getByRole("menu");
  expect(menu.closest('[data-fullscreen="true"]')).not.toBeNull();
});
