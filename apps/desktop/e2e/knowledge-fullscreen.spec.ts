import { expect, test } from "@playwright/test";

for (const mode of ["element", "viewport"] as const) {
  test(`knowledge map ${mode} fullscreen preserves the mounted graph and camera`, async ({
    page,
  }) => {
    if (mode === "viewport") {
      await page.addInitScript(() => {
        Element.prototype.requestFullscreen = async () => {
          throw new DOMException(
            "Fixture disallows fullscreen",
            "NotAllowedError",
          );
        };
      });
      await page.setViewportSize({ width: 620, height: 900 });
    }
    await page.goto("/e2e/knowledge.html");
    await page
      .getByRole("button", { name: "研究内容知识库", exact: true })
      .click();
    await page.getByRole("button", { name: "知识地图", exact: true }).click();
    const map = page.locator(".knowledge-map");
    const canvas = map.locator(".react-flow");
    const camera = canvas.locator(".react-flow__viewport");
    const pinned = canvas.locator(
      '.react-flow__node[data-id="paper:library-A"]',
    );
    const enter = map.getByRole("button", { name: "全屏", exact: true });
    const exit = map.getByRole("button", { name: "退出全屏", exact: true });
    await expect(pinned).toHaveClass(/pinned/);
    const renderer = await canvas.elementHandle();
    const beforeCamera = await camera.evaluate(
      (el) => getComputedStyle(el).transform,
    );
    const beforeNode = await pinned.evaluate(
      (el) => getComputedStyle(el).transform,
    );
    await enter.click();
    await expect(map).toHaveAttribute("data-fullscreen", mode);
    await expect(exit).toBeFocused();
    await expect(map.getByRole("button", { name: "聚焦图谱" })).toBeVisible();
    await expect(map.getByLabel("知识地图图例")).toBeVisible();
    expect(
      await map.evaluate(
        (el) => el.getBoundingClientRect().height >= innerHeight - 1,
      ),
    ).toBe(true);
    expect(
      await page.evaluate(() =>
        Boolean(document.querySelector("nav")?.closest("[inert]")),
      ),
    ).toBe(true);
    expect(
      await canvas.evaluate((el, previous) => el === previous, renderer),
    ).toBe(true);
    await expect(camera).toHaveCSS("transform", beforeCamera);
    await expect(pinned).toHaveCSS("transform", beforeNode);
    await expect(pinned).toHaveClass(/pinned/);
    await page.keyboard.press("Escape");
    await expect(map).not.toHaveAttribute("data-fullscreen", /.+/);
    await expect(enter).toBeFocused();
    expect(await page.evaluate(() => document.fullscreenElement)).toBeNull();
    expect(
      await page.evaluate(() =>
        Boolean(document.querySelector("nav")?.closest("[inert]")),
      ),
    ).toBe(false);
    await expect(camera).toHaveCSS("transform", beforeCamera);

    await enter.click();
    await expect(map).toHaveAttribute("data-fullscreen", mode);
    await exit.click();
    await expect(enter).toBeFocused();
    expect(
      await canvas.evaluate((el, previous) => el === previous, renderer),
    ).toBe(true);
    await expect(camera).toHaveCSS("transform", beforeCamera);
    await expect(pinned).toHaveCSS("transform", beforeNode);
    expect(await page.evaluate(() => window.__knowledgeLayoutWrites)).toBe(0);
    expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);
  });
}

test("paper details can open above the fullscreen map and return to paper reading", async ({
  page,
}) => {
  await page.goto("/e2e/knowledge.html");
  await page
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  await page.getByRole("button", { name: "知识地图", exact: true }).click();
  const map = page.locator(".knowledge-map");
  await map.getByRole("button", { name: "全屏", exact: true }).click();
  await expect(map).toHaveAttribute("data-fullscreen", "element");
  await map.locator('.react-flow__node[data-id="paper:library-A"]').click();
  const openPaper = map.getByRole("button", { name: "打开论文知识与阅读入口" });
  const paper = page.getByRole("dialog", { name: "论文知识", exact: true });
  await openPaper.click();
  await expect(paper).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(paper).toHaveCount(0);
  await expect(map).toHaveAttribute("data-fullscreen", "element");
  await openPaper.click();
  await paper.getByRole("button", { name: "返回论文阅读" }).click();
  await expect(map).toHaveCount(0);
  await expect
    .poll(() => page.evaluate(() => document.fullscreenElement === null))
    .toBe(true);
  expect(
    await page.evaluate(() =>
      Boolean(document.querySelector("nav")?.closest("[inert]")),
    ),
  ).toBe(false);
});
