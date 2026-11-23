import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { ModelDocumentPanel } from "./ModelDocumentPanel";
import { api, type ImportSession, type ModelDocumentSegment } from "./api";

vi.mock("./api", () => ({
  api: {
    modelDocumentParse: vi.fn(),
    modelDocumentOutputs: vi.fn(),
    updateModelDocumentSegment: vi.fn(),
    updateModelDocumentOutput: vi.fn(),
    modelChapterReadingStates: vi.fn(),
    saveModelChapterReadingState: vi.fn(),
    importSession: vi.fn(),
    job: vi.fn(),
    retryImportItem: vi.fn(),
    generateModelDocumentOutput: vi.fn(),
    repairModelDocumentOutput: vi.fn(),
    recoverModelDocumentOutput: vi.fn(),
    modelDocumentFormatRepair: vi.fn(),
    repairModelDocumentBatch: vi.fn(),
  },
}));

const segment = {
  id: "table-1",
  chapter_ref: "results",
  chapter_title: "Results",
  chapter_level: 1,
  chapter_order: 0,
  kind: "table",
  ordinal: 0,
  text: null,
  latex: null,
  mathml: null,
  raw_table_text: "A | B\n1 | 2",
  table_data: { columns: ["A", "B"], rows: [["1", "2"]] },
  locator: null,
  status: "ok",
  warnings: [],
};

function mount(
  activeView: "overview" | "reading" | "materials" = "materials",
  paperId?: string,
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const mounted = render(
    <QueryClientProvider client={client}>
      <ModelDocumentPanel
        sessionId="session-1"
        connected
        activeView={activeView}
        sessionStatus="succeeded"
        sessionError={null}
        paperId={paperId}
      />
    </QueryClientProvider>,
  );
  return { ...mounted, client };
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.importSession).mockRejectedValue(
    new Error("fixture has no running job"),
  );
  vi.mocked(api.modelChapterReadingStates).mockResolvedValue({
    parse_id: "parse-1",
    items: [],
  });
  vi.mocked(api.saveModelChapterReadingState).mockImplementation(
    async (_sessionId, value) => ({
      ...value,
      updated_at: "2026-11-18T06:00:00Z",
    }),
  );
  vi.mocked(api.modelDocumentParse).mockResolvedValue({
    id: "parse-1",
    import_session_id: "session-1",
    parse_version: "test-v1",
    modality: "pdf",
    status: "succeeded",
    warnings: [],
    error_code: null,
    error: null,
    segments: [segment],
  });
  vi.mocked(api.modelDocumentOutputs).mockResolvedValue([]);
  vi.mocked(api.recoverModelDocumentOutput).mockRejectedValue(
    new Error("fixture has no recovery"),
  );
  vi.mocked(api.modelDocumentFormatRepair).mockResolvedValue({
    available: false,
    batch_id: null,
    page_start: null,
    page_end: null,
    reason_code: "NO_FAILED_CONTRACT",
    repair_attempts: 0,
    request_count: 0,
  });
  vi.mocked(api.updateModelDocumentSegment).mockResolvedValue(segment);
});

const readingSegment = {
  ...segment,
  id: "paragraph-1",
  kind: "paragraph",
  text: "Claim concept evidence limitation.",
  table_data: null,
  raw_table_text: null,
  locator: { page_start: 2, page_end: 3 },
};

function readingParse(extra: ModelDocumentSegment[] = []) {
  return {
    id: "parse-1",
    import_session_id: "session-1",
    parse_version: "test-v1",
    modality: "pdf",
    status: "succeeded",
    warnings: [],
    error_code: null,
    error: null,
    segments: [readingSegment, ...extra],
  };
}

function completeReading() {
  return {
    id: "reading-1",
    parse_id: "parse-1",
    import_session_id: "session-1",
    item_kind: "paper_reading",
    status: "succeeded",
    error: null,
    error_code: null,
    output_json: {
      schema_version: "model-document-reading-1",
      item_kind: "paper_reading",
      paragraphs: [
        {
          paragraph_id: "paragraph-1",
          translation_zh: null,
          paragraph_function: "STATE_CLAIM" as const,
          logic_role_zh: "提出核心主张并说明支撑和局限。",
          critical_note_zh: "核查结果适用范围。",
          reading_question_zh: null,
          highlights: [
            { type: "THESIS" as const, quote_en: "Claim", occurrence_index: 0 },
            {
              type: "CONCEPT" as const,
              quote_en: "concept",
              occurrence_index: 0,
            },
            {
              type: "EVIDENCE" as const,
              quote_en: "evidence",
              occurrence_index: 0,
            },
            {
              type: "COUNTERARGUMENT" as const,
              quote_en: "limitation",
              occurrence_index: 0,
            },
          ],
          related_graph_node_ids: [],
        },
      ],
      paper_argument: {
        logic_chain_zh: ["提出核心主张", "给出结果及局限"],
        core_claim_zh: "作者的主张。",
        strong_point_zh: null,
        question_to_verify_zh: null,
      },
    },
  };
}

