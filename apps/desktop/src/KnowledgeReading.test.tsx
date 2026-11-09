import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { KnowledgeReading } from "./KnowledgeReading";
import { api, type KnowledgeNode, type Evidence } from "./api";

vi.mock("./api", () => ({
  api: {
    structure: vi.fn(),
    knowledge: vi.fn(),
    providers: vi.fn(),
    runs: vi.fn(),
    node: vi.fn(),
    preview: vi.fn(),
    extract: vi.fn(),
    review: vi.fn(),
    annotations: vi.fn(),
  },
}));
const evidence: Evidence = {
  id: "ev",
  document_version_id: "v",
  section_id: "s",
  paragraph_id: "p",
  page_index: 1,
  start_offset: 0,
  end_offset: 29,
  quote: "No improvement was observed.",
  text_sha256: "a".repeat(64),
  normalization: "identity-v1",
  bbox_list: [[1, 2, 3, 4]],
};
const node: KnowledgeNode = {
  id: "n",
  paper_id: "paper",
  document_version_id: "v",
  kind: "claim",
  text: "No improvement was observed.",
  payload: {
    statement: "No improvement was observed.",
    origin: "author_claim",
  },
  origin: "author_claim",
  authorship: "paper_author",
  source_status: "source_verified",
  review_status: "unreviewed",
  issues: [],
  dimension: null,
  known_state: null,
  value: null,
  unit: null,
  model_run_id: null,
  revision: 1,
  created_at: "2026-11-01T00:00:00Z",
  updated_at: "2026-11-01T00:00:00Z",
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.structure).mockResolvedValue({
    document_version_id: "v",
    sections: [
      {
        id: "s",
        document_version_id: "v",
        title: "Results",
        ordinal: 0,
        role: "results",
        parser: "test",
      },
    ],
    evidence: [evidence],
  });
  vi.mocked(api.knowledge).mockResolvedValue({
    items: [node],
    graph_revision: 2,
  });
  vi.mocked(api.providers).mockResolvedValue({
    configured: true,
    model: "test-model",
    mock: "offline",
    transmitted_data: "paper",
  });
  vi.mocked(api.runs).mockResolvedValue([]);
  vi.mocked(api.annotations).mockResolvedValue([]);
  vi.mocked(api.node).mockResolvedValue({
    node,
    evidence: [evidence],
    reviews: [],
    model_run: null,
    graph_revision: 2,
  });
  vi.mocked(api.preview).mockResolvedValue({
    data_url: "data:image/png;base64,AA",
    page_index: 1,
    precision: "block",
  });
});
function mount(connected = true, liteMode = false) {
  render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <KnowledgeReading
        versionId="v"
        connected={connected}
        liteMode={liteMode}
      />
    </QueryClientProvider>,
  );
}

test("card resolves persisted evidence and PDF page highlight", async () => {
  const user = userEvent.setup();
  mount();
  await user.click(screen.getByRole("button", { name: /论文结构与知识/ }));
  await user.click(
    await screen.findByRole("button", { name: /No improvement was observed/ }),
  );
  expect(await screen.findByAltText("PDF 第 2 页原文块高亮")).toBeVisible();
  expect(api.preview).toHaveBeenCalledWith("ev");
});

test("real extraction requires explicit text transfer consent", async () => {
  const user = userEvent.setup();
  mount();
  await user.click(screen.getByRole("button", { name: /论文结构与知识/ }));
  expect(screen.queryByText(/离线 Mock|旧 P01/)).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "生成论文知识图谱" }),
  ).toBeDisabled();
  await user.click(screen.getByRole("checkbox"));
  await user.click(screen.getByRole("button", { name: "生成论文知识图谱" }));
  expect(api.extract).toHaveBeenCalledWith(
    "v",
    "project",
    true,
    "paper-reading-v1",
  );
});

test("reading retains provenance without requiring human review", async () => {
  const user = userEvent.setup();
  mount();
  await user.click(screen.getByRole("button", { name: /论文结构与知识/ }));
  await user.click(
    await screen.findByRole("button", { name: /No improvement was observed/ }),
  );
  expect(await screen.findByText("原始模型与修改历史")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "保存修订待审" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByLabelText("审核理由")).not.toBeInTheDocument();
  expect(api.review).not.toHaveBeenCalled();
});

test("offline reading disables extraction without issuing new calls", async () => {
  const user = userEvent.setup();
  mount(false);
  await user.click(screen.getByRole("button", { name: /论文结构与知识/ }));
  expect(
    screen.getByRole("button", { name: "生成论文知识图谱" }),
  ).toBeDisabled();
  expect(api.knowledge).not.toHaveBeenCalled();
});

test("Lite reading opens the local index and never exposes extraction", async () => {
  vi.mocked(api.knowledge).mockResolvedValue({ items: [], graph_revision: 0 });
  mount(true, true);
  expect(screen.getByRole("button", { name: /章节与本地索引/ })).toBeVisible();
  expect(await screen.findByRole("status")).toHaveTextContent(
    "本地结构索引已就绪：1 个章节、1 个可定位原文片段。",
  );
  expect(
    screen.queryByRole("button", { name: "生成论文知识图谱" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText(/尚未生成 AI 内容/)).toBeVisible();
  expect(api.extract).not.toHaveBeenCalled();
});
