import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { PaperTranslation } from "./PaperTranslation";
import { TranslationSettings } from "./TranslationSettings";
import { JobHistory } from "./JobHistory";
import {
  api,
  request,
  type TranslationPreparation,
  type TranslationView,
} from "./api";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("./api", () => ({
  request: vi.fn(),
  api: {
    translationSettings: vi.fn(),
    saveTranslationSettings: vi.fn(),
    checkTranslationService: vi.fn(),
    translations: vi.fn(),
    prepareTranslation: vi.fn(),
    createTranslation: vi.fn(),
    cancelTranslation: vi.fn(),
    jobs: vi.fn(),
    projectJobs: vi.fn(),
    jobAction: vi.fn(),
  },
}));

const preparation: TranslationPreparation = {
  paper_id: "p",
  document_version_id: "v",
  source_hash: "abc123",
  page_start: 1,
  page_end: 3,
  page_count: 3,
  source_characters: 6000,
  estimated_input_tokens: 3000,
  estimate_is_limit: false,
  estimate_note: "本地估算，不是实际用量。",
  profile_id: "m",
  model_id: "fixture",
  cache_hit: false,
  cached_translation_id: null,
  service_ready: true,
  active_tasks: 0,
  warnings: [],
  prepare_fingerprint: "a".repeat(64),
  output_mode: "dual",
};
const record: TranslationView = {
  id: "t",
  paper_id: "p",
  document_version_id: "v",
  source_hash: "abc123",
  profile_id: "m",
  model_id: "fixture",
  status: "COMPLETED",
  page_start: 1,
  page_end: 3,
  page_count: 3,
  progress: 100,
  stage: "completed",
  job_id: "j",
  external_task_id: "external",
  external_state: "completed",
  cache_hit: false,
  error_code: null,
  error: null,
  warnings: [],
  artifacts: [
    { kind: "mono", sha256: "x", size_bytes: 100, page_count: 3 },
    { kind: "dual", sha256: "y", size_bytes: 200, page_count: 6 },
  ],
  usage: {
    calls: 2,
    retry_count: 0,
    input_tokens: 1000,
    output_tokens: 500,
    total_tokens: 1500,
    unknown_usage_calls: 0,
    cost_estimate: null,
    cost_known: false,
  },
  max_calls: 100,
  max_input_tokens: 200000,
  created_at: "2026-11-11T00:00:00Z",
  updated_at: "2026-11-11T00:00:00Z",
};

function mount(
  element = (
    <PaperTranslation paperId="p" revisionId="v" pageCount={3} connected />
  ),
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    ...render(
      <QueryClientProvider client={client}>{element}</QueryClientProvider>,
    ),
    client,
  };
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.translationSettings).mockResolvedValue({
    enabled: true,
    service_url: "http://127.0.0.1:8890",
    launch_mode: "manual",
  });
  vi.mocked(api.translations).mockResolvedValue([]);
  vi.mocked(api.prepareTranslation).mockResolvedValue(preparation);
  vi.mocked(api.createTranslation).mockResolvedValue({
    ...record,
    status: "PENDING",
  });
  vi.mocked(api.cancelTranslation).mockResolvedValue({
    ...record,
    status: "CANCELLED",
  });
  vi.mocked(request).mockResolvedValue({
    profiles: [
      { id: "m", name: "合成模型", model: "fixture", provider: "compatible" },
    ],
    connections: [],
    roles: { extraction: "m", reasoning: "m" },
  });
  vi.mocked(api.jobs).mockResolvedValue([]);
});

