import { useState } from "react";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api, type LiteUsage } from "./api";
import { SourceFiles } from "./SourceFiles";
import { JobHistory } from "./JobHistory";
import { KnowledgeReading } from "./KnowledgeReading";
import { ZoteroImport } from "./ZoteroImport";
import { WorkbenchSection } from "./WorkbenchSection";
function errorText(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

export type ExperienceMode = "lite" | "legacy" | "full";

export function Papers({
  projectId,
  connected,
  experienceMode = "full",
}: {
  projectId: string;
  connected: boolean;
  experienceMode?: ExperienceMode;
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
    refetchInterval: 2000,
  });
  const importing = useMutation({
    mutationFn: () => api.importPdf(projectId, mode),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
  const items = papers.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <section className="paper-workbench" aria-label="文献与阅读">
      {experienceMode === "lite" && (
        <LiteUsageSummary
          projectId={projectId}
          connected={connected}
          paperId={paperId ?? undefined}
        />
      )}
      <WorkbenchSection
        projectId={projectId}
        id="import"
        title="导入论文"
        description="本地 PDF / Zotero Collection 与附件"
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
            {experienceMode === "lite"
              ? "选择本地 PDF 后仅在本机解析章节、文本块和全文索引，不会自动调用模型。"
              : "选择本地 PDF 解析原文，随后可在项目文献中抽取知识。"}
            每次一份，最多 50 MiB / 300 页。
          </p>
          {[importing.error].filter(Boolean).map((error, i) => (
            <p role="alert" className="error-text" key={i}>
              {errorText(error)}
            </p>
          ))}
        </div>
        <div hidden={source !== "zotero"}>
          {zoteroVisited && (
            <ZoteroImport
              projectId={projectId}
              connected={connected}
              liteMode={experienceMode === "lite"}
            />
          )}
        </div>
      </WorkbenchSection>
      <WorkbenchSection
        projectId={projectId}
        id="jobs"
        title="任务记录"
        description="处理进度、失败原因、继续未完成批次与历史"
      >
        <JobHistory projectId={projectId} connected={connected} />
      </WorkbenchSection>
      <WorkbenchSection
        projectId={projectId}
        id="library"
        title={`项目文献 · ${items.length}`}
        description="文献列表、知识概览、来源证据与模型记录"
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
                  : "导入论文后查看知识状态、证据和图谱入口。"}
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
              connected={connected}
              experienceMode={experienceMode}
            />
          ) : (
            <div className="paper-reading muted">
              选择文献查看知识概览、证据和抽取状态。
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
  const data: LiteUsage | undefined = usage.data;
  if (!data) return null;
  const unrecordedRuns = data.unrecorded_runs;
  const unattributedRuns = data.unattributed_runs;
  const callsKnown = data.calls_known;
  const callLabel = callsKnown
    ? data.calls === 0
      ? data.cache_hits > 0
        ? "0 次新增模型调用"
        : "尚未调用模型"
      : `${data.calls} 次调用`
    : `已记录调用 ${data.calls} 次；${
        unrecordedRuns > 0
          ? `另有 ${unrecordedRuns} 条历史记录未记录调用次数`
          : "调用次数不完整"
      }`;
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
        <dt>重试次数</dt>
        <dd>{data.retry_count}</dd>
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
      {paperId && unattributedRuns > 0 && (
        <p className="quality-note">
          另有 {unattributedRuns}{" "}
          条项目级历史请求未归入这篇论文，以上单篇统计不包含它们。
        </p>
      )}
      {!paperId && unattributedRuns > 0 && (
        <p className="quality-note">
          有 {unattributedRuns} 条项目级历史请求没有归入单篇论文。
        </p>
      )}
      {data.cache_hits > 0 && (
        <p className="muted">
          缓存命中 {data.cache_hits} 次，未产生新的模型调用或 Token。
        </p>
      )}
      {data.calls === 0 && data.cache_hits === 0 && (
        <p className="muted">
          本地解析、章节建立和全文索引不会产生模型 Token。
        </p>
      )}
    </section>
  );
}

function PaperText({
  paperId,
  connected,
  experienceMode,
}: {
  paperId: string;
  connected: boolean;
  experienceMode: ExperienceMode;
}) {
  const detail = useQuery({
    queryKey: ["paper", paperId],
    queryFn: () => api.paper(paperId),
    enabled: connected,
    refetchInterval: 2000,
  });
  const [chosen, setChosen] = useState("");
  const revisionId = chosen || detail.data?.revisions[0]?.id || "";
  const revision = detail.data?.revisions.find(
    (item) => item.id === revisionId,
  );
  const chunks = useInfiniteQuery({
    queryKey: ["chunks", revisionId],
    queryFn: ({ pageParam }) => api.chunks(revisionId, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: connected && !!revisionId,
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
          {detail.data.zotero_links?.map((link) => (
            <a
              className="button secondary"
              href={link.url}
              key={`${link.item_key}-${link.attachment_key}`}
            >
              在 Zotero 中打开
            </a>
          ))}
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
                SHA-256: {revision.sha256}
                <br />
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
            <KnowledgeReading
              key={revisionId}
              versionId={revisionId}
              connected={connected}
              liteMode={experienceMode === "lite"}
            />
          )}
          <details>
            <summary>解析原文（按需查看）</summary>
            <p className="quiet-note">
              页序从 1 开始；坐标为解析器文本块边界，不代表已审核证据。
            </p>
            {chunks.isError && (
              <p role="alert" className="error-text">
                {errorText(chunks.error)}
              </p>
            )}
            {chunks.isPending && connected && <p>正在加载原文…</p>}
            {chunks.isSuccess && !chunks.data.pages[0].items.length && (
              <p>没有可提取文本。扫描件暂不执行 OCR。</p>
            )}
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
                  <details>
                    <summary>定位信息</summary>
                    <span className="mono small">
                      块 ID {chunk.id}
                      <br />
                      字符区间 [0, {Array.from(chunk.text).length}) · bbox{" "}
                      {chunk.bbox.map((n) => n.toFixed(1)).join(", ")}
                    </span>
                  </details>
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
