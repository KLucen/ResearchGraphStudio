import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { P5Workspace } from "./P5Workspace";
import { api, type PaperList } from "./api";
import {
  p5Api,
  type LintRun,
  type LintIssue,
  type WikiPageView,
  type WorkflowView,
  type PersonalSource,
  type ExternalDocument,
} from "./p5Api";

vi.mock("./api", () => ({
  api: {
    papers: vi.fn(),
    preview: vi.fn(),
    jobAction: vi.fn(),
    noteRoots: vi.fn(),
    notePermissions: vi.fn(),
    notes: vi.fn(),
    noteAction: vi.fn(),
    authorizeNotes: vi.fn(),
  },
}));
vi.mock("./p5Api", () => ({
  emptyPersonalSelection: () => ({
    version: "p5-personal-sources-1",
    note_ids: [],
    annotation_ids: [],
    external_version_ids: [],
  }),
  p5Api: {
    lintDocuments: vi.fn(),
    personalSources: vi.fn(),
    annotationGrant: vi.fn(),
    externalDocuments: vi.fn(),
    externalDocument: vi.fn(),
    externalPreview: vi.fn(),
    externalRegister: vi.fn(),
    lintRuns: vi.fn(),
    lintStart: vi.fn(),
    lintRun: vi.fn(),
    lintAdvance: vi.fn(),
    lintCancel: vi.fn(),
    lintIssues: vi.fn(),
    lintDependencies: vi.fn(),
    rebuildDependencies: vi.fn(),
    wikiPages: vi.fn(),
    wikiPage: vi.fn(),
    wikiSave: vi.fn(),
    wikiRoots: vi.fn(),
    authorizeOutput: vi.fn(),
    revokeOutput: vi.fn(),
    wikiPublish: vi.fn(),
    wikiRecover: vi.fn(),
    wikiPublications: vi.fn(),
    inspectWikiFile: vi.fn(),
    workflows: vi.fn(),
    prepare: vi.fn(),
    workflow: vi.fn(),
    generate: vi.fn(),
    materialize: vi.fn(),
    evidence: vi.fn(),
  },
}));

const run: LintRun = {
  id: "lint-1",
  project_id: "p",
  status: "completed",
  scope: { paper_ids: [], document_ids: [], include_personal: false },
  rule_version: "rules-1",
  event_sequence: 0,
  input_hash: "h",
  total: 25,
  processed: 25,
  progress: 1,
  counts: { error: 1, warning: 0, info: 0 },
  diff: { new: 1, persistent: 0, resolved: 0 },
  previous_run_id: null,
  errors: [],
  created_at: "2026-11-05T00:00:00Z",
  updated_at: "2026-11-05T00:00:00Z",
  finished_at: "2026-11-05T00:00:00Z",
};
const issue: LintIssue = {
  id: "issue-1",
  fingerprint: "f",
  code: "SOURCE_CHANGED",
  rule_version: "rules-1",
  severity: "error",
  category: "evidence",
  object_type: "evidence",
  object_id: "evidence-1",
  paper_id: "paper-1",
  location: {
    evidence_id: "evidence-1",
    node_id: "node-1",
    page_id: "wiki-1",
    page_index: 2,
  },
  message: "来源文件已变化",
  suggestion: "重新核验来源，不覆盖旧证据。",
  lifecycle: "new",
  deterministic: true,
};
const draft: WikiPageView = {
  page_id: "wiki-1",
  title: "合成主题整理",
  version_id: "version-1",
  head_version_id: "version-1",
  saved_version_id: null,
  revision: 1,
  state: "draft",
  content_state: "valid",
  content_hash: "a".repeat(64),
  markdown: "# 合成主题整理\n\n有据内容",
  diff: "+有据内容",
  sections: [
    {
      section_id: "section-1",
      heading: "方法与条件",
      text: "合成实验仅在指定条件下有效。",
      attribution: "paper_author",
      dependencies: [
        {
          type: "evidence",
          id: "evidence-1",
          quote: "Synthetic result under conditions.",
        },
      ],
      caveats: ["不外推其他条件"],
      conditions: [
        { dimension: "温度", state: "known", value: "20", unit: "C" },
      ],
      stale: false,
    },
  ],
  versions: [
    {
      version_id: "version-1",
      revision: 1,
      state: "draft",
      content_hash: "a".repeat(64),
    },
  ],
  file: { state: "not_exported" },
};
const workflow: WorkflowView = {
  id: "workflow-1",
  kind: "wiki_synthesis",
  status: "succeeded",
  input_hash: "frozen-input",
  job_id: "job-1",
  can_continue: false,
  error_code: null,
  error: null,
  question: "冻结的原主题",
  created_at: "2026-11-05T00:00:00Z",
  model_runs: [],
  result: { draft: { title: draft.title, passages: draft.sections } },
};
const root = {
  root_id: "root-1",
  path: "synthetic-output",
  active: true,
  revision: 1,
};

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  vi.mocked(p5Api.lintDocuments).mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 10,
  });
  vi.mocked(p5Api.personalSources).mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 10,
  });
  vi.mocked(api.noteRoots).mockResolvedValue([]);
  vi.mocked(api.notes).mockResolvedValue([]);
  vi.mocked(p5Api.externalDocuments).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(api.papers).mockResolvedValue({
    items: [
      { id: "paper-1", title: "合成论文一" },
      { id: "paper-2", title: "合成论文二" },
    ],
    next_cursor: null,
  } as PaperList);
  vi.mocked(p5Api.lintRuns).mockResolvedValue({
    items: [run],
    total: 1,
    page: 1,
    page_size: 10,
  });
  vi.mocked(p5Api.lintRun).mockResolvedValue(run);
  vi.mocked(p5Api.lintIssues).mockResolvedValue({
    items: [issue],
    total: 1,
    page: 1,
    page_size: 10,
  });
  vi.mocked(p5Api.workflows).mockResolvedValue({ items: [] });
  vi.mocked(p5Api.workflow).mockResolvedValue(workflow);
  vi.mocked(p5Api.wikiPages).mockResolvedValue({
    items: [],
    total: 0,
    offset: 0,
    limit: 10,
  });
  vi.mocked(p5Api.wikiPublications).mockResolvedValue({
    items: [],
    total: 0,
    offset: 0,
    limit: 10,
  });
  vi.mocked(p5Api.lintDependencies).mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 10,
  });
  vi.mocked(p5Api.wikiRoots).mockResolvedValue({ items: [] });
  vi.mocked(p5Api.wikiPage).mockResolvedValue(draft);
  vi.mocked(p5Api.wikiPublish).mockResolvedValue({
    operation_id: "publication-1",
    state: "succeeded",
  });
});
function mount(mode: "lint" | "wiki" = "lint", connected = true) {
  const onGraphNode = vi.fn(),
    onWikiPage = vi.fn();
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <P5Workspace
        projectId="p"
        connected={connected}
        mode={mode}
        onGraphNode={onGraphNode}
        onWikiPage={onWikiPage}
      />
    </QueryClientProvider>,
  );
  return { ...view, onGraphNode, onWikiPage, client };
}
function activeWiki(value = draft) {
  localStorage.setItem("rgs.wiki.active.p", value.page_id);
  vi.mocked(p5Api.wikiPage).mockResolvedValue(value);
}

