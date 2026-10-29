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
  Check,
  CircleDot,
  FolderOpen,
  Layers3,
  LoaderCircle,
  Network,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  X,
} from "lucide-react";
import { api, type Project } from "./api";
import { Papers } from "./Papers";

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
function date(value: string): string {
  return new Date(value).toLocaleDateString("zh-CN");
}

export default function App() {
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

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-symbol">
            <Network size={24} />
          </div>
          <div>
            ResearchGraph<span>STUDIO</span>
          </div>
        </div>
        <div className="workspace-label">个人研究空间</div>
        <nav aria-label="主导航">
          <button
            className={page === "projects" ? "nav active" : "nav"}
            onClick={() => {
              setPage("projects");
              setSelected(null);
            }}
          >
            <Layers3 size={18} />
            研究项目<span>{allProjects.length}</span>
          </button>
          <button
            className={page === "settings" ? "nav active" : "nav"}
            onClick={() => setPage("settings")}
          >
            <Settings2 size={18} />
            设置与诊断
          </button>
        </nav>
        <div className="sidebar-note">
          <ShieldCheck size={20} />
          <strong>知识，留在本地</strong>
          <p>
            项目保存在这台电脑上。
            <br />
            当前版本不调用云端模型。
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
        <div className="version">
          PHASE 1 <span>0.0.1</span>
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
            <CircleDot size={13} />
            LOCAL WORKSPACE
          </span>
        </header>
        <div className="content">
          {health.isError && (
            <div role="alert" className="error-banner">
              <strong>本地引擎未连接</strong>
              <p>{host.data?.error || message(health.error)}</p>
              <button
                className="button secondary"
                onClick={() => setPage("settings")}
              >
                打开连接诊断
                <ArrowRight size={15} />
              </button>
            </div>
          )}
          {page === "settings" ? (
            <Settings
              connected={connected}
              directory={host.data?.data_dir}
              health={connected ? health.data : undefined}
            />
          ) : selected ? (
            <section>
              <button className="text-button" onClick={() => setSelected(null)}>
                ← 返回研究项目
              </button>
              <div className="eyebrow">RESEARCH PROJECT</div>
              <h1>{selected.name}</h1>
              <p className="lead">
                {selected.description || "还没有添加研究问题描述。"}
              </p>
              <div className="project-detail">
                <ShieldCheck size={28} />
                <h2>项目已保存</h2>
                <p>项目信息存储在本地数据库，重新启动后可继续打开。</p>
                <dl>
                  <dt>创建日期</dt>
                  <dd>{date(selected.created_at)}</dd>
                  <dt>项目标识</dt>
                  <dd className="mono">{selected.id}</dd>
                </dl>
              </div>
              <Papers
                key={selected.id}
                projectId={selected.id}
                connected={connected}
              />
            </section>
          ) : (
            <>
              <div className="heading-row">
                <div>
                  <div className="eyebrow">YOUR RESEARCH, CONNECTED</div>
                  <h1>从一个研究问题开始</h1>
                  <p className="lead">
                    为你的研究建立独立空间，让每一次探索有迹可循。
                  </p>
                </div>
                <button
                  className="button primary"
                  disabled={!connected}
                  onClick={() => setCreating(true)}
                >
                  <Plus size={18} />
                  新建研究项目
                </button>
              </div>
              <section className="intro-strip">
                <div className="intro-icon">
                  <Network size={27} />
                </div>
                <div>
                  <strong>把研究组织起来</strong>
                  <p>按主题管理项目，先记录你想弄清楚的问题。</p>
                </div>
                <span className="pill">本地优先</span>
              </section>
              <div className="section-toolbar">
                <h2>
                  我的项目 <span>{allProjects.length}</span>
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
                      onClick={() => setSelected(p)}
                    >
                      <div className="card-top">
                        <FolderOpen size={22} />
                        <ArrowRight size={16} />
                      </div>
                      <h3>{p.name}</h3>
                      <p>{p.description || "从这里记录你的研究问题。"}</p>
                      <footer>
                        <i />
                        本地项目<span>{date(p.created_at)}</span>
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
                  <h3>
                    {search ? "没有找到匹配的项目" : "你的第一个研究项目"}
                  </h3>
                  <p>
                    {search
                      ? "试试其他关键词，或继续加载更多项目。"
                      : "一个明确的问题，是构建研究知识的起点。"}
                  </p>
                  {!search && (
                    <button
                      className="button secondary"
                      disabled={!connected}
                      onClick={() => setCreating(true)}
                    >
                      创建项目
                      <ArrowRight size={16} />
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
                  <ArrowDown size={16} />
                  加载更多
                </button>
              )}
              <footer className="page-footer">
                <span>RESEARCHGRAPH STUDIO</span>
                <span>从证据到理解，每一步都有来源。</span>
              </footer>
            </>
          )}
        </div>
      </main>
      {creating && (
        <CreateProject
          onClose={() => setCreating(false)}
          onCreated={(p) => {
            setCreating(false);
            setSelected(p);
            void client.invalidateQueries({ queryKey: ["projects"] });
          }}
        />
      )}
    </div>
  );
}

