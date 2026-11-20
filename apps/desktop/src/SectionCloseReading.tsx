import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  type ConceptUnderstanding,
  type GuideUsage,
  type ParagraphAnalysis,
  type ReadingParagraph,
  type ReadingState,
  type SectionReadingAnalysis,
  type SelfAssessment,
} from "./api";
import { highlightSegments, readingHighlightTypes } from "./readingHighlights";
import "./readingHighlights.css";
import "./sectionCloseReading.css";

const functions = {
  INTRODUCE_PROBLEM: "提出问题",
  DEFINE_CONCEPT: "定义概念",
  STATE_CLAIM: "陈述论点",
  EXPLAIN_METHOD: "解释方法",
  PRESENT_EVIDENCE: "呈现论据",
  HANDLE_OBJECTION: "回应异议",
  DISCUSS_LIMITATION: "讨论局限",
  SUMMARIZE_TRANSITION: "总结与过渡",
  OTHER: "其他",
};
export const assessmentLabels: Record<SelfAssessment, string> = {
  UNSET: "尚未自评",
  UNSURE: "还不确定",
  PARTIAL: "部分理解",
  CONFIDENT: "自认为已理解",
};
export const checkLabels = {
  NOT_CHECKED: "尚未检查",
  ADEQUATE: "复述充分",
  PARTIAL: "仍有遗漏",
  MISCONCEPTION: "可能存在误解",
  UNCERTAIN: "依据不足，无法确定",
};
const statusLabels = {
  PENDING: "正在生成",
  COMPLETED: "已完成",
  INCOMPLETE: "部分完成",
  FAILED: "生成失败",
  STALE: "内容或配置已变化",
};
type Props = {
  paperId: string;
  revisionId: string;
  sectionId: string;
  title: string;
  connected: boolean;
  onOpenGraph?: (nodeId: string) => void;
  onAskParagraph?: (paragraph: ReadingParagraph) => void;
  initialParagraphId?: string;
  historyOnly?: boolean;
};

export function SectionCloseReading(props: Props) {
  const paragraphs = useQuery({
    queryKey: [
      "reading-paragraphs",
      props.paperId,
      props.revisionId,
      props.sectionId,
    ],
    queryFn: () =>
      api.sectionParagraphs(props.paperId, props.sectionId, props.revisionId),
    enabled: props.connected,
    retry: false,
  });
  return (
    <section className="close-reading" aria-label="双栏精读">
      {paragraphs.isPending && <p role="status">正在读取本地段落…</p>}
      {paragraphs.isError && (
        <p role="alert" className="error-text">
          {paragraphs.error.message}
          <button
            className="text-button"
            onClick={() => void paragraphs.refetch()}
          >
            重试读取段落
          </button>
        </p>
      )}
      {paragraphs.data && (
        <CloseReadingSession
          key={`${props.revisionId}:${props.sectionId}:${paragraphs.data.source_hash}`}
          {...props}
          paragraphs={paragraphs.data.paragraphs}
        />
      )}
    </section>
  );
}

