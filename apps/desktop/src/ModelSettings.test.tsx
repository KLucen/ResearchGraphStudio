import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { ModelSettings, type GlobalModels } from "./ModelSettings";
import { request } from "./api";

vi.mock("./api", () => ({ request: vi.fn() }));

const empty: GlobalModels = {
  connections: [],
  profiles: [],
  roles: { extraction: null, reasoning: null },
};
const connection = {
  id: "c",
  name: "Gateway",
  provider: "compatible" as const,
  base_url: "https://model.example/v1",
  has_api_key: true,
};
const profile = {
  id: "m",
  name: "Model",
  connection_id: "c",
  connection_name: "Gateway",
  provider: "compatible" as const,
  base_url: connection.base_url,
  model: "fixture",
  has_api_key: true,
  parameters: {
    temperature: null,
    top_p: null,
    reasoning_effort: null,
    timeout_seconds: 90,
    json_mode: true,
  },
};

function mount() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ModelSettings connected />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  vi.mocked(request).mockImplementation(async (method, path) => {
    if (method === "GET" && path === "/api/v1/settings/models") return empty;
    if (method === "POST" && path === "/api/v1/settings/connections")
      return connection;
    if (method === "POST" && path === "/api/v1/settings/models") return profile;
    return {};
  });
});

test("common provider preset saves a connection and its model directory", async () => {
  const user = userEvent.setup();
  mount();

  await user.click(screen.getByRole("button", { name: /添加模型提供商/ }));
  expect(screen.getByRole("tab", { name: "第三方模型提供商" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await user.click(screen.getByRole("button", { name: /DeepSeek/ }));
  await user.type(screen.getByLabelText("API 密钥"), "unit-credential-value");
  await user.click(screen.getByRole("button", { name: "创建提供商" }));

  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "POST",
      "/api/v1/settings/connections",
      expect.objectContaining({
        name: "DeepSeek",
        provider: "compatible",
        base_url: "https://api.deepseek.com/v1",
        api_key: "unit-credential-value",
      }),
    ),
  );
  const connectionCall = vi
    .mocked(request)
    .mock.calls.find(
      (call) =>
        call[0] === "POST" && call[1] === "/api/v1/settings/connections",
    );
  expect(connectionCall?.[2]).not.toHaveProperty("provider_id");
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "POST",
      "/api/v1/settings/models",
      expect.objectContaining({
        connection_id: "c",
        model: "deepseek-chat",
        parameters: expect.objectContaining({
          text_timeout_policy: "activity",
          timeout_seconds: 90,
        }),
      }),
    ),
  );
  expect(
    localStorage.getItem("researchgraph.model-provider-ids"),
  ).not.toContain("unit-credential-value");
});

test("PDF capability can be declared and remains on provider edits", async () => {
  const user = userEvent.setup();
  const pdfProfile = {
    ...profile,
    parameters: {
      ...profile.parameters,
      capabilities: {
        document_input: "pdf" as const,
        document_transport: "chat_file" as const,
        multimodal: false,
        source: "user_declared",
        context_window: null,
        max_output_tokens: null,
      },
    },
  };
  vi.mocked(request).mockImplementation(async (method, path) => {
    if (method === "GET")
      return {
        connections: [connection],
        profiles: [pdfProfile],
        roles: { ...empty.roles, document_parse: "m" },
      };
    if (path.includes("connections") && path.endsWith("update"))
      return connection;
    return {};
  });
  mount();
  await waitFor(() =>
    expect(screen.getByLabelText("论文解析模型")).toHaveValue("m"),
  );
  await user.click(screen.getByRole("button", { name: "编辑" }));
  expect(screen.getByLabelText("文档输入能力 1")).toHaveValue("pdf");
  expect(screen.getByLabelText("文件传输方式 1")).toHaveValue("chat_file");
  await user.click(screen.getByRole("button", { name: "保存提供商" }));
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "POST",
      "/api/v1/settings/models/m/update",
      expect.objectContaining({
        parameters: {
          ...pdfProfile.parameters,
          text_timeout_policy: "activity",
          document_timeout_seconds: 600,
          document_total_timeout_seconds: 1800,
        },
      }),
    ),
  );
});

