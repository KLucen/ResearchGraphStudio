import { useState } from "react";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";
import { api } from "./api";
import { SourceFiles } from "./SourceFiles";
import { JobHistory } from "./JobHistory";
import { KnowledgeReading } from "./KnowledgeReading";
import { PaperOverview } from "./PaperOverview";
import { ZoteroImport } from "./ZoteroImport";
import { WorkbenchSection } from "./WorkbenchSection";
const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

export function Papers({
  projectId,
  connected,
}: {
  projectId: string;
  connected: boolean;
  experienceMode?: "lite";
}) {
  const [mode, setMode] = useState<"reference" | "managed">("reference");
  const [paperId, setPaperId] = useState<string | null>(null);
  const [source, setSource] = useState<"pdf" | "zotero">("pdf");
  const [zoteroVisited, setZoteroVisited] = useState(false);
  const client = useQueryClient();
  const papers = useInfiniteQuery({
    queryKey: ["papers", projectId],
    queryFn: ({ pageParam }) => api.papers(projectId, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: connected,
    refetchInterval: 3000,
  });
  const importing = useMutation({
    mutationFn: () => api.importPdf(projectId, mode),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      void client.invalidateQueries({ queryKey: ["papers", projectId] });
    },
  });
  const items = papers.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <section className="paper-workbench" aria-label="文献与阅读">
      <LiteUsageSummary
        projectId={projectId}
        connected={connected}
        paperId={paperId ?? undefined}
      />
      <WorkbenchSection
        projectId={projectId}
        id="import"
        title="导入论文"
        description="本地 PDF / Zotero 分类与附件"
      >
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
          <p className="muted">
            选择 PDF
            后仅在本机解析章节、文本块和全文索引，不会自动调用模型。每次一份，最多
            50 MiB / 300 页。
          </p>
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
      </WorkbenchSection>
      <WorkbenchSection
        projectId={projectId}
        id="jobs"
        title="任务记录"
        description="本地处理和概览生成进度"
      >
        <JobHistory projectId={projectId} connected={connected} />
      </WorkbenchSection>
      <WorkbenchSection
        projectId={projectId}
        id="library"
        title={`项目文献 · ${items.length}`}
        description="章节、原文检索与论文概览"
      >
        {papers.error && (
          <p role="alert" className="error-text">
            {errorText(papers.error)}
          </p>
        )}
        <div className="paper-columns">
          <div className="paper-list">
            <h3>选择文献</h3>
            {!items.length && (
              <p className="muted">
                {papers.isPending && connected
                  ? "正在加载…"
                  : "导入论文后查看章节、原文和概览。"}
              </p>
            )}
            {items.map((paper) => (
              <button
                className={
                  paper.id === paperId ? "paper-item selected" : "paper-item"
                }
                aria-pressed={paper.id === paperId}
                key={paper.id}
                onClick={() => setPaperId(paper.id)}
              >
                {paper.title}
              </button>
            ))}
            {papers.hasNextPage && (
              <button
                className="text-button"
                disabled={papers.isFetchingNextPage}
                onClick={() => void papers.fetchNextPage()}
              >
                加载更多文献
              </button>
            )}
          </div>
          {paperId ? (
            <PaperText
              key={paperId}
              paperId={paperId}
              projectId={projectId}
              connected={connected}
            />
          ) : (
            <div className="paper-reading muted">
              选择文献查看章节、原文和论文概览。
            </div>
          )}
        </div>
      </WorkbenchSection>
    </section>
  );
}

function LiteUsageSummary({
  projectId,
  connected,
  paperId,
}: {
  projectId: string;
  connected: boolean;
  paperId?: string;
}) {
  const usage = useQuery({
    queryKey: ["lite-usage", projectId, paperId ?? null],
    queryFn: () => api.liteUsage(projectId, paperId),
    enabled: connected,
    refetchInterval: 5000,
  });
  if (usage.isPending) return <p className="muted">正在读取本地用量统计…</p>;
  if (usage.isError)
    return <p className="quality-note">用量统计暂不可用，阅读流程仍可继续。</p>;
  const data = usage.data;
  const callLabel = data.calls_known
    ? data.calls === 0
      ? data.cache_hits > 0
        ? "0 次新增模型调用"
        : "尚未调用模型"
      : `${data.calls} 次调用`
    : `已记录调用 ${data.calls} 次；另有 ${data.unrecorded_runs} 条历史记录未记录调用次数`;
  return (
    <section className="settings-card" aria-label="Lite 模型用量">
      <div className="settings-title">
        <h2>Lite 用量</h2>
        <span className="pill">{callLabel}</span>
      </div>
      <dl>
        <dt>输入 Token</dt>
        <dd>{data.input_tokens.toLocaleString("zh-CN")}</dd>
        <dt>输出 Token</dt>
        <dd>{data.output_tokens.toLocaleString("zh-CN")}</dd>
        <dt>调用 / 重试</dt>
        <dd>
          {data.calls} / {data.retry_count}
        </dd>
        <dt>缓存命中</dt>
        <dd>{data.cache_hits}</dd>
        <dt>费用</dt>
        <dd>
          {data.cost_known && data.cost_estimate !== null
            ? data.cost_estimate.toLocaleString("zh-CN", {
                style: "currency",
                currency: "USD",
              })
            : "未提供定价"}
        </dd>
      </dl>
      {data.unknown_usage_calls > 0 && (
        <p className="quality-note">
          {data.unknown_usage_calls} 次请求未返回完整 Token 用量，不能按 0
          计算。
        </p>
      )}
      {data.cache_hits > 0 && (
        <p className="muted">
          缓存命中 {data.cache_hits} 次，未产生新的模型调用或 Token。
        </p>
      )}
      {data.calls === 0 && (
        <p className="muted">
          本地解析、章节建立和全文索引不会产生模型 Token。
        </p>
      )}
    </section>
  );
}

