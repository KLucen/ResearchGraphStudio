import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { PaperCardSet } from "./PaperCardSet";
import { syntheticCardSet } from "./paperCardSetFixtures";

function mount(
  data = syntheticCardSet(),
  resultId = "result-1",
  initialCardId = "",
) {
  const onOpenSection = vi.fn();
  const view = render(
    <PaperCardSet
      data={data}
      paperId="paper-1"
      revisionId="revision-1"
      resultId={resultId}
      initialCardId={initialCardId}
      onOpenSection={onOpenSection}
    />,
  );
  return { ...view, onOpenSection };
}

beforeEach(() => localStorage.clear());

test("article overview, introduction and exact evidence stay distinct from analysis and translation", async () => {
  const { onOpenSection } = mount();
  expect(screen.getByRole("heading", { name: "文章总览" })).toBeVisible();
  expect(
    screen.getByText("这篇合成文章研究共享记忆方法的运行效率。"),
  ).toBeVisible();
  expect(
    screen.getByText("先了解研究问题，再核查方法和结果；共有三张匿名卡片。"),
  ).toBeVisible();
  const card = screen.getByRole("article", {
    name: "研究问题卡片：降低共享记忆任务的运行时间",
  });
  expect(within(card).getByText("作者陈述的概括")).toBeVisible();
  expect(
    within(card).getByText("We study the runtime of shared memory tasks."),
  ).toBeVisible();
  expect(within(card).getByText("译文（ZH）· 辅助翻译")).toBeVisible();
  expect(within(card).getByText("第 2 页")).toBeVisible();
  await userEvent.click(
    within(card).getByRole("button", { name: "查看对应原文" }),
  );
  expect(onOpenSection).toHaveBeenCalledExactlyOnceWith(
    "intro",
    "intro-unit-1",
  );
  await userEvent.click(
    within(screen.getByRole("navigation", { name: "卡片类别" })).getByRole(
      "button",
      { name: /主要结果/ },
    ),
  );
  expect(screen.getByText("模型分析 · 待核查")).toBeVisible();
  expect(screen.getByText("此条依据尚未提供中文译文。")).toBeVisible();
  expect(screen.getByText("页码不可用")).toBeVisible();
});

test("category, keyword and initial concept selection operate on the same card set without layout work", async () => {
  mount(syntheticCardSet(), "result-1", "card-concept");
  expect(
    screen.getByRole("article", { name: "关键概念卡片：共享记忆" }),
  ).toBeVisible();
  await userEvent.type(
    screen.getByRole("textbox", { name: "搜索文章卡片" }),
    "12%",
  );
  expect(
    screen.getByRole("article", { name: "主要结果卡片：结果需要核对对照条件" }),
  ).toBeVisible();
  expect(screen.getByText("显示 1 张卡片")).toBeVisible();
  await userEvent.click(
    within(screen.getByRole("navigation", { name: "卡片类别" })).getByRole(
      "button",
      { name: /作者自述局限/ },
    ),
  );
  expect(screen.getByText("此范围没有卡片")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "重置筛选" }));
  expect(screen.getByText("显示 3 张卡片")).toBeVisible();
});

test("read, saved, hidden and personal notes persist locally and remain isolated by result version", async () => {
  const first = mount();
  await userEvent.click(screen.getByRole("button", { name: "标为已读完" }));
  await userEvent.click(screen.getByRole("button", { name: "收藏卡片" }));
  await userEvent.click(screen.getByText("我的笔记", { selector: "summary" }));
  await userEvent.type(
    screen.getByRole("textbox", { name: "个人阅读笔记" }),
    "我的理解，仍需核查。",
  );
  await userEvent.click(screen.getByRole("button", { name: "保存个人笔记" }));
  expect(
    screen.getByText("个人笔记已在本机保存，本次模型调用为 0。"),
  ).toBeVisible();
  first.unmount();
  const restored = mount();
  expect(screen.getByRole("button", { name: "取消收藏" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByRole("button", { name: "已读完" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByRole("textbox", { name: "个人阅读笔记" })).toHaveValue(
    "我的理解，仍需核查。",
  );
  await userEvent.click(screen.getByRole("button", { name: "隐藏卡片" }));
  await userEvent.selectOptions(
    screen.getByRole("combobox", { name: "卡片查看范围" }),
    "hidden",
  );
  expect(
    screen.getByRole("article", {
      name: "研究问题卡片：降低共享记忆任务的运行时间",
    }),
  ).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "恢复显示" }));
  expect(screen.getByText("此范围没有卡片")).toBeVisible();
  restored.unmount();
  mount(syntheticCardSet(), "result-2");
  expect(screen.getByRole("button", { name: "收藏卡片" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  expect(screen.getByRole("button", { name: "标为已读完" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
});

test("model source shows its segment and never fabricates unavailable PDF navigation", async () => {
  const data = syntheticCardSet();
  data.source_kind = "model_parse";
  data.cards = [data.cards[2]];
  mount(data);
  expect(screen.getByText(/依据已保存的模型解析材料/)).toBeVisible();
  expect(screen.getByText("页码不可用 · 模型解析片段")).toBeVisible();
  expect(screen.queryByRole("button", { name: "查看对应原文" })).toBeNull();
  fireEvent.click(screen.getByText("定位信息", { selector: "summary" }));
  expect(screen.getByText("segment-result")).toBeVisible();
});

test("storage failure is reported without claiming the personal note was saved", async () => {
  mount();
  const writer = vi
    .spyOn(Storage.prototype, "setItem")
    .mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
  try {
    await userEvent.click(
      screen.getByText("我的笔记", { selector: "summary" }),
    );
    await userEvent.type(
      screen.getByRole("textbox", { name: "个人阅读笔记" }),
      "保存失败时仍然保留当前输入。",
    );
    await userEvent.click(screen.getByRole("button", { name: "保存个人笔记" }));
    expect(screen.getByRole("alert")).toHaveTextContent("本机偏好暂时无法保存");
    expect(screen.getByRole("button", { name: "保存个人笔记" })).toBeEnabled();
    expect(
      screen.getByText("我的笔记", { selector: "summary" }),
    ).not.toHaveTextContent("已保存");
    expect(
      screen.queryByText("个人笔记已在本机保存，本次模型调用为 0。"),
    ).not.toBeInTheDocument();
  } finally {
    writer.mockRestore();
  }
});
