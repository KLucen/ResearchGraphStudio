import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  type QAScope,
  type SearchHit,
  type QAView,
  type ReadingParagraph,
  type Section,
  type Structure,
} from "./api";
import { PaperCloseReading } from "./PaperCloseReading";
import { ReadingOutline } from "./ReadingOutline";

const sectionTargetId = (id: string) => `reading-section-${id || "all"}`;
type DirectoryNotice = { sectionId: string; spanKey: string };
type LocalSearchScope = { sectionId: string; query: string; epoch: number };

type KnowledgeReadingProps = {
  versionId: string;
  paperId: string;
  connected: boolean;
  panel?: "guide" | "qa" | "all";
  initialSectionId?: string;
  initialParagraphId?: string;
  selectedSpanIds?: string[];
  onSectionChange?: (sectionId: string) => void;
  onOpenGraph?: (nodeId: string) => void;
  onAskParagraph?: (sectionId: string, paragraph: ReadingParagraph) => void;
};

export function KnowledgeReading(props: KnowledgeReadingProps) {
  if (props.panel === "guide") {
    return (
      <PaperCloseReading
        key={`${props.paperId}:${props.versionId}`}
        paperId={props.paperId}
        revisionId={props.versionId}
        connected={props.connected}
        initialParagraphId={props.initialParagraphId}
        onOpenGraph={props.onOpenGraph}
        onAskParagraph={props.onAskParagraph}
      />
    );
  }
  return <LegacyKnowledgeReading {...props} />;
}