const personalCatalog: PersonalSource[] = [
  {
    type: "note",
    id: "note-1",
    label: "个人方法笔记",
    text: "个人推测",
    sha256: "n",
    allow_model: true,
    authorization_revision: 1,
    root_id: "read-root",
  },
  {
    type: "annotation",
    id: "annotation-1",
    label: "论文评论",
    text: "个人评论内容",
    highlight: "已有原文高亮",
    sha256: "a",
    allow_model: false,
    authorization_revision: 2,
    evidence_id: "evidence-1",
  },
  {
    type: "external",
    id: "external-v1",
    label: "外部材料",
    text: "未核验外部内容",
    sha256: "e",
    allow_model: true,
    authorization_revision: 1,
    root_id: "read-root",
  },
];
const externalDocument: ExternalDocument = {
  document_id: "external-1",
  version_id: "external-v1",
  current_version_id: "external-v1",
  title: "外部阅读登记",
  revision: 1,
  attribution: "user_view",
  content_state: "unverified",
  source_verified: false,
  root_id: "read-root",
  relative_path: "reading.md",
  sha256: "d".repeat(64),
  text: "外部当前文本",
  file_state: "in_sync",
  versions: [
    {
      version_id: "external-v1",
      revision: 1,
      sha256: "d".repeat(64),
      title: "外部阅读登记",
      attribution: "user_view",
    },
  ],
};

test("personal comments need independent grants and explicit task selection resets model consent", async () => {
  const user = userEvent.setup();
  let catalog = personalCatalog.map((item) => ({ ...item }));
  vi.mocked(p5Api.personalSources).mockImplementation(async () => ({
    items: catalog,
    total: catalog.length,
    page: 1,
    page_size: 10,
  }));
  vi.mocked(api.noteRoots).mockResolvedValue([
    {
      id: "read-root",
      path: "只读目录",
      active: true,
      query_permissions: { allow_local: true, allow_model: true },
    },
  ]);
  vi.mocked(p5Api.annotationGrant).mockImplementation(
    async (_project, id, body) => {
      catalog = catalog.map((item) =>
        item.id === id
          ? {
              ...item,
              allow_model: body.allow_model,
              authorization_revision: 3,
            }
          : item,
      );
      return { annotation_id: id, allow_model: body.allow_model, revision: 3 };
    },
  );
  vi.mocked(p5Api.prepare).mockResolvedValue({
    ...workflow,
    status: "insufficient",
  });
  mount("wiki");
  expect(p5Api.personalSources).not.toHaveBeenCalled();
  await user.type(screen.getByLabelText("Wiki 主题或问题"), "方法比较");
  await user.click(
    screen.getByLabelText("包含已独立授权的个人笔记、批注评论与外部资料"),
  );
  const comment = await screen.findByLabelText("模型来源 · 论文评论");
  expect(comment).toBeDisabled();
  expect(screen.getByLabelText("模型来源 · 个人方法笔记")).not.toBeChecked();
  await user.click(
    screen.getByRole("button", { name: "独立授权模型使用 · 论文评论" }),
  );
  await waitFor(() => expect(comment).toBeEnabled());
  expect(comment).not.toBeChecked();
  expect(p5Api.annotationGrant).toHaveBeenCalledWith(
    "p",
    "annotation-1",
    { allow_model: true, expected_revision: 2 },
    expect.any(String),
  );
  const consent = screen.getByLabelText(
    "允许本次主题阅读整理发送必要来源给模型",
  );
  await user.click(consent);
  await user.click(comment);
  expect(consent).not.toBeChecked();
  await user.click(screen.getByLabelText("模型来源 · 外部材料"));
  await user.click(consent);
  await user.click(screen.getByRole("button", { name: "生成有据整理" }));
  await waitFor(() => expect(p5Api.prepare).toHaveBeenCalled());
  expect(vi.mocked(p5Api.prepare).mock.calls[0][1].personal_sources).toEqual({
    version: "p5-personal-sources-1",
    note_ids: [],
    annotation_ids: ["annotation-1"],
    external_version_ids: ["external-v1"],
  });
  expect(p5Api.generate).not.toHaveBeenCalled();
});

test("root model revocation preserves local permission and clears task selection", async () => {
  const user = userEvent.setup();
  vi.mocked(p5Api.personalSources).mockResolvedValue({
    items: personalCatalog,
    total: 3,
    page: 1,
    page_size: 10,
  });
  vi.mocked(api.noteRoots).mockResolvedValue([
    {
      id: "read-root",
      path: "只读目录",
      active: true,
      query_permissions: { allow_local: true, allow_model: true },
    },
  ]);
  vi.mocked(api.notePermissions).mockResolvedValue({
    root_id: "read-root",
    allow_local: true,
    allow_model: false,
  });
  mount("wiki");
  await user.click(
    screen.getByLabelText("包含已独立授权的个人笔记、批注评论与外部资料"),
  );
  const note = await screen.findByLabelText("模型来源 · 个人方法笔记");
  await user.click(note);
  await user.click(screen.getByLabelText("模型来源 · 外部材料"));
  await user.click(
    screen.getByRole("button", { name: "撤销模型使用授权 · 个人方法笔记" }),
  );
  await waitFor(() => expect(note).not.toBeChecked());
  expect(screen.getByLabelText("模型来源 · 外部材料")).not.toBeChecked();
  expect(api.notePermissions).toHaveBeenCalledWith("read-root", {
    allow_local: true,
    allow_model: false,
  });
});

test("Lint selects document metadata across pages and clears private scope when disabled", async () => {
  const user = userEvent.setup();
  vi.mocked(p5Api.lintDocuments).mockImplementation(async (_project, page) => ({
    items: [
      {
        id: `doc-${page}`,
        title: `文档${page}`,
        kind: "wiki",
        status: page === 1 ? "draft" : "invalid",
        current_version_id: null,
        latest_version_id: `v${page}`,
      },
    ],
    total: 11,
    page,
    page_size: 10,
  }));
  vi.mocked(p5Api.lintStart).mockResolvedValue(run);
  mount();
  await user.click(screen.getByText("检查文档范围 · 全部可用文档"));
  await user.click(await screen.findByLabelText("检查文档 · 文档1"));
  await user.click(screen.getByLabelText("检查文档下一页"));
  await user.click(await screen.findByLabelText("检查文档 · 文档2"));
  await user.click(screen.getByRole("button", { name: "开始规则扫描" }));
  await waitFor(() => expect(p5Api.lintStart).toHaveBeenCalled());
  expect(vi.mocked(p5Api.lintStart).mock.calls[0][1].document_ids).toEqual([
    "doc-1",
    "doc-2",
  ]);
  await user.click(screen.getByLabelText("包含已授权私人 Markdown 的只读检查"));
  expect(screen.getByText("检查文档范围 · 全部可用文档")).toBeInTheDocument();
});

