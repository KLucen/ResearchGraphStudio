import { expect, test } from "@playwright/test";

test("workspace keeps search, graph and per-paper options in order and loads every paper page", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/e2e/workspace.html");
  const search = page.getByRole("region", { name: "图谱搜索与筛选" });
  const panel = page.getByRole("region", { name: "知识图谱展示" });
  const options = page.getByRole("region", { name: "论文候选与建图选项" });
  await expect(search).toBeVisible();
  await expect(panel).toBeVisible();
  await expect(options.getByRole("heading", { level: 4 })).toHaveCount(3);
  await expect(page.locator(".react-flow__node")).toHaveCount(12);
  const ordered = await page.evaluate(() => {
    const search = document.querySelector('[aria-label="图谱搜索与筛选"]')!;
    const graph = document.querySelector(".graph-panel")!;
    const options = document.querySelector(
      '[aria-label="论文候选与建图选项"]',
    )!;
    return (
      Boolean(
        search.compareDocumentPosition(graph) &
        Node.DOCUMENT_POSITION_FOLLOWING,
      ) &&
      Boolean(
        graph.compareDocumentPosition(options) &
        Node.DOCUMENT_POSITION_FOLLOWING,
      )
    );
  });
  expect(ordered).toBe(true);
  await expect(search.getByLabel("论文筛选").locator("option")).toHaveCount(4);
  await expect(
    panel.getByRole("complementary", { name: "图谱节点类型说明" }),
  ).toBeVisible();
  await expect(panel.getByRole("button", { name: "适应图谱" })).toBeVisible();
  await expect(panel.getByText("本页 3 篇论文 · 12 个节点")).toBeVisible();
  const paperRequests = await page.evaluate(() =>
    window.workspaceHarness.requests.filter((request) =>
      request.path.includes("/papers?"),
    ),
  );
  expect(
    paperRequests.some((request) => request.path.includes("cursor=2")),
  ).toBe(true);
  expect(
    await page.evaluate(() =>
      window.workspaceHarness.requests.some((request) =>
        /\/projects\/[^/]+\/jobs/.test(request.path),
      ),
    ),
  ).toBe(false);
  expect(errors).toEqual([]);
});

test("fullscreen grows the real canvas, retains DOM and coordinates, then Escape restores focus and scrolling", async ({
  page,
}, testInfo) => {
  await page.goto("/e2e/workspace.html");
  const canvas = page.locator(".projection-canvas");
  const node = page.locator('.react-flow__node[data-id="paper-1-Claim"]');
  await expect(node).toBeVisible();
  await expect(node).toHaveClass(/pinned/);
  const before = await canvas.boundingBox();
  if (!before) throw new Error("Synthetic workspace canvas did not render");
  await page.screenshot({ path: testInfo.outputPath("workspace-normal.png") });
  const coordinates = await node.evaluate((element) => {
    window.workspaceHarness.retainedNode = element;
    return (element as HTMLElement).style.transform;
  });
  const requestsBefore = await page.evaluate(
    () =>
      window.workspaceHarness.requests.filter(
        (request) =>
          request.method === "POST" && request.path.endsWith("/layout"),
      ).length,
  );
  const trigger = page.getByRole("button", { name: "全屏显示图谱" });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "知识图谱展示" });
  await expect(dialog).toBeVisible();
  await expect(page.locator("body")).toHaveCSS("overflow", "hidden");
  await expect
    .poll(async () => (await canvas.boundingBox())?.width ?? 0)
    .toBeGreaterThan(before.width + 60);
  await expect
    .poll(async () => (await canvas.boundingBox())?.height ?? 0)
    .toBeGreaterThan(before.height + 30);
  await testInfo.attach("canvas-size", {
    body: JSON.stringify({
      normal: before,
      fullscreen: await canvas.boundingBox(),
    }),
    contentType: "application/json",
  });
  await page.screenshot({
    path: testInfo.outputPath("workspace-fullscreen.png"),
  });
  expect(
    await node.evaluate(
      (element) => element === window.workspaceHarness.retainedNode,
    ),
  ).toBe(true);
  expect(
    await node.evaluate((element) => (element as HTMLElement).style.transform),
  ).toBe(coordinates);
  await expect(node).toHaveClass(/pinned/);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");
  expect(
    await node.evaluate(
      (element) => element === window.workspaceHarness.retainedNode,
    ),
  ).toBe(true);
  expect(
    await node.evaluate((element) => (element as HTMLElement).style.transform),
  ).toBe(coordinates);
  await page.waitForTimeout(900);
  expect(
    await page.evaluate(
      () =>
        window.workspaceHarness.requests.filter(
          (request) =>
            request.method === "POST" && request.path.endsWith("/layout"),
        ).length,
    ),
  ).toBe(requestsBefore);
});

