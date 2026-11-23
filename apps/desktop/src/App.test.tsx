import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { api } from "./api";
import { knowledgeApi } from "./knowledgeApi";
import { sidebarPapers, sidebarProjects } from "./sidebarFixtures";

vi.mock("./api", () => ({
  request: vi.fn(),
  api: Object.fromEntries(
    [
      "host",
      "health",
      "projects",
      "project",
      "papers",
      "jobs",
      "jobsPage",
      "restart",
      "createProject",
      "diagnose",
    ].map((key) => [key, vi.fn()]),
  ),
}));
vi.mock("./knowledgeApi", () => ({ knowledgeApi: { reports: vi.fn() } }));
vi.mock("./Papers", () => ({
  Papers: ({
    projectId,
    initialPaperId,
  }: {
    projectId: string;
    initialPaperId?: string;
  }) => (
    <p>
      已选择：{projectId} / {initialPaperId ?? "项目"}
    </p>
  ),
  PaperImport: ({ projectId }: { projectId: string }) => (
    <p>导入目标：{projectId}</p>
  ),
}));
vi.mock("./ModelSettings", () => ({
  ModelSettings: () => <div>模型设置</div>,
}));
vi.mock("./ResearchKnowledgeBase", () => ({
  ResearchKnowledgeBase: ({
    onOpenPaper,
  }: {
    onOpenPaper: (projectId: string, paperId: string) => Promise<void>;
  }) => (
    <div>
      知识库工作区
      <button
        onClick={() => void onOpenPaper("unloaded-project", "linked-paper")}
      >
        返回来源论文
      </button>
    </div>
  ),
}));
vi.mock("./LiteUsageSummary", () => ({ LiteUsageSummary: () => null }));

let projects = [...sidebarProjects];
beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  projects = [...sidebarProjects];
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: false })),
  );
  vi.mocked(api.host).mockResolvedValue({
    running: true,
    data_dir: "synthetic-data",
    error: null,
  });
  vi.mocked(api.health).mockResolvedValue({
    status: "ok",
    active_jobs: 0,
  } as never);
  vi.mocked(api.projects).mockImplementation(async () => ({
    items: projects,
    next_cursor: null,
  }));
  vi.mocked(api.papers).mockImplementation(async (id) => ({
    items: sidebarPapers(id),
    next_cursor: null,
  }));
  vi.mocked(api.jobs).mockResolvedValue([]);
  vi.mocked(api.jobsPage).mockResolvedValue({ items: [], next_cursor: null });
  vi.mocked(knowledgeApi.reports).mockResolvedValue({ items: [], total: 0 });
});

function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
}

test("sidebar uses the total and loads the older paper page", async () => {
  const user = userEvent.setup();
  const project = sidebarProjects[0];
  const papers = Array.from({ length: 51 }, (_, index) => ({
    id: `synthetic-${index + 1}`,
    title: `合成论文 ${index + 1}`,
    project_id: project.id,
    created_at: "2026-11-20",
  }));
  vi.mocked(api.papers).mockImplementation(async (id, cursor = 0) =>
    id === project.id
      ? {
          items: papers.slice(cursor, cursor + 50),
          total: 51,
          next_cursor: cursor === 0 ? 50 : null,
        }
      : { items: [], total: 0, next_cursor: null },
  );
  mount();
  const tree = screen.getByRole("region", { name: "个人研究项目" });
  expect(await within(tree).findByText("51")).toBeVisible();
  expect(
    within(tree).queryByRole("button", { name: "合成论文 51" }),
  ).toBeNull();
  await user.click(
    within(tree).getByRole("button", { name: `加载${project.name}的更多论文` }),
  );
  const older = await within(tree).findByRole("button", {
    name: "合成论文 51",
  });
  await user.click(older);
  expect(
    screen.getByText(`已选择：${project.id} / synthetic-51`),
  ).toBeVisible();
  expect(api.papers).toHaveBeenCalledWith(project.id, 50);
});

test("knowledge sources can open a project outside the loaded project page", async () => {
  const user = userEvent.setup();
  vi.mocked(api.project).mockResolvedValue({
    ...sidebarProjects[0],
    id: "unloaded-project",
    name: "较早的研究项目",
  });
  mount();
  await user.click(screen.getByRole("button", { name: "研究内容知识库" }));
  await user.click(screen.getByRole("button", { name: "返回来源论文" }));
  expect(
    await screen.findByText("已选择：unloaded-project / linked-paper"),
  ).toBeVisible();
  expect(api.project).toHaveBeenCalledWith("unloaded-project");
});

test("workspace task history pages independently of the live active count", async () => {
  const user = userEvent.setup();
  vi.mocked(api.health).mockResolvedValue({
    status: "ok",
    active_jobs: 1,
    worker_status: "recovering",
    worker_error: "DATABASE_BUSY",
  } as never);
  const job = {
    id: "recent",
    kind: "diagnostics",
    project_id: null,
    attempt: 1,
    stage: null,
    result: null,
    error: null,
    created_at: "2026-11-20",
    updated_at: "2026-11-20",
  };
  vi.mocked(api.jobsPage).mockImplementation(async (cursor) =>
    cursor === "older-page"
      ? {
          items: [{ ...job, id: "older", status: "running" }],
          next_cursor: null,
        }
      : { items: [{ ...job, status: "succeeded" }], next_cursor: "older-page" },
  );
  mount();
  await user.click(screen.getByRole("button", { name: "任务记录" }));
  expect(await screen.findByText("1 项正在处理")).toBeVisible();
  expect(screen.getByText("本机数据库繁忙，任务队列正在恢复。")).toBeVisible();
  await user.click(await screen.findByRole("button", { name: "加载更早任务" }));
  await waitFor(() => expect(screen.getAllByRole("article")).toHaveLength(2));
  expect(screen.getAllByRole("article").at(-1)).toHaveTextContent("正在处理");
  expect(api.jobsPage).toHaveBeenCalledWith("older-page");
});

