import { test, expect } from "@playwright/test";
declare global {
  interface Window {
    hoverEvents: string[];
  }
}

test("real renderer keeps hover stable and all nodes visible throughout dragging", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/e2e/graph.html");
  const dots = page.locator(".react-flow__node");
  await expect(dots).toHaveCount(12);
  const first = dots.filter({ hasText: "合成节点 0" });
  await expect(first).toBeVisible();
  await page.evaluate(() => {
    const dot = document.querySelector('.react-flow__node[data-id="n0"]')!;
    window.hoverEvents = [];
    for (const type of ["mouseenter", "mouseleave"])
      dot.addEventListener(type, () => window.hoverEvents.push(type));
  });
  await first.hover();
  const hiddenFrames = await page.evaluate(async () => {
    let missing = 0;
    for (let i = 0; i < 60; i++) {
      await new Promise(requestAnimationFrame);
      if (
        [...document.querySelectorAll(".react-flow__node")].some(
          (n) => getComputedStyle(n).visibility !== "visible",
        )
      )
        missing++;
    }
    return missing;
  });
  expect(hiddenFrames).toBe(0);
  await page.waitForTimeout(1200);
  expect(await page.evaluate(() => window.hoverEvents)).toEqual(["mouseenter"]);
  const start = await first.boundingBox();
  if (!start) throw new Error("Missing graph dot");
  const before = await dots.nth(1).getAttribute("style");
  await page.mouse.down();
  for (let i = 1; i <= 40; i++) {
    await page.mouse.move(start.x + 9 + i * 3, start.y + 9 + i * 2);
    await page.waitForTimeout(16);
    const state = await dots.evaluateAll((nodes) =>
      nodes.map((n) => ({
        visibility: getComputedStyle(n).visibility,
        transform: getComputedStyle(n).transform,
        x: n.getBoundingClientRect().x,
        y: n.getBoundingClientRect().y,
      })),
    );
    expect(state).toHaveLength(12);
    expect(
      state.every(
        (n) =>
          n.visibility === "visible" &&
          !/NaN|Infinity/.test(n.transform) &&
          Number.isFinite(n.x) &&
          Number.isFinite(n.y),
      ),
    ).toBe(true);
  }
  await page.mouse.up();
  expect(await dots.nth(1).getAttribute("style")).not.toBe(before);
  await page.waitForTimeout(2500);
  await page.getByRole("button", { name: "模拟轮询" }).click();
  await expect(dots).toHaveCount(12);
  expect(errors).toEqual([]);
});

test("pin, zoom, fast drag and container resize preserve the real renderer", async ({
  page,
}) => {
  await page.goto("/e2e/graph.html");
  const node = page.locator('.react-flow__node[data-id="n0"]');
  await node.dblclick();
  await expect(node).toHaveClass(/pinned/);
  const pinned = await node.getAttribute("style");
  await page.waitForTimeout(2400);
  expect(await node.getAttribute("style")).toBe(pinned);
  const start = await node.boundingBox();
  if (!start) throw new Error("Missing node");
  await page.mouse.move(start.x + 9, start.y + 9);
  await page.mouse.down();
  await page.mouse.move(start.x + 120, start.y + 50);
  await page.mouse.up();
  await expect.poll(() => node.getAttribute("style")).not.toBe(pinned);
  await expect(node).toHaveClass(/pinned/);
  await page.mouse.wheel(0, -180);
  await page.setViewportSize({ width: 1100, height: 800 });
  await page.getByRole("button", { name: "模拟轮询" }).click();
  const state = await page
    .locator(".react-flow__node")
    .evaluateAll((ns) => ns.map((n) => getComputedStyle(n).visibility));
  expect(state).toEqual(Array(12).fill("visible"));
  await node.dblclick();
  await expect(node).not.toHaveClass(/pinned/);
});

test("shared support survives collapsing another unit and preserves pinned layout", async ({
  page,
}) => {
  await page.goto("/e2e/graph.html");
  await page.getByRole("button", { name: "分层模式" }).click();
  const nodes = page.locator(".react-flow__node");
  await expect(nodes).toHaveCount(6);
  const shared = page.locator('.react-flow__node[data-id="n3"]');
  await shared.dblclick();
  await expect(shared).toHaveClass(/pinned/);
  const position = await shared.getAttribute("style");
  await page.getByRole("button", { name: "切换支撑 a" }).click();
  await expect(nodes).toHaveCount(5);
  await expect(shared).toHaveClass(/pinned/);
  expect(await shared.getAttribute("style")).toBe(position);
  await page.getByRole("button", { name: "切换支撑 b" }).click();
  await expect(nodes).toHaveCount(3);
  await page.getByRole("button", { name: "切换支撑 b" }).click();
  await expect(nodes).toHaveCount(5);
  await expect(shared).toHaveClass(/pinned/);
  expect(await shared.getAttribute("style")).toBe(position);
});

