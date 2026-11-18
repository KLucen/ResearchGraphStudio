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

const nestedEntries: OutlineEntry[] = [
  { id: "chapter", label: "1 Introduction", targetId: "chapter", level: 1 },
  { id: "sub", label: "1.1 Context", targetId: "sub", level: 2 },
  { id: "detail", label: "1.1.1 Detail", targetId: "detail", level: 3 },
  { id: "next", label: "2 Methods", targetId: "next", level: 1 },
];

test("three heading levels form nested branches and folding never selects or navigates", async () => {
  const user = userEvent.setup();
  const select = vi.fn();
  mount({ entries: nestedEntries, onSelect: select });
  const directory = screen.getByRole("navigation", { name: "文章目录" });
  expect(directory.querySelectorAll(".reading-outline-tree > li")).toHaveLength(
    2,
  );
  expect(
    within(directory)
      .getByRole("button", { name: "1.1.1 Detail" })
      .closest("li"),
  ).toHaveAttribute("data-outline-level", "3");
  await user.click(
    screen.getByRole("button", { name: "收起 1.1 Context 的子章节" }),
  );
  expect(
    within(directory).queryByRole("button", {
      name: "1.1.1 Detail",
    }),
  ).not.toBeInTheDocument();
  expect(
    within(directory).getByRole("button", { name: "1.1 Context" }),
  ).toBeVisible();
  await user.click(
    screen.getByRole("button", { name: "收起 1 Introduction 的子章节" }),
  );
  expect(
    within(directory).queryByRole("button", {
      name: "1.1 Context",
    }),
  ).not.toBeInTheDocument();
  expect(select).not.toHaveBeenCalled();
  expect(scroll).not.toHaveBeenCalled();
});

test("locating the current chapter opens every ancestor while rerenders respect a manually folded branch", async () => {
  const user = userEvent.setup();
  const view = mount({ entries: nestedEntries, activeId: "detail" });
  await user.click(
    screen.getByRole("button", { name: "收起 1.1 Context 的子章节" }),
  );
  await user.click(
    screen.getByRole("button", { name: "收起 1 Introduction 的子章节" }),
  );
  view.rerender(
    <ReadingOutline
      entries={nestedEntries.map((entry) => ({ ...entry }))}
      activeId="detail"
    >
      <p>Same current chapter</p>
    </ReadingOutline>,
  );
  expect(
    screen.queryByRole("button", { name: "1.1.1 Detail" }),
  ).not.toBeInTheDocument();
  await user.click(
    screen.getByRole("button", { name: "在目录中定位当前章节" }),
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "1.1.1 Detail" })).toHaveFocus(),
  );
  expect(
    screen.getByRole("button", { name: "收起 1 Introduction 的子章节" }),
  ).toHaveAttribute("aria-expanded", "true");
  expect(
    screen.getByRole("button", { name: "收起 1.1 Context 的子章节" }),
  ).toHaveAttribute("aria-expanded", "true");
  expect(scroll).not.toHaveBeenCalled();
});

test("a newly current chapter reveals its ancestors without navigating the article", async () => {
  const user = userEvent.setup();
  const view = mount({ entries: nestedEntries, activeId: "next" });
  await user.click(
    screen.getByRole("button", { name: "收起 1 Introduction 的子章节" }),
  );
  view.rerender(
    <ReadingOutline entries={nestedEntries} activeId="detail">
      <p>Current chapter changed locally</p>
    </ReadingOutline>,
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "1.1.1 Detail" })).toBeVisible(),
  );
  expect(scroll).not.toHaveBeenCalled();
});

test("explicit parent relationships override levels; missing, self and cyclic parents remain reachable", () => {
  const explicit: OutlineEntry[] = [
    { id: "root", label: "Root", targetId: "r", level: 3, parentId: null },
    { id: "child", label: "Child", targetId: "c", level: 1, parentId: "root" },
    {
      id: "missing",
      label: "Missing",
      targetId: "m",
      level: 3,
      parentId: "absent",
    },
    { id: "self", label: "Self", targetId: "s", parentId: "self" },
    { id: "cycle-a", label: "Cycle A", targetId: "a", parentId: "cycle-b" },
    { id: "cycle-b", label: "Cycle B", targetId: "b", parentId: "cycle-a" },
  ];
  mount({ entries: explicit });
  const directory = screen.getByRole("navigation", { name: "文章目录" });
  for (const entry of explicit) {
    expect(
      within(directory).getAllByRole("button", {
        name: entry.label,
      }),
    ).toHaveLength(1);
  }
  expect(
    within(directory).getByRole("button", { name: "Child" }).closest("li"),
  ).toHaveAttribute("data-outline-level", "2");
  expect(
    within(directory).getByRole("button", { name: "Missing" }).closest("li"),
  ).toHaveAttribute("data-outline-level", "1");
  expect(
    within(directory).getByRole("button", { name: "Self" }).closest("li"),
  ).toHaveAttribute("data-outline-level", "1");
});

test("refreshing the current chapter's parent reveals its new ancestor without reopening an unchanged path", async () => {
  const user = userEvent.setup();
  const chapters: OutlineEntry[] = [
    { id: "a", label: "Chapter A", targetId: "a", parentId: null },
    { id: "current", label: "Current child", targetId: "c", parentId: "a" },
    { id: "b", label: "Chapter B", targetId: "b", parentId: null },
    { id: "other", label: "Other child", targetId: "o", parentId: "b" },
  ];
  const view = mount({ entries: chapters, activeId: "current" });
  await user.click(
    screen.getByRole("button", { name: "收起 Chapter B 的子章节" }),
  );
  const moved = chapters.map((entry) =>
    entry.id === "current" ? { ...entry, parentId: "b" } : { ...entry },
  );
  view.rerender(
    <ReadingOutline entries={moved} activeId="current">
      <p>Parent changed</p>
    </ReadingOutline>,
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Current child" })).toBeVisible(),
  );
  expect(
    screen.getByRole("button", { name: "收起 Chapter B 的子章节" }),
  ).toHaveAttribute("aria-expanded", "true");
  await user.click(
    screen.getByRole("button", { name: "收起 Chapter B 的子章节" }),
  );
  view.rerender(
    <ReadingOutline
      entries={moved.map((entry) => ({ ...entry }))}
      activeId="current"
    >
      <p>Same hierarchy refreshed</p>
    </ReadingOutline>,
  );
  expect(
    screen.queryByRole("button", { name: "Current child" }),
  ).not.toBeInTheDocument();
  expect(scroll).not.toHaveBeenCalled();
});
