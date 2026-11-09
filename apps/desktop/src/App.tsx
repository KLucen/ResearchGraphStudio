import { useRef, useState } from "react";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowRight,
  CircleDot,
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
  X,
} from "lucide-react";
import { api, type Project } from "./api";
import { ModelSettings } from "./ModelSettings";
import { Papers } from "./Papers";

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
  const [page, setPage] = useState<"projects" | "settings">("projects");
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<Project | null>(null);
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
        <div className="workspace-label">个人研究空间</div>
        <nav aria-label="主导航">
          <button
            aria-label="研究项目"
            title="研究项目"
            className={page === "projects" ? "nav active" : "nav"}
            onClick={() => {
              setPage("projects");
              setSelected(null);
            }}
          >
            <Layers3 size={18} />
            <span className="nav-label">研究项目</span>
            <span className="nav-count">{allProjects.length}</span>
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
          ) : selected ? (
            <section>
              <button className="text-button" onClick={() => setSelected(null)}>
                ← 返回研究项目
              </button>
              <h2 className="project-title">{selected.name}</h2>
              {selected.description && (
                <p className="quiet-note">{selected.description}</p>
              )}
              <p className="quality-note">
                Lite 阅读模式：选择论文后只进行本地 PDF
                解析、章节建立和全文索引。PaperCard 与 LightGraph
                仅在你主动请求时生成。
              </p>
              <Papers
                key={selected.id}
                projectId={selected.id}
                connected={connected}
                experienceMode="lite"
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
    </div>
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
