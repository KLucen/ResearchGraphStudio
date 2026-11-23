import { expect, test } from "@playwright/test";

test("activity text waiting and legacy compatibility save and reopen independently from document limits", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/e2e/document-settings.html");
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  const policy = page.getByLabel("文字生成等待方式 1");
  const seconds = page.getByLabel("文字等待超时 1");
  await expect(policy).toHaveValue("activity");
  await expect(seconds).toHaveValue("90");
  await expect(page.getByText(/连接单独等待最多 15 秒/)).toContainText(
    "收到正文或公开 reasoning 增量会重新计时",
  );
  await expect(page.getByText(/纯心跳不算生成/)).toContainText(
    "服务端隐藏的思考无法直接观测",
  );
  await expect(page.getByText(/180 表示 180 秒/)).toContainText(
    "显式继续知识任务会使用当前设置创建后继",
  );
  await policy.selectOption("legacy");
  await expect(
    page.getByText(/即使仍在生成，达到总时限也会结束等待/),
  ).toBeVisible();
  await policy.selectOption("activity");
  await seconds.fill("180");
  await page.getByRole("button", { name: "保存提供商" }).click();
  await expect(
    page.getByText("Synthetic Ark 已保存，模型目录已更新。"),
  ).toBeVisible();
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await expect(policy).toHaveValue("activity");
  await expect(seconds).toHaveValue("180");
  await expect(page.getByLabel("文档等待超时 1")).toHaveValue("600");
  await expect(page.getByLabel("文档解析总时限 1")).toHaveValue("1800");
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await policy.scrollIntoViewIfNeeded();
    const dialog = page.getByRole("dialog", { name: "编辑模型提供商" });
    expect(
      await dialog.evaluate(
        (element) => element.scrollWidth <= element.clientWidth + 1,
      ),
    ).toBe(true);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
  }
  await page.screenshot({
    path: testInfo.outputPath("text-generation-wait-policy.png"),
  });
  await policy.selectOption("legacy");
  await page.getByRole("button", { name: "保存提供商" }).click();
  await expect(
    page.getByText("Synthetic Ark 已保存，模型目录已更新。"),
  ).toBeVisible();
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await expect(policy).toHaveValue("legacy");
  await expect(seconds).toHaveValue("180");
  const calls = await page.evaluate(() => window.__documentSettingsCalls);
  const saved = calls.filter(
    (call) => call.path === "/api/v1/settings/models/fixture-profile/update",
  );
  expect(
    saved.map((call) => (call.body as { parameters: unknown }).parameters),
  ).toEqual([
    expect.objectContaining({
      text_timeout_policy: "activity",
      timeout_seconds: 180,
      document_timeout_seconds: 600,
      document_total_timeout_seconds: 1800,
    }),
    expect.objectContaining({
      text_timeout_policy: "legacy",
      timeout_seconds: 180,
      document_timeout_seconds: 600,
      document_total_timeout_seconds: 1800,
    }),
  ]);
  expect(calls.some((call) => call.path.endsWith("/test"))).toBe(false);
  expect(errors).toEqual([]);
});

test("recommended visual parsing settings save and reopen with independent timeouts", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/e2e/document-settings.html");
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await expect(page.getByLabel("推理强度 1")).toHaveValue("max");
  await page.getByRole("button", { name: "应用推荐解析配置 1" }).click();
  await expect(page.getByLabel("文件传输方式 1")).toHaveValue("chat_images");
  await expect(page.getByLabel("文档等待超时 1")).toHaveValue("600");
  await expect(page.getByLabel("文档解析总时限 1")).toHaveValue("1800");
  await expect(page.getByLabel("推理强度 1")).toHaveValue("none");
  await page.getByRole("button", { name: "保存提供商" }).click();
  await expect(
    page.getByText("Synthetic Ark 已保存，模型目录已更新。"),
  ).toBeVisible();
  const calls = await page.evaluate(() => window.__documentSettingsCalls);
  const saved = calls.find(
    (call) => call.path === "/api/v1/settings/models/fixture-profile/update",
  );
  expect(saved?.body).toMatchObject({
    parameters: {
      timeout_seconds: 90,
      document_timeout_seconds: 600,
      document_total_timeout_seconds: 1800,
      reasoning_effort: "none",
      capabilities: {
        document_input: "image",
        multimodal: true,
        document_transport: "chat_images",
      },
    },
  });
  expect(calls.some((call) => call.path.endsWith("/test"))).toBe(false);
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await expect(page.getByLabel("文件传输方式 1")).toHaveValue("chat_images");
  await expect(page.getByLabel("文档等待超时 1")).toHaveValue("600");
  await page.getByLabel("文档解析总时限 1").fill("120");
  await expect(page.getByRole("button", { name: "保存提供商" })).toBeDisabled();
  await page.getByLabel("文档解析总时限 1").fill("1800");
  await page.getByLabel("文件传输方式 1").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: testInfo.outputPath("document-settings.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
