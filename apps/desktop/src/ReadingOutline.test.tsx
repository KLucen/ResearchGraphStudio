import { useState } from "react";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ReadingOutline, type OutlineEntry } from "./ReadingOutline";

const entries: OutlineEntry[] = [
  { id: "intro", label: "Introduction", targetId: "source-intro", level: 1 },
  { id: "results", label: "Results", targetId: "source-results", level: 1 },
];
const scroll = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  HTMLElement.prototype.scrollIntoView = scroll;
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
function mount(
  props: Partial<React.ComponentProps<typeof ReadingOutline>> = {},
) {
  return render(
    <ReadingOutline entries={entries} {...props}>
      <h2 id="source-intro" tabIndex={-1}>
        Introduction
      </h2>
      <p>Local source paragraph</p>
      <h2 id="source-results" tabIndex={-1}>
        Results
      </h2>
    </ReadingOutline>,
  );
}

test("collapse and locating the current directory entry preserve article position; choosing a chapter navigates", async () => {
  const user = userEvent.setup();
  const select = vi.fn();
  mount({ onSelect: select });
  await user.click(screen.getByRole("button", { name: "收起文章目录" }));
  expect(screen.getByRole("button", { name: "展开文章目录" })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  expect(
    screen.queryByRole("navigation", { name: "文章目录" }),
  ).not.toBeInTheDocument();
  expect(scroll).not.toHaveBeenCalled();
  await user.click(
    screen.getByRole("button", { name: "在目录中定位当前章节" }),
  );
  const directory = screen.getByRole("navigation", { name: "文章目录" });
  await waitFor(() =>
    expect(
      within(directory).getByRole("button", { name: "Introduction" }),
    ).toHaveFocus(),
  );
  expect(scroll).not.toHaveBeenCalled();
  await user.click(within(directory).getByRole("button", { name: "Results" }));
  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "Results" })).toHaveFocus(),
  );
  expect(select).toHaveBeenCalledExactlyOnceWith("results");
  expect(scroll).toHaveBeenCalledTimes(1);
  expect(
    within(directory).getByRole("button", { name: "Results" }),
  ).toHaveAttribute("aria-current", "location");
});

test("the current section follows article scroll without selecting scope or navigation", async () => {
  let secondTop = 1200;
  const realBounds = HTMLElement.prototype.getBoundingClientRect;
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(
    function (this: HTMLElement) {
      if (this.id === "source-intro")
        return {
          top: -300,
          bottom: -270,
          left: 0,
          right: 600,
          width: 600,
          height: 30,
        } as DOMRect;
      if (this.id === "source-results")
        return {
          top: secondTop,
          bottom: secondTop + 30,
          left: 0,
          right: 600,
          width: 600,
          height: 30,
        } as DOMRect;
      return realBounds.call(this);
    },
  );
  const select = vi.fn();
  mount({ trackScroll: true, onSelect: select });
  const results = within(
    screen.getByRole("navigation", { name: "文章目录" }),
  ).getByRole("button", { name: "Results" });
  secondTop = 100;
  fireEvent.scroll(window);
  await waitFor(() =>
    expect(results).toHaveAttribute("aria-current", "location"),
  );
  expect(select).not.toHaveBeenCalled();
  expect(scroll).not.toHaveBeenCalled();
});

test("a compact directory closes by Escape or outside pointer and restores a visible focus target", async () => {
  vi.stubGlobal("matchMedia", () => ({ matches: true }));
  const user = userEvent.setup();
  mount();
  const open = screen.getByRole("button", { name: "展开文章目录" });
  await user.click(open);
  await user.keyboard("{Escape}");
  expect(open).toHaveAttribute("aria-expanded", "false");
  expect(open).toHaveFocus();
  await user.click(open);
  const directory = screen.getByRole("navigation", { name: "文章目录" });
  within(directory).getByRole("button", { name: "Results" }).focus();
  fireEvent.pointerDown(screen.getByText("Local source paragraph"));
  expect(open).toHaveAttribute("aria-expanded", "false");
  expect(open).toHaveFocus();
  expect(scroll).not.toHaveBeenCalled();
});

test("explicit section selection focuses the replacement view after selected-paragraph state remounts", async () => {
  const user = userEvent.setup();
  function Harness() {
    const [selected, setSelected] = useState("intro");
    const entry = entries.find((item) => item.id === selected)!;
    return (
      <ReadingOutline
        key={selected}
        entries={entries}
        activeId={selected}
        onSelect={setSelected}
      >
        <h2 id={entry.targetId} tabIndex={-1}>
          {entry.label}
        </h2>
      </ReadingOutline>
    );
  }
  render(<Harness />);
  await user.click(
    within(screen.getByRole("navigation", { name: "文章目录" })).getByRole(
      "button",
      { name: "Results" },
    ),
  );
  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "Results" })).toHaveFocus(),
  );
  expect(scroll).toHaveBeenCalledTimes(1);
});
