import { useMemo, useState, type CSSProperties, type ReactNode } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";
import type { FormulaPreview, ParagraphAnalysis } from "./api";
import {
  readingAnnotationSegments,
  readingHighlightRanges,
  readingHighlightTypes,
} from "./readingHighlights";
import { useReadingAnnotationLayout } from "./useReadingAnnotationLayout";
import "./readingHighlights.css";
import "./paperCloseReading.css";

export function ReadingFormulaDisplay({
  latex: inputLatex,
  status: inputStatus,
  source = "",
  loadPreview,
  unverified = false,
}: {
  latex?: string | null;
  status?: string | null;
  source?: string;
  loadPreview?: () => Promise<FormulaPreview>;
  unverified?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const [preview, setPreview] = useState<FormulaPreview | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const latex = inputLatex?.trim();
  const status = inputStatus ?? (latex ? "recognized" : "detected");
  const togglePreview = async () => {
    if (preview) {
      setPreviewOpen((open) => !open);
      return;
    }
    if (!loadPreview) {
      setPreviewError("当前公式没有可用的原图定位信息。");
      return;
    }
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const value = await loadPreview();
      setPreview(value);
      setPreviewOpen(true);
    } catch (error) {
      setPreviewError(
        error instanceof Error ? error.message : "公式原图预览读取失败。",
      );
    } finally {
      setPreviewLoading(false);
    }
  };
  const previewControl = loadPreview ? (
    <>
      <button
        className="text-button"
        type="button"
        disabled={previewLoading}
        onClick={() => void togglePreview()}
      >
        {previewLoading
          ? "正在读取原图…"
          : previewOpen
            ? "隐藏原图区域"
            : "查看原图区域"}
      </button>
      {previewError && (
        <span className="paper-formula-preview-error" role="alert">
          {previewError}
        </span>
      )}
      {previewOpen && preview && (
        <figure className="paper-formula-preview">
          <img
            src={`data:${preview.mime_type};base64,${preview.data_base64}`}
            alt={`PDF 第 ${preview.page} 页公式原图区域`}
          />
          <figcaption>
            PDF 第 {preview.page} 页 · 原始区域已按登记来源截取；请以此核对
            LaTeX、上下标和积分上下限。
          </figcaption>
        </figure>
      )}
    </>
  ) : null;
  const canRender = unverified
    ? !["failed", "unavailable"].includes(status)
    : status === "recognized";
  if (!latex || !canRender) {
    return (
      <div className="paper-formula-fallback" role="note">
        <span className="paper-formula-status">
          {status === "uncertain" || status === "detected"
            ? "公式已定位，LaTeX 尚未可靠确认"
            : "公式暂未转换为 LaTeX"}
        </span>
        <pre>{source || "请查看原始 PDF 中的公式区域。"}</pre>
        <div className="paper-formula-actions">{previewControl}</div>
      </div>
    );
  }
  let html: string;
  try {
    html = katex.renderToString(latex, {
      displayMode: true,
      throwOnError: false,
      strict: "warn",
      trust: false,
    });
  } catch {
    return (
      <div className="paper-formula-fallback" role="note">
        <span className="paper-formula-status">
          LaTeX 渲染失败，保留原始公式
        </span>
        <pre>{source || latex}</pre>
        <div className="paper-formula-actions">{previewControl}</div>
      </div>
    );
  }
  return (
    <div className="paper-formula-rendered" role="note" aria-label="LaTeX 公式">
      {unverified && (
        <p className="paper-formula-status">模型提取公式，待核对</p>
      )}
      <div dangerouslySetInnerHTML={{ __html: html }} />
      <div className="paper-formula-actions">
        <button
          className="text-button"
          type="button"
          onClick={() => {
            if (!navigator.clipboard) return;
            void navigator.clipboard.writeText(latex).then(() => {
              setCopied(true);
              window.setTimeout(() => setCopied(false), 1400);
            });
          }}
        >
          {copied ? "已复制 LaTeX" : "复制 LaTeX"}
        </button>
        {previewControl}
      </div>
      <details className="paper-formula-source">
        <summary>查看 LaTeX 与原始公式</summary>
        <pre>{latex}</pre>
        {source && source !== latex && <pre>{source}</pre>}
      </details>
    </div>
  );
}

function tableCell(value: unknown): string | null {
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  )
    return String(value);
  if (value === null) return "";
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const cell = value as Record<string, unknown>;
    // Complex merged-cell data stays in its complete original representation.
    if (
      (cell.rowspan ?? cell.row_span ?? 1) !== 1 ||
      (cell.colspan ?? cell.col_span ?? 1) !== 1
    )
      return null;
    if (typeof cell.text === "string") return cell.text;
  }
  return null;
}

