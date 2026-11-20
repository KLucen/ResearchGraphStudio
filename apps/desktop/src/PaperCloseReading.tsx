import { useEffect, useState } from "react";
import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  api,
  type DocumentReadingUnit,
  type DocumentReadingView,
  type ParagraphAnalysis,
  type ReadingParagraph,
  type ChapterProgress,
} from "./api";
import { ArgumentSummary, UsageNote } from "./SectionCloseReading";
import {
  ReadingFormulaDisplay,
  ReadingLegend,
  ReadingParagraphCard,
} from "./ReadingContent";
import { ReadingOutline, type OutlineEntry } from "./ReadingOutline";
import { ChapterProgressControls } from "./ChapterProgress";
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
  formula: "公式区域",
  caption: "图表标题与图注",
  figure_label: "疑似图内标签",
  running: "页眉页脚",
  reference: "参考文献",
  contents: "原文目录",
  unresolved: "待核对材料",
};

function FormulaDisplay({
  unit,
  revisionId,
}: {
  unit: DocumentReadingUnit;
  revisionId: string;
}) {
  return (
    <ReadingFormulaDisplay
      latex={unit.formula_latex}
      status={unit.formula_status}
      source={unit.formula_source_text || unit.text}
      loadPreview={
        unit.formula_id
          ? () => api.formulaPreview(revisionId, unit.formula_id!)
          : undefined
      }
    />
  );
}

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
function localReadingTime(value: string | null) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isFinite(date.getTime())
    ? date.toLocaleString("zh-CN", { hour12: false })
    : null;
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
  useEffect(() => {
    // The chapter query and the persisted full-reading projection are mounted
    // together. If the projection upgrades a legacy structure while the
    // directory request was still in flight, make the directory read the new
    // tree instead of keeping the old 1→5 outline in React Query.
    if (!local.data?.projection_hash) return;
    void client.invalidateQueries({ queryKey: ["sections", props.revisionId] });
  }, [client, local.data?.projection_hash, props.revisionId]);
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
      void client.invalidateQueries({
        queryKey: ["sections", props.revisionId],
      });
    },
  });
  const recognizeFormulas = useMutation({
    mutationFn: () => api.recognizeFormulas(props.revisionId),
    retry: false,
    onSuccess: async (value) => {
      if (value.reading_document_refresh_required) {
        const refreshed = await local.refetch();
        if (refreshed.data) client.setQueryData(documentKey, refreshed.data);
        void client.invalidateQueries({ queryKey: notesKey });
        void client.invalidateQueries({
          queryKey: ["sections", props.revisionId],
        });
      }
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
            disabled={
              pending || refresh.isPending || recognizeFormulas.isPending
            }
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
            refresh.isPending ||
            recognizeFormulas.isPending
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
          disabled={
            !props.connected ||
            pending ||
            refresh.isPending ||
            recognizeFormulas.isPending
          }
          onClick={() => refresh.mutate()}
        >
          {refresh.isPending ? "正在整理本地版面…" : "重新整理本地阅读版面"}
        </button>
        <button
          className="button secondary"
          disabled={
            !props.connected ||
            pending ||
            refresh.isPending ||
            recognizeFormulas.isPending ||
            !(
              local.data?.units.some(
                (unit) => unit.material_type === "formula",
              ) ?? false
            )
          }
          onClick={() => recognizeFormulas.mutate()}
        >
          {recognizeFormulas.isPending ? "正在识别公式…" : "自动识别公式并刷新"}
        </button>
        <p className="paper-reading-action-note muted">
          全文笔记只发送正文，不发送图表材料；单次容量不足会在调用前提示。重新整理只处理本地
          PDF，模型调用为 0。公式识别只使用已配置的本地 OCR，不发送 PDF 或公式到
          LLM。
          模型容量未知时只能按当前配置估算，不能保证一次完成；实际用量以模型返回为准。
        </p>
      </div>
      {(local.error ||
        notes.error ||
        generate.error ||
        refresh.error ||
        recognizeFormulas.error ||
        cancel.error) && (
        <p role="alert" className="error-text">
          {
            (
              local.error ??
              notes.error ??
              generate.error ??
              refresh.error ??
              recognizeFormulas.error ??
              cancel.error
            )?.message
          }
        </p>
      )}
      {recognizeFormulas.data?.status === "unavailable" && (
        <p className="quality-note" role="status">
          当前安装包没有配置本地公式 OCR；已保留原图和原始文本，没有生成不可靠的
          LaTeX。 请先配置专用公式识别器后再次操作。
        </p>
      )}
      {recognizeFormulas.data?.status === "partial" && (
        <p className="quality-note" role="status">
          部分公式已生成 LaTeX，低置信度或失败项仍保留原图，请逐项核对。
        </p>
      )}
      {(local.isError || notes.isError) && (
        <p className="paper-reading-retry">
          <button
            className="button secondary"
            disabled={
              !props.connected ||
              local.isFetching ||
              notes.isFetching ||
              refresh.isPending
            }
            onClick={() => {
              void Promise.all([local.refetch(), notes.refetch()]);
            }}
          >
            {local.isFetching || notes.isFetching
              ? "正在重新读取…"
              : "重新读取本地存档"}
          </button>
          <span className="muted">
            重新读取本地正文和已有笔记，模型调用为 0。
          </span>
        </p>
      )}
      {notes.data?.error && (
        <p role="alert" className="error-text">
          {notes.data.error_code} · {notes.data.error}
        </p>
      )}
      {local.isPending && props.connected && (
        <p role="status">正在读取本地阅读内容…</p>
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
            connected={props.connected}
            revisionId={props.revisionId}
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
  connected,
  revisionId,
  analyses,
  pending,
  stale,
  onOpenGraph,
  onAskParagraph,
}: {
  document: DocumentReadingView;
  connected: boolean;
  revisionId: string;
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
  const refreshedAt = localReadingTime(document.refreshed_at);
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
        level: unit.heading_level ?? section?.level,
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
  const entryBySection = new Map<string, string>();
  for (const entry of outlineEntries) {
    const unit = body.find((item) => item.id === entry.id);
    if (unit?.section_id && !entryBySection.has(unit.section_id))
      entryBySection.set(unit.section_id, entry.id);
  }
  for (const entry of outlineEntries) {
    const unit = body.find((item) => item.id === entry.id);
    const section = document.sections.find(
      (item) => item.section_id === unit?.section_id,
    );
    // Old projections may only have levels. New projections carry the source
    // tree explicitly; the synthetic Document root is not a containing chapter.
    if (
      section?.parent_id !== undefined &&
      entryBySection.get(section.section_id) === entry.id
    ) {
      const parent = document.sections.find(
        (item) => item.section_id === section.parent_id,
      );
      entry.parentId =
        parent?.role === "document"
          ? null
          : (entryBySection.get(section.parent_id ?? "") ?? null);
    }
  }
  const minLevel = Math.min(...outlineEntries.map((entry) => entry.level ?? 1));
  const mainEntries = outlineEntries.filter(
    (entry) =>
      entry.parentId === null ||
      (entry.parentId === undefined && (entry.level ?? 1) === minLevel),
  );
  const mainSectionIds = new Map(
    mainEntries.flatMap((entry) => {
      const sectionId = body.find((unit) => unit.id === entry.id)?.section_id;
      return sectionId ? [[entry.id, sectionId] as const] : [];
    }),
  );
  const mainEntryById = new Map(mainEntries.map((entry) => [entry.id, entry]));
  const chapterGroups: {
    entry?: OutlineEntry;
    units: DocumentReadingUnit[];
  }[] = [];
  let chapterGroup: (typeof chapterGroups)[number] = { units: [] };
  // Only body order defines chapter boundaries. The projection appends detected
  // figures and formulas after all body units, then renumbers their ordinals.
  // Their array position must never make an earlier chapter's material belong
  // to the last chapter. Recovered headings can still share one old section ID.
  for (const unit of body) {
    if (mainSectionIds.has(unit.id)) {
      if (chapterGroup.units.length) chapterGroups.push(chapterGroup);
      chapterGroup = { entry: mainEntryById.get(unit.id), units: [] };
    }
    chapterGroup.units.push(unit);
  }
  if (chapterGroup.units.length) chapterGroups.push(chapterGroup);
  const bodyGroups = chapterGroups.map((group) => ({
    group,
    body: [...group.units],
    firstIndex: document.units.findIndex(
      (unit) => unit.id === group.units[0]?.id,
    ),
  }));
  const sectionsById = new Map(
    document.sections.map((section) => [section.section_id, section]),
  );
  const unassignedMaterials: DocumentReadingUnit[] = [];
  for (const material of materials) {
    let candidates: (typeof bodyGroups)[number][] = [];
    let sectionId = material.section_id;
    const visitedSections = new Set<string>();
    while (sectionId && !visitedSections.has(sectionId)) {
      visitedSections.add(sectionId);
      candidates = bodyGroups.filter(
        ({ group, body: units }) =>
          group.entry && units.some((unit) => unit.section_id === sectionId),
      );
      if (candidates.length) break;
      sectionId = sectionsById.get(sectionId)?.parent_id ?? null;
    }
    // A shared source chunk/span can identify a concrete paragraph even if the
    // historical section was reused for several recovered chapter headings.
    const chunks = new Set(material.sources.map((source) => source.chunk_id));
    const spans = new Set(
      material.sources.flatMap((source) => source.span_ids),
    );
    const sourceCandidates = bodyGroups.filter(
      ({ group, body: units }) =>
        group.entry &&
        units.some(
          (unit) =>
            unit.kind === "paragraph" &&
            unit.sources.some(
              (source) =>
                chunks.has(source.chunk_id) ||
                source.span_ids.some((span) => spans.has(span)),
            ),
        ),
    );
    let owner =
      sourceCandidates.length === 1 &&
      (!candidates.length || candidates.includes(sourceCandidates[0]))
        ? sourceCandidates[0]
        : candidates.length === 1 && !sourceCandidates.length
          ? candidates[0]
          : undefined;
    if (!owner && candidates.length > 1 && !sourceCandidates.length) {
      const pageCandidates = candidates.filter(({ body: units }) => {
        const firstPage = Math.min(...units.map((unit) => unit.page_start));
        const lastPage = Math.max(...units.map((unit) => unit.page_end));
        return (
          material.page_start >= firstPage && material.page_end <= lastPage
        );
      });
      if (pageCandidates.length === 1) owner = pageCandidates[0];
      else {
        const materialIndex = document.units.findIndex(
          (unit) => unit.id === material.id,
        );
        // A truly interleaved item before the next body chapter has an explicit
        // position. A tail-appended item has no such bounded interval.
        const orderedCandidates = candidates.filter((candidate) => {
          const index = bodyGroups.indexOf(candidate);
          const next = bodyGroups[index + 1];
          return (
            next &&
            materialIndex > candidate.firstIndex &&
            materialIndex < next.firstIndex
          );
        });
        if (orderedCandidates.length === 1) owner = orderedCandidates[0];
      }
    }
    if (owner) owner.group.units.push(material);
    else unassignedMaterials.push(material);
  }
  const client = useQueryClient();
  const uniqueSectionIds = [...new Set(mainSectionIds.values())];
  const states = useQueries({
    queries: uniqueSectionIds.map((sectionId) => ({
      queryKey: ["reading-state", document.paper_id, revisionId, sectionId],
      queryFn: () => api.readingState(document.paper_id, sectionId, revisionId),
      enabled: connected,
      retry: false,
    })),
  });
  const stateBySection = new Map(
    uniqueSectionIds.map((sectionId, index) => [sectionId, states[index]]),
  );
  const saveProgress = useMutation({
    mutationFn: ({
      sectionId,
      progress,
    }: {
      sectionId: string;
      progress: ChapterProgress;
    }) =>
      api.saveReadingProgress(document.paper_id, sectionId, {
        document_version_id: revisionId,
        progress,
      }),
    retry: false,
    onSuccess: (value) => {
      client.setQueryData(
        ["reading-state", document.paper_id, revisionId, value.section_id],
        value,
      );
    },
  });
  for (const entry of mainEntries) {
    const sectionId = mainSectionIds.get(entry.id);
    if (sectionId)
      entry.progress =
        stateBySection.get(sectionId)?.data?.progress ?? "NOT_STARTED";
  }
  return (
    <ReadingOutline entries={outlineEntries} trackScroll>
      {(saveProgress.error || states.some((state) => state.isError)) && (
        <p role="alert" className="error-text">
          {saveProgress.error?.message ??
            "章节阅读状态暂未读取成功，请稍后重新读取。"}
          <button
            type="button"
            className="text-button"
            onClick={() =>
              void Promise.all(states.map((state) => state.refetch()))
            }
          >
            重新读取阅读状态
          </button>
        </p>
      )}
      <div className="paper-reading-local-status">
        <span>
          本地阅读内容已就绪 · {paragraphs.length} 段正文 · {materials.length}{" "}
          项单独材料
        </span>
        {refreshedAt && (
          <span>
            上次本地整理：
            <time dateTime={document.refreshed_at!}>{refreshedAt}</time>
          </span>
        )}
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
      <ReadingLegend />
      {!!paragraphs.length && (
        <div className="paper-reading-column-labels" aria-hidden="true">
          <span>正文与常驻中文译文</span>
          <span>标记与整段批注</span>
        </div>
      )}
      <div className="paper-reading-body">
        {chapterGroups.map((chapter, chapterIndex) => (
          <section
            key={chapter.entry?.id ?? `unheaded-${chapterIndex}`}
            className="paper-reading-chapter"
            data-chapter-id={chapter.entry?.id}
          >
            {chapter.units
              .filter((unit) => unit.kind !== "material")
              .map((unit) =>
                unit.kind === "heading" ? (
                  <header
                    className="paper-reading-section-heading"
                    key={unit.id}
                    id={unitElementId(unit.id)}
                    data-reading-anchor
                    tabIndex={-1}
                    data-heading-level={
                      unit.heading_level ??
                      document.sections.find(
                        (s) => s.section_id === unit.section_id,
                      )?.level ??
                      1
                    }
                  >
                    <h5>{unit.text}</h5>
                    <span className="muted">{pageLabel(unit)}</span>
                  </header>
                ) : (
                  <PaperParagraph
                    key={unit.id}
                    unit={unit}
                    revisionId={revisionId}
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
            {(chapter.units.some((unit) => unit.kind === "material") ||
              (!materials.length &&
                chapterIndex === chapterGroups.length - 1)) && (
              <ReadingMaterials
                materials={chapter.units.filter(
                  (unit) => unit.kind === "material",
                )}
                revisionId={revisionId}
              />
            )}
            {chapter.entry && mainSectionIds.has(chapter.entry.id) && (
              <ChapterProgressControls
                title={chapter.entry.label}
                progress={
                  stateBySection.get(mainSectionIds.get(chapter.entry.id)!)
                    ?.data?.progress ?? "NOT_STARTED"
                }
                disabled={
                  !connected ||
                  saveProgress.isPending ||
                  !stateBySection.get(mainSectionIds.get(chapter.entry.id)!)
                    ?.isSuccess
                }
                onChange={(progress) =>
                  saveProgress.mutate({
                    sectionId: mainSectionIds.get(chapter.entry!.id)!,
                    progress,
                  })
                }
              />
            )}
          </section>
        ))}
      </div>
      {!!unassignedMaterials.length && (
        <ReadingMaterials
          materials={unassignedMaterials}
          revisionId={revisionId}
          unassigned
        />
      )}
      {!paragraphs.length && (
        <p className="quality-note">
          尚未识别出可靠正文。请查看材料区或原始 PDF；扫描页暂不执行 OCR。
        </p>
      )}
      {!materials.length && !chapterGroups.length && (
        <ReadingMaterials materials={[]} revisionId={revisionId} />
      )}
    </ReadingOutline>
  );
}

function ReadingMaterials({
  materials,
  revisionId,
  unassigned = false,
}: {
  materials: DocumentReadingUnit[];
  revisionId: string;
  unassigned?: boolean;
}) {
  return (
    <details
      className="paper-reading-materials"
      data-unassigned-materials={unassigned || undefined}
    >
      <summary>
        {unassigned ? "未确定章节的图表与其他材料" : "图表与其他材料"}（
        {materials.length}）
      </summary>
      <section
        aria-label={
          unassigned ? "未确定章节的图表与其他材料" : "图表与其他材料"
        }
      >
        {unassigned && (
          <p className="quality-note">
            现有来源无法唯一确定这些材料所属的章节，单独保留在这里；请按原始页码和定位核对。
          </p>
        )}
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
            {unit.material_type === "formula" && (
              <FormulaDisplay unit={unit} revisionId={revisionId} />
            )}
            <pre className="paper-material-raw">
              {unit.sources.length
                ? unit.sources.map((source) => source.text).join("\n")
                : unit.text || "此区域没有可提取的文字；请查看原始 PDF 图像。"}
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
  );
}

function PaperParagraph({
  unit,
  revisionId,
  paragraphNumber,
  analysis,
  pending,
  stale,
  onOpenGraph,
  onAsk,
}: {
  unit: DocumentReadingUnit;
  revisionId: string;
  paragraphNumber: number;
  analysis?: ParagraphAnalysis;
  pending: boolean;
  stale: boolean;
  onOpenGraph?: Props["onOpenGraph"];
  onAsk?: () => void;
}) {
  return (
    <ReadingParagraphCard
      id={unit.id}
      elementId={unitElementId(unit.id)}
      text={unit.text}
      paragraphNumber={paragraphNumber}
      metadata={
        <>
          {pageLabel(unit)}
          {unit.sources.length > 1
            ? ` · ${unit.sources.length} 个原始块组合`
            : ""}
        </>
      }
      sourceDetails={<SourceMap unit={unit} />}
      formula={
        unit.formula_latex ? (
          <FormulaDisplay unit={unit} revisionId={revisionId} />
        ) : undefined
      }
      analysis={analysis}
      pending={pending}
      stale={stale}
      onOpenGraph={onOpenGraph}
      onAsk={onAsk}
    />
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
