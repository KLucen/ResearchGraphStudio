import { useState } from "react";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Eraser, Pencil, Save, Trash2, X } from "lucide-react";
import {
  api,
  defaultPostImportPlan,
  type PostImportPlan,
  type ReadingParagraph,
} from "./api";
import { ImportPostProcessingPlan } from "./ImportPostProcessingPlan";
import { PaperMetadata } from "./PaperMetadata";
import { KnowledgeReading } from "./KnowledgeReading";
import { PaperOverview } from "./PaperOverview";
import { ZoteroImport } from "./ZoteroImport";
import { ModelDocumentPanel } from "./ModelDocumentPanel";
import { PaperParsing } from "./PaperParsing";
const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

export function Papers({
  projectId,
  connected,
  projectName,
  initialPaperId,
  onOpenTasks,
  onPaperDeleted,
}: {
  projectId: string;
  connected: boolean;
  projectName?: string;
  initialPaperId?: string | null;
  onOpenTasks?: () => void;
  onPaperDeleted?: () => void;
}) {
  const paperId = initialPaperId ?? null;
  const [categories, setCategories] = useState<Record<string, string>>(() => {
    try {
      return JSON.parse(
        localStorage.getItem(`rgs.paper-categories.${projectId}`) ?? "{}",
      ) as Record<string, string>;
    } catch {
      return {};
    }
  });
  const papers = useInfiniteQuery({
    queryKey: ["papers", projectId],
    queryFn: ({ pageParam }) => api.papers(projectId, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: connected,
    refetchInterval: 3000,
  });
  const items = papers.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <section className="paper-workbench" aria-label="论文阅读工作区">
      {papers.error && (
        <p role="alert" className="error-text">
          {errorText(papers.error)}
        </p>
      )}
      {!paperId && (
        <div className="project-toolbar">
          <div>
            <div className="eyebrow">CURRENT PROJECT</div>
            <strong>{projectName ?? "研究项目"}</strong>
            <span className="project-toolbar-meta">
              {items.length} 篇论文 · 从左侧选择文献
            </span>
          </div>
        </div>
      )}
      {!paperId ? (
        <div className="project-reading-empty">
          <div className="project-reading-empty-copy">
            <div className="empty-art">
              <span className="empty-art-mark">↗</span>
            </div>
            <div>
              <h2>从左侧选择一篇论文</h2>
              <p>
                选中文献后，这里显示对应的论文阅读工作区：论文概览、论文精读和论文回答。
              </p>
            </div>
          </div>
          <div className="project-reading-empty-actions">
            <PaperImport projectId={projectId} connected={connected} />
            {onOpenTasks && (
              <button className="button secondary" onClick={onOpenTasks}>
                查看任务记录
              </button>
            )}
          </div>
        </div>
      ) : (
        <PaperText
          key={paperId}
          paperId={paperId}
          projectId={projectId}
          connected={connected}
          onPaperDeleted={onPaperDeleted}
          category={categories[paperId] ?? ""}
          onCategoryChange={(value) => {
            const next = { ...categories, [paperId]: value };
            setCategories(next);
            try {
              localStorage.setItem(
                `rgs.paper-categories.${projectId}`,
                JSON.stringify(next),
              );
            } catch {
              /* The in-memory classification remains available. */
            }
          }}
        />
      )}
    </section>
  );
}

