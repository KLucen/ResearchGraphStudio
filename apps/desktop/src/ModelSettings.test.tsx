import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { ModelSettings } from "./ModelSettings";
import { request } from "./api";

vi.mock("./api", () => ({ request: vi.fn() }));
beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
});
test("save clears the password field and never places the key in query cache or browser storage", async () => {
  const user = userEvent.setup();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  vi.mocked(request).mockResolvedValue({
    profiles: [],
    roles: { extraction: null, reasoning: null },
  });
  render(
    <QueryClientProvider client={client}>
      <ModelSettings connected />
    </QueryClientProvider>,
  );
  await user.type(screen.getByLabelText("配置名称"), "Gateway");
  await user.type(
    screen.getByLabelText("Base URL"),
    "https://model.example/v1",
  );
  await user.type(screen.getByLabelText("Model ID"), "fixture-model");
  const secret = "unit-credential-value";
  await user.type(screen.getByLabelText("API Key"), secret);
  await user.click(screen.getByRole("button", { name: "保存模型配置" }));
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "POST",
      "/api/v1/settings/models",
      expect.objectContaining({ api_key: secret }),
    ),
  );
  expect(screen.getByLabelText("API Key")).toHaveValue("");
  expect(
    JSON.stringify(
      client
        .getQueryCache()
        .getAll()
        .map((q) => q.state.data),
    ),
  ).not.toContain(secret);
  expect(localStorage.length).toBe(0);
});

test("role selection preserves the other role and connection test uses the selected profile", async () => {
  const user = userEvent.setup();
  vi.mocked(request).mockImplementation(async (method, path) => {
    if (path.endsWith("/test"))
      return { connected: true, valid_json: true, mock: false };
    return {
      profiles: [
        {
          id: "m",
          name: "Model",
          model: "fixture",
          provider: "compatible",
          base_url: "https://model.example/v1",
          has_api_key: true,
        },
      ],
      roles: { extraction: null, reasoning: "m" },
    };
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ModelSettings connected />
    </QueryClientProvider>,
  );
  await screen.findByText("Model · compatible · fixture");
  await user.selectOptions(screen.getByLabelText("Extraction 抽取模型"), "m");
  expect(request).toHaveBeenCalledWith("POST", "/api/v1/settings/model-roles", {
    extraction: "m",
    reasoning: "m",
  });
  await user.click(screen.getByRole("button", { name: "测试连接 Model" }));
  await screen.findByText("真实模型连接成功；JSON 校验通过");
});
