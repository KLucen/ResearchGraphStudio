import { expect, test } from "@playwright/test";
import { knowledgePapers } from "../src/knowledgeFixtures";

test("dense knowledge map shows readable circular labels and preserves its layout across languages", async ({
  page,
}, testInfo) => {
  const papers = knowledgePapers();
  const graph = papers[0].current_version!.content.graph!;
  const concept = graph.nodes.find((node) => node.id === "A-1")!;
  const chinese = "合成研究方法在多个任务与环境下的适用范围";
  const english =
    "Scope of a synthetic method across multiple tasks and environments";
  concept.label_zh = chinese;
  concept.label_en = english;
  for (let index = 0; index < 19; index++) {
    graph.nodes.push({
      ...concept,
      id: `dense-${index}`,
      label_zh: `${chinese} ${index}`,
      label_en: `${english} ${index}`,
    });
  }
  const layout = {
    view_key: "library:all:all",
    layout: {
      viewport: { x: 48, y: 36, zoom: 0.92 },
      positions: [
        { node_id: "paper:library-A", x: 36, y: 170, pinned: true },
        { node_id: "paper:library-B", x: 540, y: 170, pinned: true },
        ...graph.nodes
          .filter((node) => node.type !== "PAPER")
          .map((node, index) => ({
            node_id: `version:version-A:${node.id}`,
            x: 152 + (index % 6) * 48,
            y: 56 + Math.floor(index / 6) * 74,
            pinned: true,
          })),
        ...papers[1]
          .current_version!.content.graph!.nodes.filter(
            (node) => node.type !== "PAPER",
          )
          .map((node, index) => ({
            node_id: `version:version-B:${node.id}`,
            x: 600,
            y: 50 + index * 65,
            pinned: true,
          })),
      ],
    },
  };
  await page.addInitScript(
    ({ papers, layout }) => {
      localStorage.setItem("kb-fixture:papers", JSON.stringify(papers));
      localStorage.setItem(
        `kb-fixture:layout:${layout.view_key}`,
        JSON.stringify(layout),
      );
    },
    { papers, layout },
  );
  const openMap = async () => {
    await page
      .getByRole("button", { name: "研究内容知识库", exact: true })
      .click();
    await page.getByRole("button", { name: "知识地图", exact: true }).click();
  };
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/e2e/knowledge.html");
  await openMap();
  await page.getByLabel("展开论文").selectOption("library-A");
  const language = page.getByLabel("节点语言");
  const nodes = page.locator(".knowledge-graph-view .react-flow__node");
  const node = page.locator('[data-id="version:version-A:A-1"]');
  const captions = page.locator(".knowledge-dot-label");
  const caption = node.locator(".knowledge-dot-label");
  const camera = page.locator(".knowledge-graph-view .react-flow__viewport");
  const detail = page.getByRole("complementary", { name: "知识地图详情" });

  await expect(nodes).toHaveCount(26);
  await expect(language).toHaveValue("zh");
  await node.click();
  await expect(caption).toHaveText(chinese);
  await expect(detail.getByRole("heading", { name: chinese })).toBeVisible();
  expect(
    await node.evaluate((element) => {
      const style = getComputedStyle(element);
      return (
        style.width === style.height &&
        parseFloat(style.borderTopLeftRadius) >= 10
      );
    }),
  ).toBe(true);
  await expect(caption.locator(":scope > span").first()).toHaveCSS(
    "white-space",
    "nowrap",
  );
  const originalCamera = await camera.evaluate(
    (element) => getComputedStyle(element).transform,
  );
  const originalPosition = await node.evaluate(
    (element) => getComputedStyle(element).transform,
  );

  await language.selectOption("en");
  await expect(caption).toHaveText(english);
  await expect(detail.getByRole("heading", { name: english })).toBeVisible();
  await language.selectOption("both");
  await expect(caption.locator(":scope > span")).toHaveText([chinese, english]);
  await expect(detail.getByText(english, { exact: true })).toBeVisible();
  await expect(camera).toHaveCSS("transform", originalCamera);
  await expect(node).toHaveCSS("transform", originalPosition);
  await expect(node).toHaveClass(/pinned/);

  expect(await captions.count()).toBeLessThan(26);
  expect(
    await captions.evaluateAll((elements) => {
      const boxes = elements.map((element) => element.getBoundingClientRect());
      return boxes.every((a, index) =>
        boxes
          .slice(index + 1)
          .every(
            (b) =>
              a.right <= b.left + 1 ||
              b.right <= a.left + 1 ||
              a.bottom <= b.top + 1 ||
              b.bottom <= a.top + 1,
          ),
      );
    }),
  ).toBe(true);
  await page
    .locator(".knowledge-map")
    .screenshot({ path: testInfo.outputPath("knowledge-map-dense.png") });
  expect(await page.evaluate(() => window.__knowledgeLayoutWrites)).toBe(0);
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);

  await page.reload();
  await openMap();
  await expect(language).toHaveValue("both");
  await expect(camera).toHaveCSS("transform", originalCamera);
  await expect(
    page.locator('[data-id="paper:library-B"]'),
  ).toHaveAccessibleName(/合成论文 B/);
});