test("external Markdown registration freezes preview bytes and retry key without file publication", async () => {
  const user = userEvent.setup();
  vi.mocked(api.noteRoots).mockResolvedValue([
    { id: "read-root", path: "只读目录", active: true },
  ]);
  vi.mocked(api.notes).mockResolvedValue([
    {
      id: "note-1",
      relative_path: "reading.md",
      sha256: "d".repeat(64),
      text: "外部当前文本",
      authorship: "user",
    },
  ]);
  vi.mocked(p5Api.externalPreview).mockResolvedValue({
    root_id: "read-root",
    relative_path: "reading.md",
    sha256: "d".repeat(64),
    text: "外部当前文本",
    source_verified: false,
    file_state: "in_sync",
  });
  vi.mocked(p5Api.externalRegister)
    .mockRejectedValueOnce(new Error("临时通信失败"))
    .mockResolvedValue(externalDocument);
  vi.mocked(p5Api.externalDocument).mockResolvedValue(externalDocument);
  mount("wiki");
  expect(p5Api.externalDocuments).not.toHaveBeenCalled();
  await user.click(screen.getByLabelText("查看并登记已授权的外部 Markdown"));
  await user.selectOptions(
    await screen.findByLabelText("外部材料读取目录"),
    "read-root",
  );
  await waitFor(() =>
    expect(
      screen.getByRole("option", { name: "reading.md" }),
    ).toBeInTheDocument(),
  );
  await user.selectOptions(
    screen.getByLabelText("外部 Markdown 文件"),
    "reading.md",
  );
  expect(p5Api.externalPreview).not.toHaveBeenCalled();
  await user.click(
    screen.getByRole("button", { name: "只读预览外部 Markdown" }),
  );
  await screen.findByText("当前文件快照 · 未核验");
  await user.clear(screen.getByLabelText("外部材料标题"));
  await user.type(screen.getByLabelText("外部材料标题"), "外部阅读登记");
  await user.click(screen.getByRole("button", { name: "登记外部阅读材料" }));
  await screen.findByText("临时通信失败");
  await user.click(screen.getByRole("button", { name: "登记外部阅读材料" }));
  await screen.findByText("外部材料快照已登记，科学来源仍未核验。");
  const calls = vi.mocked(p5Api.externalRegister).mock.calls;
  expect(calls[0]).toEqual(calls[1]);
  expect(calls[0][1]).toEqual({
    root_id: "read-root",
    relative_path: "reading.md",
    expected_sha256: "d".repeat(64),
    title: "外部阅读登记",
    attribution: "user_view",
  });
  expect(p5Api.wikiPublish).not.toHaveBeenCalled();
  expect(p5Api.prepare).not.toHaveBeenCalled();
});

test("external file browsing respects a revoked local-reading grant", async () => {
  const user = userEvent.setup();
  vi.mocked(api.noteRoots).mockResolvedValue([
    {
      id: "read-root",
      path: "本地权限已撤销的目录",
      active: true,
      query_permissions: { allow_local: false, allow_model: false },
    },
  ]);
  mount("wiki");
  await user.click(screen.getByLabelText("查看并登记已授权的外部 Markdown"));
  await waitFor(() =>
    expect(
      screen.getByRole("option", { name: "本地权限已撤销的目录" }),
    ).toBeInTheDocument(),
  );
  await user.selectOptions(
    screen.getByLabelText("外部材料读取目录"),
    "read-root",
  );
  expect(screen.getByLabelText("外部 Markdown 文件")).toBeDisabled();
  expect(screen.getByRole("button", { name: "只读扫描目录" })).toBeDisabled();
  expect(api.notes).not.toHaveBeenCalled();
  expect(p5Api.externalPreview).not.toHaveBeenCalled();
  expect(
    screen.getByRole("button", { name: "允许本地读取此目录材料" }),
  ).toBeEnabled();
});

test("redacted annotation grants preserve independent permissions and reuse the retry key", async () => {
  const user = userEvent.setup();
  let local = false,
    model = true,
    revision = 0,
    first = true;
  vi.mocked(p5Api.personalSources).mockImplementation(async () => ({
    items: [
      {
        type: "annotation",
        id: "annotation-1",
        label: local ? "可读评论" : "已撤销本地读取的批注",
        allow_local: local,
        allow_model: model,
        redacted: !local,
        authorization_revision: revision,
        ...(local ? { text: "评论正文", sha256: "a" } : {}),
      },
    ],
    total: 1,
    page: 1,
    page_size: 10,
  }));
  vi.mocked(p5Api.annotationGrant).mockImplementation(
    async (_project, id, body) => {
      if (first) {
        first = false;
        throw new Error("授权结果未收到");
      }
      local = body.allow_local ?? local;
      model = body.allow_model;
      revision += 1;
      return {
        annotation_id: id,
        allow_model: model,
        allow_local: local,
        revision,
      };
    },
  );
  mount("wiki");
  await user.click(
    screen.getByLabelText("包含已独立授权的个人笔记、批注评论与外部资料"),
  );
  const restore = await screen.findByRole("button", {
    name: "允许本地读取批注 · 已撤销本地读取的批注",
  });
  expect(
    screen.getByLabelText("模型来源 · 已撤销本地读取的批注"),
  ).toBeDisabled();
  expect(screen.queryByText("查看材料与定位")).not.toBeInTheDocument();
  await user.click(restore);
  await screen.findByText("授权结果未收到");
  await user.click(restore);
  const comment = await screen.findByLabelText("模型来源 · 可读评论");
  expect(comment).toBeEnabled();
  expect(comment).not.toBeChecked();
  const calls = vi.mocked(p5Api.annotationGrant).mock.calls;
  expect(calls[0]).toEqual(calls[1]);
  expect(calls[0][2]).toEqual({
    allow_model: true,
    allow_local: true,
    expected_revision: 0,
  });
  await user.click(comment);
  await user.click(
    screen.getByRole("button", { name: "撤销批注本地读取权限 · 可读评论" }),
  );
  const redacted =
    await screen.findByLabelText("模型来源 · 已撤销本地读取的批注");
  expect(redacted).not.toBeChecked();
  expect(screen.queryByText("评论正文")).not.toBeInTheDocument();
  await user.click(
    screen.getByRole("button", {
      name: "撤销模型使用授权 · 已撤销本地读取的批注",
    }),
  );
  await waitFor(() => expect(p5Api.annotationGrant).toHaveBeenCalledTimes(4));
  expect(calls[3][2]).toEqual({ allow_model: false, expected_revision: 2 });
  expect(local).toBe(false);
});

test("deterministic scan advances in bounded requests with the selected papers and no model call", async () => {
  const user = userEvent.setup();
  vi.mocked(p5Api.lintStart).mockResolvedValue({
    ...run,
    status: "queued",
    processed: 0,
  });
  vi.mocked(p5Api.lintAdvance).mockResolvedValue(run);
  mount();
  await user.click(screen.getByText("检查论文范围 · 全部论文"));
  await user.click(await screen.findByLabelText("检查论文范围 · 合成论文二"));
  await user.click(screen.getByRole("button", { name: "开始规则扫描" }));
  await screen.findByText("已检查 25 / 25 个对象 · 规则 rules-1");
  expect(p5Api.lintStart).toHaveBeenCalledWith(
    "p",
    { paper_ids: ["paper-2"], document_ids: [], include_personal: false },
    expect.any(String),
  );
  expect(p5Api.lintAdvance).toHaveBeenCalledTimes(1);
  expect(p5Api.generate).not.toHaveBeenCalled();
  expect(p5Api.materialize).not.toHaveBeenCalled();
});