test("opening translation only reads local state; explicit preflight and two permissions gate submission", async () => {
  const user = userEvent.setup();
  mount();
  await screen.findByRole("option", { name: /合成模型/ });
  expect(api.prepareTranslation).not.toHaveBeenCalled();
  expect(api.checkTranslationService).not.toHaveBeenCalled();
  expect(api.createTranslation).not.toHaveBeenCalled();
  const generate = screen.getByRole("button", { name: "生成双语对照 PDF" });
  expect(generate).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "预检范围与预算" }));
  await screen.findByText("翻译预检");
  expect(api.prepareTranslation).toHaveBeenCalledWith("p", {
    document_version_id: "v",
    profile_id: "m",
    output_mode: "dual",
    max_calls: 100,
    max_input_tokens: 200000,
  });
  await user.click(screen.getByRole("checkbox", { name: /允许将所选 PDF/ }));
  expect(generate).toBeDisabled();
  await user.click(
    screen.getByRole("checkbox", { name: /确认该服务由本应用独占/ }),
  );
  expect(generate).toBeEnabled();
  await user.click(generate);
  await waitFor(() =>
    expect(api.createTranslation).toHaveBeenCalledWith(
      "p",
      expect.objectContaining({
        allow_network: true,
        exclusive_service: true,
        profile_id: "m",
        expected_fingerprint: preparation.prepare_fingerprint,
      }),
    ),
  );
});

test("bundled translation defaults to dual output and only asks for model API authorization", async () => {
  const user = userEvent.setup();
  vi.mocked(api.translationSettings).mockResolvedValue({
    enabled: true,
    service_url: "http://127.0.0.1:8890",
    launch_mode: "bundled",
  });
  vi.mocked(api.prepareTranslation).mockResolvedValue({
    ...preparation,
    launch_mode: "bundled",
  });
  mount();
  await screen.findByRole("option", { name: /合成模型/ });
  expect(screen.getByLabelText("输出文件")).toHaveValue("dual");
  expect(
    screen.queryByRole("checkbox", { name: /确认该服务由本应用独占/ }),
  ).not.toBeInTheDocument();
  expect(api.prepareTranslation).not.toHaveBeenCalled();
  expect(invoke).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "预检范围与预算" }));
  await screen.findByText(/内置引擎资源就绪。预检没有启动进程/);
  expect(
    screen.getByRole("button", { name: "生成双语对照 PDF" }),
  ).toBeDisabled();
  await user.click(
    screen.getByRole("checkbox", {
      name: /允许将所选论文的文本发送到上述模型 API/,
    }),
  );
  await user.click(screen.getByRole("button", { name: "生成双语对照 PDF" }));
  await waitFor(() =>
    expect(api.createTranslation).toHaveBeenCalledWith(
      "p",
      expect.objectContaining({
        output_mode: "dual",
        allow_network: true,
        exclusive_service: true,
      }),
    ),
  );
  expect(api.checkTranslationService).not.toHaveBeenCalled();
});

test("changing output invalidates cached preparation and consent even when switching back", async () => {
  const user = userEvent.setup();
  vi.mocked(api.translationSettings).mockResolvedValue({
    enabled: true,
    service_url: "http://127.0.0.1:8890",
    launch_mode: "bundled",
  });
  vi.mocked(api.prepareTranslation).mockImplementation(
    async (_paperId, input) => ({
      ...preparation,
      launch_mode: "bundled",
      output_mode: input.output_mode,
      cache_hit: input.output_mode === "dual",
      cached_translation_id: input.output_mode === "dual" ? "t" : null,
    }),
  );
  mount();
  await screen.findByRole("option", { name: /合成模型/ });
  await user.click(screen.getByRole("button", { name: "预检范围与预算" }));
  await screen.findByText("已找到匹配缓存，不新增模型调用");
  await user.click(
    screen.getByRole("checkbox", { name: /允许将所选论文的文本/ }),
  );
  await user.selectOptions(screen.getByLabelText("输出文件"), "mono");
  expect(
    screen.queryByText("已找到匹配缓存，不新增模型调用"),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("checkbox", { name: /允许将所选论文的文本/ }),
  ).not.toBeChecked();
  expect(screen.getByRole("button", { name: "生成中文 PDF" })).toBeDisabled();
  await user.selectOptions(screen.getByLabelText("输出文件"), "dual");
  expect(
    screen.queryByRole("button", { name: "读取匹配译文缓存" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "生成双语对照 PDF" }),
  ).toBeDisabled();
  await user.selectOptions(screen.getByLabelText("输出文件"), "mono");
  await user.click(screen.getByRole("button", { name: "预检范围与预算" }));
  await screen.findByText("翻译预检");
  expect(api.prepareTranslation).toHaveBeenLastCalledWith(
    "p",
    expect.objectContaining({ output_mode: "mono" }),
  );
  expect(screen.getByRole("button", { name: "生成中文 PDF" })).toBeDisabled();
  await user.click(
    screen.getByRole("checkbox", { name: /允许将所选论文的文本/ }),
  );
  await user.click(screen.getByRole("button", { name: "生成中文 PDF" }));
  await waitFor(() =>
    expect(api.createTranslation).toHaveBeenCalledWith(
      "p",
      expect.objectContaining({
        output_mode: "mono",
        allow_network: true,
        exclusive_service: true,
      }),
    ),
  );
});

