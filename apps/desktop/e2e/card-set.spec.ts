import { expect, test } from "@playwright/test";

for (const source of ["local", "model"] as const) {
  test(`${source} detailed card set categorizes evidence and keeps all browsing local`, async ({
    page,
  }, testInfo) => {
    const errors: string[] = [];
    const unexpected: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("request", (request) => {
      if (!request.url().startsWith("http://127.0.0.1:1427/"))
        unexpected.push(request.url());
    });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`/e2e/card-set.html?source=${source}`);
    await expect(page.getByRole("heading", { name: "文章总览" })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "这篇文章的卡片集" }),
    ).toBeVisible();
    await expect(
      page.getByText("这篇合成文章研究共享记忆方法的运行效率。"),
    ).toBeVisible();
    await expect(page.locator(".react-flow")).toHaveCount(0);
    const card = page.getByRole("article");
    await expect(card).toHaveAccessibleName(
      "研究问题卡片：降低共享记忆任务的运行时间",
    );
    await expect(card).toContainText(
      "We study the runtime of shared memory tasks.",
    );
    await expect(card).toContainText("我们研究共享记忆任务的运行时间。");
    await expect(card).toContainText("作者陈述的概括");
    await expect(
      card.getByRole("heading", { name: "Paper Evidence / 原文依据" }),
    ).toBeVisible();
    if (source === "local") {
      await expect(card).toContainText("第 2 页");
      await card.getByRole("button", { name: "查看对应原文" }).click();
      expect(await page.evaluate(() => window.__cardNavigation)).toEqual([
        { sectionId: "intro", paragraphId: "intro-unit-1" },
      ]);
    } else {
      await expect(card).toContainText("页码不可用 · 模型解析片段");
      await expect(
        card.getByRole("button", { name: "查看对应原文" }),
      ).toHaveCount(0);
      await card.getByText("定位信息", { exact: true }).click();
      await expect(card).toContainText("model-segment-s1");
    }
    await page.screenshot({
      path: testInfo.outputPath(`card-set-${source}-desktop.png`),
      fullPage: true,
    });
    const categories = page.getByRole("navigation", { name: "卡片类别" });
    await categories.getByRole("button", { name: /关键概念/ }).click();
    await expect(card).toHaveAccessibleName("关键概念卡片：共享记忆");
    await categories.getByRole("button", { name: /全部类别/ }).click();
    await page.getByRole("textbox", { name: "搜索文章卡片" }).fill("12%");
    await expect(card).toHaveAccessibleName(
      "主要结果卡片：结果需要核对对照条件",
    );
    await expect(card).toContainText("模型分析 · 待核查");
    await expect(card).toContainText("此条依据尚未提供中文译文。");
    await categories.getByRole("button", { name: /作者自述局限/ }).click();
    await expect(page.getByText("此范围没有卡片")).toBeVisible();
    await page.getByRole("button", { name: "重置筛选" }).click();
    await page
      .getByLabel("总览依据卡片")
      .getByRole("button", { name: "降低共享记忆任务的运行时间" })
      .click();
    await card.getByRole("button", { name: "标为已读完" }).click();
    await card.getByRole("button", { name: "收藏卡片" }).click();
    await card.getByText("我的笔记", { exact: true }).click();
    await card
      .getByRole("textbox", { name: "个人阅读笔记" })
      .fill("我的阅读疑问，保留待核查。");
    await card.getByRole("button", { name: "保存个人笔记" }).click();
    await page.reload();
    await expect(
      card.getByRole("button", { name: "已读完", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    await expect(
      card.getByRole("button", { name: "取消收藏" }),
    ).toHaveAttribute("aria-pressed", "true");
    await expect(
      card.getByRole("textbox", { name: "个人阅读笔记" }),
    ).toHaveValue("我的阅读疑问，保留待核查。");
    await page
      .getByRole("combobox", { name: "卡片查看范围" })
      .selectOption("saved");
    await expect(page.getByText("显示 1 张卡片")).toBeVisible();
    await card.getByRole("button", { name: "隐藏卡片" }).click();
    await expect(page.getByText("此范围没有卡片")).toBeVisible();
    await page
      .getByRole("combobox", { name: "卡片查看范围" })
      .selectOption("hidden");
    await expect(card).toHaveAccessibleName(
      "研究问题卡片：降低共享记忆任务的运行时间",
    );
    await card.getByRole("button", { name: "恢复显示" }).click();
    await page
      .getByRole("combobox", { name: "卡片查看范围" })
      .selectOption("all");
    await page.getByRole("button", { name: "切换合成结果版本" }).click();
    await expect(
      card.getByRole("button", { name: "标为已读完" }),
    ).toHaveAttribute("aria-pressed", "false");
    await expect(
      card.getByRole("button", { name: "收藏卡片" }),
    ).toHaveAttribute("aria-pressed", "false");
    await page.getByRole("button", { name: "切换合成结果版本" }).click();
    await expect(
      card.getByRole("button", { name: "已读完", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(await page.evaluate(() => window.__cardRequests)).toEqual([]);
    expect(errors).toEqual([]);
    expect(unexpected).toEqual([]);
  });
}

test("narrow card set scrolls categories inside the panel and exposes full evidence without page overflow", async ({
  page,
}, testInfo) => {
  for (const width of [620, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/e2e/card-set.html");
    await expect(page.getByRole("heading", { name: "文章总览" })).toBeVisible();
    const categories = page.getByRole("navigation", { name: "卡片类别" });
    await categories.getByRole("button", { name: /主要结果/ }).click();
    await expect(page.getByRole("article")).toHaveAccessibleName(
      "主要结果卡片：结果需要核对对照条件",
    );
    await expect(page.getByRole("article")).toContainText(
      "Runtime falls by 12% in the synthetic setting.",
    );
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    await page.screenshot({
      path: testInfo.outputPath(`card-set-${width}.png`),
      fullPage: true,
    });
    expect(await page.evaluate(() => window.__cardRequests)).toEqual([]);
  }
});

test("legacy content is absent and explicit consent alone authorizes one new card request", async ({
  page,
}) => {
  await page.goto("/e2e/card-set.html?source=model&scenario=legacy");
  await expect(page.getByText(/尚未生成新版论文卡片集/)).toBeVisible();
  await expect(page.getByText("LEGACY_GRAPH_CARD_MUST_NOT_APPEAR")).toHaveCount(
    0,
  );
  await expect(page.getByText("OLD_GRAPH_MUST_NOT_APPEAR")).toHaveCount(0);
  const generate = page.getByRole("button", { name: "生成论文卡片集" });
  await expect(generate).toBeDisabled();
  expect(await page.evaluate(() => window.__cardRequests)).toEqual([]);
  await page
    .getByRole("checkbox", { name: /允许向已配置模型发送本篇论文内容/ })
    .check();
  await generate.click();
  await expect(page.getByText("任务进行中：论文卡片集生成")).toBeVisible();
  expect(await page.evaluate(() => window.__cardRequests)).toEqual([
    { kind: "model-generate", args: ["paper", "revision", true, false, true] },
  ]);
});
