import { expect, test } from "@playwright/test";

test("project and paper menus expose matching existing actions by mouse and keyboard", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/e2e/sidebar.html");
  const tree = page.getByRole("region", { name: "个人研究项目" });
  const project = tree.getByRole("button", {
    name: "合成研究项目 1",
    exact: true,
  });
  await project.click({ button: "right" });
  const projectMenu = page.getByRole("menu", { name: "研究项目操作" });
  await expect(
    projectMenu.getByRole("menuitem", { name: "打开项目" }),
  ).toBeFocused();
  await projectMenu.getByRole("menuitem", { name: "收起论文列表" }).click();
  const paper = tree.getByRole("button", { name: /^合成论文 01：/ });
  await expect(paper).toHaveCount(0);

  await project.press("Shift+F10");
  await projectMenu.getByRole("menuitem", { name: "展开论文列表" }).click();
  await paper.click({ button: "right" });
  const paperMenu = page.getByRole("menu", { name: "项目论文操作" });
  await paperMenu.getByRole("menuitem", { name: "打开论文阅读" }).click();
  await expect(paper).toHaveAttribute("aria-current", "page");
  await expect
    .poll(() => page.evaluate(() => window.__sidebarViewedPapers))
    .toContain("sidebar-project-1-paper-1");
  expect(await page.evaluate(() => window.__sidebarUnexpectedRequests)).toEqual(
    [],
  );
});

test("a report can be pinned or opened from its context menu without starting model work", async ({
  page,
}) => {
  await page.goto("/e2e/knowledge.html");
  await page
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  const report = page.getByRole("button", {
    name: /合成论文 B 与已有研究的联系/,
  });
  await report.click({ button: "right" });
  const menu = page.getByRole("menu", { name: "联系汇报操作" });
  await menu.getByRole("menuitem", { name: "置顶汇报", exact: true }).click();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          JSON.parse(localStorage.getItem("kb-fixture:report") ?? "{}").pinned,
      ),
    )
    .toBe(true);

  await report.press("Shift+F10");
  await expect(menu.getByRole("menuitem", { name: "取消置顶" })).toBeVisible();
  await menu.getByRole("menuitem", { name: "打开联系汇报" }).click();
  await expect(
    page.getByRole("dialog", { name: "联系汇报", exact: true }),
  ).toBeVisible();
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);
});
