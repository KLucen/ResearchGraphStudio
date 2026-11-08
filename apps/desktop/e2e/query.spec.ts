import { expect, test, type Page } from "@playwright/test";

const consent = "允许本次将问题与必要来源资料发送给全局 Reasoning 模型";
async function generate(page: Page) {
  await page.getByLabel("研究问题").fill("这些论文的方法在什么条件下有效？");
  await expect(
    page.getByRole("button", { name: "生成有据回答" }),
  ).toBeDisabled();
  await page.getByLabel(consent).check();
  await page.getByRole("button", { name: "生成有据回答" }).click();
}
async function calls(page: Page, ending: string) {
  return page.evaluate(
    (suffix) =>
      window.queryHarness.requests.filter((r) =>
        r.path.split("?")[0].endsWith(suffix),
      ),
    ending,
  );
}

test("real Query renders citations, saves selected knowledge and restores history without model resend", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/e2e/query.html");
  await page.getByLabel("研究问题").fill("有效条件");
  await page.getByText("论文范围 · 全部论文").click();
  await expect(page.getByLabel("合成论文3", { exact: true })).toBeVisible();
  await page.getByLabel("合成论文2", { exact: true }).check();
  await page.getByRole("button", { name: "本地预览来源" }).click();
  await expect(
    page.getByText("合成方法在20 C下有效。", { exact: true }),
  ).toBeVisible();
  expect((await calls(page, "/query/search/page"))[0].body).toMatchObject({
    request: {
      paper_ids: ["paper-2"],
      purpose: "local",
      include_personal: false,
    },
    page_size: 10,
  });
  expect(await calls(page, "/generate")).toHaveLength(0);
  await generate(page);
  await expect(
    page.getByText("作者报告：合成方法在20 C条件下有效。", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/本次模型请求 1\/2 · Token 120/)).toBeVisible();
  expect(await calls(page, "/save")).toHaveLength(0);
  const record = page.getByRole("region", { name: "本次问答记录" });
  await expect(
    record.getByRole("heading", { name: "这些论文的方法在什么条件下有效？" }),
  ).toBeVisible();
  await record
    .getByRole("button", { name: "展开所有引用", exact: true })
    .click();
  await expect(
    record.getByText("已有中文要点：该结果在20 C下报告。"),
  ).toBeVisible();
  await expect(record.getByText("Synthetic result under 20 C.")).toBeVisible();
  await page.getByRole("button", { name: /查看完整证据 · 合成论文1/ }).click();
  const evidence = page.getByRole("dialog", { name: "回答证据" });
  await expect(
    evidence.getByText("Synthetic result under 20 C."),
  ).toBeVisible();
  await expect(evidence.getByText(/PDF 第 2 页/)).toBeVisible();
  await expect(evidence.getByText(/合成离线附件/)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(evidence).not.toBeVisible();
  await page.getByLabel("选择此段保存 · 论文作者主张").check();
  await page.getByRole("button", { name: "保存所选 1 段" }).click();
  await expect(
    page.getByText("阅读知识已保存，可在下方查看，退出重开仍可读取。"),
  ).toBeVisible();
  expect((await calls(page, "/save"))[0].body).toMatchObject({
    selected_passage_refs: ["p1"],
    target_document_id: null,
    kind: "synthesis",
  });
  await page.getByLabel("显示独立衍生图层").check();
  const derived = page.getByRole("region", { name: "阅读综合衍生图层" });
  await expect(derived.locator(".react-flow__node")).toHaveCount(3);
  await expect(derived.locator(".react-flow__edge")).toHaveCount(2);
  await derived.locator('.react-flow__node[data-id="source-claim"]').click();
  await expect(
    page.getByRole("status").filter({ hasText: "图谱定位：claim" }),
  ).toBeVisible();
  await derived.locator('.react-flow__node[data-id="source-chunk"]').click();
  await expect(
    derived.getByRole("complementary", { name: "衍生引用来源" }),
  ).toContainText("原文：合成证据");
  expect(await page.evaluate(() => window.queryHarness.graphFocuses)).toEqual([
    "claim",
  ]);
  await derived.getByRole("button", { name: "查看关联阅读知识" }).click();
  await page.screenshot({
    path: testInfo.outputPath("query-saved-and-derived.png"),
    fullPage: true,
  });
  await page.getByLabel("显示独立衍生图层").uncheck();
  await expect(derived).not.toBeVisible();
  expect(await calls(page, "/generate")).toHaveLength(1);
  expect(await calls(page, "/save")).toHaveLength(1);
  await page.reload();
  await expect(
    page.getByText("作者报告：合成方法在20 C条件下有效。", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /合成阅读综合 阅读综合/ }),
  ).toBeVisible();
  await expect(page.getByLabel(consent)).not.toBeChecked();
  expect(await calls(page, "/generate")).toHaveLength(0);
  expect(await calls(page, "/save")).toHaveLength(0);
  expect(await page.evaluate(() => window.queryHarness.unexpected)).toEqual([]);
  expect(errors).toEqual([]);
});

