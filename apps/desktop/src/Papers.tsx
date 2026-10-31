import { useState } from "react";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "./api";
import { SourceFiles } from "./SourceFiles";
import { JobHistory } from "./JobHistory";
function errorText(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

export function Papers({
  projectId,
  connected,
}: {
  projectId: string;
  connected: boolean;
}) {
  const [mode, setMode] = useState<"reference" | "managed">("reference");
  const [paperId, setPaperId] = useState<string | null>(null);
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
    <section className="paper-workbench" aria-label="项目文献">
      <div className="settings-title">
        <h2>文献与原文</h2>
        <span className="pill">本地 PDF</span>
      </div>
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
        {mode === "reference"
          ? "保存原文件路径和解析文本；移动原文件后可在来源文件中重新定位。"
          : "明确复制所选 PDF 到本地应用存储，保留独立副本。"}{" "}
        每次一份，最多 50 MiB / 300 页。
      </p>
      {[importing.error, papers.error].filter(Boolean).map((error, i) => (
        <p role="alert" className="error-text" key={i}>
          {errorText(error)}
        </p>
      ))}
      <JobHistory projectId={projectId} connected={connected} />
      <div className="paper-columns">
        <div className="paper-list">
          <h3>项目文献 · {items.length}</h3>
          {!items.length && (
            <p className="muted">
              {papers.isPending && connected
                ? "正在加载…"
                : "导入一份 PDF 后，查看页码与原文块。"}
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
          <PaperText key={paperId} paperId={paperId} connected={connected} />
        ) : (
          <div className="paper-reading muted">
            选择文献查看来源、附件修订和解析原文。
          </div>
        )}
      </div>
    </section>
  );
}

function PaperText({
  paperId,
  connected,
}: {
  paperId: string;
  connected: boolean;
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
          <p className="quiet-note">
            以下为解析原文。页序从 1
            开始；坐标为解析器文本块边界，不代表已审核证据。
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
                  PDF 第 {chunk.page_index + 1} 页 · 块 {chunk.block_index + 1}
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
        </>
      )}
    </div>
  );
}
