import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  type DocumentReadingUnit,
  type DocumentReadingView,
  type ParagraphAnalysis,
  type ReadingParagraph,
} from "./api";
import { ArgumentSummary, UsageNote } from "./SectionCloseReading";
import { highlightSegments, readingHighlightTypes } from "./readingHighlights";
import { ReadingOutline, type OutlineEntry } from "./ReadingOutline";
import "./paperCloseReading.css";

const statusLabels = {
  PENDING: "正在生成全文笔记",
  COMPLETED: "全文笔记已完成",
  INCOMPLETE: "笔记部分完成",
  FAILED: "生成失败",
  STALE: "旧笔记已保留",
};
const materialLabels = {
  table: "表格",
  figure: "图像区域",
  caption: "图表标题与图注",
  figure_label: "疑似图内标签",
  running: "页眉页脚",
  reference: "参考文献",
  unresolved: "待核对材料",
};
const functionLabels = {
  INTRODUCE_PROBLEM: "提出问题",
  DEFINE_CONCEPT: "定义概念",
  STATE_CLAIM: "陈述论点",
  EXPLAIN_METHOD: "解释方法",
  PRESENT_EVIDENCE: "呈现论据",
  HANDLE_OBJECTION: "回应异议",
  DISCUSS_LIMITATION: "讨论局限",
  SUMMARIZE_TRANSITION: "总结与过渡",
  OTHER: "阅读批注",
};

type Props = {
  paperId: string;
  revisionId: string;
  connected: boolean;
  initialParagraphId?: string;
  onOpenGraph?: (nodeId: string) => void;
  onAskParagraph?: (sectionId: string, paragraph: ReadingParagraph) => void;
};

const unitElementId = (id: string) => `paper-reading-${id}`;
function focusUnit(id: string) {
  const element = document.getElementById(unitElementId(id));
  element?.scrollIntoView?.({ block: "center", behavior: "auto" });
  element?.focus({ preventScroll: true });
}
function pageLabel(unit: Pick<DocumentReadingUnit, "page_start" | "page_end">) {
  return unit.page_start === unit.page_end
    ? `PDF 第 ${unit.page_start} 页`
    : `PDF 第 ${unit.page_start}–${unit.page_end} 页`;
}

