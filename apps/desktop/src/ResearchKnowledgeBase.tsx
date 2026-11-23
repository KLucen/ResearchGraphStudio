import { useEffect, useMemo, useRef, useState } from "react";
import {
  useIsMutating,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  ArrowUpRight,
  BookOpen,
  Bookmark,
  Check,
  Download,
  FolderCog,
  FolderPlus,
  GitBranch,
  Library,
  LoaderCircle,
  Maximize2,
  Minimize2,
  Plus,
  Search,
  Settings2,
} from "lucide-react";
import type { Project } from "./api";
import { archiveApi } from "./archiveApi";
import { ForceGraph, type GraphContextTarget } from "./ForceGraph";
import { useContextMenu, type ContextMenuEvent } from "./ContextMenu";
import { getGraphAppearance } from "./graphAppearance";
import {
  graphNodeKind,
  type GraphData,
  type GraphEdge,
  type GraphNode,
  type GraphPosition,
} from "./graphTypes";
import {
  knowledgeApi,
  knowledgeErrorMessage,
  type KnowledgeCollection,
  type KnowledgeLayout,
  type KnowledgePaper,
  type KnowledgeRelation,
  type KnowledgeReport,
  type KnowledgeSettings,
  type KnowledgeSourceRef,
  type KnowledgeVersion,
} from "./knowledgeApi";
import { knowledgeNodeText } from "./knowledgeGraphLabels";
import {
  topicContextCandidates,
  topicGraphApi,
  type ExternalTopicPaper,
} from "./knowledgeTopicGraph";
import { useGraphFullscreen } from "./useGraphFullscreen";
import { handleWorkspaceFind } from "./workspaceSearchShortcut";
import { KnowledgeDialog } from "./KnowledgeDialog";
import { PaperTopicAssignment, TopicManagement } from "./TopicManagement";
import "./researchKnowledgeBase.css";

const inputBudgetExceeded = (text: string) =>
  text.includes("KNOWLEDGE_INPUT_BUDGET_EXCEEDED");
const errorText = (error: unknown) => {
  const text = error instanceof Error ? error.message : String(error);
  return knowledgeErrorMessage(text);
};
const date = (value: string) =>
  new Date(value).toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
const localRecoveryAudit = (version?: KnowledgeVersion | null) => {
  const coverage = version?.content.coverage;
  if (!coverage || typeof coverage !== "object") return null;
  const value = coverage as Record<string, unknown>;
  if (value.status !== "partial") return null;
  const audit = value.local_recovery;
  return audit && typeof audit === "object"
    ? (audit as Record<string, unknown>)
    : {};
};
const partialKnowledgeLabel = (version?: KnowledgeVersion | null) => {
  const audit = localRecoveryAudit(version);
  if (!audit) return "";
  const nodes = audit.excluded_node_indices;
  const edges = audit.excluded_edge_indices;
  const excluded = [
    Array.isArray(nodes) && nodes.length ? `${nodes.length} 个知识节点` : "",
    Array.isArray(edges) && edges.length ? `${edges.length} 条关系` : "",
  ].filter(Boolean);
  return excluded.length
    ? `部分知识 · 已隔离 ${excluded.join("和 ")}`
    : "部分知识 · 内容不完整";
};
const active = (status: string) =>
  ["queued", "running", "pending"].includes(status);
const statusLabels: Record<string, string> = {
  queued: "等待处理",
  running: "正在处理",
  succeeded: "已完成",
  failed: "处理失败",
  interrupted: "已中断",
  paused: "已暂停",
  completed: "已完成",
  partial: "部分完成",
  no_candidates: "暂无可比较论文",
};
const scopeLabels: Record<string, string> = {
  project: "同研究项目",
  all: "全知识库",
  collection: "指定专题",
};
const relationLabels: Record<string, string> = {
  SAME_PROBLEM: "共同研究问题",
  SHARED_QUESTION: "共同研究问题",
  RELATED_CONCEPT: "概念联系",
  RELATED_METHOD: "方法相关",
  METHOD_RELATED: "方法相关",
  COMPLEMENTARY: "方法互补",
  COMPLEMENTARY_METHODS: "方法互补",
  COMPARABLE_RESULT: "结果可比较",
  COMPARABLE_RESULTS: "结果可比较",
  RESEARCH_OPPORTUNITY: "研究线索",
};
const graphLabelLanguageKey = "rgs.knowledge.graph-label-language.v1";
type GraphLabelLanguage = "zh" | "en" | "both";

function savedGraphLabelLanguage(): GraphLabelLanguage {
  try {
    const saved = localStorage.getItem(graphLabelLanguageKey);
    return saved === "en" || saved === "both" ? saved : "zh";
  } catch {
    return "zh";
  }
}

function nodeReferences(
  node: GraphNode,
  version: KnowledgeVersion,
): KnowledgeSourceRef[] {
  const refs =
    (node as GraphNode & { source_refs?: KnowledgeSourceRef[] }).source_refs ??
    [];
  return refs.map((ref) => {
    const source = version.content.sources?.find(
      (item) => item.ref === ref.source_id,
    );
    return {
      ...source,
      ...ref,
      source_kind: version.source_kind,
      section_id: String(source?.chapter_title ?? source?.chapter_ref ?? ""),
      source_ref: ref.source_id,
      page_start: source?.page_start ?? null,
    };
  });
}

