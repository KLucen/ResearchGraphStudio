import { test, expect } from "@playwright/test";

test("actual reading component keeps desktop rows aligned and stacks each paragraph on narrow screens", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.goto("/e2e/reading.html");
  await expect(page.getByText("缓存命中 · 新增调用 0")).toBeVisible();
  const rows = page.locator(".bilingual-row");
  await expect(rows).toHaveCount(2);
  for (let i = 0; i < 2; i++) {
    const row = rows.nth(i),
      source = await row.locator(".bilingual-source").boundingBox(),
      annotation = await row.locator(".paragraph-annotation").boundingBox();
    expect(source && annotation).toBeTruthy();
    expect(Math.abs(source!.y - annotation!.y)).toBeLessThan(2);
    expect(annotation!.x).toBeGreaterThan(source!.x + source!.width - 1);
    expect(source!.width / annotation!.width).toBeGreaterThan(1.45);
    await expect(row.locator(".paragraph-translation")).toBeVisible();
  }
  await expect(page.locator(".paragraph-english").first()).toHaveText(
    "We test a bounded method. A bounded method may fail under noise.",
  );
  await expect(page.locator("mark[data-highlight-type=METHOD]")).toHaveText(
    "bounded method",
  );
  await expect(
    page.locator(".close-reading script,.close-reading img"),
  ).toHaveCount(0);
  await expect(
    page.getByText(/<script>此处仅显示文本<\/script>/),
  ).toBeVisible();
  expect(await page.evaluate(() => window.__readingCalls)).toEqual([]);
  await page.screenshot({
    path: testInfo.outputPath("reading-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 620, height: 900 });
  for (let i = 0; i < 2; i++) {
    const row = rows.nth(i),
      english = await row.locator(".paragraph-english").boundingBox(),
      translation = await row.locator(".paragraph-translation").boundingBox(),
      annotation = await row.locator(".paragraph-annotation").boundingBox();
    expect(translation!.y).toBeGreaterThan(english!.y + english!.height);
    expect(annotation!.y).toBeGreaterThan(translation!.y + translation!.height);
    expect(annotation!.width).toBeGreaterThan(500);
  }
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: testInfo.outputPath("reading-narrow.png"),
    fullPage: true,
  });
});

test("partial reading renders every translation slot and sends only an explicitly authorized missing range", async ({
  page,
}) => {
  await page.goto("/e2e/reading.html?scenario=partial");
  await expect(page.getByLabel("第 1 段中文译文")).toContainText(
    "我们测试一种有界方法",
  );
  await expect(page.getByLabel("第 2 段中文译文")).toContainText(
    "本段译文尚未生成",
  );
  expect(await page.evaluate(() => window.__readingCalls)).toEqual([]);
  const retry = page.getByRole("button", { name: "仅重试缺失的 1 段" });
  await expect(retry).toBeDisabled();
  await page
    .getByRole("checkbox", { name: "允许本次发送所选段落，生成译文和批注" })
    .check();
  await retry.click();
  await expect(page.getByLabel("第 2 段中文译文")).toContainText(
    "观察到的结果有条件限制",
  );
  await expect(page.getByLabel("第 1 段中文译文")).toContainText(
    "我们测试一种有界方法",
  );
  expect(await page.evaluate(() => window.__readingCalls)).toEqual([
    {
      kind: "A02",
      body: {
        document_version_id: "v",
        paragraph_ids: ["p2"],
        allow_network: true,
        retry_missing_of: "cr1",
      },
    },
  ]);
  await page
    .getByRole("combobox", { name: "阅读进度" })
    .selectOption("READING");
  expect((await page.evaluate(() => window.__readingCalls)).length).toBe(1);
});

test("range selection, graph and paragraph navigation stay local; stale drafts remain separate", async ({
  page,
}) => {
  await page.goto("/e2e/reading.html");
  await page.getByRole("button", { name: "有界方法", exact: true }).click();
  await page.getByRole("button", { name: "对这一段提问" }).first().click();
  expect(await page.evaluate(() => window.__readingNavigation)).toEqual([
    { nodeId: "n1" },
    { paragraphId: "p1" },
  ]);
  await page.getByLabel("起始段落").selectOption("1");
  await expect(page.locator(".bilingual-row")).toHaveCount(1);
  await expect(
    page.getByRole("region", { name: "所选范围论证结构" }),
  ).toBeVisible();
  expect(await page.evaluate(() => window.__readingCalls)).toEqual([]);
  await page.goto("/e2e/reading.html?scenario=stale");
  await expect(page.getByLabel("第 1 段中文译文")).toContainText(
    "原文或生成配置已变化",
  );
  await expect(page.locator(".paragraph-english mark")).toHaveCount(0);
  await page.getByText("查看旧版本译文与批注（不与当前原文对齐）").click();
  await expect(
    page.getByText("我们测试一种有界方法。有界方法可能在噪声下失效。", {
      exact: true,
    }),
  ).toBeVisible();
  expect(await page.evaluate(() => window.__readingCalls)).toEqual([]);
});