test("changing budget invalidates preflight and unavailable service cannot be submitted", async () => {
  const user = userEvent.setup();
  mount();
  await screen.findByRole("option", { name: /合成模型/ });
  await user.click(screen.getByRole("button", { name: "预检范围与预算" }));
  await screen.findByText("翻译预检");
  await user.click(screen.getByRole("checkbox", { name: /允许将所选 PDF/ }));
  await user.click(
    screen.getByRole("checkbox", { name: /确认该服务由本应用独占/ }),
  );
  await user.clear(screen.getByLabelText("最多模型请求数"));
  await user.type(screen.getByLabelText("最多模型请求数"), "20");
  expect(
    screen.getByRole("button", { name: "生成双语对照 PDF" }),
  ).toBeDisabled();
  vi.mocked(api.prepareTranslation).mockResolvedValue({
    ...preparation,
    service_ready: false,
  });
  await user.click(screen.getByRole("button", { name: "预检范围与预算" }));
  await screen.findByText("翻译引擎尚未就绪，请检查设置后重新预检。");
  expect(
    screen.getByRole("button", { name: "生成双语对照 PDF" }),
  ).toBeDisabled();
});

test("completed artifacts use controlled native opening and other revisions stay hidden", async () => {
  const user = userEvent.setup();
  vi.mocked(api.translations).mockResolvedValue([
    record,
    {
      ...record,
      id: "old",
      document_version_id: "old-revision",
      model_id: "old-model",
    },
  ]);
  mount();
  await screen.findByText("引擎已生成");
  expect(screen.queryByText(/old-model/)).not.toBeInTheDocument();
  expect(api.translations).toHaveBeenCalledWith("p", "v");
  await user.click(screen.getByRole("button", { name: "打开双语 PDF" }));
  expect(invoke).toHaveBeenCalledWith("open_translation_artifact", {
    translationId: "t",
    kind: "dual",
  });
  expect(screen.getByText(/全文质量尚未验证/)).toBeInTheDocument();
  expect(api.createTranslation).not.toHaveBeenCalled();
});

test("mono translation only offers the artifact actually returned by the engine", async () => {
  const user = userEvent.setup();
  vi.mocked(api.translations).mockResolvedValue([
    {
      ...record,
      launch_mode: "bundled",
      output_mode: "mono",
      artifacts: [record.artifacts[0]],
    },
  ]);
  mount();
  await screen.findByText(/fixture · 输出 中文 PDF/);
  expect(
    screen.queryByRole("button", { name: "打开双语 PDF" }),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "打开中文 PDF" }));
  expect(invoke).toHaveBeenCalledWith("open_translation_artifact", {
    translationId: "t",
    kind: "mono",
  });
  expect(api.createTranslation).not.toHaveBeenCalled();
});

test("active translation exposes cancellation without reissuing a model request", async () => {
  const user = userEvent.setup();
  vi.mocked(api.translations).mockResolvedValue([
    { ...record, status: "RUNNING", progress: 30, stage: "翻译文本" },
  ]);
  mount();
  await user.click(await screen.findByRole("button", { name: "取消翻译" }));
  await waitFor(() =>
    expect(api.cancelTranslation).toHaveBeenCalledWith("p", "t"),
  );
  expect(api.createTranslation).not.toHaveBeenCalled();
  expect(api.prepareTranslation).not.toHaveBeenCalled();
});