test("all eleven kinds and an unknown kind render colored dots without a white node overlay", async ({
  page,
}) => {
  await page.goto("/e2e/graph.html");
  await page.getByRole("button", { name: "类型颜色示例" }).click();
  const legend = page.getByRole("complementary", { name: "图谱节点类型说明" });
  await expect(legend.getByRole("listitem")).toHaveCount(11);
  const kinds = [
    "Paper",
    "Concept",
    "Method",
    "Claim",
    "ResearchQuestion",
    "Experiment",
    "Condition",
    "Finding",
    "Metric",
    "Argument",
    "Limitation",
    "UnsupportedKind",
  ];
  const colors = [];
  for (const kind of kinds) {
    const dot = page
      .locator(".react-flow__node")
      .filter({ has: page.locator(`.dot-label[data-kind="${kind}"]`) });
    await expect(dot).toBeVisible();
    await expect(dot).toHaveClass(/react-flow__node-default/);
    const appearance = await dot.evaluate((node) => {
      const style = getComputedStyle(node);
      const bounds = node.getBoundingClientRect();
      const topNode = document
        .elementFromPoint(
          bounds.x + bounds.width / 2,
          bounds.y + bounds.height / 2,
        )
        ?.closest(".react-flow__node");
      return {
        color: style.backgroundColor,
        before: getComputedStyle(node, "::before").backgroundColor,
        after: getComputedStyle(node, "::after").backgroundColor,
        diameter: [bounds.width, bounds.height],
        topNodeId: topNode?.getAttribute("data-id"),
      };
    });
    expect(appearance.color).not.toBe("rgb(255, 255, 255)");
    expect(appearance.color).not.toBe("rgba(0, 0, 0, 0)");
    expect(appearance.before).toBe("rgba(0, 0, 0, 0)");
    expect(appearance.after).toBe("rgba(0, 0, 0, 0)");
    expect(appearance.diameter).toEqual([18, 18]);
    expect(appearance.topNodeId).toBe(await dot.getAttribute("data-id"));
    if (kind !== "UnsupportedKind") {
      const swatch = legend.locator(
        `[data-kind="${kind}"] .graph-legend-swatch`,
      );
      expect(
        await swatch.evaluate((node) => getComputedStyle(node).backgroundColor),
      ).toBe(appearance.color);
    }
    colors.push(appearance.color);
  }
  expect(new Set(colors).size).toBe(12);
  await expect(legend.getByRole("button")).toHaveCount(0);
});

test("changing paper scope and explicit fit recover the camera without polling or resize resets", async ({
  page,
}) => {
  await page.goto("/e2e/graph.html");
  const viewport = page.locator(".react-flow__viewport");
  await expect(viewport).toHaveCSS("transform", "matrix(1, 0, 0, 1, 130, 100)");
  const canvas = page.locator(".projection-canvas");
  const pane = page.locator(".react-flow__pane");
  const panAway = async () => {
    const bounds = await pane.boundingBox();
    if (!bounds) throw new Error("Missing graph pane");
    await page.mouse.move(
      bounds.x + bounds.width - 40,
      bounds.y + bounds.height - 40,
    );
    await page.mouse.down();
    await page.mouse.move(bounds.x + 300, bounds.y + 180, { steps: 8 });
    await page.mouse.up();
  };
  const expectAllInside = async () => {
    await expect
      .poll(() =>
        canvas.evaluate((element) => {
          const canvas = element.getBoundingClientRect();
          return [...element.querySelectorAll(".react-flow__node")].every(
            (node) => {
              const bounds = node.getBoundingClientRect();
              return (
                bounds.left >= canvas.left &&
                bounds.top >= canvas.top &&
                bounds.right <= canvas.right &&
                bounds.bottom <= canvas.bottom
              );
            },
          );
        }),
      )
      .toBe(true);
  };
  await panAway();
  const panned = await viewport.getAttribute("style");
  await page.getByRole("button", { name: "切换论文范围" }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(6);
  await expect.poll(() => viewport.getAttribute("style")).not.toBe(panned);
  await expectAllInside();
  const fitted = await viewport.getAttribute("style");
  await page.getByRole("button", { name: "模拟轮询" }).click();
  await page.setViewportSize({ width: 1190, height: 850 });
  expect(await viewport.getAttribute("style")).toBe(fitted);
  await panAway();
  await page.getByRole("button", { name: "适应图谱", exact: true }).click();
  await expectAllInside();
  await page.getByRole("button", { name: "切换论文范围" }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(12);
  await expectAllInside();
});

test("reduced-motion dragging settles visibly and a pin stays fixed after polling", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/e2e/graph.html");
  const nodes = page.locator(".react-flow__node");
  const node = page.locator('.react-flow__node[data-id="n0"]');
  await expect(nodes).toHaveCount(12);
  await node.dblclick();
  await expect(node).toHaveClass(/pinned/);
  const before = await node.getAttribute("style");
  const start = await node.boundingBox();
  if (!start) throw new Error("Reduced-motion graph did not render");
  await page.mouse.move(start.x + 9, start.y + 9);
  await page.mouse.down();
  await page.mouse.move(start.x + 119, start.y + 79, { steps: 20 });
  await page.mouse.up();
  await expect.poll(() => node.getAttribute("style")).not.toBe(before);
  await expect(node).toHaveClass(/pinned/);
  await expect
    .poll(async () => {
      const text = await page.getByTestId("layout").textContent();
      return JSON.parse(text!).positions.find(
        (position: { node_id: string }) => position.node_id === "n0",
      )?.pinned;
    })
    .toBe(true);
  const settled = await page.getByTestId("layout").textContent();
  const pinned = await node.getAttribute("style");
  await page.waitForTimeout(600);
  expect(await page.getByTestId("layout").textContent()).toBe(settled);
  await page.getByRole("button", { name: "模拟轮询" }).click();
  expect(await node.getAttribute("style")).toBe(pinned);
  expect(
    await nodes.evaluateAll((elements) =>
      elements.every((element) => {
        const style = getComputedStyle(element);
        return (
          style.visibility === "visible" &&
          !/NaN|Infinity/.test(style.transform)
        );
      }),
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});
