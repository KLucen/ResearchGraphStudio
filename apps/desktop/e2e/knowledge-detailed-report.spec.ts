import { expect, test } from "@playwright/test";
import { detailedKnowledgeReport } from "../src/knowledgeFixtures";

test("the detailed report lays out both papers and their evidence, with a concise edge", async ({
  page,
}, testInfo) => {
  const report = detailedKnowledgeReport();
  const relation = report.relations![0];
  await page.addInitScript((value) => {
    localStorage.setItem("kb-fixture:report", JSON.stringify(value));
  }, report);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/e2e/knowledge.html");
  await page
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  await page.getByRole("button", { name: report.title }).click();
  const dialog = page.getByRole("dialog", { name: "联系汇报" });
  const detail = dialog.getByLabel("详细关系总结");
  await expect(detail).toContainText(relation.detail!.source_zh);
  await expect(detail).toContainText(relation.detail!.target_zh);
  await expect(dialog.getByText(relation.detail!.conditions_zh)).toBeVisible();
  const sides = detail.locator(":scope > div");
  expect(
    await sides.evaluateAll(
      (elements) =>
        elements[0].getBoundingClientRect().top ===
        elements[1].getBoundingClientRect().top,
    ),
  ).toBe(true);
  const evidenceLink = dialog.getByRole("link", { name: "查看依据 1" });
  await evidenceLink.focus();
  await expect(dialog.locator(".knowledge-relation")).toHaveAttribute(
    "data-preview",
    "true",
  );
  await evidenceLink.click();
  await expect(dialog.locator(".knowledge-relation")).toBeFocused();
  await dialog.getByText(/本地解析材料 · 第 2 页/).click();
  await expect(dialog.getByText("B synthetic source text.")).toBeVisible();
  await dialog.getByText(/模型提取材料 · 章节 模型方法章节/).click();
  await expect(dialog.getByText("A synthetic source text.")).toBeVisible();
  await detail.screenshot({ path: testInfo.outputPath("detailed-report.png") });

  await page.setViewportSize({ width: 520, height: 900 });
  await expect
    .poll(() =>
      sides.evaluateAll(
        (elements) =>
          elements[0].getBoundingClientRect().bottom <=
          elements[1].getBoundingClientRect().top,
      ),
    )
    .toBe(true);
  expect(
    await detail.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    ),
  ).toBe(true);
  await dialog
    .getByRole("button", { name: /在知识地图中定位这条联系/ })
    .click();
  const graphDetails = page.getByRole("complementary", {
    name: "知识地图详情",
  });
  await expect(graphDetails.getByText(relation.explanation_zh!)).toBeVisible();
  await expect(
    graphDetails.getByText(relation.detail!.comparison_zh),
  ).toHaveCount(0);
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);
});