test("matching cache can be read with zero new network consent", async () => {
  const user = userEvent.setup();
  vi.mocked(api.prepareTranslation).mockResolvedValue({
    ...preparation,
    cache_hit: true,
    cached_translation_id: "t",
    service_ready: false,
  });
  mount();
  await screen.findByRole("option", { name: /合成模型/ });
  await user.click(screen.getByRole("button", { name: "预检范围与预算" }));
  await user.click(
    await screen.findByRole("button", { name: "读取匹配译文缓存" }),
  );
  await waitFor(() =>
    expect(api.createTranslation).toHaveBeenCalledWith(
      "p",
      expect.objectContaining({
        allow_network: false,
        exclusive_service: false,
      }),
    ),
  );
});

test("settings default to the bundled engine without paths; resource check only happens on explicit click", async () => {
  const user = userEvent.setup();
  vi.mocked(api.translationSettings).mockResolvedValue({
    enabled: true,
    service_url: "http://127.0.0.1:8890",
  });
  vi.mocked(api.saveTranslationSettings).mockResolvedValue({
    enabled: true,
    service_url: "http://127.0.0.1:8890",
    launch_mode: "bundled",
  });
  vi.mocked(api.checkTranslationService).mockResolvedValue({
    available: true,
    status: "ok",
    version: "fixture",
    active_tasks: 0,
    message: "合成服务",
  });
  mount(<TranslationSettings connected />);
  const enabled = await screen.findByRole("checkbox", {
    name: "启用文献翻译",
  });
  expect(enabled).toBeChecked();
  expect(
    screen.getByRole("radio", { name: "内置翻译引擎（推荐）" }),
  ).toBeChecked();
  expect(screen.queryByLabelText("Python 解释器路径")).not.toBeInTheDocument();
  expect(
    screen.getByText("高级：外部翻译服务").closest("details"),
  ).not.toHaveAttribute("open");
  expect(api.checkTranslationService).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "保存翻译设置" }));
  await waitFor(() =>
    expect(api.saveTranslationSettings).toHaveBeenCalledWith({
      enabled: true,
      service_url: "http://127.0.0.1:8890",
      launch_mode: "bundled",
      python_path: null,
      server_path: null,
    }),
  );
  await user.click(screen.getByRole("button", { name: "检查内置引擎资源" }));
  await screen.findByText(/运行文件与资源检查通过.*合成服务/);
  expect(api.checkTranslationService).toHaveBeenCalledTimes(1);
  expect(api.createTranslation).not.toHaveBeenCalled();
  expect(invoke).not.toHaveBeenCalled();
});

test("advanced external modes retain paths when returning to the bundled engine", async () => {
  const user = userEvent.setup();
  const saved = {
    enabled: true,
    service_url: "http://127.0.0.1:8890",
    launch_mode: "bundled" as const,
    python_path: "C:\\existing-env\\python.exe",
    server_path: "C:\\existing-server\\server.py",
  };
  vi.mocked(api.translationSettings).mockResolvedValue(saved);
  vi.mocked(api.saveTranslationSettings).mockResolvedValue(saved);
  mount(<TranslationSettings connected />);
  await screen.findByRole("radio", { name: "内置翻译引擎（推荐）" });
  await user.click(screen.getByText("高级：外部翻译服务"));
  await user.click(screen.getByRole("radio", { name: "外部服务自动启停" }));
  expect(screen.getByLabelText("Python 解释器路径")).toHaveValue(
    saved.python_path,
  );
  expect(screen.getByLabelText("Server 脚本路径")).toHaveValue(
    saved.server_path,
  );
  await user.click(screen.getByRole("radio", { name: "手动连接外部服务" }));
  expect(screen.queryByLabelText("Python 解释器路径")).not.toBeInTheDocument();
  expect(screen.getByLabelText("本机服务地址")).toHaveValue(saved.service_url);
  await user.click(screen.getByRole("radio", { name: "内置翻译引擎（推荐）" }));
  expect(screen.queryByLabelText("本机服务地址")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "保存翻译设置" }));
  await waitFor(() =>
    expect(api.saveTranslationSettings).toHaveBeenCalledWith(saved),
  );
  expect(api.checkTranslationService).not.toHaveBeenCalled();
  expect(invoke).not.toHaveBeenCalled();
});