export function PaperImport({
  projectId,
  connected,
  compact = false,
}: {
  projectId: string;
  connected: boolean;
  compact?: boolean;
}) {
  const [mode, setMode] = useState<"reference" | "managed">("reference");
  const [source, setSource] = useState<"pdf" | "zotero">("pdf");
  const [zoteroVisited, setZoteroVisited] = useState(false);
  const [postImportPlan, setPostImportPlan] = useState<PostImportPlan>(() =>
    defaultPostImportPlan(),
  );
  const client = useQueryClient();
  const importing = useMutation({
    mutationFn: async () => {
      const selection = await api.selectPdfImport();
      if (!selection) return null;
      return api.submitPdfImport(
        projectId,
        mode,
        selection.selection_id,
        postImportPlan.parse ? postImportPlan : undefined,
      );
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      void client.invalidateQueries({ queryKey: ["papers", projectId] });
      void client.invalidateQueries({
        queryKey: ["sidebar-papers", projectId],
      });
    },
  });
  return (
    <div className={compact ? "paper-import compact" : "paper-import"}>
      <div className="import-source-tabs" aria-label="论文导入来源">
        <button
          className={source === "pdf" ? "button primary" : "button secondary"}
          aria-pressed={source === "pdf"}
          onClick={() => setSource("pdf")}
        >
          本地 PDF
        </button>
        <button
          className={
            source === "zotero" ? "button primary" : "button secondary"
          }
          aria-pressed={source === "zotero"}
          onClick={() => {
            setSource("zotero");
            setZoteroVisited(true);
          }}
        >
          Zotero
        </button>
      </div>
      <div hidden={source !== "pdf"}>
        <div className="import-controls">
          <label>
            保存方式{" "}
            <select
              value={mode}
              disabled={importing.isPending}
              onChange={(e) => setMode(e.target.value as typeof mode)}
            >
              <option value="reference">引用原文件</option>
              <option value="managed">复制到项目存储</option>
            </select>
          </label>
          <button
            className="button primary"
            disabled={
              !connected ||
              importing.isPending ||
              (postImportPlan.parse && !postImportPlan.allow_network)
            }
            onClick={() => importing.mutate()}
          >
            {importing.isPending ? "正在选择…" : "选择 PDF 导入"}
          </button>
        </div>
        <ImportPostProcessingPlan
          value={postImportPlan}
          onChange={setPostImportPlan}
        />
        {!compact && (
          <p className="muted">
            默认使用本地解析；选择模型解析时才发送已授权的 PDF。每次一份，最多
            50 MiB / 300 页。
          </p>
        )}
        {importing.isError && (
          <p role="alert" className="error-text">
            {errorText(importing.error)}
          </p>
        )}
      </div>
      <div hidden={source !== "zotero"}>
        {zoteroVisited && (
          <ZoteroImport projectId={projectId} connected={connected} />
        )}
      </div>
    </div>
  );
}