function PaperText({
  paperId,
  projectId,
  connected,
}: {
  paperId: string;
  projectId: string;
  connected: boolean;
}) {
  const detail = useQuery({
    queryKey: ["paper", paperId],
    queryFn: () => api.paper(paperId),
    enabled: connected,
  });
  const openZotero = useMutation({
    mutationFn: (url: string) => invoke("open_zotero", { url }),
  });
  const [chosen, setChosen] = useState("");
  const [showText, setShowText] = useState(false);
  const revisionId = chosen || detail.data?.revisions[0]?.id || "";
  const revision = detail.data?.revisions.find(
    (item) => item.id === revisionId,
  );
  const chunks = useInfiniteQuery({
    queryKey: ["chunks", revisionId],
    queryFn: ({ pageParam }) => api.chunks(revisionId, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: connected && !!revisionId && showText,
  });
  return (
    <div className="paper-reading">
      {detail.isError && (
        <p role="alert" className="error-text">
          {errorText(detail.error)}
        </p>
      )}
      {detail.isPending && <p>正在加载文献…</p>}
      {detail.data && (
        <>
          <h3>{detail.data.paper.title}</h3>
          {detail.data.zotero_links?.map(
            (link) =>
              link.url && (
                <button
                  className="button secondary"
                  key={`${link.item_key}-${link.attachment_key}`}
                  disabled={openZotero.isPending}
                  onClick={() => openZotero.mutate(link.url!)}
                >
                  在 Zotero 中打开
                </button>
              ),
          )}
          {openZotero.isError && (
            <p role="alert" className="error-text">
              {errorText(openZotero.error)}
            </p>
          )}
          <label>
            附件修订{" "}
            <select
              value={revisionId}
              onChange={(e) => setChosen(e.target.value)}
            >
              {detail.data.revisions.map((item, index) => (
                <option key={item.id} value={item.id}>
                  {index === 0 ? "最新保存 · " : "历史 · "}
                  {new Date(item.created_at).toLocaleString("zh-CN")} ·{" "}
                  {item.sha256.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
          {revision && (
            <>
              <p className="mono small">
                {revision.parser_version} · {revision.page_count} 页
              </p>
              {revision.warnings.map((warning) => (
                <p className="quality-note" key={warning}>
                  {warning}
                </p>
              ))}
            </>
          )}
          <SourceFiles
            sources={detail.data.sources}
            paperId={paperId}
            selectedRevisionId={revisionId}
            connected={connected}
          />
          {revisionId && (
            <>
              <KnowledgeReading
                key={revisionId}
                versionId={revisionId}
                paperId={paperId}
                connected={connected}
              />
              <PaperOverview
                key={`overview-${revisionId}`}
                paperId={paperId}
                revisionId={revisionId}
                projectId={projectId}
                connected={connected}
              />
            </>
          )}
          <details onToggle={(e) => setShowText(e.currentTarget.open)}>
            <summary>解析原文（按需查看）</summary>
            <p className="quiet-note">
              PDF 页序从 1 开始；扫描件暂不执行 OCR。
            </p>
            {chunks.isError && (
              <p role="alert" className="error-text">
                {errorText(chunks.error)}
              </p>
            )}
            {showText && chunks.isPending && <p>正在加载原文…</p>}
            {chunks.data?.pages
              .flatMap((page) => page.items)
              .map((chunk) => (
                <article className="text-chunk" key={chunk.id}>
                  <header>
                    PDF 第 {chunk.page_index + 1} 页 · 块{" "}
                    {chunk.block_index + 1}
                    {chunk.page_label && ` · 页标签 ${chunk.page_label}`}
                  </header>
                  <pre>{chunk.text}</pre>
                </article>
              ))}
            {chunks.hasNextPage && (
              <button
                className="button secondary"
                disabled={chunks.isFetchingNextPage}
                onClick={() => void chunks.fetchNextPage()}
              >
                加载更多原文块
              </button>
            )}
          </details>
        </>
      )}
    </div>
  );
}
