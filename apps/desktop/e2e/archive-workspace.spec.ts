import { expect, test } from "@playwright/test";
import type { Job } from "../src/api";

test("task history stages a task, restores it, and permanently clears it only from Archives", async ({
  page,
}) => {
  const job: Job = {
    id: "archivable-task",
    kind: "pdf_import",
    project_id: null,
    status: "succeeded",
    stage: "complete",
    attempt: 1,
    error: null,
    result: { title: "匿名导入任务" },
    created_at: "2026-11-22T00:00:00Z",
    updated_at: "2026-11-22T00:00:01Z",
  };
  await page.addInitScript(
    (job) => localStorage.setItem("kb-fixture:jobs", JSON.stringify([job])),
    job,
  );
  await page.goto("/e2e/knowledge.html");
  const nav = page.getByRole("navigation", { name: "主导航" });
  const history = nav.getByRole("button", { name: "任务记录" });
  const archives = nav.getByRole("button", { name: "归档管理" });
  const row = page.locator(`#job-${job.id}`);
  await history.click();
  await row.click({ button: "right" });
  await page.getByRole("menuitem", { name: "归档任务" }).click();
  await expect(row).toHaveCount(0);
  await archives.click();
  const archived = page
    .getByRole("listitem")
    .filter({ hasText: "匿名导入任务" });
  await expect(archived).toBeVisible();
  await archived.getByRole("button", { name: "恢复" }).click();
  await expect(archived).toHaveCount(0);
  await history.click();
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "归档任务" }).click();
  await expect(row).toHaveCount(0);
  await archives.click();
  await page.getByLabel("内容类型").selectOption("job");
  const more = archived.getByRole("button", { name: "更多操作" });
  const dialog = page.getByRole("dialog", { name: "彻底清除归档" });
  await more.click();
  await page.getByRole("menuitem", { name: "彻底清除" }).click();
  await expect(dialog.getByRole("button", { name: "取消" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(archived).toBeVisible();
  await expect(more).toBeFocused();
  await more.click();
  await page.getByRole("menuitem", { name: "彻底清除" }).click();
  await dialog.getByRole("button", { name: "彻底清除" }).click();
  await expect(archived).toHaveCount(0);
  await history.click();
  await expect(row).toHaveCount(0);
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);
});