function CreateProject({
  onClose,
  onCreated,
}: {
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
  const dialog = useRef<HTMLDialogElement>(null);
  return (
    <dialog
      className="dialog"
      aria-labelledby="create-project-title"
      ref={(node) => {
        dialog.current = node;
        if (node && !node.open) node.showModal();
      }}
      onCancel={(e) => {
        e.preventDefault();
        if (!mutation.isPending) onClose();
      }}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <div className="dialog-header">
          <div className="eyebrow">NEW PROJECT</div>
          <button
            type="button"
            className="icon-button"
            aria-label="关闭新建项目"
            disabled={mutation.isPending}
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        <h2 id="create-project-title">新建研究项目</h2>
        <p className="lead">给研究一个名字，留下一条清晰的问题线索。</p>
        <label className="field">
          项目名称
          <input
            autoFocus
            required
            maxLength={120}
            value={name}
            placeholder="例如：多智能体的共享记忆"
            disabled={mutation.isPending}
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
            disabled={mutation.isPending}
            placeholder="你希望通过这项研究弄清楚什么？"
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
          <button
            type="button"
            className="button secondary"
            disabled={mutation.isPending}
            onClick={onClose}
          >
            取消
          </button>
          <button
            className="button primary"
            disabled={!name.trim() || mutation.isPending}
          >
            {mutation.isPending ? "正在保存…" : "创建项目"}
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
}: {
  connected: boolean;
  directory?: string;
  health?: Awaited<ReturnType<typeof api.health>>;
}) {
  const client = useQueryClient();
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: api.jobs,
    enabled: connected,
    refetchInterval: 2000,
  });
  const restart = useMutation({
    mutationFn: api.restart,
    onSuccess: () => {
      void client.invalidateQueries();
    },
  });
  const diagnose = useMutation({
    mutationFn: () => api.diagnose(crypto.randomUUID()),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
  const action = useMutation({
    mutationFn: ({ id, kind }: { id: string; kind: "cancel" | "retry" }) =>
      api.jobAction(id, kind, crypto.randomUUID()),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
  const names: Record<string, string> = {
    queued: "等待执行",
    running: "执行中",
    succeeded: "检查通过",
    failed: "失败",
    cancelled: "已取消",
    interrupted: "已中断",
  };
  return (
    <>
      <div className="eyebrow">LOCAL ENVIRONMENT</div>
      <h1>设置与诊断</h1>
      <p className="lead">查看本地运行状态，检查项目存储是否正常。</p>
      <section className="settings-card">
        <div className="settings-title">
          <ShieldCheck size={22} />
          <h2>本地引擎</h2>
          <span className="pill">{connected ? "已连接" : "未连接"}</span>
        </div>
        <dl>
          <dt>引擎版本</dt>
          <dd>{health?.version ?? "等待连接"}</dd>
          <dt>数据库版本</dt>
          <dd>{health?.schema_version ?? "等待连接"}</dd>
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
        <p>检查 SQLite 完整性、外键和全文检索，不读取论文或个人笔记。</p>
        {(diagnose.isError || action.isError || jobs.isError) && (
          <p role="alert" className="error-text">
            {message(diagnose.error || action.error || jobs.error)}
          </p>
        )}
        <div className="job-list">
          {jobs.data?.length ? (
            jobs.data
              .filter((job) => job.kind === "diagnostics")
              .map((job) => (
                <div className="job" key={job.id}>
                  <div className="job-symbol">
                    {job.status === "succeeded" ? (
                      <Check size={18} />
                    ) : (
                      <CircleDot size={18} />
                    )}
                  </div>
                  <div>
                    <strong>存储诊断 · {names[job.status]}</strong>
                    <small>
                      {date(job.created_at)} · 第 {job.attempt} 次执行
                    </small>
                    {job.error && <p className="error-text">{job.error}</p>}
                  </div>
                  {["queued", "running"].includes(job.status) ? (
                    <button
                      className="text-button"
                      disabled={action.isPending}
                      onClick={() =>
                        action.mutate({ id: job.id, kind: "cancel" })
                      }
                    >
                      取消
                    </button>
                  ) : ["failed", "interrupted", "cancelled"].includes(
                      job.status,
                    ) && job.attempt < 3 ? (
                    <button
                      className="text-button"
                      disabled={action.isPending}
                      onClick={() =>
                        action.mutate({ id: job.id, kind: "retry" })
                      }
                    >
                      重试
                    </button>
                  ) : null}
                </div>
              ))
          ) : (
            <p className="muted">尚未运行诊断。</p>
          )}
        </div>
      </section>
      <p className="quiet-note">
        当前支持本地项目与 PDF 原文导入。模型和知识图谱功能将在后续阶段开放。
      </p>
    </>
  );
}