test("model paragraphs share translation slots, annotation legend and KaTeX rendering before notes are selected", async () => {
  const session = failedSession();
  session.status = "succeeded";
  session.plan.reading = false;
  session.items = [];
  vi.mocked(api.importSession).mockResolvedValue(session);
  vi.mocked(api.modelDocumentParse).mockResolvedValue(
    readingParse([
      {
        ...segment,
        id: "formula-1",
        kind: "formula",
        status: "needs_review",
        latex: "x_v^{(l)} = W x_v^{(l-1)}",
        table_data: null,
        raw_table_text: null,
      },
    ]),
  );
  mount("reading");
  expect(await screen.findByLabelText("正文第 1 段中文译文")).toHaveTextContent(
    "尚无本段译文",
  );
  expect(screen.getByLabelText("正文第 1 段论证批注")).toHaveTextContent(
    "全文笔记生成后",
  );
  expect(screen.getByLabelText("全文论证标注图例")).toHaveTextContent(
    "核心论点",
  );
  expect(screen.getByLabelText("全文论证标注图例")).toHaveTextContent(
    "反驳与局限",
  );
  expect(
    screen.getByText("尚无全文精读笔记，可在下方选择生成。"),
  ).toBeVisible();
  expect(screen.queryByLabelText("当次导入选择")).not.toBeInTheDocument();
  expect(
    screen.getByLabelText("LaTeX 公式").querySelector(".katex"),
  ).not.toBeNull();
  expect(screen.getByText("模型提取公式，待核对")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "查看原图区域" }),
  ).not.toBeInTheDocument();
  expect(api.generateModelDocumentOutput).not.toHaveBeenCalled();
  expect(api.modelDocumentFormatRepair).not.toHaveBeenCalled();
});

test("validated model reading displays all four argument categories and joins translations by segment identity", async () => {
  vi.mocked(api.modelDocumentParse).mockResolvedValue(readingParse());
  vi.mocked(api.modelDocumentOutputs).mockResolvedValue([
    completeReading(),
    {
      id: "translation-1",
      parse_id: "parse-1",
      import_session_id: "session-1",
      item_kind: "translation",
      status: "succeeded",
      error: null,
      error_code: null,
      output_json: {
        schema_version: "model-document-translation-1",
        translations: [
          {
            paragraph_id: "paragraph-1",
            chapter_ref: "results",
            source_text: readingSegment.text,
            translation_zh: "主张、概念、论据与局限。",
          },
        ],
      },
    },
  ]);
  const mounted = mount("reading");
  expect(
    await screen.findByText("提出核心主张并说明支撑和局限。"),
  ).toBeVisible();
  expect(screen.getByLabelText("正文第 1 段中文译文")).toHaveTextContent(
    "主张、概念、论据与局限。",
  );
  expect(screen.getByLabelText("全文论证结构")).toHaveTextContent(
    "作者的主张。",
  );
  expect(
    [...mounted.container.querySelectorAll("mark")].map(
      (mark) => mark.dataset.highlightType,
    ),
  ).toEqual(["THESIS", "CONCEPT", "EVIDENCE", "COUNTERARGUMENT"]);
});

test("legacy prose stays a legacy result and generation requires explicit network and translation choices", async () => {
  const user = userEvent.setup();
  vi.mocked(api.modelDocumentParse).mockResolvedValue(readingParse());
  vi.mocked(api.modelDocumentOutputs).mockResolvedValue([
    {
      id: "old",
      parse_id: "parse-1",
      import_session_id: "session-1",
      item_kind: "paper_reading",
      status: "succeeded",
      output_json: {
        sections: [
          { chapter_ref: "results", role: "THESIS", text: "旧章节摘要" },
        ],
      },
      error: null,
      error_code: null,
    },
  ]);
  vi.mocked(api.generateModelDocumentOutput).mockResolvedValue({
    id: "new-reading-job",
    kind: "llm_document_postprocess",
    project_id: "project",
    status: "queued",
    stage: "queued",
    attempt: 1,
    error: null,
    result: null,
    created_at: "now",
    updated_at: "now",
  });
  const mounted = mount("reading");
  const generate = await screen.findByRole("button", {
    name: "重新生成全文精读笔记",
  });
  expect(generate).toBeDisabled();
  expect(screen.getByText(/旧版章节摘要已保留/)).toBeVisible();
  expect(mounted.container.querySelector("mark")).toBeNull();
  await user.click(
    screen.getByRole("checkbox", { name: /允许本次发送模型提取内容/ }),
  );
  await user.click(
    screen.getByRole("checkbox", { name: "同时生成逐段中文翻译" }),
  );
  await user.click(generate);
  await waitFor(() =>
    expect(api.generateModelDocumentOutput).toHaveBeenCalledExactlyOnceWith(
      "session-1",
      "paper_reading",
      {
        allow_network: true,
        translation_mode: "full",
        force_regenerate: true,
      },
    ),
  );
});

