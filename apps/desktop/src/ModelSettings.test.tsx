import { render, screen, waitFor } from "@testing-library/react";
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
      }),
    ),
  );
  expect(
    localStorage.getItem("researchgraph.model-provider-ids"),
  ).not.toContain("unit-credential-value");
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
