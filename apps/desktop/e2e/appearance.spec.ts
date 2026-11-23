import { expect, test } from "@playwright/test";

test("theme follows the system or a remembered choice without changing the study", async ({
  page,
}, testInfo) => {
  await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  await page.goto("/e2e/knowledge.html");
  const root = page.locator("html");
  const nav = page.getByRole("navigation", { name: "主导航" });
  const openSettings = () =>
    page.getByRole("button", { name: "设置与诊断", exact: true }).click();
  await expect(root).toHaveAttribute("data-theme", "dark");
  await openSettings();
  await expect(page.getByRole("radio", { name: "跟随系统" })).toBeChecked();
  await page.getByRole("radio", { name: "浅色" }).check();
  await expect(root).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(root).toHaveAttribute("data-theme", "light");
  await openSettings();
  await expect(page.getByRole("radio", { name: "浅色" })).toBeChecked();
  await page.getByRole("radio", { name: "深色" }).check();
  await page.emulateMedia({ colorScheme: "light" });
  await expect(root).toHaveAttribute("data-theme", "dark");
  await page.getByRole("radio", { name: "跟随系统" }).check();
  await expect(root).toHaveAttribute("data-theme", "light");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(root).toHaveAttribute("data-theme", "dark");
  await page.getByRole("radio", { name: "深色" }).check();
  await nav
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  await page.getByRole("button", { name: "知识地图", exact: true }).click();
  await expect(page.locator(".react-flow")).toHaveClass(/dark/);
  const kinds = page.getByRole("group", { name: "显示类型" });
  await expect(kinds.getByRole("checkbox")).toHaveCount(5);
  const controls = await kinds.boundingBox();
  expect(controls?.height).toBeLessThanOrEqual(58);
  const background = await root.evaluate(
    (element) => getComputedStyle(element).backgroundColor,
  );
  expect(background).toBe("rgb(23, 29, 26)");
  await page.screenshot({
    path: testInfo.outputPath("dark-knowledge-map.png"),
  });
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);
});

test("the production HTML resolves a stored preference before React", async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.addInitScript(() =>
    localStorage.setItem("rgs.appearance", "dark"),
  );
  await page.route("**/src/main.tsx", (route) => route.abort());
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-appearance", "dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("#root")).toBeEmpty();
});
