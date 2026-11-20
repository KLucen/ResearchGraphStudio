import { expect, test } from "@playwright/test";

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
