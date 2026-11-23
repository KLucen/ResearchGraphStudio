import { beforeEach, expect, test, vi } from "vitest";
import { request } from "./api";
import { knowledgeApi, knowledgeErrorMessage } from "./knowledgeApi";
import {
  knowledgePapers,
  knowledgeReport,
  knowledgeSettings,
} from "./knowledgeFixtures";
vi.mock("./api", () => ({ request: vi.fn() }));
beforeEach(() => vi.clearAllMocks());

test("invalid knowledge response directs error details to the task record without guessing the cause", () => {
  expect(knowledgeErrorMessage("KNOWLEDGE_RESPONSE_INVALID")).toBe(
    "知识任务未完成。错误详情见任务记录；可在此显式继续，系统不会自动重发。",
  );
  expect(knowledgeErrorMessage("KNOWLEDGE_RESPONSE_INVALID")).not.toMatch(
    /格式|来源|原始响应|知识库查看原因/,
  );
});

test("reports retrieves every page and preserves the global unread count", async () => {
  const report = knowledgeReport();
  vi.mocked(request)
    .mockResolvedValueOnce({
      items: Array.from({ length: 200 }, (_, i) => ({
        ...report,
        id: `report-${i}`,
      })),
      total: 201,
      unread: 137,
    })
    .mockResolvedValueOnce({
      items: [{ ...report, id: "report-200" }],
      total: 201,
    });
  const result = await knowledgeApi.reports();
  expect(request).toHaveBeenNthCalledWith(
    1,
    "GET",
    "/api/v1/knowledge/reports?limit=200&offset=0",
  );
  expect(request).toHaveBeenNthCalledWith(
    2,
    "GET",
    "/api/v1/knowledge/reports?limit=200&offset=200",
  );
  expect(result.items).toHaveLength(201);
  expect(result.unread).toBe(137);
});
test("existing-overview collection sends the immutable selected source and idempotency key", async () => {
  vi.mocked(request).mockResolvedValue(knowledgePapers()[0]);
  const body = {
    paper_id: "paper-A",
    source_kind: "model_parse" as const,
    source_id: "parse-A",
    overview_result_id: "overview-A",
  };
  await knowledgeApi.collect(body);
  expect(request).toHaveBeenCalledExactlyOnceWith(
    "POST",
    "/api/v1/knowledge/papers/collect",
    body,
    expect.any(String),
  );
});
test("paper pagination keeps scope and archive filters independent from model submission", async () => {
  vi.mocked(request).mockResolvedValue({ items: [], total: 0 });
  await knowledgeApi.papers({
    project_id: "project-1",
    collection_id: "collection-1",
    search: "合成",
    include_archived: true,
    offset: 50,
    limit: 200,
  });
  expect(request).toHaveBeenCalledExactlyOnceWith(
    "GET",
    expect.stringContaining("include_archived=true&offset=50&limit=200"),
  );
});

test("unlimited budgets are sent as explicit nulls with the cumulative limit intact", async () => {
  const settings = {
    ...knowledgeSettings,
    max_input_tokens: null,
    max_output_tokens: null,
    max_requests_per_run: null,
  };
  await knowledgeApi.saveSettings(settings);
  expect(request).toHaveBeenCalledExactlyOnceWith(
    "PATCH",
    "/api/v1/knowledge/library",
    settings,
    expect.any(String),
  );
});
