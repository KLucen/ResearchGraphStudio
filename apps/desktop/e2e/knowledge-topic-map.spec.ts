import { expect, test } from "@playwright/test";
import { knowledgePapers, knowledgeReport } from "../src/knowledgeFixtures";

test("topic scope keeps saved relations and can show direct outside context without changing the collection", async ({
  page,
}) => {
  const [inside, outside] = knowledgePapers();
  inside.collection_ids = ["collection-1"];
  const unrelated = {
    ...outside,
    id: "library-C",
    title: "合成论文 C",
    current_version: {
      ...outside.current_version!,
      id: "version-C",
      library_paper_id: "library-C",
    },
  };
  const report = knowledgeReport();
  report.relations?.push({
    ...report.relations[0],
    id: "outside-to-outside",
    target_library_paper_id: "library-C",
    target_version_id: "version-C",
  });
  const layouts = [
    { viewKey: "library:all:all", letters: ["A", "B", "C"] },
    { viewKey: "library:all:collection-1", letters: ["A"] },
  ].map(({ viewKey, letters }) => ({
    view_key: viewKey,
    layout: {
      viewport: { x: 80, y: 80, zoom: 0.75 },
      positions: letters.flatMap((letter, row) => [
        {
          node_id: `paper:library-${letter}`,
          x: 90 + row * 210,
          y: 160,
          pinned: true,
        },
        ...Array.from({ length: 5 }, (_, i) => ({
          node_id: `version:version-${letter}:${letter === "C" ? "B" : letter}-${i}`,
          x: 180 + (i % 3) * 120 + row * 40,
          y: 100 + Math.floor(i / 3) * 180 + row * 70,
          pinned: true,
        })),
      ]),
    },
  }));
  await page.addInitScript(
    ({ papers, report, layouts }) => {
      localStorage.setItem("rgs.knowledge.tab", "map");
      localStorage.setItem("kb-fixture:papers", JSON.stringify(papers));
      localStorage.setItem("kb-fixture:report", JSON.stringify(report));
      for (const layout of layouts)
        localStorage.setItem(
          `kb-fixture:layout:${layout.view_key}`,
          JSON.stringify(layout),
        );
    },
    { papers: [inside, outside, unrelated], report, layouts },
  );
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/e2e/knowledge.html");
  await page
    .getByRole("navigation", { name: "主导航" })
    .getByRole("button", { name: "研究内容知识库" })
    .click();
  await page
    .getByRole("combobox", { name: "专题筛选" })
    .selectOption("collection-1");
  const toggle = page.getByRole("checkbox", { name: "显示专题外联系" });
  const outsideNode = page.locator(
    '.react-flow__node[data-id="paper:library-B"]',
  );
  const edge = page.locator('.react-flow__edge[data-id="cross:relation-1"]');
  await expect(
    page.locator('.react-flow__node[data-id="paper:library-A"]'),
  ).toBeVisible();
  await expect(toggle).not.toBeChecked();
  await expect(outsideNode).toHaveCount(0);
  await expect(edge).toHaveCount(0);
  expect(
    await page.evaluate(() => window.__knowledgeTopicContextReads),
  ).toEqual([]);

  await toggle.check();
  await expect(outsideNode).toHaveClass(/outside-topic/);
  await expect(outsideNode).toHaveAttribute("aria-label", /专题外论文/);
  await expect(edge).toHaveClass(/outside-topic/);
  await expect(page.getByLabel("知识地图图例")).toContainText(
    "长短虚线 · 专题外联系",
  );
  await expect(
    page.locator('.react-flow__node[data-id="paper:library-C"]'),
  ).toHaveCount(0);
  await expect(
    page.locator('.react-flow__node[data-id^="version:version-B:"]'),
  ).toHaveCount(0);
  expect(
    await page.evaluate(() => window.__knowledgeTopicContextReads),
  ).toEqual([{ collectionId: "collection-1", paperIds: ["library-B"] }]);

  await edge.locator(".react-flow__edge-interaction").click({ force: true });
  const detail = page.getByRole("complementary", { name: "知识地图详情" });
  await expect(detail).toContainText("AI 联系分析 · 专题外联系");
  await expect(
    detail.getByRole("button", { name: /打开对应联系汇报/ }),
  ).toBeVisible();
  await toggle.uncheck();
  await expect(edge).toHaveCount(0);
  await expect(outsideNode).toHaveCount(0);
  const layoutWrites = await page.evaluate(async () => {
    // Wait through the layout save debounce so a preview-triggered write cannot slip by.
    await new Promise<void>((done) => window.setTimeout(done, 650));
    return window.__knowledgeLayoutWrites;
  });
  expect(layoutWrites).toBe(0);
  await page.getByRole("combobox", { name: "专题筛选" }).selectOption("");
  await expect(edge).toBeVisible();
  await expect(edge).not.toHaveClass(/outside-topic/);
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);
  expect(
    await page.evaluate(
      () =>
        JSON.parse(localStorage.getItem("kb-fixture:papers")!)[0]
          .collection_ids,
    ),
  ).toEqual(["collection-1"]);
});
