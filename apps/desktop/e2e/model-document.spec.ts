import { expect, test } from "@playwright/test";

test("model column labels follow the actual annotation layout rather than the window breakpoint", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/e2e/model-document.html");
  const row = page.locator(".paper-reading-paragraph").first();
  const labels = page.locator(".paper-reading-column-labels");
  await expect(row).toHaveAttribute("data-note-layout", "anchored");
  await expect(labels).toBeVisible();
  // Desktop reading keeps the actual analysis beside the source even when
  // navigation shares its width; only the genuinely narrow layout stacks.
  await page.setViewportSize({ width: 1000, height: 1000 });
  await expect(row).toHaveAttribute("data-note-layout", "anchored");
  await expect(labels).toBeVisible();
  await page.setViewportSize({ width: 620, height: 900 });
  await expect(row).toHaveAttribute("data-note-layout", "stacked");
  await expect(labels).not.toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await expect(row).toHaveAttribute("data-note-layout", "anchored");
  await expect(labels).toBeVisible();
  expect(
    await page.evaluate(() => window.__modelDocumentGenerationRequests),
  ).toEqual([]);
});

test("model annotations keep the actual analysis on the right without repeating marked quotes", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/e2e/model-document.html");
  const row = page.locator(".paper-reading-paragraph").first();
  await expect(row.locator(".paper-highlight-reference")).toHaveCount(4);
  await expect(
    row.locator(".paper-highlight-note, .paper-paragraph-note blockquote"),
  ).toHaveCount(0);
  await expect(row.locator(".paper-paragraph-comment")).toContainText(
    "说明作者主张的支撑关系",
  );
  await expect(row.locator(".paper-paragraph-comment")).toContainText("整段");
  const quotes = ["core claim", "concept", "Evidence", "limitation"];
  for (let index = 0; index < quotes.length; index++) {
    const mark = row.locator(`mark[data-annotation-key="${index}"]`);
    const reference = row.locator(
      `.paper-highlight-reference[data-annotation-key="${index}"]`,
    );
    await expect(mark).toContainText(quotes[index]);
    await expect(row.locator(".paper-paragraph-note")).not.toContainText(
      quotes[index],
    );
    await mark.click();
    await expect(reference).toHaveAttribute("data-active", "true");
    await expect(reference).toBeFocused();
    await reference.click();
    await expect(mark).toBeFocused();
  }
  expect(
    await page.evaluate(() => window.__modelDocumentGenerationRequests),
  ).toEqual([]);
});

test("major chapter progress appears after all its subsection text and model materials", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/e2e/model-document.html");
  const chapters = page.locator(".model-reading-chapter");
  await expect(chapters).toHaveCount(3);
  for (const chapter of await chapters.all()) {
    await expect(
      chapter.locator("header .chapter-reading-progress"),
    ).toHaveCount(0);
    const footer = chapter.locator("footer[data-chapter-progress-footer]");
    await expect(footer).toHaveCount(1);
    const position = await chapter.evaluate((element) => {
      const footer = element.querySelector("[data-chapter-progress-footer]")!;
      return [
        ...element.querySelectorAll(
          ".paper-reading-paragraph, .paper-formula-rendered, .paper-reading-table",
        ),
      ].every((content) =>
        Boolean(
          content.compareDocumentPosition(footer) &
          Node.DOCUMENT_POSITION_FOLLOWING,
        ),
      );
    });
    expect(position).toBeTruthy();
  }
  const introduction = chapters.first();
  await expect(introduction).toContainText("Synthetic source scope.");
  await expect(
    introduction.locator("[data-chapter-progress-footer]"),
  ).toContainText("1 Introduction");
  expect(
    await page.evaluate(() => window.__modelDocumentGenerationRequests),
  ).toEqual([]);
});