test("paper filtering returns all three papers and bottom options do not change the graph filter", async ({
  page,
}) => {
  await page.goto("/e2e/workspace.html");
  const filter = page.getByLabel("论文筛选");
  const nodes = page.locator(".react-flow__node");
  await expect(filter.locator("option")).toHaveCount(4);
  await expect(nodes).toHaveCount(12);
  await filter.selectOption("paper-2");
  await expect(nodes).toHaveCount(4);
  await expect(page.getByText("本页 1 篇论文 · 4 个节点")).toBeVisible();
  const options = page.getByRole("region", { name: "论文候选与建图选项" });
  const lastPaper = options.locator("article").filter({
    has: page.getByRole("heading", { name: "合成论文三", exact: true }),
  });
  await lastPaper
    .getByRole("button", { name: "查看已保存候选与建图选项" })
    .click();
  await expect(
    lastPaper.getByText("结论选择与全部候选", { exact: false }),
  ).toBeVisible();
  await expect(filter).toHaveValue("paper-2");
  await expect(nodes).toHaveCount(4);
  const projections = await page.evaluate(() =>
    window.workspaceHarness.requests.filter((request) =>
      request.path.endsWith("/projection"),
    ),
  );
  expect(projections.at(-1)?.body?.paper_id).toBe("paper-2");
  expect(
    await page.evaluate(() =>
      window.workspaceHarness.requests.some((request) =>
        /\/projects\/[^/]+\/jobs/.test(request.path),
      ),
    ),
  ).toBe(false);
  await filter.selectOption("");
  await expect(nodes).toHaveCount(12);
  await expect(page.getByText("本页 3 篇论文 · 12 个节点")).toBeVisible();
  const renderedPapers = await nodes.evaluateAll((elements) =>
    elements
      .filter((element) =>
        ["paper-1", "paper-2", "paper-3"].includes(
          element.getAttribute("data-id") ?? "",
        ),
      )
      .map((element) => element.getAttribute("data-id")),
  );
  expect(renderedPapers.sort()).toEqual(["paper-1", "paper-2", "paper-3"]);
});

test("saved drag, pin and camera survive a real workspace reload without resaving every frame", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/e2e/workspace.html");
  const node = page.locator('.react-flow__node[data-id="paper-1-Method"]');
  await expect(node).toBeVisible();
  await node.dblclick();
  await expect(node).toHaveClass(/pinned/);
  const start = await node.boundingBox();
  if (!start) throw new Error("Synthetic saved-layout node did not render");
  await page.mouse.move(start.x + 9, start.y + 9);
  await page.mouse.down();
  await page.mouse.move(start.x + 129, start.y + 59, { steps: 20 });
  await page.mouse.up();
  await page.mouse.wheel(0, -160);
  await expect(page.getByText(/布局已同步/)).toBeVisible();
  await page.waitForTimeout(3000);
  await expect(page.getByText(/布局已同步/)).toBeVisible();
  const persisted = await page.evaluate(() =>
    JSON.parse(
      sessionStorage.getItem(
        "researchgraph.synthetic-workspace.server-layout",
      )!,
    ),
  );
  const savedNode = persisted.positions.find(
    (position: { node_id: string }) => position.node_id === "paper-1-Method",
  );
  expect(savedNode).toMatchObject({ pinned: true });
  expect(savedNode.x).not.toBe(90);
  expect(savedNode.y).not.toBe(265);
  expect(persisted.zoom).toBeGreaterThan(1);
  const posts = await page.evaluate(() =>
    window.workspaceHarness.requests.filter(
      (request) =>
        request.method === "POST" && request.path.endsWith("/layout"),
    ),
  );
  expect(posts.length).toBeGreaterThan(0);
  expect(posts.length).toBeLessThan(8);
  expect(
    await page.evaluate(() =>
      localStorage.getItem("researchgraph.layout-draft.synthetic-workspace"),
    ),
  ).toBeNull();
  const coordinates = await node.evaluate(
    (element) => (element as HTMLElement).style.transform,
  );
  const camera = await page
    .locator(".react-flow__viewport")
    .getAttribute("style");
  await page.reload();
  await expect(node).toBeVisible();
  await expect(node).toHaveClass(/pinned/);
  expect(
    await node.evaluate((element) => (element as HTMLElement).style.transform),
  ).toBe(coordinates);
  expect(
    await page.locator(".react-flow__viewport").getAttribute("style"),
  ).toBe(camera);
  await page.waitForTimeout(1000);
  expect(
    await page.evaluate(() =>
      window.workspaceHarness.requests.filter(
        (request) =>
          request.method === "POST" && request.path.endsWith("/layout"),
      ),
    ),
  ).toEqual([]);
  expect(errors).toEqual([]);
});