test("preparation is explicit and an unknown condition completes as information without errors", async () => {
  const user = userEvent.setup();
  let prepared!: (value: LintRun) => void;
  vi.mocked(p5Api.lintStart).mockReturnValue(
    new Promise((resolve) => {
      prepared = resolve;
    }),
  );
  const informational = { ...run, counts: { error: 0, warning: 0, info: 1 } };
  vi.mocked(p5Api.lintRun).mockResolvedValue(informational);
  vi.mocked(p5Api.lintAdvance).mockResolvedValue(informational);
  vi.mocked(p5Api.lintIssues).mockResolvedValue({
    items: [
      {
        ...issue,
        severity: "info",
        code: "CONDITION_UNKNOWN",
        category: "condition",
        message: "实验条件为未知，属于信息缺口",
        suggestion: "保留 unknown，不据此推断矛盾或补造条件",
      },
    ],
    total: 1,
    page: 1,
    page_size: 10,
  });
  mount();
  await user.click(screen.getByRole("button", { name: "开始规则扫描" }));
  expect(
    screen.getByText(
      "正在准备检查范围并核验来源；总数确定后开始逐批检查，不调用模型。",
    ),
  ).toBeVisible();
  expect(
    screen.getByRole("progressbar", { name: "扫描准备进度" }),
  ).not.toHaveAttribute("value");
  expect(screen.getByText("检查总数待定")).toBeVisible();
  expect(p5Api.lintAdvance).not.toHaveBeenCalled();
  await act(async () => {
    prepared({ ...informational, status: "queued", processed: 0 });
  });
  expect(
    await screen.findByText(
      /规则检查完成：未发现错误或警告，保留 1 条信息提示/,
    ),
  ).toBeVisible();
  expect(screen.getByText(/规则结果不等于科学正确性证明/)).toBeVisible();
  const card = screen
    .getByText("实验条件为未知，属于信息缺口")
    .closest("article")!;
  expect(within(card).getByText("提示 · 新发现")).toHaveClass("info");
  expect(within(card).getByText("修复 / 处理方案")).toBeVisible();
  expect(within(card).getByText("回查原文中的实验条件")).toBeVisible();
  expect(within(card).getByText(/unknown 不等于 conflicting/)).toBeVisible();
  expect(
    within(card).getByText("有明确证据时受控重建或创建新版本"),
  ).toBeVisible();
  expect(within(card).getByText(/当前诊断不直接编辑条件/)).toBeVisible();
  expect(within(card).getByText(/由后续受控流程决定/)).toBeVisible();
  expect(card.querySelector(".error, .error-text")).toBeNull();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(p5Api.prepare).not.toHaveBeenCalled();
  expect(p5Api.generate).not.toHaveBeenCalled();
});

test("source availability gaps show a safe source-check repair plan", async () => {
  vi.mocked(p5Api.lintIssues).mockResolvedValue({
    items: [
      {
        ...issue,
        severity: "info",
        code: "SOURCE_UNCHECKED",
        category: "unverifiable",
        message: "原始文件尚无可用性检查记录",
        suggestion: "在文献页显式检查来源，不能据此判断科学结论错误",
      },
    ],
    total: 1,
    page: 1,
    page_size: 10,
  });
  localStorage.setItem("rgs.lint.active.p", run.id);
  mount();
  const card = (await screen.findByText("原始文件尚无可用性检查记录")).closest(
    "article",
  )!;
  expect(within(card).getByText("在文献页检查原始来源")).toBeVisible();
  expect(within(card).getByText("重新运行 Lint")).toBeVisible();
  expect(
    within(card).getByText(/没有检查记录时不能判定科学结论错误/),
  ).toBeVisible();
});

test("backend repair plans distinguish no-model, model-required and undecided steps", async () => {
  vi.mocked(p5Api.lintIssues).mockResolvedValue({
    items: [
      {
        ...issue,
        repair_plan: {
          status: "actionable",
          summary: "核对来源后按受控流程处理。",
          steps: [
            {
              id: "local-check",
              title: "本地来源核验",
              description: "仅在本机核验来源。",
              requires_model: false,
            },
            {
              id: "model-step",
              title: "经单独授权后生成",
              description: "根据冻结来源生成新版本。",
              requires_model: true,
            },
            {
              id: "controlled-step",
              title: "后续受控重建",
              description: "根据实际受控流程决定是否调用模型。",
              requires_model: null,
            },
            {
              id: "legacy-step",
              title: "旧方案未声明用量",
              description: "尚未声明是否需要模型的旧方案步骤。",
            },
          ],
          safeguards: ["不执行未经确认的修改。"],
        },
      },
    ],
    total: 1,
    page: 1,
    page_size: 10,
  });
  localStorage.setItem("rgs.lint.active.p", run.id);
  mount();
  const card = (await screen.findByText(issue.message)).closest("article")!;
  expect(within(card).getByText("核对来源后按受控流程处理。")).toBeVisible();
  const localStep = within(card).getByText("本地来源核验").closest("li")!;
  const modelStep = within(card).getByText("经单独授权后生成").closest("li")!;
  const controlledStep = within(card).getByText("后续受控重建").closest("li")!;
  const legacyStep = within(card).getByText("旧方案未声明用量").closest("li")!;
  expect(within(localStep).getByText(/此步骤不调用模型/)).toBeVisible();
  expect(within(modelStep).getByText(/需要模型（需单独授权）/)).toBeVisible();
  expect(within(controlledStep).getByText(/由后续受控流程决定/)).toBeVisible();
  expect(within(legacyStep).getByText(/由后续受控流程决定/)).toBeVisible();
  expect(within(controlledStep).queryByText(/此步骤不调用模型/)).toBeNull();
  expect(within(legacyStep).queryByText(/此步骤不调用模型/)).toBeNull();
  expect(p5Api.prepare).not.toHaveBeenCalled();
  expect(p5Api.generate).not.toHaveBeenCalled();
});

test.each([
  {
    lifecycle: "resolved",
    title: "按需查看历史报告",
    summary: "本次检查中问题已消失，只需按需查看历史报告，无需重复修复。",
  },
  {
    lifecycle: "input_stale",
    title: "重新扫描当前范围",
    summary: "检查输入已变化；先重新扫描当前范围，再依据新报告决定处理方案。",
  },
])(
  "legacy repair fallback respects $lifecycle before rule-specific steps",
  async ({ lifecycle, title, summary }) => {
    vi.mocked(p5Api.lintIssues).mockResolvedValue({
      items: [{ ...issue, code: "SOURCE_UNCHECKED", lifecycle }],
      total: 1,
      page: 1,
      page_size: 10,
    });
    localStorage.setItem("rgs.lint.active.p", run.id);
    mount();
    const card = (await screen.findByText(issue.message)).closest("article")!;
    const plan = within(card).getByRole("region", {
      name: "Lint 修复或处理方案",
    });
    expect(within(plan).getByText(title)).toBeVisible();
    expect(within(plan).getByText(summary)).toBeVisible();
    expect(within(plan).getByText(/此步骤不调用模型/)).toBeVisible();
    expect(within(plan).queryByText("在文献页检查原始来源")).toBeNull();
    expect(
      within(plan).queryByText("有明确证据时受控重建或创建新版本"),
    ).toBeNull();
    expect(within(plan).queryByRole("button")).toBeNull();
    expect(p5Api.lintStart).not.toHaveBeenCalled();
    expect(p5Api.prepare).not.toHaveBeenCalled();
    expect(p5Api.generate).not.toHaveBeenCalled();
  },
);

