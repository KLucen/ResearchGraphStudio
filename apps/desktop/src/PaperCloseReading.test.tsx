import { render, screen, within, waitFor } from "@testing-library/react";
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