test("storage access errors leave the application and sidebar reachable", async () => {
  const user = userEvent.setup();
  const descriptor = Object.getOwnPropertyDescriptor(window, "localStorage")!;
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    get: () => {
      throw new DOMException("blocked", "SecurityError");
    },
  });
  try {
    mount();
    await screen.findByRole("button", { name: "合成研究项目 1" });
    await user.click(screen.getByRole("button", { name: "折叠侧边栏" }));
    expect(screen.getByRole("button", { name: "展开侧边栏" })).toBeVisible();
  } finally {
    Object.defineProperty(window, "localStorage", descriptor);
  }
});

test("sidebar keeps only the workspace header and preserves navigation and collapse preferences", async () => {
  const user = userEvent.setup();
  mount();
  const sidebar = screen.getByRole("complementary", { name: "工作空间侧边栏" });
  expect(within(sidebar).getByText("个人研究空间")).toBeVisible();
  expect(
    within(sidebar).queryByText(/ResearchGraph|知识，留在本地|LITE|0\.1\.0/),
  ).toBeNull();
  await screen.findByRole("button", { name: "合成研究项目 1" });
  await user.click(within(sidebar).getByRole("button", { name: "任务记录" }));
  expect(screen.getByRole("heading", { name: "任务记录" })).toBeVisible();
  expect(
    within(sidebar).getByRole("button", { name: "任务记录" }),
  ).toHaveAttribute("aria-current", "page");
  await user.click(
    within(sidebar).getByRole("button", { name: "研究内容知识库" }),
  );
  expect(screen.getByText("知识库工作区")).toBeVisible();
  await user.click(within(sidebar).getByRole("button", { name: "设置与诊断" }));
  expect(screen.getByRole("heading", { name: "设置与诊断" })).toBeVisible();
  const toggle = within(sidebar).getByRole("button", { name: "折叠侧边栏" });
  await user.click(toggle);
  expect(localStorage.getItem("rgs.sidebar.collapsed")).toBe("true");
  expect(
    within(sidebar).getByRole("button", { name: "展开侧边栏" }),
  ).toHaveFocus();
  await user.keyboard("{Enter}");
  expect(localStorage.getItem("rgs.sidebar.collapsed")).toBe("false");
  expect(
    within(sidebar).getByRole("button", { name: "折叠侧边栏" }),
  ).toHaveAttribute("aria-expanded", "true");
});

test("long paper titles remain keyboard selectable and project import and creation keep their targets", async () => {
  const user = userEvent.setup();
  mount();
  const tree = screen.getByRole("region", { name: "个人研究项目" });
  const paper = sidebarPapers(sidebarProjects[0].id).at(-1)!;
  const button = await within(tree).findByRole("button", { name: paper.title });
  button.focus();
  await user.keyboard("{Enter}");
  expect(button).toHaveAttribute("aria-current", "page");
  expect(
    screen.getByText(`已选择：${paper.project_id} / ${paper.id}`),
  ).toBeVisible();
  const sidebar = screen.getByRole("complementary", { name: "工作空间侧边栏" });
  await user.click(within(sidebar).getByRole("button", { name: "导入论文" }));
  expect(
    within(screen.getByRole("dialog", { name: "导入论文" })).getByText(
      `导入目标：${paper.project_id}`,
    ),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "关闭导入论文" }));
  vi.mocked(api.createProject).mockImplementation(async (body) => {
    const project = {
      ...sidebarProjects[0],
      ...body,
      id: "created-sidebar-project",
    };
    projects = [...projects, project];
    return project;
  });
  await user.click(
    within(sidebar).getByRole("button", { name: "新建研究项目" }),
  );
  await user.type(screen.getByLabelText("项目名称"), "新增合成项目");
  await user.click(screen.getByRole("button", { name: "创建 Lite 项目" }));
  await waitFor(() =>
    expect(api.createProject).toHaveBeenCalledWith(
      { name: "新增合成项目", description: "" },
      expect.any(String),
    ),
  );
  expect(
    await within(tree).findByRole("button", { name: "新增合成项目" }),
  ).toBeVisible();
  expect(
    screen.getByText("已选择：created-sidebar-project / 项目"),
  ).toBeVisible();
});

test("small-screen sidebar expands for the paper tree and closes after selection or Escape", async () => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: true })),
  );
  const user = userEvent.setup();
  mount();
  await user.click(screen.getByRole("button", { name: "展开侧边栏" }));
  const tree = screen.getByRole("region", { name: "个人研究项目" });
  await user.click(
    await within(tree).findByRole("button", {
      name: sidebarPapers(sidebarProjects[0].id)[0].title,
    }),
  );
  expect(screen.getByRole("button", { name: "展开侧边栏" })).toHaveFocus();
  await user.keyboard("{Enter}");
  expect(screen.getByRole("button", { name: "折叠侧边栏" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
  await user.keyboard("{Escape}");
  expect(screen.getByRole("button", { name: "展开侧边栏" })).toHaveFocus();
});