test("restored active reports poll read-only until terminal and then stop", async () => {
  const user = userEvent.setup();
  localStorage.setItem("rgs.lint.active.p", run.id);
  vi.mocked(p5Api.lintRun)
    .mockResolvedValueOnce({ ...run, status: "running", processed: 5 })
    .mockResolvedValue(run);
  mount();
  expect(await screen.findByText("检查尚未完成，可继续检查")).toBeVisible();
  expect(screen.getByRole("button", { name: "重新读取报告" })).toBeEnabled();
  await screen.findByText("检查完成", {}, { timeout: 3500 });
  const reads = vi.mocked(p5Api.lintRun).mock.calls.length;
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 2200));
  });
  expect(p5Api.lintRun).toHaveBeenCalledTimes(reads);
  await user.click(screen.getByRole("button", { name: "重新读取报告" }));
  await waitFor(() => expect(p5Api.lintRun).toHaveBeenCalledTimes(reads + 1));
  expect(p5Api.lintStart).not.toHaveBeenCalled();
  expect(p5Api.lintAdvance).not.toHaveBeenCalled();
  expect(p5Api.prepare).not.toHaveBeenCalled();
  expect(p5Api.generate).not.toHaveBeenCalled();
}, 8000);

test("the last object batch advances to dependency rebuilding at the same count and uses a separate request key", async () => {
  const user = userEvent.setup();
  localStorage.setItem("rgs.lint.active.p", run.id);
  const scanning: LintRun = {
    ...run,
    status: "running",
    phase: "scanning",
  };
  const rebuilding: LintRun = {
    ...scanning,
    phase: "rebuilding_dependencies",
  };
  vi.mocked(p5Api.lintRun)
    .mockResolvedValueOnce(scanning)
    .mockResolvedValue({
      ...scanning,
      updated_at: "2026-11-07T10:00:00Z",
    });
  let finish!: (value: LintRun) => void;
  vi.mocked(p5Api.lintAdvance)
    .mockResolvedValueOnce(rebuilding)
    .mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
  const view = mount();
  await user.click(
    await screen.findByRole("button", { name: "继续未完成检查" }),
  );
  await screen.findByText("正在重建依赖索引");
  expect(
    screen.getByText("已检查 25 / 25 个对象 · 规则 rules-1"),
  ).toBeVisible();
  expect(
    screen.getByText(
      "对象检查已完成，正在重建依赖索引；完成后才结束本轮扫描。",
    ),
  ).toBeVisible();
  expect(
    screen.getByRole("progressbar", { name: "扫描依赖索引重建进度" }),
  ).not.toHaveAttribute("value");
  expect(screen.queryByText("检查完成")).not.toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await waitFor(() => expect(p5Api.lintAdvance).toHaveBeenCalledTimes(2));
  const calls = vi.mocked(p5Api.lintAdvance).mock.calls;
  expect(calls[0][2]).not.toBe(calls[1][2]);

  await user.click(screen.getByRole("button", { name: "重新读取报告" }));
  await waitFor(() => expect(p5Api.lintRun).toHaveBeenCalledTimes(2));
  expect(
    (view.client.getQueryData(["lint-run", "p", run.id]) as LintRun).phase,
  ).toBe("rebuilding_dependencies");
  expect(screen.getByText("正在重建依赖索引")).toBeVisible();
  await act(async () => {
    finish({ ...run, phase: "finished" });
  });
  expect(await screen.findByText("检查完成")).toBeVisible();
  expect(
    screen.queryByRole("progressbar", { name: "扫描依赖索引重建进度" }),
  ).not.toBeInTheDocument();
  expect(p5Api.lintAdvance).toHaveBeenCalledTimes(2);
  expect(p5Api.lintStart).not.toHaveBeenCalled();
  expect(p5Api.generate).not.toHaveBeenCalled();
});

test("restoring a dependency rebuilding report remains read-only until explicit continuation", async () => {
  const user = userEvent.setup();
  localStorage.setItem("rgs.lint.active.p", run.id);
  vi.mocked(p5Api.lintRun).mockResolvedValue({
    ...run,
    status: "running",
    phase: "rebuilding_dependencies",
  });
  vi.mocked(p5Api.lintAdvance).mockResolvedValue({ ...run, phase: "finished" });
  mount();
  expect(await screen.findByText("依赖索引待重建，可继续检查")).toBeVisible();
  expect(
    screen.getByText("对象检查已完成，依赖索引尚未重建；继续检查后完成报告。"),
  ).toBeVisible();
  expect(screen.queryByText("检查完成")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("progressbar", { name: "扫描依赖索引重建进度" }),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "重新读取报告" }));
  await waitFor(() => expect(p5Api.lintRun).toHaveBeenCalledTimes(2));
  expect(p5Api.lintAdvance).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "继续未完成检查" }));
  expect(await screen.findByText("检查完成")).toBeVisible();
  expect(p5Api.lintAdvance).toHaveBeenCalledTimes(1);
  expect(p5Api.lintStart).not.toHaveBeenCalled();
  expect(p5Api.generate).not.toHaveBeenCalled();
});

test("an unchanged count and phase stops rather than repeating the same advance request", async () => {
  const user = userEvent.setup();
  localStorage.setItem("rgs.lint.active.p", run.id);
  const stalled: LintRun = {
    ...run,
    processed: 5,
    status: "running",
    phase: "scanning",
  };
  vi.mocked(p5Api.lintRun).mockResolvedValue(stalled);
  vi.mocked(p5Api.lintAdvance).mockResolvedValue(stalled);
  mount();
  await user.click(
    await screen.findByRole("button", { name: "继续未完成检查" }),
  );
  expect(
    await screen.findByText("本次扫描未推进，请重新读取报告后继续。"),
  ).toBeVisible();
  expect(p5Api.lintAdvance).toHaveBeenCalledTimes(1);
  expect(screen.queryByText("检查完成")).not.toBeInTheDocument();
});

test("legacy reports leave unrecorded phase timings unknown", async () => {
  const user = userEvent.setup();
  localStorage.setItem("rgs.lint.active.p", run.id);
  mount();
  await screen.findByText("检查完成");
  await user.click(screen.getByText("阶段耗时"));
  const timings = screen.getByText("阶段耗时").closest("details")!;
  expect(within(timings).getAllByText("未记录")).toHaveLength(8);
  expect(within(timings).queryByText(/0\.000 秒/)).not.toBeInTheDocument();
  expect(p5Api.lintAdvance).not.toHaveBeenCalled();
});

test("recorded phase timings show seconds and request counts with their own units", async () => {
  const user = userEvent.setup();
  localStorage.setItem("rgs.lint.active.p", run.id);
  vi.mocked(p5Api.lintRun).mockResolvedValue({
    ...run,
    phase: "finished",
    timings: {
      prepare_seconds: 0,
      validate_seconds: 0.1,
      check_seconds: 1.25,
      dependency_rebuild_seconds: 2.5,
      finalize_seconds: 0.02,
      elapsed_seconds: 3.87,
      last_advance_seconds: 2.52,
      advance_calls: 3,
    },
  });
  mount();
  await screen.findByText("检查完成");
  await user.click(screen.getByText("阶段耗时"));
  const timings = screen.getByText("阶段耗时").closest("details")!;
  expect(within(timings).getByText("0.000 秒")).toBeVisible();
  expect(within(timings).getByText("1.250 秒")).toBeVisible();
  expect(within(timings).getByText("2.500 秒")).toBeVisible();
  expect(within(timings).getByText("3.870 秒")).toBeVisible();
  expect(within(timings).getByText("2.520 秒")).toBeVisible();
  expect(within(timings).getByText("3 次")).toBeVisible();
  expect(within(timings).queryByText("3.000 秒")).not.toBeInTheDocument();
  expect(within(timings).queryByText("未记录")).not.toBeInTheDocument();
});