test("failed postprocessing exposes one explicit paid format repair without automatically calling it", async () => {
  const user = userEvent.setup();
  vi.mocked(api.modelDocumentParse).mockResolvedValue(readingParse());
  vi.mocked(api.modelDocumentOutputs).mockResolvedValue([
    {
      id: "bad-output",
      parse_id: "parse-1",
      import_session_id: "session-1",
      item_kind: "paper_reading",
      status: "failed",
      output_json: null,
      error: "paragraphs[0].highlights 无效",
      error_code: "MODEL_DOCUMENT_POSTPROCESS_CONTRACT_FAILED",
      format_repair_available: true,
    },
  ]);
  vi.mocked(api.repairModelDocumentOutput).mockResolvedValue({
    id: "repair-job",
    kind: "llm_document_postprocess",
    project_id: "project",
    status: "queued",
    stage: "queued",
    attempt: 1,
    error: null,
    result: null,
    created_at: "now",
    updated_at: "now",
  });
  mount("reading");
  const repair = await screen.findByRole("button", {
    name: "调用模型分析并修复此结果",
  });
  expect(repair).toBeDisabled();
  expect(api.repairModelDocumentOutput).not.toHaveBeenCalled();
  await user.click(
    screen.getByRole("checkbox", {
      name: /允许额外一次模型请求，分析并修复此失败结果/,
    }),
  );
  await user.click(repair);
  await waitFor(() =>
    expect(api.repairModelDocumentOutput).toHaveBeenCalledExactlyOnceWith(
      "session-1",
      "bad-output",
    ),
  );
  expect(repair).toBeDisabled();
});

test("local recovery is explicit, keeps the failed response, and leaves only independently validated translation visible", async () => {
  const user = userEvent.setup();
  vi.mocked(api.modelDocumentParse).mockResolvedValue(readingParse());
  const failed = {
    id: "bad-output",
    parse_id: "parse-1",
    import_session_id: "session-1",
    item_kind: "paper_reading",
    status: "failed",
    output_json: null,
    error: "paragraphs[0].highlights 无效",
    error_code: "MODEL_DOCUMENT_POSTPROCESS_CONTRACT_FAILED",
    format_repair_available: true,
    local_recovery_available: true,
  };
  const partial = {
    ...completeReading(),
    id: "recovered-output",
    status: "partial",
    recovery_summary: { normalized_types: 11, unresolved_highlights: 2 },
  };
  expect(partial.output_json.paragraphs[0].translation_zh).toBeNull();
  const translation = {
    id: "translation-1",
    parse_id: "parse-1",
    import_session_id: "session-1",
    item_kind: "translation",
    status: "succeeded",
    error: null,
    error_code: null,
    output_json: {
      schema_version: "model-document-translation-1",
      translations: [
        {
          paragraph_id: "paragraph-1",
          chapter_ref: "results",
          source_text: readingSegment.text,
          translation_zh: "已通过校验的中文翻译。",
        },
      ],
    },
  };
  vi.mocked(api.modelDocumentOutputs)
    .mockResolvedValueOnce([failed, translation])
    .mockResolvedValue([failed, partial, translation]);
  vi.mocked(api.recoverModelDocumentOutput).mockResolvedValue(partial);

  mount("reading", "paper-1");
  const recover = await screen.findByRole("button", {
    name: "本地恢复可验证的精读标记（不调用模型）",
  });
  expect(recover).toBeEnabled();
  expect(api.recoverModelDocumentOutput).not.toHaveBeenCalled();
  expect(api.repairModelDocumentOutput).not.toHaveBeenCalled();

  await user.click(recover);
  await waitFor(() =>
    expect(api.recoverModelDocumentOutput).toHaveBeenCalledExactlyOnceWith(
      "paper-1",
      "bad-output",
    ),
  );
  expect(await screen.findByText(/精读标记部分可用/)).toHaveTextContent(
    "已隐藏2处引文不匹配的标记",
  );
  expect(screen.getByText(/11处标记类型已按契约规范化/)).toBeVisible();
  expect(screen.getByLabelText("正文第 1 段中文译文")).toHaveTextContent(
    "已通过校验的中文翻译。",
  );
  expect(recover).toBeDisabled();
  await user.click(recover);
  expect(api.recoverModelDocumentOutput).toHaveBeenCalledExactlyOnceWith(
    "paper-1",
    "bad-output",
  );
  expect(screen.getByLabelText("生成内容校验失败")).toHaveTextContent(
    "paragraphs[0].highlights 无效",
  );
  expect(api.repairModelDocumentOutput).not.toHaveBeenCalled();
  expect(api.generateModelDocumentOutput).not.toHaveBeenCalled();
  expect(api.modelDocumentFormatRepair).not.toHaveBeenCalled();
});

