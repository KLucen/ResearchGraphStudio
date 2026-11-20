import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  type OverviewLayout,
  type OverviewView,
  type ConceptUnderstanding,
  type ReadingParagraph,
  type SelfAssessment,
} from "./api";
import { ForceGraph } from "./ForceGraph";
import { GraphLegend } from "./graphAppearance";
import type { GraphData } from "./graphTypes";
import { assessmentLabels, checkLabels } from "./SectionCloseReading";
import { knowledgeApi } from "./knowledgeApi";

const errorText = (value: unknown) =>
  value instanceof Error ? value.message : String(value);

type PaperOverviewProps = {
  paperId: string;
  revisionId: string;
  projectId: string;
  connected: boolean;
  source?: "local" | "model";
  initialNodeId?: string;
  onOpenSection?: (sectionId: string, paragraphId?: string) => void;
  onAskParagraph?: (sectionId: string, paragraph: ReadingParagraph) => void;
};

export function PaperOverview(props: PaperOverviewProps) {
  return (
    <PaperOverviewSession
      key={`${props.source ?? "local"}:${props.paperId}:${props.revisionId}`}
      {...props}
    />
  );
}

function PaperOverviewSession({
  paperId,
  revisionId,
  projectId,
  connected,
  source = "local",
  initialNodeId = "",
  onOpenSection,
  onAskParagraph,
}: PaperOverviewProps) {
  const client = useQueryClient();
  const queryName = source === "model" ? "model-overview" : "overview";
  const layoutQueryName =
    source === "model" ? "model-overview-layout" : "overview-layout";
  const [allowNetwork, setAllowNetwork] = useState(false);
  const [selectedNode, setSelectedNode] = useState(initialNodeId);
  const [selectedEdge, setSelectedEdge] = useState("");
  const [layout, setLayout] = useState<OverviewLayout | null>(null);
  const [reset, setReset] = useState(0);
  const pendingLayout = useRef<OverviewLayout | null>(null);
  const layoutTimer = useRef<number | null>(null);
  const layoutWrites = useRef<Promise<unknown>>(Promise.resolve());
  const previousStatus = useRef<string | undefined>(undefined);
  const overview = useQuery({
    queryKey: [queryName, paperId, revisionId],
    queryFn: () =>
      source === "model"
        ? api.modelOverview(paperId, revisionId)
        : api.overview(paperId, revisionId),
    enabled: connected,
    refetchInterval: (query) =>
      query.state.data?.status === "PENDING" ? 1500 : false,
  });
  const generate = useMutation({
    mutationFn: ({
      retryFailed,
      forceRegenerate,
    }: {
      retryFailed: boolean;
      forceRegenerate: boolean;
    }) =>
      (source === "model" ? api.generateModelOverview : api.generateOverview)(
        paperId,
        revisionId,
        allowNetwork,
        retryFailed,
        forceRegenerate,
      ),
    onSuccess: (value) => {
      setLayout(null);
      setAllowNetwork(false);
      setSelectedNode("");
      setSelectedEdge("");
      client.setQueryData([queryName, paperId, revisionId], value);
    },
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ["lite-usage", projectId] });
      void client.invalidateQueries({ queryKey: ["jobs", projectId] });
    },
  });
  const data = overview.data;
  const completed =
    !!data?.paper_card &&
    !!data.graph &&
    (data.status === "COMPLETED" || source === "model");
  const showingPrevious =
    source === "model" &&
    !!data?.display_result_id &&
    data.display_result_id !== data.id;
  const resultId = data?.display_result_id ?? data?.id ?? "";
  const collectKnowledge = useMutation({
    mutationFn: () =>
      knowledgeApi.collect({
        paper_id: paperId,
        source_kind: source === "model" ? "model_parse" : "local_revision",
        source_id: revisionId,
        overview_result_id: resultId,
      }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["knowledge"] }),
  });
  const understanding = useQuery({
    queryKey: ["concept-understanding", paperId, revisionId, resultId],
    queryFn: () => api.conceptUnderstanding(paperId, revisionId, resultId),
    enabled: connected && source === "local" && completed && !!resultId,
    retry: false,
  });
  useEffect(() => {
    if (
      previousStatus.current === "PENDING" &&
      data?.status &&
      data.status !== "PENDING"
    ) {
      void client.invalidateQueries({ queryKey: ["lite-usage", projectId] });
      void client.invalidateQueries({ queryKey: ["jobs", projectId] });
    }
    previousStatus.current = data?.status ?? undefined;
  }, [client, data?.status, projectId]);
  const layoutQuery = useQuery({
    queryKey: [layoutQueryName, paperId, resultId],
    queryFn: () =>
      source === "model"
        ? api.modelOverviewLayout(paperId, resultId)
        : api.overviewLayout(paperId, resultId),
    enabled: connected && !!resultId && completed,
  });
  const { mutate: persistLayout, error: layoutError } = useMutation({
    mutationFn: (value: OverviewLayout) => {
      const write = layoutWrites.current.then(() =>
        source === "model"
          ? api.saveModelOverviewLayout(paperId, value)
          : api.saveOverviewLayout(paperId, value),
      );
      layoutWrites.current = write.catch(() => undefined);
      return write;
    },
    onSuccess: (value) =>
      client.setQueryData(
        [layoutQueryName, paperId, value.overview_result_id],
        value,
      ),
  });
  const resetLayout = useMutation({
    mutationFn: (overviewResultId: string) => {
      if (layoutTimer.current !== null)
        window.clearTimeout(layoutTimer.current);
      pendingLayout.current = null;
      const write = layoutWrites.current.then(() =>
        source === "model"
          ? api.resetModelOverviewLayout(paperId, overviewResultId)
          : api.resetOverviewLayout(paperId, overviewResultId),
      );
      layoutWrites.current = write.catch(() => undefined);
      return write;
    },
    onSuccess: (value) => {
      client.setQueryData(
        [layoutQueryName, paperId, value.overview_result_id],
        value,
      );
      setLayout(null);
      setReset((current) => current + 1);
    },
  });
  useEffect(() => {
    if (!layout || !resultId || layout.overview_result_id !== resultId) return;
    pendingLayout.current = layout;
    layoutTimer.current = window.setTimeout(() => {
      pendingLayout.current = null;
      layoutTimer.current = null;
      persistLayout(layout);
    }, 500);
    return () => {
      if (layoutTimer.current !== null)
        window.clearTimeout(layoutTimer.current);
    };
  }, [layout, resultId, persistLayout]);
  useEffect(
    () => () => {
      const pending = pendingLayout.current;
      if (pending?.overview_result_id === resultId) {
        pendingLayout.current = null;
        persistLayout(pending);
      }
    },
    [resultId, persistLayout],
  );
  const graph = useMemo<GraphData | null>(
    () =>
      data?.graph
        ? {
            nodes: data.graph.nodes.map((node) => ({
              id: node.id,
              type: node.type,
              label_zh: node.label_zh,
              label_en: node.label_en,
              description_zh: node.description_zh,
              basis: node.basis,
              reading_level: understanding.data?.find(
                (concept) =>
                  concept.graph_node_id === node.id &&
                  concept.association_status === "CURRENT",
              )?.self_level,
              reading_check: understanding.data?.find(
                (concept) =>
                  concept.graph_node_id === node.id &&
                  concept.association_status === "CURRENT",
              )?.last_check_result,
              reading_unresolved: understanding.data?.find(
                (concept) =>
                  concept.graph_node_id === node.id &&
                  concept.association_status === "CURRENT",
              )?.has_unresolved_question,
            })),
            edges: data.graph.edges.map((edge) => ({
              id: edge.id,
              source: edge.source,
              target: edge.target,
              type: edge.type,
              relation: edge.type,
              basis: edge.basis,
            })),
          }
        : null,
    [data, understanding.data],
  );
  const selected = graph?.nodes.find((node) => node.id === selectedNode);
  const edge = graph?.edges.find((item) => item.id === selectedEdge);
  const edgeSource =
    edge && graph?.nodes.find((node) => node.id === edge.source);
  const edgeTarget =
    edge && graph?.nodes.find((node) => node.id === edge.target);
  const currentLayout =
    layout?.overview_result_id === resultId ? layout : layoutQuery.data;
  const rendererLayout = currentLayout
    ? {
        version:
          currentLayout.positions.length || currentLayout.viewport ? 1 : 0,
        pan_x: currentLayout.viewport?.x ?? 0,
        pan_y: currentLayout.viewport?.y ?? 0,
        zoom: currentLayout.viewport?.zoom ?? 1,
        positions: currentLayout.positions,
      }
    : { version: 0, pan_x: 0, pan_y: 0, zoom: 1, positions: [] };
  return (
    <section className="settings-card paper-overview" aria-label="论文概览">
      <div className="settings-title">
        <h3>论文概览</h3>
        {completed && <span className="pill">PaperCard + LightGraph</span>}
      </div>
      <p className="muted">
        PaperCard
        与轻量知识图谱由一次联合请求生成；图谱只保留短属性和关系，不生成
        Evidence 节点。
      </p>
      {overview.isPending && <p role="status">正在读取概览缓存…</p>}
      {overview.isError && (
        <p role="alert" className="error-text">
          {errorText(overview.error)}
        </p>
      )}
      {overview.isSuccess && !data && (
        <p className="quality-note">
          尚未生成知识卡片和轻量图谱。允许一次模型调用后，可在这里生成论文概览。
        </p>
      )}
      {data?.status === "PENDING" && (
        <p role="status">正在生成概览…章节内容仍可继续阅读。</p>
      )}
      {data?.status === "FAILED" && (
        <div role="alert" className="quality-note">
          <strong>概览生成失败</strong>
          <p>{data.error || data.error_code || "模型响应未通过校验"}</p>
        </div>
      )}
      {showingPrevious && (
        <p role="status" className="quality-note">
          {data?.status === "PENDING"
            ? "正在重新生成概览，以下保留上一次成功的知识卡片与图谱。"
            : "本次概览生成未完成，以下显示上一次成功的知识卡片与图谱。"}
        </p>
      )}
      {data?.status !== "PENDING" && (
        <div className="import-controls">
          <label>
            <input
              type="checkbox"
              checked={allowNetwork}
              onChange={(event) => setAllowNetwork(event.target.checked)}
            />
            允许向已配置模型发送本篇论文内容
          </label>
          <button
            className="button primary"
            disabled={!connected || !allowNetwork || generate.isPending}
            onClick={() =>
              generate.mutate({
                retryFailed: data?.status === "FAILED",
                forceRegenerate: completed,
              })
            }
          >
            {generate.isPending
              ? "正在提交…"
              : completed || data?.status === "FAILED"
                ? "重新生成概览"
                : "生成论文概览"}
          </button>
        </div>
      )}
      {generate.isError && (
        <p role="alert" className="error-text">
          {errorText(generate.error)}
        </p>
      )}
      {layoutError && (
        <p role="alert" className="error-text">
          布局保存失败：{errorText(layoutError)}
        </p>
      )}
      {resetLayout.isError && (
        <p role="alert" className="error-text">
          布局重置失败：{errorText(resetLayout.error)}
        </p>
      )}
      {completed && data?.paper_card && graph && (
        <>
          <div className="import-controls">
            <button
              className="button secondary"
              disabled={
                !connected ||
                collectKnowledge.isPending ||
                collectKnowledge.isSuccess
              }
              onClick={() => collectKnowledge.mutate()}
            >
              {collectKnowledge.isSuccess
                ? "已存入知识库"
                : "加入研究内容知识库"}
            </button>
            <small className="muted">收藏当前概览，不调用模型。</small>
          </div>
          {collectKnowledge.isSuccess && (
            <p role="status">
              已收藏到研究内容知识库，当前概览与图谱会独立保存。
            </p>
          )}
          {collectKnowledge.error && (
            <p role="alert" className="error-text">
              {errorText(collectKnowledge.error)}
            </p>
          )}
          <Card
            card={data.paper_card}
            cacheHit={data.cache_hit}
            usage={showingPrevious ? null : data.usage}
          />
          <div className="graph-layout">
            <div className="graph-canvas">
              <div className="section-toolbar">
                <h4>轻量图谱 · LightGraph</h4>
                <button
                  className="text-button"
                  disabled={resetLayout.isPending}
                  onClick={() => resetLayout.mutate(resultId)}
                >
                  重置布局
                </button>
              </div>
              <div className="graph-view projection-canvas">
                {layoutQuery.isPending ? (
                  <p role="status">正在读取图谱布局…</p>
                ) : layoutQuery.isError ? (
                  <p role="alert">布局读取失败，请刷新后重试。</p>
                ) : (
                  <ForceGraph
                    key={`${resultId}:${reset}`}
                    graph={graph}
                    layout={rendererLayout}
                    selected={selectedNode}
                    language="both"
                    reset={reset}
                    pinRequest={null}
                    viewKey={resultId}
                    onSelect={(id) => {
                      setSelectedNode(id);
                      setSelectedEdge("");
                    }}
                    onEdge={(id) => {
                      setSelectedEdge(id);
                      setSelectedNode("");
                    }}
                    onPositions={(positions) => {
                      if (resetLayout.isPending) return;
                      setLayout((old) => ({
                        overview_result_id: resultId,
                        positions,
                        viewport:
                          (old?.overview_result_id === resultId
                            ? old.viewport
                            : undefined) ??
                          layoutQuery.data?.viewport ??
                          undefined,
                      }));
                    }}
                    onViewport={(viewport) => {
                      if (resetLayout.isPending) return;
                      setLayout((old) => ({
                        overview_result_id: resultId,
                        positions:
                          (old?.overview_result_id === resultId
                            ? old.positions
                            : undefined) ??
                          layoutQuery.data?.positions ??
                          [],
                        viewport,
                      }));
                    }}
                  />
                )}
              </div>
              <GraphLegend />
              {source === "local" && (
                <div className="graph-reading-legend" aria-label="阅读状态图例">
                  <span>实线圈：自认为已理解</span>
                  <span>虚线圈：部分理解 / 还不确定</span>
                  <span>外侧光环：待解问题 / 需复查</span>
                </div>
              )}
            </div>
            <aside className="graph-detail" aria-label="图谱详情">
              {selected ? (
                <>
                  <h4>{selected.label_zh}</h4>
                  {selected.label_en && (
                    <p className="muted">{selected.label_en}</p>
                  )}
                  <p>{selected.description_zh}</p>
                  <small>
                    {selected.basis === "EXPLICIT"
                      ? "原文明确提及"
                      : "模型归纳"}
                  </small>
                  {understanding.isError && (
                    <p role="alert" className="error-text">
                      阅读状态读取失败：{understanding.error.message}
                    </p>
                  )}
                  {understanding.data?.find(
                    (concept) =>
                      concept.graph_node_id === selected.id &&
                      concept.association_status === "CURRENT",
                  ) && (
                    <ConceptReadingDetails
                      key={`${resultId}:${selected.id}`}
                      concept={understanding.data.find(
                        (concept) =>
                          concept.graph_node_id === selected.id &&
                          concept.association_status === "CURRENT",
                      )!}
                      paperId={paperId}
                      revisionId={revisionId}
                      resultId={resultId}
                      onOpenSection={onOpenSection}
                      onAskParagraph={onAskParagraph}
                    />
                  )}
                </>
              ) : edge ? (
                <>
                  <h4>关系</h4>
                  <p>{edge.type}</p>
                  <p className="muted">
                    {edgeSource?.label_zh ||
                      edgeSource?.label_en ||
                      edge.source}{" "}
                    →{" "}
                    {edgeTarget?.label_zh ||
                      edgeTarget?.label_en ||
                      edge.target}
                  </p>
                </>
              ) : (
                <p className="muted">
                  点击节点查看详情，点击关系查看连接类型。
                </p>
              )}
            </aside>
          </div>
          {understanding.data?.some(
            (concept) => concept.association_status === "NEEDS_RELINK",
          ) && (
            <details className="reading-warnings">
              <summary>旧图谱阅读记录待重新关联</summary>
              <p className="muted">
                以下概念的版本或语义已变化，原自评与记录保留，不会自动指向当前节点。
              </p>
              <ul>
                {understanding.data
                  .filter(
                    (concept) => concept.association_status === "NEEDS_RELINK",
                  )
                  .map((concept) => (
                    <li
                      key={
                        concept.id ??
                        `${concept.overview_result_id}:${concept.graph_node_id}`
                      }
                    >
                      {concept.node_label_zh ||
                        concept.node_label_en ||
                        concept.graph_node_id}{" "}
                      · {assessmentLabels[concept.self_level]}
                      {concept.note_zh ? ` · ${concept.note_zh}` : ""}
                    </li>
                  ))}
              </ul>
            </details>
          )}
        </>
      )}
    </section>
  );
}

