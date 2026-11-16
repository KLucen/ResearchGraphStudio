import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "./api";
import { SectionCloseReading, BilingualParagraph } from "./SectionCloseReading";
import { highlightSegments } from "./readingHighlights";
import {
  readingSource,
  readingComplete,
  readingPartial,
  readingState,
  readingConcept,
  readingCheck,
} from "./closeReadingFixtures";
vi.mock("./api", () => ({
  api: {
    sectionParagraphs: vi.fn(),
    closeReading: vi.fn(),
    generateCloseReading: vi.fn(),
    readingState: vi.fn(),
    saveReadingState: vi.fn(),
    conceptUnderstanding: vi.fn(),
    understandingCheck: vi.fn(),
    generateUnderstandingCheck: vi.fn(),
  },
}));
function mount(element: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>{element}</QueryClientProvider>,
    ),
  };
}
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.sectionParagraphs).mockResolvedValue(readingSource);
  vi.mocked(api.closeReading).mockResolvedValue(null);
  vi.mocked(api.readingState).mockResolvedValue(readingState);
  vi.mocked(api.conceptUnderstanding).mockResolvedValue([readingConcept]);
  vi.mocked(api.understandingCheck).mockResolvedValue(null);
  vi.mocked(api.generateCloseReading).mockResolvedValue(readingComplete);
  vi.mocked(api.generateUnderstandingCheck).mockResolvedValue(readingCheck);
  vi.mocked(api.saveReadingState).mockImplementation(
    async (_paper, _section, body) => ({
      ...readingState,
      ...body,
      updated_at: "2026-11-14T00:00:00Z",
    }),
  );
});
test("exact highlights keep nth occurrence, overlap precedence and all local source text", () => {
  const text = "alpha alpha beta <img src=x>";
  const segments = highlightSegments(text, [
    { type: "METHOD", quote_en: "alpha beta", occurrence_index: 0 },
    { type: "THESIS", quote_en: "alpha", occurrence_index: 1 },
    { type: "EVIDENCE", quote_en: "missing", occurrence_index: 0 },
    { type: "CONCEPT", quote_en: "alpha", occurrence_index: 50 },
  ]);
  expect(segments.map((s) => s.text).join("")).toBe(text);
  expect(segments.find((s) => s.type === "THESIS")).toMatchObject({
    text: "alpha",
    start: 6,
  });
  expect(segments.find((s) => s.type === "METHOD")?.text).toBe(" beta");
  expect(segments.filter((s) => s.type)).toHaveLength(2);
});
test("secondary historical reading preserves state and A03 while removing old range generation", async () => {
  mount(
    <SectionCloseReading
      paperId="paper"
      revisionId="v"
      sectionId="s"
      title="Historical Methods"
      connected
      historyOnly
    />,
  );
  await screen.findByLabelText("第 1 段中文译文");
  expect(screen.getByRole("region", { name: "我的阅读状态" })).toBeVisible();
  expect(screen.getByText("用自己的话复述 · 按需理解检查")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "生成双栏精读" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("checkbox", {
      name: "允许本次发送所选段落，生成译文和批注",
    }),
  ).not.toBeInTheDocument();
  expect(api.generateCloseReading).not.toHaveBeenCalled();
  expect(api.generateUnderstandingCheck).not.toHaveBeenCalled();
});
test("bilingual row always renders translation and safely renders text with local highlights", () => {
  const paragraph = {
    ...readingSource.paragraphs[0],
    text_en: "<img src=x onerror=alert(1)> alpha alpha",
  };
  const annotation = {
    ...readingComplete.analysis!.paragraphs[0],
    translation_zh: "<script>不执行</script>",
    highlights: [
      { type: "CONCEPT" as const, quote_en: "alpha", occurrence_index: 1 },
    ],
  };
  const { container } = mount(
    <BilingualParagraph paragraph={paragraph} analysis={annotation} />,
  );
  expect(screen.getByLabelText("第 1 段中文译文")).toBeVisible();
  expect(screen.getByText("<script>不执行</script>")).toBeVisible();
  expect(container.querySelector("img,script")).toBeNull();
  expect(container.querySelector(".paragraph-english")?.textContent).toBe(
    paragraph.text_en,
  );
  expect(container.querySelectorAll("mark")).toHaveLength(1);
  expect(container.querySelector("mark")?.textContent).toBe("alpha");
});
test("opening and changing a range are local; only an explicit authorized A02 sends selected IDs", async () => {
  const user = userEvent.setup();
  mount(
    <SectionCloseReading
      paperId="paper"
      revisionId="v"
      sectionId="s"
      title="Methods"
      connected
    />,
  );
  expect(await screen.findByLabelText("第 1 段中文译文")).toHaveTextContent(
    "本段译文尚未生成",
  );
  expect(screen.getByLabelText("第 2 段中文译文")).toBeVisible();
  expect(api.generateCloseReading).not.toHaveBeenCalled();
  expect(api.generateUnderstandingCheck).not.toHaveBeenCalled();
  await user.selectOptions(screen.getByLabelText("起始段落"), "1");
  expect(screen.queryByLabelText("第 1 段中文译文")).not.toBeInTheDocument();
  await waitFor(() =>
    expect(api.closeReading).toHaveBeenLastCalledWith("paper", "s", "v", [
      "p2",
    ]),
  );
  const generate = screen.getByRole("button", { name: "生成双栏精读" });
  expect(generate).toBeDisabled();
  await user.click(
    screen.getByRole("checkbox", {
      name: "允许本次发送所选段落，生成译文和批注",
    }),
  );
  await user.click(generate);
  expect(api.generateCloseReading).toHaveBeenCalledExactlyOnceWith(
    "paper",
    "s",
    {
      document_version_id: "v",
      paragraph_ids: ["p2"],
      allow_network: true,
      force_regenerate: false,
    },
  );
});
test("partial results retain validated translation and retry only missing IDs without replacing parent", async () => {
  vi.mocked(api.closeReading).mockImplementation(
    async (_p, _s, _v, _ids, id) =>
      id
        ? {
            ...readingComplete,
            id: "repair",
            range: { ...readingComplete.range, paragraph_ids: ["p2"] },
          }
        : readingPartial,
  );
  vi.mocked(api.generateCloseReading).mockResolvedValue({
    ...readingComplete,
    id: "repair",
    range: { ...readingComplete.range, paragraph_ids: ["p2"] },
  });
  const user = userEvent.setup();
  mount(
    <SectionCloseReading
      paperId="paper"
      revisionId="v"
      sectionId="s"
      title="Methods"
      connected
    />,
  );
  await waitFor(() =>
    expect(screen.getByLabelText("第 1 段中文译文")).toHaveTextContent(
      "我们测试一种有界方法",
    ),
  );
  expect(screen.getByLabelText("第 2 段中文译文")).toHaveTextContent(
    "本段译文尚未生成",
  );
  const retry = screen.getByRole("button", { name: "仅重试缺失的 1 段" });
  expect(retry).toBeDisabled();
  await user.click(
    screen.getByRole("checkbox", {
      name: "允许本次发送所选段落，生成译文和批注",
    }),
  );
  await user.click(retry);
  expect(api.generateCloseReading).toHaveBeenCalledExactlyOnceWith(
    "paper",
    "s",
    {
      document_version_id: "v",
      paragraph_ids: ["p2"],
      allow_network: true,
      retry_missing_of: "cr1",
    },
  );
  expect(screen.getByLabelText("第 1 段中文译文")).toHaveTextContent(
    "我们测试一种有界方法",
  );
});
test("reading state saves and question resolution never generate model work", async () => {
  const user = userEvent.setup();
  mount(
    <SectionCloseReading
      paperId="paper"
      revisionId="v"
      sectionId="s"
      title="Methods"
      connected
    />,
  );
  await user.selectOptions(await screen.findByLabelText("阅读进度"), "READING");
  await waitFor(() =>
    expect(api.saveReadingState).toHaveBeenCalledWith(
      "paper",
      "s",
      expect.objectContaining({
        progress: "READING",
        self_assessment: "UNSET",
      }),
    ),
  );
  await user.type(screen.getByLabelText("添加待解问题"), "限制条件是什么？");
  await user.click(screen.getByRole("button", { name: "保存问题" }));
  expect(await screen.findByText("限制条件是什么？")).toBeVisible();
  expect(api.generateCloseReading).not.toHaveBeenCalled();
  expect(api.generateUnderstandingCheck).not.toHaveBeenCalled();
});
test("A03 is explicit and an UNCERTAIN suggestion does not alter self-assessment", async () => {
  const user = userEvent.setup();
  mount(
    <SectionCloseReading
      paperId="paper"
      revisionId="v"
      sectionId="s"
      title="Methods"
      connected
    />,
  );
  await screen.findByLabelText("阅读进度");
  await user.click(screen.getByText("用自己的话复述 · 按需理解检查"));
  const check = screen.getByRole("region", { name: "理解检查" });
  await user.type(
    within(check).getByLabelText("我的复述"),
    "方法在噪声下可能失败。",
  );
  expect(api.generateUnderstandingCheck).not.toHaveBeenCalled();
  expect(
    within(check).getByRole("button", { name: "提交理解检查" }),
  ).toBeDisabled();
  await user.click(
    within(check).getByRole("checkbox", { name: "允许本次检查我的复述" }),
  );
  await user.click(within(check).getByRole("button", { name: "提交理解检查" }));
  expect(await screen.findByText("模型建议：依据不足，无法确定")).toBeVisible();
  expect(api.saveReadingState).not.toHaveBeenCalled();
  expect(screen.getByLabelText("我的理解自评")).toHaveValue("UNSET");
});
test("cached result and argument summary open without new model work and link locally", async () => {
  vi.mocked(api.closeReading).mockResolvedValue(readingComplete);
  const user = userEvent.setup();
  const graph = vi.fn(),
    qa = vi.fn();
  mount(
    <SectionCloseReading
      paperId="paper"
      revisionId="v"
      sectionId="s"
      title="Methods"
      connected
      onOpenGraph={graph}
      onAskParagraph={qa}
    />,
  );
  expect(await screen.findByText("缓存命中 · 新增调用 0")).toBeVisible();
  expect(screen.getByRole("region", { name: "小节论证结构" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "有界方法" }));
  expect(graph).toHaveBeenCalledWith("n1");
  await user.click(screen.getAllByRole("button", { name: "对这一段提问" })[0]);
  expect(qa).toHaveBeenCalledWith(readingSource.paragraphs[0]);
  expect(api.generateCloseReading).not.toHaveBeenCalled();
});
