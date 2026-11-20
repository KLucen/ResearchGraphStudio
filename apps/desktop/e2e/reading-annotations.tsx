import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ReadingLegend,
  ReadingParagraphCard,
  type ReadingParagraphAnalysis,
} from "../src/ReadingContent";
import "../src/style.css";

// Invented, distributable material. No database, PDF, Provider or API access.
const context =
  "The surrounding discussion preserves the original wording and explains the scope of this synthetic example. ";
const sparseText = [
  context.repeat(4),
  "The bounded model improves the stated objective.",
  context.repeat(5),
  "The term bounded model names a limited family of functions.",
  context.repeat(5),
  "A synthetic trial reports 12 observations.",
  context.repeat(5),
  "The result remains limited to this trial.",
  context.repeat(5),
  "The procedure samples each input in sequence.",
  context.repeat(3),
].join(" ");
const denseText =
  "alpha alpha beta. The bounded model improves a synthetic objective. " +
  "A trial reports 12 observations, but the result has a scope limitation. " +
  "The procedure samples each input in sequence. <img src=x onerror=alert(1)>";

const sparse: ReadingParagraphAnalysis = {
  paragraph_id: "annotation-sparse",
  paragraph_function: "STATE_CLAIM",
  translation_zh: "合成译文：这段依次给出主张、定义、证据、局限及方法。",
  logic_role_zh: "本段将主张、术语、试验和范围限制串联起来。",
  critical_note_zh: "这是整段解读，不是任一单独高亮的专属解释。",
  reading_question_zh: "这些证据是否覆盖了主张的适用范围？",
  related_graph_node_ids: [],
  highlights: [
    {
      type: "THESIS",
      quote_en: "The bounded model improves the stated objective.",
      occurrence_index: 0,
    },
    {
      type: "CONCEPT",
      quote_en: "The term bounded model names a limited family of functions.",
      occurrence_index: 0,
    },
    {
      type: "EVIDENCE",
      quote_en: "A synthetic trial reports 12 observations.",
      occurrence_index: 0,
    },
    {
      type: "COUNTERARGUMENT",
      quote_en: "The result remains limited to this trial.",
      occurrence_index: 0,
    },
    {
      type: "METHOD",
      quote_en: "The procedure samples each input in sequence.",
      occurrence_index: 0,
    },
  ],
};
const dense: ReadingParagraphAnalysis = {
  ...sparse,
  paragraph_id: "annotation-dense",
  paragraph_function: "OTHER",
  translation_zh: "合成译文：重复词和密集标记保留独立对应关系。",
  logic_role_zh: "密集例子同时保留重复词的出现位置与重叠标记。",
  critical_note_zh: "请对照编号阅读，不把整段说明等同于每个片段的解释。",
  reading_question_zh: null,
  highlights: [
    { type: "METHOD", quote_en: "alpha alpha beta", occurrence_index: 0 },
    { type: "THESIS", quote_en: "alpha", occurrence_index: 1 },
    { type: "CONCEPT", quote_en: "bounded model", occurrence_index: 0 },
    { type: "EVIDENCE", quote_en: "12 observations", occurrence_index: 0 },
    {
      type: "COUNTERARGUMENT",
      quote_en: "scope limitation",
      occurrence_index: 0,
    },
    {
      type: "METHOD",
      quote_en: "samples each input in sequence",
      occurrence_index: 0,
    },
  ],
};

declare global {
  interface Window {
    __annotationSources: Record<string, string>;
  }
}
window.__annotationSources = {
  "annotation-sparse": sparseText,
  "annotation-dense": denseText,
};

function Fixture() {
  const [largeFont, setLargeFont] = useState(false);
  const [compact, setCompact] = useState(false);
  const [expandedMetadata, setExpandedMetadata] = useState(false);
  return (
    <main
      className="annotation-fixture paper-close-reading"
      data-large-font={largeFont}
      style={{
        width: compact ? "520px" : "1280px",
        maxWidth: "calc(100% - 32px)",
        margin: "24px auto",
      }}
    >
      <style>{`
        .annotation-fixture[data-large-font="true"] .paper-paragraph-english { font-size: 25px; }
      `}</style>
      <h1>精读标记与批注位置验证</h1>
      <p>两种来源共用真实阅读组件；本页仅含合成材料。</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
        <button onClick={() => setLargeFont((value) => !value)}>
          {largeFont ? "恢复正文字号" : "增大正文字号"}
        </button>
        <button onClick={() => setCompact((value) => !value)}>
          {compact ? "恢复阅读宽度" : "缩小阅读宽度"}
        </button>
        <button onClick={() => setExpandedMetadata((value) => !value)}>
          {expandedMetadata ? "收起来源信息" : "展开来源信息"}
        </button>
      </div>
      <ReadingLegend />
      <ReadingParagraphCard
        id="annotation-sparse"
        elementId="annotation-sparse-row"
        text={sparseText}
        paragraphNumber={1}
        metadata="第 1 段 · 本地解析 · 稀疏标记"
        analysis={sparse}
      />
      <ReadingParagraphCard
        id="annotation-dense"
        elementId="annotation-dense-row"
        text={denseText}
        paragraphNumber={2}
        metadata={
          expandedMetadata ? (
            <>
              第 2 段 · 模型提取稿 · 密集与重叠标记
              <br />
              合成来源位置：第二页，第一段。
              <br />
              本页仅用于验证来源信息展开后的定位。
            </>
          ) : (
            "第 2 段 · 模型提取稿 · 密集与重叠标记"
          )
        }
        analysis={dense}
      />
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Fixture />
  </StrictMode>,
);