function ConceptReadingDetails({
  concept,
  paperId,
  revisionId,
  resultId,
  onOpenSection,
  onAskParagraph,
}: {
  concept: ConceptUnderstanding;
  paperId: string;
  revisionId: string;
  resultId: string;
  onOpenSection?: PaperOverviewProps["onOpenSection"];
  onAskParagraph?: PaperOverviewProps["onAskParagraph"];
}) {
  const [level, setLevel] = useState<SelfAssessment>(concept.self_level);
  const [note, setNote] = useState(concept.note_zh);
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: () =>
      api.saveConceptUnderstanding(paperId, concept.graph_node_id, {
        document_version_id: revisionId,
        overview_result_id: resultId,
        self_level: level,
        note_zh: note,
      }),
    retry: false,
    onSuccess: () =>
      void client.invalidateQueries({
        queryKey: ["concept-understanding", paperId, revisionId],
      }),
  });
  const related = useQuery({
    queryKey: [
      "concept-reading-sections",
      paperId,
      revisionId,
      resultId,
      concept.graph_node_id,
      concept.related_sections,
    ],
    queryFn: () =>
      Promise.all(
        concept.related_sections.map(async (section) => {
          const [state, source] = await Promise.all([
            api.readingState(paperId, section.section_id, revisionId),
            api.sectionParagraphs(paperId, section.section_id, revisionId),
          ]);
          return { ...section, state, paragraphs: source.paragraphs };
        }),
      ),
    enabled: concept.related_sections.length > 0,
    retry: false,
  });
  return (
    <div className="concept-reading-controls">
      <h5>我的概念理解</h5>
      <label>
        概念理解自评
        <select
          value={level}
          onChange={(event) => setLevel(event.target.value as SelfAssessment)}
        >
          {Object.entries(assessmentLabels).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <p className="muted">
        模型理解检查：{checkLabels[concept.last_check_result]}
      </p>
      {concept.last_check_note_zh && <p>{concept.last_check_note_zh}</p>}
      {concept.has_unresolved_question && (
        <span className="concept-status-badge">关联阅读中有待解问题</span>
      )}
      <label>
        我的概念笔记
        <textarea
          value={note}
          maxLength={1600}
          onChange={(event) => setNote(event.target.value)}
        />
      </label>
      <button
        className="button secondary"
        disabled={save.isPending}
        onClick={() => save.mutate()}
      >
        {save.isPending ? "正在保存…" : "保存理解记录"}
      </button>
      {save.isSuccess && (
        <p role="status" className="muted">
          阅读记录已保存，本次模型调用 0。
        </p>
      )}
      {save.error && (
        <p role="alert" className="error-text">
          {save.error.message}
        </p>
      )}
      <h5>关联章节与待解问题</h5>
      {related.isError && (
        <p role="alert" className="error-text">
          {related.error.message}
        </p>
      )}
      {!concept.related_sections.length && (
        <p className="muted">
          尚无已记录的章节关联，可从双栏精读中的关联概念进入。
        </p>
      )}
      {related.data?.map((section) => (
        <div key={section.section_id}>
          <button
            className="text-button"
            onClick={() => onOpenSection?.(section.section_id)}
            disabled={!onOpenSection}
          >
            {section.title}
          </button>
          <small className="muted">
            {" "}
            ·{" "}
            {section.state.progress === "COMPLETED"
              ? "已读完"
              : section.state.progress === "READING"
                ? "阅读中"
                : "未开始"}{" "}
            · {assessmentLabels[section.state.self_assessment]}
          </small>
          {section.state.questions
            .filter((question) => !question.resolved)
            .map((question, index) => {
              const paragraph = section.paragraphs.find(
                (p) => p.paragraph_id === question.paragraph_id,
              );
              return (
                <div className="paragraph-question" key={index}>
                  <p>{question.text}</p>
                  {paragraph && (
                    <>
                      <button
                        className="text-button"
                        disabled={!onOpenSection}
                        onClick={() =>
                          onOpenSection?.(
                            section.section_id,
                            paragraph.paragraph_id,
                          )
                        }
                      >
                        返回对应段落
                      </button>
                      {" · "}
                      <button
                        className="text-button"
                        disabled={!onAskParagraph}
                        onClick={() =>
                          onAskParagraph?.(section.section_id, paragraph)
                        }
                      >
                        对该段落提问
                      </button>
                    </>
                  )}
                </div>
              );
            })}
        </div>
      ))}
    </div>
  );
}

function Card({
  card,
  cacheHit,
  usage,
}: {
  card: NonNullable<OverviewView["paper_card"]>;
  cacheHit: boolean;
  usage: OverviewView["usage"];
}) {
  return (
    <article className="paper-card">
      <div className="settings-title">
        <h4>知识卡片 · PaperCard</h4>
        {cacheHit && <span className="pill">缓存命中</span>}
      </div>
      <dl>
        <dt>研究问题</dt>
        <dd>{card.research_question}</dd>
        <dt>动机</dt>
        <dd>{card.motivation}</dd>
        <dt>方法概述</dt>
        <dd>{card.method_summary}</dd>
      </dl>
      <List title="主要贡献" values={card.contributions} />
      <List title="主要发现" values={card.main_findings} />
      <List title="局限" values={card.limitations} />
      {usage && (
        <small className="muted">
          生成此概览的 Token：{usage.total_tokens ?? "未知"}
        </small>
      )}
      {cacheHit && <p className="muted">本次使用缓存，新增模型调用为 0。</p>}
    </article>
  );
}
function List({ title, values }: { title: string; values: string[] }) {
  return values.length ? (
    <div>
      <strong>{title}</strong>
      <ul>
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </div>
  ) : null;
}