test("visual plan recommendation is explicit and preserves unrelated model parameters", async () => {
  const user = userEvent.setup();
  const planConnection = {
    ...connection,
    base_url: "https://ark.cn-beijing.volces.com/api/plan/v3",
  };
  const planProfile = {
    ...profile,
    base_url: planConnection.base_url,
    parameters: {
      ...profile.parameters,
      temperature: 0.25,
      top_p: 0.7,
      reasoning_effort: "max" as const,
    },
  };
  vi.mocked(request).mockImplementation(async (method, path) => {
    if (method === "GET")
      return {
        connections: [planConnection],
        profiles: [planProfile],
        roles: { ...empty.roles, document_parse: "m" },
      };
    if (path.includes("connections") && path.endsWith("update"))
      return planConnection;
    return {};
  });
  mount();
  await user.click(await screen.findByRole("button", { name: "编辑" }));
  expect(screen.getByLabelText("文件传输方式 1")).toHaveValue("none");
  expect(screen.getByLabelText("推理强度 1")).toHaveValue("max");
  expect(screen.getByLabelText("文档等待超时 1")).toHaveValue(600);
  await user.click(screen.getByRole("button", { name: "应用推荐解析配置 1" }));
  expect(screen.getByLabelText("文件传输方式 1")).toHaveValue("chat_images");
  expect(screen.getByLabelText("文档输入能力 1")).toHaveValue("image");
  expect(screen.getByLabelText("推理强度 1")).toHaveValue("none");
  await user.clear(screen.getByLabelText("文档等待超时 1"));
  await user.type(screen.getByLabelText("文档等待超时 1"), "720");
  await user.click(screen.getByRole("button", { name: "保存提供商" }));
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "POST",
      "/api/v1/settings/models/m/update",
      expect.objectContaining({
        parameters: expect.objectContaining({
          temperature: 0.25,
          top_p: 0.7,
          timeout_seconds: 90,
          document_timeout_seconds: 720,
          document_total_timeout_seconds: 1800,
          reasoning_effort: "none",
          capabilities: expect.objectContaining({
            document_input: "image",
            multimodal: true,
            document_transport: "chat_images",
          }),
        }),
      }),
    ),
  );
});

test("document timeout controls reject an invalid total and allow a corrected save", async () => {
  const user = userEvent.setup();
  vi.mocked(request).mockImplementation(async (method, path) => {
    if (method === "GET")
      return {
        connections: [connection],
        profiles: [profile],
        roles: empty.roles,
      };
    if (path.includes("connections") && path.endsWith("update"))
      return connection;
    return {};
  });
  mount();
  await user.click(await screen.findByRole("button", { name: "编辑" }));
  await user.clear(screen.getByLabelText("文档解析总时限 1"));
  await user.type(screen.getByLabelText("文档解析总时限 1"), "300");
  expect(screen.getByRole("button", { name: "保存提供商" })).toBeDisabled();
  expect(screen.getByRole("alert")).toHaveTextContent("不小于等待超时");
  await user.clear(screen.getByLabelText("文档解析总时限 1"));
  await user.type(screen.getByLabelText("文档解析总时限 1"), "900");
  expect(screen.getByRole("button", { name: "保存提供商" })).toBeEnabled();
  await user.selectOptions(screen.getByLabelText("文档输入能力 1"), "image");
  expect(screen.getByLabelText("文件传输方式 1")).toHaveValue("chat_images");
  await user.selectOptions(screen.getByLabelText("推理强度 1"), "low");
  await user.click(screen.getByRole("button", { name: "保存提供商" }));
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "POST",
      "/api/v1/settings/models/m/update",
      expect.objectContaining({
        parameters: expect.objectContaining({
          document_timeout_seconds: 600,
          document_total_timeout_seconds: 900,
          reasoning_effort: "low",
        }),
      }),
    ),
  );
});

