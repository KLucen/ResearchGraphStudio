import { expect, test } from "@playwright/test";

test("knowledge navigation, real graph, report and both source chains form a read-only loop", async ({
  page,
}, testInfo) => {
  const errors: string[] = [],
    external: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (!request.url().startsWith("http://127.0.0.1:1427/"))
      external.push(request.url());
  });
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.goto("/e2e/knowledge.html");
  const nav = page.getByRole("navigation", { name: "主导航" });
  await expect(nav.getByRole("button")).toHaveText([
    "研究项目1",
    "研究内容知识库",
    "任务记录",
  ]);
  await nav
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  await expect(nav.getByLabel("1 份未读联系汇报")).toBeVisible();
  await page.getByRole("button", { name: "知识地图", exact: true }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(2);
  const root = page.locator('.react-flow__node[data-id="paper:library-A"]');
  await root.click();
  await expect(page.locator(".react-flow__node")).toHaveCount(7);
  await page.getByRole("button", { name: "聚焦图谱", exact: true }).click();
  await page
    .locator('.react-flow__node[data-id="version:version-A:A-2"]')
    .click();
  await page.getByText("本地解析材料 · 第 2 页 · 章节 合成方法章节").click();
  await expect(page.getByText("A synthetic source text.")).toBeVisible();
  const edge = page.locator('.react-flow__edge[data-id="cross:relation-1"]');
  await expect(edge.locator(".react-flow__edge-path")).toHaveCSS(
    "stroke-dasharray",
    "4px, 5px",
  );
  await edge.click({ force: true });
  await page.getByRole("button", { name: "打开对应联系汇报" }).click();
  const dialog = page.getByRole("dialog", { name: "联系汇报" });
  await expect(dialog.getByText("新增论文依据")).toBeVisible();
  await expect(dialog.getByText("已有论文依据")).toBeVisible();
  await expect(dialog.getByText(/任务条件不同/)).toBeVisible();
  await dialog.getByText("模型提取材料 · 章节 模型方法章节").click();
  await expect(dialog.getByText("A synthetic source text.")).toBeVisible();
  await dialog.getByRole("button", { name: "置顶汇报", exact: true }).click();
  await dialog.getByLabel("汇报个人备注").fill("需要核查任务条件");
  await dialog.getByRole("button", { name: "保存汇报备注" }).click();
  await expect
    .poll(async () =>
      page.evaluate(
        () => JSON.parse(localStorage.getItem("kb-fixture:report")!).note,
      ),
    )
    .toBe("需要核查任务条件");
  await page.screenshot({ path: testInfo.outputPath("knowledge-report.png") });
  await dialog
    .getByRole("button", { name: "在知识地图中定位这条联系" })
    .click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByLabel("展开论文")).toHaveValue("library-B");
  await expect(
    page.getByRole("button", { name: "打开对应联系汇报" }),
  ).toBeVisible();
  await expect(page.locator(".react-flow__node")).toHaveCount(7);
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});

test("saved report metadata, camera and fixed nodes survive reload and narrow layouts", async ({
  page,
}) => {
  await page.goto("/e2e/knowledge.html");
  await page
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  await page
    .getByRole("button", { name: /合成论文 B 与已有研究的联系/ })
    .click();
  await page.getByLabel("汇报个人备注").fill("长期保存的个人判断");
  await page.getByRole("button", { name: "保存汇报备注" }).click();
  await page.getByRole("button", { name: "置顶汇报", exact: true }).click();
  await page.getByRole("button", { name: "关闭", exact: true }).click();
  await page.getByRole("button", { name: "知识地图", exact: true }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(2);
  await page.locator(".react-flow__controls-zoomin").click();
  await expect
    .poll(async () => page.evaluate(() => window.__knowledgeLayoutWrites))
    .toBeGreaterThan(0);
  const before = await page.evaluate(
    () =>
      JSON.parse(localStorage.getItem("kb-fixture:layout:library:all:all")!)
        .layout.viewport,
  );
  await page.reload();
  await page
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  await expect(
    page.locator('.react-flow__node[data-id="paper:library-A"]'),
  ).toHaveClass(/pinned/);
  const camera = await page
    .locator(".react-flow__viewport")
    .evaluate((element) => {
      const matrix = new DOMMatrixReadOnly(getComputedStyle(element).transform);
      return { x: matrix.e, y: matrix.f, zoom: matrix.a };
    });
  expect(camera.x).toBeCloseTo(before.x, 2);
  expect(camera.y).toBeCloseTo(before.y, 2);
  expect(camera.zoom).toBeCloseTo(before.zoom, 2);
  await page.getByRole("button", { name: "联系汇报", exact: true }).click();
  await page
    .getByRole("button", { name: /合成论文 B 与已有研究的联系/ })
    .click();
  await expect(page.getByLabel("汇报个人备注")).toHaveValue(
    "长期保存的个人判断",
  );
  await expect(page.getByRole("button", { name: "取消置顶" })).toBeVisible();
  await page.getByRole("button", { name: "关闭", exact: true }).click();
  for (const width of [620, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBe(true);
    await page.getByRole("button", { name: "知识地图", exact: true }).click();
    await expect(page.locator(".react-flow__node")).toHaveCount(2);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBe(true);
  }
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);
});

test("only an explicit selected source and consent can submit a knowledge model task", async ({
  page,
}) => {
  await page.goto("/e2e/knowledge.html");
  await page
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  await page
    .getByRole("button", { name: "加入论文知识", exact: true })
    .first()
    .click();
  await page.getByLabel("选择入库论文").selectOption("paper-A");
  await page.getByLabel("选择知识来源").selectOption("model_parse:parse-A");
  await expect(
    page.getByRole("button", { name: "生成带来源知识", exact: true }),
  ).toBeDisabled();
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);
  await page
    .getByRole("checkbox", { name: /允许向已配置模型发送此来源版本/ })
    .check();
  await page
    .getByRole("button", { name: "生成带来源知识", exact: true })
    .click();
  await expect
    .poll(async () => page.evaluate(() => window.__knowledgeModelCalls))
    .toEqual([
      {
        kind: "extract",
        paper_id: "paper-A",
        source_kind: "model_parse",
        source_id: "parse-A",
        allow_network: true,
      },
    ]);
});
