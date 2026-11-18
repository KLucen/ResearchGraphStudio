import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { ModelDocumentPanel } from "./ModelDocumentPanel";
import { api } from "./api";

vi.mock("./api", () => ({
  api: {
    modelDocumentParse: vi.fn(),
    modelDocumentOutputs: vi.fn(),
    updateModelDocumentSegment: vi.fn(),
    updateModelDocumentOutput: vi.fn(),
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

function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ModelDocumentPanel
        sessionId="session-1"
        connected
        activeView="materials"
        sessionStatus="succeeded"
        sessionError={null}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
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
  vi.mocked(api.updateModelDocumentSegment).mockResolvedValue(segment);
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
