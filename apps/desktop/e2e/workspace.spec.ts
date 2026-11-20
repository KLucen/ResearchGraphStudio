import { expect, test } from "@playwright/test";

for (const mode of ["local", "dual", "model-only"]) {
  test(`paper workspace keeps three tabs and parsing menu for ${mode}`, async ({
    page,
  }, testInfo) => {
    const errors: string[] = [];
    const externalRequests: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("request", (request) => {
      if (!request.url().startsWith("http://127.0.0.1:1427/"))
        externalRequests.push(request.url());
    });
    await page.setViewportSize({ width: 620, height: 900 });
    await page.goto(
      `/e2e/model-document.html?workspace=${mode}&mode=unselected`,
    );
    const tabs = page.getByRole("navigation", { name: "论文阅读板块" });
    await expect(tabs.getByRole("button")).toHaveText([
      "论文概览",
      "论文精读",
      "论文回答",
    ]);
    const trigger = page.getByRole("button", { name: "论文解析操作" });
    await trigger.click();
    const menu = page.locator(".paper-parsing-options");
    await expect(menu).toBeVisible();
    await expect(menu.getByRole("button")).toHaveCount(4);
    if (mode === "model-only")
      await expect(
        menu.getByRole("button", { name: "查看本地解析内容" }),
      ).toBeDisabled();
    else
      await expect(
        menu.getByRole("button", { name: "查看本地解析内容" }),
      ).toBeEnabled();
    if (mode === "local")
      await expect(
        menu.getByRole("button", { name: "查看模型解析内容" }),
      ).toBeDisabled();
    else
      await expect(
        menu.getByRole("button", { name: "查看模型解析内容" }),
      ).toBeEnabled();
    await page.screenshot({
      path: testInfo.outputPath(`workspace-${mode}.png`),
    });
    await page.keyboard.press("Escape");
    await tabs.getByRole("button", { name: "论文精读" }).click();
    await expect(
      page.getByRole("heading", { name: "全文精读", exact: true }),
    ).toBeVisible();
    if (mode !== "local")
      await expect(
        page.getByText("查看/编辑本次模型解析章节材料"),
      ).toBeVisible();
    await tabs.getByRole("button", { name: "论文回答" }).click();
    if (mode === "model-only") {
      await expect(
        page.getByText(/论文回答需要本地解析建立原文索引/),
      ).toBeVisible();
    } else {
      await page.getByRole("button", { name: "展开文章目录" }).click();
      await page.getByRole("button", { name: "Local source chapter" }).click();
      await expect(
        page.getByRole("region", { name: "局部证据问答" }),
      ).toBeVisible();
      if (mode === "dual")
        await expect(
          page.getByText(/论文回答使用这篇论文的本地解析原文/),
        ).toBeVisible();
    }
    if (mode === "dual") {
      await trigger.click();
      await menu.getByRole("button", { name: "查看本地解析内容" }).click();
      await tabs.getByRole("button", { name: "论文精读" }).click();
      await expect(
        page.getByRole("heading", { name: "全文精读", exact: true }),
      ).toBeVisible();
      await expect(page.getByText("查看/编辑本次模型解析章节材料")).toHaveCount(
        0,
      );
      await trigger.click();
      await menu.getByRole("button", { name: "查看模型解析内容" }).click();
      await expect(
        page.getByText("查看/编辑本次模型解析章节材料"),
      ).toBeVisible();
    }
    expect(
      await page.evaluate(() => window.__modelDocumentGenerationRequests),
    ).toEqual([]);
    expect(errors).toEqual([]);
    expect(externalRequests).toEqual([]);
  });
}
