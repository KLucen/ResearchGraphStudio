import { expect, test } from "@playwright/test";

test("workspace tree owns the available sidebar height and scrolls independently at desktop sizes", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/e2e/sidebar.html");
  const sidebar = page.getByRole("complementary", { name: "工作空间侧边栏" });
  const tree = page.getByRole("region", { name: "个人研究项目" });
  await expect(
    tree.getByRole("button", { name: "合成研究项目 1", exact: true }),
  ).toBeVisible();
  await expect(
    sidebar.getByText(/ResearchGraph|知识，留在本地|LITE|0\.1\.0/),
  ).toHaveCount(0);
  const measurements: unknown[] = [];
  for (const size of [
    { width: 1280, height: 800 },
    { width: 1440, height: 1024 },
    { width: 900, height: 640 },
  ]) {
    await page.setViewportSize(size);
    const bounds = await sidebar.boundingBox();
    const treeBounds = await tree.boundingBox();
    measurements.push({
      ...size,
      treeHeight: treeBounds!.height,
      sidebarHeight: bounds!.height,
      treeShare: treeBounds!.height / bounds!.height,
    });
    expect(treeBounds!.height / bounds!.height).toBeGreaterThanOrEqual(0.45);
    expect(
      await sidebar.evaluate(
        (element) => element.scrollHeight <= element.clientHeight + 1,
      ),
    ).toBe(true);
    expect(
      await tree.evaluate(
        (element) => element.scrollHeight > element.clientHeight,
      ),
    ).toBe(true);
    await expect(
      sidebar.getByRole("button", { name: "设置与诊断", exact: true }),
    ).toBeInViewport();
    await page.screenshot({
      path: testInfo.outputPath(`sidebar-${size.width}x${size.height}.png`),
    });
  }
  await testInfo.attach("sidebar-layout.json", {
    body: JSON.stringify(measurements),
    contentType: "application/json",
  });
  await page.setViewportSize({ width: 1280, height: 800 });
  const navStyles = await sidebar.locator(".nav").evaluateAll((buttons) =>
    buttons.map((button) => {
      const style = getComputedStyle(button);
      const icon = button.querySelector("svg")!.getBoundingClientRect();
      return [style.fontSize, style.lineHeight, icon.width, icon.height];
    }),
  );
  expect(navStyles).toEqual(
    Array.from({ length: 5 }, () => ["13px", "20px", 18, 18]),
  );
  await tree.hover();
  await page.mouse.wheel(0, 700);
  await expect
    .poll(() => tree.evaluate((element) => element.scrollTop))
    .toBeGreaterThan(0);
  expect(await page.evaluate(() => scrollY)).toBe(0);
  const paper = tree.getByRole("button", { name: /^合成论文 24：/ });
  await paper.focus();
  await page.keyboard.press("Enter");
  await expect(paper).toHaveAttribute("aria-current", "page");
  await expect
    .poll(() => page.evaluate(() => window.__sidebarViewedPapers))
    .toContain("sidebar-project-1-paper-24");
  await sidebar.getByRole("button", { name: "导入论文", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "导入论文", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "本地 PDF", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "关闭导入论文" }).click();
  await sidebar
    .getByRole("button", { name: "新建研究项目", exact: true })
    .click();
  await page.getByLabel("项目名称").fill("新增侧栏合成项目");
  await page.getByRole("button", { name: "创建 Lite 项目" }).click();
  await expect
    .poll(() => page.evaluate(() => window.__sidebarCreatedProjects))
    .toEqual(["新增侧栏合成项目"]);
  await expect(
    tree.getByRole("button", { name: "新增侧栏合成项目", exact: true }),
  ).toBeAttached();
  await sidebar.getByRole("button", { name: "折叠侧边栏" }).click();
  await expect(tree).toBeHidden();
  await expect(
    sidebar.getByRole("button", { name: "展开侧边栏" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(tree).toBeVisible();
  await expect(
    sidebar.getByRole("button", { name: "折叠侧边栏" }),
  ).toHaveAttribute("aria-expanded", "true");
  await page.setViewportSize({ width: 620, height: 800 });
  await expect(tree).toBeHidden();
  await sidebar.getByRole("button", { name: "展开侧边栏" }).click();
  await expect(tree).toBeVisible();
  expect(await page.evaluate(() => window.__sidebarUnexpectedRequests)).toEqual(
    [],
  );
  expect(errors).toEqual([]);
});

for (const width of [620, 390]) {
  test(`small screen ${width} keeps the paper tree reachable through the compact sidebar`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 800 });
    await page.goto("/e2e/sidebar.html");
    const sidebar = page.getByRole("complementary", { name: "工作空间侧边栏" });
    const tree = page.getByRole("region", { name: "个人研究项目" });
    await expect(
      sidebar.getByRole("button", { name: "展开侧边栏" }),
    ).toBeVisible();
    await expect(tree).toBeHidden();
    await sidebar.getByRole("button", { name: "展开侧边栏" }).click();
    await expect(tree).toBeVisible();
    expect(
      await sidebar.evaluate(
        (element) => element.scrollHeight <= element.clientHeight + 1,
      ),
    ).toBe(true);
    const paper = tree.getByRole("button", { name: /^合成论文 24：/ });
    await paper.scrollIntoViewIfNeeded();
    await paper.click();
    await expect(tree).toBeHidden();
    await expect(
      sidebar.getByRole("button", { name: "展开侧边栏" }),
    ).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(paper).toHaveAttribute("aria-current", "page");
    await page.screenshot({
      path: testInfo.outputPath(`sidebar-narrow-${width}.png`),
    });
    await page.keyboard.press("Escape");
    await expect(tree).toBeHidden();
    await sidebar.getByRole("button", { name: "展开侧边栏" }).click();
    await page
      .getByRole("button", { name: "收起侧边栏", exact: true })
      .click({ position: { x: width - 10, y: 400 } });
    await expect(tree).toBeHidden();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
    expect(
      await page.evaluate(() => window.__sidebarUnexpectedRequests),
    ).toEqual([]);
  });
}
