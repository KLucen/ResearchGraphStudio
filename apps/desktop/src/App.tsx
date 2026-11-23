import { useEffect, useRef, useState } from "react";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Archive,
  ArrowDown,
  ArrowRight,
  ClipboardList,
  CircleDot,
  FolderOpen,
  Layers3,
  Library,
  LoaderCircle,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  Upload,
  X,
} from "lucide-react";
import { api, type Health, type Project } from "./api";
import { ModelSettings } from "./ModelSettings";
import { WindowCloseSettings } from "./WindowCloseSettings";
import { AppearanceSettings } from "./AppearanceSettings";
import { WorkspaceBackupSettings } from "./WorkspaceBackupSettings";
import { bindAppearance } from "./appearance";
import { PaperImport, Papers } from "./Papers";
import { JobHistory } from "./JobHistory";
import { LiteUsageSummary } from "./LiteUsageSummary";
import { ResearchKnowledgeBase } from "./ResearchKnowledgeBase";
import { ArchiveWorkspace } from "./ArchiveWorkspace";
import { knowledgeApi } from "./knowledgeApi";
import { useContextMenu } from "./ContextMenu";
import { ProjectSidebar } from "./ProjectSidebar";
import { WorkspaceSearchDialog } from "./WorkspaceSearchDialog";
import { handleWorkspaceFind } from "./workspaceSearchShortcut";

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
function date(value: string): string {
  return new Date(value).toLocaleDateString("zh-CN");
}

function workerWarning(health: Health | undefined): string | null {
  if (health?.worker_status === "recovering") {
    return health.worker_error === "DATABASE_BUSY"
      ? "本机数据库繁忙，任务队列正在恢复。"
      : "任务队列正在恢复，请稍候。";
  }
  if (health?.worker_status === "stopped") {
    return "任务队列已停止。请在设置与诊断中重新连接引擎。";
  }
  return null;
}