test("local recovery stays hidden when the failed output has no recoverable payload", async () => {
  vi.mocked(api.modelDocumentParse).mockResolvedValue(readingParse());
  vi.mocked(api.modelDocumentOutputs).mockResolvedValue([
    {
      id: "bad-output",
      parse_id: "parse-1",
      import_session_id: "session-1",
      item_kind: "paper_reading",
      status: "failed",
      output_json: null,
      error: "没有可用的已保存响应",
      error_code: "MODEL_DOCUMENT_POSTPROCESS_CONTRACT_FAILED",
      format_repair_available: false,
      local_recovery_available: false,
    },
  ]);

  mount("reading", "paper-1");

  expect(await screen.findByLabelText("生成内容校验失败")).toHaveTextContent(
    "没有可用的已保存响应",
  );
  expect(
    screen.queryByRole("button", {
      name: "本地恢复可验证的精读标记（不调用模型）",
    }),
  ).not.toBeInTheDocument();
  expect(api.recoverModelDocumentOutput).not.toHaveBeenCalled();
  expect(api.generateModelDocumentOutput).not.toHaveBeenCalled();
});

test("local recovery errors are shown without invoking model repair", async () => {
  const user = userEvent.setup();
  vi.mocked(api.modelDocumentParse).mockResolvedValue(readingParse());
  vi.mocked(api.modelDocumentOutputs).mockResolvedValue([
    {
      id: "bad-output",
      parse_id: "parse-1",
      import_session_id: "session-1",
      item_kind: "paper_reading",
      status: "failed",
      output_json: null,
      error: "paragraphs[0].highlights 无效",
      error_code: "MODEL_DOCUMENT_POSTPROCESS_CONTRACT_FAILED",
      format_repair_available: false,
      local_recovery_available: true,
    },
  ]);

  mount("reading", "paper-1");
  await user.click(
    await screen.findByRole("button", {
      name: "本地恢复可验证的精读标记（不调用模型）",
    }),
  );

  expect(await screen.findByText("fixture has no recovery")).toBeVisible();
  expect(screen.getByLabelText("生成内容校验失败")).toHaveTextContent(
    "paragraphs[0].highlights 无效",
  );
  expect(api.recoverModelDocumentOutput).toHaveBeenCalledExactlyOnceWith(
    "paper-1",
    "bad-output",
  );
  expect(api.generateModelDocumentOutput).not.toHaveBeenCalled();
  expect(api.repairModelDocumentOutput).not.toHaveBeenCalled();
});

test("a failed batch offers a separately confirmed single format repair and preserves parse retry", async () => {
  const user = userEvent.setup();
  const session = failedSession();
  session.status = "failed";
  session.items[0].status = "failed";
  vi.mocked(api.importSession).mockResolvedValue(session);
  vi.mocked(api.job).mockRejectedValue(new Error("fixture job unavailable"));
  vi.mocked(api.modelDocumentParse).mockResolvedValue({
    ...readingParse(),
    status: "failed",
    error: "批次字段校验失败",
    error_code: "DOCUMENT_BATCH_CONTRACT_FAILED",
  });
  vi.mocked(api.modelDocumentFormatRepair).mockResolvedValue({
    available: true,
    batch_id: "batch-2",
    page_start: 5,
    page_end: 9,
    reason_code: "CONTRACT_FAILED",
    repair_attempts: 0,
    request_count: 1,
  });
  vi.mocked(api.repairModelDocumentBatch).mockResolvedValue({
    id: "batch-repair-job",
    kind: "zotero_import",
    project_id: "project",
    status: "queued",
    stage: "queued",
    attempt: 2,
    error: null,
    result: null,
    created_at: "now",
    updated_at: "now",
  });
  mount("reading");
  const repair = await screen.findByRole("button", {
    name: "调用模型分析并修复本批格式",
  });
  expect(screen.getByLabelText("失败批次格式修复")).toHaveTextContent(
    "第 5–9 页",
  );
  expect(repair).toBeDisabled();
  expect(api.repairModelDocumentBatch).not.toHaveBeenCalled();
  await user.click(
    screen.getByRole("checkbox", { name: /允许额外一次模型请求修复本批格式/ }),
  );
  await user.click(repair);
  await waitFor(() =>
    expect(api.repairModelDocumentBatch).toHaveBeenCalledExactlyOnceWith(
      "session-1",
    ),
  );
  expect(api.retryImportItem).not.toHaveBeenCalled();
});

test("a translation for a different source text is not attached to the current model paragraph", async () => {
  vi.mocked(api.modelDocumentParse).mockResolvedValue(readingParse());
  vi.mocked(api.modelDocumentOutputs).mockResolvedValue([
    {
      id: "translation-1",
      parse_id: "parse-1",
      import_session_id: "session-1",
      item_kind: "translation",
      status: "succeeded",
      error: null,
      error_code: null,
      output_json: {
        schema_version: "model-document-translation-1",
        translations: [
          {
            paragraph_id: "paragraph-1",
            chapter_ref: "results",
            source_text: "Text before a source edit.",
            translation_zh: "不应显示的旧译文。",
          },
        ],
      },
    },
  ]);
  mount("reading");
  expect(await screen.findByLabelText("正文第 1 段中文译文")).toHaveTextContent(
    "尚无本段译文",
  );
  expect(screen.queryByText("不应显示的旧译文。")).not.toBeInTheDocument();
});

