import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  type GuideDepth,
  type QAScope,
  type SearchHit,
  type QAView,
  type ReadingGuide,
} from "./api";

export function KnowledgeReading({
  versionId,
  paperId,
  connected,
  panel = "all",
}: {
  versionId: string;
  paperId: string;
  connected: boolean;
  panel?: "guide" | "qa" | "all";
}) {
  const [query, setQuery] = useState("");
  const [sectionId, setSectionId] = useState("");
  const [depth, setDepth] = useState<GuideDepth>("standard");
  const [allowNetwork, setAllowNetwork] = useState(false);
  const [qaQuestion, setQaQuestion] = useState("");
  const [qaScope, setQaScope] = useState<QAScope>("section");
  const [qaAllowNetwork, setQaAllowNetwork] = useState(false);
  const [keywordAllowNetwork, setKeywordAllowNetwork] = useState(false);
  const [expandedKeywords, setExpandedKeywords] = useState<string[]>([]);
  const [expandedResults, setExpandedResults] = useState<SearchHit[] | null>(
    null,
  );
  const [keywordRecordId, setKeywordRecordId] = useState<string | null>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">(
    "idle",
  );
  const client = useQueryClient();
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
    onSuccess: () => {
      setExpandedKeywords([]);
      setExpandedResults(null);
      setKeywordAllowNetwork(false);
      setKeywordRecordId(null);
    },
  });
  const keywordRecord = useQuery({
    queryKey: ["search-keywords", paperId, versionId, sectionId, query.trim()],
    queryFn: () => api.keyword(paperId, keywordRecordId as string),
    enabled: connected && Boolean(keywordRecordId),
    retry: false,
    refetchInterval: (current) =>
      current.state.data?.status === "PENDING" ? 800 : false,
  });
  const runExpandedSearch = useCallback(
    async (keywords: string[]) => {
      const cleaned = keywords.filter(Boolean).slice(0, 5);
      setExpandedKeywords(cleaned);
      setKeywordAllowNetwork(false);
      if (!cleaned.length) {
        setExpandedResults([]);
        return;
      }
      try {
        const results = await Promise.all(
          cleaned.map((keyword) =>
            api.search(paperId, keyword, versionId, sectionId || undefined),
          ),
        );
        const byChunk = new Map<string, SearchHit>();
        results.forEach((result) =>
          result.items.forEach((item) => byChunk.set(item.chunk_id, item)),
        );
        setExpandedResults([...byChunk.values()]);
      } catch {
        setExpandedResults(null);
      }
    },
    [paperId, sectionId, versionId],
  );
  const expandKeywords = useMutation({
    mutationFn: () =>
      api.expandSearchKeywords(paperId, {
        document_version_id: versionId,
        section_id: sectionId || undefined,
        question: query.trim(),
        allow_network: true,
      }),
    onSuccess: async (value) => {
      setKeywordRecordId(value.status === "PENDING" ? value.id : null);
      if (value.status === "COMPLETED" && value.keywords) {
        await runExpandedSearch(value.keywords.english_queries);
      }
    },
  });
  useEffect(() => {
    const value = keywordRecord.data;
    if (value?.status === "COMPLETED" && value.keywords) {
      const next = value.keywords.english_queries.filter(Boolean).slice(0, 5);
      if (next.join("\u0000") !== expandedKeywords.join("\u0000")) {
        // The query is an asynchronous external result; update local display
        // state only after React finishes the current effect pass.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        void runExpandedSearch(next);
      }
    }
  }, [expandedKeywords, keywordRecord.data, runExpandedSearch]);
  const selected = sections.data?.sections.find(
    (section) => section.id === sectionId,
  );
  const readable = Boolean(
    selected && !selected.excluded && selected.role !== "references",
  );
  const guide = useQuery({
    queryKey: ["section-guide", paperId, versionId, sectionId, depth],
    queryFn: () => api.sectionGuide(paperId, sectionId, versionId, depth),
    enabled: connected && readable,
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.status === "PENDING" ? 1200 : false,
  });
  const generateGuide = useMutation({
    mutationFn: () =>
      api.generateSectionGuide(
        paperId,
        sectionId,
        versionId,
        depth,
        true,
        guide.data?.status === "FAILED",
        guide.data?.status === "COMPLETED" || guide.data?.status === "STALE",
      ),
    onSuccess: (value) => {
      client.setQueryData(
        [
          "section-guide",
          value.paper_id,
          value.document_version_id,
          value.section_id,
          value.depth,
        ],
        value,
      );
      void client.invalidateQueries({ queryKey: ["lite-usage"] });
      setAllowNetwork(false);
    },
  });
  const guideText = guide.data?.guide ? formatGuide(guide.data.guide) : "";
  const qaHistory = useQuery({
    queryKey: ["paper-qa", paperId, versionId, sectionId, qaScope],
    queryFn: () =>
      api.qa
        ? api.qa(
            paperId,
            versionId,
            qaScope === "section" ? sectionId || undefined : undefined,
            qaScope,
          )
        : Promise.resolve([]),
    enabled: connected && Boolean(sectionId || qaScope === "paper"),
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.some((item) => item.status === "PENDING")
        ? 1200
        : false,
  });
  const currentQuestion = qaQuestion.trim();
  const latestQA = currentQuestion
    ? (qaHistory.data?.find((item) => item.question === currentQuestion) ??
      null)
    : null;
  const askQA = useMutation({
    mutationFn: () =>
      api.askQA(paperId, {
        document_version_id: versionId,
        section_id: qaScope === "section" ? sectionId || undefined : undefined,
        scope: qaScope,
        question: qaQuestion.trim(),
        allow_network: true,
      }),
    onSuccess: (value) => {
      client.setQueryData(
        ["paper-qa", paperId, versionId, sectionId, qaScope],
        (items: QAView[] | undefined) => [
          value,
          ...(items ?? []).filter((item) => item.id !== value.id),
        ],
      );
      void client.invalidateQueries({ queryKey: ["lite-usage"] });
      setQaAllowNetwork(false);
    },
  });
  const copyGuide = async () => {
    if (!guideText) return;
    try {
      await navigator.clipboard.writeText(guideText);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  };
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
              onChange={(e) => {
                setSectionId(e.target.value);
                setAllowNetwork(false);
                setQaAllowNetwork(false);
                setKeywordAllowNetwork(false);
                setExpandedKeywords([]);
                setExpandedResults(null);
                setCopyState("idle");
              }}
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
          <div className="section-directory" aria-label="章节目录">
            {sections.data.sections
              .filter(
                (section) => !section.excluded && section.role !== "references",
              )
              .map((section) => (
                <button
                  key={section.id}
                  type="button"
                  className={
                    section.id === sectionId
                      ? "section-link selected"
                      : "section-link"
                  }
                  aria-pressed={section.id === sectionId}
                  onClick={() => {
                    setSectionId(section.id);
                    setAllowNetwork(false);
                    setQaAllowNetwork(false);
                    setKeywordAllowNetwork(false);
                    setExpandedKeywords([]);
                    setExpandedResults(null);
                    setCopyState("idle");
                  }}
                >
                  <span
                    style={{
                      paddingLeft: `${Math.min(section.level, 5) * 12}px`,
                    }}
                  >
                    {section.title || `章节 ${section.ordinal + 1}`}
                  </span>
                </button>
              ))}
          </div>
          {selected && (
            <details key={selected.id} open>
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
          {selected && readable && (panel === "guide" || panel === "all") && (
            <section className="section-guide" aria-label="章节导读">
              <div className="section-guide-header">
                <div>
                  <h5>章节导读</h5>
                  <p className="muted">
                    只处理当前小节。切换章节只读取缓存状态，不会自动调用模型。
                  </p>
                </div>
                <span className="pill">
                  {guide.isPending
                    ? "正在读取状态…"
                    : guide.data?.status === "PENDING"
                      ? "正在生成…"
                      : guide.data?.status === "COMPLETED"
                        ? guide.data.cache_hit
                          ? "缓存命中"
                          : "已有导读"
                        : guide.data?.status === "STALE"
                          ? "版本已变化"
                          : guide.data?.status === "FAILED"
                            ? "生成失败"
                            : "尚未生成"}
                </span>
              </div>
              <div className="guide-controls">
                <label>
                  导读深度{" "}
                  <select
                    value={depth}
                    onChange={(e) => {
                      setDepth(e.target.value as GuideDepth);
                      setAllowNetwork(false);
                      setCopyState("idle");
                    }}
                  >
                    <option value="quick">快速</option>
                    <option value="standard">标准</option>
                    <option value="deep">深入</option>
                  </select>
                </label>
                <label className="consent-inline">
                  <input
                    type="checkbox"
                    checked={allowNetwork}
                    onChange={(e) => setAllowNetwork(e.target.checked)}
                  />
                  允许本次把当前小节发送给已配置模型
                </label>
                <button
                  type="button"
                  className="button primary"
                  disabled={
                    !connected ||
                    !allowNetwork ||
                    guide.isPending ||
                    generateGuide.isPending ||
                    guide.data?.status === "PENDING"
                  }
                  onClick={() => generateGuide.mutate()}
                >
                  {generateGuide.isPending || guide.data?.status === "PENDING"
                    ? "正在生成…"
                    : guide.data?.status === "COMPLETED"
                      ? "重新生成导读"
                      : "生成导读"}
                </button>
              </div>
              {guide.isError && (
                <p role="alert" className="error-text">
                  {guide.error.message}
                </p>
              )}
              {generateGuide.isError && (
                <p role="alert" className="error-text">
                  {generateGuide.error.message}
                </p>
              )}
              {guide.data?.error && guide.data.status === "FAILED" && (
                <p role="alert" className="error-text">
                  {guide.data.error}
                </p>
              )}
              {guide.data?.status === "STALE" && (
                <p className="quality-note">
                  当前导读来自旧文献版本，保留旧内容；请确认后重新生成当前版本。
                </p>
              )}
              {guide.data?.guide && (
                <GuideResult
                  guide={guide.data.guide}
                  evidence={guide.data.evidence}
                  onCopy={copyGuide}
                  copyState={copyState}
                />
              )}
            </section>
          )}
          {readable && (panel === "qa" || panel === "all") && (
            <section className="qa-panel" aria-label="局部证据问答">
              <div className="section-guide-header">
                <div>
                  <h5>局部证据问答</h5>
                  <p className="muted">
                    默认只检索当前小节的少量原文片段；回答必须引用这些片段，不会自动扩大范围。
                  </p>
                </div>
                <span className="pill">
                  {askQA.isPending || latestQA?.status === "PENDING"
                    ? "正在处理…"
                    : latestQA?.status === "COMPLETED"
                      ? latestQA.cache_hit
                        ? "缓存命中"
                        : "已有回答"
                      : latestQA?.status === "FAILED"
                        ? "回答失败"
                        : "尚未提问"}
                </span>
              </div>
              <form
                className="qa-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (
                    connected &&
                    qaQuestion.trim() &&
                    qaAllowNetwork &&
                    !askQA.isPending &&
                    latestQA?.status !== "PENDING"
                  ) {
                    askQA.mutate();
                  }
                }}
              >
                <label>
                  作用范围
                  <select
                    value={qaScope}
                    onChange={(event) => {
                      setQaScope(event.target.value as QAScope);
                      setQaAllowNetwork(false);
                    }}
                  >
                    <option value="section">当前小节</option>
                    <option value="paper">整篇论文（仍只发送少量片段）</option>
                    <option value="selection" disabled>
                      已选原文片段（请先选择 Span）
                    </option>
                  </select>
                </label>
                <label>
                  你的问题
                  <textarea
                    rows={3}
                    maxLength={3000}
                    value={qaQuestion}
                    placeholder="例如：这项方法在本节中解决了什么问题？"
                    disabled={!connected || askQA.isPending}
                    onChange={(event) => setQaQuestion(event.target.value)}
                  />
                </label>
                {qaQuestion.trim() && (
                  <label className="consent-inline">
                    <input
                      type="checkbox"
                      checked={qaAllowNetwork}
                      onChange={(event) =>
                        setQaAllowNetwork(event.target.checked)
                      }
                    />
                    允许本次把检索片段发送给已配置模型
                  </label>
                )}
                <button
                  type="submit"
                  className="button primary"
                  disabled={
                    !connected ||
                    !qaQuestion.trim() ||
                    !qaAllowNetwork ||
                    askQA.isPending ||
                    latestQA?.status === "PENDING"
                  }
                >
                  {askQA.isPending || latestQA?.status === "PENDING"
                    ? "正在回答…"
                    : latestQA?.status === "COMPLETED"
                      ? "再次提问"
                      : "提交问题"}
                </button>
              </form>
              {qaHistory.isError && (
                <p role="alert" className="error-text">
                  {qaHistory.error.message}
                </p>
              )}
              {askQA.isError && (
                <p role="alert" className="error-text">
                  {askQA.error.message}
                </p>
              )}
              {latestQA?.error && latestQA.status === "FAILED" && (
                <p role="alert" className="error-text">
                  {latestQA.error}
                </p>
              )}
              {latestQA?.answer && <QAResult qa={latestQA} />}
            </section>
          )}
        </>
      )}
      {(panel === "guide" || panel === "all") && (
        <>
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
                onChange={(e) => {
                  setQuery(e.target.value);
                  setKeywordAllowNetwork(false);
                  setExpandedKeywords([]);
                  setExpandedResults(null);
                }}
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
              {!search.data.items.length && (
                <KeywordExpansion
                  allowNetwork={keywordAllowNetwork}
                  pending={
                    expandKeywords.isPending ||
                    keywordRecord.data?.status === "PENDING"
                  }
                  keywords={
                    keywordRecord.data?.keywords?.english_queries ??
                    expandedKeywords
                  }
                  results={expandedResults}
                  onAllowNetwork={setKeywordAllowNetwork}
                  onGenerate={() => expandKeywords.mutate()}
                  error={
                    expandKeywords.error ??
                    (keywordRecord.data?.error
                      ? new Error(keywordRecord.data.error)
                      : null)
                  }
                />
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}

function KeywordExpansion({
  allowNetwork,
  pending,
  keywords,
  results,
  onAllowNetwork,
  onGenerate,
  error,
}: {
  allowNetwork: boolean;
  pending: boolean;
  keywords: string[];
  results: SearchHit[] | null;
  onAllowNetwork: (value: boolean) => void;
  onGenerate: () => void;
  error: Error | null;
}) {
  return (
    <section className="keyword-helper" aria-label="英文关键词辅助">
      <p className="quality-note">
        本地检索没有命中。可以让模型根据问题和当前章节标题生成少量英文关键词，再重新运行本地检索；不会用它回答科学问题。
      </p>
      <label className="consent-inline">
        <input
          type="checkbox"
          checked={allowNetwork}
          onChange={(event) => onAllowNetwork(event.target.checked)}
        />
        允许本次生成英文关键词
      </label>
      <button
        type="button"
        className="button secondary"
        disabled={!allowNetwork || pending}
        onClick={onGenerate}
      >
        {pending ? "正在生成关键词…" : "使用英文关键词辅助"}
      </button>
      {error && (
        <p role="alert" className="error-text">
          {error.message}
        </p>
      )}
      {keywords.length > 0 && (
        <p className="muted">关键词：{keywords.join(" · ")}</p>
      )}
      {results && (
        <section className="keyword-results" aria-label="英文关键词检索结果">
          <p>
            {results.length
              ? `英文关键词检索命中 ${results.length} 个片段`
              : "英文关键词也没有找到原文片段。"}
          </p>
          {results.map((hit) => (
            <article className="text-chunk" key={hit.chunk_id}>
              <header>
                PDF 第 {hit.page_index + 1} 页
                {hit.page_label ? ` · ${hit.page_label}` : ""}
              </header>
              <pre>{hit.text}</pre>
            </article>
          ))}
        </section>
      )}
    </section>
  );
}

function QAResult({ qa }: { qa: QAView }) {
  const cited = new Set(
    (qa.answer?.evidence_citations ?? []).map((citation) => citation.span_id),
  );
  return (
    <article className="qa-result">
      <h6>回答</h6>
      <p>{qa.answer?.answer_zh}</p>
      {qa.answer?.insufficient_evidence && (
        <p className="quality-note">
          当前范围的原文证据不足，不能据此确定答案。请先扩大作用范围后再提问；系统不会自动扩大或补造条件。
        </p>
      )}
      {qa.answer?.uncertainty_zh && (
        <p className="quality-note">{qa.answer.uncertainty_zh}</p>
      )}
      {qa.retrieval_spans.length > 0 && (
        <div className="guide-evidence">
          <h6>原文依据</h6>
          <ul>
            {qa.retrieval_spans.map((span) => {
              const citation = qa.answer?.evidence_citations.find(
                (item) => item.span_id === span.span_id,
              );
              return (
                <li key={span.span_id}>
                  <span className="mono">
                    {`PDF 第 ${span.page_start}${span.page_end !== span.page_start ? `–${span.page_end}` : ""} 页`}
                  </span>{" "}
                  <span>{span.quote}</span>
                  {cited.has(span.span_id) && citation && (
                    <small className="muted">（{citation.reason_zh}）</small>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {qa.answer?.suggest_expand_scope && !qa.answer.insufficient_evidence && (
        <p className="quality-note">
          模型认为更大范围可能有帮助，请由你决定是否切换作用范围。
        </p>
      )}
    </article>
  );
}

function formatGuide(guide: ReadingGuide): string {
  const lines = [
    `章节导读（${guide.section_id}）`,
    "",
    guide.overview_zh,
    "",
    "重点：",
    ...guide.key_points.map((item) => `- ${item}`),
    "",
    "阅读问题：",
    ...guide.reading_questions.map((item) => `- ${item}`),
  ];
  if (guide.difficult_terms.length) {
    lines.push(
      "",
      "困难术语：",
      ...guide.difficult_terms.map(
        (item) => `- ${item.term_en}：${item.hint_zh}`,
      ),
    );
  }
  if (guide.caveats.length)
    lines.push("", "限制：", ...guide.caveats.map((item) => `- ${item}`));
  if (guide.evidence_span_ids.length) {
    lines.push("", `原文依据 Span：${guide.evidence_span_ids.join(", ")}`);
  }
  return lines.join("\n");
}

function GuideResult({
  guide,
  evidence,
  onCopy,
  copyState,
}: {
  guide: ReadingGuide;
  evidence: {
    span_id: string;
    page_start: number;
    page_end: number;
    quote: string;
  }[];
  onCopy: () => void;
  copyState: "idle" | "copied" | "failed";
}) {
  return (
    <article className="guide-result">
      <div className="guide-result-actions">
        <strong>导读结果</strong>
        <button type="button" className="button secondary" onClick={onCopy}>
          复制导读
        </button>
        {copyState === "copied" && <span className="muted">已复制</span>}
        {copyState === "failed" && (
          <span className="error-text">复制失败，请手动选择文本</span>
        )}
      </div>
      <p>{guide.overview_zh}</p>
      <h6>重点</h6>
      <ul>
        {guide.key_points.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      <h6>阅读问题</h6>
      <ul>
        {guide.reading_questions.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      {guide.difficult_terms.length > 0 && (
        <>
          <h6>困难术语</h6>
          <ul>
            {guide.difficult_terms.map((item) => (
              <li key={item.term_en}>
                <strong>{item.term_en}</strong>：{item.hint_zh}
              </li>
            ))}
          </ul>
        </>
      )}
      {guide.evidence_span_ids.length > 0 && (
        <div className="guide-evidence">
          <h6>原文位置</h6>
          <ul>
            {guide.evidence_span_ids.map((spanId) => {
              const item = evidence.find(
                (candidate) => candidate.span_id === spanId,
              );
              return (
                <li key={spanId}>
                  <span className="mono">
                    {item
                      ? `PDF 第 ${item.page_start}${item.page_end !== item.page_start ? `–${item.page_end}` : ""} 页`
                      : "原文 Span"}
                  </span>{" "}
                  <span>{item?.quote || spanId}</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {guide.needs_more_context && (
        <p className="quality-note">
          当前导读需要更多上下文，不能据此补造缺失内容。
        </p>
      )}
      {guide.caveats.length > 0 && (
        <ul className="quality-note">
          {guide.caveats.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </article>
  );
}