export default function App() {
  useEffect(bindAppearance, []);
  const [collapsed, setCollapsed] = useState(() => {
    try {
      const stored = localStorage.getItem("rgs.sidebar.collapsed");
      if (stored === "true" || stored === "false") return stored === "true";
    } catch {
      // Keep the workbench available without stored preferences.
    }
    return window.matchMedia?.("(max-width: 760px)").matches ?? false;
  });
  const sidebarToggle = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const media = window.matchMedia?.("(max-width: 760px)");
    if (!media) return;
    const compactOnResize = (event: MediaQueryListEvent) => {
      if (event.matches) {
        setCollapsed(true);
        const toggle = sidebarToggle.current;
        if (toggle?.closest(".sidebar")?.contains(document.activeElement))
          toggle.focus();
      }
    };
    media.addEventListener?.("change", compactOnResize);
    return () => media.removeEventListener?.("change", compactOnResize);
  }, []);
  function setSidebarCollapsed(next: boolean) {
    setCollapsed(next);
    try {
      localStorage.setItem("rgs.sidebar.collapsed", String(next));
    } catch {
      // In-memory sidebar state is still usable.
    }
    if (next) sidebarToggle.current?.focus();
  }
  function closeNarrowSidebar() {
    if (window.matchMedia?.("(max-width: 760px)").matches)
      setSidebarCollapsed(true);
  }
  const [page, setPage] = useState<
    "projects" | "knowledge" | "tasks" | "archive" | "settings"
  >("projects");
  const [creating, setCreating] = useState(false);
  const [importProjectId, setImportProjectId] = useState<string | null>(null);
  const importDialogRef = useRef<HTMLDialogElement>(null);
  const [selected, setSelected] = useState<Project | null>(null);
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);
  const [workspaceSearchOpen, setWorkspaceSearchOpen] = useState(false);
  useEffect(() => {
    if (page === "knowledge") return;
    const onKey = (event: KeyboardEvent) => {
      handleWorkspaceFind(event, () => setWorkspaceSearchOpen(true));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [page]);
  const client = useQueryClient();
  const knowledgeNavigation = useRef(0);
  useEffect(
    () => () => {
      knowledgeNavigation.current += 1;
    },
    [page],
  );
  useEffect(() => {
    const dialog = importDialogRef.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, [importProjectId]);
  const host = useQuery({
    queryKey: ["host"],
    queryFn: api.host,
    refetchInterval: 3000,
  });
  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 5000,
  });
  const projects = useInfiniteQuery({
    queryKey: ["projects"],
    queryFn: ({ pageParam }) => api.projects(pageParam),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: health.isSuccess,
  });
  const allProjects = projects.data?.pages.flatMap((p) => p.items) ?? [];
  const sidebarProjects =
    selected && !allProjects.some((project) => project.id === selected.id)
      ? [...allProjects, selected]
      : allProjects;
  const connected = health.isSuccess && !health.isError;
  const globalJobs = useQuery({
    queryKey: ["jobs", "global"],
    queryFn: api.jobs,
    enabled: connected,
    refetchInterval: 3000,
  });
  const activeTaskCount = connected ? (health.data?.active_jobs ?? null) : null;
  const knowledgeReports = useQuery({
    queryKey: ["knowledge", "reports"],
    queryFn: knowledgeApi.reports,
    enabled:
      connected &&
      (page === "knowledge" ||
        !!globalJobs.data?.some((job) =>
          String(job.kind).startsWith("knowledge_"),
        )),
    refetchInterval: 5000,
  });
  const unreadKnowledgeReports =
    knowledgeReports.data?.unread ??
    knowledgeReports.data?.items.filter((report) => !report.read).length ??
    0;
  const paperJobSignature = (globalJobs.data ?? [])
    .filter((job) => job.kind === "pdf_import" || job.kind === "zotero_import")
    .map((job) => `${job.id}:${job.status}:${job.updated_at}`)
    .sort()
    .join("|");
  const lastPaperJobSignature = useRef("");
  useEffect(() => {
    if (
      !connected ||
      !globalJobs.data ||
      paperJobSignature === lastPaperJobSignature.current
    ) {
      return;
    }
    lastPaperJobSignature.current = paperJobSignature;
    // A paper row is published by the worker, after the import request returns.
    // Refresh both list projections whenever that durable job changes so the
    // sidebar and the project view observe the same committed state.
    void client.invalidateQueries({ queryKey: ["sidebar-papers"] });
    void client.invalidateQueries({ queryKey: ["papers"] });
  }, [client, connected, globalJobs.data, paperJobSignature]);
  const projectNames = Object.fromEntries(
    allProjects.map((project) => [project.id, project.name]),
  );
  const restart = useMutation({
    mutationFn: api.restart,
    onSuccess: () => void client.invalidateQueries(),
  });

  return (
    <div className={`app-shell${collapsed ? " sidebar-collapsed" : ""}`}>
      <aside
        className="sidebar"
        aria-label="工作空间侧边栏"
        onKeyDown={(event) => {
          if (event.key === "Escape" && !collapsed) {
            event.preventDefault();
            setSidebarCollapsed(true);
          }
        }}
      >
        <div className="workspace-heading">
          <div className="workspace-label">个人研究空间</div>
          <button
            type="button"
            className="sidebar-add"
            aria-label="搜索个人研究空间"
            aria-keyshortcuts="Control+F"
            title="搜索个人研究空间 (Ctrl+F)"
            onClick={() => setWorkspaceSearchOpen(true)}
          >
            <Search size={16} />
          </button>
          <button
            type="button"
            className="sidebar-add"
            aria-label="新建研究项目"
            title="新建研究项目"
            disabled={!connected}
            onClick={() => setCreating(true)}
          >
            <Plus size={15} />
          </button>
          <button
            ref={sidebarToggle}
            className="sidebar-toggle"
            aria-label={collapsed ? "展开侧边栏" : "折叠侧边栏"}
            title={collapsed ? "展开侧边栏" : "折叠侧边栏"}
            aria-expanded={!collapsed}
            onClick={() => setSidebarCollapsed(!collapsed)}
          >
            {collapsed ? (
              <PanelLeftOpen size={18} />
            ) : (
              <PanelLeftClose size={18} />
            )}
          </button>
        </div>
        <ProjectSidebar
          connected={connected}
          projects={sidebarProjects}
          selectedProjectId={selected?.id ?? null}
          selectedPaperId={selectedPaperId}
          onCreate={() => setCreating(true)}
          onImport={(projectId) => setImportProjectId(projectId)}
          onSelect={(project, paperId) => {
            setPage("projects");
            setSelected(project);
            setSelectedPaperId(paperId);
            closeNarrowSidebar();
          }}
        />
        <div className="sidebar-footer">
          <div className="sidebar-project-actions">
            <button
              type="button"
              className="sidebar-action"
              disabled={!connected || !selected}
              onClick={() => selected && setImportProjectId(selected.id)}
              title={
                selected ? `向${selected.name}导入论文` : "先选择一个研究项目"
              }
            >
              <Upload size={14} />
              <span>导入论文</span>
            </button>
          </div>
          <nav aria-label="主导航">
            <button
              aria-label="研究项目"
              title="研究项目"
              aria-current={page === "projects" ? "page" : undefined}
              className={page === "projects" ? "nav active" : "nav"}
              onClick={() => {
                setPage("projects");
                setSelected(null);
                setSelectedPaperId(null);
                closeNarrowSidebar();
              }}
            >
              <Layers3 size={18} />
              <span className="nav-label">研究项目</span>
              <span className="nav-count">{allProjects.length}</span>
            </button>
            <button
              aria-label="研究内容知识库"
              title="研究内容知识库"
              aria-current={page === "knowledge" ? "page" : undefined}
              className={page === "knowledge" ? "nav active" : "nav"}
              onClick={() => {
                setPage("knowledge");
                closeNarrowSidebar();
              }}
            >
              <Library size={18} />
              <span className="nav-label">研究内容知识库</span>
              {unreadKnowledgeReports > 0 && (
                <span
                  className="nav-count"
                  aria-label={`${unreadKnowledgeReports} 份未读联系汇报`}
                >
                  {unreadKnowledgeReports}
                </span>
              )}
            </button>
            <button
              aria-label="任务记录"
              title="任务记录"
              aria-current={page === "tasks" ? "page" : undefined}
              className={page === "tasks" ? "nav active" : "nav"}
              onClick={() => {
                setPage("tasks");
                closeNarrowSidebar();
              }}
            >
              <ClipboardList size={18} />
              <span className="nav-label">任务记录</span>
              {activeTaskCount !== null && activeTaskCount > 0 && (
                <span className="nav-count">{activeTaskCount}</span>
              )}
            </button>
            <button
              aria-label="归档管理"
              title="归档管理"
              aria-current={page === "archive" ? "page" : undefined}
              className={page === "archive" ? "nav active" : "nav"}
              onClick={() => {
                setPage("archive");
                closeNarrowSidebar();
              }}
            >
              <Archive size={18} />
              <span className="nav-label">归档管理</span>
            </button>
          </nav>
          <div className="sidebar-tools">
            <button
              aria-label="设置与诊断"
              title="设置与诊断"
              aria-current={page === "settings" ? "page" : undefined}
              className={page === "settings" ? "nav active" : "nav"}
              onClick={() => {
                setPage("settings");
                closeNarrowSidebar();
              }}
            >
              <Settings2 size={18} />
              <span className="nav-label">设置与诊断</span>
            </button>
            <div
              className="connection"
              title={connected ? "本地引擎已连接" : "本地引擎未连接"}
            >
              <i className={connected ? "online" : ""} />
              <span>
                {connected
                  ? "本地引擎已连接"
                  : health.isPending
                    ? "正在连接本地引擎"
                    : "引擎未连接"}
              </span>
            </div>
          </div>
        </div>
      </aside>
      {!collapsed && (
        <button
          className="sidebar-scrim"
          aria-label="收起侧边栏"
          onClick={() => setSidebarCollapsed(true)}
          tabIndex={-1}
        />
      )}
      <main>
        <header className="topbar">
          <span>
            工作空间 <span className="slash">/</span>{" "}
            {page === "settings"
              ? "设置与诊断"
              : page === "tasks"
                ? "任务记录"
                : page === "archive"
                  ? "归档管理"
                  : page === "knowledge"
                    ? "研究内容知识库"
                    : selected
                      ? selected.name
                      : "研究项目"}
          </span>
          <span className="local-tag">
            <CircleDot size={13} /> LOCAL WORKSPACE
          </span>
        </header>
        <div
          className={`content${selected && page === "projects" ? " project-content" : ""}`}
        >
          {health.isError && (
            <div role="alert" className="error-banner">
              <strong>本地引擎未连接</strong>
              <p>{host.data?.error || message(health.error)}</p>
              <button
                className="button secondary"
                onClick={() => setPage("settings")}
              >
                打开连接诊断 <ArrowRight size={15} />
              </button>
            </div>
          )}
          {page === "settings" ? (
            <Settings
              connected={connected}
              directory={host.data?.data_dir}
              health={health.data}
              restart={restart}
            />
          ) : page === "tasks" ? (
            <TaskCenter
              connected={connected}
              projects={projectNames}
              activeCount={activeTaskCount}
              warning={workerWarning(health.data)}
            />
          ) : page === "archive" ? (
            <ArchiveWorkspace
              connected={connected}
              projectNames={projectNames}
            />
          ) : page === "knowledge" ? (
            <ResearchKnowledgeBase
              connected={connected}
              projects={allProjects}
              onOpenTasks={() => setPage("tasks")}
              onOpenPaper={async (projectId, paperId) => {
                const navigation = ++knowledgeNavigation.current;
                const project =
                  allProjects.find((item) => item.id === projectId) ??
                  (await client.fetchQuery<Project>({
                    queryKey: ["project", projectId],
                    queryFn: () => api.project(projectId),
                  }));
                if (navigation !== knowledgeNavigation.current) return;
                setSelected(project);
                setSelectedPaperId(paperId);
                setPage("projects");
                closeNarrowSidebar();
              }}
            />
          ) : selected ? (
            <section>
              <Papers
                key={`${selected.id}:${selectedPaperId ?? "none"}`}
                projectId={selected.id}
                projectName={selected.name}
                connected={connected}
                initialPaperId={selectedPaperId}
                onOpenTasks={() => setPage("tasks")}
                onPaperDeleted={() => setSelectedPaperId(null)}
              />
            </section>
          ) : (
            <Projects
              connected={connected}
              projects={projects}
              items={allProjects}
              onSearch={() => setWorkspaceSearchOpen(true)}
              onSelect={setSelected}
              onImport={setImportProjectId}
              onCreate={() => setCreating(true)}
            />
          )}
        </div>
      </main>
      {workspaceSearchOpen && (
        <WorkspaceSearchDialog
          connected={connected}
          onClose={() => setWorkspaceSearchOpen(false)}
          onOpen={(hit) => {
            setWorkspaceSearchOpen(false);
            setPage("projects");
            setSelected(hit.project);
            setSelectedPaperId(hit.kind === "paper" ? hit.id : null);
            closeNarrowSidebar();
          }}
        />
      )}
      {creating && (
        <CreateProject
          connected={connected}
          onClose={() => setCreating(false)}
          onCreated={(project) => {
            setCreating(false);
            void client.invalidateQueries({ queryKey: ["projects"] });
            setPage("projects");
            setSelected(project);
            setSelectedPaperId(null);
            closeNarrowSidebar();
          }}
        />
      )}
      {importProjectId && (
        <dialog
          ref={importDialogRef}
          className="dialog import-dialog"
          aria-labelledby="import-paper-title"
          onCancel={(event) => {
            event.preventDefault();
            setImportProjectId(null);
          }}
        >
          <div className="dialog-header">
            <div className="eyebrow">ADD TO PROJECT</div>
            <button
              type="button"
              className="icon-button"
              aria-label="关闭导入论文"
              onClick={() => setImportProjectId(null)}
            >
              <X size={20} />
            </button>
          </div>
          <h2 id="import-paper-title">导入论文</h2>
          <p className="lead">
            论文会出现在左侧项目文件夹中；解析和索引默认只在本机执行。
          </p>
          <PaperImport projectId={importProjectId} connected={connected} />
        </dialog>
      )}
    </div>
  );
}

