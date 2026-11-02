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