function downloadJson(value: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `research-knowledge-${new Date().toISOString().slice(0, 10)}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function SourceReferences({
  refs,
  label = "原文依据",
}: {
  refs: KnowledgeSourceRef[];
  label?: string;
}) {
  return (
    <div className="knowledge-source-refs">
      <h4>{label}</h4>
      {refs.length ? (
        refs
          .map((item) => {
            const source = item.source as KnowledgeSourceRef | undefined;
            const origin = source?.origin as
              Record<string, unknown> | undefined;
            return {
              ...source,
              ...item,
              source_kind:
                item.source_kind ??
                (origin?.segment_id ? "model_parse" : "local_revision"),
              section_id:
                item.section_id ??
                String(source?.chapter_title ?? source?.chapter_ref ?? ""),
            };
          })
          .map((ref, index) => (
            <details key={String(ref.id ?? ref.source_ref ?? index)}>
              <summary>
                {ref.source_kind === "model_parse" ||
                ref.source_kind === "model_segment" ||
                ref.segment_id
                  ? "模型提取材料"
                  : "本地解析材料"}
                {typeof (ref.page ?? ref.page_start) === "number"
                  ? ` · 第 ${ref.page ?? ref.page_start} 页`
                  : ""}
                {ref.section_id ? ` · 章节 ${ref.section_id}` : ""}
              </summary>
              <blockquote>
                {ref.quote ||
                  ref.quote_en ||
                  ref.text ||
                  "此条来源未提供可显示的摘录。"}
              </blockquote>
              <small>
                {String(ref.source_ref ?? ref.id ?? ref.source_id ?? "")}
              </small>
            </details>
          ))
      ) : (
        <p className="muted">
          历史概览尚无逐项原文定位；需生成带来源知识后才可用于联系分析。
        </p>
      )}
    </div>
  );
}

type RelationFocus = { id: string; reportId: string };
type MapLookup = {
  paperId: string;
  otherPaperId?: string;
  relation?: RelationFocus;
  reportId: string;
};

const mapPageSize = 12;
const paperPageSize = 50;
const expandMapPage = "all";
const noExternalTopicPapers: ExternalTopicPaper[] = [];
const mapKnowledgeKinds = [
  "RESEARCH_QUESTION",
  "CONCEPT",
  "METHOD",
  "CONTRIBUTION",
  "FINDING",
];

function mergeMapPositions(saved: GraphPosition[], visible: GraphPosition[]) {
  const positions = new Map(
    saved.map((position) => [position.node_id, position]),
  );
  const visibleIds = new Set<string>();
  for (const position of visible) {
    visibleIds.add(position.node_id);
    positions.set(position.node_id, position);
  }
  const entries = [...positions.values()];
  // Keep the saved projection within the layout endpoint's position limit.
  if (entries.length <= 2000) return entries;
  return entries
    .sort(
      (a, b) =>
        Number(b.pinned) - Number(a.pinned) ||
        Number(visibleIds.has(b.node_id)) - Number(visibleIds.has(a.node_id)),
    )
    .slice(0, 2000);
}

function KnowledgeMap({
  focusedPaper,
  focusedRelation,
  onOpenReport,
  papers,
  reports,
  connected,
  collectionId,
  search,
  onSearch,
  viewKey,
  hiddenKinds,
  onToggleKind,
  onSelectPaper,
}: {
  focusedPaper: string;
  focusedRelation: RelationFocus | null;
  onOpenReport: (id: string) => void;
  papers: KnowledgePaper[];
  reports: KnowledgeReport[];
  connected: boolean;
  collectionId: string;
  search?: string;
  onSearch: (value: string) => void;
  viewKey: string;
  hiddenKinds: ReadonlySet<string>;
  onToggleKind: (kind: string) => void;
  onSelectPaper: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(expandMapPage);
  const expansion =
    expanded === "" || papers.some((paper) => paper.id === expanded)
      ? expanded
      : expandMapPage;
  const [selected, setSelected] = useState(
    focusedPaper && !focusedRelation ? `paper:${focusedPaper}` : "",
  );
  const [selectedEdge, setSelectedEdge] = useState(
    focusedRelation ? `cross:${focusedRelation.id}` : "",
  );
  const [fit, setFit] = useState(0);
  const [pinRequest, setPinRequest] = useState<{
    id: string;
    seq: number;
  } | null>(null);
  const [language, setLanguage] = useState(savedGraphLabelLanguage);
  const [showExternal, setShowExternal] = useState(false);
  const showTopicContext = !!collectionId && showExternal;
  const candidates = useMemo(
    () => (showTopicContext ? topicContextCandidates(papers, reports) : null),
    [papers, reports, showTopicContext],
  );
  const external = useQuery({
    queryKey: ["knowledge", "topic-context", collectionId, candidates?.ids],
    queryFn: () =>
      topicGraphApi.externalPapers(collectionId, candidates?.ids ?? []),
    enabled: connected && !!candidates?.ids.length,
  });
  const externalPapers =
    (showTopicContext ? external.data?.items : null) ?? noExternalTopicPapers;
  const { openContextMenu, contextMenu } = useContextMenu();
  const {
    containerRef,
    toggleRef,
    mode: fullscreenMode,
    toggle: toggleFullscreen,
  } = useGraphFullscreen();
  function changeLanguage(value: string) {
    if (value !== "zh" && value !== "en" && value !== "both") return;
    setLanguage(value);
    try {
      localStorage.setItem(graphLabelLanguageKey, value);
    } catch {
      /* Keep the current selection available for this view. */
    }
  }
  const key = `library:${viewKey}`;
  const client = useQueryClient();
  const layoutKey = ["knowledge", "layout", key];
  const layout = useQuery({
    queryKey: layoutKey,
    queryFn: () => knowledgeApi.layout(key),
    enabled: connected,
  });
  const [editedLayout, setEditedLayout] = useState<KnowledgeLayout | null>(
    null,
  );
  const latestLayout = useRef<KnowledgeLayout | null>(null);
  const pending = useRef<KnowledgeLayout | null>(null);
  const timer = useRef<number | null>(null);
  const pendingSaves = useIsMutating({ mutationKey: layoutKey, exact: true });
  const [openedDuringSave] = useState(() => pendingSaves > 0);
  const save = useMutation({
    mutationKey: layoutKey,
    scope: { id: key },
    mutationFn: async (value: KnowledgeLayout) => {
      const saved = await knowledgeApi.saveLayout(value);
      const savedKey = ["knowledge", "layout", value.view_key];
      await client.cancelQueries({ queryKey: savedKey, exact: true });
      client.setQueryData(savedKey, saved);
    },
  });
  const persist = useRef(save.mutate);
  useEffect(() => {
    persist.current = save.mutate;
  }, [save.mutate]);
  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
      if (pending.current) persist.current(pending.current);
      pending.current = null;
    },
    [key],
  );
  const updateLayout = (part: Partial<KnowledgeLayout["layout"]>) => {
    const current = (latestLayout.current ?? layout.data)?.layout;
    const value = {
      view_key: key,
      layout: {
        positions: part.positions
          ? mergeMapPositions(current?.positions ?? [], part.positions)
          : (current?.positions ?? []),
        viewport: part.viewport ?? current?.viewport ?? null,
      },
    };
    latestLayout.current = value;
    pending.current = value;
    setEditedLayout(value);
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      const value = pending.current;
      pending.current = null;
      if (value) save.mutate(value);
    }, 600);
  };
  const data = useMemo(() => {
    const graph: GraphData = { nodes: [], edges: [] };
    const details = new Map<
      string,
      {
        paperId: string;
        version: KnowledgeVersion | null;
        node: GraphNode;
      }
    >();
    const versions = new Map<
      string,
      { id: string; external?: ExternalTopicPaper }
    >();
    const relationMap = new Map<
      string,
      {
        relation: KnowledgeRelation;
        report: KnowledgeReport;
        outsideTopic: boolean;
      }
    >();
    const crossEdges = new Map<
      string,
      { edge: GraphEdge; relation: KnowledgeRelation; report: KnowledgeReport }
    >();
    for (const paper of papers) {
      const version = paper.current_version;
      const root = `paper:${paper.id}`;
      const rootNode: GraphNode = {
        id: root,
        type: "PAPER",
        label_zh: paper.title,
      };
      graph.nodes.push(rootNode);
      details.set(root, { paperId: paper.id, version, node: rootNode });
      if (!version) continue;
      versions.set(version.id, paper);
      if (expansion !== expandMapPage && expansion !== paper.id) continue;
      for (const node of version.content.graph?.nodes ?? []) {
        const kind = graphNodeKind(node);
        if (kind === "PAPER" || hiddenKinds.has(kind)) continue;
        const id = `version:${version.id}:${node.id}`;
        graph.nodes.push({ ...node, id });
        details.set(id, { paperId: paper.id, version, node });
        graph.edges.push({
          id: `owns:${id}`,
          source: root,
          target: id,
          type: "CONTAINS",
          label_zh: "论文归属",
        });
      }
      for (const edge of version.content.graph?.edges ?? []) {
        const source = `version:${version.id}:${edge.source}`,
          target = `version:${version.id}:${edge.target}`;
        if (details.has(source) && details.has(target))
          graph.edges.push({
            ...edge,
            id: `version:${version.id}:${edge.id}`,
            source,
            target,
          });
      }
    }
    for (const paper of externalPapers) {
      if (!details.has(`paper:${paper.id}`) && !versions.has(paper.version_id))
        versions.set(paper.version_id, { id: paper.id, external: paper });
    }
    const addExternalRoot = (paper?: ExternalTopicPaper) => {
      if (!paper) return;
      const id = `paper:${paper.id}`;
      if (details.has(id)) return;
      const node: GraphNode = {
        id,
        type: "PAPER",
        label_zh: paper.title,
        outside_topic: true,
      };
      graph.nodes.push(node);
      details.set(id, { paperId: paper.id, version: null, node });
    };
    for (const report of reports) {
      if (report.stale) continue;
      for (const relation of report.relations ?? []) {
        const a = versions.get(relation.source_version_id ?? ""),
          b = versions.get(relation.target_version_id ?? "");
        if (!a || !b || (a.external && b.external)) continue;
        const sourceDetail = `version:${relation.source_version_id}:${relation.source_node_id}`;
        const targetDetail = `version:${relation.target_version_id}:${relation.target_node_id}`;
        const endpoints = JSON.stringify([
          sourceDetail,
          targetDetail,
          relation.type,
        ]);
        const currentEdge = crossEdges.get(endpoints);
        if (currentEdge) {
          const currentFocused =
            currentEdge.relation.id === focusedRelation?.id &&
            currentEdge.report.id === focusedRelation?.reportId;
          const nextFocused =
            relation.id === focusedRelation?.id &&
            report.id === focusedRelation?.reportId;
          if (
            currentFocused ||
            (!nextFocused && currentEdge.report.created_at >= report.created_at)
          )
            continue;
        }
        addExternalRoot(a.external);
        addExternalRoot(b.external);
        crossEdges.set(endpoints, {
          edge: {
            id: `cross:${relation.id}`,
            source: details.has(sourceDetail) ? sourceDetail : `paper:${a.id}`,
            target: details.has(targetDetail) ? targetDetail : `paper:${b.id}`,
            type: relation.type,
            label_zh: relationLabels[relation.type] ?? relation.type,
            is_dashed: true,
            outside_topic: !!(a.external || b.external),
          },
          relation,
          report,
        });
      }
    }
    for (const { edge, relation, report } of crossEdges.values()) {
      graph.edges.push(edge);
      relationMap.set(edge.id, {
        relation,
        report,
        outsideTopic: !!edge.outside_topic,
      });
    }
    return { graph, details, relationMap };
  }, [
    papers,
    reports,
    expansion,
    hiddenKinds,
    focusedRelation,
    externalPapers,
  ]);
  const current = data.details.get(selected);
  const detailText = current && knowledgeNodeText(current.node, language);
  const cross = data.relationMap.get(selectedEdge);
  const stored = (editedLayout ?? layout.data)?.layout;

  function selectNode(id: string) {
    setSelected(id);
    setSelectedEdge("");
    const detail = data.details.get(id);
    if (
      detail &&
      !detail.node.outside_topic &&
      graphNodeKind(detail.node) === "PAPER" &&
      expansion !== expandMapPage
    )
      setExpanded(detail.paperId);
  }

  function selectEdge(id: string) {
    setSelectedEdge(id);
    setSelected("");
  }

  function showGraphMenu(event: ContextMenuEvent, target: GraphContextTarget) {
    if (target.kind === "node") {
      const detail = data.details.get(target.id);
      if (!detail) return;
      openContextMenu(event, "知识地图节点操作", [
        { label: "查看节点详情", action: () => selectNode(target.id) },
        { label: "打开论文知识", action: () => onSelectPaper(detail.paperId) },
        ...(!detail.node.outside_topic
          ? [
              {
                label: target.pinned ? "取消固定节点" : "固定节点",
                action: () =>
                  setPinRequest((previous) => ({
                    id: target.id,
                    seq: (previous?.seq ?? 0) + 1,
                  })),
              },
            ]
          : []),
      ]);
      return;
    }

    if (target.kind === "edge") {
      const connection = data.relationMap.get(target.id);
      if (connection) {
        openContextMenu(event, "知识地图关系操作", [
          { label: "查看关系详情", action: () => selectEdge(target.id) },
          {
            label: "打开联系汇报",
            action: () => onOpenReport(connection.report.id),
          },
        ]);
      } else {
        const edge = data.graph.edges.find((item) => item.id === target.id);
        if (edge)
          openContextMenu(event, "知识地图关系操作", [
            { label: "查看起点", action: () => selectNode(edge.source) },
            { label: "查看终点", action: () => selectNode(edge.target) },
          ]);
      }
      return;
    }

    openContextMenu(event, "知识地图画布操作", [
      { label: "聚焦图谱", action: () => setFit((value) => value + 1) },
      {
        label: fullscreenMode ? "退出全屏" : "全屏",
        action: () => void toggleFullscreen(),
      },
    ]);
  }
  return (
    <div
      className="knowledge-map"
      ref={containerRef}
      data-fullscreen={fullscreenMode ?? undefined}
      role={fullscreenMode ? "dialog" : undefined}
      aria-modal={fullscreenMode ? true : undefined}
      aria-label={fullscreenMode ? "知识地图全屏" : undefined}
    >
      <div className="knowledge-map-canvas">
        <div className="knowledge-map-toolbar">
          {fullscreenMode && search !== undefined && (
            <label className="knowledge-search knowledge-map-search">
              <Search size={15} aria-hidden="true" />
              <input
                type="search"
                data-knowledge-search
                aria-label="搜索知识库"
                placeholder="搜索论文、研究问题与概念"
                maxLength={300}
                value={search}
                onChange={(event) => onSearch(event.currentTarget.value)}
              />
            </label>
          )}
          <label className="knowledge-map-paper-choice">
            展开论文{" "}
            <select
              aria-label="展开论文"
              value={expansion}
              onChange={(event) => {
                const choice = event.target.value;
                setExpanded(choice);
                setSelectedEdge("");
                setSelected(
                  choice && choice !== expandMapPage ? `paper:${choice}` : "",
                );
              }}
            >
              <option value={expandMapPage}>展开本页所有论文</option>
              <option value="">仅显示论文与汇总联系</option>
              {papers.map((paper) => (
                <option key={paper.id} value={paper.id}>
                  {paper.title}
                </option>
              ))}
            </select>
          </label>
          <div
            className="knowledge-map-tools"
            role="group"
            aria-label="图谱视图"
          >
            <label>
              节点语言
              <select
                value={language}
                onChange={(event) => changeLanguage(event.target.value)}
              >
                <option value="zh">中文</option>
                <option value="en">English</option>
                <option value="both">中英双语</option>
              </select>
            </label>
            <button
              type="button"
              className="text-button"
              onClick={() => setFit((value) => value + 1)}
            >
              聚焦图谱
            </button>
            <button
              ref={toggleRef}
              type="button"
              className="text-button"
              onClick={toggleFullscreen}
            >
              {fullscreenMode ? (
                <>
                  <Minimize2 size={14} aria-hidden="true" /> 退出全屏
                </>
              ) : (
                <>
                  <Maximize2 size={14} aria-hidden="true" /> 全屏
                </>
              )}
            </button>
          </div>
          <fieldset className="knowledge-map-kinds">
            <legend className="sr-only">显示类型</legend>
            <div>
              <span aria-hidden="true">显示类型</span>
              {mapKnowledgeKinds.map((kind) => {
                const appearance = getGraphAppearance(kind);
                return (
                  <label key={kind}>
                    <input
                      type="checkbox"
                      aria-label={`显示${appearance.label}`}
                      checked={!hiddenKinds.has(kind)}
                      style={{ accentColor: appearance.color }}
                      onChange={() => {
                        if (current && graphNodeKind(current.node) === kind)
                          setSelected("");
                        onToggleKind(kind);
                      }}
                    />
                    {appearance.label}
                  </label>
                );
              })}
            </div>
          </fieldset>
          {collectionId && (
            <div className="knowledge-topic-map-tools">
              <label>
                <input
                  type="checkbox"
                  checked={showTopicContext}
                  disabled={!connected}
                  onChange={(event) => {
                    if (!event.currentTarget.checked) {
                      if (current?.node.outside_topic) setSelected("");
                      if (cross?.outsideTopic) setSelectedEdge("");
                    }
                    setShowExternal(event.currentTarget.checked);
                  }}
                />
                显示专题外联系
              </label>
              {showTopicContext && !external.isError && (
                <span role="status">
                  {candidates?.ids.length && external.isPending
                    ? "正在读取专题外联系…"
                    : candidates?.limited || external.data?.has_more
                      ? "当前页关联论文较多，地图仅预览部分专题外联系。"
                      : data.graph.nodes.some((node) => node.outside_topic)
                        ? "专题外论文只显示标题。"
                        : "当前页暂无可显示的专题外联系。"}
                </span>
              )}
              {showTopicContext && external.isError && (
                <span role="alert">
                  专题外联系读取失败：{errorText(external.error)}{" "}
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => void external.refetch()}
                  >
                    重试
                  </button>
                </span>
              )}
            </div>
          )}
        </div>
        <div className="knowledge-graph-view">
          {layout.isPending ||
          (openedDuringSave && pendingSaves > 0 && !editedLayout) ? (
            <p role="status">正在读取地图…</p>
          ) : layout.isError ? (
            <p role="alert">地图布局读取失败：{errorText(layout.error)}</p>
          ) : (
            !!papers.length && (
              <ForceGraph
                graph={data.graph}
                layout={{
                  version: stored?.positions.length || stored?.viewport ? 1 : 0,
                  positions: stored?.positions ?? [],
                  zoom: stored?.viewport?.zoom ?? 1,
                  pan_x: stored?.viewport?.x ?? 0,
                  pan_y: stored?.viewport?.y ?? 0,
                }}
                selected={current ? selected : ""}
                selectedEdge={cross ? selectedEdge : ""}
                language={language}
                appearance="knowledge"
                reset={0}
                pinRequest={pinRequest}
                viewKey={key}
                fitRequest={fit}
                persistSettledPositions={!showTopicContext}
                onSelect={selectNode}
                onEdge={selectEdge}
                onGraphContextMenu={showGraphMenu}
                onPositions={(positions) =>
                  updateLayout({
                    positions: positions.filter(
                      (position) =>
                        data.details.has(position.node_id) &&
                        !data.details.get(position.node_id)?.node.outside_topic,
                    ),
                  })
                }
                onViewport={(viewport) => updateLayout({ viewport })}
              />
            )
          )}
        </div>
        <div className="knowledge-map-legend" aria-label="知识地图图例">
          {["PAPER", ...mapKnowledgeKinds].map((kind) => {
            const appearance = getGraphAppearance(kind);
            return (
              <span key={kind}>
                <i
                  style={{ background: appearance.color }}
                  aria-hidden="true"
                />
                {appearance.label}
              </span>
            );
          })}
          <span>
            <b className="knowledge-legend-line" aria-hidden="true" /> 实线 ·
            论文内组织
          </span>
          <span>
            <b className="knowledge-legend-line dashed" aria-hidden="true" />{" "}
            虚线 · AI 跨论文联系
          </span>
          {showTopicContext && (
            <>
              <span>
                <b
                  className="knowledge-legend-line outside-topic"
                  aria-hidden="true"
                />{" "}
                长短虚线 · 专题外联系
              </span>
              <span>
                <i
                  className="knowledge-legend-topic-paper"
                  aria-hidden="true"
                />{" "}
                专题外论文
              </span>
            </>
          )}
        </div>
        {save.isError && (
          <p role="alert">
            布局保存失败：{errorText(save.error)}{" "}
            <button
              type="button"
              className="text-button"
              onClick={() => {
                if (latestLayout.current) save.mutate(latestLayout.current);
              }}
            >
              重试保存布局
            </button>
          </p>
        )}
      </div>
      <aside className="knowledge-map-detail" aria-label="知识地图详情">
        {current ? (
          <>
            <span className="eyebrow">
              {current.node.outside_topic
                ? "专题外论文"
                : getGraphAppearance(current.node.type ?? "").label}
            </span>
            <h3>{detailText?.primary}</h3>
            {detailText?.secondary && (
              <p className="muted" lang="en">
                {detailText.secondary}
              </p>
            )}
            <p>{current.node.description_zh}</p>
            {current.node.type === "CONTRIBUTION" && (
              <p className="quality-note">
                作者宣称的贡献；不代表全领域新颖性已经验证。
              </p>
            )}
            <button
              className="text-button"
              onClick={() => onSelectPaper(current.paperId)}
            >
              打开论文知识与阅读入口 <ArrowUpRight size={13} />
            </button>
            {graphNodeKind(current.node) !== "PAPER" && current.version && (
              <SourceReferences
                refs={nodeReferences(current.node, current.version)}
              />
            )}
          </>
        ) : cross ? (
          <>
            <span className="eyebrow">
              {cross.outsideTopic ? "AI 联系分析 · 专题外联系" : "AI 联系分析"}
            </span>
            <h3>
              {relationLabels[cross.relation.type] ?? cross.relation.type}
            </h3>
            <p>{cross.relation.explanation_zh ?? cross.relation.explanation}</p>
            <p className="quality-note">
              {String(
                cross.relation.limitations_zh ??
                  cross.relation.limitations ??
                  "请结合双方材料判断适用范围。",
              )}
            </p>
            <button
              className="text-button"
              onClick={() => onOpenReport(cross.report.id)}
            >
              打开对应联系汇报 <ArrowUpRight size={13} />
            </button>
            <SourceReferences
              label={
                cross.relation.source_title
                  ? `${cross.relation.source_title}的原文依据`
                  : "新增论文依据"
              }
              refs={cross.relation.source_refs ?? []}
            />
            <SourceReferences
              label={
                cross.relation.detail && cross.relation.target_title
                  ? `${cross.relation.target_title}的原文依据`
                  : "已有论文依据"
              }
              refs={cross.relation.target_refs ?? []}
            />
          </>
        ) : (
          <>
            <h3>选择知识节点</h3>
            <p className="muted">
              点击节点查看详情，点击虚线核对双方依据。右键可固定节点。
            </p>
            <p className="muted">当前显示 {papers.length} 篇论文。</p>
          </>
        )}
      </aside>
      {contextMenu}
    </div>
  );
}

function KnowledgePaperPanel({
  paper,
  loading,
  error,
  collections,
  settings,
  connected,
  onClose,
  onOpenPaper,
  onOpenReport,
  onOpenTasks,
  onAssignTopic,
  onSaved,
  onArchive,
  archiving,
  archiveError,
}: {
  paper?: KnowledgePaper;
  loading: boolean;
  error: unknown;
  collections: KnowledgeCollection[];
  settings?: KnowledgeSettings;
  connected: boolean;
  onClose: () => void;
  onOpenPaper: Props["onOpenPaper"];
  onOpenReport: (id: string) => void;
  onOpenTasks: () => void;
  onAssignTopic: (paper: KnowledgePaper) => void;
  onSaved: () => void;
  onArchive: (id: string) => void;
  archiving: boolean;
  archiveError: Error | null;
}) {
  return (
    <KnowledgeDialog title="论文知识" onClose={onClose}>
      {loading ? (
        <p role="status">正在读取论文知识…</p>
      ) : error ? (
        <p role="alert">{errorText(error)}</p>
      ) : paper ? (
        <KnowledgePaperContents
          key={paper.id}
          paper={paper}
          collections={collections}
          settings={settings}
          connected={connected}
          onOpenPaper={onOpenPaper}
          onOpenReport={onOpenReport}
          onOpenTasks={onOpenTasks}
          onAssignTopic={onAssignTopic}
          onSaved={onSaved}
          onArchive={onArchive}
          archiving={archiving}
        />
      ) : null}
      {archiveError && (
        <p role="alert" className="error-text">
          {errorText(archiveError)}
        </p>
      )}
    </KnowledgeDialog>
  );
}

function KnowledgePaperContents({
  paper,
  collections,
  settings,
  connected,
  onOpenPaper,
  onOpenReport,
  onOpenTasks,
  onAssignTopic,
  onSaved,
  onArchive,
  archiving,
}: {
  paper: KnowledgePaper;
  collections: KnowledgeCollection[];
  settings?: KnowledgeSettings;
  connected: boolean;
  onOpenPaper: Props["onOpenPaper"];
  onOpenReport: (id: string) => void;
  onOpenTasks: () => void;
  onAssignTopic: (paper: KnowledgePaper) => void;
  onSaved: () => void;
  onArchive: (id: string) => void;
  archiving: boolean;
}) {
  const [versionId, setVersionId] = useState(paper.current_version?.id ?? "");
  const [note, setNote] = useState(paper.note);
  const [allowNetwork, setAllowNetwork] = useState(false);
  const openSource = useMutation({
    mutationFn: async ({
      projectId,
      paperId,
    }: {
      projectId: string;
      paperId: string;
    }) => onOpenPaper(projectId, paperId),
  });
  const version =
    paper.versions.find((item) => item.id === versionId) ??
    paper.current_version;
  const canAnalyzeCurrent =
    !paper.archived && version?.id === paper.current_version?.id;
  const scope = settings && scopeLabels[settings.scope];
  const collection =
    settings?.scope === "collection"
      ? collections.find((item) => item.id === settings.collection_id)
      : undefined;
  const save = useMutation({
    mutationFn: () => knowledgeApi.updatePaper(paper.id, { note }),
    onSuccess: onSaved,
  });
  const adopt = useMutation({
    mutationFn: () =>
      knowledgeApi.updatePaper(paper.id, { current_version_id: version!.id }),
    onSuccess: onSaved,
  });
  const connect = useMutation({
    mutationFn: (forceRegenerate: boolean) =>
      knowledgeApi.connect(version!.id, {
        allow_network: true,
        ...(forceRegenerate ? { force_regenerate: true } : {}),
      }),
    onSuccess: () => {
      setAllowNetwork(false);
      onSaved();
    },
  });
  const result =
    connect.data && "result" in connect.data ? connect.data.result : null;
  const completedReportId =
    connect.data?.status === "succeeded" &&
    result &&
    typeof result === "object" &&
    "report_id" in result &&
    typeof result.report_id === "string"
      ? result.report_id
      : null;
  return (
    <div className="knowledge-paper-detail">
      <h3>{paper.title}</h3>
      <div className="knowledge-detail-actions">
        {paper.source_links.map((link) => (
          <button
            key={`${link.project_id}:${link.original_paper_id}`}
            className="button secondary"
            disabled={
              !connected ||
              !link.source_available ||
              !link.paper_id ||
              openSource.isPending
            }
            onClick={() => {
              if (link.paper_id)
                openSource.mutate({
                  projectId: link.project_id,
                  paperId: link.paper_id,
                });
            }}
          >
            {link.source_available ? "返回论文阅读" : "原项目论文已移除"}
            <ArrowUpRight size={14} />
          </button>
        ))}
        <button
          className="text-button"
          disabled={!connected || archiving || paper.archived}
          onClick={() => onArchive(paper.id)}
        >
          {paper.archived ? "已归档" : "归档论文知识"}
        </button>
      </div>
      {openSource.isPending && <p role="status">正在打开论文阅读…</p>}
      {openSource.isError && (
        <p role="alert" className="error-text">
          无法打开论文阅读。{errorText(openSource.error)}
        </p>
      )}
      <label>
        知识版本{" "}
        <select
          aria-label="知识版本"
          value={version?.id ?? ""}
          onChange={(event) => {
            setVersionId(event.target.value);
            setAllowNetwork(false);
          }}
        >
          {paper.versions.map((item) => (
            <option key={item.id} value={item.id}>
              {date(item.created_at)} ·{" "}
              {item.source_kind === "model_parse" ? "模型解析" : "本地解析"}
              {partialKnowledgeLabel(item) ? " · 部分知识" : ""}
              {item.id === paper.current_version?.id ? " · 当前版本" : ""}
            </option>
          ))}
        </select>
      </label>
      {version && version.id !== paper.current_version?.id && (
        <button
          className="button secondary"
          disabled={adopt.isPending}
          onClick={() => adopt.mutate()}
        >
          采用此知识版本
        </button>
      )}
      <p className="quality-note">
        {partialKnowledgeLabel(version)
          ? `${partialKnowledgeLabel(version)}：剩余内容通过原文来源校验，但不代表完整关系图。`
          : version?.evidence_status === "grounded"
            ? "带来源知识：节点依据可回查。引用合法不等于科学结论已经验证。"
            : "历史概览：尚无逐项原文定位，保留用于浏览，不参与强关系发布。"}
      </p>
      {localRecoveryAudit(version) && (
        <p className="quality-note knowledge-partial-note" role="status">
          此版本由本机恢复生成。联系分析会使用部分知识，请结合论文原文核对。
        </p>
      )}
      {version?.content.warnings?.map((warning) => (
        <p className="quality-note" key={warning}>
          {warning}
        </p>
      ))}
      <div className="knowledge-detail-nodes">
        {version?.content.graph?.nodes
          .filter((node) => node.type !== "PAPER")
          .map((node) => (
            <details key={node.id}>
              <summary>
                <span
                  style={{ color: getGraphAppearance(node.type ?? "").color }}
                >
                  {getGraphAppearance(node.type ?? "").label}
                </span>{" "}
                · {node.label_zh || node.label_en}
              </summary>
              <p>{node.description_zh}</p>
              <SourceReferences
                refs={version ? nodeReferences(node, version) : []}
              />
            </details>
          ))}
      </div>
      <label>
        个人备注
        <textarea
          aria-label="论文个人备注"
          value={note}
          maxLength={10000}
          onChange={(event) => setNote(event.target.value)}
        />
      </label>
      <button
        className="button secondary"
        disabled={save.isPending}
        onClick={() => save.mutate()}
      >
        保存论文备注
      </button>
      {save.isSuccess && <p role="status">个人备注已保存。</p>}
      <fieldset>
        <legend>所属专题</legend>
        <p className="muted">
          {collections
            .filter((topic) => paper.collection_ids.includes(topic.id))
            .map((topic) => topic.name)
            .join("、") || "未归入专题"}
        </p>
        <button
          type="button"
          className="button secondary"
          disabled={!connected || paper.archived}
          onClick={() => onAssignTopic(paper)}
        >
          <FolderCog size={15} />
          管理论文专题
        </button>
      </fieldset>
      {version?.evidence_status === "grounded" && (
        <fieldset>
          <legend>与已有论文建立联系</legend>
          <p className="knowledge-analysis-scope">
            {settings
              ? `本次分析范围 · ${scope}${collection ? ` · ${collection.name}` : ""} · 最多 ${settings.max_candidates} 篇候选`
              : "正在读取联系分析设置"}
          </p>
          <label className="knowledge-check">
            <input
              type="checkbox"
              checked={allowNetwork}
              disabled={!canAnalyzeCurrent || !settings || connect.isPending}
              onChange={(event) => setAllowNetwork(event.target.checked)}
            />
            允许发送本版本及候选论文知识与依据进行联系分析
          </label>
          <div className="knowledge-detail-actions">
            <button
              type="button"
              className="button primary"
              disabled={
                !connected ||
                !canAnalyzeCurrent ||
                !settings ||
                !allowNetwork ||
                connect.isPending
              }
              onClick={() => connect.mutate(false)}
            >
              {connect.isPending && !connect.variables
                ? "正在提交…"
                : "分析论文联系"}
            </button>
            <button
              type="button"
              className="button secondary"
              disabled={
                !connected ||
                !canAnalyzeCurrent ||
                !settings ||
                !allowNetwork ||
                connect.isPending
              }
              onClick={() => connect.mutate(true)}
            >
              {connect.isPending && connect.variables
                ? "正在提交…"
                : "重新分析并生成详细汇报"}
            </button>
          </div>
          {canAnalyzeCurrent ? (
            <p className="muted">
              普通分析可复用已有结果。重新分析按当前范围和预算另存汇报，可能产生模型费用。
            </p>
          ) : (
            <p className="muted">联系分析使用未归档论文的当前知识版本。</p>
          )}
          {connect.isSuccess && (
            <div className="knowledge-analysis-outcome" role="status">
              {completedReportId ? (
                <>
                  已复用已有联系汇报。
                  <button
                    className="text-button"
                    onClick={() => onOpenReport(completedReportId)}
                  >
                    打开已保存汇报
                  </button>
                </>
              ) : active(connect.data.status) ? (
                "联系任务已进入任务流程。完成后可查看汇报。"
              ) : (
                <>
                  {statusLabels[connect.data.status] ?? "已有分析任务"}
                  <button className="text-button" onClick={onOpenTasks}>
                    查看任务记录
                  </button>
                </>
              )}
            </div>
          )}
        </fieldset>
      )}
      {[save.error, adopt.error, connect.error]
        .filter(Boolean)
        .map((item, index) => (
          <p key={index} role="alert" className="error-text">
            {errorText(item)}
          </p>
        ))}
    </div>
  );
}

function KnowledgeReportPanel({
  report,
  loading,
  error,
  papers,
  onClose,
  onOpenPaper,
  onLocateRelation,
  onUpdate,
}: {
  report?: KnowledgeReport;
  loading: boolean;
  error: unknown;
  papers: KnowledgePaper[];
  onClose: () => void;
  onOpenPaper: (id: string) => void;
  onLocateRelation: (relation: KnowledgeRelation) => void;
  onUpdate: (body: { read?: boolean; pinned?: boolean; note?: string }) => void;
}) {
  return (
    <KnowledgeDialog title="联系汇报" onClose={onClose}>
      {loading ? (
        <p role="status">正在读取汇报…</p>
      ) : error ? (
        <p role="alert">{errorText(error)}</p>
      ) : report ? (
        <KnowledgeReportContents
          key={report.id}
          report={report}
          papers={papers}
          onOpenPaper={onOpenPaper}
          onLocateRelation={onLocateRelation}
          onUpdate={onUpdate}
        />
      ) : null}
    </KnowledgeDialog>
  );
}

function KnowledgeReportContents({
  report,
  papers,
  onOpenPaper,
  onLocateRelation,
  onUpdate,
}: {
  report: KnowledgeReport;
  papers: KnowledgePaper[];
  onOpenPaper: (id: string) => void;
  onLocateRelation: (relation: KnowledgeRelation) => void;
  onUpdate: (body: { read?: boolean; pinned?: boolean; note?: string }) => void;
}) {
  const [note, setNote] = useState(report.note);
  const [pointedRelation, setPointedRelation] = useState<string | null>(null);
  const [focusedRelation, setFocusedRelation] = useState<string | null>(null);
  const relations = report.relations ?? [];
  const relationNumbers = new Map(
    relations.map((relation, index) => [relation.id, index + 1]),
  );
  const coverage = report.coverage;
  const scopeName =
    scopeLabels[coverage?.scope as keyof typeof scopeLabels] ?? "范围未记录";
  return (
    <article className="knowledge-report-detail">
      <div className="eyebrow">AI 联系分析 · {date(report.created_at)}</div>
      <h3>{report.title}</h3>
      <p className="knowledge-report-coverage">
        {statusLabels[report.status] ?? report.status} · {scopeName} · 实际比较{" "}
        {String(coverage?.compared ?? "未知")} 篇 · 入选{" "}
        {String(coverage?.selected ?? "未知")} 篇 · 库内范围{" "}
        {String(coverage?.eligible ?? "未知")}
        {typeof coverage?.excluded_legacy === "number" &&
        coverage.excluded_legacy > 0
          ? ` · 排除历史概览 ${coverage.excluded_legacy}`
          : ""}
      </p>
      <p className="muted">
        引文用于追溯来源。比较条件、指标和结论仍须对照原文。
      </p>
      {report.summary?.map((item, index) => (
        <p className="knowledge-report-summary" key={index}>
          {item.text_zh}
          {!!item.relation_ids.length && (
            <span className="knowledge-summary-links">
              {item.relation_ids.map((id) => {
                const number = relationNumbers.get(id);
                if (!number) return null;
                return (
                  <a
                    key={id}
                    href={`#knowledge-relation-${id}`}
                    onPointerEnter={(event) => {
                      if (event.pointerType === "mouse") setPointedRelation(id);
                    }}
                    onPointerLeave={() => setPointedRelation(null)}
                    onFocus={() => setFocusedRelation(id)}
                    onBlur={() => setFocusedRelation(null)}
                    onClick={(event) => {
                      event.preventDefault();
                      const relation = document.getElementById(
                        `knowledge-relation-${id}`,
                      );
                      relation?.focus({ preventScroll: true });
                      relation?.scrollIntoView?.({ block: "nearest" });
                    }}
                  >
                    查看依据 {number}
                  </a>
                );
              })}
            </span>
          )}
        </p>
      ))}
      <div className="knowledge-detail-actions">
        <button
          className="button secondary"
          onClick={() => onUpdate({ pinned: !report.pinned })}
        >
          <Bookmark size={14} />
          {report.pinned ? "取消置顶" : "置顶汇报"}
        </button>
        <button
          className="text-button"
          onClick={() => onUpdate({ read: !report.read })}
        >
          {report.read ? "标为未读" : "标为已读"}
        </button>
        <button className="text-button" onClick={() => downloadJson(report)}>
          <Download size={14} />
          导出此汇报
        </button>
      </div>
      {report.stale && (
        <p className="quality-note">
          此汇报依赖历史知识版本，更新后的论文需要单独分析，原报告予以保留。
        </p>
      )}
      {relations.map((relation, index) => {
        const target = papers.find((paper) =>
          paper.versions.some(
            (version) => version.id === relation.target_version_id,
          ),
        );
        const sourceId =
          relation.source_library_paper_id ?? report.library_paper_id;
        const targetId = relation.target_library_paper_id ?? target?.id;
        const sourceTitle = relation.source_title ?? "新增论文";
        const targetTitle =
          relation.target_title ?? target?.title ?? "已有论文";
        return (
          <section
            className="knowledge-relation"
            id={`knowledge-relation-${relation.id}`}
            key={relation.id}
            tabIndex={-1}
            data-preview={(pointedRelation ?? focusedRelation) === relation.id}
          >
            <h4>
              关系 {index + 1} ·{" "}
              {relationLabels[relation.type] ?? relation.type}
            </h4>
            <button
              className="text-button"
              disabled={report.stale}
              onClick={() => onLocateRelation(relation)}
            >
              在知识地图中定位这条联系 <ArrowUpRight size={13} />
            </button>
            <p>{relation.explanation_zh ?? relation.explanation}</p>
            {relation.detail ? (
              <dl className="knowledge-relation-detail">
                <div>
                  <dt>两篇论文的对应点</dt>
                  <dd>{relation.detail.comparison_zh}</dd>
                </div>
                <div>
                  <dt>适用条件与差异</dt>
                  <dd>{relation.detail.conditions_zh}</dd>
                </div>
                {relation.detail.follow_up_zh && (
                  <div>
                    <dt>AI 提出的待核查问题</dt>
                    <dd>{relation.detail.follow_up_zh}</dd>
                  </div>
                )}
              </dl>
            ) : (
              <p className="quality-note">
                限制与差异：
                {String(
                  relation.limitations_zh ??
                    relation.limitations ??
                    "未提供额外说明，请核对双方条件。",
                )}
              </p>
            )}
            <div
              className="knowledge-relation-sources"
              aria-label={relation.detail ? "详细关系总结" : "双方论文依据"}
            >
              <div>
                <h5>{sourceTitle}</h5>
                {relation.detail && <p>{relation.detail.source_zh}</p>}
                <button
                  className="text-button"
                  disabled={!sourceId}
                  onClick={() => sourceId && onOpenPaper(sourceId)}
                >
                  在知识地图中打开{sourceTitle}
                </button>
                <SourceReferences
                  label={
                    relation.source_title
                      ? `${sourceTitle}的原文依据`
                      : "新增论文依据"
                  }
                  refs={relation.source_refs ?? []}
                />
              </div>
              <div>
                <h5>{targetTitle}</h5>
                {relation.detail && <p>{relation.detail.target_zh}</p>}
                <button
                  className="text-button"
                  disabled={!targetId}
                  onClick={() => targetId && onOpenPaper(targetId)}
                >
                  在知识地图中打开
                  {targetTitle}
                </button>
                <SourceReferences
                  label={
                    relation.detail && relation.target_title
                      ? `${targetTitle}的原文依据`
                      : "已有论文依据"
                  }
                  refs={relation.target_refs ?? []}
                />
              </div>
            </div>
          </section>
        );
      })}
      {!report.relations?.length && (
        <p className="quality-note">
          本次未发布有双侧依据的联系；请结合实际比较范围理解，不能据此断言与全库无关。
        </p>
      )}
      <label>
        个人备注
        <textarea
          aria-label="汇报个人备注"
          maxLength={5000}
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
      </label>
      <button className="button secondary" onClick={() => onUpdate({ note })}>
        保存汇报备注
      </button>
    </article>
  );
}