test("the newest validated notes and translations stay visible after a newer regeneration fails", async () => {
  vi.mocked(api.modelDocumentParse).mockResolvedValue(readingParse());
  const previous = completeReading();
  previous.output_json.paragraphs[0].logic_role_zh = "旧版批注。";
  const latest = completeReading();
  latest.id = "reading-2";
  latest.output_json.paragraphs[0].logic_role_zh = "最新已通过校验的批注。";
  const translation = (id: string, text: string) => ({
    id,
    parse_id: "parse-1",
    import_session_id: "session-1",
    item_kind: "translation",
    status: "succeeded",
    error: null,
    error_code: null,
    output_json: {
      schema_version: "model-document-translation-1",
      translations: [
        {
          paragraph_id: "paragraph-1",
          chapter_ref: "results",
          source_text: readingSegment.text,
          translation_zh: text,
        },
      ],
    },
  });
  vi.mocked(api.modelDocumentOutputs).mockResolvedValue([
    previous,
    translation("old-translation", "旧版译文。"),
    latest,
    translation("new-translation", "最新已通过校验的译文。"),
    {
      ...latest,
      id: "failed-newest",
      status: "failed",
      output_json: null,
      error: "重新生成失败，旧结果保留。",
      error_code: "MODEL_DOCUMENT_POSTPROCESS_FAILED",
    },
  ]);
  mount("reading");
  expect(await screen.findByText("最新已通过校验的批注。")).toBeVisible();
  expect(screen.getByLabelText("正文第 1 段中文译文")).toHaveTextContent(
    "最新已通过校验的译文。",
  );
  expect(screen.queryByText("旧版批注。")).not.toBeInTheDocument();
  expect(screen.queryByText("旧版译文。")).not.toBeInTheDocument();
  expect(screen.getByLabelText("生成内容校验失败")).toHaveTextContent(
    "重新生成失败，旧结果保留。",
  );
});

test("adding a translation queues only translation and keeps validated reading notes", async () => {
  const user = userEvent.setup();
  vi.mocked(api.modelDocumentParse).mockResolvedValue(readingParse());
  vi.mocked(api.modelDocumentOutputs).mockResolvedValue([completeReading()]);
  const session = failedSession();
  vi.mocked(api.importSession).mockResolvedValue({ ...session, items: [] });
  const job = {
    id: "translation-job",
    kind: "llm_document_postprocess",
    project_id: "project",
    status: "queued" as const,
    stage: "queued",
    attempt: 1,
    error: null,
    result: null,
    created_at: "now",
    updated_at: "now",
  };
  vi.mocked(api.generateModelDocumentOutput).mockImplementation(async () => {
    vi.mocked(api.importSession).mockResolvedValue({
      ...session,
      status: "queued",
      items: [
        {
          ...session.items[0],
          item_kind: "translation",
          status: "queued",
          job_id: job.id,
        },
      ],
    });
    return job;
  });
  mount("reading");
  await user.click(
    await screen.findByText("更多精读操作", { selector: "summary" }),
  );
  const translate = await screen.findByRole("button", {
    name: "仅补生成中文译文",
  });
  expect(translate).toBeDisabled();
  await user.click(
    screen.getByRole("checkbox", { name: /允许本次发送模型提取内容/ }),
  );
  await user.click(translate);
  await waitFor(() =>
    expect(api.generateModelDocumentOutput).toHaveBeenCalledExactlyOnceWith(
      "session-1",
      "translation",
      {
        allow_network: true,
        translation_mode: "full",
        force_regenerate: true,
      },
    ),
  );
  expect(screen.getByText("提出核心主张并说明支撑和局限。")).toBeVisible();
  expect(await screen.findByText("任务进行中：逐段中文翻译")).toBeVisible();
});

function failedSession(allowNetwork = true): ImportSession {
  return {
    id: "session-1",
    project_id: "project",
    source_kind: "zotero",
    selection_id: "selection",
    source_snapshot: {},
    plan: {
      overview: false,
      reading: true,
      translation_mode: "none",
      modality: "auto",
      require_multimodal: false,
      allow_network: allowNetwork,
    },
    status: "running",
    error: null,
    created_at: "2026-11-18T00:00:00Z",
    updated_at: "2026-11-18T00:00:00Z",
    items: [
      {
        id: "item",
        item_kind: "document_parse",
        status: "running",
        config: {},
        job_id: "parse-job",
        attempt: 1,
        error: null,
        result: null,
        created_at: "2026-11-18T00:00:00Z",
        updated_at: "2026-11-18T00:00:00Z",
      },
    ],
  };
}