test("timeout is never resent automatically and manual continuation uses the frozen query", async ({
  page,
}) => {
  await page.goto("/e2e/query.html?mode=timeout");
  await generate(page);
  await expect(page.getByRole("alert")).toContainText("模型请求超时");
  expect(await calls(page, "/generate")).toHaveLength(1);
  await page.reload();
  const button = page.getByRole("button", { name: "继续未完成问答" });
  await expect(button).toBeDisabled();
  expect(await calls(page, "/generate")).toHaveLength(0);
  await page.getByLabel(consent).check();
  await button.click();
  await expect(
    page.getByText("作者报告：合成方法在20 C条件下有效。", { exact: true }),
  ).toBeVisible();
  expect(await calls(page, "/prepare")).toHaveLength(0);
  expect((await calls(page, "/generate"))[0].body).toEqual({
    allow_network: true,
    continue_requested: true,
  });
  expect(await page.evaluate(() => window.queryHarness.unexpected)).toEqual([]);
});

test("saved knowledge opens its complete original question and supports persistent personal annotations and explicit removal without model calls", async ({
  page,
}) => {
  await page.goto("/e2e/query.html");
  await generate(page);
  await expect(
    page.getByText("作者报告：合成方法在20 C条件下有效。", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("选择此段保存 · 论文作者主张").check();
  await page.getByRole("button", { name: "保存所选 1 段" }).click();
  await page
    .getByLabel("个人批注", { exact: true })
    .fill("关注20 C条件，不应外推到其他温度。");
  await page.getByRole("button", { name: "保存个人批注", exact: true }).click();
  await expect(
    page.getByText("个人批注已保存。", { exact: true }),
  ).toBeVisible();
  expect((await calls(page, "/annotation"))[0]).toMatchObject({
    method: "PUT",
    body: {
      annotation: "关注20 C条件，不应外推到其他温度。",
      expected_revision: 0,
    },
  });
  const previousReads = (await calls(page, "/query/runs/query")).length;
  await page.getByRole("button", { name: "查看原问答与引用" }).click();
  const record = page.getByRole("region", { name: "本次问答记录" });
  await expect(record).toBeFocused();
  await expect(
    record.getByRole("heading", {
      name: "这些论文的方法在什么条件下有效？",
      exact: true,
    }),
  ).toBeVisible();
  await record
    .getByRole("button", { name: "展开所有引用", exact: true })
    .click();
  await expect(
    record.getByText("已有中文要点：该结果在20 C下报告。"),
  ).toBeVisible();
  await page.getByRole("button", { name: "查看原问答与引用" }).click();
  await expect(record).toBeFocused();
  expect(await calls(page, "/query/runs/query")).toHaveLength(
    previousReads + 2,
  );
  expect(await calls(page, "/generate")).toHaveLength(1);
  await page.reload();
  await page.getByRole("button", { name: /合成阅读综合 阅读综合/ }).click();
  await expect(
    page.getByRole("textbox", { name: "个人批注", exact: true }),
  ).toHaveValue("关注20 C条件，不应外推到其他温度。");
  await page.getByRole("button", { name: "移除保存内容", exact: true }).click();
  const confirm = page.getByRole("group", { name: "确认移除保存内容" });
  await expect(confirm).toContainText("原问答、论文证据与模型历史仍保留");
  expect(await calls(page, "/remove")).toHaveLength(0);
  await confirm.getByRole("button", { name: "取消移除" }).click();
  await page.getByRole("button", { name: "移除保存内容", exact: true }).click();
  await confirm.getByRole("button", { name: "确认移除", exact: true }).click();
  await expect(
    page.getByText("尚未保存阅读知识。", { exact: true }),
  ).toBeVisible();
  expect((await calls(page, "/remove"))[0]).toMatchObject({
    method: "POST",
    body: { expected_revision: 1 },
  });
  await page
    .getByRole("button", { name: /这些论文的方法在什么条件下有效？ 回答完成/ })
    .click();
  await expect(record).toBeFocused();
  await record
    .getByRole("button", { name: "展开所有引用", exact: true })
    .click();
  await expect(record.getByText("Synthetic result under 20 C.")).toBeVisible();
  expect(await calls(page, "/generate")).toHaveLength(0);
  expect(await calls(page, "/save")).toHaveLength(0);
  expect(await page.evaluate(() => window.queryHarness.unexpected)).toEqual([]);
});

test("running query cancels through unified job API and no task list or source writes are added", async ({
  page,
}) => {
  await page.goto("/e2e/query.html?mode=running");
  await generate(page);
  await page.getByRole("button", { name: "取消本次生成" }).click();
  await expect(
    page.getByRole("heading", { name: "已取消", exact: true }),
  ).toBeVisible();
  expect(await calls(page, "/cancel")).toHaveLength(1);
  expect(await calls(page, "/save")).toHaveLength(0);
  expect(
    await page.evaluate(() =>
      window.queryHarness.requests.some(
        (r) => r.method !== "GET" && /\/graph\//.test(r.path),
      ),
    ),
  ).toBe(false);
  await expect(page.getByText(/完整任务记录集中在/)).toBeVisible();
  expect(await page.evaluate(() => window.queryHarness.unexpected)).toEqual([]);
});

test("full local browsing and grouped answers paginate ten with independent filters and nested citation disclosure", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/e2e/query.html?mode=browse");
  await page.getByLabel("研究问题").fill("关键结论");
  await page.getByRole("button", { name: "本地预览来源" }).click();
  const sources = page.locator(".query-retrieval");
  await expect(
    sources.getByRole("navigation", { name: "来源预览分页" }),
  ).toContainText("共 23 条");
  await expect(sources.locator(":scope > article")).toHaveCount(10);
  await expect(
    sources.getByText("已在默认图谱中", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    sources.getByText("未进入默认图谱 · 仍可检索", { exact: true }).first(),
  ).toBeVisible();
  await sources.getByLabel("来源预览页码").selectOption("3");
  await expect(sources.locator(":scope > article")).toHaveCount(3);
  await expect(sources.getByText("分页来源23", { exact: true })).toBeVisible();
  await sources.getByText("来源论文筛选 · 全部论文", { exact: true }).click();
  await sources.getByLabel("来源论文筛选 · 合成论文2", { exact: true }).check();
  await expect(
    sources.getByRole("navigation", { name: "来源预览分页" }),
  ).toContainText("共 8 条");
  expect((await calls(page, "/query/search/page")).at(-1)?.body).toMatchObject({
    request: { paper_ids: [] },
    display_paper_ids: ["paper-2"],
    page: 1,
  });
  expect(await calls(page, "/generate")).toHaveLength(0);
  await generate(page);
  const answer = page.getByRole("region", { name: "问答结果" });
  await expect(
    answer.getByRole("navigation", { name: "回答段落分页" }),
  ).toContainText("共 14 条");
  await expect(answer.locator(".query-passage")).toHaveCount(10);
  const first = answer.locator(".query-passage").first();
  await expect(first.locator(".query-citation-list")).not.toHaveAttribute(
    "open",
  );
  await first.getByText("引用 · 23 条", { exact: true }).click();
  await expect(first.locator(".query-citation-entry")).toHaveCount(10);
  await expect(first.locator(".query-citation-entry[open]")).toHaveCount(0);
  await first
    .getByRole("button", { name: "展开所有引用", exact: true })
    .click();
  await expect(first.locator(".query-citation-entry[open]")).toHaveCount(10);
  await first.getByLabel("段落p1引用页码").selectOption("3");
  await expect(first.locator(".query-citation-entry[open]")).toHaveCount(3);
  await first
    .getByRole("button", { name: "收起所有引用", exact: true })
    .click();
  await expect(first.locator(".query-citation-list")).not.toHaveAttribute(
    "open",
  );
  await first.getByLabel("选择此段保存 · 论文作者主张").check();
  await answer.getByLabel("回答段落页码").selectOption("2");
  await expect(answer.locator(".query-passage")).toHaveCount(4);
  await expect(
    answer.getByRole("region", { name: "回答分组：跨论文综合" }),
  ).toBeVisible();
  await expect(
    answer.getByText("两篇论文的综合比较。", { exact: true }),
  ).toHaveCount(1);
  await answer
    .locator(".query-passage")
    .first()
    .getByLabel("选择此段保存 · 论文作者主张")
    .check();
  await answer.getByText("回答论文筛选 · 全部论文", { exact: true }).click();
  await answer.getByLabel("回答论文筛选 · 合成论文2", { exact: true }).check();
  await expect(answer.locator(".query-passage")).toHaveCount(2);
  await expect(
    answer.getByRole("button", { name: "保存所选 2 段", exact: true }),
  ).toBeVisible();
  expect((await calls(page, "/prepare"))[0].body).toMatchObject({
    paper_ids: [],
    limit: 20,
  });
  expect(await calls(page, "/generate")).toHaveLength(1);
  expect(await calls(page, "/save")).toHaveLength(0);
  await page.screenshot({
    path: testInfo.outputPath("query-full-browse-grouped.png"),
    fullPage: true,
  });
  expect(await page.evaluate(() => window.queryHarness.unexpected)).toEqual([]);
  expect(errors).toEqual([]);
});
