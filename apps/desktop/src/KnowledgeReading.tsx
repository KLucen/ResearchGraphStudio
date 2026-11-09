import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "./api";

export function KnowledgeReading({
  versionId,
  paperId,
  connected,
}: {
  versionId: string;
  paperId: string;
  connected: boolean;
}) {
  const [query, setQuery] = useState("");
  const [sectionId, setSectionId] = useState("");
  const sections = useQuery({
    queryKey: ["sections", versionId],
    queryFn: () => api.sections(versionId),
    enabled: connected,
    retry: false,
  });
  const search = useMutation({
    mutationFn: () =>
      api.search(paperId, query.trim(), versionId, sectionId || undefined),
    retry: false,
  });
  const selected = sections.data?.sections.find(
    (section) => section.id === sectionId,
  );
  return (
    <section className="knowledge-area" aria-label="章节与本地索引">
      <h4>章节与本地索引</h4>
      <p className="muted">章节识别和原文搜索在本机完成，不调用模型。</p>
      {sections.isPending && connected && <p role="status">正在读取章节…</p>}
      {sections.isError && (
        <p role="alert" className="error-text">
          {sections.error.message}
          <button
            className="text-button"
            onClick={() => void sections.refetch()}
          >
            重试读取
          </button>
        </p>
      )}
      {sections.data && (
        <>
          <p role="status">
            本地索引已就绪：{sections.data.sections.length} 个章节。
          </p>
          <label>
            选择章节{" "}
            <select
              value={sectionId}
              onChange={(e) => setSectionId(e.target.value)}
            >
              <option value="">全部章节</option>
              {sections.data.sections.map((section) => (
                <option key={section.id} value={section.id}>
                  {section.title || `章节 ${section.ordinal + 1}`}
                  {section.excluded ? "（参考文献等）" : ""}
                </option>
              ))}
            </select>
          </label>
          {selected && (
            <details key={selected.id}>
              <summary>{selected.title} · 查看章节原文</summary>
              {selected.start_page !== null && (
                <p className="muted">
                  PDF 第 {selected.start_page + 1} 页
                  {selected.end_page !== null &&
                  selected.end_page !== selected.start_page
                    ? ` 至第 ${selected.end_page + 1} 页`
                    : ""}
                </p>
              )}
              <pre className="section-text">
                {selected.text || "此章节没有可提取文本。"}
              </pre>
            </details>
          )}
        </>
      )}
      <form
        className="import-controls"
        onSubmit={(e) => {
          e.preventDefault();
          if (connected && query.trim()) search.mutate();
        }}
      >
        <label>
          搜索论文原文
          <input
            value={query}
            maxLength={500}
            placeholder="输入原文中的关键词"
            disabled={!connected}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <button
          className="button secondary"
          disabled={!connected || !query.trim() || search.isPending}
        >
          {search.isPending ? "正在搜索…" : "本地搜索"}
        </button>
      </form>
      {search.isError && (
        <p role="alert" className="error-text">
          {search.error.message}
        </p>
      )}
      {search.data && (
        <div aria-label="本地检索结果">
          <p>
            {search.data.items.length
              ? `“${search.data.query}” 的原文命中`
              : "未找到匹配原文，请尝试原文中的词语。"}
          </p>
          {search.data.items.map((hit) => (
            <article className="text-chunk" key={hit.chunk_id}>
              <header>
                PDF 第 {hit.page_index + 1} 页
                {hit.page_label ? ` · ${hit.page_label}` : ""}
              </header>
              <pre>{hit.text}</pre>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
