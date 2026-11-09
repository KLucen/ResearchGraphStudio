import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { ZoteroImport } from "./ZoteroImport";
import { api, request } from "./api";

vi.mock("./api", () => ({ request: vi.fn(), api: { jobAction: vi.fn() } }));
beforeEach(() => {
  vi.resetAllMocks();
});
test("collection selection and select-all submit only available attachments without filesystem paths", async () => {
  const user = userEvent.setup();
  vi.mocked(request).mockImplementation(async (method, path) => {
    if (path.includes("/collections?"))
      return [
        { key: "COLLECT1", data: { name: "Test", parentCollection: false } },
      ];
    if (path.endsWith("/browse"))
      return {
        next_start: null,
        items: [
          {
            key: "PAPER001",
            title: "Fixture paper",
            attachments: [
              {
                key: "ATTACH01",
                title: "PDF",
                filename: "fixture.pdf",
                available: true,
              },
              {
                key: "ATTACH02",
                title: "Missing",
                filename: "missing.pdf",
                available: false,
              },
            ],
          },
        ],
      };
    return [];
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ZoteroImport projectId="p" connected />
    </QueryClientProvider>,
  );
  await user.click(screen.getByRole("button", { name: "连接并读取分类" }));
  await screen.findByLabelText("Collection");
  await user.selectOptions(screen.getByLabelText("Collection"), "COLLECT1");
  await screen.findByText("Fixture paper");
  expect(screen.getByLabelText("选择附件 ATTACH02")).toBeDisabled();
  await user.click(screen.getByLabelText("全选本页可用附件"));
  expect(
    screen.getByRole("button", { name: "开始建图 · 已选 1 个附件" }),
  ).toBeDisabled();
  await user.click(screen.getByRole("checkbox", { name: /同意向已配置模型/ }));
  await user.click(
    screen.getByRole("button", { name: "开始建图 · 已选 1 个附件" }),
  );
  expect(request).toHaveBeenCalledWith(
    "POST",
    "/api/v1/projects/p/zotero-imports",
    {
      library: "users/0",
      collection_key: "COLLECT1",
      mode: "reference",
      extract_after_parse: true,
      provider: "project",
      allow_network: true,
      selections: [{ item_key: "PAPER001", attachment_key: "ATTACH01" }],
    },
    expect.any(String),
  );
});

test("failed item remains visible and can be retried independently", async () => {
  const user = userEvent.setup();
  vi.mocked(request).mockImplementation(async (method, path) => {
    if (path.includes("/collections?"))
      return [{ key: "COLLECT1", data: { name: "Test" } }];
    if (path.endsWith("/browse")) return { items: [], next_start: null };
    return [
      {
        library: "users/0",
        collection_key: "COLLECT1",
        item_key: "PAPER001",
        attachment_key: "ATTACH01",
        job: {
          id: "failed-job",
          status: "failed",
          error: "PDF 未下载",
          stage: "reading",
        },
      },
    ];
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ZoteroImport projectId="p" connected />
    </QueryClientProvider>,
  );
  await user.click(screen.getByRole("button", { name: "连接并读取分类" }));
  await screen.findByLabelText("Collection");
  await user.selectOptions(screen.getByLabelText("Collection"), "COLLECT1");
  await screen.findByText("PDF 未下载");
  await user.click(screen.getByRole("button", { name: "重试 ATTACH01" }));
  expect(api.jobAction).toHaveBeenCalledWith(
    "failed-job",
    "retry",
    expect.any(String),
  );
});

test("Lite mode submits local parsing only and hides model controls", async () => {
  const user = userEvent.setup();
  vi.mocked(request).mockImplementation(async (_method, path) => {
    if (path.includes("/collections?"))
      return [{ key: "COLLECT1", data: { name: "Test" } }];
    if (path.endsWith("/browse"))
      return {
        items: [
          {
            key: "PAPER001",
            title: "Lite paper",
            attachments: [
              {
                key: "ATTACH01",
                title: "PDF",
                filename: "fixture.pdf",
                available: true,
              },
            ],
          },
        ],
        next_start: null,
      };
    if (path.endsWith("/zotero-imports")) return [];
    return [];
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ZoteroImport projectId="p" connected liteMode />
    </QueryClientProvider>,
  );
  await user.click(screen.getByRole("button", { name: "连接并读取分类" }));
  await user.selectOptions(
    await screen.findByLabelText("Collection"),
    "COLLECT1",
  );
  await screen.findByText("Lite paper");
  expect(screen.getByText(/Lite 模式：仅解析/)).toBeVisible();
  expect(screen.queryByText("解析后直接建图")).toBeNull();
  expect(screen.queryByText("同意向已配置模型发送所选论文原文片段")).toBeNull();
  await user.click(screen.getByLabelText("全选本页可用附件"));
  await user.click(
    screen.getByRole("button", { name: "仅解析 · 已选 1 个附件" }),
  );
  expect(request).toHaveBeenCalledWith(
    "POST",
    "/api/v1/projects/p/zotero-imports",
    expect.objectContaining({
      extract_after_parse: false,
      allow_network: false,
    }),
    expect.any(String),
  );
});
