import { expect, test } from "@playwright/test";

test("the paper outline follows article scroll, reveals the active item and collapses without navigation", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto("/e2e/reading-outline.html");
  const outline = page.getByRole("navigation", { name: "文章目录" });
  await expect(outline).toBeVisible();
  await page
    .locator("#paper-reading-h16")
    .evaluate((element) => element.scrollIntoView({ block: "start" }));
  const active = outline.getByRole("button", {
    name: "Section 16",
    exact: true,
  });
  await expect(active).toHaveAttribute("aria-current", "location");
  const listBox = await outline.boundingBox();
  const activeBox = await active.boundingBox();
  expect(activeBox!.y).toBeGreaterThanOrEqual(listBox!.y - 1);
  expect(activeBox!.y + activeBox!.height).toBeLessThanOrEqual(
    listBox!.y + listBox!.height + 1,
  );
  const toggle = page.getByRole("button", { name: "收起文章目录" });
  const sidebar = await page
    .getByRole("complementary", { name: "阅读导航" })
    .boundingBox();
  const body = await page.locator(".reading-outline-content").boundingBox();
  expect(sidebar!.x + sidebar!.width).toBeLessThan(body!.x);
  expect(sidebar!.y).toBeGreaterThanOrEqual(18);
  await page.screenshot({ path: testInfo.outputPath("outline-desktop.png") });
  const paragraph = page.locator("#paper-reading-p16 .paper-paragraph-english");
  await paragraph.evaluate((element) =>
    window.scrollBy({
      top: element.getBoundingClientRect().top - 140,
      behavior: "instant",
    }),
  );
  const paragraphTop = (await paragraph.boundingBox())!.y;
  await toggle.click();
  await expect(outline).not.toBeVisible();
  expect(
    Math.abs((await paragraph.boundingBox())!.y - paragraphTop),
  ).toBeLessThan(2);
  const expandedBody = await page
    .locator(".reading-outline-content")
    .boundingBox();
  expect(expandedBody!.width).toBeGreaterThan(body!.width + 140);
  const before = await page.evaluate(() => window.scrollY);
  await page.getByRole("button", { name: "在目录中定位当前章节" }).click();
  await expect(outline).toBeVisible();
  await expect(active).toHaveAttribute("aria-current", "location");
  expect(
    Math.abs((await paragraph.boundingBox())!.y - paragraphTop),
  ).toBeLessThan(2);
  await expect(active).toBeFocused();
  // Also preserve the actual text line halfway through a long paragraph. Its
  // boundary may reflow, so compare a live character range in the original text.
  const textAnchor = await paragraph.evaluateHandle((element) => {
    const text = document
      .createTreeWalker(element, NodeFilter.SHOW_TEXT)
      .nextNode()!;
    const midpoint = document.createRange();
    midpoint.setStart(text, Math.floor((text.textContent?.length || 0) / 2));
    midpoint.collapse(true);
    window.scrollBy({
      top: midpoint.getBoundingClientRect().top - 140,
      behavior: "instant",
    });
    return document.caretRangeFromPoint(
      element.getBoundingClientRect().left + 8,
      140,
    )!;
  });
  const textTop = await textAnchor.evaluate(
    (range) => range.getBoundingClientRect().top,
  );
  await toggle.click();
  expect(
    Math.abs(
      (await textAnchor.evaluate(
        (range) => range.getBoundingClientRect().top,
      )) - textTop,
    ),
  ).toBeLessThan(2);
  await page.getByRole("button", { name: "在目录中定位当前章节" }).click();
  expect(
    Math.abs(
      (await textAnchor.evaluate(
        (range) => range.getBoundingClientRect().top,
      )) - textTop,
    ),
  ).toBeLessThan(2);
  await textAnchor.dispose();
  expect(await page.evaluate(() => window.__outlineModelCalls)).toBe(0);
  expect(before).toBeGreaterThan(0);
});

test("compact outline uses workspace width and closes by Escape, outside click and section selection", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1120, height: 900 });
  await page.goto("/e2e/reading-outline.html");
  const layout = page.locator(".reading-outline-layout");
  await expect(layout).toHaveAttribute("data-narrow", "true");
  const toggle = page.getByRole("button", { name: "展开文章目录" });
  await expect(toggle).toBeVisible();
  await toggle.click();
  await page.keyboard.press("Escape");
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(toggle).toBeFocused();
  await toggle.click();
  await page.getByRole("heading", { name: "全文精读", exact: true }).click();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await page
    .getByRole("navigation", { name: "文章目录" })
    .getByRole("button", { name: "Section 10", exact: true })
    .click();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator("#paper-reading-h10")).toBeFocused();
  await page.screenshot({
    path: testInfo.outputPath("outline-compact-workspace.png"),
  });
  await page.setViewportSize({ width: 620, height: 900 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath("outline-narrow.png") });
  expect(await page.evaluate(() => window.__outlineModelCalls)).toBe(0);
});