function PaperText({
  paperId,
  projectId,
  connected,
  category,
  onCategoryChange,
  onPaperDeleted,
}: {
  paperId: string;
  projectId: string;
  connected: boolean;
  category: string;
  onCategoryChange: (value: string) => void;
  onPaperDeleted?: () => void;
}) {
  const detail = useQuery({
    queryKey: ["paper", paperId],
    queryFn: () => api.paper(paperId),
    enabled: connected,
    // Local import creates the paper before the immutable parsed revision.
    refetchInterval: (query) =>
      query.state.data && query.state.data.revisions.length === 0
        ? 1500
        : false,
  });
  const importSessions = useQuery({
    queryKey: ["paper-import-sessions", projectId],
    queryFn: () => api.importSessions(projectId),
    enabled: connected,
    refetchInterval: (query) =>
      query.state.data?.some((session) =>
        ["planned", "queued", "running"].includes(session.status),
      )
        ? 1500
        : false,
  });
  const [chosen, setChosen] = useState("");
  const [activePanel, setActivePanel] = useState<"overview" | "guide" | "qa">(
    "overview",
  );
  const [readingSection, setReadingSection] = useState("");
  const [readingParagraph, setReadingParagraph] = useState("");
  const [graphNode, setGraphNode] = useState("");
  const [qaParagraph, setQaParagraph] = useState<ReadingParagraph | null>(null);
  const revisionId =
    detail.data?.revisions.find((revision) => revision.id === chosen)?.id ??
    detail.data?.revisions[0]?.id ??
    "";
  const [showLocal, setShowLocal] = useState(false);
  const latestModelSession = (importSessions.data ?? [])
    .filter((session) => session.source_snapshot.paper_id === paperId)
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at))[0];
  const modelSession = showLocal ? undefined : latestModelSession;
  const client = useQueryClient();
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [managementMessage, setManagementMessage] = useState("");
  const renamePaper = useMutation({
    mutationFn: () => api.updatePaper(paperId, { title: titleDraft.trim() }),
    onSuccess: () => {
      setEditingTitle(false);
      setManagementMessage("论文题名已保存");
      void client.invalidateQueries({ queryKey: ["paper", paperId] });
      void client.invalidateQueries({ queryKey: ["papers", projectId] });
      void client.invalidateQueries({
        queryKey: ["sidebar-papers", projectId],
      });
    },
  });
  const clearLegacy = useMutation({
    mutationFn: () => api.clearPaperLegacyContent(paperId),
    onSuccess: (result) => {
      setChosen("");
      setManagementMessage(
        `已清理旧本地解析及缓存；保留个人记录 ${result.retained_personal_metadata} 项`,
      );
      void client.invalidateQueries({ queryKey: ["paper", paperId] });
      void client.invalidateQueries({ queryKey: ["papers", projectId] });
      void client.invalidateQueries({
        queryKey: ["sidebar-papers", projectId],
      });
    },
  });
  const deletePaper = useMutation({
    mutationFn: () => api.deletePaper(paperId),
    onSuccess: () => {
      void client.removeQueries({ queryKey: ["paper", paperId] });
      void client.invalidateQueries({ queryKey: ["papers", projectId] });
      void client.invalidateQueries({
        queryKey: ["sidebar-papers", projectId],
      });
      void client.invalidateQueries({
        queryKey: ["paper-import-sessions", projectId],
      });
      onPaperDeleted?.();
    },
  });
  const confirmClearLegacy = () => {
    if (
      window.confirm(
        "清理这篇论文的旧本地解析与缓存？个人笔记、已生成的概览/精读/问答、模型章节内容、论文记录及 PDF/Zotero 源文件都会保留。",
      )
    ) {
      setManagementMessage("");
      clearLegacy.mutate();
    }
  };
  const confirmDeletePaper = () => {
    if (
      window.confirm(
        "删除这篇论文及其本地生成内容？PDF 与 Zotero 文献库原件不会删除；已删除内容无法从应用恢复。",
      )
    ) {
      setManagementMessage("");
      deletePaper.mutate();
    }
  };
  const visibleTabs = [
    ["overview", "论文概览"],
    ["guide", "论文精读"],
    ["qa", "论文回答"],
  ] as const;
  return (
    <div className="paper-reading paper-reading-focused">
      {detail.isError && (
        <p role="alert" className="error-text">
          {errorText(detail.error)}
        </p>
      )}
      {detail.isPending && <p role="status">正在加载文献…</p>}
      {detail.data && (
        <>
          <header className="paper-workspace-header">
            <div className="paper-workspace-context">
              <h2>论文阅读工作区</h2>
              <span
                className="paper-workspace-paper"
                title={detail.data.paper.title}
              >
                {detail.data.paper.title}
              </span>
            </div>
            <div className="paper-management-actions" aria-label="论文管理">
              {!editingTitle ? (
                <button
                  type="button"
                  className="button secondary compact"
                  onClick={() => {
                    setTitleDraft(detail.data!.paper.title);
                    setEditingTitle(true);
                    setManagementMessage("");
                  }}
                >
                  <Pencil size={14} /> 编辑题名
                </button>
              ) : (
                <form
                  className="paper-title-edit"
                  onSubmit={(event) => {
                    event.preventDefault();
                    renamePaper.mutate();
                  }}
                >
                  <input
                    aria-label="编辑论文题名"
                    maxLength={500}
                    value={titleDraft}
                    onChange={(event) => setTitleDraft(event.target.value)}
                  />
                  <button
                    type="submit"
                    className="icon-button"
                    aria-label="保存论文题名"
                    title="保存"
                    disabled={!titleDraft.trim() || renamePaper.isPending}
                  >
                    <Save size={16} />
                  </button>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label="取消编辑论文题名"
                    title="取消"
                    onClick={() => setEditingTitle(false)}
                    disabled={renamePaper.isPending}
                  >
                    <X size={16} />
                  </button>
                </form>
              )}
              {detail.data.revisions.length > 0 && (
                <button
                  type="button"
                  className="button secondary compact"
                  onClick={confirmClearLegacy}
                  disabled={clearLegacy.isPending || deletePaper.isPending}
                  title="清理旧本地解析及缓存，保留个人笔记与已生成内容"
                >
                  <Eraser size={14} /> 清理旧解析
                </button>
              )}
              <button
                type="button"
                className="button danger compact"
                onClick={confirmDeletePaper}
                disabled={deletePaper.isPending || clearLegacy.isPending}
                title="删除论文和本地生成内容"
              >
                <Trash2 size={14} /> 删除论文
              </button>
            </div>
            {(managementMessage ||
              renamePaper.isError ||
              clearLegacy.isError ||
              deletePaper.isError) && (
              <p
                className={
                  renamePaper.isError ||
                  clearLegacy.isError ||
                  deletePaper.isError
                    ? "error-text"
                    : "paper-management-status"
                }
                role={
                  renamePaper.isError ||
                  clearLegacy.isError ||
                  deletePaper.isError
                    ? "alert"
                    : "status"
                }
              >
                {renamePaper.isError
                  ? errorText(renamePaper.error)
                  : clearLegacy.isError
                    ? errorText(clearLegacy.error)
                    : deletePaper.isError
                      ? errorText(deletePaper.error)
                      : managementMessage}
              </p>
            )}
            <PaperParsing
              paperId={paperId}
              projectId={projectId}
              connected={connected}
              hasLocal={!!revisionId}
              hasModel={!!latestModelSession}
              source={modelSession ? "model" : "local"}
              onViewSource={(mode) => setShowLocal(mode === "local")}
              onQueued={(mode) => {
                setShowLocal(mode === "local");
                if (activePanel !== "qa") setActivePanel("guide");
              }}
            >
              <nav
                className="reading-panels paper-workspace-tabs"
                aria-label="论文阅读板块"
              >
                {visibleTabs.map(([value, label]) => (
                  <button
                    type="button"
                    key={value}
                    className={
                      activePanel === value
                        ? "button primary"
                        : "button secondary"
                    }
                    aria-pressed={activePanel === value}
                    onClick={() => setActivePanel(value)}
                  >
                    {label}
                  </button>
                ))}
              </nav>
            </PaperParsing>
          </header>
          {modelSession && activePanel !== "qa" && (
            <ModelDocumentPanel
              paperId={paperId}
              sessionId={modelSession.id}
              connected={connected}
              activeView={activePanel === "guide" ? "reading" : "overview"}
              sessionStatus={modelSession.status}
              sessionError={modelSession.error}
            />
          )}
          {!modelSession && !revisionId && activePanel !== "qa" && (
            <div className="quality-note" role="status">
              <strong>正在准备论文阅读功能</strong>
              <p>
                当前论文尚无可读的解析版本。打开“论文解析操作”，选择本地或模型解析。
              </p>
              <p className="muted">
                如果长时间没有变化，请打开左侧“任务记录”查看 PDF 导入是否失败。
              </p>
            </div>
          )}
          {!modelSession && revisionId && (
            <>
              {activePanel === "overview" && (
                <section className="reading-panel" aria-label="论文概览">
                  <PaperOverview
                    key={`overview-${revisionId}-${graphNode}`}
                    paperId={paperId}
                    revisionId={revisionId}
                    projectId={projectId}
                    connected={connected}
                    initialNodeId={graphNode}
                    onOpenSection={(sectionId, paragraphId) => {
                      setReadingSection(sectionId);
                      setReadingParagraph(paragraphId ?? "");
                      setActivePanel("guide");
                    }}
                    onAskParagraph={(sectionId, paragraph) => {
                      setReadingSection(sectionId);
                      setQaParagraph(paragraph);
                      setActivePanel("qa");
                    }}
                  />
                </section>
              )}
              {activePanel === "guide" && (
                <section className="reading-panel" aria-label="论文精读">
                  <KnowledgeReading
                    key={`guide-${revisionId}`}
                    versionId={revisionId}
                    paperId={paperId}
                    connected={connected}
                    panel="guide"
                    initialSectionId={readingSection}
                    initialParagraphId={readingParagraph || undefined}
                    onSectionChange={(sectionId) => {
                      setReadingSection(sectionId);
                      setReadingParagraph("");
                    }}
                    onOpenGraph={(nodeId) => {
                      setGraphNode(nodeId);
                      setActivePanel("overview");
                    }}
                    onAskParagraph={(sectionId, paragraph) => {
                      setReadingSection(sectionId);
                      setQaParagraph(paragraph);
                      setActivePanel("qa");
                    }}
                  />
                </section>
              )}
            </>
          )}
          {activePanel === "qa" && (
            <section className="reading-panel" aria-label="论文回答">
              {revisionId ? (
                <>
                  {modelSession && (
                    <p className="quality-note">
                      论文回答使用这篇论文的本地解析原文作为引用来源。
                    </p>
                  )}
                  <KnowledgeReading
                    key={`qa-${revisionId}-${qaParagraph?.paragraph_id ?? ""}`}
                    versionId={revisionId}
                    paperId={paperId}
                    connected={connected}
                    panel="qa"
                    initialSectionId={readingSection}
                    selectedSpanIds={qaParagraph?.span_ids ?? []}
                    onSectionChange={(sectionId) => {
                      setReadingSection(sectionId);
                      setQaParagraph(null);
                    }}
                  />
                </>
              ) : (
                <p className="quality-note" role="status">
                  论文回答需要本地解析建立原文索引。打开圆形“论文解析操作”菜单，选择“本地解析
                  / 重试”。
                </p>
              )}
            </section>
          )}
          <PaperMetadata
            key={paperId}
            detail={detail.data}
            revisionId={revisionId}
            connected={connected}
            category={category}
            onCategoryChange={onCategoryChange}
            hideLegacyText={!!modelSession}
            onRevisionChange={(revisionId) => {
              setChosen(revisionId);
              setReadingSection("");
              setReadingParagraph("");
              setGraphNode("");
              setQaParagraph(null);
            }}
          />
        </>
      )}
    </div>
  );
}