function TaskCenter({
  connected,
  projects,
  activeCount,
  warning,
}: {
  connected: boolean;
  projects: Record<string, string>;
  activeCount: number | null;
  warning: string | null;
}) {
  return (
    <>
      <div className="heading-row">
        <div>
          <div className="eyebrow">WORKSPACE ACTIVITY</div>
          <h1>任务记录</h1>
          <p className="lead">
            查看所有研究项目的导入、解析、索引和按需生成任务。
          </p>
        </div>
        <span className="task-status-pill">
          {activeCount === null
            ? "任务状态暂不可用"
            : activeCount > 0
              ? `${activeCount} 项正在处理`
              : "当前没有进行中的任务"}
        </span>
      </div>
      {warning && (
        <p role="status" className="error-text">
          {warning}
        </p>
      )}
      <section className="settings-card task-center-card">
        <JobHistory
          connected={connected}
          projectNames={projects}
          title="全部项目任务"
        />
      </section>
    </>
  );
}

function Projects({
  connected,
  projects,
  items,
  onSearch,
  onSelect,
  onImport,
  onCreate,
}: {
  connected: boolean;
  projects: {
    isError: boolean;
    error: Error | null;
    isPending: boolean;
    refetch: () => Promise<unknown>;
    hasNextPage?: boolean;
    isFetchingNextPage: boolean;
    fetchNextPage: () => Promise<unknown>;
  };
  items: Project[];
  onSearch: () => void;
  onSelect: (project: Project) => void;
  onImport: (projectId: string) => void;
  onCreate: () => void;
}) {
  const { contextMenuProps, contextMenu } = useContextMenu();
  return (
    <>
      <div className="heading-row">
        <div>
          <h1>研究项目</h1>
          <p className="lead">用最少的步骤读懂一篇论文。</p>
        </div>
        <button
          className="button primary"
          disabled={!connected}
          onClick={onCreate}
        >
          <Plus size={18} /> 新建研究项目
        </button>
      </div>
      <div className="section-toolbar">
        <h2>
          我的项目 <span>{items.length}</span>
        </h2>
        <button type="button" className="button secondary" onClick={onSearch}>
          <Search size={16} /> 搜索项目与论文
        </button>
      </div>
      {projects.isError ? (
        <div role="alert" className="error-banner">
          {message(projects.error)}
          <button
            className="text-button"
            onClick={() => void projects.refetch()}
          >
            重试加载
          </button>
        </div>
      ) : projects.isPending ? (
        <div className="empty">
          <LoaderCircle className="spin" />
          <p>{connected ? "正在读取项目…" : "等待本地引擎就绪…"}</p>
        </div>
      ) : items.length ? (
        <div className="project-grid">
          {items.map((p) => (
            <button
              className="project-card"
              key={p.id}
              {...contextMenuProps("研究项目操作", [
                { label: "打开项目", action: () => onSelect(p) },
                {
                  label: "导入论文",
                  disabled: !connected,
                  action: () => onImport(p.id),
                },
              ])}
              onClick={() => onSelect(p)}
            >
              <div className="card-top">
                <FolderOpen size={22} />
                <ArrowRight size={16} />
              </div>
              <h3>{p.name}</h3>
              {p.description && <p>{p.description}</p>}
              <footer>
                <i />
                本地 Lite 项目<span>{date(p.created_at)}</span>
              </footer>
            </button>
          ))}
        </div>
      ) : (
        <div className="empty">
          <div className="empty-art">
            <FolderOpen size={34} />
            <span>
              <Plus size={12} />
            </span>
          </div>
          <h3>你的第一个研究项目</h3>
          <button
            className="button secondary"
            disabled={!connected}
            onClick={onCreate}
          >
            创建项目 <ArrowRight size={16} />
          </button>
        </div>
      )}
      {projects.hasNextPage && (
        <button
          className="button secondary load-more"
          disabled={projects.isFetchingNextPage}
          onClick={() => void projects.fetchNextPage()}
        >
          <ArrowDown size={16} /> 加载更多
        </button>
      )}
      {contextMenu}
    </>
  );
}

