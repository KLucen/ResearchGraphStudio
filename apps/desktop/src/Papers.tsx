import { useState } from "react";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "./api";
import { PaperMetadata } from "./PaperMetadata";
import { KnowledgeReading } from "./KnowledgeReading";
import { PaperOverview } from "./PaperOverview";
import { PaperTranslation } from "./PaperTranslation";
import { ZoteroImport } from "./ZoteroImport";
const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

export function Papers({
  projectId,
  connected,
  projectName,
  initialPaperId,
  onOpenTasks,
}: {
  projectId: string;
  connected: boolean;
  projectName?: string;
  initialPaperId?: string | null;
  onOpenTasks?: () => void;
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
                选中文献后，这里显示对应的论文阅读工作区：论文概览、章节精读、论文问答和文献翻译。
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
  const client = useQueryClient();
  const importing = useMutation({
    mutationFn: () => api.importPdf(projectId, mode),
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
            disabled={!connected || importing.isPending}
            onClick={() => importing.mutate()}
          >
            {importing.isPending ? "正在选择…" : "选择 PDF 导入"}
          </button>
        </div>
        {!compact && (
          <p className="muted">
            选择 PDF
            后仅在本机解析章节、文本块和全文索引，不会自动调用模型。每次一份，最多
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
}: {
  paperId: string;
  projectId: string;
  connected: boolean;
  category: string;
  onCategoryChange: (value: string) => void;
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
  const [chosen, setChosen] = useState("");
  const [activePanel, setActivePanel] = useState<
    "overview" | "guide" | "qa" | "translation"
  >("overview");
  const revisionId = chosen || detail.data?.revisions[0]?.id || "";
  const revision = detail.data?.revisions.find(
    (item) => item.id === revisionId,
  );
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
            <nav
              className="reading-panels paper-workspace-tabs"
              aria-label="论文阅读板块"
            >
              {(
                [
                  ["overview", "论文概览"],
                  ["guide", "章节精读"],
                  ["qa", "论文问答"],
                  ["translation", "文献翻译"],
                ] as const
              ).map(([value, label]) => (
                <button
                  type="button"
                  key={value}
                  className={
                    activePanel === value
                      ? "button primary"
                      : "button secondary"
                  }
                  aria-pressed={activePanel === value}
                  disabled={!revisionId}
                  onClick={() => setActivePanel(value)}
                >
                  {label}
                </button>
              ))}
            </nav>
          </header>
          {!revisionId && (
            <div className="quality-note" role="status">
              <strong>正在准备论文阅读功能</strong>
              <p>
                当前论文还没有完成的 PDF
                解析版本。系统正在等待本地解析和章节索引；完成后会启用论文概览、章节精读、论文问答和文献翻译。
              </p>
              <p className="muted">
                如果长时间没有变化，请打开左侧“任务记录”查看 PDF 导入是否失败。
              </p>
            </div>
          )}
          {revisionId && (
            <>
              {activePanel === "overview" && (
                <section className="reading-panel" aria-label="论文概览">
                  <PaperOverview
                    key={`overview-${revisionId}`}
                    paperId={paperId}
                    revisionId={revisionId}
                    projectId={projectId}
                    connected={connected}
                  />
                </section>
              )}
              {activePanel === "guide" && (
                <section className="reading-panel" aria-label="章节精读">
                  <KnowledgeReading
                    key={`guide-${revisionId}`}
                    versionId={revisionId}
                    paperId={paperId}
                    connected={connected}
                    panel="guide"
                  />
                </section>
              )}
              {activePanel === "qa" && (
                <section className="reading-panel" aria-label="论文问答">
                  <KnowledgeReading
                    key={`qa-${revisionId}`}
                    versionId={revisionId}
                    paperId={paperId}
                    connected={connected}
                    panel="qa"
                  />
                </section>
              )}
              {activePanel === "translation" && (
                <section className="reading-panel" aria-label="文献翻译工作区">
                  <PaperTranslation
                    paperId={paperId}
                    revisionId={revisionId}
                    pageCount={revision?.page_count ?? 0}
                    connected={connected}
                  />
                </section>
              )}
            </>
          )}
          <PaperMetadata
            key={paperId}
            detail={detail.data}
            revisionId={revisionId}
            connected={connected}
            category={category}
            onCategoryChange={onCategoryChange}
            onRevisionChange={setChosen}
          />
        </>
      )}
    </div>
  );
}