test("workspace shows only active task names and clears the status after completion", async () => {
  const session = failedSession();
  const parseItem = { ...session.items[0], status: "succeeded" as const };
  const readingItem = {
    ...parseItem,
    id: "reading",
    item_kind: "paper_reading" as const,
    status: "running" as const,
    job_id: "reading-job",
  };
  const translationItem = {
    ...parseItem,
    id: "translation",
    item_kind: "translation" as const,
    status: "queued" as const,
    job_id: "translation-job",
  };
  const current = {
    ...session,
    status: "failed" as const,
    items: [
      parseItem,
      {
        ...parseItem,
        id: "overview",
        item_kind: "paper_overview" as const,
        status: "failed" as const,
      },
      readingItem,
      translationItem,
    ],
  };
  vi.mocked(api.importSession).mockResolvedValue(current);
  vi.mocked(api.job).mockResolvedValue({
    id: parseItem.job_id!,
    kind: "llm_document_parse",
    project_id: session.project_id,
    status: "succeeded",
    stage: "completed",
    attempt: 1,
    error: null,
    result: {
      document_request: {
        elapsed_seconds: 34,
        read_timeout_seconds: 600,
        total_timeout_seconds: 1800,
      },
      document_batches: {
        total: 3,
        completed: 3,
        requests_sent: 8,
        request_budget: 8,
        phase: "completed",
      },
    },
    created_at: "now",
    updated_at: "now",
  });
  const { client } = mount("reading");
  const status = "任务进行中：全文精读笔记生成、逐段中文翻译";
  expect(await screen.findByText(status)).toBeVisible();
  expect(screen.queryByLabelText("当次导入选择")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("文档请求状态")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("文档批次状态")).not.toBeInTheDocument();
  vi.mocked(api.importSession).mockResolvedValue({
    ...current,
    items: current.items.map((item) => ({
      ...item,
      status: item.status === "failed" ? "failed" : "succeeded",
    })),
  });
  void client.invalidateQueries({
    queryKey: ["model-document-import-session", session.id],
  });
  await waitFor(() =>
    expect(screen.queryByText(status)).not.toBeInTheDocument(),
  );
});

test.each([
  ["paper_overview", "论文概览生成"],
  ["paper_card_set", "论文卡片集生成"],
] as const)(
  "workspace checks the exact active overview job subtype %s",
  async (readingTask, name) => {
    const session = failedSession();
    const jobId = "overview-job";
    vi.mocked(api.importSession).mockResolvedValue({
      ...session,
      status: "running",
      items: [
        { ...session.items[0], item_kind: "paper_overview", job_id: jobId },
      ],
    });
    vi.mocked(api.job).mockResolvedValue({
      id: jobId,
      kind: "llm_document_postprocess",
      project_id: session.project_id,
      status: "running",
      stage: "generating",
      attempt: 1,
      error: null,
      result: null,
      reading_task: readingTask,
      created_at: "now",
      updated_at: "now",
    });
    mount("reading");
    await waitFor(() => expect(api.job).toHaveBeenCalledExactlyOnceWith(jobId));
    expect(await screen.findByText(`任务进行中：${name}`)).toBeVisible();
  },
);

test("a failed job replaces stale parsing status and only an explicit retry requeues it", async () => {
  const user = userEvent.setup();
  const session = failedSession();
  vi.mocked(api.importSession).mockResolvedValue(session);
  const job = {
    id: "parse-job",
    kind: "zotero_import",
    project_id: "project",
    status: "failed" as const,
    stage: "preparing_provider",
    attempt: 1,
    error: "MODEL_DOCUMENT_PROVIDER_FAILED · 解析失败",
    result: null,
    created_at: "2026-11-18T00:00:00Z",
    updated_at: "2026-11-18T00:00:01Z",
  };
  vi.mocked(api.job).mockResolvedValue(job);
  vi.mocked(api.modelDocumentParse).mockResolvedValue({
    id: "parse-1",
    import_session_id: "session-1",
    parse_version: "test-v1",
    modality: "pdf",
    status: "running",
    warnings: [],
    error_code: null,
    error: null,
    segments: [],
  });
  mount();
  const retry = await screen.findByRole("button", { name: "重试模型解析" });
  expect(screen.getByText("模型章节解析：失败")).toBeVisible();
  expect(screen.getByRole("alert")).toHaveTextContent("解析失败");
  expect(screen.queryByText("准备文档解析模型")).not.toBeInTheDocument();
  expect(api.retryImportItem).not.toHaveBeenCalled();
  const queued = {
    ...session,
    status: "queued" as const,
    items: session.items.map((item) => ({
      ...item,
      status: "queued" as const,
    })),
  };
  vi.mocked(api.retryImportItem).mockResolvedValue(queued);
  vi.mocked(api.importSession).mockResolvedValue(queued);
  vi.mocked(api.job).mockResolvedValue({
    ...job,
    status: "queued",
    error: null,
  });
  await user.click(retry);
  await waitFor(() =>
    expect(api.retryImportItem).toHaveBeenCalledExactlyOnceWith(
      "session-1",
      "document_parse",
    ),
  );
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "重试模型解析" }),
    ).not.toBeInTheDocument(),
  );
});

test("retry does not add network consent to an unauthorized import plan", async () => {
  vi.mocked(api.importSession).mockResolvedValue(failedSession(false));
  vi.mocked(api.job).mockResolvedValue({
    id: "parse-job",
    kind: "zotero_import",
    project_id: "project",
    status: "failed",
    stage: null,
    attempt: 1,
    error: "Needs network consent",
    result: null,
    created_at: "2026-11-18T00:00:00Z",
    updated_at: "2026-11-18T00:00:01Z",
  });
  mount();
  expect(await screen.findByText(/当前导入计划没有联网授权/)).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "重试模型解析" }),
  ).not.toBeInTheDocument();
  expect(api.retryImportItem).not.toHaveBeenCalled();
});