function CreateProject({
  connected,
  onClose,
  onCreated,
}: {
  connected: boolean;
  onClose: () => void;
  onCreated: (project: Project) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const dialogRef = useRef<HTMLDialogElement>(null);
  const key = useRef(crypto.randomUUID());
  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);
  const mutation = useMutation({
    mutationFn: () =>
      api.createProject({ name: name.trim(), description }, key.current),
    onSuccess: onCreated,
  });
  return (
    <dialog
      ref={dialogRef}
      className="dialog"
      aria-labelledby="create-project-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <div className="dialog-header">
          <div className="eyebrow">NEW LITE PROJECT</div>
          <button
            type="button"
            className="icon-button"
            aria-label="关闭新建项目"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        <h2 id="create-project-title">新建研究项目</h2>
        <p className="lead">给研究一个名字，留下清晰的问题线索。</p>
        <label className="field">
          项目名称
          <input
            autoFocus
            required
            maxLength={120}
            value={name}
            disabled={!connected || mutation.isPending}
            onChange={(e) => {
              setName(e.target.value);
              key.current = crypto.randomUUID();
            }}
          />
        </label>
        <label className="field">
          研究问题 <span>选填</span>
          <textarea
            maxLength={4000}
            rows={4}
            value={description}
            disabled={!connected || mutation.isPending}
            onChange={(e) => {
              setDescription(e.target.value);
              key.current = crypto.randomUUID();
            }}
          />
        </label>
        {mutation.isError && (
          <p role="alert" className="error-text">
            {message(mutation.error)}
          </p>
        )}
        <div className="dialog-actions">
          <button type="button" className="button secondary" onClick={onClose}>
            取消
          </button>
          <button
            className="button primary"
            disabled={!connected || !name.trim() || mutation.isPending}
          >
            {mutation.isPending ? "正在保存…" : "创建 Lite 项目"}
            <ArrowRight size={16} />
          </button>
        </div>
      </form>
    </dialog>
  );
}

