import { act, render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "./api";
import { PaperCloseReading } from "./PaperCloseReading";
import {
  paperReadingDocument,
  paperReadingComplete,
} from "./paperReadingFixtures";

vi.mock("./api", () => ({
  api: {
    readingDocument: vi.fn(),
    refreshReadingDocument: vi.fn(),
    paperReadingNotes: vi.fn(),
    generatePaperReadingNotes: vi.fn(),
    jobAction: vi.fn(),
    formulaPreview: vi.fn(),
    recognizeFormulas: vi.fn(),
  },
}));
function mount(
  props: Partial<React.ComponentProps<typeof PaperCloseReading>> = {},
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PaperCloseReading paperId="paper" revisionId="v" connected {...props} />
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.readingDocument).mockResolvedValue(
    structuredClone(paperReadingDocument),
  );
  vi.mocked(api.paperReadingNotes).mockResolvedValue(null);
  vi.mocked(api.refreshReadingDocument).mockResolvedValue(
    structuredClone(paperReadingDocument),
  );
  vi.mocked(api.generatePaperReadingNotes).mockResolvedValue(
    structuredClone(paperReadingComplete),
  );
  vi.mocked(api.formulaPreview).mockResolvedValue({
    formula_id: "formula-1",
    revision_id: "v",
    page: 2,
    bbox: [40, 120, 420, 180],
    mime_type: "image/png",
    data_base64: "iVBORw0KGgo=",
  });
  vi.mocked(api.recognizeFormulas).mockResolvedValue({
    revision_id: "v",
    source_sha256: "sha",
    status: "unavailable",
    recognizer: null,
    items: [],
    warnings: [],
    reading_document_refresh_required: false,
    model_calls: 0,
  });
});

test("busy local reads recover through read-only retry without refreshing the PDF or generating notes", async () => {
  const user = userEvent.setup();
  const busy = new Error(
    "DATABASE_BUSY · 本地数据库正在处理其他任务，请稍后刷新重试",
  );
  vi.mocked(api.readingDocument).mockRejectedValueOnce(busy);
  vi.mocked(api.paperReadingNotes).mockRejectedValueOnce(busy);
  mount();
  expect(await screen.findByRole("alert")).toHaveTextContent("DATABASE_BUSY");
  expect(api.readingDocument).toHaveBeenCalledTimes(1);
  expect(api.paperReadingNotes).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole("button", { name: "重新读取本地存档" }));
  await screen.findByRole("heading", { name: "2. Synthetic Methods" });
  await waitFor(() =>
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
  );
  expect(api.readingDocument).toHaveBeenCalledTimes(2);
  expect(api.paperReadingNotes).toHaveBeenCalledTimes(2);
  expect(api.refreshReadingDocument).not.toHaveBeenCalled();
  expect(api.generatePaperReadingNotes).not.toHaveBeenCalled();
  expect(api.jobAction).not.toHaveBeenCalled();
  expect(screen.queryByText(/上次本地整理/)).not.toBeInTheDocument();
});

test("reading loads local content and displays the saved local organization time when available", async () => {
  const document = structuredClone(paperReadingDocument);
  document.refreshed_at = "2026-11-16T02:30:00+00:00";
  let finishRead!: (value: typeof document) => void;
  vi.mocked(api.readingDocument).mockReturnValue(
    new Promise((resolve) => {
      finishRead = resolve;
    }),
  );
  const { container } = mount();
  expect(screen.getByText("正在读取本地阅读内容…")).toBeVisible();
  await act(async () => finishRead(document));
  expect(await screen.findByText(/本地阅读内容已就绪/)).toBeVisible();
  expect(screen.getByText(/上次本地整理/)).toBeVisible();
  expect(container.querySelector("time")).toHaveAttribute(
    "datetime",
    document.refreshed_at,
  );
  expect(api.refreshReadingDocument).not.toHaveBeenCalled();
  expect(api.generatePaperReadingNotes).not.toHaveBeenCalled();
});

test("notes read failure leaves the local document visible while retry only reloads existing data", async () => {
  const user = userEvent.setup();
  vi.mocked(api.paperReadingNotes).mockRejectedValueOnce(
    new Error("DATABASE_BUSY · 请稍后重试"),
  );
  mount();
  await screen.findByRole("heading", { name: "2. Synthetic Methods" });
  expect(await screen.findByRole("alert")).toHaveTextContent("DATABASE_BUSY");
  expect(screen.getByText(/本地阅读内容已就绪/)).toBeVisible();
  await user.click(screen.getByRole("button", { name: "重新读取本地存档" }));
  await waitFor(() =>
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
  );
  expect(
    screen.getByRole("heading", { name: "2. Synthetic Methods" }),
  ).toBeVisible();
  expect(api.refreshReadingDocument).not.toHaveBeenCalled();
  expect(api.generatePaperReadingNotes).not.toHaveBeenCalled();
});