function LegacyKnowledgeReading({
  versionId,
  paperId,
  connected,
  panel = "all",
  initialSectionId = "",
  selectedSpanIds = [],
  onSectionChange,
}: {
  versionId: string;
  paperId: string;
  connected: boolean;
  panel?: "guide" | "qa" | "all";
  initialSectionId?: string;
  initialParagraphId?: string;
  selectedSpanIds?: string[];
  onSectionChange?: (sectionId: string) => void;
  onOpenGraph?: (nodeId: string) => void;
  onAskParagraph?: (sectionId: string, paragraph: ReadingParagraph) => void;
}) {
  const client = useQueryClient();
  const [directoryNotice, setDirectoryNotice] =
    useState<DirectoryNotice | null>(
      () =>
        client.getQueryData(["reading-directory-notice", paperId, versionId]) ??
        null,
    );
  const [blockedSpanKey, setBlockedSpanKey] = useState<string | null>(
    directoryNotice?.spanKey ?? null,
  );
  const selectedSpanKey = selectedSpanIds.join(",");
  const usableSpanIds =
    blockedSpanKey === selectedSpanKey ? [] : selectedSpanIds;
  const [query, setQuery] = useState("");
  const [sectionId, setSectionId] = useState(initialSectionId);
  const [qaQuestion, setQaQuestion] = useState("");
  const [qaScope, setQaScope] = useState<QAScope>(
    usableSpanIds.length ? "selection" : "section",
  );
  const [qaAllowNetwork, setQaAllowNetwork] = useState(false);
  const [keywordAllowNetwork, setKeywordAllowNetwork] = useState(false);
  const [expandedKeywords, setExpandedKeywords] = useState<string[]>([]);
  const [expandedResults, setExpandedResults] = useState<SearchHit[] | null>(
    null,
  );
  const [keywordRecordId, setKeywordRecordId] = useState<string | null>(null);
  const searchEpoch = useRef(0);
  const sections = useQuery({
    queryKey: ["sections", versionId],
    queryFn: () => api.sections(versionId, { includeText: false }),
    enabled: connected,
    retry: false,
  });
  const selected = sections.data?.sections.find(
    (section) => section.id === sectionId,
  );
  const readable = Boolean(
    selected && !selected.excluded && selected.role !== "references",
  );
  const currentSectionExists = useCallback(
    (id: string, requireReadable = false) =>
      client
        .getQueryData<Structure>(["sections", versionId])
        ?.sections.some(
          (section) =>
            section.id === id &&
            (!requireReadable ||
              (!section.excluded && section.role !== "references")),
        ) ?? false,
    [client, versionId],
  );
  const search = useMutation({
    mutationFn: (input: LocalSearchScope) => {
      if (input.sectionId && !currentSectionExists(input.sectionId))
        throw new Error("章节目录已更新，请重新选择当前章节后搜索。");
      return api.search(
        paperId,
        input.query,
        versionId,
        input.sectionId || undefined,
      );
    },
    retry: false,
    onSuccess: (_value, input) => {
      if (input.epoch !== searchEpoch.current) return;
      setExpandedKeywords([]);
      setExpandedResults(null);
      setKeywordAllowNetwork(false);
      setKeywordRecordId(null);
    },
  });
  const keywordRecord = useQuery({
    queryKey: ["search-keywords", paperId, versionId, sectionId, query.trim()],
    queryFn: () => api.keyword(paperId, keywordRecordId as string),
    enabled:
      connected &&
      Boolean(keywordRecordId) &&
      (!sectionId || Boolean(selected)),
    retry: false,
    refetchInterval: (current) =>
      current.state.data?.status === "PENDING" ? 800 : false,
  });
  const runExpandedSearch = useCallback(
    async (keywords: string[], input: LocalSearchScope) => {
      if (
        input.epoch !== searchEpoch.current ||
        (input.sectionId && !currentSectionExists(input.sectionId))
      )
        return;
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
            api.search(
              paperId,
              keyword,
              versionId,
              input.sectionId || undefined,
            ),
          ),
        );
        const byChunk = new Map<string, SearchHit>();
        results.forEach((result) =>
          result.items.forEach((item) => byChunk.set(item.chunk_id, item)),
        );
        if (
          input.epoch !== searchEpoch.current ||
          (input.sectionId && !currentSectionExists(input.sectionId))
        )
          return;
        setExpandedResults([...byChunk.values()]);
      } catch {
        if (input.epoch === searchEpoch.current) setExpandedResults(null);
      }
    },
    [paperId, versionId, currentSectionExists],
  );
  const expandKeywords = useMutation({
    mutationFn: (input: LocalSearchScope) => {
      if (input.sectionId && !currentSectionExists(input.sectionId))
        throw new Error("章节目录已更新，请重新选择当前章节并确认本次授权。");
      return api.expandSearchKeywords(paperId, {
        document_version_id: versionId,
        section_id: input.sectionId || undefined,
        question: input.query,
        allow_network: true,
      });
    },
    onSuccess: async (value, input) => {
      if (
        input.epoch !== searchEpoch.current ||
        value.section_id !== (input.sectionId || null) ||
        value.document_version_id !== versionId ||
        value.question !== input.query ||
        (value.section_id && !currentSectionExists(value.section_id))
      )
        return;
      setKeywordRecordId(value.status === "PENDING" ? value.id : null);
      if (value.status === "COMPLETED" && value.keywords) {
        await runExpandedSearch(value.keywords.english_queries, input);
      }
    },
  });
  useEffect(() => {
    const value = keywordRecord.data;
    if (
      value?.status === "COMPLETED" &&
      value.keywords &&
      keywordRecordId &&
      value.section_id === (sectionId || null) &&
      value.question === query.trim() &&
      (!value.section_id || currentSectionExists(value.section_id))
    ) {
      const next = value.keywords.english_queries.filter(Boolean).slice(0, 5);
      if (next.join("\u0000") !== expandedKeywords.join("\u0000")) {
        // The query is an asynchronous external result; update local display
        // state only after React finishes the current effect pass.
        void runExpandedSearch(next, {
          sectionId,
          query: query.trim(),
          epoch: searchEpoch.current,
        });
      }
    }
  }, [
    expandedKeywords,
    keywordRecord.data,
    keywordRecordId,
    runExpandedSearch,
    sectionId,
    query,
    currentSectionExists,
  ]);
  const qaHistory = useQuery({
    queryKey: [
      "paper-qa",
      paperId,
      versionId,
      sectionId,
      qaScope,
      usableSpanIds.join(","),
    ],
    queryFn: () =>
      api.qa
        ? api.qa(
            paperId,
            versionId,
            qaScope !== "paper" ? sectionId || undefined : undefined,
            qaScope,
          )
        : Promise.resolve([]),
    enabled: connected && readable,
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.some((item) => item.status === "PENDING")
        ? 1200
        : false,
  });
  const currentQuestion = qaQuestion.trim();
  const latestQA = currentQuestion
    ? (qaHistory.data?.find(
        (item) =>
          item.question === currentQuestion &&
          (qaScope !== "selection" ||
            (item.retrieval_spans.length === usableSpanIds.length &&
              item.retrieval_spans.every((span) =>
                usableSpanIds.includes(span.span_id),
              ))),
      ) ?? null)
    : null;
  const askQA = useMutation({
    mutationFn: (input: {
      sectionId: string;
      scope: QAScope;
      spanIds: string[];
      question: string;
    }) => {
      if (
        !input.sectionId ||
        !currentSectionExists(input.sectionId, true) ||
        (input.scope === "selection" && !input.spanIds.length)
      )
        throw new Error(
          "章节目录已更新，请重新选择正文小节或原文段落并确认本次授权。",
        );
      return api.askQA(paperId, {
        document_version_id: versionId,
        section_id: input.scope !== "paper" ? input.sectionId : undefined,
        scope: input.scope,
        question: input.question,
        ...(input.scope === "selection"
          ? { selection_span_ids: input.spanIds }
          : {}),
        allow_network: true,
      });
    },
    onSuccess: (value, input) => {
      client.setQueryData(
        [
          "paper-qa",
          value.paper_id,
          value.document_version_id,
          input.sectionId,
          input.scope,
          input.spanIds.join(","),
        ],
        (items: QAView[] | undefined) => [
          value,
          ...(items ?? []).filter((item) => item.id !== value.id),
        ],
      );
      void client.invalidateQueries({ queryKey: ["lite-usage"] });
      setQaAllowNetwork(false);
    },
  });
  const resetSearch = search.reset;
  const resetExpansion = expandKeywords.reset;
  const resetQA = askQA.reset;
  useEffect(() => {
    if (!sections.isSuccess || !sectionId || selected) return;
    const notice = { sectionId, spanKey: selectedSpanKey };
    searchEpoch.current += 1;
    client.setQueryData(
      ["reading-directory-notice", paperId, versionId],
      notice,
    );
    // A successful local directory refresh invalidates this selected identity;
    // clear its consent instead of silently sending it under a new chapter.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDirectoryNotice(notice);
    setBlockedSpanKey(selectedSpanKey);
    setSectionId("");
    setQaAllowNetwork(false);
    setKeywordAllowNetwork(false);
    setQaScope("section");
    setQuery("");
    setExpandedKeywords([]);
    setExpandedResults(null);
    setKeywordRecordId(null);
    resetSearch();
    resetExpansion();
    resetQA();
    onSectionChange?.("");
  }, [
    sections.isSuccess,
    sectionId,
    selected,
    selectedSpanKey,
    client,
    paperId,
    versionId,
    onSectionChange,
    resetSearch,
    resetExpansion,
    resetQA,
  ]);

  const chooseSection = (id: string) => {
    searchEpoch.current += 1;
    setSectionId(id);
    setDirectoryNotice(null);
    client.setQueryData(["reading-directory-notice", paperId, versionId], null);
    onSectionChange?.(id);
    setQaAllowNetwork(false);
    setKeywordAllowNetwork(false);
    setExpandedKeywords([]);
    setExpandedResults(null);
    setKeywordRecordId(null);
    resetSearch();
    resetExpansion();
  };
  return (
    <section className="knowledge-area" aria-label="章节与本地索引">
      <h4>章节与本地索引</h4>
      <p className="muted">章节识别和原文搜索在本机完成，不调用模型。</p>
      {sections.isPending && connected && <p role="status">正在读取章节…</p>}
      {sections.isError && (
        <div role="alert" className="error-text">
          <p>章节目录读取失败。{sections.error.message}</p>
          <button
            className="text-button"
            onClick={() => void sections.refetch()}
          >
            重新读取目录
          </button>
        </div>
      )}
      {directoryNotice && (
        <p role="status" className="quality-note">
          章节目录已更新，原先选择的章节已不在当前目录中，已清除章节选择和本次模型授权。请从当前目录重新选择正文小节。
          历史图谱或链接可能指向旧解析；当前入口无法定位该历史章节，不会自动将其归入新章节。
        </p>
      )}
      {sections.data && (
        <ReadingOutline
          key={`${paperId}:${versionId}:${panel}`}
          entries={sections.data.sections
            .filter(
              (section) => !section.excluded && section.role !== "references",
            )
            .map((section) => ({
              id: section.id,
              label: section.title || `章节 ${section.ordinal + 1}`,
              targetId: sectionTargetId(section.id),
              level: section.level,
              parentId: section.parent_id,
              detail:
                section.start_page === null
                  ? undefined
                  : `PDF 第 ${section.start_page + 1} 页`,
            }))}
          activeId={sectionId}
          onSelect={chooseSection}
          controls={
            <label>
              选择章节
              <select
                value={sectionId}
                onChange={(event) => chooseSection(event.target.value)}
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
          }
        >
          <div
            id={sectionTargetId(sectionId)}
            className="reading-outline-section"
            tabIndex={-1}
          >
            <p role="status">
              本地索引已就绪：{sections.data.sections.length} 个章节。
            </p>
            {selected && (
              <SectionTextPreview
                key={selected.id}
                section={selected}
                versionId={versionId}
                connected={connected}
              />
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
                      askQA.mutate({
                        sectionId,
                        scope: qaScope,
                        spanIds: [...usableSpanIds],
                        question: qaQuestion.trim(),
                      });
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
                      <option value="paper">
                        整篇论文（仍只发送少量片段）
                      </option>
                      <option
                        value="selection"
                        disabled={!usableSpanIds.length}
                      >
                        {usableSpanIds.length
                          ? "已选段落原文"
                          : "已选原文片段（请先在双栏精读选择段落）"}
                      </option>
                    </select>
                  </label>
                  {qaScope === "selection" && (
                    <p className="quality-note">
                      当前仅使用从双栏精读选中的段落，共 {usableSpanIds.length}{" "}
                      个原文 Span。提交前不会自动扩大范围。
                    </p>
                  )}
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
          </div>
        </ReadingOutline>
      )}
      {panel === "all" && (
        <>
          <form
            className="import-controls"
            onSubmit={(e) => {
              e.preventDefault();
              if (connected && query.trim())
                search.mutate({
                  sectionId,
                  query: query.trim(),
                  epoch: searchEpoch.current,
                });
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
                  searchEpoch.current += 1;
                  setQuery(e.target.value);
                  setKeywordAllowNetwork(false);
                  setExpandedKeywords([]);
                  setExpandedResults(null);
                  setKeywordRecordId(null);
                  resetSearch();
                  resetExpansion();
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
                  onGenerate={() =>
                    expandKeywords.mutate({
                      sectionId,
                      query: query.trim(),
                      epoch: searchEpoch.current,
                    })
                  }
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

function SectionTextPreview({
  section,
  versionId,
  connected,
}: {
  section: Section;
  versionId: string;
  connected: boolean;
}) {
  const [open, setOpen] = useState(false);
  const preview = useQuery({
    queryKey: ["section-text", versionId, section.id],
    queryFn: async () => {
      const result = await api.sections(versionId, { sectionId: section.id });
      if (
        result.document_version_id !== versionId ||
        result.sections.length !== 1 ||
        result.sections[0]?.id !== section.id
      ) {
        throw new Error("章节与当前目录不一致，请重新读取目录。");
      }
      return result.sections[0].text;
    },
    enabled: connected && open,
    retry: false,
  });
  return (
    <details onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>{section.title} · 查看章节原文</summary>
      {section.start_page !== null && (
        <p className="muted">
          PDF 第 {section.start_page + 1} 页
          {section.end_page !== null && section.end_page !== section.start_page
            ? ` 至第 ${section.end_page + 1} 页`
            : ""}
        </p>
      )}
      {open && preview.isPending && connected && (
        <p role="status">正在读取所选章节的原文…</p>
      )}
      {open && preview.isError && (
        <div role="alert" className="error-text">
          <p>{preview.error.message}</p>
          <button
            className="text-button"
            disabled={!connected}
            onClick={() => void preview.refetch()}
          >
            重新读取原文
          </button>
        </div>
      )}
      {preview.isSuccess && (
        <pre className="section-text" data-reading-anchor>
          {preview.data || "此章节没有可提取文本。"}
        </pre>
      )}
    </details>
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