test("model full reading marks major chapters and resumes the next chapter after reopening", async ({
  page,
}, testInfo) => {
  const pageErrors: string[] = [];
  const apiRequests: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.route("**/api/**", async (route) => {
    apiRequests.push(route.request().url());
    await route.abort();
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/e2e/model-document.html");
  const directory = page.getByRole("navigation", { name: "文章目录" });
  const introduction = page.getByRole("group", {
    name: "1 Introduction 阅读状态",
  });
  await expect(
    introduction.getByRole("button", { name: "已读完", exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByRole("group", { name: "1.1 Scope 阅读状态" }),
  ).toHaveCount(0);
  await expect(
    page.getByText(
      "Synthetic source introduction. The core claim introduces a concept. Evidence supports the result under a limitation.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(page.locator(".paper-formula-rendered .katex")).toBeVisible();
  await expect(page.locator(".paper-formula-rendered annotation")).toHaveText(
    String.raw`L(\theta) = \sum_{i=1}^{n}(y_i - f_{\theta}(x_i))^2`,
  );
  await expect(page.getByRole("table", { name: "模型提取表格" })).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "Baseline", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("模型提取公式，待核对", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .locator(".model-reading-chapter")
      .getByText("合成译文：核心主张引入概念，论据在限定条件下支撑结果。", {
        exact: true,
      }),
  ).toBeVisible();
  await expect(page.locator(".paper-paragraph-translation")).toHaveCount(8);
  await expect(page.locator("mark[data-highlight-type]")).toHaveCount(4);
  for (const type of ["THESIS", "CONCEPT", "EVIDENCE", "COUNTERARGUMENT"]) {
    await expect(
      page.locator(`mark[data-highlight-type="${type}"]`),
    ).toBeVisible();
  }
  await expect(page.getByLabel("正文第 1 段论证批注")).toContainText(
    "说明作者主张的支撑关系",
  );
  await expect(page.getByLabel("全文论证结构")).toContainText("合成核心主张");
  await introduction
    .getByRole("button", { name: "已读完", exact: true })
    .click();
  await expect(
    introduction.getByRole("button", { name: "已读完", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByText("已读完 1 / 3 个大章节", { exact: true }),
  ).toBeVisible();
  await expect(
    directory.getByRole("button", { name: "1 Introduction", exact: true }),
  ).toContainText("✓ 已读完");
  expect(
    await page.evaluate(() => window.__modelDocumentProgressWrites),
  ).toEqual([
    {
      parse_id: "browser-model-parse",
      chapter_ref: "introduction",
      progress: "COMPLETED",
      updated_at: "2026-11-18T06:00:00Z",
    },
  ]);
  await page.screenshot({
    path: testInfo.outputPath("model-document-desktop.png"),
    fullPage: false,
  });
  // Read the actual public toggle before continuing navigation.
  const expandDirectory = page.getByRole("button", { name: "展开文章目录" });
  if (await expandDirectory.isVisible()) await expandDirectory.click();
  await page
    .getByRole("button", { name: "继续阅读：2 Methods", exact: true })
    .click();
  const methods = page.locator("#model-reading-browser-model-parse-methods");
  await expect(methods).toBeFocused();
  await expect(
    directory.getByRole("button", { name: "2 Methods", exact: true }),
  ).toHaveAttribute("aria-current", "location");
  expect((await methods.boundingBox())!.y).toBeLessThan(200);
  await page.reload();
  await expect(
    introduction.getByRole("button", { name: "已读完", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    directory.getByRole("button", { name: "1 Introduction", exact: true }),
  ).toContainText("✓ 已读完");
  await expect(
    page.getByRole("button", { name: "继续阅读：2 Methods", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => window.__modelDocumentProgressReads),
  ).toBeGreaterThan(0);
  expect(
    await page.evaluate(() => window.__modelDocumentProgressWrites),
  ).toEqual([]);
  expect(pageErrors).toEqual([]);
  expect(apiRequests).toEqual([]);
  expect(
    await page.evaluate(() => window.__modelDocumentGenerationRequests),
  ).toEqual([]);
});

test("model reading remains within a narrow viewport and its directory resumes reading", async ({
  page,
}, testInfo) => {
  for (const width of [620, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/e2e/model-document.html");
    await expect(page.locator(".reading-outline-layout")).toHaveAttribute(
      "data-narrow",
      "true",
    );
    const introduction = page.getByRole("group", {
      name: "1 Introduction 阅读状态",
    });
    await introduction
      .getByRole("button", { name: "已读完", exact: true })
      .click();
    await page.getByRole("button", { name: "展开文章目录" }).click();
    await expect(
      page.getByText("已读完 1 / 3 个大章节", { exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "继续阅读：2 Methods", exact: true })
      .click();
    const methods = page.locator("#model-reading-browser-model-parse-methods");
    await expect(methods).toBeFocused();
    await expect(
      page.getByRole("navigation", { name: "文章目录" }),
    ).not.toBeVisible();
    const toolbar = await page
      .locator(".reading-outline-toolbar")
      .boundingBox();
    const heading = await methods.boundingBox();
    expect(toolbar).not.toBeNull();
    expect(heading).not.toBeNull();
    expect(heading!.y).toBeGreaterThanOrEqual(toolbar!.y + toolbar!.height + 8);
    await expect(page.locator(".paper-formula-rendered .katex")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    await page.screenshot({
      path: testInfo.outputPath(
        width === 620
          ? "model-document-narrow.png"
          : "model-document-narrow-390.png",
      ),
      fullPage: false,
    });
  }
});

test("model reading without selected translation retains translation slots and validated annotations", async ({
  page,
}, testInfo) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto("/e2e/model-document.html?mode=no-translation");
  await expect(page.getByLabel("当次导入选择")).toHaveCount(0);
  await expect(page.locator(".paper-paragraph-translation")).toHaveCount(8);
  await expect(page.getByLabel("正文第 1 段中文译文")).toContainText(
    "尚无本段译文",
  );
  await expect(page.getByLabel("正文第 1 段论证批注")).toContainText(
    "说明作者主张的支撑关系",
  );
  await expect(page.locator("mark[data-highlight-type]")).toHaveCount(4);
  await expect(page.locator(".paper-formula-rendered .katex")).toBeVisible();
  expect(
    await page.evaluate(() => window.__modelDocumentGenerationRequests),
  ).toEqual([]);
  expect(pageErrors).toEqual([]);
  await page.screenshot({
    path: testInfo.outputPath("model-reading-no-translation.png"),
    fullPage: false,
  });
  const translate = page.getByRole("button", {
    name: "仅补生成中文译文",
    exact: true,
  });
  await expect(translate).toBeHidden();
  await page.getByText("更多精读操作", { exact: true }).click();
  await expect(translate).toBeDisabled();
  await page
    .getByRole("checkbox", { name: /允许本次发送模型提取内容/ })
    .check();
  await translate.click();
  await expect(
    page.getByText("任务进行中：逐段中文翻译", {
      exact: true,
    }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => window.__modelDocumentGenerationRequests),
  ).toEqual([{ item_kind: "translation", translation_mode: "full" }]);
  await expect(page.locator("mark[data-highlight-type]")).toHaveCount(4);
});

test("an import without reading generation shows common placeholders and generates only after explicit choices", async ({
  page,
}, testInfo) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto("/e2e/model-document.html?mode=unselected");
  await expect(
    page.getByText("尚无全文精读笔记，可在下方选择生成。"),
  ).toBeVisible();
  await expect(page.locator(".paper-paragraph-translation")).toHaveCount(8);
  await expect(page.getByLabel("正文第 1 段论证批注")).toContainText(
    "全文笔记生成后",
  );
  await expect(page.getByLabel("全文论证标注图例")).toContainText("核心论点");
  await expect(page.locator("mark[data-highlight-type]")).toHaveCount(0);
  await expect(page.locator(".paper-formula-rendered .katex")).toBeVisible();
  const generate = page.getByRole("button", {
    name: "生成全文精读笔记",
    exact: true,
  });
  await expect(generate).toBeDisabled();
  expect(
    await page.evaluate(() => window.__modelDocumentGenerationRequests),
  ).toEqual([]);
  await page.screenshot({
    path: testInfo.outputPath("model-reading-not-generated.png"),
    fullPage: false,
  });
  await page
    .getByRole("checkbox", { name: /允许本次发送模型提取内容/ })
    .check();
  await page.getByRole("checkbox", { name: "同时生成逐段中文翻译" }).check();
  await generate.click();
  await expect(
    page.getByText("任务进行中：全文精读笔记生成、逐段中文翻译", {
      exact: true,
    }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => window.__modelDocumentGenerationRequests),
  ).toEqual([{ item_kind: "paper_reading", translation_mode: "full" }]);
  expect(pageErrors).toEqual([]);
});

test("active model card status stays visible while switching to local reading and QA", async ({
  page,
}) => {
  await page.goto("/e2e/model-document.html?workspace=dual&mode=active");
  const status = page.getByText("任务进行中：论文卡片集生成", { exact: true });
  await expect(status).toHaveCount(1);
  await page.getByRole("combobox", { name: "查看来源" }).selectOption("local");
  await expect(status).toHaveCount(1);
  await page.getByRole("button", { name: "论文回答" }).click();
  await expect(status).toHaveCount(1);
  await expect(page.getByLabel("当次导入选择")).toHaveCount(0);
});