test("local reading separates headings, body and folded materials; whole-paper generation needs explicit consent", async () => {
  const user = userEvent.setup();
  const { container } = mount();
  expect(
    await screen.findByRole("heading", { name: "2. Synthetic Methods" }),
  ).toBeVisible();
  expect(container.querySelectorAll(".paper-reading-paragraph")).toHaveLength(
    2,
  );
  expect(
    screen.getByText("58.0 T3: Flights", {
      selector: "pre.paper-material-raw",
    }),
  ).not.toBeVisible();
  expect(
    screen.getByText("Group Score A 58.0", {
      selector: "pre.paper-material-raw",
    }),
  ).not.toBeVisible();
  expect(api.generatePaperReadingNotes).not.toHaveBeenCalled();
  const generate = screen.getByRole("button", { name: "生成全文精读笔记" });
  expect(generate).toBeDisabled();
  expect(screen.queryByLabelText("起始段落")).not.toBeInTheDocument();
  await user.click(
    screen.getByRole("checkbox", {
      name: "允许本次发送整篇正文，生成全文精读笔记",
    }),
  );
  await user.click(generate);
  await screen.findByText("缓存命中 · 新增调用 0");
  expect(api.generatePaperReadingNotes).toHaveBeenCalledTimes(1);
  expect(api.generatePaperReadingNotes).toHaveBeenCalledWith("paper", {
    document_version_id: "v",
    allow_network: true,
    force_regenerate: false,
  });
  expect(screen.getByLabelText("正文第 1 段中文译文")).toHaveTextContent(
    "我们测试一种有界方法",
  );
  expect(screen.getByLabelText("正文第 2 段中文译文")).toHaveTextContent(
    "观察到的结果有条件限制",
  );
  expect(screen.getByRole("region", { name: "全文论证结构" })).toBeVisible();
  expect(
    container.querySelectorAll(".paper-paragraph-english mark").length,
  ).toBeGreaterThan(0);
});

test("materials preserve original text, source hashes, page and detected image region without translation cards", async () => {
  const user = userEvent.setup();
  mount();
  await screen.findByRole("heading", { name: "2. Synthetic Methods" });
  await user.click(
    screen.getByText("图表与其他材料（3）", { selector: "summary" }),
  );
  const materials = screen.getByRole("region", { name: "图表与其他材料" });
  await user.click(
    within(materials).getByText("疑似图内标签", { selector: "strong" }),
  );
  expect(
    within(materials).getByText("58.0 T3: Flights", {
      selector: "pre.paper-material-raw",
    }),
  ).toBeVisible();
  expect(materials.querySelector("pre.paper-material-raw")?.textContent).toBe(
    "58.0\nT3: Flights",
  );
  expect(
    within(materials).getByText(
      /处理建议：请在 Zotero 原始 PDF 第 2 页查看图像/,
    ),
  ).toBeVisible();
  const source = within(materials).getAllByText("原始块与定位", {
    selector: "summary",
  })[0];
  await user.click(source);
  expect(
    within(materials).getByText(/chunk-m1 · SHA-256 synthetic-m1/),
  ).toBeVisible();
  await user.click(
    within(materials).getByText("图像区域", { selector: "strong" }),
  );
  const image = within(materials)
    .getByText("图像区域", { selector: "strong" })
    .closest("details")!;
  await user.click(
    within(image).getByText("原始块与定位", { selector: "summary" }),
  );
  expect(
    within(image).getByText(/来源区域 · PDF 第 2 页 · 坐标 40, 200, 400, 500/),
  ).toBeVisible();
  expect(within(materials).queryByText("中文译文")).not.toBeInTheDocument();
  expect(api.generatePaperReadingNotes).not.toHaveBeenCalled();
});

