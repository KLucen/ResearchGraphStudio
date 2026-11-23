import { expect, test } from "@playwright/test";
import { knowledgePapers } from "../src/knowledgeFixtures";

test("creates, edits, filters, archives and restores a topic without model requests", async ({
  page,
}) => {
  await page.goto("/e2e/knowledge.html");
  await page
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  await page.getByRole("button", { name: "新建专题", exact: true }).click();
  const manage = page.getByRole("dialog", { name: "专题管理" });
  await manage.getByLabel("专题名称").fill("数据来源");
  await manage.getByLabel("专题说明（可选）").fill("按数据来源整理");
  await manage.getByRole("button", { name: "创建专题" }).click();
  await expect(manage.getByRole("heading", { name: "数据来源" })).toBeVisible();
  await expect(manage.getByText("按数据来源整理")).toBeVisible();

  await manage.getByRole("button", { name: "编辑专题" }).click();
  await manage.getByLabel("专题名称").fill("定性数据来源");
  await manage.getByLabel("专题说明（可选）").fill("定性材料及其出处");
  await manage.getByRole("button", { name: "保存专题" }).click();
  await expect(
    manage.getByRole("heading", { name: "定性数据来源" }),
  ).toBeVisible();
  await expect(manage.getByText("定性材料及其出处")).toBeVisible();
  await manage.getByRole("button", { name: "浏览专题" }).click();
  await expect(manage).toBeHidden();
  await expect(
    page.getByLabel("专题筛选").locator("option:checked"),
  ).toHaveText("定性数据来源");

  await page.getByRole("button", { name: "专题管理", exact: true }).click();
  await manage.getByRole("button", { name: "归档专题", exact: true }).click();
  await manage.getByRole("button", { name: "确认归档专题" }).click();
  await expect(
    manage.getByRole("button", { name: "定性数据来源" }),
  ).toHaveCount(0);
  await manage.getByRole("button", { name: "关闭" }).click();
  await expect(page.getByLabel("专题筛选")).toHaveValue("");
  await page.getByRole("button", { name: "归档管理", exact: true }).click();
  await expect(page.getByText("定性数据来源", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "恢复", exact: true }).click();
  await page
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  await expect(page.getByLabel("专题筛选").locator("option")).toContainText([
    "全部专题",
    "方法比较",
    "定性数据来源",
  ]);
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);
});

test("assigns paged selections and moves only the chosen topic membership", async ({
  page,
}) => {
  const contributions = knowledgePapers();
  const [a, b] = contributions;
  const topics = [
    {
      id: "source",
      name: "来源主题",
      description: "",
      created_at: "2026-11-24",
    },
    {
      id: "target",
      name: "目标主题",
      description: "",
      created_at: "2026-11-24",
    },
    {
      id: "retained",
      name: "保留主题",
      description: "",
      created_at: "2026-11-24",
    },
  ];
  await page.addInitScript(
    ({ a, b, topics }) => {
      localStorage.setItem("kb-fixture:collections", JSON.stringify(topics));
      const extras = Array.from({ length: 18 }, (_, index) => ({
        ...b,
        id: `paper-${index}`,
        title: `可归类论著 ${String(index + 1).padStart(2, "0")}`,
        collection_ids: [],
      }));
      localStorage.setItem(
        "kb-fixture:papers",
        JSON.stringify([
          { ...a, collection_ids: ["source", "retained"] },
          { ...b, collection_ids: [] },
          ...extras,
        ]),
      );
    },
    { a, b, topics },
  );
  await page.goto("/e2e/knowledge.html");
  await page
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  await page.getByRole("button", { name: "专题管理", exact: true }).click();
  const manage = page.getByRole("dialog", { name: "专题管理" });
  await manage.getByRole("button", { name: "目标主题", exact: true }).click();
  await manage.getByRole("button", { name: "添加已有论文" }).click();
  await manage.getByRole("checkbox", { name: b.title, exact: true }).check();
  await manage.getByRole("button", { name: "下一页", exact: true }).click();
  await manage
    .getByRole("checkbox", { name: "可归类论著 18", exact: true })
    .check();
  await expect(manage.getByText("已选 2 篇", { exact: true })).toBeVisible();
  await manage.getByRole("button", { name: "添加所选论文" }).click();
  await expect(manage.getByText(/添加 2 条归属/)).toBeVisible();

  await manage.getByRole("button", { name: "从其他专题移入" }).click();
  await manage.getByLabel("来源专题").selectOption("source");
  await manage.getByRole("checkbox", { name: a.title, exact: true }).check();
  await manage.getByRole("button", { name: "移动所选论文" }).click();
  await expect(manage.getByText(/添加 1 条归属 · 移除 1 条归属/)).toBeVisible();
  await manage.getByRole("button", { name: "浏览专题" }).click();
  await page.getByRole("button", { name: "论文知识", exact: true }).click();
  const row = page.getByRole("group", { name: a.title, exact: true });
  await expect(row.getByText(/专题 · 目标主题、保留主题/)).toBeVisible();
  await row.getByRole("button", { name: "管理专题", exact: true }).click();
  const assign = page.getByRole("dialog", { name: "管理论文专题" });
  await assign.getByLabel("归类操作").selectOption("remove");
  await assign.getByLabel("要移出的专题").selectOption("target");
  await assign.getByRole("button", { name: "应用归类" }).click();
  await expect(assign).toBeHidden();
  await expect(row).toHaveCount(0);

  const stored = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("kb-fixture:papers") ?? "[]"),
  );
  expect(stored.find((paper: { id: string }) => paper.id === a.id)).toEqual({
    ...a,
    collection_ids: ["retained"],
  });
  expect(stored.find((paper: { id: string }) => paper.id === b.id)).toEqual({
    ...b,
    collection_ids: ["target"],
  });
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);
});