test.each([true, false, "true"])(
  "boundary HTTP 400 offers compatibility continuation only when enabled %s",
  async (available) => {
    const user = userEvent.setup();
    const session = failedSession();
    vi.mocked(api.importSession).mockResolvedValue(session);
    vi.mocked(api.job).mockResolvedValue({
      id: "parse-job",
      kind: "llm_document_parse",
      project_id: "project",
      status: "failed",
      stage: "failed",
      attempt: 3,
      error: "MODEL_DOCUMENT_PROVIDER_HTTP_ERROR",
      result: {
        document_request: {
          http_status: 400,
          response_body: "private provider response",
        },
        document_batches: {
          total: 3,
          completed: 3,
          current: 1,
          current_kind: "boundary",
          boundaries_total: 2,
          compatibility_retry_available: available,
        },
      },
      created_at: "2026-11-18T00:00:00Z",
      updated_at: "2026-11-18T00:00:01Z",
    });
    mount();
    expect(
      await screen.findByText(/相同 HTTP 400 请先停止重复点击/),
    ).toHaveTextContent("安装修复版后只继续边界复核，保留已完成的正文批次");
    expect(screen.queryByText(/private provider/)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "重试模型解析" }),
    ).not.toBeInTheDocument();
    expect(api.retryImportItem).not.toHaveBeenCalled();
    if (available === true) {
      vi.mocked(api.retryImportItem).mockResolvedValue({
        ...session,
        status: "queued",
      });
      await user.click(
        screen.getByRole("button", {
          name: "确认继续边界复核（可能收费）",
        }),
      );
      await waitFor(() =>
        expect(api.retryImportItem).toHaveBeenCalledExactlyOnceWith(
          "session-1",
          "document_parse",
        ),
      );
    } else {
      expect(
        screen.queryByRole("button", {
          name: "确认继续边界复核（可能收费）",
        }),
      ).not.toBeInTheDocument();
    }
  },
);

test.each([true, false, "true"])(
  "publication failure offers only a strictly available local publication retry %s",
  async (available) => {
    const user = userEvent.setup();
    const session = failedSession();
    vi.mocked(api.importSession).mockResolvedValue(session);
    vi.mocked(api.job).mockResolvedValue({
      id: "parse-job",
      kind: "llm_document_parse",
      project_id: "project",
      status: "failed",
      stage: "failed",
      attempt: 6,
      error: "MODEL_DOCUMENT_PUBLISH_INTEGRITY_ERROR",
      result: {
        document_batches: {
          total: 3,
          completed: 3,
          boundaries_total: 2,
          boundaries_completed: 2,
          current_kind: "publication",
          phase: "publication_failed",
          publication_retry_available: available,
        },
      },
      created_at: "2026-11-18T00:00:00Z",
      updated_at: "2026-11-18T00:00:01Z",
    });
    mount();
    expect(
      await screen.findByText(/章节发布未完成，已校验批次保留/),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "重试模型解析" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/修改模型能力或解析模型后/),
    ).not.toBeInTheDocument();
    expect(api.retryImportItem).not.toHaveBeenCalled();
    if (available === true) {
      expect(
        screen.getByText(/不重发已校验批次，也不重新上传 PDF/),
      ).toBeVisible();
      expect(
        screen.getByText(
          /原计划选中的概览或精读任务仍会继续，可能产生模型请求和费用/,
        ),
      ).toBeVisible();
      vi.mocked(api.retryImportItem).mockResolvedValue({
        ...session,
        status: "queued",
      });
      await user.click(
        screen.getByRole("button", {
          name: "仅重新发布章节（不重发批次）",
        }),
      );
      await waitFor(() =>
        expect(api.retryImportItem).toHaveBeenCalledExactlyOnceWith(
          "session-1",
          "document_parse",
        ),
      );
    } else {
      expect(screen.getByText(/当前任务已无可用的仅发布恢复/)).toBeVisible();
      expect(
        screen.queryByRole("button", {
          name: "仅重新发布章节（不重发批次）",
        }),
      ).not.toBeInTheDocument();
    }
  },
);

test("local publication recovery does not require adding network consent", async () => {
  vi.mocked(api.importSession).mockResolvedValue(failedSession(false));
  vi.mocked(api.job).mockResolvedValue({
    id: "parse-job",
    kind: "llm_document_parse",
    project_id: "project",
    status: "failed",
    stage: "failed",
    attempt: 4,
    error: "MODEL_DOCUMENT_PUBLISH_INTEGRITY_ERROR",
    result: {
      document_batches: {
        phase: "publication_failed",
        publication_retry_available: true,
      },
    },
    created_at: "2026-11-18T00:00:00Z",
    updated_at: "2026-11-18T00:00:01Z",
  });
  mount();
  expect(
    await screen.findByRole("button", {
      name: "仅重新发布章节（不重发批次）",
    }),
  ).toBeVisible();
  expect(
    screen.queryByText(/当前导入计划没有联网授权/),
  ).not.toBeInTheDocument();
  expect(api.retryImportItem).not.toHaveBeenCalled();
});