test("recognized formula renders from LaTeX while retaining source and uncertain fallback", async () => {
  const document = structuredClone(paperReadingDocument);
  document.units.push({
    ...document.units[0],
    id: "formula-1",
    kind: "material",
    material_type: "formula",
    text: "x(l) = ReLU(W_self x(l-1) + ...)",
    formula_latex: "x_v^{(l)} = W_{self} x_v^{(l-1)}",
    formula_status: "recognized",
    formula_confidence: "high",
    formula_source_text: "x(l) = ReLU(W_self x(l-1) + ...)",
    formula_id: "formula-1",
    sources: [],
    reason: "检测到独立公式区域。",
    solution: "可复制 LaTeX；请用原始 PDF 核对上下标。",
  });
  document.units.push({
    ...document.units[0],
    id: "formula-2",
    kind: "material",
    material_type: "formula",
    text: "W(l) self x(l-1) +",
    formula_latex: null,
    formula_status: "uncertain",
    formula_source_text: "W(l) self x(l-1) +",
    formula_id: "formula-2",
    sources: [],
    reason: "公式识别结果不完整。",
    solution: "请查看原始 PDF 公式区域。",
  });
  vi.mocked(api.readingDocument).mockResolvedValue(document);
  const user = userEvent.setup();
  mount();
  await screen.findByRole("heading", { name: "2. Synthetic Methods" });
  await user.click(
    screen.getByText(/图表与其他材料（5）/, { selector: "summary" }),
  );
  const materials = screen.getByRole("region", { name: "图表与其他材料" });
  await user.click(
    within(materials).getAllByText("公式区域", { selector: "strong" })[0],
  );
  const recognized = within(materials)
    .getAllByText("公式区域", { selector: "strong" })[0]
    .closest("details")!;
  expect(within(recognized).getByLabelText("LaTeX 公式")).toBeVisible();
  expect(within(recognized).getByText("复制 LaTeX")).toBeVisible();
  expect(within(recognized).getAllByText(/x_v/).length).toBeGreaterThan(0);
  await user.click(
    within(recognized).getByRole("button", { name: "查看原图区域" }),
  );
  expect(api.formulaPreview).toHaveBeenCalledWith("v", "formula-1");
  expect(
    await within(recognized).findByAltText("PDF 第 2 页公式原图区域"),
  ).toHaveAttribute("src", "data:image/png;base64,iVBORw0KGgo=");
  await user.click(
    within(recognized).getByRole("button", { name: "隐藏原图区域" }),
  );
  expect(
    within(recognized).queryByAltText("PDF 第 2 页公式原图区域"),
  ).not.toBeInTheDocument();
  await user.click(
    within(materials).getAllByText("公式区域", { selector: "strong" })[1],
  );
  const uncertain = within(materials)
    .getAllByText("公式区域", { selector: "strong" })[1]
    .closest("details")!;
  expect(
    within(uncertain).getByText("公式已定位，LaTeX 尚未可靠确认"),
  ).toBeVisible();
  expect(
    within(uncertain).getAllByText("W(l) self x(l-1) +", { selector: "pre" })
      .length,
  ).toBeGreaterThan(0);
  vi.mocked(api.formulaPreview).mockRejectedValueOnce(
    new Error("FORMULA_SOURCE_UNAVAILABLE · 原始 PDF 不可用"),
  );
  await user.click(
    within(uncertain).getByRole("button", { name: "查看原图区域" }),
  );
  expect(await within(uncertain).findByRole("alert")).toHaveTextContent(
    "FORMULA_SOURCE_UNAVAILABLE",
  );
});

test("refreshing projection is local and keeps old notes separate from current text", async () => {
  const user = userEvent.setup();
  vi.mocked(api.paperReadingNotes).mockResolvedValue(
    structuredClone(paperReadingComplete),
  );
  const refreshed = structuredClone(paperReadingDocument);
  refreshed.projection_hash = "new-projection";
  vi.mocked(api.refreshReadingDocument).mockResolvedValue(refreshed);
  const { container } = mount();
  expect(await screen.findByLabelText("正文第 1 段中文译文")).toHaveTextContent(
    "我们测试一种有界方法",
  );
  await user.click(
    screen.getByRole("button", { name: "重新整理本地阅读版面" }),
  );
  await waitFor(() =>
    expect(screen.getByLabelText("正文第 1 段中文译文")).toHaveTextContent(
      "旧笔记未与当前原文对齐",
    ),
  );
  expect(
    container.querySelectorAll(".paper-paragraph-english mark"),
  ).toHaveLength(0);
  await user.click(
    screen.getByText("查看旧版本全文笔记", { selector: "summary" }),
  );
  expect(
    screen.getByText(
      paperReadingComplete.analysis!.paragraphs[0].translation_zh,
    ),
  ).toBeVisible();
  expect(api.refreshReadingDocument).toHaveBeenCalledWith("paper", "v");
  expect(api.generatePaperReadingNotes).not.toHaveBeenCalled();
});