function AddKnowledgeDialog({
  projectId,
  connected,
  onClose,
  onSaved,
}: {
  projectId: string;
  connected: boolean;
  onClose: () => void;
  onSaved: (text: string) => void;
}) {
  const sources = useQuery({
    queryKey: ["knowledge", "sources", projectId],
    queryFn: () => knowledgeApi.sources(projectId),
    enabled: connected,
  });
  const [paperId, setPaperId] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [allowNetwork, setAllowNetwork] = useState(false);
  const paper = sources.data?.items.find((item) => item.paper_id === paperId);
  const source = paper?.sources.find(
    (item) => `${item.source_kind}:${item.source_id}` === sourceId,
  );
  const collect = useMutation({
    mutationFn: () =>
      knowledgeApi.collect({
        paper_id: paper!.paper_id,
        source_kind: source!.source_kind,
        source_id: source!.source_id,
        overview_result_id: source!.overview_result_id ?? undefined,
      }),
    onSuccess: () => onSaved("已有概览已收藏，新增模型调用 0。"),
  });
  const extract = useMutation({
    mutationFn: () =>
      knowledgeApi.extract({
        paper_id: paper!.paper_id,
        source_kind: source!.source_kind,
        source_id: source!.source_id,
        allow_network: true,
      }),
    onSuccess: () =>
      onSaved(
        "带来源知识任务已提交；完成后会保存版本，并按已授权策略分析联系。",
      ),
  });
  return (
    <KnowledgeDialog title="加入论文知识" onClose={onClose}>
      <p className="muted">
        选择真实解析材料。已有概览可直接收藏；带来源知识需要单独生成。
      </p>
      {sources.isPending && <p role="status">正在读取可用论文…</p>}
      {sources.error && <p role="alert">{errorText(sources.error)}</p>}
      <label>
        论文
        <select
          aria-label="选择入库论文"
          value={paperId}
          onChange={(event) => {
            setPaperId(event.target.value);
            setSourceId("");
            setAllowNetwork(false);
          }}
        >
          <option value="">选择论文</option>
          {sources.data?.items.map((item) => (
            <option key={item.paper_id} value={item.paper_id}>
              {item.title}
            </option>
          ))}
        </select>
      </label>
      <label>
        解析来源
        <select
          aria-label="选择知识来源"
          value={sourceId}
          disabled={!paper}
          onChange={(event) => {
            setSourceId(event.target.value);
            setAllowNetwork(false);
          }}
        >
          <option value="">选择来源版本</option>
          {paper?.sources.map((item) => (
            <option
              key={`${item.source_kind}:${item.source_id}`}
              value={`${item.source_kind}:${item.source_id}`}
            >
              {item.label}
            </option>
          ))}
        </select>
      </label>
      {source && (
        <>
          <div className="knowledge-add-option">
            <h3>收藏已有概览</h3>
            <p>保留当前知识卡片和轻量图谱，标为历史概览，不补造原文出处。</p>
            <button
              className="button secondary"
              disabled={
                !source.has_overview || collect.isPending || extract.isPending
              }
              onClick={() => collect.mutate()}
            >
              {source.has_overview
                ? "零模型收藏已有概览"
                : "此来源尚无可收藏概览"}
            </button>
          </div>
          <div className="knowledge-add-option">
            <h3>生成带来源知识</h3>
            <p>
              提取研究问题、概念、方法、作者贡献与结果，并绑定所选解析材料中的依据。
            </p>
            <label className="knowledge-check">
              <input
                type="checkbox"
                checked={allowNetwork}
                onChange={(event) => setAllowNetwork(event.target.checked)}
              />
              允许向已配置模型发送此来源版本的论文内容
            </label>
            <button
              className="button primary"
              disabled={!allowNetwork || extract.isPending || collect.isPending}
              onClick={() => extract.mutate()}
            >
              {extract.isPending ? "正在提交…" : "生成带来源知识"}
            </button>
          </div>
        </>
      )}
      {[collect.error, extract.error].filter(Boolean).map((item, index) => (
        <p role="alert" className="error-text" key={index}>
          {errorText(item)}
        </p>
      ))}
      {sources.isSuccess && !sources.data.items.length && (
        <p>当前范围暂无已解析论文，请先在研究项目中完成本地或模型解析。</p>
      )}
    </KnowledgeDialog>
  );
}

