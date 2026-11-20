import { expect, test, type Locator } from "@playwright/test";

async function paragraphLayout(row: Locator) {
  // ResizeObserver/rAF changes the paragraph layout after viewport updates,
  // and the reading outline may restore its scroll anchor in the meantime.
  // Read every box in one browser task so a scroll cannot split the sample.
  return row.evaluate((element) => {
    const source = element.querySelector(".paper-paragraph-source");
    const translation = element.querySelector(".paper-paragraph-translation");
    const note = element.querySelector(".paper-paragraph-note");
    if (!source || !translation || !note) return null;
    const sourceBox = source.getBoundingClientRect();
    const translationBox = translation.getBoundingClientRect();
    const noteBox = note.getBoundingClientRect();
    return {
      mode: (element as HTMLElement).dataset.noteLayout,
      topDifference: Math.abs(sourceBox.top - noteBox.top),
      rightGap: noteBox.left - sourceBox.right,
      belowTranslationGap: noteBox.top - translationBox.bottom,
      noteWidth: noteBox.width,
    };
  });
}

test("local chapter progress is available after its complete text and folded materials", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/e2e/paper-reading.html");
  const chapter = page.locator(".paper-reading-chapter").first();
  await expect(chapter.locator(".paper-reading-paragraph")).toHaveCount(2);
  await expect(chapter.locator("header .chapter-reading-progress")).toHaveCount(
    0,
  );
  const footer = chapter.locator("footer[data-chapter-progress-footer]");
  await expect(footer).toHaveCount(1);
  await expect(footer).toContainText("2. Synthetic Methods");
  expect(
    await chapter.evaluate((element) => {
      const footer = element.querySelector("[data-chapter-progress-footer]")!;
      return [
        ...element.querySelectorAll(
          ".paper-reading-paragraph, .paper-reading-materials",
        ),
      ].every((content) =>
        Boolean(
          content.compareDocumentPosition(footer) &
          Node.DOCUMENT_POSITION_FOLLOWING,
        ),
      );
    }),
  ).toBeTruthy();
  await footer.getByRole("button", { name: "已读完", exact: true }).click();
  await expect(
    footer.getByRole("button", { name: "已读完", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  expect(
    await page.evaluate(() => window.__paperReadingProgressWrites),
  ).toEqual([
    {
      paperId: "paper",
      sectionId: "s",
      document_version_id: "v",
      progress: "COMPLETED",
    },
  ]);
  expect(await page.evaluate(() => window.__paperReadingCalls)).toEqual([]);
});

test("full-paper reading renders headings and body paragraphs while preserving folded material source information", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto("/e2e/paper-reading.html");
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
  await expect(page.getByText("缓存命中 · 新增调用 0")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "2. Synthetic Methods" }),
  ).toBeVisible();
  await expect(page.locator(".paper-reading-paragraph")).toHaveCount(2);
  await expect(
    page.locator(
      ".paper-reading-chapter .paper-reading-materials .paper-material",
    ),
  ).toHaveCount(3);
  await expect(page.locator(".paper-material-raw").first()).not.toBeVisible();
  await expect(page.locator(".paper-paragraph-english").first()).toHaveText(
    "We test a bounded method. A bounded method may fail under noise.",
  );
  await expect(
    page.locator(".paper-paragraph-english mark[data-highlight-type=METHOD]"),
  ).toHaveText("bounded method");
  await expect(page.getByLabel("正文第 1 段中文译文")).toContainText(
    "我们测试一种有界方法",
  );
  await expect(page.getByLabel("正文第 2 段中文译文")).toContainText(
    "<script>只显示文字</script>",
  );
  await expect(
    page.locator(".paper-close-reading img,.paper-close-reading script"),
  ).toHaveCount(0);
  for (const row of await page.locator(".paper-reading-paragraph").all()) {
    await expect(async () => {
      const geometry = await paragraphLayout(row);
      expect(geometry).not.toBeNull();
      expect(geometry!.mode).toBe("anchored");
      expect(geometry!.topDifference).toBeLessThan(2);
      expect(geometry!.rightGap).toBeGreaterThan(0);
    }).toPass({ timeout: 5000 });
  }
  expect(await page.evaluate(() => window.__paperReadingCalls)).toEqual([]);
  await page.screenshot({
    path: testInfo.outputPath("paper-reading-desktop.png"),
    fullPage: true,
  });
  await page.getByText("图表与其他材料（3）", { exact: true }).click();
  const material = page.locator(".paper-material").first();
  await material.locator("summary").first().click();
  await expect(material.locator(".paper-material-raw")).toHaveText(
    "58.0\nT3: Flights",
  );
  await expect(material).toContainText("PDF 第 2 页");
  await expect(material).toContainText(
    "处理建议：请在 Zotero 原始 PDF 第 2 页查看图像",
  );
  await material.getByText("原始块与定位", { exact: true }).click();
  await expect(material).toContainText("chunk-m1 · SHA-256 synthetic-m1");
  await expect(material.locator(".paper-paragraph-translation")).toHaveCount(0);
  const figure = page.locator(".paper-material").nth(2);
  await figure.locator("summary").first().click();
  await figure.getByText("原始块与定位", { exact: true }).click();
  await expect(figure).toContainText("坐标 40, 200, 400, 500");
  await page.screenshot({
    path: testInfo.outputPath("paper-reading-materials.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 900 });
  for (const row of await page.locator(".paper-reading-paragraph").all()) {
    await expect(async () => {
      const geometry = await paragraphLayout(row);
      expect(geometry).not.toBeNull();
      expect(geometry!.mode).toBe("stacked");
      expect(geometry!.belowTranslationGap).toBeGreaterThan(0);
      expect(geometry!.noteWidth).toBeGreaterThan(300);
    }).toPass({ timeout: 5000 });
  }
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: testInfo.outputPath("paper-reading-narrow.png"),
    fullPage: true,
  });
});