test("legacy null policy displays the new activity default without rewriting it on an unrelated save", async () => {
  const user = userEvent.setup();
  const legacyProfile = {
    ...profile,
    parameters: { ...profile.parameters, text_timeout_policy: null },
  };
  vi.mocked(request).mockImplementation(async (method, path) => {
    if (method === "GET")
      return {
        connections: [connection],
        profiles: [legacyProfile],
        roles: empty.roles,
      };
    if (path.includes("connections") && path.endsWith("update"))
      return connection;
    return {};
  });
  mount();
  await user.click(await screen.findByRole("button", { name: "编辑" }));
  expect(screen.getByLabelText("文字生成等待方式 1")).toHaveValue("activity");
  expect(screen.getByLabelText("文字等待超时 1")).toHaveValue(90);
  expect(screen.getByText(/连接单独等待最多 15 秒/)).toHaveTextContent(
    "收到正文或公开 reasoning 增量会重新计时",
  );
  expect(screen.getByText(/纯心跳不算生成/)).toHaveTextContent(
    "服务端隐藏的思考无法直接观测",
  );
  expect(screen.getByText(/纯心跳不算生成/)).toHaveTextContent(
    "非流式服务只能监测响应数据接收进展。",
  );
  expect(screen.getByText(/180 表示 180 秒/)).toHaveTextContent(
    "显式继续知识任务会使用当前设置创建后继",
  );
  await user.click(screen.getByRole("button", { name: "保存提供商" }));
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "POST",
      "/api/v1/settings/models/m/update",
      expect.objectContaining({
        parameters: expect.objectContaining({
          text_timeout_policy: null,
          timeout_seconds: 90,
        }),
      }),
    ),
  );
});

test.each(["activity", "legacy"] as const)(
  "explicit text timeout policy %s is saved independently from document limits",
  async (policy) => {
    const user = userEvent.setup();
    const configuredProfile = {
      ...profile,
      parameters: {
        ...profile.parameters,
        text_timeout_policy: "legacy" as const,
        document_timeout_seconds: 720,
        document_total_timeout_seconds: 2400,
      },
    };
    vi.mocked(request).mockImplementation(async (method, path) => {
      if (method === "GET")
        return {
          connections: [connection],
          profiles: [configuredProfile],
          roles: empty.roles,
        };
      if (path.includes("connections") && path.endsWith("update"))
        return connection;
      return {};
    });
    mount();
    await user.click(await screen.findByRole("button", { name: "编辑" }));
    expect(screen.getByLabelText("文字生成等待方式 1")).toHaveValue("legacy");
    await user.selectOptions(
      screen.getByLabelText("文字生成等待方式 1"),
      policy,
    );
    fireEvent.change(screen.getByLabelText("文字等待超时 1"), {
      target: { value: "180" },
    });
    expect(screen.getByLabelText("文档等待超时 1")).toHaveValue(720);
    expect(screen.getByLabelText("文档解析总时限 1")).toHaveValue(2400);
    await user.click(screen.getByRole("button", { name: "保存提供商" }));
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith(
        "POST",
        "/api/v1/settings/models/m/update",
        expect.objectContaining({
          parameters: expect.objectContaining({
            text_timeout_policy: policy,
            timeout_seconds: 180,
            document_timeout_seconds: 720,
            document_total_timeout_seconds: 2400,
          }),
        }),
      ),
    );
    expect(
      vi
        .mocked(request)
        .mock.calls.some((call) => String(call[1]).endsWith("/test")),
    ).toBe(false);
  },
);

test("text waiting seconds reject zero, fractional and out-of-range values before saving", async () => {
  const user = userEvent.setup();
  mount();
  await user.click(screen.getByRole("button", { name: /添加模型提供商/ }));
  const input = screen.getByLabelText("文字等待超时 1");
  for (const invalid of ["", "4", "181", "90.5"]) {
    fireEvent.change(input, { target: { value: invalid } });
    expect(screen.getByRole("button", { name: "创建提供商" })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "文字等待须为 5–180 秒的整数",
    );
  }
  for (const valid of ["5", "180"]) {
    fireEvent.change(input, { target: { value: valid } });
    expect(screen.getByRole("button", { name: "创建提供商" })).toBeEnabled();
  }
  expect(vi.mocked(request).mock.calls.some((call) => call[0] === "POST")).toBe(
    false,
  );
});