export function PaperCloseReading(props: Props) {
  const client = useQueryClient();
  const documentKey = ["reading-document", props.paperId, props.revisionId];
  const notesKey = ["paper-reading-notes", props.paperId, props.revisionId];
  const local = useQuery({
    queryKey: documentKey,
    queryFn: () => api.readingDocument(props.paperId, props.revisionId),
    enabled: props.connected,
    retry: false,
  });
  const notes = useQuery({
    queryKey: notesKey,
    queryFn: () => api.paperReadingNotes(props.paperId, props.revisionId),
    enabled: props.connected,
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.status === "PENDING" ? 1200 : false,
  });
  const [allowNetwork, setAllowNetwork] = useState(false);
  const generate = useMutation({
    mutationFn: () =>
      api.generatePaperReadingNotes(props.paperId, {
        document_version_id: props.revisionId,
        allow_network: true,
        force_regenerate: !!notes.data,
      }),
    retry: false,
    onSuccess: (value) => {
      client.setQueryData(notesKey, value);
      setAllowNetwork(false);
      void client.invalidateQueries({ queryKey: ["lite-usage"] });
      void client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
  const refresh = useMutation({
    mutationFn: () =>
      api.refreshReadingDocument(props.paperId, props.revisionId),
    retry: false,
    onSuccess: (value) => {
      client.setQueryData(documentKey, value);
      setAllowNetwork(false);
      void client.invalidateQueries({ queryKey: notesKey });
    },
  });
  const cancel = useMutation({
    mutationFn: () =>
      api.jobAction(notes.data!.job_id!, "cancel", crypto.randomUUID()),
    retry: false,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: notesKey });
      void client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
  useEffect(() => {
    if (!notes.data?.status || notes.data.status === "PENDING") return;
    void client.invalidateQueries({ queryKey: ["lite-usage"] });
    void client.invalidateQueries({ queryKey: ["jobs"] });
  }, [client, notes.data?.status]);
  useEffect(() => {
    if (!props.initialParagraphId || !local.data) return;
    const target = local.data.units.find(
      (unit) =>
        unit.id === props.initialParagraphId ||
        unit.sources.some(
          (source) => source.chunk_id === props.initialParagraphId,
        ),
    );
    if (target) focusUnit(target.id);
  }, [local.data, props.initialParagraphId]);
  const pending = generate.isPending || notes.data?.status === "PENDING";
  const stale =
    notes.data?.status === "STALE" ||
    (!!notes.data &&
      !!local.data &&
      notes.data.projection_hash !== local.data.projection_hash);
  const current = stale ? null : notes.data?.analysis;
  const paragraphs =
    local.data?.units.filter((u) => u.kind === "paragraph") ?? [];
  const byId = new Map(
    (current?.paragraphs ?? []).map((paragraph) => [
      paragraph.paragraph_id,
      paragraph,
    ]),
  );
  return (
    <section className="paper-close-reading" aria-label="全文精读笔记">
      <header className="paper-reading-header">
        <div>
          <h4>全文精读</h4>
          <p className="muted">
            先读本地整理的正文，再按需一次生成整篇论文的译文与论证笔记。
          </p>
        </div>
        <span className="pill" role="status">
          {stale
            ? "旧笔记已保留"
            : notes.data?.cache_hit
              ? "缓存命中 · 新增调用 0"
              : notes.data?.status
                ? statusLabels[notes.data.status]
                : "本地阅读 · 模型调用 0"}
        </span>
      </header>
      <div className="paper-reading-actions">
        <label className="consent-inline">
          <input
            type="checkbox"
            checked={allowNetwork}
            disabled={pending || refresh.isPending}
            onChange={(event) => setAllowNetwork(event.target.checked)}
          />
          允许本次发送整篇正文，生成全文精读笔记
        </label>
        <button
          className="button primary"
          disabled={
            !props.connected ||
            !allowNetwork ||
            !paragraphs.length ||
            local.isPending ||
            notes.isPending ||
            pending ||
            refresh.isPending
          }
          onClick={() => generate.mutate()}
        >
          {pending
            ? "正在生成全文笔记…"
            : notes.data
              ? "重新生成全文笔记"
              : "生成全文精读笔记"}
        </button>
        {pending && notes.data?.job_id && (
          <button
            className="text-button"
            disabled={cancel.isPending}
            onClick={() => cancel.mutate()}
          >
            取消任务
          </button>
        )}
        <button
          className="button secondary"
          disabled={!props.connected || pending || refresh.isPending}
          onClick={() => refresh.mutate()}
        >
          {refresh.isPending ? "正在整理本地版面…" : "重新整理本地阅读版面"}
        </button>
        <p className="paper-reading-action-note muted">
          全文笔记只发送正文，不发送图表材料；单次容量不足会在调用前提示。重新整理只处理本地
          PDF，模型调用为 0。
          模型容量未知时只能按当前配置估算，不能保证一次完成；实际用量以模型返回为准。
        </p>
      </div>
      {(local.error ||
        notes.error ||
        generate.error ||
        refresh.error ||
        cancel.error) && (
        <p role="alert" className="error-text">
          {
            (
              local.error ??
              notes.error ??
              generate.error ??
              refresh.error ??
              cancel.error
            )?.message
          }
        </p>
      )}
      {notes.data?.error && (
        <p role="alert" className="error-text">
          {notes.data.error_code} · {notes.data.error}
        </p>
      )}
      {local.isPending && props.connected && (
        <p role="status">正在整理本地正文与材料…</p>
      )}
      {stale && (
        <p className="quality-note">
          原文、阅读版面或模型配置已变化。旧笔记保留在下方，当前正文不套用旧译文与标注；重新生成须再次确认。
        </p>
      )}
      {notes.data?.status === "INCOMPLETE" && !stale && (
        <p className="quality-note" role="status">
          本次笔记不完整：保留已校验的译文和批注，尚缺{" "}
          {notes.data.missing_paragraph_ids.length}{" "}
          段。不会自动追加请求；如需重做，请明确重新生成全文笔记。
        </p>
      )}
      {notes.data?.estimated && (
        <p className="reading-cost muted">
          本文估算：输入{" "}
          {notes.data.estimated.estimated_input_tokens.toLocaleString()} · 输出{" "}
          {notes.data.estimated.estimated_output_tokens.toLocaleString()} · 合计{" "}
          {notes.data.estimated.estimated_total_tokens.toLocaleString()}{" "}
          Token；估算不计为实际用量。
          {notes.data.estimated.warning && ` ${notes.data.estimated.warning}`}
        </p>
      )}
      {local.data && (
        <>
          <ReadingDocument
            document={local.data}
            analyses={byId}
            pending={pending}
            stale={stale}
            onOpenGraph={props.onOpenGraph}
            onAskParagraph={props.onAskParagraph}
          />
          {current?.paper_argument && (
            <ArgumentSummary
              argument={current.paper_argument}
              label="全文论证结构"
              incomplete={notes.data?.status === "INCOMPLETE"}
            />
          )}
        </>
      )}
      {!!notes.data?.warnings.length && (
        <details className="reading-warnings">
          <summary>笔记校验提示（{notes.data.warnings.length}）</summary>
          <ul>
            {notes.data.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </details>
      )}
      {notes.data?.usage && (
        <UsageNote usage={notes.data.usage} cacheHit={notes.data.cache_hit} />
      )}
      {stale && notes.data?.analysis && (
        <details className="reading-old-draft">
          <summary>查看旧版本全文笔记</summary>
          <p className="muted">下方旧稿未与当前原文重新对齐。</p>
          {notes.data.analysis.paragraphs.map((paragraph, index) => (
            <article key={paragraph.paragraph_id}>
              <h5>旧稿第 {index + 1} 段</h5>
              <p>{paragraph.translation_zh}</p>
              <p>{paragraph.logic_role_zh}</p>
              {paragraph.critical_note_zh && (
                <p>{paragraph.critical_note_zh}</p>
              )}
            </article>
          ))}
          {notes.data.analysis.paper_argument && (
            <ArgumentSummary
              argument={notes.data.analysis.paper_argument}
              label="旧稿全文论证结构"
              incomplete={false}
            />
          )}
        </details>
      )}
    </section>
  );
}

function ReadingDocument({
  document,
  analyses,
  pending,
  stale,
  onOpenGraph,
  onAskParagraph,
}: {
  document: DocumentReadingView;
  analyses: Map<string, ParagraphAnalysis>;
  pending: boolean;
  stale: boolean;
  onOpenGraph?: Props["onOpenGraph"];
  onAskParagraph?: Props["onAskParagraph"];
}) {
  const body = document.units.filter((unit) => unit.kind !== "material");
  const materials = document.units.filter((unit) => unit.kind === "material");
  const headings = body.filter((unit) => unit.kind === "heading");
  const paragraphs = body.filter((unit) => unit.kind === "paragraph");
  const paragraphNumbers = new Map(
    paragraphs.map((unit, index) => [unit.id, index + 1]),
  );
  const outlineEntries: OutlineEntry[] = [];
  const headedSections = new Set(headings.map((unit) => unit.section_id));
  const fallbackSections = new Set<string | null>();
  for (const unit of body) {
    const section = document.sections.find(
      (item) => item.section_id === unit.section_id,
    );
    if (unit.kind === "heading") {
      outlineEntries.push({
        id: unit.id,
        label: unit.text,
        targetId: unitElementId(unit.id),
        level: section?.level,
        detail: pageLabel(unit),
      });
    } else if (
      !headedSections.has(unit.section_id) &&
      !fallbackSections.has(unit.section_id)
    ) {
      fallbackSections.add(unit.section_id);
      outlineEntries.push({
        id: unit.id,
        label: section?.title || "正文",
        targetId: unitElementId(unit.id),
        level: section?.level,
        detail: pageLabel(unit),
      });
    }
  }
  return (
    <ReadingOutline entries={outlineEntries} trackScroll>
      <div className="paper-reading-local-status">
        <span>
          {paragraphs.length} 段正文 · {materials.length} 项单独材料
        </span>
        <span>原始文字块、定位与哈希保留</span>
      </div>
      {!!document.warnings.length && (
        <details className="reading-warnings">
          <summary>本地解析提示（{document.warnings.length}）</summary>
          <ul>
            {document.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </details>
      )}
      <div className="reading-legend" aria-label="全文论证标注图例">
        {Object.entries(readingHighlightTypes).map(([type, appearance]) => (
          <span key={type}>
            <i style={{ background: appearance.color }} />
            {appearance.label}
          </span>
        ))}
      </div>
      {!!paragraphs.length && (
        <div className="paper-reading-column-labels" aria-hidden="true">
          <span>正文与常驻中文译文</span>
          <span>论证笔记</span>
        </div>
      )}
      <div className="paper-reading-body">
        {body.map((unit) =>
          unit.kind === "heading" ? (
            <header
              className="paper-reading-section-heading"
              key={unit.id}
              id={unitElementId(unit.id)}
              data-reading-anchor
              tabIndex={-1}
            >
              <h5>{unit.text}</h5>
              <span className="muted">{pageLabel(unit)}</span>
            </header>
          ) : (
            <PaperParagraph
              key={unit.id}
              unit={unit}
              paragraphNumber={paragraphNumbers.get(unit.id)!}
              analysis={analyses.get(unit.id)}
              pending={pending}
              stale={stale}
              onOpenGraph={onOpenGraph}
              onAsk={
                unit.section_id && onAskParagraph
                  ? () =>
                      onAskParagraph(unit.section_id!, {
                        paragraph_id: unit.id,
                        text_en: unit.text,
                        text_hash: unit.source_hash,
                        page_start: unit.page_start,
                        page_end: unit.page_end,
                        ordinal: unit.ordinal,
                        span_ids: unit.sources.flatMap(
                          (source) => source.span_ids,
                        ),
                      })
                  : undefined
              }
            />
          ),
        )}
      </div>
      {!paragraphs.length && (
        <p className="quality-note">
          尚未识别出可靠正文。请查看材料区或原始 PDF；扫描页暂不执行 OCR。
        </p>
      )}
      <details className="paper-reading-materials">
        <summary>图表与其他材料（{materials.length}）</summary>
        <section aria-label="图表与其他材料">
          <p className="muted">
            图表、图注及疑似图内标签单独保留，不生成译文或论证批注。以下页码可用于在
            Zotero 原始 PDF 中核对；图像区域仅作定位识别。
          </p>
          {materials.map((unit) => (
            <details className="paper-material" key={unit.id}>
              <summary>
                <strong>
                  {unit.material_type
                    ? materialLabels[unit.material_type]
                    : "其他材料"}
                </strong>
                <span>
                  {pageLabel(unit)}
                  {unit.confidence === "suspected" ? " · 待核对" : ""}
                </span>
                {unit.text && (
                  <small>{unit.text.replace(/\s+/g, " ").slice(0, 100)}</small>
                )}
              </summary>
              <p className="paper-material-reason">
                {unit.reason || "此内容作为版面材料保留。"}
              </p>
              <p className="quality-note">
                处理建议：
                {unit.solution ||
                  "请在 Zotero 中打开原始 PDF，按页码查看；尚未对图表内容进行分析。"}
              </p>
              <pre className="paper-material-raw">
                {unit.sources.length
                  ? unit.sources.map((source) => source.text).join("\n")
                  : unit.text ||
                    "此区域没有可提取的文字；请查看原始 PDF 图像。"}
              </pre>
              <SourceMap unit={unit} />
            </details>
          ))}
          {!materials.length && (
            <p className="muted">
              当前未识别到单独材料。这不代表 PDF 不含图片或表格。
            </p>
          )}
        </section>
      </details>
    </ReadingOutline>
  );
}

function PaperParagraph({
  unit,
  paragraphNumber,
  analysis,
  pending,
  stale,
  onOpenGraph,
  onAsk,
}: {
  unit: DocumentReadingUnit;
  paragraphNumber: number;
  analysis?: ParagraphAnalysis;
  pending: boolean;
  stale: boolean;
  onOpenGraph?: Props["onOpenGraph"];
  onAsk?: () => void;
}) {
  return (
    <article
      className="paper-reading-paragraph"
      id={unitElementId(unit.id)}
      tabIndex={-1}
      data-paragraph-id={unit.id}
    >
      <div className="paper-paragraph-source">
        <div className="paper-paragraph-meta">
          <span>
            {pageLabel(unit)}
            {unit.sources.length > 1
              ? ` · ${unit.sources.length} 个原始块组合`
              : ""}
          </span>
          {onAsk && (
            <button className="text-button" onClick={onAsk}>
              对这段提问
            </button>
          )}
        </div>
        <p className="paper-paragraph-english" data-reading-anchor>
          {highlightSegments(unit.text, analysis?.highlights ?? []).map(
            (segment) =>
              segment.type ? (
                <mark
                  key={segment.start}
                  className={`argument-mark mark-${segment.type.toLowerCase()}`}
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
          className="paper-paragraph-translation"
          aria-label={`正文第 ${paragraphNumber} 段中文译文`}
        >
          <small>中文译文</small>
          <p className={analysis ? "" : "muted"}>
            {analysis?.translation_zh ??
              (stale
                ? "旧笔记未与当前原文对齐；生成当前全文笔记后显示译文。"
                : pending
                  ? "正在生成全文笔记，本段译文将在校验后显示。"
                  : "尚无本段译文；生成全文精读笔记后常驻显示。")}
          </p>
        </div>
        <SourceMap unit={unit} />
      </div>
      <aside
        className="paper-paragraph-note"
        aria-label={`正文第 ${paragraphNumber} 段论证批注`}
      >
        {analysis ? (
          <>
            <small>{functionLabels[analysis.paragraph_function]}</small>
            <p>{analysis.logic_role_zh}</p>
            {analysis.critical_note_zh && (
              <p className="paper-critical-note">{analysis.critical_note_zh}</p>
            )}
            {analysis.reading_question_zh && (
              <p className="paragraph-question">
                {analysis.reading_question_zh}
              </p>
            )}
            {onOpenGraph &&
              analysis.related_graph_node_ids.map((nodeId, index) => (
                <button
                  className="text-button"
                  key={nodeId}
                  onClick={() => onOpenGraph(nodeId)}
                >
                  查看关联概念 {index + 1}
                </button>
              ))}
          </>
        ) : (
          <p className="muted">
            {stale
              ? "当前正文暂无有效批注。"
              : "全文笔记生成后，在这里对照阅读。"}
          </p>
        )}
      </aside>
    </article>
  );
}

function SourceMap({ unit }: { unit: DocumentReadingUnit }) {
  return (
    <details className="paper-reading-source-map">
      <summary>
        原始块与定位{unit.join_reason ? " · 已组合连续正文" : ""}
      </summary>
      {unit.join_reason && <p>{unit.join_reason}</p>}
      <p className="mono">阅读单元哈希：{unit.source_hash}</p>
      {unit.regions.map((region, index) => (
        <p key={`region:${index}`}>
          来源区域 · PDF 第 {region.page} 页 · 坐标{" "}
          {region.bbox.map((value) => Number(value.toFixed(1))).join(", ")}
        </p>
      ))}
      {unit.sources.map((source, index) => (
        <article key={`${source.chunk_id}:${index}`}>
          <p>
            PDF 第 {source.page} 页 · 坐标{" "}
            {source.bbox.map((value) => Number(value.toFixed(1))).join(", ")} ·
            字符 {source.start_offset}–{source.end_offset}
          </p>
          <p className="mono">
            {source.chunk_id} · SHA-256 {source.text_hash}
          </p>
          <pre>{source.text}</pre>
        </article>
      ))}
      {!unit.sources.length && (
        <p className="muted">
          此图像定位没有对应文字块。请按页码查看原始 PDF。
        </p>
      )}
    </details>
  );
}