function KnowledgeSettingsDialog({
  settings,
  collections,
  onClose,
  onSaved,
}: {
  settings: KnowledgeSettings;
  collections: KnowledgeCollection[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [value, setValue] = useState(settings);
  const lastFinite = useRef({
    max_candidates: settings.max_candidates,
    max_requests_per_run: settings.max_requests_per_run ?? 2,
    max_input_tokens: settings.max_input_tokens ?? 48000,
    max_output_tokens: settings.max_output_tokens ?? 6000,
    total_request_limit: settings.total_request_limit,
  });
  const save = useMutation({
    mutationFn: () => knowledgeApi.saveSettings(value),
    onSuccess: onSaved,
  });
  const numeric: {
    key: keyof Pick<
      KnowledgeSettings,
      | "max_candidates"
      | "max_requests_per_run"
      | "max_input_tokens"
      | "max_output_tokens"
      | "total_request_limit"
    >;
    label: string;
    min: number;
    max?: number;
    allowUnlimited?: boolean;
  }[] = [
    { key: "max_candidates", label: "每篇最多候选论文", min: 1, max: 50 },
    {
      key: "max_requests_per_run",
      label: "每次分析最多请求数",
      min: 1,
      max: 8,
      allowUnlimited: true,
    },
    {
      key: "max_input_tokens",
      label: "单次输入 Token 预算",
      min: 1024,
      max: 2000000,
      allowUnlimited: true,
    },
    {
      key: "max_output_tokens",
      label: "单次输出 Token 预算",
      min: 256,
      max: 200000,
      allowUnlimited: true,
    },
    {
      key: "total_request_limit",
      label: "知识库累计请求上限",
      min: 1,
      max: 100000,
    },
  ];
  return (
    <KnowledgeDialog title="自动分析设置" onClose={onClose}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <p className="muted">
          关闭后会撤回对应自动任务中尚未发送的请求，重新开启不会恢复已撤销的任务。已发送的请求可能产生费用。
        </p>
        <label className="knowledge-check">
          <input
            type="checkbox"
            checked={value.auto_collect}
            onChange={(event) =>
              setValue({ ...value, auto_collect: event.target.checked })
            }
          />
          新解析完成后自动构建论文知识（调用模型）
        </label>
        <label className="knowledge-check">
          <input
            type="checkbox"
            checked={value.auto_connect}
            onChange={(event) =>
              setValue({ ...value, auto_connect: event.target.checked })
            }
          />
          新知识版本入库后自动分析联系
        </label>
        <label className="knowledge-check">
          <input
            type="checkbox"
            checked={value.allow_network}
            onChange={(event) =>
              setValue({ ...value, allow_network: event.target.checked })
            }
          />
          授权在以下范围与预算内自动向已配置模型发送知识和原文依据
        </label>
        <label>
          比较范围
          <select
            aria-label="自动比较范围"
            value={value.scope}
            onChange={(event) =>
              setValue({
                ...value,
                scope: event.target.value as KnowledgeSettings["scope"],
              })
            }
          >
            <option value="project">论文所在研究项目</option>
            <option value="collection">指定专题</option>
            <option value="all">全知识库候选</option>
          </select>
        </label>
        {value.scope === "collection" && (
          <label>
            比较专题
            <select
              required
              aria-label="自动比较专题"
              value={value.collection_id ?? ""}
              onChange={(event) =>
                setValue({
                  ...value,
                  collection_id: event.target.value || null,
                })
              }
            >
              <option value="">选择专题</option>
              {collections.map((collection) => (
                <option key={collection.id} value={collection.id}>
                  {collection.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="knowledge-settings-grid">
          {numeric.map(({ key, label, min, max, allowUnlimited }) => (
            <div className="knowledge-budget-control" key={key}>
              <label htmlFor={`knowledge-setting-${key}`}>{label}</label>
              <input
                id={`knowledge-setting-${key}`}
                aria-label={label}
                required
                type="number"
                min={min}
                max={max}
                step={1}
                disabled={value[key] === null}
                value={value[key] ?? ""}
                onChange={(event) =>
                  setValue({ ...value, [key]: Number(event.target.value) })
                }
              />
              {allowUnlimited && (
                <label className="knowledge-check">
                  <input
                    type="checkbox"
                    aria-label={`${label}无上限`}
                    checked={value[key] === null}
                    onChange={(event) => {
                      const current = value[key];
                      if (event.target.checked && current !== null)
                        lastFinite.current[key] = current;
                      setValue({
                        ...value,
                        [key]: event.target.checked
                          ? null
                          : lastFinite.current[key],
                      });
                    }}
                  />
                  无上限
                </label>
              )}
            </div>
          ))}
        </div>
        {(value.auto_collect || value.auto_connect) && !value.allow_network && (
          <p className="quality-note">
            请明确授权自动发送后保存策略。自动构建和联系分析会使用同一累计请求预算。
          </p>
        )}
        <p className="muted">
          无上限仍受模型上下文容量、输出能力和知识库累计请求上限约束。
          候选数是本次优先比较范围，不代表穷尽全库。超出预算会暂停。
        </p>
        <button
          className="button primary"
          disabled={
            save.isPending ||
            ((value.auto_collect || value.auto_connect) && !value.allow_network)
          }
        >
          保存分析策略
        </button>
        {save.error && (
          <p role="alert" className="error-text">
            {errorText(save.error)}
          </p>
        )}
      </form>
    </KnowledgeDialog>
  );
}

type Props = {
  connected: boolean;
  projects: Project[];
  onOpenPaper: (projectId: string, paperId: string) => void | Promise<void>;
  onOpenTasks: () => void;
};

export function ResearchKnowledgeBase({
  connected,
  projects,
  onOpenPaper,
  onOpenTasks,
}: Props) {
  const client = useQueryClient();
  const { contextMenuProps, contextMenu } = useContextMenu();
  const [tab, setTab] = useState<"map" | "papers" | "reports">(() => {
    try {
      const saved = localStorage.getItem("rgs.knowledge.tab");
      if (saved === "map" || saved === "papers") return saved;
    } catch {
      // Keep the workbench available without saved preferences.
    }
    return "reports";
  });
  const [projectId, setProjectId] = useState("");
  const [collectionId, setCollectionId] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [reportOffset, setReportOffset] = useState(0);
  const [selectedPaper, setSelectedPaper] = useState("");
  const [selectedReport, setSelectedReport] = useState("");
  const [mapLookup, setMapLookup] = useState<MapLookup | null>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const focusAfterLookup = useRef(false);
  useEffect(() => {
    const focusSearch = () => {
      const fullscreenSearch = document.querySelector<HTMLInputElement>(
        "[data-fullscreen] [data-knowledge-search]",
      );
      const input = fullscreenSearch ?? searchInput.current;
      input?.focus();
      input?.select();
    };
    if (focusAfterLookup.current && !mapLookup) {
      focusAfterLookup.current = false;
      focusSearch();
    }
    const onKey = (event: KeyboardEvent) => {
      handleWorkspaceFind(event, () => {
        if (mapLookup) {
          focusAfterLookup.current = true;
          setMapLookup(null);
        } else {
          focusSearch();
        }
      });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mapLookup]);
  const mapFocus = mapLookup?.paperId ?? "";
  const mapOtherFocus = mapLookup?.otherPaperId ?? "";
  const mapRelation = mapLookup?.relation ?? null;
  const activeTab = mapLookup ? "map" : tab;
  const [hiddenMapKinds, setHiddenMapKinds] = useState<ReadonlySet<string>>(
    () => new Set(),
  );
  const [addOpen, setAddOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [topicDialog, setTopicDialog] = useState<"manage" | "create" | null>(
    null,
  );
  const [topicPaper, setTopicPaper] = useState<KnowledgePaper | null>(null);
  const [notice, setNotice] = useState("");
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["knowledge"] });
    void client.invalidateQueries({ queryKey: ["jobs"] });
    void client.invalidateQueries({ queryKey: ["lite-usage"] });
  };
  const archiveKnowledge = useMutation({
    mutationFn: (id: string) => archiveApi.stage("knowledge_paper", id),
    onSuccess: (item) => {
      setSelectedPaper("");
      setNotice(`「${item.title}」已移至归档管理。`);
      refresh();
      void client.invalidateQueries({ queryKey: ["archive"] });
    },
  });
  function stageKnowledgePaper(id: string) {
    archiveKnowledge.mutate(id);
  }
  const library = useQuery({
    queryKey: ["knowledge", "library"],
    queryFn: knowledgeApi.library,
    enabled: connected,
  });
  const pageSize = tab === "map" ? mapPageSize : paperPageSize;
  const papers = useQuery({
    queryKey: [
      "knowledge",
      "papers",
      projectId,
      collectionId,
      search,
      offset,
      pageSize,
    ],
    queryFn: () =>
      knowledgeApi.papers({
        project_id: projectId,
        collection_id: collectionId,
        search,
        offset,
        limit: pageSize,
      }),
    enabled: connected,
    refetchInterval: 5000,
  });
  const collections = useQuery({
    queryKey: ["knowledge", "collections"],
    queryFn: knowledgeApi.collections,
    enabled: connected,
  });
  const reports = useQuery({
    queryKey: ["knowledge", "reports"],
    queryFn: knowledgeApi.reports,
    enabled: connected,
    refetchInterval: 5000,
  });
  const usage = useQuery({
    queryKey: ["knowledge", "usage"],
    queryFn: knowledgeApi.usage,
    enabled: connected,
    refetchInterval: 5000,
  });
  const reportScope = useQuery({
    queryKey: ["knowledge", "report-scope", projectId, collectionId],
    queryFn: async () => {
      const result: KnowledgePaper[] = [];
      let total = 1;
      while (result.length < total) {
        const page = await knowledgeApi.papers({
          project_id: projectId,
          collection_id: collectionId,
          include_archived: true,
          limit: 200,
          offset: result.length,
        });
        total = page.total;
        if (!page.items.length) break;
        result.push(...page.items);
      }
      return result;
    },
    enabled: connected && tab === "reports" && !!(projectId || collectionId),
  });
  const focusedPaper = useQuery({
    queryKey: ["knowledge", "focus-paper", mapFocus],
    queryFn: () => knowledgeApi.paper(mapFocus),
    enabled:
      connected &&
      !!mapFocus &&
      !papers.data?.items.some((paper) => paper.id === mapFocus),
  });
  const otherFocusedPaper = useQuery({
    queryKey: ["knowledge", "focus-paper", mapOtherFocus],
    queryFn: () => knowledgeApi.paper(mapOtherFocus),
    enabled:
      connected &&
      !!mapOtherFocus &&
      !papers.data?.items.some((paper) => paper.id === mapOtherFocus),
  });
  const runs = useQuery({
    queryKey: ["knowledge", "runs"],
    queryFn: () => knowledgeApi.runs(),
    enabled: connected,
    refetchInterval: 3000,
  });
  const detail = useQuery({
    queryKey: ["knowledge", "paper", selectedPaper],
    queryFn: () => knowledgeApi.paper(selectedPaper),
    enabled: connected && !!selectedPaper,
  });
  const reportDetail = useQuery({
    queryKey: ["knowledge", "report", selectedReport],
    queryFn: () => knowledgeApi.report(selectedReport),
    enabled: connected && !!selectedReport,
  });
  const updateReport = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: string;
      body: { read?: boolean; pinned?: boolean; note?: string };
    }) => knowledgeApi.updateReport(id, body),
    onSuccess: refresh,
  });
  const exportLibrary = useMutation({
    mutationFn: knowledgeApi.export,
    onSuccess: downloadJson,
  });
  const retry = useMutation({
    mutationFn: (id: string) => knowledgeApi.retryRun(id),
    onSuccess: () => {
      setNotice("知识任务已继续，已完成的处理结果会复用。");
      refresh();
    },
  });
  const selectTab = (value: typeof tab) => {
    setMapLookup(null);
    if (tab !== value) setOffset(0);
    setTab(value);
    try {
      localStorage.setItem("rgs.knowledge.tab", value);
    } catch {
      // Keep the in-memory tab when local storage is unavailable.
    }
  };
  const items = papers.data?.items ?? [];
  const mapLookupIds = [...new Set([mapFocus, mapOtherFocus].filter(Boolean))];
  const mapPapers = mapLookup
    ? mapLookupIds
        .map(
          (id) =>
            items.find((paper) => paper.id === id) ??
            [focusedPaper.data, otherFocusedPaper.data].find(
              (paper) => paper?.id === id,
            ),
        )
        .filter((paper): paper is KnowledgePaper => !!paper)
    : items;
  const mapViewKey = mapLookup
    ? `locate:${mapLookupIds.join(":")}`
    : `${projectId || "all"}:${collectionId || "all"}`;
  const allReports = reports.data?.items ?? [];
  const visibleReports = allReports
    .filter(
      (report) =>
        !search ||
        `${report.title} ${report.summary?.map((item) => item.text_zh).join(" ") ?? ""}`
          .toLowerCase()
          .includes(search.toLowerCase()),
    )
    .filter(
      (report) =>
        (!projectId && !collectionId) ||
        reportScope.data?.some((paper) => paper.id === report.library_paper_id),
    );
  const unread =
    reports.data?.unread ?? allReports.filter((report) => !report.read).length;
  const running = runs.data?.items.filter((run) => active(run.status)) ?? [];
  const openReport = (report: KnowledgeReport) => {
    setSelectedReport(report.id);
    if (!report.read)
      updateReport.mutate({ id: report.id, body: { read: true } });
  };
  const openReportById = (id: string) => {
    const report = allReports.find((item) => item.id === id);
    if (report) openReport(report);
    else setSelectedReport(id);
  };
  const filters = (update: () => void) => {
    update();
    setOffset(0);
    setReportOffset(0);
    setSelectedPaper("");
    setSelectedReport("");
  };

  return (
    <section className="research-knowledge-base" aria-label="研究内容知识库">
      <header className="knowledge-header">
        <div>
          <h1>研究内容知识库</h1>
          <p>保存论文中的研究知识，让每次阅读与过去的积累建立联系。</p>
        </div>
        <div className="knowledge-header-actions">
          <button
            className="button secondary"
            disabled={!connected || exportLibrary.isPending}
            onClick={() => exportLibrary.mutate()}
          >
            <Download size={15} />
            导出
          </button>
          <button
            className="button secondary"
            disabled={!library.data}
            onClick={() => setSettingsOpen(true)}
          >
            <Settings2 size={15} />
            自动分析设置
          </button>
          <button
            className="button primary"
            disabled={!connected}
            onClick={() => setAddOpen(true)}
          >
            <Plus size={16} />
            加入论文知识
          </button>
        </div>
      </header>
      <div className="knowledge-stats" aria-label="知识库概况">
        <span>
          <strong>{papers.data?.total ?? "—"}</strong>篇论文知识
        </span>
        <span>
          <strong>{reports.data?.total ?? "—"}</strong>份联系汇报
        </span>
        <span>
          <strong>{unread}</strong>份未读
        </span>
        <span className={running.length ? "knowledge-processing" : ""}>
          {running.length ? (
            <LoaderCircle size={14} className="spin" />
          ) : (
            <Check size={14} />
          )}
          {running.length
            ? `${running.length} 项正在处理`
            : "阅读与浏览不调用模型"}
        </span>
      </div>
      {usage.data && (
        <details className="knowledge-run-status">
          <summary>
            知识库模型用量 · 已记录 {usage.data.calls} 次调用 / 累计上限{" "}
            {library.data?.settings.total_request_limit ?? "—"}
          </summary>
          <p>
            输入 Token：{usage.data.input_tokens.toLocaleString("zh-CN")} · 输出
            Token：{usage.data.output_tokens.toLocaleString("zh-CN")} ·{" "}
            {usage.data.cost_known && usage.data.cost_estimate !== null
              ? `估算费用 $${usage.data.cost_estimate}`
              : "费用未知"}
          </p>
          <p>
            包含论文知识建模与联系分析；历史未记录用量不计为零。缓存命中与阅读浏览不产生新调用。
          </p>
        </details>
      )}
      <nav className="knowledge-tabs" aria-label="知识库视图">
        {(
          [
            ["map", "知识地图", GitBranch],
            ["papers", "论文知识", Library],
            ["reports", "联系汇报", BookOpen],
          ] as const
        ).map(([value, label, Icon]) => (
          <button
            key={value}
            className={activeTab === value ? "active" : ""}
            aria-current={activeTab === value ? "page" : undefined}
            onClick={() => selectTab(value)}
          >
            <Icon size={16} />
            {label}
            {value === "reports" && unread > 0 && (
              <span className="knowledge-unread">{unread}</span>
            )}
          </button>
        ))}
      </nav>
      {mapLookup ? (
        <div className="knowledge-locator-bar">
          <span>正在定位汇报中的论文知识</span>
          <button
            type="button"
            className="button secondary"
            onClick={() => {
              setMapLookup(null);
              setSelectedReport(mapLookup.reportId);
            }}
          >
            返回联系汇报
          </button>
        </div>
      ) : (
        <div
          className="knowledge-filters"
          role="group"
          aria-label="知识库浏览筛选"
        >
          <label className="knowledge-search">
            <Search size={15} />
            <input
              ref={searchInput}
              type="search"
              aria-label="搜索知识库"
              aria-keyshortcuts="Control+F"
              maxLength={300}
              value={search}
              onChange={(event) => filters(() => setSearch(event.target.value))}
              placeholder={
                tab === "reports"
                  ? "搜索汇报标题或摘要"
                  : "搜索论文、研究问题与概念"
              }
            />
          </label>
          <label>
            <span className="sr-only">研究项目筛选</span>
            <select
              aria-label="研究项目筛选"
              value={projectId}
              onChange={(event) =>
                filters(() => setProjectId(event.target.value))
              }
            >
              <option value="">全部研究项目</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="sr-only">专题筛选</span>
            <select
              aria-label="专题筛选"
              value={collectionId}
              onChange={(event) =>
                filters(() => setCollectionId(event.target.value))
              }
            >
              <option value="">全部专题</option>
              {collections.data?.items.map((collection) => (
                <option key={collection.id} value={collection.id}>
                  {collection.name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="text-button"
            disabled={!connected}
            onClick={() => setTopicDialog("create")}
          >
            <FolderPlus size={14} />
            新建专题
          </button>
          <button
            type="button"
            className="button secondary"
            disabled={!connected}
            onClick={() => setTopicDialog("manage")}
          >
            <FolderCog size={15} />
            专题管理
          </button>
        </div>
      )}
      {[
        library.error,
        papers.error,
        !selectedPaper ? archiveKnowledge.error : null,
        collections.error,
        reports.error,
        usage.error,
        reportScope.error,
        focusedPaper.error,
        otherFocusedPaper.error,
        runs.error,
        updateReport.error,
        exportLibrary.error,
        retry.error,
      ]
        .filter(Boolean)
        .map((error, index) => (
          <p role="alert" className="error-text" key={index}>
            {errorText(error)}
          </p>
        ))}
      {notice && (
        <p role="status" className="knowledge-notice">
          {notice}
        </p>
      )}
      {!!runs.data?.items.length && (
        <details className="knowledge-run-status">
          <summary>
            {running.length ? "查看正在处理的知识任务" : "最近知识任务"}
          </summary>
          {runs.data.items.slice(0, 5).map((run) => (
            <div
              className="knowledge-run-row"
              id={`knowledge-run-${run.id}`}
              key={run.id}
            >
              <span>
                {run.kind === "extract" ? "论文知识建模" : "论文联系分析"} ·{" "}
                {statusLabels[run.status] ?? run.status}
                {typeof run.request_count === "number" &&
                  ` · 已发送 ${run.request_count} / 预算 ${run.max_requests === null ? "无上限" : (run.max_requests ?? "未知")} 次请求`}
              </span>
              {run.error && !run.local_recovery?.available && (
                <button className="text-button" onClick={onOpenTasks}>
                  查看任务记录中的错误原因
                </button>
              )}
              {run.error && inputBudgetExceeded(run.error) && (
                <button
                  className="text-button"
                  disabled={!connected || !library.data}
                  onClick={() => setSettingsOpen(true)}
                >
                  调整知识库预算
                </button>
              )}
              {run.kind === "extract" &&
                run.status === "failed" &&
                run.local_recovery?.available && (
                  <button
                    className="text-button"
                    disabled={!connected}
                    onClick={onOpenTasks}
                  >
                    查看任务记录与本机恢复
                  </button>
                )}
              {run.kind === "extract" &&
                run.local_recovery?.published_version_id && (
                  <span className="knowledge-partial-badge">
                    已本机恢复为部分知识
                  </span>
                )}
              {["failed", "interrupted", "paused"].includes(run.status) && (
                <button
                  className="text-button"
                  disabled={!connected || retry.isPending}
                  onClick={() => {
                    if (
                      window.confirm(
                        "继续知识任务可能发送所选材料并产生费用，确认在当前预算内继续？",
                      )
                    )
                      retry.mutate(run.id);
                  }}
                >
                  确认继续知识任务
                </button>
              )}
            </div>
          ))}
          <button className="text-button" onClick={onOpenTasks}>
            打开任务记录 <ArrowUpRight size={13} />
          </button>
        </details>
      )}
      {papers.isPending && <p role="status">正在读取本机知识库…</p>}
      {activeTab === "map" ? (
        <KnowledgeMap
          key={`${mapViewKey}:${mapRelation?.id ?? ""}:${mapRelation?.reportId ?? ""}`}
          focusedPaper={mapFocus}
          focusedRelation={mapRelation}
          onOpenReport={openReportById}
          papers={mapPapers}
          reports={allReports}
          connected={connected}
          collectionId={mapLookup ? "" : collectionId}
          search={mapLookup ? undefined : search}
          onSearch={(value) => filters(() => setSearch(value))}
          viewKey={mapViewKey}
          hiddenKinds={hiddenMapKinds}
          onToggleKind={(kind) => {
            setHiddenMapKinds((current) => {
              const next = new Set(current);
              if (next.has(kind)) next.delete(kind);
              else next.add(kind);
              return next;
            });
          }}
          onSelectPaper={setSelectedPaper}
        />
      ) : activeTab === "papers" ? (
        <div className="knowledge-paper-list">
          {items.map((paper) => (
            <div
              className="knowledge-paper-entry"
              key={paper.id}
              role="group"
              aria-label={paper.title}
            >
              <button
                className={`knowledge-paper-row${selectedPaper === paper.id ? " selected" : ""}`}
                {...contextMenuProps("论文知识操作", [
                  {
                    label: "打开论文知识",
                    action: () => setSelectedPaper(paper.id),
                  },
                  {
                    label: "管理论文专题",
                    action: () => setTopicPaper(paper),
                    disabled: !connected || paper.archived,
                  },
                  {
                    label: "归档论文知识",
                    action: () => stageKnowledgePaper(paper.id),
                    disabled:
                      !connected ||
                      paper.archived ||
                      archiveKnowledge.isPending,
                  },
                ])}
                onClick={() => setSelectedPaper(paper.id)}
              >
                <span className="knowledge-paper-icon">
                  <Library size={18} />
                </span>
                <span className="knowledge-paper-title">
                  <strong>{paper.title}</strong>
                  <small>
                    {partialKnowledgeLabel(paper.current_version) ||
                      (paper.current_version?.evidence_status === "grounded"
                        ? "带来源知识"
                        : "历史概览 · 尚无逐项来源")}
                    {paper.archived ? " · 已归档" : ""}
                    {paper.current_version
                      ? ` · ${date(paper.current_version.created_at)}`
                      : ""}
                  </small>
                  {!!paper.collection_ids.length && (
                    <small className="knowledge-paper-topics">
                      专题 ·{" "}
                      {collections.data?.items
                        .filter((topic) =>
                          paper.collection_ids.includes(topic.id),
                        )
                        .map((topic) => topic.name)
                        .join("、") || "—"}
                    </small>
                  )}
                </span>
                <span className="knowledge-row-count">
                  {paper.current_version?.content.graph?.nodes.filter(
                    (node) => node.type !== "PAPER",
                  ).length ?? 0}{" "}
                  项知识
                </span>
                <ArrowUpRight size={15} />
              </button>
              <button
                type="button"
                className="text-button knowledge-paper-assign"
                disabled={!connected || paper.archived}
                onClick={() => setTopicPaper(paper)}
              >
                <FolderCog size={15} />
                管理专题
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="knowledge-reports">
          {visibleReports
            .sort(
              (a, b) =>
                Number(b.pinned) - Number(a.pinned) ||
                b.created_at.localeCompare(a.created_at),
            )
            .slice(reportOffset, reportOffset + 50)
            .map((report) => (
              <button
                key={report.id}
                className={`knowledge-report-row${report.read ? "" : " unread"}`}
                {...contextMenuProps("联系汇报操作", [
                  { label: "打开联系汇报", action: () => openReport(report) },
                  {
                    label: report.read ? "标为未读" : "标为已读",
                    action: () =>
                      updateReport.mutate({
                        id: report.id,
                        body: { read: !report.read },
                      }),
                    disabled: !connected || updateReport.isPending,
                  },
                  {
                    label: report.pinned ? "取消置顶" : "置顶汇报",
                    action: () =>
                      updateReport.mutate({
                        id: report.id,
                        body: { pinned: !report.pinned },
                      }),
                    disabled: !connected || updateReport.isPending,
                  },
                ])}
                onClick={() => openReport(report)}
              >
                <span className="knowledge-report-date">
                  {date(report.created_at)}
                </span>
                <span>
                  <strong>{report.title}</strong>
                  <small>
                    {report.summary?.[0]?.text_zh ||
                      "打开查看比较范围、论文联系与双方依据。"}
                  </small>
                </span>
                <span className="knowledge-report-state">
                  {report.pinned && <Bookmark size={13} />}
                  {report.stale
                    ? "依据旧版本"
                    : (statusLabels[report.status] ?? report.status)}
                  {!report.read && <i aria-label="未读" />}
                </span>
              </button>
            ))}
        </div>
      )}
      {!mapLookup &&
        !papers.isPending &&
        ((tab !== "reports" && !items.length) ||
          (tab === "reports" && !visibleReports.length)) && (
          <div className="knowledge-empty">
            <GitBranch size={34} />
            <h2>
              {tab === "reports"
                ? "联系会随着论文积累出现"
                : "从一篇论文开始积累"}
            </h2>
            <p>
              {tab === "reports"
                ? "加入论文知识后，可分析与已入库论文的联系，汇报将保存在这里。"
                : "收藏已有概览不调用模型；生成带来源的知识后，可以继续分析论文间的联系。"}
            </p>
            <button
              className="button secondary"
              onClick={() => setAddOpen(true)}
            >
              加入论文知识
            </button>
          </div>
        )}
      {!mapLookup &&
        tab !== "reports" &&
        (papers.data?.total ?? 0) > pageSize && (
          <div className="knowledge-pagination">
            <span>
              显示 {offset + 1}–
              {Math.min(offset + pageSize, papers.data?.total ?? 0)} /{" "}
              {papers.data?.total}
            </span>
            <button
              className="text-button"
              disabled={!offset}
              onClick={() => setOffset(Math.max(0, offset - pageSize))}
            >
              上一页
            </button>
            <button
              className="text-button"
              disabled={offset + pageSize >= (papers.data?.total ?? 0)}
              onClick={() => setOffset(offset + pageSize)}
            >
              下一页
            </button>
          </div>
        )}
      {!mapLookup && tab === "reports" && visibleReports.length > 50 && (
        <div className="knowledge-pagination">
          <span>
            显示 {reportOffset + 1}–
            {Math.min(reportOffset + 50, visibleReports.length)} /{" "}
            {visibleReports.length} 份汇报
          </span>
          <button
            className="text-button"
            disabled={!reportOffset}
            onClick={() => setReportOffset(Math.max(0, reportOffset - 50))}
          >
            上一页汇报
          </button>
          <button
            className="text-button"
            disabled={reportOffset + 50 >= visibleReports.length}
            onClick={() => setReportOffset(reportOffset + 50)}
          >
            下一页汇报
          </button>
        </div>
      )}
      {selectedPaper && (
        <KnowledgePaperPanel
          paper={detail.data}
          loading={detail.isPending}
          error={detail.error}
          collections={collections.data?.items ?? []}
          settings={library.data?.settings}
          connected={connected}
          onClose={() => setSelectedPaper("")}
          onOpenPaper={onOpenPaper}
          onOpenReport={(id) => {
            setSelectedPaper("");
            openReportById(id);
          }}
          onOpenTasks={onOpenTasks}
          onAssignTopic={setTopicPaper}
          onSaved={refresh}
          onArchive={stageKnowledgePaper}
          archiving={archiveKnowledge.isPending}
          archiveError={archiveKnowledge.error}
        />
      )}
      {topicPaper && (
        <PaperTopicAssignment
          key={topicPaper.id}
          paper={topicPaper}
          topics={collections.data?.items ?? []}
          selectedId={collectionId}
          onClose={() => setTopicPaper(null)}
          onCreate={() => {
            setTopicPaper(null);
            setTopicDialog("create");
          }}
          onSaved={(message) => {
            setTopicPaper(null);
            setNotice(message);
            setOffset(0);
            refresh();
          }}
        />
      )}
      {topicDialog && (
        <TopicManagement
          connected={connected}
          selectedId={collectionId}
          create={topicDialog === "create"}
          onClose={() => setTopicDialog(null)}
          onBrowse={(id) => {
            setTopicDialog(null);
            filters(() => {
              setCollectionId(id);
              setSearch("");
            });
          }}
          onChanged={() => {
            setOffset(0);
            setReportOffset(0);
            refresh();
          }}
          onArchived={(id, name) => {
            if (collectionId === id) filters(() => setCollectionId(""));
            setNotice(`专题「${name}」已移至归档管理。`);
            refresh();
            void client.invalidateQueries({ queryKey: ["archive"] });
          }}
        />
      )}
      {selectedReport && (
        <KnowledgeReportPanel
          report={reportDetail.data}
          loading={reportDetail.isPending}
          error={reportDetail.error}
          papers={items}
          onClose={() => setSelectedReport("")}
          onOpenPaper={(id) => {
            setSelectedReport("");
            setMapLookup({ paperId: id, reportId: selectedReport });
          }}
          onLocateRelation={(relation) => {
            setSelectedReport("");
            setMapLookup({
              paperId:
                relation.source_library_paper_id ??
                reportDetail.data?.library_paper_id ??
                "",
              otherPaperId:
                relation.target_library_paper_id ??
                items.find((paper) =>
                  paper.versions.some(
                    (version) => version.id === relation.target_version_id,
                  ),
                )?.id,
              relation: { id: relation.id, reportId: selectedReport },
              reportId: selectedReport,
            });
          }}
          onUpdate={(body) => updateReport.mutate({ id: selectedReport, body })}
        />
      )}
      {addOpen && (
        <AddKnowledgeDialog
          projectId={projectId}
          connected={connected}
          onClose={() => setAddOpen(false)}
          onSaved={(text) => {
            setAddOpen(false);
            setNotice(text);
            refresh();
            selectTab("papers");
          }}
        />
      )}
      {settingsOpen && library.data && (
        <KnowledgeSettingsDialog
          settings={library.data.settings}
          collections={collections.data?.items ?? []}
          onClose={() => setSettingsOpen(false)}
          onSaved={() => {
            setSettingsOpen(false);
            refresh();
          }}
        />
      )}
      {contextMenu}
    </section>
  );
}