test.each(["completed", "cancelled"])(
  "an old report GET cannot overwrite a newer %s result",
  async (status) => {
    const user = userEvent.setup();
    const pending = { ...run, status: "running", processed: 0 };
    localStorage.setItem("rgs.lint.active.p", run.id);
    let finishRead!: (value: LintRun) => void,
      finishAdvance!: (value: LintRun) => void;
    vi.mocked(p5Api.lintRun)
      .mockResolvedValueOnce(pending)
      .mockImplementation(
        () =>
          new Promise((resolve) => {
            finishRead = resolve;
          }),
      );
    vi.mocked(p5Api.lintAdvance).mockImplementation(
      () =>
        new Promise((resolve) => {
          finishAdvance = resolve;
        }),
    );
    vi.mocked(p5Api.lintCancel).mockResolvedValue({
      ...pending,
      status: "cancelled",
    });
    const view = mount();
    await screen.findByText("检查尚未完成，可继续检查");
    if (status === "completed") {
      await user.click(screen.getByRole("button", { name: "继续未完成检查" }));
      await waitFor(() => expect(p5Api.lintAdvance).toHaveBeenCalledTimes(1));
    }
    await user.click(screen.getByRole("button", { name: "重新读取报告" }));
    await waitFor(() => expect(p5Api.lintRun).toHaveBeenCalledTimes(2));
    if (status === "completed")
      await act(async () => {
        finishAdvance(run);
      });
    else await user.click(screen.getByRole("button", { name: "取消规则扫描" }));
    await screen.findByText(status === "completed" ? "检查完成" : "已取消");
    await act(async () => {
      finishRead(pending);
    });
    expect(
      (view.client.getQueryData(["lint-run", "p", run.id]) as LintRun).status,
    ).toBe(status);
    expect(
      screen.queryByText("检查尚未完成，可继续检查"),
    ).not.toBeInTheDocument();
    expect(p5Api.lintStart).not.toHaveBeenCalled();
    expect(p5Api.generate).not.toHaveBeenCalled();
  },
);

test("unknown information can be visible during a slow advance and a terminal read wins over its late response", async () => {
  const user = userEvent.setup();
  localStorage.setItem("rgs.lint.active.p", run.id);
  const informational = { ...run, counts: { error: 0, warning: 0, info: 1 } };
  const slow = { ...informational, status: "running", processed: 5 };
  vi.mocked(p5Api.lintRun)
    .mockResolvedValueOnce(slow)
    .mockResolvedValue(informational);
  vi.mocked(p5Api.lintIssues).mockResolvedValue({
    items: [
      {
        ...issue,
        code: "CONDITION_UNKNOWN",
        severity: "info",
        category: "condition",
        message: "实验条件为未知，属于信息缺口",
        suggestion: "保留 unknown，不据此推断矛盾或补造条件",
      },
    ],
    total: 1,
    page: 1,
    page_size: 10,
  });
  let finish!: (value: LintRun) => void;
  vi.mocked(p5Api.lintAdvance).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  mount();
  await user.click(
    await screen.findByRole("button", { name: "继续未完成检查" }),
  );
  expect(await screen.findByText("实验条件为未知，属于信息缺口")).toBeVisible();
  expect(screen.getByText("已检查 5 / 25 个对象 · 规则 rules-1")).toBeVisible();
  await screen.findByText("检查完成", {}, { timeout: 3500 });
  expect(
    screen.queryByText("正在逐批检查；进度在本批完成后更新，不调用模型。"),
  ).not.toBeInTheDocument();
  expect(screen.getByText(/未发现错误或警告，保留 1 条信息提示/)).toBeVisible();
  await act(async () => {
    finish(slow);
  });
  expect(screen.getByText("检查完成")).toBeVisible();
  expect(
    screen.getByText("已检查 25 / 25 个对象 · 规则 rules-1"),
  ).toBeVisible();
  expect(p5Api.lintAdvance).toHaveBeenCalledTimes(1);
  expect(p5Api.lintStart).not.toHaveBeenCalled();
  expect(p5Api.generate).not.toHaveBeenCalled();
});

test("an older same-run read cannot move active progress backwards", async () => {
  const user = userEvent.setup();
  localStorage.setItem("rgs.lint.active.p", run.id);
  vi.mocked(p5Api.lintRun).mockResolvedValue({
    ...run,
    status: "running",
    processed: 5,
  });
  let finish!: (value: LintRun) => void;
  vi.mocked(p5Api.lintAdvance)
    .mockResolvedValueOnce({ ...run, status: "running", processed: 20 })
    .mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
  vi.mocked(p5Api.lintCancel).mockResolvedValue({
    ...run,
    status: "cancelled",
    processed: 20,
  });
  mount();
  await user.click(
    await screen.findByRole("button", { name: "继续未完成检查" }),
  );
  await screen.findByText("已检查 20 / 25 个对象 · 规则 rules-1");
  await user.click(screen.getByRole("button", { name: "重新读取报告" }));
  await waitFor(() => expect(p5Api.lintRun).toHaveBeenCalledTimes(2));
  expect(
    screen.getByText("已检查 20 / 25 个对象 · 规则 rules-1"),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "取消规则扫描" }));
  await screen.findByText("已取消");
  await act(async () => {
    finish(run);
  });
  expect(screen.getByText("已取消")).toBeVisible();
});

test("unmounting during preparation never starts or publishes a late scan", async () => {
  const user = userEvent.setup();
  let finish!: (value: LintRun) => void;
  vi.mocked(p5Api.lintStart).mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const view = mount();
  await user.click(screen.getByRole("button", { name: "开始规则扫描" }));
  view.unmount();
  await act(async () => {
    finish({ ...run, status: "queued", processed: 0 });
  });
  expect(p5Api.lintAdvance).not.toHaveBeenCalled();
  expect(view.client.getQueryData(["lint-run", "p", run.id])).toBeUndefined();
  expect(p5Api.generate).not.toHaveBeenCalled();
});

test("diagnostic pagination and filters preserve evidence and graph navigation", async () => {
  const user = userEvent.setup();
  localStorage.setItem("rgs.lint.active.p", run.id);
  vi.mocked(p5Api.lintIssues).mockImplementation(async (_p, _id, filters) => ({
    items: [issue],
    total: 21,
    page: filters.page,
    page_size: 10,
  }));
  const view = mount();
  await screen.findByText(issue.message);
  await user.click(screen.getByRole("button", { name: "诊断结果下一页" }));
  await waitFor(() =>
    expect(p5Api.lintIssues).toHaveBeenLastCalledWith(
      "p",
      run.id,
      expect.objectContaining({ page: 2 }),
    ),
  );
  await user.selectOptions(screen.getByLabelText("严重性"), "error");
  await waitFor(() =>
    expect(p5Api.lintIssues).toHaveBeenLastCalledWith(
      "p",
      run.id,
      expect.objectContaining({ page: 1, severity: "error" }),
    ),
  );
  await user.click(screen.getByRole("button", { name: "在知识图谱中定位" }));
  await user.click(screen.getByRole("button", { name: "查看关联 Wiki" }));
  expect(view.onGraphNode).toHaveBeenCalledWith("node-1");
  expect(view.onWikiPage).toHaveBeenCalledWith("wiki-1");
  expect(screen.getByText("PDF 第 3 页")).toBeVisible();
});