function CloseReadingSession({
  paperId,
  revisionId,
  sectionId,
  title,
  connected,
  paragraphs,
  onOpenGraph,
  onAskParagraph,
  initialParagraphId,
  historyOnly = false,
}: Props & { paragraphs: ReadingParagraph[] }) {
  const initialIndex = Math.max(
    0,
    paragraphs.findIndex((p) => p.paragraph_id === initialParagraphId),
  );
  const [start, setStart] = useState(initialParagraphId ? initialIndex : 0);
  const [end, setEnd] = useState(
    initialParagraphId ? initialIndex : paragraphs.length - 1,
  );
  const [allowNetwork, setAllowNetwork] = useState(false);
  const [repairId, setRepairId] = useState("");
  const [activeParagraph, setActiveParagraph] = useState(
    initialParagraphId ?? "",
  );
  const client = useQueryClient();
  const selected = paragraphs.slice(start, end + 1);
  const ids = selected.map((p) => p.paragraph_id);
  const scope = ids.join(",");
  const queryKey = ["close-reading", paperId, revisionId, sectionId, scope];
  const analysis = useQuery({
    queryKey,
    queryFn: () => api.closeReading(paperId, sectionId, revisionId, ids),
    enabled: connected && ids.length > 0,
    retry: false,
    refetchInterval: (current) =>
      current.state.data?.status === "PENDING" ? 1200 : false,
  });
  const concepts = useQuery({
    queryKey: ["concept-understanding", paperId, revisionId],
    queryFn: () => api.conceptUnderstanding(paperId, revisionId),
    enabled: connected,
    retry: false,
  });
  useEffect(() => {
    if (!analysis.data?.status || analysis.data.status === "PENDING") return;
    void client.invalidateQueries({ queryKey: ["lite-usage"] });
    void client.invalidateQueries({ queryKey: ["jobs"] });
    void client.invalidateQueries({
      queryKey: ["concept-understanding", paperId, revisionId],
    });
  }, [client, paperId, revisionId, analysis.data?.status]);
  const repair = useQuery({
    queryKey: [
      "close-reading-repair",
      paperId,
      revisionId,
      sectionId,
      repairId,
    ],
    queryFn: () =>
      api.closeReading(paperId, sectionId, revisionId, [], repairId),
    enabled: connected && !!repairId,
    retry: false,
    refetchInterval: (q) => (q.state.data?.status === "PENDING" ? 1000 : false),
  });
  useEffect(() => {
    if (!repairId || !repair.data?.status || repair.data.status === "PENDING")
      return;
    void client.invalidateQueries({
      queryKey: ["close-reading", paperId, revisionId, sectionId],
    });
    void client.invalidateQueries({ queryKey: ["lite-usage"] });
    void client.invalidateQueries({
      queryKey: ["concept-understanding", paperId, revisionId],
    });
  }, [client, paperId, revisionId, sectionId, repairId, repair.data?.status]);
  const generate = useMutation({
    mutationFn: (missingOnly: boolean) =>
      api.generateCloseReading(paperId, sectionId, {
        document_version_id: revisionId,
        paragraph_ids: missingOnly
          ? (analysis.data?.missing_paragraph_ids ?? [])
          : ids,
        allow_network: true,
        ...(missingOnly && analysis.data?.id
          ? { retry_missing_of: analysis.data.id }
          : {
              force_regenerate: !!analysis.data?.id,
            }),
      }),
    retry: false,
    onSuccess: (value, missingOnly) => {
      if (missingOnly && value.id) setRepairId(value.id);
      else client.setQueryData(queryKey, value);
      setAllowNetwork(false);
      void client.invalidateQueries({ queryKey: ["lite-usage"] });
      void client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
  const pending =
    generate.isPending ||
    analysis.data?.status === "PENDING" ||
    (!!repairId && repair.isPending) ||
    repair.data?.status === "PENDING";
  const current =
    analysis.data?.status === "STALE" ? null : analysis.data?.analysis;
  const byId = new Map(
    (current?.paragraphs ?? []).map((p) => [p.paragraph_id, p]),
  );
  const fullSection = start === 0 && end === paragraphs.length - 1;
  const rangeLabel = fullSection
    ? "当前完整小节"
    : `所选第 ${start + 1}–${end + 1} 段`;
  const estimate = selected.reduce(
    (sum, p) => sum + estimateReadingSource(p.text_en),
    0,
  );
  const currentConcepts =
    concepts.data?.filter((c) => c.association_status === "CURRENT") ?? [];
  const stateKey = ["reading-state", paperId, revisionId, sectionId];
  const state = useQuery({
    queryKey: stateKey,
    queryFn: () => api.readingState(paperId, sectionId, revisionId),
    enabled: connected,
    retry: false,
  });
  const saveState = useMutation({
    mutationFn: (patch: Partial<ReadingState>) => {
      if (!state.data) throw new Error("请先读取阅读状态");
      const value = { ...state.data, ...patch };
      return api.saveReadingState(paperId, sectionId, {
        document_version_id: revisionId,
        progress: value.progress,
        self_assessment: value.self_assessment,
        unresolved_concept_ids: value.unresolved_concept_ids,
        questions: value.questions,
        ...(value.overview_result_id
          ? { overview_result_id: value.overview_result_id }
          : {}),
      });
    },
    retry: false,
    onSuccess: (value) => {
      client.setQueryData(stateKey, value);
      void client.invalidateQueries({
        queryKey: ["concept-understanding", paperId, revisionId],
      });
    },
  });
  const recordQuestion = (paragraphId: string, text: string) => {
    if (
      !state.data ||
      state.data.questions.some(
        (q) => q.paragraph_id === paragraphId && q.text === text,
      )
    )
      return;
    saveState.mutate({
      questions: [
        ...state.data.questions,
        { paragraph_id: paragraphId, text, resolved: false },
      ],
    });
  };
  return (
    <>
      <header className="close-reading-heading">
        <div>
          <div className="eyebrow">CLOSE READING</div>
          <h4>{title}</h4>
          <p className="muted">
            {historyOnly
              ? "查看已有小节精读、保存个人状态，或主动提交理解检查。新笔记请在全文精读中生成。"
              : "逐段阅读英文与常驻译文，沿着右栏批注梳理论证。"}
          </p>
        </div>
        <span className="pill">
          {analysis.data?.cache_hit
            ? "缓存命中 · 新增调用 0"
            : analysis.data?.status
              ? statusLabels[analysis.data.status]
              : "本地原文已就绪"}
        </span>
      </header>
      {!paragraphs.length ? (
        <p className="quality-note">
          本小节没有可用段落，请核对 PDF 本地解析结果。
        </p>
      ) : (
        <>
          <div className="close-reading-toolbar">
            <div className="reading-range">
              <strong>阅读范围</strong>
              <label>
                从第
                <select
                  aria-label="起始段落"
                  value={start}
                  disabled={pending}
                  onChange={(e) => {
                    const value = Number(e.target.value);
                    setStart(value);
                    if (value > end) setEnd(value);
                    setAllowNetwork(false);
                  }}
                >
                  {paragraphs.map((p, i) => (
                    <option key={p.paragraph_id} value={i}>
                      {i + 1} 段
                    </option>
                  ))}
                </select>
              </label>
              <label>
                至第
                <select
                  aria-label="结束段落"
                  value={end}
                  disabled={pending}
                  onChange={(e) => {
                    const value = Number(e.target.value);
                    setEnd(value);
                    if (value < start) setStart(value);
                    setAllowNetwork(false);
                  }}
                >
                  {paragraphs.map((p, i) => (
                    <option key={p.paragraph_id} value={i}>
                      {i + 1} 段
                    </option>
                  ))}
                </select>
              </label>
              <span className="muted">
                {selected.length} / {paragraphs.length} 段
              </span>
            </div>
            {!historyOnly && (
              <div className="reading-generation">
                <label className="consent-inline">
                  <input
                    type="checkbox"
                    checked={allowNetwork}
                    onChange={(e) => setAllowNetwork(e.target.checked)}
                  />
                  允许本次发送所选段落，生成译文和批注
                </label>
                <button
                  className="button primary"
                  disabled={
                    !connected ||
                    !allowNetwork ||
                    pending ||
                    analysis.isPending ||
                    estimate > 2000 ||
                    ids.length > 100
                  }
                  onClick={() => generate.mutate(false)}
                >
                  {pending
                    ? "正在生成双栏精读…"
                    : analysis.data?.status === "COMPLETED"
                      ? "重新生成所选范围"
                      : "生成双栏精读"}
                </button>
                {analysis.data?.status === "INCOMPLETE" &&
                  analysis.data.missing_paragraph_ids.length > 0 && (
                    <button
                      className="button secondary"
                      disabled={!connected || !allowNetwork || pending}
                      onClick={() => generate.mutate(true)}
                    >
                      仅重试缺失的 {analysis.data.missing_paragraph_ids.length}{" "}
                      段
                    </button>
                  )}
              </div>
            )}
            {!historyOnly && (
              <p className="reading-cost muted">
                {rangeLabel} · 原文约 {estimate.toLocaleString()} 输入
                Token（字符估算，另有提示词开销）；输出包含中文译文和批注，以模型实际返回用量为准。长小节可手动缩小范围。
              </p>
            )}
            {!historyOnly && (estimate > 2000 || ids.length > 100) && (
              <p className="quality-note">
                当前范围超过单次精读预算（原文约 2,000 Token /
                最多100段），请手动选择更少段落；系统不会自动处理其余范围。
              </p>
            )}
            {analysis.data?.estimated && (
              <p className="reading-cost muted">
                此范围后端估算：输入{" "}
                {analysis.data.estimated.estimated_input_tokens} · 输出{" "}
                {analysis.data.estimated.estimated_output_tokens} · 合计{" "}
                {analysis.data.estimated.estimated_total_tokens}{" "}
                Token（估算值，不计为真实用量）。
              </p>
            )}
          </div>
          <div className="reading-legend" aria-label="论证标注图例">
            {Object.entries(readingHighlightTypes).map(([type, appearance]) => (
              <span key={type}>
                <i style={{ background: appearance.color }} />
                {appearance.label}
              </span>
            ))}
            <small>重叠片段按图例顺序优先显示</small>
          </div>
          {analysis.isError && (
            <p role="alert" className="error-text">
              {analysis.error.message}
            </p>
          )}
          {generate.isError && (
            <p role="alert" className="error-text">
              {generate.error.message}
            </p>
          )}
          {analysis.data?.error && (
            <p role="alert" className="error-text">
              {analysis.data.error_code} · {analysis.data.error}
            </p>
          )}
          {analysis.data?.status === "STALE" && (
            <p className="quality-note">
              原文或生成配置已变化，旧结果已保留。当前范围需重新生成译文与批注。
            </p>
          )}
          {analysis.data?.status === "INCOMPLETE" && !historyOnly && (
            <p role="status" className="quality-note">
              当前结果不完整：已校验段落可以继续阅读，缺失段落的译文保留占位。点击“仅重试缺失”后只处理未完成段落。
            </p>
          )}
          {!!analysis.data?.warnings?.length && (
            <details className="reading-warnings">
              <summary>校验提示（{analysis.data.warnings.length}）</summary>
              <ul>
                {analysis.data.warnings.map((warning, i) => (
                  <li key={i}>{warning}</li>
                ))}
              </ul>
            </details>
          )}
          <div className="close-reading-columns">
            <strong>英文原文与中文译文</strong>
            <strong>中文论证批注</strong>
          </div>
          <div className="reading-paragraphs">
            {selected.map((paragraph) => (
              <BilingualParagraph
                key={paragraph.paragraph_id}
                paragraph={paragraph}
                analysis={byId.get(paragraph.paragraph_id)}
                pending={pending}
                stale={analysis.data?.status === "STALE"}
                active={activeParagraph === paragraph.paragraph_id}
                onActive={() => setActiveParagraph(paragraph.paragraph_id)}
                onAsk={
                  onAskParagraph ? () => onAskParagraph(paragraph) : undefined
                }
                onOpenGraph={onOpenGraph}
                concepts={currentConcepts}
                onRecordQuestion={(text) =>
                  recordQuestion(paragraph.paragraph_id, text)
                }
                stateReady={!!state.data && !saveState.isPending}
              />
            ))}
          </div>
          {current?.section_argument && (
            <ArgumentSummary
              argument={current.section_argument}
              label={
                fullSection && analysis.data?.status === "COMPLETED"
                  ? "小节论证结构"
                  : "所选范围论证结构"
              }
              incomplete={analysis.data?.status === "INCOMPLETE"}
            />
          )}
          {analysis.data?.usage && (
            <UsageNote
              usage={analysis.data.usage}
              cacheHit={analysis.data.cache_hit}
            />
          )}
          <ReadingStatePanel
            value={state.data}
            error={state.error ?? saveState.error}
            pending={saveState.isPending}
            concepts={currentConcepts}
            onChange={(patch) => saveState.mutate(patch)}
          />
          <UnderstandingCheck
            key={scope}
            paperId={paperId}
            revisionId={revisionId}
            sectionId={sectionId}
            paragraphIds={ids}
            connected={connected}
            concepts={currentConcepts}
          />
        </>
      )}
      {analysis.data?.status === "STALE" && analysis.data.analysis && (
        <details className="reading-old-draft">
          <summary>查看旧版本译文与批注（不与当前原文对齐）</summary>
          <p className="quality-note">
            这些内容属于原有记录，当前内容或配置校验已失效。下方仅展示旧稿，不用于标注当前英文原文。
          </p>
          {analysis.data.analysis.paragraphs.map((paragraph) => (
            <article key={paragraph.paragraph_id}>
              <small className="muted">旧段落 {paragraph.paragraph_id}</small>
              <div className="paragraph-translation">
                <span className="translation-label">旧版中文译文</span>
                <p>{paragraph.translation_zh}</p>
              </div>
              <p>{paragraph.logic_role_zh}</p>
              {paragraph.critical_note_zh && (
                <p>{paragraph.critical_note_zh}</p>
              )}
            </article>
          ))}
        </details>
      )}
      {repair.isError && (
        <p role="alert" className="error-text">
          缺段任务状态读取失败：{repair.error.message}
          <button className="text-button" onClick={() => void repair.refetch()}>
            重新读取
          </button>
        </p>
      )}
      {repair.data?.status === "FAILED" && (
        <p role="alert" className="error-text">
          缺段重试失败，原有结果已保留：{repair.data.error}
        </p>
      )}
    </>
  );
}

export function BilingualParagraph({
  paragraph,
  analysis,
  pending = false,
  stale = false,
  active = false,
  onActive,
  onAsk,
  onOpenGraph,
  concepts = [],
  onRecordQuestion,
  stateReady = false,
}: {
  paragraph: ReadingParagraph;
  analysis?: ParagraphAnalysis;
  pending?: boolean;
  stale?: boolean;
  active?: boolean;
  onActive?: () => void;
  onAsk?: () => void;
  onOpenGraph?: (id: string) => void;
  concepts?: ConceptUnderstanding[];
  onRecordQuestion?: (text: string) => void;
  stateReady?: boolean;
}) {
  const segments = highlightSegments(
    paragraph.text_en,
    analysis?.highlights ?? [],
  );
  return (
    <article
      id={`reading-${paragraph.paragraph_id}`}
      data-paragraph-id={paragraph.paragraph_id}
      className={`bilingual-row${active ? " active" : ""}`}
      onMouseEnter={onActive}
      onFocusCapture={onActive}
    >
      <div className="bilingual-source">
        <header className="paragraph-heading">
          <span>第 {paragraph.ordinal} 段</span>
          <span>
            PDF 第 {paragraph.page_start}
            {paragraph.page_end !== paragraph.page_start
              ? `–${paragraph.page_end}`
              : ""}{" "}
            页
          </span>
        </header>
        <p className="paragraph-english" lang="en">
          {segments.map((segment) =>
            segment.type ? (
              <mark
                key={segment.start}
                className={`argument-mark mark-${segment.type.toLowerCase()}`}
                title={readingHighlightTypes[segment.type].label}
                data-highlight-type={segment.type}
              >
                {segment.text}
              </mark>
            ) : (
              <span key={segment.start}>{segment.text}</span>
            ),
          )}
        </p>
        <div
          className={`paragraph-translation${!analysis ? " translation-placeholder" : ""}`}
          lang="zh-CN"
          aria-label={`第 ${paragraph.ordinal} 段中文译文`}
        >
          <span className="translation-label">中文译文</span>
          <p>
            {analysis?.translation_zh ||
              (stale
                ? "原文或生成配置已变化，当前段落译文待重新生成。"
                : pending
                  ? "正在生成本段译文…"
                  : "本段译文尚未生成。生成所选范围后，译文会在这里常驻显示。")}
          </p>
        </div>
        {onAsk && (
          <button
            type="button"
            className="text-button paragraph-qa"
            onClick={onAsk}
          >
            对这一段提问
          </button>
        )}
      </div>
      <aside
        className="paragraph-annotation"
        aria-label={`第 ${paragraph.ordinal} 段论证批注`}
      >
        {analysis ? (
          <>
            <span className="paragraph-function">
              {functions[analysis.paragraph_function]}
            </span>
            <h5>逻辑作用</h5>
            <p>{analysis.logic_role_zh}</p>
            {analysis.critical_note_zh && (
              <>
                <h5>阅读批注</h5>
                <p>{analysis.critical_note_zh}</p>
              </>
            )}
            {analysis.reading_question_zh && (
              <div className="paragraph-question">
                <h5>带着问题读</h5>
                <p>{analysis.reading_question_zh}</p>
                {onRecordQuestion && (
                  <button
                    className="text-button"
                    disabled={!stateReady}
                    onClick={() =>
                      onRecordQuestion(analysis.reading_question_zh!)
                    }
                  >
                    记录为待解问题
                  </button>
                )}
              </div>
            )}
            {analysis.related_graph_node_ids.length > 0 && (
              <div className="paragraph-concepts">
                <h5>关联概念</h5>
                {analysis.related_graph_node_ids.map((id) => (
                  <button
                    key={id}
                    className="concept-link"
                    disabled={!onOpenGraph}
                    onClick={() => onOpenGraph?.(id)}
                  >
                    {concepts.find((concept) => concept.graph_node_id === id)
                      ?.node_label_zh || id}
                    <span aria-hidden="true"> ↗</span>
                  </button>
                ))}
              </div>
            )}
          </>
        ) : (
          <p className="muted annotation-placeholder">
            {pending
              ? "正在分析本段的论证作用…"
              : "本段批注尚未生成，与左侧原文逐段对应。"}
          </p>
        )}
      </aside>
    </article>
  );
}

export function ArgumentSummary({
  argument,
  label,
  incomplete = false,
}: {
  argument: NonNullable<SectionReadingAnalysis["section_argument"]>;
  label: string;
  incomplete?: boolean;
}) {
  return (
    <section className="reading-argument" aria-label={label}>
      <div className="eyebrow">ARGUMENT MAP</div>
      <h4>{label}</h4>
      {incomplete && (
        <p className="quality-note">
          部分段落尚未完成，以下为已返回的范围摘要，不能视为完整小节结论。
        </p>
      )}
      <ol>
        {argument.logic_chain_zh.map((step, i) => (
          <li key={i}>{step}</li>
        ))}
      </ol>
      <dl>
        {argument.core_claim_zh && (
          <>
            <dt>核心主张</dt>
            <dd>{argument.core_claim_zh}</dd>
          </>
        )}
        {argument.strong_point_zh && (
          <>
            <dt>论证的支点</dt>
            <dd>{argument.strong_point_zh}</dd>
          </>
        )}
        {argument.question_to_verify_zh && (
          <>
            <dt>需要进一步核查</dt>
            <dd>{argument.question_to_verify_zh}</dd>
          </>
        )}
      </dl>
    </section>
  );
}

export function UsageNote({
  usage,
  cacheHit = false,
}: {
  usage: GuideUsage;
  cacheHit?: boolean;
}) {
  return (
    <p className="reading-usage muted">
      {cacheHit
        ? "本次缓存命中，新增模型调用 0。原生成记录："
        : "本范围累计实际记录（读取不触发模型）："}
      输入 {usage.input_tokens ?? "未知"} · 输出 {usage.output_tokens ?? "未知"}{" "}
      · 合计 {usage.total_tokens ?? "未知"} Token · {usage.calls} 次调用 ·{" "}
      {usage.retry_count} 次重试 · 费用{" "}
      {usage.cost === null ? "未知" : usage.cost}。
    </p>
  );
}

function ReadingStatePanel({
  value,
  error,
  pending,
  concepts,
  onChange,
}: {
  value?: ReadingState;
  error: Error | null;
  pending: boolean;
  concepts: ConceptUnderstanding[];
  onChange: (patch: Partial<ReadingState>) => void;
}) {
  const [question, setQuestion] = useState("");
  return (
    <section className="reading-state-panel" aria-label="我的阅读状态">
      <div className="section-guide-header">
        <div>
          <h4>我的阅读状态</h4>
          <p className="muted">本地保存的主观记录；自评与模型建议分别展示。</p>
        </div>
        {pending && <span role="status">正在保存…</span>}
      </div>
      {error && (
        <p role="alert" className="error-text">
          {error.message}
        </p>
      )}
      {!value ? (
        <p className="muted">正在读取阅读状态…</p>
      ) : (
        <>
          {value.source_changed && (
            <p className="quality-note">
              原文已变化，保留此前的阅读记录，请重新确认自己的理解。
            </p>
          )}
          {value.unresolved_unlinked_ids.length > 0 && (
            <p className="quality-note">
              有 {value.unresolved_unlinked_ids.length}{" "}
              个旧概念待重新关联，尚未指向当前图谱。
            </p>
          )}
          <div className="reading-state-controls">
            <label>
              阅读进度
              <select
                value={value.progress}
                disabled={pending}
                onChange={(e) =>
                  onChange({
                    progress: e.target.value as ReadingState["progress"],
                  })
                }
              >
                <option value="NOT_STARTED">未开始</option>
                <option value="READING">阅读中</option>
                <option value="COMPLETED">已读完</option>
              </select>
            </label>
            <label>
              我的理解自评
              <select
                value={value.self_assessment}
                disabled={pending}
                onChange={(e) =>
                  onChange({
                    self_assessment: e.target.value as SelfAssessment,
                  })
                }
              >
                {Object.entries(assessmentLabels).map(([level, label]) => (
                  <option key={level} value={level}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {concepts.length > 0 && (
            <details>
              <summary>记录尚未理解的概念</summary>
              <div className="unresolved-concepts">
                {concepts.map((concept) => (
                  <label key={concept.graph_node_id}>
                    <input
                      type="checkbox"
                      checked={value.unresolved_concept_ids.includes(
                        concept.graph_node_id,
                      )}
                      disabled={pending}
                      onChange={(e) =>
                        onChange({
                          unresolved_concept_ids: e.target.checked
                            ? [
                                ...value.unresolved_concept_ids,
                                concept.graph_node_id,
                              ]
                            : value.unresolved_concept_ids.filter(
                                (id) => id !== concept.graph_node_id,
                              ),
                        })
                      }
                    />
                    {concept.node_label_zh ||
                      concept.node_label_en ||
                      concept.graph_node_id}
                  </label>
                ))}
              </div>
            </details>
          )}
          <div className="reading-questions">
            <label>
              添加待解问题
              <input
                value={question}
                maxLength={1000}
                placeholder="读完这一节，还有什么需要弄清？"
                onChange={(e) => setQuestion(e.target.value)}
              />
            </label>
            <button
              className="button secondary"
              disabled={pending || !question.trim()}
              onClick={() => {
                onChange({
                  questions: [
                    ...value.questions,
                    { text: question.trim(), resolved: false },
                  ],
                });
                setQuestion("");
              }}
            >
              保存问题
            </button>
            {value.questions.map((item, index) => (
              <label
                className="reading-question-record"
                key={`${index}:${item.text}`}
              >
                <input
                  type="checkbox"
                  checked={item.resolved}
                  disabled={pending}
                  onChange={(e) =>
                    onChange({
                      questions: value.questions.map((q, i) =>
                        i === index ? { ...q, resolved: e.target.checked } : q,
                      ),
                    })
                  }
                />
                <span>{item.text}</span>
                <small>{item.resolved ? "已解决" : "待解"}</small>
              </label>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function UnderstandingCheck({
  paperId,
  revisionId,
  sectionId,
  paragraphIds,
  connected,
  concepts,
}: {
  paperId: string;
  revisionId: string;
  sectionId: string;
  paragraphIds: string[];
  connected: boolean;
  concepts: ConceptUnderstanding[];
}) {
  const [explanation, setExplanation] = useState("");
  const [allow, setAllow] = useState(false);
  const [nodeId, setNodeId] = useState("");
  const [checkId, setCheckId] = useState("");
  const client = useQueryClient();
  const check = useQuery({
    queryKey: ["understanding-check", paperId, revisionId, sectionId, checkId],
    queryFn: () =>
      api.understandingCheck(
        paperId,
        sectionId,
        revisionId,
        checkId,
        paragraphIds,
      ),
    enabled: connected && !!paragraphIds.length,
    retry: false,
    refetchInterval: (q) => (q.state.data?.status === "PENDING" ? 1000 : false),
  });
  const generate = useMutation({
    mutationFn: () => {
      const concept = concepts.find((c) => c.graph_node_id === nodeId);
      return api.generateUnderstandingCheck(paperId, sectionId, {
        document_version_id: revisionId,
        paragraph_ids: paragraphIds,
        user_explanation: explanation.trim(),
        allow_network: true,
        ...(concept?.overview_result_id
          ? {
              graph_node_ids: [nodeId],
              overview_result_id: concept.overview_result_id,
            }
          : {}),
      });
    },
    retry: false,
    onSuccess: (value) => {
      setAllow(false);
      if (value.id) {
        setCheckId(value.id);
        client.setQueryData(
          ["understanding-check", paperId, revisionId, sectionId, value.id],
          value,
        );
      }
      void client.invalidateQueries({ queryKey: ["lite-usage"] });
      void client.invalidateQueries({
        queryKey: ["concept-understanding", paperId, revisionId],
      });
    },
  });
  const value = check.data ?? generate.data;
  useEffect(() => {
    if (check.data?.status !== "COMPLETED") return;
    void client.invalidateQueries({ queryKey: ["lite-usage"] });
    void client.invalidateQueries({
      queryKey: ["concept-understanding", paperId, revisionId],
    });
  }, [client, paperId, revisionId, check.data?.status]);
  const pending = generate.isPending || value?.status === "PENDING";
  return (
    <details className="understanding-check">
      <summary>用自己的话复述 · 按需理解检查</summary>
      <section aria-label="理解检查">
        <p className="muted">
          只在主动提交时，向模型发送当前范围原文和你的复述；反馈仅作建议，不会修改理解自评。
        </p>
        <label>
          我的复述
          <textarea
            rows={4}
            maxLength={3000}
            value={explanation}
            onChange={(e) => {
              setExplanation(e.target.value);
              setAllow(false);
            }}
            placeholder="用几句话说明你理解的观点、条件和依据…"
          />
        </label>
        {concepts.length > 0 && (
          <label>
            关联概念（可选）
            <select value={nodeId} onChange={(e) => setNodeId(e.target.value)}>
              <option value="">不关联单个概念</option>
              {concepts.map((c) => (
                <option key={c.graph_node_id} value={c.graph_node_id}>
                  {c.node_label_zh || c.node_label_en || c.graph_node_id}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="consent-inline">
          <input
            type="checkbox"
            checked={allow}
            onChange={(e) => setAllow(e.target.checked)}
          />
          允许本次检查我的复述
        </label>
        <button
          className="button secondary"
          disabled={
            !connected ||
            !allow ||
            !explanation.trim() ||
            !paragraphIds.length ||
            pending
          }
          onClick={() => generate.mutate()}
        >
          {pending ? "正在检查…" : "提交理解检查"}
        </button>
        {(generate.error || check.error) && (
          <p role="alert" className="error-text">
            {(generate.error ?? check.error)?.message}
          </p>
        )}
        {value?.error && (
          <p role="alert" className="error-text">
            {value.error}
          </p>
        )}
        {value?.user_explanation && (
          <p className="muted">这份反馈对应的复述：{value.user_explanation}</p>
        )}
        {value?.check && (
          <article className="understanding-feedback">
            <h5>模型建议：{checkLabels[value.check.check_result]}</h5>
            <p>{value.check.feedback_zh}</p>
            {value.check.correct_points_zh.length > 0 && (
              <>
                <h6>理解到的部分</h6>
                <ul>
                  {value.check.correct_points_zh.map((point, i) => (
                    <li key={i}>{point}</li>
                  ))}
                </ul>
              </>
            )}
            {value.check.missing_or_mistaken_zh.length > 0 && (
              <>
                <h6>可以再想一想</h6>
                <ul>
                  {value.check.missing_or_mistaken_zh.map((point, i) => (
                    <li key={i}>{point}</li>
                  ))}
                </ul>
              </>
            )}
            <p className="paragraph-question">
              {value.check.follow_up_question_zh}
            </p>
            <UsageNote usage={value.usage} cacheHit={value.cache_hit} />
          </article>
        )}
      </section>
    </details>
  );
}

function estimateReadingSource(text: string) {
  let units = 0;
  for (const character of text)
    units += character.charCodeAt(0) < 128 ? 0.25 : 1;
  return Math.ceil(units);
}