test("one explicit consent generates full-paper notes and local refresh never starts generation", async ({
  page,
}) => {
  await page.goto("/e2e/paper-reading.html?scenario=empty");
  await expect(
    page.getByRole("heading", { name: "2. Synthetic Methods" }),
  ).toBeVisible();
  const generate = page.getByRole("button", {
    name: "生成全文精读笔记",
    exact: true,
  });
  await expect(generate).toBeDisabled();
  await expect(page.getByLabel("起始段落")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /仅重试缺失/ })).toHaveCount(0);
  expect(await page.evaluate(() => window.__paperReadingCalls)).toEqual([]);
  await page
    .getByRole("checkbox", { name: "允许本次发送整篇正文，生成全文精读笔记" })
    .check();
  await generate.click();
  await expect(page.getByLabel("正文第 2 段中文译文")).toContainText(
    "观察到的结果有条件限制",
  );
  expect(await page.evaluate(() => window.__paperReadingCalls)).toEqual([
    { document_version_id: "v", allow_network: true, force_regenerate: false },
  ]);
  await page.getByRole("button", { name: "对这段提问" }).first().click();
  await page.getByRole("button", { name: "查看关联概念 1" }).click();
  expect(await page.evaluate(() => window.__paperReadingNavigation)).toEqual([
    { sectionId: "s", paragraphId: "p1" },
    { nodeId: "n1" },
  ]);
  await page.getByRole("button", { name: "重新整理本地阅读版面" }).click();
  await expect(page.getByLabel("正文第 1 段中文译文")).toContainText(
    "旧笔记未与当前原文对齐",
  );
  expect(await page.evaluate(() => window.__paperReadingLocalRefresh)).toBe(1);
  expect((await page.evaluate(() => window.__paperReadingCalls)).length).toBe(
    1,
  );
  await page.getByText("查看旧版本全文笔记", { exact: true }).click();
  await expect(
    page.getByText("我们测试一种有界方法。有界方法可能在噪声下失效。", {
      exact: true,
    }),
  ).toBeVisible();
});