test("custom provider exposes protocol and editable model directory", async () => {
  const user = userEvent.setup();
  mount();

  await user.click(screen.getByRole("button", { name: /添加模型提供商/ }));
  await user.click(screen.getByRole("tab", { name: "自定义模型 API" }));
  await user.type(screen.getByLabelText("Provider ID"), "acme-gateway");
  await user.clear(screen.getByLabelText("显示名称"));
  await user.type(screen.getByLabelText("显示名称"), "Acme Gateway");
  await user.clear(screen.getByLabelText("API 地址"));
  await user.type(
    screen.getByLabelText("API 地址"),
    "https://gateway.example/v1",
  );
  await user.clear(screen.getByLabelText("模型 ID 1"));
  await user.type(screen.getByLabelText("模型 ID 1"), "acme-reasoner");
  await user.clear(screen.getByLabelText("模型显示名称 1"));
  await user.type(screen.getByLabelText("模型显示名称 1"), "Reasoner");
  await user.click(screen.getByRole("button", { name: "创建提供商" }));

  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "POST",
      "/api/v1/settings/connections",
      expect.objectContaining({
        name: "Acme Gateway",
        provider: "compatible",
        base_url: "https://gateway.example/v1",
      }),
    ),
  );
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "POST",
      "/api/v1/settings/models",
      expect.objectContaining({
        name: "Reasoner",
        model: "acme-reasoner",
      }),
    ),
  );
});

test("role selection and connection testing use the selected profile", async () => {
  const user = userEvent.setup();
  const settings = {
    connections: [connection],
    profiles: [profile],
    roles: { extraction: null, reasoning: "m" },
  };
  vi.mocked(request).mockImplementation(async (method, path) => {
    if (method === "GET") return settings;
    if (path.endsWith("/test")) return { connected: true, valid_json: true };
    return settings;
  });
  mount();

  expect(await screen.findAllByText("Model · fixture")).not.toHaveLength(0);
  await user.selectOptions(screen.getByLabelText("论文概览模型"), "m");
  expect(request).toHaveBeenCalledWith("POST", "/api/v1/settings/model-roles", {
    extraction: "m",
    reasoning: "m",
  });
  await user.click(screen.getByRole("button", { name: "测试连接" }));
  await screen.findByText(
    "连接成功，固定 JSON 校验通过。这只验证接口可用性，不代表论文概览质量已验证。",
  );
});

test("editing a provider updates model profiles without sending credentials to profile routes", async () => {
  const user = userEvent.setup();
  vi.mocked(request).mockImplementation(async (method, path) => {
    if (method === "GET")
      return {
        connections: [connection],
        profiles: [profile],
        roles: empty.roles,
      };
    if (path.endsWith("/update") && path.includes("/connections/"))
      return connection;
    return {};
  });
  mount();

  await user.click(await screen.findByRole("button", { name: "编辑" }));
  await user.click(screen.getByRole("button", { name: "+ 添加模型" }));
  await user.type(screen.getByLabelText("模型 ID 2"), "second-model");
  await user.type(screen.getByLabelText("模型显示名称 2"), "Second");
  await user.click(screen.getByRole("button", { name: "保存提供商" }));

  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "POST",
      "/api/v1/settings/models",
      expect.objectContaining({
        model: "second-model",
        name: "Second",
      }),
    ),
  );
  const profileCalls = vi
    .mocked(request)
    .mock.calls.filter(
      (call) =>
        call[0] === "POST" &&
        String(call[1]).includes("/api/v1/settings/models"),
    );
  expect(
    profileCalls.every(
      (call) => !(call[2] as Record<string, unknown>)?.api_key,
    ),
  ).toBe(true);
});

test("removing a saved model from the directory archives it when the provider is saved", async () => {
  const user = userEvent.setup();
  const archivePath = "/api/v1/archive";
  vi.mocked(request).mockImplementation(async (method, path) => {
    if (method === "GET")
      return {
        connections: [connection],
        profiles: [profile, { ...profile, id: "other", model: "another" }],
        roles: empty.roles,
      };
    if (path.includes("/connections/") && path.endsWith("/update"))
      return connection;
    return {};
  });
  mount();

  await user.click(await screen.findByRole("button", { name: "编辑" }));
  await user.click(screen.getByRole("button", { name: "保存时归档模型 1" }));
  expect(request).not.toHaveBeenCalledWith(
    "POST",
    archivePath,
    expect.anything(),
    expect.anything(),
  );
  await user.click(screen.getByRole("button", { name: "保存提供商" }));
  await screen.findByText("Gateway 已保存。1 项模型配置已移至归档管理。");
  expect(request).toHaveBeenCalledWith(
    "POST",
    archivePath,
    { kind: "model_profile", target_id: "m" },
    expect.any(String),
  );
});