test("managed mode saves one-time launch paths and checks configuration without starting a process", async () => {
  const user = userEvent.setup();
  vi.mocked(api.translationSettings).mockResolvedValue({
    enabled: true,
    service_url: "http://127.0.0.1:8890",
    launch_mode: "managed",
    python_path: null,
    server_path: null,
  });
  vi.mocked(api.saveTranslationSettings).mockResolvedValue({
    enabled: true,
    service_url: "http://127.0.0.1:8890",
    launch_mode: "managed",
    python_path: "C:\\translation-env\\python.exe",
    server_path: "C:\\translation-server\\server.py",
  });
  vi.mocked(api.checkTranslationService).mockResolvedValue({
    available: true,
    status: "configured",
    version: null,
    active_tasks: 0,
    message: "配置检查通过，未启动进程",
  });
  mount(<TranslationSettings connected />);
  await user.click(screen.getByText("高级：外部翻译服务"));
  await waitFor(() =>
    expect(
      screen.getByRole("radio", { name: "外部服务自动启停" }),
    ).toBeChecked(),
  );
  await user.type(
    screen.getByLabelText("Python 解释器路径"),
    "C:\\translation-env\\python.exe",
  );
  await user.type(
    screen.getByLabelText("Server 脚本路径"),
    "C:\\translation-server\\server.py",
  );
  expect(screen.getByRole("button", { name: "检查启动配置" })).toBeDisabled();
  expect(api.checkTranslationService).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "保存翻译设置" }));
  await waitFor(() =>
    expect(api.saveTranslationSettings).toHaveBeenCalledWith({
      enabled: true,
      service_url: "http://127.0.0.1:8890",
      launch_mode: "managed",
      python_path: "C:\\translation-env\\python.exe",
      server_path: "C:\\translation-server\\server.py",
    }),
  );
  await user.click(screen.getByRole("button", { name: "检查启动配置" }));
  await screen.findByText(/启动配置就绪.*配置检查通过，未启动进程/);
  expect(api.checkTranslationService).toHaveBeenCalledTimes(1);
  expect(api.prepareTranslation).not.toHaveBeenCalled();
  expect(api.createTranslation).not.toHaveBeenCalled();
  expect(invoke).not.toHaveBeenCalled();
});

test("managed offline preflight permits an explicitly authorized translation without starting during preparation", async () => {
  const user = userEvent.setup();
  vi.mocked(api.translationSettings).mockResolvedValue({
    enabled: true,
    service_url: "http://127.0.0.1:8890",
    launch_mode: "managed",
    python_path: "C:\\env\\python.exe",
    server_path: "C:\\server\\server.py",
  });
  vi.mocked(api.prepareTranslation).mockResolvedValue({
    ...preparation,
    launch_mode: "managed",
    service_ready: true,
    warnings: ["本地启动配置有效，进程尚未运行"],
  });
  mount();
  await screen.findByRole("option", { name: /合成模型/ });
  await user.click(screen.getByRole("button", { name: "预检范围与预算" }));
  await screen.findByText(/启动配置就绪。预检没有启动进程/);
  expect(api.createTranslation).not.toHaveBeenCalled();
  expect(api.checkTranslationService).not.toHaveBeenCalled();
  expect(invoke).not.toHaveBeenCalled();
  await user.click(screen.getByRole("checkbox", { name: /允许将所选 PDF/ }));
  await user.click(
    screen.getByRole("checkbox", { name: /确认该服务由本应用独占/ }),
  );
  await user.click(screen.getByRole("button", { name: "生成双语对照 PDF" }));
  await waitFor(() =>
    expect(api.createTranslation).toHaveBeenCalledWith(
      "p",
      expect.objectContaining({
        expected_fingerprint: preparation.prepare_fingerprint,
        allow_network: true,
        exclusive_service: true,
      }),
    ),
  );
});

