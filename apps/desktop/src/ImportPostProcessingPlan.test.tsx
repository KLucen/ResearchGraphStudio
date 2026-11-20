import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { defaultPostImportPlan, request, type PostImportPlan } from "./api";
import { ImportPostProcessingPlan } from "./ImportPostProcessingPlan";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, request: vi.fn() };
});

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(request).mockResolvedValue({
    roles: { document_parse: "vision" },
    profiles: [
      {
        id: "vision",
        name: "Synthetic vision",
        model: "fixture",
        parameters: {
          document_timeout_seconds: 600,
          document_total_timeout_seconds: 1800,
          capabilities: {
            document_input: "image",
            document_transport: "chat_images",
            multimodal: true,
          },
        },
      },
    ],
  });
});

function mount(initial: Partial<PostImportPlan> = {}) {
  const changed = vi.fn();
  function Controlled() {
    const [plan, setPlan] = useState({
      ...defaultPostImportPlan(),
      parse: true,
      ...initial,
    });
    return (
      <ImportPostProcessingPlan
        value={plan}
        onChange={(next) => {
          changed(next);
          setPlan(next);
        }}
      />
    );
  }
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <Controlled />
    </QueryClientProvider>,
  );
  return changed;
}

test("new model plans default to sequential five-page batches with separate repair consent", async () => {
  expect(defaultPostImportPlan()).toMatchObject({
    overview: false,
    reading: false,
    translation_mode: "none",
  });
  mount();
  await screen.findByText(/论文解析模型：Synthetic vision/);
  expect(
    screen.getByRole("checkbox", { name: "按页分批解析（顺序执行）" }),
  ).toBeChecked();
  expect(
    screen.getByRole("combobox", { name: "每批最多页数（含共享页）" }),
  ).toHaveValue("5");
  expect(screen.getByText(/相邻批次共享 1 页并保留原始页码/)).toBeVisible();
  expect(
    screen.getByRole("checkbox", {
      name: "允许契约校验失败时修复本批格式（可能额外收费）",
    }),
  ).not.toBeChecked();
  expect(screen.getByLabelText("解析请求预算")).toHaveTextContent(
    "抽取 B 次，边界检查最多 B−1 次，格式修复 0 次",
  );
  expect(screen.getByText(/单请求响应等待上限 600 秒/)).toBeVisible();
});

test("changing batch and repair budget requires fresh network consent", async () => {
  const user = userEvent.setup();
  const changed = mount({ allow_network: true });
  const consent = screen.getByRole("checkbox", {
    name: "允许将所选 PDF 发送给已配置的论文解析模型",
  });
  await user.click(
    screen.getByRole("checkbox", {
      name: "允许契约校验失败时修复本批格式（可能额外收费）",
    }),
  );
  expect(consent).not.toBeChecked();
  expect(changed).toHaveBeenLastCalledWith(
    expect.objectContaining({
      allow_format_repair: true,
      allow_network: false,
    }),
  );
  expect(screen.getByLabelText("解析请求预算")).toHaveTextContent(
    "格式修复最多 B 次",
  );
  expect(
    screen.getByText(/仅发送该批响应、契约和错误，不重传 PDF/),
  ).toBeVisible();
  await user.click(consent);
  await user.selectOptions(
    screen.getByRole("combobox", { name: "每批最多页数（含共享页）" }),
    "8",
  );
  expect(consent).not.toBeChecked();
  expect(changed).toHaveBeenLastCalledWith(
    expect.objectContaining({ pages_per_batch: 8, allow_network: false }),
  );
  await user.click(
    screen.getByRole("checkbox", {
      name: "允许按需调用模型检查相邻批次的截断与续接",
    }),
  );
  expect(screen.getByLabelText("解析请求预算")).toHaveTextContent(
    "边界检查 0 次",
  );
});

test("single-request and local modes do not imply batch repair authorization", async () => {
  const user = userEvent.setup();
  mount({ allow_network: true });
  await user.click(
    screen.getByRole("checkbox", { name: "按页分批解析（顺序执行）" }),
  );
  expect(screen.getByText(/本次不使用批次检查点/)).toBeVisible();
  expect(screen.queryByLabelText("解析请求预算")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("checkbox", {
      name: "允许契约校验失败时修复本批格式（可能额外收费）",
    }),
  ).not.toBeInTheDocument();
  await user.click(
    screen.getByRole("radio", { name: "本地解析（不调用模型）" }),
  );
  expect(
    screen.queryByRole("checkbox", { name: "按页分批解析（顺序执行）" }),
  ).not.toBeInTheDocument();
});