test("QA directory selects and locates a local chapter while retaining the chosen question scope", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto("/e2e/reading-outline.html?scenario=qa");
  const scope = page.getByRole("combobox", { name: "作用范围", exact: true });
  await scope.selectOption("paper");
  const outline = page.getByRole("navigation", { name: "文章目录" });
  await outline
    .getByRole("button", { name: "Section 12", exact: true })
    .click();
  await expect(
    outline.getByRole("button", { name: "Section 12", exact: true }),
  ).toHaveAttribute("aria-current", "location");
  await expect(scope).toHaveValue("paper");
  await expect(page.locator("#reading-section-s12")).toBeFocused();
  expect(await page.evaluate(() => window.__outlineSourceReads)).toEqual([]);
  await expect(page.locator(".section-text")).toHaveCount(0);
  await page.getByText("Section 12 · 查看章节原文", { exact: true }).click();
  await expect(page.locator(".section-text")).toContainText(
    "Original source for Section 12",
  );
  expect(await page.evaluate(() => window.__outlineSourceReads)).toEqual([
    "s12",
  ]);
  await page.getByRole("button", { name: "收起文章目录" }).click();
  await page.getByRole("button", { name: "在目录中定位当前章节" }).click();
  await expect(
    outline.getByRole("button", { name: "Section 12", exact: true }),
  ).toBeFocused();
  await expect(scope).toHaveValue("paper");
  const source = page.locator(".section-text");
  await source.evaluate((element) => {
    // Midway through the internal range, with the toolbar still visible, so
    // a normal click needs no preparatory page scrolling by the browser.
    element.scrollTop = (element.scrollHeight - element.clientHeight) / 2;
    window.scrollBy({
      top: element.getBoundingClientRect().top - 120,
      behavior: "instant",
    });
  });
  expect(await source.evaluate((element) => element.scrollTop)).toBeGreaterThan(
    0,
  );
  const sourceTop = (await source.boundingBox())!.y;
  const sourceAnchor = await source.evaluateHandle((element) =>
    document.caretRangeFromPoint(
      element.getBoundingClientRect().left + 8,
      140,
    )!,
  );
  expect(
    await sourceAnchor.evaluate((range) =>
      document.querySelector(".section-text")!.contains(range.startContainer),
    ),
  ).toBeTruthy();
  const sourceTextTop = await sourceAnchor.evaluate(
    (range) => range.getBoundingClientRect().top,
  );
  await page.getByRole("button", { name: "收起文章目录" }).click();
  expect(Math.abs((await source.boundingBox())!.y - sourceTop)).toBeLessThan(2);
  expect(
    Math.abs(
      (await sourceAnchor.evaluate(
        (range) => range.getBoundingClientRect().top,
      )) - sourceTextTop,
    ),
  ).toBeLessThan(2);
  await page.getByRole("button", { name: "在目录中定位当前章节" }).click();
  expect(Math.abs((await source.boundingBox())!.y - sourceTop)).toBeLessThan(2);
  expect(
    Math.abs(
      (await sourceAnchor.evaluate(
        (range) => range.getBoundingClientRect().top,
      )) - sourceTextTop,
    ),
  ).toBeLessThan(2);
  await sourceAnchor.dispose();
  await expect(scope).toHaveValue("paper");
  expect(await page.evaluate(() => window.__outlineModelCalls)).toBe(0);
  await page.screenshot({ path: testInfo.outputPath("outline-qa.png") });
});

test("a short final section remains current at the bottom of a real scrolling document", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.goto("/e2e/reading-outline.html?scenario=short");
  const outline = page.getByRole("navigation", { name: "文章目录" });
  await expect(
    outline.getByRole("button", { name: "Introduction", exact: true }),
  ).toHaveAttribute("aria-current", "location");
  await page.evaluate(() =>
    window.scrollTo(0, document.documentElement.scrollHeight),
  );
  const final = outline.getByRole("button", {
    name: "Final short section",
    exact: true,
  });
  await expect(final).toHaveAttribute("aria-current", "location");
  await final.click();
  await expect(final).toHaveAttribute("aria-current", "location");
});

test("three-level outline branches fold locally and locating or reading a new chapter reveals its ancestors", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto("/e2e/reading-outline.html?scenario=tree");
  const outline = page.getByRole("navigation", { name: "文章目录" });
  const detail = outline.getByRole("button", {
    name: "1.1.1 Detail",
    exact: true,
  });
  await expect(detail.locator("xpath=ancestor::li[1]")).toHaveAttribute(
    "data-outline-level",
    "3",
  );
  await detail.click();
  await expect(page.locator("#tree-detail-1")).toBeFocused();
  await page.screenshot({
    path: testInfo.outputPath("outline-tree-desktop.png"),
  });
  const beforeFold = await page.evaluate(() => window.scrollY);
  await outline
    .getByRole("button", { name: "收起 1.1 Context 的子章节" })
    .click();
  await expect(detail).not.toBeVisible();
  await outline
    .getByRole("button", { name: "收起 1 Introduction 的子章节" })
    .click();
  await expect(
    outline.getByRole("button", { name: "1.1 Context", exact: true }),
  ).not.toBeVisible();
  expect(await page.evaluate(() => window.scrollY)).toBe(beforeFold);
  await page.screenshot({
    path: testInfo.outputPath("outline-tree-folded.png"),
  });
  await page.getByRole("button", { name: "在目录中定位当前章节" }).click();
  await expect(detail).toBeVisible();
  await expect(detail).toBeFocused();
  expect(await page.evaluate(() => window.scrollY)).toBe(beforeFold);
  await outline
    .getByRole("button", { name: "收起 2 Methods 的子章节" })
    .click();
  const next = outline.getByRole("button", {
    name: "2.1.1 Parameters",
    exact: true,
  });
  await expect(next).not.toBeVisible();
  await page
    .locator("#tree-detail-2")
    .evaluate((element) => element.scrollIntoView({ block: "start" }));
  await expect(next).toBeVisible();
  await expect(next).toHaveAttribute("aria-current", "location");
  await page.setViewportSize({ width: 1120, height: 900 });
  await expect(
    page.getByRole("button", { name: "展开文章目录" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "展开文章目录" }).click();
  await page.screenshot({
    path: testInfo.outputPath("outline-tree-compact.png"),
  });
  expect(await page.evaluate(() => window.__outlineModelCalls)).toBe(0);
});