test("managed runtime file browsing fills paths and cancelling a picker keeps the existing path", async () => {
  const user = userEvent.setup();
  vi.mocked(api.translationSettings).mockResolvedValue({
    enabled: true,
    service_url: "http://127.0.0.1:8890",
    launch_mode: "managed",
    python_path: null,
    server_path: "C:\\server\\server.py",
  });
  vi.mocked(invoke)
    .mockResolvedValueOnce("C:\\chosen-env\\python.exe")
    .mockResolvedValueOnce(null);
  mount(<TranslationSettings connected />);
  await user.click(screen.getByText("高级：外部翻译服务"));
  await user.click(
    await screen.findByRole("button", { name: "选择 Python 解释器" }),
  );
  await waitFor(() =>
    expect(screen.getByLabelText("Python 解释器路径")).toHaveValue(
      "C:\\chosen-env\\python.exe",
    ),
  );
  expect(invoke).toHaveBeenNthCalledWith(1, "choose_translation_runtime_file", {
    kind: "python",
  });
  await user.click(screen.getByRole("button", { name: "选择 Server 脚本" }));
  await waitFor(() =>
    expect(invoke).toHaveBeenNthCalledWith(
      2,
      "choose_translation_runtime_file",
      { kind: "server" },
    ),
  );
  expect(screen.getByLabelText("Server 脚本路径")).toHaveValue(
    "C:\\server\\server.py",
  );
  expect(api.checkTranslationService).not.toHaveBeenCalled();
  expect(api.createTranslation).not.toHaveBeenCalled();
});

test("changing saved launch configuration invalidates an existing preparation", async () => {
  const user = userEvent.setup();
  const { client } = mount();
  await screen.findByRole("option", { name: /合成模型/ });
  await user.click(screen.getByRole("button", { name: "预检范围与预算" }));
  await screen.findByText("翻译预检");
  await user.click(screen.getByRole("checkbox", { name: /允许将所选 PDF/ }));
  await user.click(
    screen.getByRole("checkbox", { name: /确认该服务由本应用独占/ }),
  );
  expect(
    screen.getByRole("button", { name: "生成双语对照 PDF" }),
  ).toBeEnabled();
  await act(async () => {
    client.setQueryData(["translation-settings"], {
      enabled: true,
      service_url: "http://127.0.0.1:8890",
      launch_mode: "managed",
      python_path: "C:\\new-env\\python.exe",
      server_path: "C:\\server\\server.py",
    });
  });
  await waitFor(() =>
    expect(screen.queryByText("翻译预检")).not.toBeInTheDocument(),
  );
  expect(
    screen.getByRole("button", { name: "生成双语对照 PDF" }),
  ).toBeDisabled();
});

test("cancelled records use their frozen launch mode while legacy records remain manual", async () => {
  vi.mocked(api.translationSettings).mockResolvedValue({
    enabled: true,
    service_url: "http://127.0.0.1:8890",
    launch_mode: "managed",
    python_path: "C:\\env\\python.exe",
    server_path: "C:\\server\\server.py",
  });
  vi.mocked(api.translations).mockResolvedValue([
    { ...record, id: "managed", status: "CANCELLED", launch_mode: "managed" },
    { ...record, id: "legacy", status: "CANCELLED" },
  ]);
  mount();
  await screen.findByText(/已阻断后续模型请求，并请求关闭本应用启动的服务/);
  expect(
    screen.getByText(
      /已阻断后续模型请求；外部排版可能仍在结束处理中，手动启动的服务不会被关闭/,
    ),
  ).toBeInTheDocument();
  expect(api.createTranslation).not.toHaveBeenCalled();
});

test("failed translation is excluded from generic local retry", async () => {
  vi.mocked(api.jobs).mockResolvedValue([
    {
      id: "j",
      kind: "pdf_translation",
      project_id: "p",
      status: "failed",
      stage: "translating",
      attempt: 1,
      error: "fixture failure",
      result: null,
      created_at: record.created_at,
      updated_at: record.updated_at,
    },
  ]);
  mount(<JobHistory connected />);
  const history = await screen.findByRole("region", { name: "文献任务" });
  await within(history).findByText("文献翻译 · 失败");
  expect(
    within(history).queryByRole("button", { name: "重试本地处理" }),
  ).not.toBeInTheDocument();
});
