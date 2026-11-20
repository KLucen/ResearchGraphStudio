import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import {
  ReadingParagraphCard,
  type ReadingParagraphAnalysis,
} from "./ReadingContent";

const analysis: ReadingParagraphAnalysis = {
  paragraph_id: "source-1",
  paragraph_function: "OTHER",
  translation_zh: null,
  logic_role_zh: "整段说明方法、概念与证据的关系。",
  critical_note_zh: "证据的适用范围需要核对。",
  reading_question_zh: "证据是否支持此主张？",
  related_graph_node_ids: ["concept-1"],
  highlights: [
    { type: "METHOD", quote_en: "alpha beta", occurrence_index: 0 },
    { type: "THESIS", quote_en: "alpha", occurrence_index: 1 },
    { type: "CONCEPT", quote_en: "beta", occurrence_index: 0 },
    { type: "EVIDENCE", quote_en: "12 observations", occurrence_index: 0 },
  ],
};
const text = "alpha alpha beta has 12 observations. <img src=x>";
const props = {
  id: "source-1",
  elementId: "source-row",
  text,
  paragraphNumber: 3,
  analysis,
};

test("compact highlight references identify the source without duplicate quote cards and keep the actual analysis together", () => {
  const { container } = render(
    <ReadingParagraphCard {...props} translation="独立成功译文" />,
  );
  const notes = screen.getByLabelText("正文第 3 段论证批注");
  for (const label of ["方法与过程", "核心论点", "概念定义", "论据与结果"]) {
    expect(within(notes).getByText(label)).toBeVisible();
  }
  const references = [
    ...container.querySelectorAll<HTMLElement>(".paper-highlight-reference"),
  ];
  expect(references).toHaveLength(4);
  expect(
    container.querySelector(".paper-highlight-note,blockquote"),
  ).toBeNull();
  for (const reference of references) {
    const index = Number(reference.dataset.annotationKey);
    const mark = container.querySelector<HTMLElement>(
      `mark[data-annotation-keys~="${index}"]`,
    );
    expect(mark).not.toBeNull();
    expect(mark?.getAttribute("aria-controls")?.split(" ")).toContain(
      reference.id,
    );
    expect(reference).not.toHaveTextContent(
      analysis.highlights[index].quote_en,
    );
  }
  const whole = screen.getByLabelText("第 3 段整段批注");
  expect(whole).toHaveTextContent("以下分析对应本段，点击编号可定位原文。");
  expect(whole).toHaveTextContent(analysis.logic_role_zh);
  expect(whole).toHaveTextContent("论证作用");
  expect(whole).toHaveTextContent("核查提醒");
  expect(whole).toHaveTextContent("阅读问题");
  expect(screen.getByLabelText("正文第 3 段中文译文")).toHaveTextContent(
    "独立成功译文",
  );
  expect(container.querySelector(".paper-paragraph-english")?.textContent).toBe(
    text,
  );
  expect(container.querySelector("img,script")).toBeNull();
});

test("overlapping and adjacent equal types keep every annotation identity and nth occurrence", async () => {
  const user = userEvent.setup();
  const highlights = [
    { type: "THESIS" as const, quote_en: "alpha", occurrence_index: 0 },
    { type: "THESIS" as const, quote_en: "beta", occurrence_index: 0 },
    { type: "CONCEPT" as const, quote_en: "alpha", occurrence_index: 0 },
    { type: "METHOD" as const, quote_en: "alpha", occurrence_index: 1 },
  ];
  const { container } = render(
    <ReadingParagraphCard
      {...props}
      text="alphabeta alpha"
      analysis={{ ...analysis, highlights }}
    />,
  );
  expect(container.querySelectorAll(".paper-highlight-reference")).toHaveLength(
    4,
  );
  expect(
    container.querySelector('mark[data-annotation-keys~="0"]'),
  ).toHaveTextContent("alpha");
  expect(
    container.querySelector('mark[data-annotation-keys~="1"]'),
  ).toHaveTextContent("beta");
  expect(container.querySelector('mark[data-annotation-keys~="2"]')).toBe(
    container.querySelector('mark[data-annotation-keys~="0"]'),
  );
  await user.click(
    screen.getByRole("button", { name: "定位原文标记 3.4 · 方法与过程" }),
  );
  expect(
    container.querySelector('mark[data-annotation-keys~="3"]'),
  ).toHaveFocus();
  await user.keyboard("{Enter}");
  expect(
    screen.getByRole("button", { name: "定位原文标记 3.4 · 方法与过程" }),
  ).toHaveFocus();
});

test("mark and reference navigation is local and changing the source clears selection", async () => {
  const user = userEvent.setup();
  const onAsk = vi.fn();
  const onOpenGraph = vi.fn();
  const { container, rerender } = render(
    <ReadingParagraphCard {...props} onAsk={onAsk} onOpenGraph={onOpenGraph} />,
  );
  const mark = container.querySelector<HTMLElement>(
    'mark[data-annotation-keys~="3"]',
  )!;
  await user.click(mark);
  const reference = screen.getByRole("button", {
    name: "定位原文标记 3.4 · 论据与结果",
  });
  expect(reference).toHaveAttribute("data-active", "true");
  expect(reference).toHaveFocus();
  await user.click(reference);
  expect(mark).toHaveFocus();
  expect(onAsk).not.toHaveBeenCalled();
  expect(onOpenGraph).not.toHaveBeenCalled();
  rerender(
    <ReadingParagraphCard {...props} text={`${text} Updated source.`} />,
  );
  expect(container.querySelector('[data-active="true"]')).toBeNull();
});

test("invalid quote or occurrence never creates an unbound note, and empty highlights keep a clearly scoped paragraph comment", () => {
  const { container, rerender } = render(
    <ReadingParagraphCard
      {...props}
      analysis={{
        ...analysis,
        highlights: [
          { type: "THESIS", quote_en: "unavailable", occurrence_index: 0 },
          { type: "METHOD", quote_en: "alpha", occurrence_index: 100 },
        ],
      }}
    />,
  );
  expect(
    container.querySelectorAll("mark,.paper-highlight-reference"),
  ).toHaveLength(0);
  expect(screen.getByLabelText("第 3 段整段批注")).toHaveTextContent(
    analysis.logic_role_zh,
  );
  rerender(<ReadingParagraphCard {...props} analysis={undefined} stale />);
  expect(screen.getByText("当前正文暂无有效批注。")).toBeVisible();
  expect(container.querySelectorAll(".paper-paragraph-comment")).toHaveLength(
    0,
  );
});