test("cancelled scan cannot be overwritten by an in-flight advance result", async () => {
  const user = userEvent.setup();
  localStorage.setItem("rgs.lint.active.p", run.id);
  vi.mocked(p5Api.lintRun).mockResolvedValue({
    ...run,
    status: "running",
    processed: 0,
  });
  let finish!: (value: LintRun) => void;
  vi.mocked(p5Api.lintAdvance).mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  vi.mocked(p5Api.lintCancel).mockResolvedValue({
    ...run,
    status: "cancelled",
    processed: 0,
  });
  mount();
  await user.click(
    await screen.findByRole("button", { name: "继续未完成检查" }),
  );
  await waitFor(() => expect(p5Api.lintAdvance).toHaveBeenCalledTimes(1));
  await user.click(screen.getByRole("button", { name: "取消规则扫描" }));
  await screen.findByText("已取消");
  await act(async () => {
    finish(run);
  });
  expect(screen.getByText("已取消")).toBeVisible();
  expect(p5Api.lintAdvance).toHaveBeenCalledTimes(1);
});

test("read failure retries history only and does not start a model or scan", async () => {
  const user = userEvent.setup();
  vi.mocked(p5Api.lintRuns)
    .mockRejectedValueOnce(new Error("本地服务暂时不可读"))
    .mockResolvedValueOnce({ items: [run], total: 1, page: 1, page_size: 10 });
  mount();
  const alert = await screen.findByRole("alert");
  await user.click(within(alert).getByRole("button", { name: "重新读取" }));
  await waitFor(() => expect(p5Api.lintRuns).toHaveBeenCalledTimes(2));
  expect(p5Api.lintStart).not.toHaveBeenCalled();
  expect(p5Api.generate).not.toHaveBeenCalled();
});

test("model generation requires explicit consent and failures do not automatically resend", async () => {
  const user = userEvent.setup();
  vi.mocked(p5Api.prepare).mockResolvedValue({
    ...workflow,
    status: "prepared",
    result: null,
  });
  vi.mocked(p5Api.generate).mockRejectedValue(
    new Error("合成超时，未自动重发"),
  );
  vi.mocked(p5Api.workflow).mockResolvedValue({
    ...workflow,
    status: "failed",
    result: null,
    can_continue: true,
    error: "合成超时",
  });
  mount("wiki");
  await user.type(screen.getByLabelText("Wiki 主题或问题"), "方法条件");
  expect(screen.getByRole("button", { name: "生成有据整理" })).toBeDisabled();
  await user.click(
    screen.getByLabelText("允许本次主题阅读整理发送必要来源给模型"),
  );
  await user.click(screen.getByRole("button", { name: "生成有据整理" }));
  await screen.findByText("合成超时，未自动重发");
  expect(p5Api.generate).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole("button", { name: "重新读取任务" }));
  expect(p5Api.generate).toHaveBeenCalledTimes(1);
  expect(p5Api.materialize).not.toHaveBeenCalled();
});

test("model result, internal draft, save and authorized export are separate explicit operations", async () => {
  const user = userEvent.setup();
  localStorage.setItem("rgs.workflow.p.wiki_synthesis.", workflow.id);
  vi.mocked(p5Api.materialize).mockResolvedValue(draft);
  vi.mocked(p5Api.wikiSave).mockImplementation(async () => {
    const saved = {
      ...draft,
      state: "saved",
      saved_version_id: draft.version_id,
    };
    vi.mocked(p5Api.wikiPage).mockResolvedValue(saved);
    return saved;
  });
  vi.mocked(p5Api.authorizeOutput).mockImplementation(async () => {
    vi.mocked(p5Api.wikiRoots).mockResolvedValue({ items: [root] });
    return root;
  });
  mount("wiki");
  expect(await screen.findByText("冻结的原主题")).toBeVisible();
  expect(p5Api.materialize).not.toHaveBeenCalled();
  expect(p5Api.wikiSave).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "创建内部整理草稿" }));
  const save = await screen.findByRole("button", { name: "保存内部版本" });
  expect(p5Api.wikiPublish).not.toHaveBeenCalled();
  await user.click(save);
  await screen.findByText("内部版本已保存。");
  expect(p5Api.wikiSave).toHaveBeenCalledWith(
    "p",
    draft.page_id,
    {
      version_id: draft.version_id,
      expected_head_version_id: draft.head_version_id,
      expected_content_hash: draft.content_hash,
    },
    expect.any(String),
  );
  await user.click(
    screen.getByRole("button", { name: "选择并授权独立导出目录" }),
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "导出 Markdown" })).toBeEnabled(),
  );
  expect(p5Api.wikiPublish).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "导出 Markdown" }));
  expect(p5Api.wikiPublish).toHaveBeenCalledWith(
    "p",
    draft.page_id,
    expect.objectContaining({
      root_id: root.root_id,
      expected_target_hash: null,
    }),
    expect.any(String),
  );
  expect(p5Api.generate).not.toHaveBeenCalled();
});

test("external modifications block the same output root and never use the observed new hash", async () => {
  const user = userEvent.setup();
  activeWiki({
    ...draft,
    state: "saved",
    file: {
      state: "modified",
      root_id: root.root_id,
      sha256: "b".repeat(64),
      current_hash: "c".repeat(64),
    },
  });
  vi.mocked(p5Api.wikiRoots).mockResolvedValue({
    items: [root, { ...root, root_id: "root-2", path: "another-output" }],
  });
  mount("wiki");
  await screen.findByRole("heading", { name: draft.title });
  await user.selectOptions(
    screen.getByLabelText("Wiki 导出目录"),
    root.root_id,
  );
  expect(screen.getByRole("button", { name: "导出 Markdown" })).toBeDisabled();
  expect(p5Api.wikiPublish).not.toHaveBeenCalled();
  await user.selectOptions(screen.getByLabelText("Wiki 导出目录"), "root-2");
  await user.click(screen.getByRole("button", { name: "导出 Markdown" }));
  expect(p5Api.wikiPublish).toHaveBeenCalledWith(
    "p",
    draft.page_id,
    expect.objectContaining({ root_id: "root-2", expected_target_hash: null }),
    expect.any(String),
  );
});

test("updating an existing managed file uses its registered hash", async () => {
  const user = userEvent.setup();
  activeWiki({
    ...draft,
    state: "saved",
    file: {
      state: "in_sync",
      root_id: root.root_id,
      sha256: "b".repeat(64),
      current_hash: "c".repeat(64),
    },
  });
  vi.mocked(p5Api.wikiRoots).mockResolvedValue({ items: [root] });
  mount("wiki");
  await screen.findByRole("heading", { name: draft.title });
  await user.selectOptions(
    screen.getByLabelText("Wiki 导出目录"),
    root.root_id,
  );
  await user.click(screen.getByRole("button", { name: "导出 Markdown" }));
  expect(p5Api.wikiPublish).toHaveBeenCalledWith(
    "p",
    draft.page_id,
    expect.objectContaining({ expected_target_hash: "b".repeat(64) }),
    expect.any(String),
  );
});

