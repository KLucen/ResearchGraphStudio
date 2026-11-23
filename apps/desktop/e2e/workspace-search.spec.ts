import { expect, test } from "@playwright/test";

test("Ctrl+F finds personal projects and papers across pages and opens the result", async ({
  page,
}) => {
  await page.setViewportSize({ width: 620, height: 900 });
  await page.goto("/e2e/sidebar.html");
  const open = page.getByRole("button", {
    name: "搜索项目与论文",
    exact: true,
  });
  await expect(open).toBeVisible();
  await open.focus();
  await page.keyboard.press("Control+f");
  const dialog = page.getByRole("dialog", { name: "搜索个人研究空间" });
  const field = dialog.getByRole("searchbox", { name: "搜索项目与论文" });
  await expect(field).toBeFocused();
  await field.fill("没有匹配的搜索");
  await expect(dialog.getByText("没有找到匹配的项目或论文。")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(open).toBeFocused();

  await open.click();
  await field.fill("合成论文");
  await expect(dialog.getByRole("status")).toHaveText("120 条结果");
  await expect(dialog.getByText("论文 · 合成研究项目 2")).toHaveCount(0);
  await dialog.getByRole("button", { name: "加载更多结果" }).click();
  await dialog
    .getByRole("button", { name: /合成论文 01.*合成研究项目 2/ })
    .click();
  await expect(dialog).toHaveCount(0);
  await expect
    .poll(() => page.evaluate(() => window.__sidebarViewedPapers))
    .toContain("sidebar-project-2-paper-1");
});

test("Ctrl+F focuses knowledge search both normally and in fullscreen", async ({
  page,
}) => {
  await page.goto("/e2e/knowledge.html");
  await page
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  await page.getByRole("button", { name: "知识地图", exact: true }).click();
  await page.keyboard.press("Control+f");
  await expect(
    page.getByRole("searchbox", { name: "搜索知识库" }),
  ).toBeFocused();
  await page.getByRole("button", { name: "全屏", exact: true }).click();
  const fullscreen = page.getByRole("dialog", { name: "知识地图全屏" });
  await expect(fullscreen).toBeVisible();
  await page.keyboard.press("Control+f");
  await expect(
    fullscreen.getByRole("searchbox", { name: "搜索知识库" }),
  ).toBeFocused();
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);
});