test("formula recognition refreshes the persisted reading projection", async () => {
  const user = userEvent.setup();
  const initial = structuredClone(paperReadingDocument);
  initial.units.push({
    ...initial.units[0],
    id: "formula-1",
    kind: "material",
    material_type: "formula",
    text: "x = y",
    formula_status: "latex_unavailable",
    formula_source_text: "x = y",
    formula_id: "formula-1",
    sources: [],
  });
  const updated = structuredClone(initial);
  updated.units[updated.units.length - 1].formula_status = "recognized";
  updated.units[updated.units.length - 1].formula_latex = "x = y";
  vi.mocked(api.readingDocument)
    .mockResolvedValueOnce(initial)
    .mockResolvedValueOnce(updated);
  vi.mocked(api.recognizeFormulas).mockResolvedValue({
    revision_id: "v",
    source_sha256: "sha",
    status: "completed",
    recognizer: "synthetic-formula-ocr",
    items: [],
    warnings: [],
    reading_document_refresh_required: true,
    model_calls: 0,
  });
  mount();
  await screen.findByRole("heading", { name: "2. Synthetic Methods" });
  await user.click(screen.getByRole("button", { name: "自动识别公式并刷新" }));
  await waitFor(() => expect(api.recognizeFormulas).toHaveBeenCalledWith("v"));
  await waitFor(() => expect(api.readingDocument).toHaveBeenCalledTimes(2));
});

