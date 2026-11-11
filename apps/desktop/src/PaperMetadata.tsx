import { useState } from "react";
import { useInfiniteQuery, useMutation } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";
import { api, type PaperDetail } from "./api";
import { SourceFiles } from "./SourceFiles";

const categories = [
  ["", "未分类"],
  ["to-read", "待读"],
  ["reading", "阅读中"],
  ["read", "已读"],
  ["important", "重点"],
] as const;
const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

export function PaperMetadata({
  detail,
  revisionId,
  connected,
  category,
  onCategoryChange,
  onRevisionChange,
}: {
  detail: PaperDetail;
  revisionId: string;
  connected: boolean;
  category: string;
  onCategoryChange: (value: string) => void;
  onRevisionChange: (value: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [showText, setShowText] = useState(false);
  const openZotero = useMutation({
    mutationFn: (url: string) => invoke("open_zotero", { url }),
  });
  const revision = detail.revisions.find((item) => item.id === revisionId);
  const chunks = useInfiniteQuery({
    queryKey: ["chunks", revisionId],
    queryFn: ({ pageParam }) => api.chunks(revisionId, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: connected && !!revisionId && expanded && showText,
  });
  return (
    <details
      className="paper-metadata-card"
      onToggle={(event) => setExpanded(event.currentTarget.open)}
    >
      <summary className="paper-metadata-summary">
        <span>
          <strong>论文信息</strong>
          <small>附件修订、分类与来源文件</small>
        </span>
        <span className="paper-metadata-toggle" aria-hidden="true" />
      </summary>
      <div className="paper-metadata-body">
        <div className="paper-metadata-title-row">
          <h3>{detail.paper.title}</h3>
          <label className="paper-category-editor">
            分类
            <select
              aria-label="论文分类"
              value={category}
              onChange={(event) => onCategoryChange(event.target.value)}
            >
              {categories.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="paper-metadata-controls">
          {detail.zotero_links?.map(
            (link) =>
              link.url && (
                <button
                  type="button"
                  className="button secondary"
                  key={`${link.item_key}-${link.attachment_key}`}
                  disabled={openZotero.isPending}
                  onClick={() => openZotero.mutate(link.url!)}
                >
                  在 Zotero 中打开
                </button>
              ),
          )}
          <label>
            附件修订
            <select
              aria-label="附件修订"
              value={revisionId}
              disabled={!detail.revisions.length}
              onChange={(event) => onRevisionChange(event.target.value)}
            >
              {detail.revisions.map((item, index) => (
                <option key={item.id} value={item.id}>
                  {index === 0 ? "最新保存 · " : "历史 · "}
                  {new Date(item.created_at).toLocaleString("zh-CN")} ·{" "}
                  {item.sha256.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
        </div>
        {openZotero.isError && (
          <p role="alert" className="error-text">
            {errorText(openZotero.error)}
          </p>
        )}
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
          sources={detail.sources}
          paperId={detail.paper.id}
          selectedRevisionId={revisionId}
          connected={connected}
        />
        {revisionId && (
          <details
            className="paper-metadata-original"
            onToggle={(event) => setShowText(event.currentTarget.open)}
          >
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
                type="button"
                className="button secondary"
                disabled={chunks.isFetchingNextPage}
                onClick={() => void chunks.fetchNextPage()}
              >
                加载更多原文块
              </button>
            )}
          </details>
        )}
      </div>
    </details>
  );
}