test("Wiki sections and nested citations start collapsed and use ten-item pages", async () => {
  const user = userEvent.setup();
  activeWiki({
    ...draft,
    sections: Array.from({ length: 11 }, (_, i) => ({
      ...draft.sections[0],
      section_id: `section-${i}`,
      heading: `合成段落 ${i + 1}`,
      dependencies: Array.from({ length: 11 }, (_, j) => ({
        type: "evidence",
        id: `e-${j}`,
        quote: `合成原文 ${j + 1}`,
      })),
    })),
  });
  mount("wiki");
  await screen.findByRole("heading", { name: "合成段落 1" });
  expect(
    screen.queryByRole("heading", { name: "合成段落 11" }),
  ).not.toBeInTheDocument();
  const first = screen
    .getByRole("heading", { name: "合成段落 1" })
    .closest("article")!;
  const outer = within(first)
    .getByText("原文引用与依赖 · 11 条")
    .closest("details")!;
  expect(outer).not.toHaveAttribute("open");
  await user.click(within(first).getByText("原文引用与依赖 · 11 条"));
  expect(outer).toHaveAttribute("open");
  expect(
    within(first).getByText("来源 1 · 原文证据").closest("details"),
  ).not.toHaveAttribute("open");
  await user.click(
    within(first).getByRole("button", { name: "段落引用下一页" }),
  );
  expect(within(first).getByText("来源 11 · 原文证据")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Wiki 段落下一页" }));
  expect(screen.getByRole("heading", { name: "合成段落 11" })).toBeVisible();
});

test("offline engine disables model, scan and output authorization", async () => {
  mount("wiki", false);
  expect(
    screen.getByRole("button", { name: "选择并授权独立导出目录" }),
  ).toBeDisabled();
  expect(screen.getByRole("button", { name: "生成有据整理" })).toBeDisabled();
  expect(p5Api.wikiRoots).not.toHaveBeenCalled();
  expect(p5Api.generate).not.toHaveBeenCalled();
});

test("changing a topic or private-source scope clears transmission consent", async () => {
  const user = userEvent.setup();
  mount("wiki");
  const topic = screen.getByLabelText("Wiki 主题或问题");
  const consent = screen.getByLabelText(
    "允许本次主题阅读整理发送必要来源给模型",
  );
  await user.type(topic, "方法条件");
  await user.click(consent);
  expect(screen.getByRole("button", { name: "生成有据整理" })).toBeEnabled();
  await user.type(topic, "与限制");
  expect(consent).not.toBeChecked();
  await user.clear(topic);
  await user.type(topic, "方法条件");
  expect(consent).not.toBeChecked();
  await user.click(consent);
  await user.click(
    screen.getByLabelText("包含已独立授权的个人笔记、批注评论与外部资料"),
  );
  expect(consent).not.toBeChecked();
  expect(p5Api.generate).not.toHaveBeenCalled();
});

test("dependency browsing and index rebuilding are explicit and do not generate model work", async () => {
  const user = userEvent.setup();
  localStorage.setItem("rgs.lint.active.p", run.id);
  vi.mocked(p5Api.lintDependencies).mockResolvedValue({
    items: [
      {
        id: "dependency-1",
        dependent_type: "document",
        dependent_id: "wiki-affected",
        source_type: "node",
        source_id: "node-1",
        role: "source",
        category: "dependency",
        state: "stale",
      },
    ],
    total: 1,
    page: 1,
    page_size: 10,
  });
  vi.mocked(p5Api.rebuildDependencies).mockResolvedValue({
    edge_count: 7,
    change_count: 1,
  });
  const view = mount();
  await screen.findByText(issue.message);
  expect(p5Api.lintDependencies).not.toHaveBeenCalled();
  expect(p5Api.rebuildDependencies).not.toHaveBeenCalled();
  await user.click(screen.getByText("查看依赖与影响范围"));
  await user.click(await screen.findByRole("button", { name: "查看关联文档" }));
  expect(view.onWikiPage).toHaveBeenCalledWith("wiki-affected");
  await user.click(screen.getByRole("button", { name: "重建派生依赖索引" }));
  expect(
    await screen.findByText("依赖索引已重建，共 7 条依赖；检测到 1 项变化。"),
  ).toBeVisible();
  expect(p5Api.generate).not.toHaveBeenCalled();
  expect(p5Api.lintStart).not.toHaveBeenCalled();
});

test("publication history survives reopening and requires explicit recovery", async () => {
  const user = userEvent.setup();
  activeWiki({ ...draft, state: "saved" });
  const interrupted = { operation_id: "publication-old", state: "staged" };
  vi.mocked(p5Api.wikiPublications).mockResolvedValue({
    items: [interrupted],
    total: 1,
    offset: 0,
    limit: 10,
  });
  vi.mocked(p5Api.wikiRecover).mockResolvedValue({
    ...interrupted,
    state: "succeeded",
  });
  mount("wiki");
  await screen.findByRole("heading", { name: draft.title });
  await user.click(screen.getByText("导出操作记录与中断恢复"));
  await user.click(await screen.findByRole("button", { name: /导出操作 1/ }));
  expect(p5Api.wikiRecover).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "核对并恢复这次导出" }));
  await screen.findByText("导出状态：生成完成");
  expect(p5Api.wikiRecover).toHaveBeenCalledWith(
    "p",
    "publication-old",
    expect.any(String),
  );
  expect(p5Api.wikiPublish).not.toHaveBeenCalled();
  expect(p5Api.generate).not.toHaveBeenCalled();
});

test("cancel and continue use the existing job and report the resulting workflow state", async () => {
  const user = userEvent.setup();
  localStorage.setItem("rgs.workflow.p.wiki_synthesis.", workflow.id);
  let status = "running";
  vi.mocked(p5Api.workflow).mockImplementation(async () => ({
    ...workflow,
    status,
    result: null,
    can_continue: status === "cancelled",
  }));
  vi.mocked(api.jobAction).mockImplementation(async () => {
    status = "cancelled";
    return { id: workflow.job_id!, status } as Awaited<
      ReturnType<typeof api.jobAction>
    >;
  });
  vi.mocked(p5Api.generate).mockImplementation(async () => {
    status = "queued";
    return { id: "job-successor", status } as Awaited<
      ReturnType<typeof p5Api.generate>
    >;
  });
  mount("wiki");
  await user.click(await screen.findByRole("button", { name: "取消模型任务" }));
  expect(api.jobAction).toHaveBeenCalledWith(
    "job-1",
    "cancel",
    expect.any(String),
  );
  expect(await screen.findByText("已取消")).toBeVisible();
  const continuation = screen.getByRole("button", {
    name: "明确继续未完成生成",
  });
  expect(continuation).toBeDisabled();
  await user.click(
    screen.getByLabelText("允许本次主题阅读整理发送必要来源给模型"),
  );
  await user.click(continuation);
  expect(p5Api.generate).toHaveBeenCalledWith(
    "p",
    workflow.id,
    true,
    expect.any(String),
  );
  expect(await screen.findByText("等待执行")).toBeVisible();
  expect(p5Api.prepare).not.toHaveBeenCalled();
  expect(p5Api.materialize).not.toHaveBeenCalled();
});
