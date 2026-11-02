import { expect, test } from "vitest";
import { ForceSimulation } from "./forceSimulation";
import { placeNodes } from "./graphLayout";

test("drag moves connected neighbors, pins stay fixed, and simulation settles", () => {
  const sim = new ForceSimulation(
    [
      { node_id: "a", x: 0, y: 0, pinned: false },
      { node_id: "b", x: 110, y: 0, pinned: false },
      { node_id: "c", x: 200, y: 90, pinned: true },
    ],
    [
      { source: "a", target: "b" },
      { source: "b", target: "c" },
    ],
  );
  sim.move("a", -200, 80);
  for (let i = 0; i < 25; i++) sim.tick();
  expect(sim.points.get("a")?.x).toBe(-200);
  expect(sim.points.get("b")?.x).not.toBe(110);
  expect(sim.points.get("c")?.x).toBe(200);
  sim.dragging = null;
  sim.pin("a");
  for (let i = 0; i < 300; i++) sim.tick();
  expect(sim.tick()).toBe(false);
  expect(sim.points.get("a")?.x).toBe(-200);
  expect(
    sim.snapshot().every((p) => Number.isFinite(p.x) && Number.isFinite(p.y)),
  ).toBe(true);
  sim.pin("a");
  sim.tick();
  expect(sim.points.get("a")?.x).not.toBe(-200);
});
test("invalid pointer and stale non-finite layout cannot poison the graph", () => {
  const sim = new ForceSimulation(
    [{ node_id: "a", x: 20, y: 30, pinned: false }],
    [],
  );
  sim.move("a", NaN, Infinity);
  expect(sim.snapshot()[0]).toMatchObject({ x: 20, y: 30 });
  const graph = { nodes: [{ id: "a" }] } as Parameters<typeof placeNodes>[0];
  const seeded = placeNodes(graph, [
    { node_id: "a", x: NaN, y: 0, pinned: false },
  ]);
  expect(Number.isFinite(seeded[0].x)).toBe(true);
});
