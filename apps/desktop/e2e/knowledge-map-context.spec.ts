import { expect, test } from "@playwright/test";
import type { KnowledgeLayout } from "../src/knowledgeApi";

test("map filters retain hidden pinned positions and graph contexts open the corresponding actions", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.goto("/e2e/knowledge.html");
  await page
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  await page.getByRole("button", { name: "知识地图", exact: true }).click();
  const map = page.locator(".knowledge-map");
  const methodId = "version:version-A:A-2";
  const conceptId = "version:version-A:A-1";
  const method = map.locator(`[data-id="${methodId}"]`);
  const concept = map.locator(`[data-id="${conceptId}"]`);
  const viewport = map.locator(".react-flow__viewport");
  const methods = map.getByRole("checkbox", { name: "显示方法" });
  await expect(map.locator(".react-flow__node")).toHaveCount(12);
  await expect(method).toHaveClass(/pinned/);
  const originalPosition = await method.evaluate((el) => el.style.transform);
  const originalCamera = await viewport.evaluate((el) => el.style.transform);

  await methods.uncheck();
  await expect(method).toHaveCount(0);
  await expect(map.locator(".react-flow__node")).toHaveCount(10);
  await concept.click({ button: "right" });
  const nodeMenu = page.getByRole("menu", { name: "知识地图节点操作" });
  await nodeMenu.getByRole("menuitem", { name: "取消固定节点" }).click();
  await expect(concept).not.toHaveClass(/pinned/);
  await expect
    .poll(() =>
      page.evaluate((id) => {
        const raw = localStorage.getItem("kb-fixture:layout:library:all:all");
        const saved = raw ? (JSON.parse(raw) as KnowledgeLayout) : null;
        return saved?.layout.positions.find((item) => item.node_id === id)
          ?.pinned;
      }, methodId),
    )
    .toBe(true);

  await methods.check();
  await expect(method).toHaveClass(/pinned/);
  await expect
    .poll(() => method.evaluate((el) => el.style.transform))
    .toBe(originalPosition);
  await expect
    .poll(() => viewport.evaluate((el) => el.style.transform))
    .toBe(originalCamera);

  await method.press("Shift+F10");
  await nodeMenu.getByRole("menuitem", { name: "查看节点详情" }).click();
  await expect(map.getByRole("heading", { name: "A 合成方法" })).toBeVisible();

  const edge = map.locator('.react-flow__edge[data-id="cross:relation-1"]');
  await edge.click({ button: "right", force: true });
  const edgeMenu = page.getByRole("menu", { name: "知识地图关系操作" });
  await edgeMenu.getByRole("menuitem", { name: "打开联系汇报" }).click();
  const report = page.getByRole("dialog", { name: "联系汇报" });
  await expect(report.getByText("新增论文依据")).toBeVisible();
  await report.getByRole("button", { name: "关闭", exact: true }).click();

  await map
    .locator(".react-flow__pane")
    .click({ button: "right", position: { x: 16, y: 16 } });
  const paneMenu = page.getByRole("menu", { name: "知识地图画布操作" });
  await expect(
    paneMenu.getByRole("menuitem", { name: "聚焦图谱" }),
  ).toBeVisible();
  await expect(paneMenu.getByRole("menuitem", { name: "全屏" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(paneMenu).toHaveCount(0);
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);
});
