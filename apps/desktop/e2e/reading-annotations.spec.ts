import { expect, test, type Locator } from "@playwright/test";

async function analysisPosition(row: Locator) {
  return row.evaluate((element) => {
    const source = element
      .querySelector<HTMLElement>(".paper-paragraph-source")!
      .getBoundingClientRect();
    const english = element
      .querySelector<HTMLElement>(".paper-paragraph-english")!
      .getBoundingClientRect();
    const analysis = element
      .querySelector<HTMLElement>(".paper-paragraph-comment")!
      .getBoundingClientRect();
    const rowTop = element.getBoundingClientRect().top;
    return {
      sourceRight: source.right,
      englishTop: english.top,
      analysisTop: analysis.top,
      analysisLeft: analysis.left,
      relativeTop: analysis.top - rowTop,
    };
  });
}

test("analysis stays beside the source and uses compact references without duplicate excerpt cards", async ({
  page,
}, testInfo) => {
  const failures: string[] = [];
  const requests: string[] = [];
  page.on("pageerror", (error) => failures.push(error.message));
  await page.route("**/api/**", async (route) => {
    requests.push(route.request().url());
    await route.abort();
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/e2e/reading-annotations.html");
  const sparse = page.locator("#annotation-sparse-row");
  const dense = page.locator("#annotation-dense-row");
  await expect(sparse).toHaveAttribute("data-note-layout", "anchored");
  await expect(sparse.locator(".paper-highlight-reference")).toHaveCount(5);
  await expect(dense.locator(".paper-highlight-reference")).toHaveCount(6);
  await expect(
    page.locator(".paper-highlight-note, .paper-paragraph-note blockquote"),
  ).toHaveCount(0);
  for (const type of [
    "核心论点",
    "概念定义",
    "论据与结果",
    "反驳与局限",
    "方法与过程",
  ]) {
    await expect(sparse.locator(".paper-paragraph-note")).toContainText(type);
  }
  const markColors = await sparse
    .locator("mark[data-highlight-type]")
    .evaluateAll((marks) =>
      marks.map((mark) => getComputedStyle(mark).backgroundColor),
    );
  expect(new Set(markColors).size).toBe(5);
  await expect(sparse.locator(".paper-paragraph-comment")).toContainText(
    "本段将主张、术语、试验和范围限制串联起来。",
  );
  for (const row of [sparse, dense]) {
    const original = await row.evaluate(
      (element) =>
        window.__annotationSources[
          (element as HTMLElement).dataset.paragraphId!
        ],
    );
    expect(await row.locator(".paper-paragraph-english").textContent()).toBe(
      original,
    );
    await expect(async () => {
      const position = await analysisPosition(row);
      expect(position.analysisLeft).toBeGreaterThan(position.sourceRight);
      expect(position.analysisTop).toBeLessThanOrEqual(
        position.englishTop + 84,
      );
    }).toPass();
    await expect(row.locator(".paper-paragraph-note")).not.toContainText(
      "The bounded model improves the stated objective.",
    );
  }
  await expect(dense.locator('mark[data-annotation-keys~="1"]')).toHaveText(
    "alpha",
  );
  await expect(dense.locator("img,script")).toHaveCount(0);
  await page.screenshot({
    path: testInfo.outputPath("reading-analysis-right.png"),
    fullPage: false,
  });
  expect(failures).toEqual([]);
  expect(requests).toEqual([]);
});

test("source marks and compact analysis references navigate in both directions with keyboard support", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/e2e/reading-annotations.html");
  const row = page.locator("#annotation-sparse-row");
  const mark = row.locator('mark[data-annotation-keys~="2"]');
  const reference = row.locator(
    '.paper-highlight-reference[data-annotation-key="2"]',
  );
  await expect(mark).toHaveAttribute("role", "button");
  await expect(mark).toHaveAttribute("data-note-number", "1.3");
  await mark.click();
  await expect(reference).toHaveAttribute("data-active", "true");
  await expect(reference).toBeFocused();
  await reference.click();
  await expect(mark).toBeFocused();
  await mark.press("Enter");
  await expect(reference).toBeFocused();
  const next = row.locator('mark[data-annotation-keys~="3"]');
  await next.focus();
  await next.press("Space");
  await expect(
    row.locator('.paper-highlight-reference[data-annotation-key="3"]'),
  ).toHaveAttribute("data-active", "true");
  await expect(reference).not.toHaveAttribute("data-active", "true");
});

test("analysis remains near the beginning after font changes and follows the actual reading width", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/e2e/reading-annotations.html");
  const row = page.locator("#annotation-sparse-row");
  await expect(row).toHaveAttribute("data-note-layout", "anchored");
  await page.getByRole("button", { name: "增大正文字号" }).click();
  await expect(async () => {
    const position = await analysisPosition(row);
    expect(position.analysisLeft).toBeGreaterThan(position.sourceRight);
    expect(position.analysisTop).toBeLessThanOrEqual(position.englishTop + 84);
  }).toPass();
  await page.getByRole("button", { name: "缩小阅读宽度" }).click();
  await expect(row).toHaveAttribute("data-note-layout", "stacked");
  await page.getByRole("button", { name: "恢复阅读宽度" }).click();
  await expect(row).toHaveAttribute("data-note-layout", "anchored");
  await expect(async () => {
    const position = await analysisPosition(row);
    expect(position.analysisLeft).toBeGreaterThan(position.sourceRight);
    expect(position.analysisTop).toBeLessThanOrEqual(position.englishTop + 84);
  }).toPass();
});

test("reading keeps analysis on the right at tablet width and stacks only on a narrow phone", async ({
  page,
}, testInfo) => {
  for (const width of [620, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/e2e/reading-annotations.html");
    const row = page.locator("#annotation-dense-row");
    await expect(row).toHaveAttribute(
      "data-note-layout",
      width === 620 ? "anchored" : "stacked",
    );
    const reference = row.locator(
      '.paper-highlight-reference[data-annotation-key="3"]',
    );
    await reference.click();
    await expect(row.locator('mark[data-annotation-keys~="3"]')).toBeFocused();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    await row.locator(".paper-paragraph-comment").scrollIntoViewIfNeeded();
    await page.screenshot({
      path: testInfo.outputPath(`reading-analysis-${width}.png`),
      fullPage: false,
    });
  }
});

test("expanding source information repositions analysis without pushing it under the translation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/e2e/reading-annotations.html");
  const row = page.locator("#annotation-dense-row");
  await expect(row).toHaveAttribute("data-note-layout", "anchored");
  const before = await analysisPosition(row);
  await page.getByRole("button", { name: "展开来源信息" }).click();
  await expect(async () => {
    const after = await analysisPosition(row);
    expect(after.relativeTop).toBeGreaterThan(before.relativeTop + 20);
    expect(after.analysisLeft).toBeGreaterThan(after.sourceRight);
    expect(after.analysisTop).toBeLessThanOrEqual(after.englishTop + 84);
  }).toPass();
  await page.getByRole("button", { name: "收起来源信息" }).click();
  await expect(async () => {
    const restored = await analysisPosition(row);
    expect(Math.abs(restored.relativeTop - before.relativeTop)).toBeLessThan(2);
  }).toPass();
});
