import { StrictMode, useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test } from "vitest";
import { GraphPanel } from "./GraphPanel";

afterEach(() => {
  document.body.style.removeProperty("overflow");
});

function StatefulGraph() {
  const [selected, setSelected] = useState(0);
  return (
    <button onClick={() => setSelected((value) => value + 1)}>
      已选节点 {selected}
    </button>
  );
}

test("fullscreen preserves the mounted graph and selection through both toggles", async () => {
  const user = userEvent.setup();
  render(
    <GraphPanel toolbar={<button>重新布局</button>} legend={<p>节点图例</p>}>
      <StatefulGraph />
    </GraphPanel>,
  );
  const graph = screen.getByRole("button", { name: "已选节点 0" });
  await user.click(graph);
  await user.click(screen.getByRole("button", { name: "全屏显示图谱" }));
  expect(screen.getByRole("dialog", { name: "知识图谱" })).toHaveAttribute(
    "aria-modal",
    "true",
  );
  expect(screen.getByRole("button", { name: "已选节点 1" })).toBe(graph);
  expect(screen.getByText("节点图例")).toBeVisible();
  expect(screen.getByRole("button", { name: "重新布局" })).toBeVisible();
  await user.click(graph);
  await user.click(screen.getByRole("button", { name: "退出全屏" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByRole("region", { name: "知识图谱" })).not.toHaveAttribute(
    "aria-modal",
  );
  expect(screen.getByRole("button", { name: "已选节点 2" })).toBe(graph);
});

test("Escape exits, restores trigger focus and restores the existing body scroll policy", async () => {
  const user = userEvent.setup();
  document.body.style.setProperty("overflow", "auto", "important");
  render(
    <GraphPanel title="论文图谱">
      <button>查看证据</button>
    </GraphPanel>,
  );
  const trigger = screen.getByRole("button", { name: "全屏显示图谱" });
  await user.click(trigger);
  expect(document.body.style.overflow).toBe("hidden");
  await user.click(screen.getByRole("button", { name: "查看证据" }));
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
  expect(document.body.style.overflow).toBe("auto");
  expect(document.body.style.getPropertyPriority("overflow")).toBe("important");
});

test("fullscreen traps keyboard and programmatic focus without exposing the background", async () => {
  const user = userEvent.setup();
  render(
    <>
      <button>背景操作</button>
      <GraphPanel>
        <button disabled>暂不可用</button>
        <button>第一个节点</button>
        <button>最后一个节点</button>
        <div style={{ display: "none" }}>
          <button>隐藏的操作</button>
        </div>
        <details>
          <summary>证据详情</summary>
          <button>收起的证据操作</button>
        </details>
      </GraphPanel>
    </>,
  );
  const trigger = screen.getByRole("button", { name: "全屏显示图谱" });
  await user.click(trigger);
  expect(trigger).toHaveFocus();
  await user.tab({ shift: true });
  expect(screen.getByText("证据详情")).toHaveFocus();
  await user.tab();
  expect(trigger).toHaveFocus();
  await user.tab();
  expect(screen.getByRole("button", { name: "第一个节点" })).toHaveFocus();
  screen.getByRole("button", { name: "背景操作" }).focus();
  expect(trigger).toHaveFocus();
});

test("unmount and StrictMode cleanup remove scroll locking and keyboard handlers", async () => {
  const user = userEvent.setup();
  const { unmount } = render(
    <StrictMode>
      <GraphPanel>
        <StatefulGraph />
      </GraphPanel>
    </StrictMode>,
  );
  await user.click(screen.getByRole("button", { name: "全屏显示图谱" }));
  expect(document.body.style.overflow).toBe("hidden");
  unmount();
  expect(document.body.style.getPropertyValue("overflow")).toBe("");
  const event = new KeyboardEvent("keydown", {
    key: "Escape",
    cancelable: true,
  });
  document.dispatchEvent(event);
  expect(event.defaultPrevented).toBe(false);
});

test("an inner control can handle Escape before the panel and focus is free after exiting", async () => {
  const user = userEvent.setup();
  render(
    <>
      <button>背景操作</button>
      <GraphPanel>
        <input
          aria-label="节点搜索"
          onKeyDown={(event) => event.preventDefault()}
        />
      </GraphPanel>
    </>,
  );
  await user.click(screen.getByRole("button", { name: "全屏显示图谱" }));
  const input = screen.getByRole("textbox", { name: "节点搜索" });
  input.focus();
  fireEvent.keyDown(input, { key: "Escape" });
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "退出全屏" }));
  screen.getByRole("button", { name: "背景操作" }).focus();
  expect(screen.getByRole("button", { name: "背景操作" })).toHaveFocus();
});
