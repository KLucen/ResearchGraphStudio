import { useEffect, useRef, useState } from "react";
import {
  useInfiniteQuery,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowRight,
  ClipboardList,
  CircleDot,
  FileText,
  FolderOpen,
  Layers3,
  LoaderCircle,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Upload,
  X,
} from "lucide-react";
import { api, type Project } from "./api";
import { ModelSettings } from "./ModelSettings";
import { PaperImport, Papers } from "./Papers";
import { JobHistory } from "./JobHistory";
import { LiteUsageSummary } from "./LiteUsageSummary";

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
function date(value: string): string {
  return new Date(value).toLocaleDateString("zh-CN");
}

export default function App() {
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem("rgs.sidebar.collapsed") === "true",
  );
  const [page, setPage] = useState<"projects" | "tasks" | "settings">(
    "projects",
  );
  const [creating, setCreating] = useState(false);
  const [importProjectId, setImportProjectId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Project | null>(null);
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const client = useQueryClient();
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
  const visible = allProjects.filter((p) =>
    `${p.name} ${p.description}`.toLowerCase().includes(search.toLowerCase()),
  );
  const connected = health.isSuccess && !health.isError;
  const globalJobs = useQuery({
    queryKey: ["jobs", "global"],
    queryFn: api.jobs,
    enabled: connected,
    refetchInterval: 3000,
  });
  const activeTaskCount =
    globalJobs.data?.filter((job) => ["queued", "running"].includes(job.status))
      .length ?? 0;
  const projectNames = Object.fromEntries(
    allProjects.map((project) => [project.id, project.name]),
  );
  const restart = useMutation({
    mutationFn: api.restart,
    onSuccess: () => void client.invalidateQueries(),
  });

  return (
    <div className={`app-shell${collapsed ? " sidebar-collapsed" : ""}`}>
      <aside className="sidebar">
        <button
          className="sidebar-toggle"
          aria-label={collapsed ? "展开侧边栏" : "折叠侧边栏"}
          title={collapsed ? "展开侧边栏" : "折叠侧边栏"}
          aria-expanded={!collapsed}
          onClick={() => {
            const next = !collapsed;
            setCollapsed(next);
            localStorage.setItem("rgs.sidebar.collapsed", String(next));
          }}
        >
          {collapsed ? (
            <PanelLeftOpen size={19} />
          ) : (
            <PanelLeftClose size={19} />
          )}
        </button>
        <div className="brand">
          <div className="brand-symbol">
            <Network size={24} />
          </div>
          <div className="brand-title">
            ResearchGraph<span>LITE</span>
          </div>
        </div>
        <div className="workspace-heading">
          <div className="workspace-label">个人研究空间</div>
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
        </div>
        <ProjectSidebar
          connected={connected}
          projects={allProjects}
          selectedProjectId={selected?.id ?? null}
          selectedPaperId={selectedPaperId}
          onCreate={() => setCreating(true)}
          onImport={(projectId) => setImportProjectId(projectId)}
          onSelect={(project, paperId) => {
            setPage("projects");
            setSelected(project);
            setSelectedPaperId(paperId);
          }}
        />
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
          {!selected && <small>选择项目后导入 PDF 或 Zotero</small>}
        </div>
        <nav aria-label="主导航">
          <button
            aria-label="研究项目"
            title="研究项目"
            className={page === "projects" ? "nav active" : "nav"}
            onClick={() => {
              setPage("projects");
              setSelected(null);
              setSelectedPaperId(null);
            }}
          >
            <Layers3 size={18} />
            <span className="nav-label">研究项目</span>
            <span className="nav-count">{allProjects.length}</span>
          </button>
          <button
            aria-label="任务记录"
            title="任务记录"
            className={page === "tasks" ? "nav active" : "nav"}
            onClick={() => setPage("tasks")}
          >
            <ClipboardList size={18} />
            <span className="nav-label">任务记录</span>
            {activeTaskCount > 0 && (
              <span className="nav-count">{activeTaskCount}</span>
            )}
          </button>
        </nav>
        <div className="sidebar-spacer" />
        <div className="sidebar-note">
          <ShieldCheck size={20} />
          <strong>知识，留在本地</strong>
          <p>
            项目保存在这台电脑上。
            <br />
            默认本地处理，模型传输需确认。
          </p>
        </div>
        <div className="connection">
          <i className={connected ? "online" : ""} />
          <span>
            {connected
              ? "本地引擎已连接"
              : health.isPending
                ? "正在连接本地引擎"
                : "引擎未连接"}
          </span>
        </div>
        <button
          aria-label="设置与诊断"
          title="设置与诊断"
          className={page === "settings" ? "nav active" : "nav"}
          onClick={() => setPage("settings")}
        >
          <Settings2 size={18} />
          <span className="nav-label">设置与诊断</span>
        </button>
        <div className="version">
          LITE <span>0.1.0</span>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <span>
            工作空间 <span className="slash">/</span>{" "}
            {page === "settings"
              ? "设置与诊断"
              : page === "tasks"
                ? "任务记录"
                : selected
                  ? selected.name
                  : "研究项目"}
          </span>
          <span className="local-tag">
            <CircleDot size={13} /> LOCAL WORKSPACE
          </span>
        </header>
        <div
          className={`content${selected && page !== "settings" ? " project-content" : ""}`}
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
              />
            </section>
          ) : (
            <Projects
              connected={connected}
              projects={projects}
              visible={visible}
              search={search}
              setSearch={setSearch}
              onSelect={setSelected}
              onCreate={() => setCreating(true)}
            />
          )}
        </div>
      </main>
      {creating && (
        <CreateProject
          connected={connected}
          onClose={() => setCreating(false)}
          onCreated={(project) => {
            setCreating(false);
            void client.invalidateQueries({ queryKey: ["projects"] });
            setSelected(project);
          }}
        />
      )}
      {importProjectId && (
        <dialog
          className="dialog import-dialog"
          open
          aria-labelledby="import-paper-title"
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

function ProjectSidebar({
  connected,
  projects,
  selectedProjectId,
  selectedPaperId,
  onCreate,
  onImport,
  onSelect,
}: {
  connected: boolean;
  projects: Project[];
  selectedProjectId: string | null;
  selectedPaperId: string | null;
  onCreate: () => void;
  onImport: (projectId: string) => void;
  onSelect: (project: Project, paperId: string | null) => void;
}) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    try {
      return JSON.parse(localStorage.getItem("rgs.sidebar.projects") ?? "{}");
    } catch {
      return {};
    }
  });
  const paperQueries = useQueries({
    queries: projects.map((project) => ({
      queryKey: ["sidebar-papers", project.id],
      queryFn: () => api.papers(project.id),
      enabled: connected,
      staleTime: 30_000,
    })),
  });

  useEffect(() => {
    localStorage.setItem("rgs.sidebar.projects", JSON.stringify(expanded));
  }, [expanded]);

  return (
    <div className="project-tree" aria-label="个人研究项目">
      {projects.length === 0 ? (
        <button
          type="button"
          className="project-tree-empty"
          disabled={!connected}
          onClick={onCreate}
        >
          <Plus size={14} />
          新建研究项目
        </button>
      ) : (
        projects.map((project, index) => {
          const query = paperQueries[index];
          const papers = query.data?.items ?? [];
          const isOpen = expanded[project.id] ?? index === 0;
          const isSelected = selectedProjectId === project.id;
          return (
            <div className="project-tree-group" key={project.id}>
              <div
                className={
                  isSelected ? "project-tree-row selected" : "project-tree-row"
                }
              >
                <button
                  type="button"
                  className="project-tree-toggle"
                  aria-label={
                    isOpen ? `收起${project.name}` : `展开${project.name}`
                  }
                  aria-expanded={isOpen}
                  onClick={() =>
                    setExpanded((current) => ({
                      ...current,
                      [project.id]: !isOpen,
                    }))
                  }
                >
                  {isOpen ? <ArrowDown size={13} /> : <ArrowRight size={13} />}
                </button>
                <button
                  type="button"
                  className="project-tree-project"
                  title={project.name}
                  onClick={() => onSelect(project, null)}
                >
                  <FolderOpen size={14} />
                  <span>{project.name}</span>
                </button>
                {selectedProjectId === project.id && (
                  <button
                    type="button"
                    className="project-tree-import"
                    aria-label={`向${project.name}导入论文`}
                    title={`向${project.name}导入论文`}
                    onClick={() => onImport(project.id)}
                  >
                    <Upload size={12} />
                  </button>
                )}
                <span className="project-tree-count">{papers.length}</span>
              </div>
              {isOpen && (
                <div className="project-tree-papers">
                  {query.isPending && (
                    <span className="project-tree-muted">读取论文…</span>
                  )}
                  {!query.isPending && !papers.length && (
                    <span className="project-tree-muted">暂无论文</span>
                  )}
                  {papers.map((paper) => (
                    <button
                      type="button"
                      className={
                        selectedProjectId === project.id &&
                        selectedPaperId === paper.id
                          ? "project-tree-paper selected"
                          : "project-tree-paper"
                      }
                      key={paper.id}
                      title={paper.title}
                      onClick={() => onSelect(project, paper.id)}
                    >
                      <FileText size={13} />
                      <span>{paper.title}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}

function TaskCenter({
  connected,
  projects,
  activeCount,
}: {
  connected: boolean;
  projects: Record<string, string>;
  activeCount: number;
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
          {activeCount ? `${activeCount} 项正在处理` : "当前没有进行中的任务"}
        </span>
      </div>
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
  visible,
  search,
  setSearch,
  onSelect,
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
  visible: Project[];
  search: string;
  setSearch: (value: string) => void;
  onSelect: (project: Project) => void;
  onCreate: () => void;
}) {
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
          我的项目 <span>{visible.length}</span>
        </h2>
        <label className="search">
          <Search size={16} />
          <input
            aria-label="搜索已加载的项目"
            placeholder="搜索已加载的项目"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
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
      ) : visible.length ? (
        <div className="project-grid">
          {visible.map((p) => (
            <button
              className="project-card"
              key={p.id}
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
          <h3>{search ? "没有找到匹配的项目" : "你的第一个研究项目"}</h3>
          {!search && (
            <button
              className="button secondary"
              disabled={!connected}
              onClick={onCreate}
            >
              创建项目 <ArrowRight size={16} />
            </button>
          )}
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
  const key = useRef(crypto.randomUUID());
  const mutation = useMutation({
    mutationFn: () =>
      api.createProject({ name: name.trim(), description }, key.current),
    onSuccess: onCreated,
  });
  return (
    <dialog className="dialog" open aria-labelledby="create-project-title">
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
          <dt>全文检索</dt>
          <dd>{health?.fts5 ? "FTS5 可用" : "等待检查"}</dd>
          <dt>项目数据位置</dt>
          <dd className="mono">{directory ?? "等待宿主信息"}</dd>
        </dl>
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