test("full reading groups source chapters and saves completed chapters for sidebar continuation", async () => {
  const user = userEvent.setup();
  vi.mocked(api.modelDocumentParse).mockResolvedValue({
    id: "parse-1",
    import_session_id: "session-1",
    parse_version: "test-v1",
    modality: "pdf",
    status: "succeeded",
    warnings: [],
    error_code: null,
    error: null,
    segments: [
      {
        ...segment,
        id: "intro",
        chapter_ref: "intro",
        chapter_title: "1 Introduction",
        kind: "paragraph",
        text: "Original introduction",
        raw_table_text: null,
        table_data: null,
      },
      {
        ...segment,
        id: "context",
        chapter_ref: "context",
        chapter_title: "1.1 Context",
        chapter_level: 2,
        chapter_order: 1,
        kind: "paragraph",
        text: "Original context",
        raw_table_text: null,
        table_data: null,
      },
      {
        ...segment,
        id: "context-table",
        chapter_ref: "context",
        chapter_title: "1.1 Context",
        chapter_level: 2,
        chapter_order: 1,
        ordinal: 1,
        raw_table_text: "Child chapter table material",
        table_data: null,
      },
      {
        ...segment,
        id: "results",
        chapter_order: 2,
        chapter_title: "2 Results",
      },
    ],
  });
  mount("reading");
  const controls = await screen.findByRole("group", {
    name: "1 Introduction 阅读状态",
  });
  await waitFor(() =>
    expect(
      within(controls).getByRole("button", { name: "已读完" }),
    ).toBeEnabled(),
  );
  expect(
    screen.queryByRole("group", { name: "1.1 Context 阅读状态" }),
  ).not.toBeInTheDocument();
  const footer = controls.closest("footer")!;
  const chapter = footer.closest(".model-reading-chapter")! as HTMLElement;
  expect(chapter.lastElementChild).toBe(footer);
  expect(chapter.querySelector("header [role=group]")).toBeNull();
  expect(within(chapter).getByText("Original context")).toBeVisible();
  expect(
    within(chapter).getByText("Child chapter table material"),
  ).toBeInTheDocument();
  expect(footer.previousElementSibling).toContainElement(
    within(chapter).getByText("Child chapter table material"),
  );
  await user.click(within(controls).getByRole("button", { name: "已读完" }));
  await waitFor(() =>
    expect(api.saveModelChapterReadingState).toHaveBeenCalledWith("session-1", {
      parse_id: "parse-1",
      chapter_ref: "intro",
      progress: "COMPLETED",
    }),
  );
  expect(await screen.findByText("已读完 1 / 2 个大章节")).toBeVisible();
  expect(
    screen.getByRole("button", { name: "继续阅读：2 Results" }),
  ).toBeVisible();
  const directory = screen.getByRole("navigation", { name: "文章目录" });
  expect(
    within(directory).getByRole("button", { name: "1 Introduction" }),
  ).toHaveTextContent("已读完");
  expect(screen.getByText("Original context")).toBeVisible();
});

test("table editor reports invalid JSON and saves the corrected structure", async () => {
  const user = userEvent.setup();
  mount();

  await user.click(
    await screen.findByRole("button", { name: "编辑table内容" }),
  );
  const tableEditor = screen.getByLabelText("结构化表格 JSON");
  fireEvent.change(tableEditor, { target: { value: "{" } });
  await user.click(screen.getByRole("button", { name: "保存解析内容" }));

  expect(
    await screen.findByText("结构化表格必须是有效的 JSON 对象或 null。"),
  ).toHaveAttribute("role", "alert");
  expect(api.updateModelDocumentSegment).not.toHaveBeenCalled();

  fireEvent.change(tableEditor, {
    target: { value: '{"columns":["A"],"rows":[["1"]]}' },
  });
  await user.click(screen.getByRole("button", { name: "保存解析内容" }));

  await waitFor(() =>
    expect(api.updateModelDocumentSegment).toHaveBeenCalledWith(
      "session-1",
      "table-1",
      expect.objectContaining({
        table_data: { columns: ["A"], rows: [["1"]] },
      }),
    ),
  );
});

test.each([4, 5, 6])(
  "overview avoids the generic reading format repair controls, version %s",
  async (version) => {
    vi.mocked(api.modelDocumentOutputs).mockResolvedValue([
      {
        id: "failed-overview",
        parse_id: "parse-1",
        import_session_id: "session-1",
        item_kind: "paper_overview",
        status: "failed",
        output_json: null,
        error: "合成校验失败",
        error_code: "MODEL_DOCUMENT_POSTPROCESS_CONTRACT_FAILED",
        format_repair_available: true,
        usage: { contract_version: version },
      },
    ]);
    mount("overview");
    await screen.findByRole("region", { name: "模型文档解析结果" });
    expect(
      screen.queryByRole("button", { name: "调用模型分析并修复此结果" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("合成校验失败")).not.toBeInTheDocument();
    expect(api.repairModelDocumentOutput).not.toHaveBeenCalled();
  },
);
