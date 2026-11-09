import { render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";
import {
  getGraphAppearance,
  GraphLegend,
  graphNodeKinds,
} from "./graphAppearance";

test("LightGraph types have distinct visible colors and Chinese labels", () => {
  const kinds = [
    "RESEARCH_QUESTION",
    "CONCEPT",
    "METHOD",
    "CONTRIBUTION",
    "FINDING",
  ];
  expect(
    new Set(kinds.map((kind) => getGraphAppearance(kind).color)).size,
  ).toBe(5);
  kinds.forEach((kind) => {
    expect(getGraphAppearance(kind).label).toBeTruthy();
    expect(getGraphAppearance(kind).color).toMatch(/^#[0-9a-f]{6}$/);
  });
});
test.each(["UnsupportedKind", "", "__proto__", "constructor"])(
  "unknown kind %s has a nonwhite fallback",
  (kind) => {
    expect(getGraphAppearance(kind)).toEqual({
      label: "其他",
      color: "#74847b",
    });
  },
);
test("legend explains the five Lite kinds", () => {
  render(<GraphLegend />);
  const legend = screen.getByRole("complementary", {
    name: "图谱节点类型说明",
  });
  expect(within(legend).getAllByRole("listitem")).toHaveLength(5);
  Object.entries(graphNodeKinds)
    .filter(([kind]) => kind !== "UNKNOWN")
    .forEach(([, value]) =>
      expect(within(legend).getByText(value.label)).toBeInTheDocument(),
    );
});