export function ReadingTableDisplay({
  data,
  rawText,
}: {
  data: Record<string, unknown> | null;
  rawText?: string | null;
}) {
  const rawHeaders = data?.columns ?? data?.headers;
  const headers = Array.isArray(rawHeaders) ? rawHeaders.map(tableCell) : [];
  const rawRows = data?.rows;
  const rows =
    Array.isArray(rawRows) && rawRows.every(Array.isArray)
      ? rawRows.map((row: unknown[]) => row.map(tableCell))
      : [];
  const width = headers.length || rows[0]?.length || 0;
  const complete =
    width > 0 &&
    rows.length > 0 &&
    headers.every((cell) => cell !== null) &&
    rows.every(
      (row) => row.length === width && row.every((cell) => cell !== null),
    );
  return (
    <>
      {complete ? (
        <div className="paper-reading-table">
          <table aria-label="模型提取表格">
            {!!headers.length && (
              <thead>
                <tr>
                  {headers.map((cell, index) => (
                    <th key={index} scope="col">
                      {cell}
                    </th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody>
              {rows.map((row, index) => (
                <tr key={index}>
                  {row.map((cell, column) => (
                    <td key={column}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : rawText ? (
        <pre className="model-document-table">{rawText}</pre>
      ) : (
        <p className="muted">
          表格结构保留在下方，请展开查看；当前结构无法完整转换为表格预览。
        </p>
      )}
      {data && (
        <details className="model-document-source">
          <summary>查看表格原始文本与结构</summary>
          {complete && rawText && (
            <pre className="model-document-table">{rawText}</pre>
          )}
          <pre className="model-document-table">
            {JSON.stringify(data, null, 2)}
          </pre>
        </details>
      )}
    </>
  );
}
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

export function ReadingLegend() {
  return (
    <div className="reading-legend" aria-label="全文论证标注图例">
      {Object.entries(readingHighlightTypes).map(([type, appearance]) => (
        <span key={type}>
          <i style={{ background: appearance.color }} />
          {appearance.label}
        </span>
      ))}
    </div>
  );
}

export type ReadingParagraphAnalysis = Omit<
  ParagraphAnalysis,
  "translation_zh"
> & {
  translation_zh: string | null;
};

export function ReadingParagraphCard({
  id,
  elementId,
  text,
  paragraphNumber,
  metadata,
  sourceDetails,
  formula,
  analysis,
  translation,
  pending = false,
  stale = false,
  translationUnavailableMessage,
  onOpenGraph,
  onAsk,
}: {
  id: string;
  elementId: string;
  text: string;
  paragraphNumber: number;
  metadata?: ReactNode;
  sourceDetails?: ReactNode;
  formula?: ReactNode;
  analysis?: ReadingParagraphAnalysis;
  translation?: string | null;
  pending?: boolean;
  stale?: boolean;
  translationUnavailableMessage?: string;
  onOpenGraph?: (nodeId: string) => void;
  onAsk?: () => void;
}) {
  const ranges = useMemo(
    () =>
      readingHighlightRanges(text, analysis?.highlights ?? []).sort(
        (a, b) => a.start - b.start || a.index - b.index,
      ),
    [text, analysis?.highlights],
  );
  const segments = useMemo(
    () => readingAnnotationSegments(text, ranges),
    [text, ranges],
  );
  const layoutKey = JSON.stringify([
    text,
    analysis,
    translation,
    metadata !== undefined,
  ]);
  const [selection, setSelection] = useState<{
    source: string;
    index: number;
  } | null>(null);
  const activeIndex = selection?.source === layoutKey ? selection.index : null;
  const [pointerPreview, setPointerPreview] = useState<typeof selection>(null);
  const [focusPreview, setFocusPreview] = useState<typeof selection>(null);
  const preview =
    pointerPreview?.source === layoutKey ? pointerPreview : focusPreview;
  const previewIndex = preview?.source === layoutKey ? preview.index : null;
  const rowRef = useReadingAnnotationLayout(layoutKey);
  const numberFor = (index: number) =>
    `${paragraphNumber}.${ranges.findIndex((range) => range.index === index) + 1}`;
  const noteId = (index: number) => `${elementId}-annotation-${index}`;
  const activateNote = (index: number) => {
    setSelection({ source: layoutKey, index });
    const card = document.getElementById(noteId(index));
    card?.focus({ preventScroll: true });
    card?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  };
  const locateMark = (index: number) => {
    setSelection({ source: layoutKey, index });
    const mark = [
      ...(rowRef.current?.querySelectorAll<HTMLElement>(
        "[data-annotation-keys]",
      ) ?? []),
    ].find((candidate) =>
      candidate.dataset.annotationKeys?.split(" ").includes(String(index)),
    );
    mark?.focus({ preventScroll: true });
    mark?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  };
  return (
    <article
      ref={rowRef}
      className="paper-reading-paragraph"
      id={elementId}
      tabIndex={-1}
      data-paragraph-id={id}
    >
      <div className="paper-paragraph-source">
        <div className="paper-paragraph-meta">
          <span>{metadata}</span>
          {onAsk && (
            <button className="text-button" onClick={onAsk}>
              对这段提问
            </button>
          )}
        </div>
        <p className="paper-paragraph-english" data-reading-anchor>
          {segments.map((segment) =>
            segment.type ? (
              <mark
                key={segment.start}
                className={`argument-mark mark-${segment.type.toLowerCase()}`}
                data-highlight-type={segment.type}
                data-annotation-keys={segment.highlightIndices.join(" ")}
                data-annotation-key={segment.highlightIndices[0]}
                data-note-number={
                  ranges
                    .filter((range) => range.start === segment.start)
                    .map((range) => numberFor(range.index))
                    .join(", ") || undefined
                }
                data-active={
                  activeIndex !== null &&
                  segment.highlightIndices.includes(activeIndex)
                }
                data-preview={
                  previewIndex !== null &&
                  segment.highlightIndices.includes(previewIndex)
                }
                role="button"
                tabIndex={0}
                aria-label={segment.highlightIndices
                  .map((index) => {
                    const range = ranges.find((item) => item.index === index)!;
                    return `标记 ${numberFor(index)} · ${readingHighlightTypes[range.type].label}：${range.quote_en}`;
                  })
                  .join("；")}
                aria-controls={segment.highlightIndices.map(noteId).join(" ")}
                aria-pressed={
                  activeIndex !== null &&
                  segment.highlightIndices.includes(activeIndex)
                }
                onPointerEnter={(event) => {
                  if (event.pointerType === "mouse")
                    setPointerPreview({
                      source: layoutKey,
                      index: segment.highlightIndices[0],
                    });
                }}
                onPointerLeave={() => setPointerPreview(null)}
                onFocus={() =>
                  setFocusPreview({
                    source: layoutKey,
                    index: segment.highlightIndices[0],
                  })
                }
                onBlur={() => setFocusPreview(null)}
                onClick={() =>
                  activateNote(
                    segment.highlightIndices.includes(activeIndex ?? -1)
                      ? activeIndex!
                      : segment.highlightIndices[0],
                  )
                }
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    activateNote(
                      segment.highlightIndices.includes(activeIndex ?? -1)
                        ? activeIndex!
                        : segment.highlightIndices[0],
                    );
                  }
                }}
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
          <p className={translation || analysis?.translation_zh ? "" : "muted"}>
            {translation ??
              analysis?.translation_zh ??
              (stale
                ? "旧笔记未与当前原文对齐；生成当前全文笔记后显示译文。"
                : pending
                  ? "正在生成全文笔记，本段译文将在校验后显示。"
                  : (translationUnavailableMessage ??
                    "尚无本段译文；生成全文精读笔记后常驻显示。"))}
          </p>
        </div>
        {sourceDetails}
        {formula}
      </div>
      <aside
        className="paper-paragraph-note"
        aria-label={`正文第 ${paragraphNumber} 段论证批注`}
      >
        {analysis ? (
          <section
            className="paper-paragraph-comment"
            aria-label={`第 ${paragraphNumber} 段整段批注`}
          >
            <div className="paper-paragraph-comment-heading">
              <strong>第 {paragraphNumber} 段 · 整段批注</strong>
              <span>{functionLabels[analysis.paragraph_function]}</span>
            </div>
            <small className="paper-comment-scope">
              以下分析对应本段{ranges.length ? "，点击编号可定位原文" : ""}。
            </small>
            {!!ranges.length && (
              <div
                className="paper-highlight-references"
                role="group"
                aria-label={`第 ${paragraphNumber} 段原文标记`}
              >
                {ranges.map((range) => (
                  <button
                    type="button"
                    key={range.index}
                    id={noteId(range.index)}
                    className="paper-highlight-reference"
                    style={
                      {
                        "--annotation-color":
                          readingHighlightTypes[range.type].color,
                      } as CSSProperties
                    }
                    data-annotation-key={range.index}
                    data-active={activeIndex === range.index}
                    data-preview={previewIndex === range.index}
                    aria-label={`定位原文标记 ${numberFor(range.index)} · ${readingHighlightTypes[range.type].label}`}
                    aria-pressed={activeIndex === range.index}
                    onPointerEnter={(event) => {
                      if (event.pointerType === "mouse")
                        setPointerPreview({
                          source: layoutKey,
                          index: range.index,
                        });
                    }}
                    onPointerLeave={() => setPointerPreview(null)}
                    onFocus={() =>
                      setFocusPreview({ source: layoutKey, index: range.index })
                    }
                    onBlur={() => setFocusPreview(null)}
                    onClick={() => locateMark(range.index)}
                  >
                    <span className="paper-highlight-number">
                      {numberFor(range.index)}
                    </span>
                    {readingHighlightTypes[range.type].label}
                  </button>
                ))}
              </div>
            )}
            <h6>论证作用</h6>
            <p>{analysis.logic_role_zh}</p>
            {analysis.critical_note_zh && (
              <>
                <h6>核查提醒</h6>
                <p className="paper-critical-note">
                  {analysis.critical_note_zh}
                </p>
              </>
            )}
            {analysis.reading_question_zh && (
              <>
                <h6>阅读问题</h6>
                <p className="paragraph-question">
                  {analysis.reading_question_zh}
                </p>
              </>
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
          </section>
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
