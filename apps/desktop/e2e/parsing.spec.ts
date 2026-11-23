import { expect, test } from "@playwright/test";
test("parsing defaults local and later model dialog follows the viewport", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 620, height: 850 });
  await page.goto("/e2e/parsing.html");
  await expect(
    page.getByRole("radio", { name: "本地解析（不调用模型）" }),
  ).toBeChecked();
  await expect(
    page.getByRole("checkbox", { name: "生成论文概览" }),
  ).toHaveCount(0);
  await page.getByRole("radio", { name: "模型解析 PDF" }).check();
  await expect(
    page.getByText("论文解析模型：Synthetic PDF · file-fixture"),
  ).toBeVisible();
  await expect(page.getByText(/输入方式：将 PDF 页面渲染成图片/)).toContainText(
    "单请求响应等待上限 600 秒，单请求总时限 1800 秒",
  );
  await page.getByRole("button", { name: "更多解析操作" }).click();
  await page.getByRole("button", { name: "本地解析 / 重试" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Synthetic local read failure",
  );
  await expect(page.getByLabel("文档请求状态")).toHaveCount(0);
  await page.getByRole("button", { name: "更多解析操作" }).click();
  await page.getByRole("button", { name: "使用模型重新解析" }).click();
  const dialog = page.getByRole("dialog", { name: "重新解析论文" });
  await expect(dialog).toBeVisible();
  const box = await dialog.boundingBox();
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.y + box!.height).toBeLessThanOrEqual(850);
  await expect(
    dialog.getByRole("button", { name: "确认模型解析" }),
  ).toBeDisabled();
  await dialog
    .getByRole("checkbox", {
      name: "允许将所选 PDF 发送给已配置的论文解析模型",
    })
    .check();
  await dialog.getByRole("button", { name: "确认模型解析" }).click();
  await expect(dialog).toHaveCount(0);
  expect(await page.evaluate(() => window.__parseCalls)).toEqual([
    { mode: "local" },
    {
      mode: "model",
      post_import_plan: {
        parse: true,
        overview: false,
        reading: false,
        translation_mode: "none",
        modality: "auto",
        extract_formulas: true,
        extract_tables: true,
        allow_network: true,
        provider_profile_id: null,
        document_batching: true,
        pages_per_batch: 5,
        allow_format_repair: false,
        allow_boundary_review: true,
      },
    },
  ]);
  await page.screenshot({ path: testInfo.outputPath("parsing-controls.png") });
  expect(errors).toEqual([]);
});

test("batch parsing defaults five pages and requires fresh consent for optional paid repair", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 620, height: 900 });
  await page.goto("/e2e/parsing.html");
  await page.getByRole("button", { name: "更多解析操作" }).click();
  await page.getByRole("button", { name: "使用模型重新解析" }).click();
  const dialog = page.getByRole("dialog", { name: "重新解析论文" });
  await expect(
    dialog.getByRole("checkbox", { name: "按页分批解析（顺序执行）" }),
  ).toBeChecked();
  const pages = dialog.getByRole("combobox", {
    name: "每批最多页数（含共享页）",
  });
  await expect(pages).toHaveValue("5");
  await expect(pages.getByRole("option")).toHaveCount(7);
  const repair = dialog.getByRole("checkbox", {
    name: "允许契约校验失败时修复本批格式（可能额外收费）",
  });
  const consent = dialog.getByRole("checkbox", {
    name: "允许将所选 PDF 发送给已配置的论文解析模型",
  });
  await expect(repair).not.toBeChecked();
  await expect(consent).not.toBeChecked();
  await expect(dialog.getByLabel("解析请求预算")).toContainText(
    "抽取 B 次，边界检查最多 B−1 次，格式修复 0 次",
  );
  await consent.check();
  await repair.check();
  await expect(consent).not.toBeChecked();
  await expect(
    dialog.getByRole("button", { name: "确认模型解析" }),
  ).toBeDisabled();
  await expect(dialog.getByText(/每个失败批次最多额外 1 次 API/)).toContainText(
    "仅发送该批响应、契约和错误，不重传 PDF",
  );
  await expect(dialog.getByLabel("解析请求预算")).toContainText(
    "格式修复最多 B 次",
  );
  await consent.check();
  await pages.selectOption("4");
  await expect(consent).not.toBeChecked();
  expect(await page.evaluate(() => window.__parseCalls)).toEqual([]);
  await dialog
    .getByText(/每个失败批次最多额外 1 次 API/)
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: testInfo.outputPath("batch-consent-narrow.png"),
  });
  await consent.check();
  await dialog.getByRole("button", { name: "确认模型解析" }).click();
  expect(await page.evaluate(() => window.__parseCalls)).toEqual([
    {
      mode: "model",
      post_import_plan: expect.objectContaining({
        document_batching: true,
        pages_per_batch: 4,
        allow_format_repair: true,
        allow_boundary_review: true,
        allow_network: true,
      }),
    },
  ]);
  expect(errors).toEqual([]);
});