function Settings({
  connected,
  directory,
  health,
  restart,
}: {
  connected: boolean;
  directory?: string;
  health?: Awaited<ReturnType<typeof api.health>>;
  restart: ReturnType<
    typeof useMutation<Awaited<ReturnType<typeof api.restart>>, Error, void>
  >;
}) {
  const client = useQueryClient();
  const diagnose = useMutation({
    mutationFn: () => api.diagnose(crypto.randomUUID()),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["jobs"] }),
  });
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: api.jobs,
    enabled: connected,
    refetchInterval: 3000,
  });
  return (
    <>
      <div className="eyebrow">LOCAL ENVIRONMENT</div>
      <h1>设置与诊断</h1>
      <p className="lead">管理本地数据、模型配置和连接状态。</p>
      <AppearanceSettings />
      <WorkspaceBackupSettings />
      <section className="settings-card">
        <div className="settings-title">
          <h2>本地引擎</h2>
          <span className="pill">{connected ? "已连接" : "未连接"}</span>
        </div>
        <dl>
          <dt>引擎版本</dt>
          <dd>{health?.version ?? "等待连接"}</dd>
          <dt>数据库版本</dt>
          <dd>{health?.schema_version ?? "等待检查"}</dd>
          {health?.worker_status && (
            <>
              <dt>任务队列</dt>
              <dd>
                {
                  {
                    idle: "待命",
                    running: "执行任务中",
                    recovering: "正在恢复",
                    stopped: "已停止",
                    disabled: "已停用",
                  }[health.worker_status]
                }
              </dd>
            </>
          )}
          <dt>全文检索</dt>
          <dd>{health?.fts5 ? "FTS5 可用" : "等待检查"}</dd>
          <dt>项目数据位置</dt>
          <dd className="mono">{directory ?? "等待宿主信息"}</dd>
        </dl>
        {workerWarning(health) && (
          <p role="status" className="error-text">
            {workerWarning(health)}
          </p>
        )}
        <button
          className="button secondary"
          disabled={restart.isPending}
          onClick={() => restart.mutate()}
        >
          <RefreshCw size={15} />
          {restart.isPending ? "正在重连…" : "重新连接引擎"}
        </button>
        {restart.isError && (
          <p role="alert" className="error-text">
            {message(restart.error)}
          </p>
        )}
      </section>
      <LiteUsageSummary connected={connected} />
      <WindowCloseSettings />
      <ModelSettings connected={connected} />
      <section className="settings-card">
        <div className="settings-title">
          <h2>存储诊断</h2>
          <button
            className="button primary"
            disabled={!connected || diagnose.isPending}
            onClick={() => diagnose.mutate()}
          >
            运行检查
          </button>
        </div>
        <p>检查 SQLite 完整性、外键和全文检索，不读取论文正文。</p>
        {(diagnose.isError || jobs.isError) && (
          <p role="alert" className="error-text">
            {message(diagnose.error || jobs.error)}
          </p>
        )}
        {jobs.data
          ?.filter((job) => job.kind === "diagnostics")
          .map((job) => (
            <div className="job" key={job.id}>
              <strong>
                {job.status === "succeeded"
                  ? "存储诊断通过"
                  : `存储诊断 · ${job.status}`}
              </strong>
              <small>
                {date(job.created_at)} · 第 {job.attempt} 次执行
              </small>
              {job.error && <p className="error-text">{job.error}</p>}
            </div>
          ))}
      </section>
    </>
  );
}