test("capacity errors stay visible and do not create a retry or range request", async () => {
  const user = userEvent.setup();
  vi.mocked(api.generatePaperReadingNotes).mockRejectedValue(
    new Error(
      "PAPER_READING_CAPACITY_EXCEEDED · 当前模型容量不足，请在设置中调整模型或输出上限。",
    ),
  );
  mount();
  await screen.findByRole("heading", { name: "2. Synthetic Methods" });
  await user.click(screen.getByRole("checkbox"));
  await user.click(screen.getByRole("button", { name: "生成全文精读笔记" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "PAPER_READING_CAPACITY_EXCEEDED",
  );
  expect(api.generatePaperReadingNotes).toHaveBeenCalledTimes(1);
  expect(
    screen.queryByRole("button", { name: /仅重试缺失/ }),
  ).not.toBeInTheDocument();
});

test("incomplete notes retain every translation placeholder; source text and API values render safely", async () => {
  const document = structuredClone(paperReadingDocument);
  document.units[1].text = "<img src=x onerror=alert(1)> safe body";
  vi.mocked(api.readingDocument).mockResolvedValue(document);
  vi.mocked(api.paperReadingNotes).mockResolvedValue({
    ...structuredClone(paperReadingComplete),
    status: "INCOMPLETE",
    missing_paragraph_ids: ["p2"],
    analysis: {
      ...paperReadingComplete.analysis!,
      paragraphs: [
        {
          ...paperReadingComplete.analysis!.paragraphs[0],
          translation_zh: "<script>只显示文本</script>",
          highlights: [],
        },
      ],
    },
  });
  const { container } = mount();
  expect(await screen.findByLabelText("正文第 1 段中文译文")).toHaveTextContent(
    "<script>只显示文本</script>",
  );
  expect(screen.getByLabelText("正文第 2 段中文译文")).toHaveTextContent(
    "尚无本段译文",
  );
  expect(screen.getByText(/尚缺 1 段/)).toBeVisible();
  expect(container.querySelector("img,script")).toBeNull();
  expect(api.generatePaperReadingNotes).not.toHaveBeenCalled();
});

test("the paper document maps explicit section parents into a three-level local directory", async () => {
  const user = userEvent.setup();
  const document = structuredClone(paperReadingDocument);
  const sectionsWithParents = [
    {
      section_id: "chapter",
      title: "1 Introduction",
      level: 1,
      role: "body",
      parent_id: null,
    },
    {
      section_id: "sub",
      title: "1.1 Context",
      level: 1,
      role: "body",
      parent_id: "chapter",
    },
    {
      section_id: "detail",
      title: "1.1.1 Definition",
      level: 1,
      role: "body",
      parent_id: "sub",
    },
    {
      section_id: "methods",
      title: "2 Methods",
      level: 1,
      role: "body",
      parent_id: null,
    },
  ];
  document.sections = sectionsWithParents;
  const originalHeading = document.units.find(
    (unit) => unit.kind === "heading",
  )!;
  const originalBody = document.units.find(
    (unit) => unit.kind === "paragraph",
  )!;
  document.units = sectionsWithParents.flatMap((section, index) => [
    {
      ...structuredClone(originalHeading),
      id: `nested-h${index + 1}`,
      section_id: section.section_id,
      text: section.title,
      ordinal: index * 2,
      heading_level: 1,
    },
    {
      ...structuredClone(originalBody),
      id: `nested-p${index + 1}`,
      section_id: section.section_id,
      text: `Local source for ${section.title}.`,
      ordinal: index * 2 + 1,
    },
  ]);
  vi.mocked(api.readingDocument).mockResolvedValue(document);
  const { container } = mount();
  await screen.findByRole("heading", { name: "1.1.1 Definition" });
  const directory = screen.getByRole("navigation", { name: "文章目录" });
  const detail = within(directory).getByRole("button", {
    name: "1.1.1 Definition",
  });
  expect(detail.closest("li")).toHaveAttribute("data-outline-level", "3");
  expect(directory.querySelectorAll(".reading-outline-tree > li")).toHaveLength(
    2,
  );
  await user.click(
    screen.getByRole("button", { name: "收起 1 Introduction 的子章节" }),
  );
  expect(
    within(directory).queryByRole("button", { name: "1.1.1 Definition" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "1.1.1 Definition" }),
  ).toBeVisible();
  expect(container.querySelectorAll(".paper-reading-paragraph")).toHaveLength(
    4,
  );
  await user.click(
    screen.getByRole("button", { name: "展开 1 Introduction 的子章节" }),
  );
  await user.click(
    within(directory).getByRole("button", { name: "1.1.1 Definition" }),
  );
  await waitFor(() =>
    expect(
      screen
        .getByRole("heading", { name: "1.1.1 Definition" })
        .closest("header"),
    ).toHaveFocus(),
  );
  expect(api.generatePaperReadingNotes).not.toHaveBeenCalled();
  expect(api.refreshReadingDocument).not.toHaveBeenCalled();
});

test("multiple recovered headings in one historical section retain their own three-level hierarchy", async () => {
  const user = userEvent.setup();
  const document = structuredClone(paperReadingDocument);
  document.sections = [
    {
      section_id: "s",
      parent_id: null,
      title: "1 Introduction",
      level: 1,
      role: "body",
    },
  ];
  const originalHeading = document.units.find(
    (unit) => unit.kind === "heading",
  )!;
  const originalBody = document.units.find(
    (unit) => unit.kind === "paragraph",
  )!;
  const headings = [
    { label: "1 Introduction", level: 1 },
    { label: "1.1 Context", level: 2 },
    { label: "1.1.1 Definition", level: 3 },
    { label: "2 Methods", level: 1 },
  ];
  document.units = headings.flatMap((heading, index) => [
    {
      ...structuredClone(originalHeading),
      id: `recovered-h${index + 1}`,
      section_id: "s",
      heading_level: heading.level,
      text: heading.label,
      ordinal: index * 2,
    },
    {
      ...structuredClone(originalBody),
      id: `recovered-p${index + 1}`,
      section_id: "s",
      text: `Source paragraph for ${heading.label}.`,
      ordinal: index * 2 + 1,
    },
  ]);
  vi.mocked(api.readingDocument).mockResolvedValue(document);
  mount();
  await screen.findByRole("heading", { name: "1.1.1 Definition" });
  const directory = screen.getByRole("navigation", { name: "文章目录" });
  expect(directory.querySelectorAll(".reading-outline-tree > li")).toHaveLength(
    2,
  );
  expect(
    within(directory)
      .getByRole("button", { name: "1.1 Context" })
      .closest("li"),
  ).toHaveAttribute("data-outline-level", "2");
  expect(
    within(directory)
      .getByRole("button", { name: "1.1.1 Definition" })
      .closest("li"),
  ).toHaveAttribute("data-outline-level", "3");
  await user.click(
    screen.getByRole("button", { name: "收起 1.1 Context 的子章节" }),
  );
  expect(
    within(directory).queryByRole("button", { name: "1.1.1 Definition" }),
  ).not.toBeInTheDocument();
  expect(
    within(directory).getByRole("button", { name: "2 Methods" }),
  ).toBeVisible();
  expect(
    screen.getByRole("heading", { name: "1.1.1 Definition" }),
  ).toBeVisible();
  expect(api.generatePaperReadingNotes).not.toHaveBeenCalled();
});
