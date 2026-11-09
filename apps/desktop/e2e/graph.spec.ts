import { expect, test } from "@playwright/test";

test("real LightGraph renderer keeps nodes visible during hover and drag", async ({
  page,
}) => {
  await page.goto("/e2e/graph.html");
  const dots = page.locator(".react-flow__node");
  await expect(dots).toHaveCount(12);
  const first = dots.first();
  await first.hover();
  const start = await first.boundingBox();
  if (!start) throw new Error("Missing graph node");
  await page.mouse.move(start.x + 9, start.y + 9);
  await page.mouse.down();
  await page.mouse.move(start.x + 130, start.y + 65, { steps: 20 });
  await page.mouse.up();
  expect(
    await dots.evaluateAll((nodes) =>
      nodes.every(
        (node) =>
          getComputedStyle(node).visibility === "visible" &&
          !/NaN|Infinity/.test(getComputedStyle(node).transform),
      ),
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "模拟轮询" }).click();
  await expect(dots).toHaveCount(12);
});
test("pin, zoom, selection and saved layout survive browser reload", async ({
  page,
}) => {
  await page.goto("/e2e/graph.html");
  const node = page.locator('.react-flow__node[data-id="n0"]');
  await node.click();
  await expect(page.getByTestId("selection")).toHaveText("n0");
  await node.dblclick();
  await expect(node).toHaveClass(/pinned/);
  await page.waitForTimeout(2500);
  await page.mouse.move(450, 350);
  await page.mouse.wheel(0, -200);
  await expect
    .poll(
      async () =>
        JSON.parse((await page.getByTestId("layout").textContent())!).zoom,
    )
    .not.toBe(1);
  const before = JSON.parse((await page.getByTestId("layout").textContent())!);
  const camera = {
    pan_x: before.pan_x,
    pan_y: before.pan_y,
    zoom: before.zoom,
  };
  await page.getByRole("button", { name: "模拟轮询" }).click();
  await page.setViewportSize({ width: 1100, height: 800 });
  expect(
    JSON.parse((await page.getByTestId("layout").textContent())!),
  ).toMatchObject(camera);
  await page.reload();
  await expect(node).toHaveClass(/pinned/);
  expect(JSON.parse((await page.getByTestId("layout").textContent())!)).toEqual(
    before,
  );
  const renderedCamera = await page
    .locator(".react-flow__viewport")
    .evaluate((element) => {
      const matrix = new DOMMatrixReadOnly(getComputedStyle(element).transform);
      return { x: matrix.e, y: matrix.f, zoom: matrix.a };
    });
  expect(renderedCamera.x).toBeCloseTo(camera.pan_x, 3);
  expect(renderedCamera.y).toBeCloseTo(camera.pan_y, 3);
  expect(renderedCamera.zoom).toBeCloseTo(camera.zoom, 3);
  await expect(page.locator(".react-flow__node")).toHaveCount(12);
});
