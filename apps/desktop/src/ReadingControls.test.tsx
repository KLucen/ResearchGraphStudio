import { beforeEach, expect, test, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReadingControls } from "./ReadingControls";
import { api, request } from "./api";

vi.mock("./api", () => ({ request: vi.fn(), api: { paper: vi.fn() } }));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.paper).mockResolvedValue({ revisions: [{ id: "v" }] } as never);
  vi.mocked(request).mockImplementation(async (method, path) => {
    if (path.includes("/candidates?"))
      return {
        items: [
          {
            node: { id: "n", kind: "claim", text: "A preserved candidate" },
            graph_role: "retrieval_only",
            reason: "Background",
            source_valid: true,
          },
        ],
        next_cursor: null,
      };
    if (method === "GET")
      return {
        selection_revision: 1,
        document_version_id: "v",
        density: "standard",
        build_state: "partial",
      };
    return { status: "succeeded" };
  });
});
function mount() {
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
      <ReadingControls paperId="p" connected onSelect={() => {}} />
    </QueryClientProvider>,
  );
}

test("density rebuild uses saved candidates and optimistic revision", async () => {
  const user = userEvent.setup();
  mount();
  await user.click(screen.getByText(/结论选择与全部候选/));
  await screen.findByText("A preserved candidate");
  await user.selectOptions(screen.getByLabelText("图谱密度"), "concise");
  await user.click(
    screen.getByRole("button", { name: "基于已有候选更新图谱" }),
  );
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "POST",
      "/api/v1/papers/p/graph-selection/rebuild",
      {
        document_version_id: "v",
        density: "concise",
        expected_revision: 1,
        allow_network: false,
      },
      expect.any(String),
    ),
  );
  expect(
    vi
      .mocked(request)
      .mock.calls.some((c) => c[1].includes("knowledge/extract")),
  ).toBe(false);
});

test("unselected candidates can be searched and displayed without a review request", async () => {
  const user = userEvent.setup();
  mount();
  await user.click(screen.getByText(/结论选择与全部候选/));
  await screen.findByText("A preserved candidate");
  await user.type(screen.getByLabelText("搜索全部候选"), "preserved");
  await user.click(screen.getByRole("button", { name: "在主图显示" }));
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "POST",
      "/api/v1/papers/p/graph-selection/preferences",
      expect.objectContaining({
        candidate_id: "n",
        action: "include_core",
        expected_revision: 1,
      }),
      expect.any(String),
    ),
  );
  expect(
    vi.mocked(request).mock.calls.some((c) => c[1].includes("reviews")),
  ).toBe(false);
});

test.each([false, true])(
  "unfinished extraction exposes saved candidates and gates partial graph while active=%s",
  async (active) => {
    const original = vi.mocked(request).getMockImplementation()!;
    vi.mocked(request).mockImplementation(async (method, path, ...args) => {
      if (method === "GET" && path.endsWith("/graph-selection"))
        return {
          selection_revision: 0,
          document_version_id: "v",
          build_state: "not_built",
          build: {
            candidate_count: 206,
            extraction_incomplete: true,
            completed_batches: 6,
            total_batches: 12,
            active,
          },
        };
      return original(method, path, ...args);
    });
    mount();
    expect(await screen.findByText(/已保存 206 条/)).toBeVisible();
    expect(screen.getByText(/6\/12 批/)).toBeVisible();
    expect(await screen.findByText("A preserved candidate")).toBeVisible();
    const button = screen.getByRole("button", {
      name: "基于已保存候选生成部分图谱",
    });
    if (active) expect(button).toBeDisabled();
    else {
      await userEvent.click(screen.getByRole("checkbox"));
      await userEvent.click(button);
      await waitFor(() =>
        expect(request).toHaveBeenCalledWith(
          "POST",
          "/api/v1/papers/p/graph-selection/rebuild",
          expect.objectContaining({
            expected_revision: 0,
            allow_network: true,
          }),
          expect.any(String),
        ),
      );
    }
    expect(
      vi
        .mocked(request)
        .mock.calls.some((c) => c[1].includes("knowledge/extract")),
    ).toBe(false);
  },
);
