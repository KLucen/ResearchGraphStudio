import { expect, test } from "vitest";
import {
  knowledgeNodeText,
  placeKnowledgeLabels,
} from "./knowledgeGraphLabels";
import type { GraphNode, GraphPosition } from "./graphTypes";

const nodes: GraphNode[] = [
  {
    id: "method",
    type: "METHOD",
    label_zh: "示例方法",
    label_en: "Synthetic method",
  },
  {
    id: "paper",
    type: "PAPER",
    label_zh: "A long original title for the synthetic paper",
  },
  {
    id: "finding",
    type: "FINDING",
    label_zh: "合成结果",
    label_en: "Synthetic finding",
  },
];
const positions = new Map(
  nodes.map((node, index): [string, GraphPosition] => [
    node.id,
    { node_id: node.id, x: 120 + index * 29, y: 80, pinned: true },
  ]),
);

test("labels use available languages and omit a repeated bilingual line", () => {
  expect(knowledgeNodeText(nodes[0], "zh")).toEqual({
    primary: "示例方法",
    secondary: "",
  });
  expect(knowledgeNodeText(nodes[0], "en")).toEqual({
    primary: "Synthetic method",
    secondary: "",
  });
  expect(knowledgeNodeText(nodes[0], "both")).toEqual({
    primary: "示例方法",
    secondary: "Synthetic method",
  });
  expect(knowledgeNodeText(nodes[1], "en").primary).toBe(nodes[1].label_zh);
  expect(
    knowledgeNodeText(
      { id: "repeat", label_zh: "  F1  ", label_en: "F1" },
      "both",
    ),
  ).toEqual({ primary: "F1", secondary: "" });
});

test("dense labels reserve non-overlapping boxes around circles", () => {
  const placements = placeKnowledgeLabels(
    nodes,
    positions,
    "both",
    "method",
    "finding",
    false,
  );
  expect([...placements.keys()]).toEqual(["method", "finding", "paper"]);
  const boxes = [...placements.entries()].map(([id, label]) => ({
    ...label,
    x: positions.get(id)!.x + label.x,
    y: positions.get(id)!.y + label.y,
  }));
  for (const [index, box] of boxes.entries()) {
    expect(box.width).toBeLessThanOrEqual(136);
    for (const other of boxes.slice(index + 1)) {
      expect(
        box.x + box.width < other.x ||
          other.x + other.width < box.x ||
          box.y + box.height < other.y ||
          other.y + other.height < box.y,
      ).toBe(true);
    }
  }
});

test("compact zoom keeps the paper, hovered, and selected labels available", () => {
  const initial = placeKnowledgeLabels(nodes, positions, "zh", "", "", true);
  expect([...initial.keys()]).toEqual(["paper"]);
  const active = placeKnowledgeLabels(
    nodes,
    positions,
    "zh",
    "method",
    "finding",
    true,
  );
  expect([...active.keys()]).toEqual(["method", "finding", "paper"]);
});
