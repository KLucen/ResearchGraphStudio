import { render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";
import {
  getGraphAppearance,
  GraphLegend,
  graphKindLabels,
  graphNodeKinds,
} from "./graphAppearance";

test("every projected kind has a distinct muted color and shared Chinese label", () => {
  expect(Object.keys(graphNodeKinds)).toHaveLength(11);
  expect(new Set(Object.values(graphNodeKinds).map((a) => a.color)).size).toBe(
    11,
  );
  for (const [kind, appearance] of Object.entries(graphNodeKinds)) {
    expect(appearance.color).toMatch(/^#[0-9a-f]{6}$/);
    expect(appearance.color).not.toMatch(/^#(?:fff|ffffff)$/i);
    expect(appearance.label).toBeTruthy();
    expect(getGraphAppearance(kind)).toBe(appearance);
    expect(graphKindLabels[kind as keyof typeof graphKindLabels]).toBe(
      appearance.label,
    );
  }
  expect(
    ["Paper", "Concept", "Method", "Claim", "ResearchQuestion"].map(
      (kind) => getGraphAppearance(kind).color,
    ),
  ).toEqual(["#537b98", "#927fba", "#508e80", "#b38e54", "#ad7c91"]);
});

test.each(["UnsupportedKind", "", "__proto__", "constructor"])(
  "unknown type %s gets a visible nonwhite fallback",
  (kind) => {
    expect(getGraphAppearance(kind)).toEqual({
      label: "其他",
      color: "#74847b",
    });
  },
);

test("the complete legend explains colors without controlling graph filtering", () => {
  render(<GraphLegend />);
  const legend = screen.getByRole("complementary", {
    name: "图谱节点类型说明",
  });
  const items = within(legend).getAllByRole("listitem");
  expect(items).toHaveLength(11);
  for (const [kind, appearance] of Object.entries(graphNodeKinds)) {
    const item = items.find((node) => node.dataset.kind === kind)!;
    expect(item).toHaveTextContent(appearance.label);
    expect(item.querySelector(".graph-legend-swatch")).toHaveStyle({
      backgroundColor: appearance.color,
    });
  }
  expect(within(legend).queryByRole("button")).not.toBeInTheDocument();
  expect(within(legend).queryByRole("checkbox")).not.toBeInTheDocument();
  expect(within(legend).queryByRole("combobox")).not.toBeInTheDocument();
});