test("workspace shows active model parse name while job history keeps safe batch diagnostics", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  const externalRequests: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (!request.url().startsWith("http://127.0.0.1:1427/"))
      externalRequests.push(request.url());
  });
  await page.goto("/e2e/parsing.html?batch=1");
  await page.getByRole("button", { name: "更多解析操作" }).click();
  await page.getByRole("button", { name: "使用模型重新解析" }).click();
  const dialog = page.getByRole("dialog", { name: "重新解析论文" });
  await dialog
    .getByRole("checkbox", {
      name: "允许将所选 PDF 发送给已配置的论文解析模型",
    })
    .check();
  await dialog.getByRole("button", { name: "确认模型解析" }).click();
  const workspace = page.getByRole("region", { name: "论文解析管理" });
  const history = page.getByRole("region", { name: "任务记录" });
  await expect(workspace.getByRole("status")).toHaveText(
    "任务进行中：模型章节解析",
  );
  await expect(workspace.getByLabel("文档批次状态")).toHaveCount(0);
  await expect(workspace.getByLabel("文档校验位置")).toHaveCount(0);
  await expect(history.getByLabel("文档批次状态")).toBeHidden();
  await history.getByText("诊断详情", { exact: true }).click();
  await expect(history.getByLabel("文档批次状态")).toHaveText(
    "第 2 / 4 批 · 原始第 5–9 页 · 已校验 1 / 4 批 · 已发送 3 / 11 次请求 · 格式修复已用 1 次 · 边界复核 0 / 3 · 等待当前批次响应",
  );
  await expect(history.getByLabel("文档校验位置")).toHaveText(
    "校验位置：segments[3].kind（literal_error）",
  );
  await expect(page.getByLabel("文档请求状态")).toHaveCount(0);
  await expect(
    page.getByText(/PRIVATE_SYNTHETIC_RESPONSE|private fixture/),
  ).toHaveCount(0);
  await expect(page.getByRole("progressbar")).toHaveCount(0);
  await page.getByLabel("文档批次状态").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: testInfo.outputPath("batch-task-diagnostics.png"),
  });
  expect(errors).toEqual([]);
  expect(externalRequests).toEqual([]);
});

test("parsing actions stay inside narrow viewport and dismisses with Escape", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/e2e/parsing.html?local-only=1");
  const trigger = page.getByRole("button", { name: "更多解析操作" });
  await expect(
    page
      .getByRole("group", { name: "论文阅读来源" })
      .getByText("本地解析", { exact: true }),
  ).toBeVisible();
  await trigger.click();
  const menu = page.locator(".paper-parsing-options");
  await expect(menu).toBeVisible();
  const bounds = await menu.boundingBox();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
  expect(bounds!.y).toBeGreaterThanOrEqual(0);
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(844);
  await expect(menu.getByRole("button")).toHaveCount(2);
  await page.screenshot({ path: testInfo.outputPath("parsing-menu-390.png") });
  await page.keyboard.press("Tab");
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(await page.evaluate(() => window.__parseCalls)).toEqual([]);
});
