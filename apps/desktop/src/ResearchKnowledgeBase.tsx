import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  BookOpen,
  Bookmark,
  Check,
  Download,
  FolderPlus,
  GitBranch,
  Library,
  LoaderCircle,
  Plus,
  Search,
  Settings2,
  X,
} from "lucide-react";
import type { Project } from "./api";
import { ForceGraph } from "./ForceGraph";
import { getGraphAppearance } from "./graphAppearance";
import type { GraphData, GraphNode } from "./graphTypes";
import {
  knowledgeApi,
  type KnowledgeCollection,
  type KnowledgeLayout,
  type KnowledgePaper,
  type KnowledgeRelation,
  type KnowledgeReport,
  type KnowledgeSettings,
  type KnowledgeSourceRef,
  type KnowledgeVersion,
} from "./knowledgeApi";
import "./researchKnowledgeBase.css";

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);
const date = (value: string) =>
  new Date(value).toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
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

function KnowledgeDialog({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (dialog.current && !dialog.current.open) dialog.current.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="dialog knowledge-dialog"
      aria-label={title}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="dialog-header">
        <h2>{title}</h2>
        <button className="icon-button" aria-label="关闭" onClick={onClose}>
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
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

function KnowledgeMap({
  focusedPaper,
  focusedRelation,
  onOpenReport,
  papers,
  reports,
  connected,
  viewKey,
  onSelectPaper,
}: {
  focusedPaper: string;
  focusedRelation: string;
  onOpenReport: (id: string) => void;
  papers: KnowledgePaper[];
  reports: KnowledgeReport[];
  connected: boolean;
  viewKey: string;
  onSelectPaper: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(focusedPaper);
  const [selected, setSelected] = useState(
    focusedPaper && !focusedRelation ? `paper:${focusedPaper}` : "",
  );
  const [selectedEdge, setSelectedEdge] = useState(
    focusedRelation ? `cross:${focusedRelation}` : "",
  );
  const [fit, setFit] = useState(0);
  const key = `library:${viewKey}`;
  const layout = useQuery({
    queryKey: ["knowledge", "layout", key],
    queryFn: () => knowledgeApi.layout(key),
    enabled: connected,
  });
  const pending = useRef<KnowledgeLayout | null>(null);
  const timer = useRef<number | null>(null);
  const writes = useRef<Promise<unknown>>(Promise.resolve());
  const save = useMutation({
    mutationFn: (value: KnowledgeLayout) => {
      const write = writes.current.then(() => knowledgeApi.saveLayout(value));
      writes.current = write.catch(() => undefined);
      return write;
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
    pending.current = {
      view_key: key,
      layout: {
        positions: [],
        viewport: null,
        ...layout.data?.layout,
        ...pending.current?.layout,
        ...part,
      },
    };
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
        paper: KnowledgePaper;
        version: KnowledgeVersion | null;
        node: GraphNode;
        refs: KnowledgeSourceRef[];
      }
    >();
    const versions = new Map<string, KnowledgePaper>();
    const relationMap = new Map<
      string,
      { relation: KnowledgeRelation; report: KnowledgeReport }
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
      details.set(root, { paper, version, node: rootNode, refs: [] });
      if (!version) continue;
      versions.set(version.id, paper);
      if (expanded !== paper.id) continue;
      for (const node of version.content.graph?.nodes ?? []) {
        if (node.type === "PAPER") continue;
        const id = `version:${version.id}:${node.id}`;
        const refs = nodeReferences(node, version);
        graph.nodes.push({ ...node, id });
        details.set(id, { paper, version, node, refs });
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
    for (const report of reports) {
      if (report.stale) continue;
      for (const relation of report.relations ?? []) {
        const a = versions.get(relation.source_version_id ?? ""),
          b = versions.get(relation.target_version_id ?? "");
        if (!a || !b) continue;
        const sourceDetail = `version:${relation.source_version_id}:${relation.source_node_id}`;
        const targetDetail = `version:${relation.target_version_id}:${relation.target_node_id}`;
        const id = `cross:${relation.id}`;
        if (relationMap.has(id)) continue;
        graph.edges.push({
          id,
          source: details.has(sourceDetail) ? sourceDetail : `paper:${a.id}`,
          target: details.has(targetDetail) ? targetDetail : `paper:${b.id}`,
          type: relation.type,
          label_zh: relationLabels[relation.type] ?? relation.type,
          is_dashed: true,
        });
        relationMap.set(id, { relation, report });
      }
    }
    return { graph, details, relationMap };
  }, [papers, reports, expanded]);
  const current = data.details.get(selected);
  const cross = data.relationMap.get(selectedEdge);
  const stored = layout.data?.layout;
  return (
    <div className="knowledge-map">
      <div className="knowledge-map-canvas">
        <div className="knowledge-map-toolbar">
          <label>
            展开论文{" "}
            <select
              aria-label="展开论文"
              value={papers.some((p) => p.id === expanded) ? expanded : ""}
              onChange={(event) => {
                setExpanded(event.target.value);
                setSelected(
                  event.target.value ? `paper:${event.target.value}` : "",
                );
              }}
            >
              <option value="">仅显示论文与汇总联系</option>
              {papers.map((paper) => (
                <option key={paper.id} value={paper.id}>
                  {paper.title}
                </option>
              ))}
            </select>
          </label>
          <button
            className="text-button"
            onClick={() => setFit((value) => value + 1)}
          >
            聚焦图谱
          </button>
        </div>
        <div className="knowledge-graph-view">
          {layout.isPending ? (
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
                selected={selected}
                language="both"
                reset={0}
                pinRequest={null}
                viewKey={key}
                fitRequest={fit}
                onSelect={(id) => {
                  setSelected(id);
                  setSelectedEdge("");
                  const item = data.details.get(id);
                  if (item?.node.type === "PAPER") setExpanded(item.paper.id);
                }}
                onEdge={(id) => {
                  setSelectedEdge(id);
                  setSelected("");
                }}
                onPositions={(positions) => updateLayout({ positions })}
                onViewport={(viewport) => updateLayout({ viewport })}
              />
            )
          )}
        </div>
        <div className="knowledge-map-legend" aria-label="知识地图图例">
          {[
            "PAPER",
            "RESEARCH_QUESTION",
            "CONCEPT",
            "METHOD",
            "CONTRIBUTION",
            "FINDING",
          ].map((kind) => (
            <span key={kind}>
              <i style={{ background: getGraphAppearance(kind).color }} />
              {getGraphAppearance(kind).label}
            </span>
          ))}
          <span>实线：论文内组织</span>
          <span>虚线：AI 跨论文联系</span>
        </div>
        {save.isError && (
          <p role="alert">布局保存失败：{errorText(save.error)}</p>
        )}
      </div>
      <aside className="knowledge-map-detail" aria-label="知识地图详情">
        {current ? (
          <>
            <span className="eyebrow">
              {getGraphAppearance(current.node.type ?? "").label}
            </span>
            <h3>{current.node.label_zh || current.node.label_en}</h3>
            {current.node.label_en && (
              <p className="muted">{current.node.label_en}</p>
            )}
            <p>{current.node.description_zh}</p>
            {current.node.type === "CONTRIBUTION" && (
              <p className="quality-note">
                作者宣称的贡献；不代表全领域新颖性已经验证。
              </p>
            )}
            <button
              className="text-button"
              onClick={() => onSelectPaper(current.paper.id)}
            >
              打开论文知识与阅读入口 <ArrowUpRight size={13} />
            </button>
            {current.node.type !== "PAPER" && (
              <SourceReferences refs={current.refs} />
            )}
          </>
        ) : cross ? (
          <>
            <span className="eyebrow">AI 联系分析</span>
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
              label="新增论文依据"
              refs={cross.relation.source_refs ?? []}
            />
            <SourceReferences
              label="已有论文依据"
              refs={cross.relation.target_refs ?? []}
            />
          </>
        ) : (
          <>
            <h3>从论文题名开始</h3>
            <p className="muted">
              点击论文展开五类知识；点击虚线核对双方依据。拖动、双击固定和缩放后会保存布局。
            </p>
            <p className="muted">
              当前显示 {papers.length} 篇论文；画布范围不决定后台分析范围。
            </p>
          </>
        )}
      </aside>
    </div>
  );
}

function KnowledgePaperPanel({
  paper,
  loading,
  error,
  collections,
  connected,
  onClose,
  onOpenPaper,
  onSaved,
}: {
  paper?: KnowledgePaper;
  loading: boolean;
  error: unknown;
  collections: KnowledgeCollection[];
  connected: boolean;
  onClose: () => void;
  onOpenPaper: Props["onOpenPaper"];
  onSaved: () => void;
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
          connected={connected}
          onOpenPaper={onOpenPaper}
          onSaved={onSaved}
          onRemoved={onClose}
        />
      ) : null}
    </KnowledgeDialog>
  );
}

function KnowledgePaperContents({
  paper,
  collections,
  connected,
  onOpenPaper,
  onSaved,
  onRemoved,
}: {
  paper: KnowledgePaper;
  collections: KnowledgeCollection[];
  connected: boolean;
  onOpenPaper: Props["onOpenPaper"];
  onSaved: () => void;
  onRemoved: () => void;
}) {
  const [versionId, setVersionId] = useState(paper.current_version?.id ?? "");
  const [note, setNote] = useState(paper.note);
  const [allowNetwork, setAllowNetwork] = useState(false);
  const version =
    paper.versions.find((item) => item.id === versionId) ??
    paper.current_version;
  const save = useMutation({
    mutationFn: () => knowledgeApi.updatePaper(paper.id, { note }),
    onSuccess: onSaved,
  });
  const archive = useMutation({
    mutationFn: () =>
      knowledgeApi.updatePaper(paper.id, { archived: !paper.archived }),
    onSuccess: onSaved,
  });
  const adopt = useMutation({
    mutationFn: () =>
      knowledgeApi.updatePaper(paper.id, { current_version_id: version!.id }),
    onSuccess: onSaved,
  });
  const membership = useMutation({
    mutationFn: ({ id, included }: { id: string; included: boolean }) =>
      knowledgeApi.setCollection(id, paper.id, included),
    onSuccess: onSaved,
  });
  const connect = useMutation({
    mutationFn: () =>
      knowledgeApi.connect(version!.id, { allow_network: true }),
    onSuccess: () => {
      setAllowNetwork(false);
      onSaved();
    },
  });
  const remove = useMutation({
    mutationFn: () => knowledgeApi.deletePaper(paper.id),
    onSuccess: () => {
      onSaved();
      onRemoved();
    },
  });
  return (
    <div className="knowledge-paper-detail">
      <h3>{paper.title}</h3>
      <div className="knowledge-detail-actions">
        {paper.source_links.map((link) => (
          <button
            key={`${link.project_id}:${link.original_paper_id}`}
            className="button secondary"
            disabled={!link.source_available || !link.paper_id}
            onClick={() => onOpenPaper(link.project_id, link.paper_id!)}
          >
            {link.source_available ? "返回论文阅读" : "原项目论文已移除"}
            <ArrowUpRight size={14} />
          </button>
        ))}
        <button
          className="text-button"
          disabled={archive.isPending}
          onClick={() => archive.mutate()}
        >
          {paper.archived ? "取消归档" : "归档论文知识"}
        </button>
      </div>
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
        {version?.evidence_status === "grounded"
          ? "带来源知识：节点依据可回查。引用合法不等于科学结论已经验证。"
          : "历史概览：尚无逐项原文定位，保留用于浏览，不参与强关系发布。"}
      </p>
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
        {collections.length ? (
          collections.map((collection) => (
            <label className="knowledge-check" key={collection.id}>
              <input
                type="checkbox"
                checked={paper.collection_ids.includes(collection.id)}
                disabled={membership.isPending}
                onChange={(event) =>
                  membership.mutate({
                    id: collection.id,
                    included: event.target.checked,
                  })
                }
              />
              {collection.name}
            </label>
          ))
        ) : (
          <p className="muted">可在知识库工具栏新建专题。</p>
        )}
      </fieldset>
      {version?.evidence_status === "grounded" && (
        <fieldset>
          <legend>与已有论文建立联系</legend>
          <label className="knowledge-check">
            <input
              type="checkbox"
              checked={allowNetwork}
              onChange={(event) => setAllowNetwork(event.target.checked)}
            />
            允许发送本版本及候选论文知识与依据进行联系分析
          </label>
          <button
            className="button primary"
            disabled={!connected || !allowNetwork || connect.isPending}
            onClick={() => connect.mutate()}
          >
            {connect.isPending ? "正在提交…" : "分析论文联系"}
          </button>
          {connect.isSuccess && (
            <p role="status">联系任务已提交，汇报会自动保存在知识库。</p>
          )}
        </fieldset>
      )}
      <details className="knowledge-remove">
        <summary>永久移除知识库条目</summary>
        <p className="muted">
          将移除此条目的知识版本、相关联系与汇报，保留原研究项目中的论文。操作前引擎会创建本机数据库备份，已消费用量继续计入预算。
        </p>
        <button
          className="button secondary"
          disabled={remove.isPending}
          onClick={() => {
            if (
              window.confirm(
                `永久移除“${paper.title}”的知识版本和相关汇报？原研究项目中的论文仍保留，操作前创建本机备份。`,
              )
            )
              remove.mutate();
          }}
        >
          永久移除此论文知识
        </button>
      </details>
      {[
        save.error,
        archive.error,
        adopt.error,
        membership.error,
        connect.error,
        remove.error,
      ]
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
  const coverageLabels: Record<string, string> = {
    eligible: "库内范围",
    selected: "入选候选",
    compared: "实际比较",
    excluded_legacy: "排除历史概览",
  };
  return (
    <article className="knowledge-report-detail">
      <div className="eyebrow">AI 联系分析 · {date(report.created_at)}</div>
      <h3>{report.title}</h3>
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
      <div className="knowledge-coverage">
        {Object.entries(coverageLabels).map(([key, label]) => (
          <span key={key}>
            {label}
            <strong>{String(report.coverage?.[key] ?? "未知")}</strong>
          </span>
        ))}
      </div>
      <p className="muted">
        {statusLabels[report.status] ?? report.status} · 比较范围：
        {(
          {
            project: "同研究项目",
            all: "全知识库",
            collection: "指定专题",
          } as Record<string, string>
        )[String(report.coverage?.scope)] ??
          String(report.coverage?.scope ?? "未记录")}
      </p>
      {report.summary?.map((item, index) => (
        <p className="knowledge-report-summary" key={index}>
          {item.text_zh}
          {!!item.relation_ids.length && (
            <span className="knowledge-summary-links">
              {item.relation_ids.map((id) => (
                <a
                  key={id}
                  href={`#knowledge-relation-${id}`}
                  onClick={(event) => {
                    event.preventDefault();
                    document
                      .getElementById(`knowledge-relation-${id}`)
                      ?.scrollIntoView({ block: "center" });
                  }}
                >
                  查看依据
                </a>
              ))}
            </span>
          )}
        </p>
      ))}
      {report.relations?.map((relation) => {
        const target = papers.find((paper) =>
          paper.versions.some(
            (version) => version.id === relation.target_version_id,
          ),
        );
        const targetId = relation.target_library_paper_id ?? target?.id;
        return (
          <section
            className="knowledge-relation"
            id={`knowledge-relation-${relation.id}`}
            key={relation.id}
          >
            <h4>{relationLabels[relation.type] ?? relation.type}</h4>
            <button
              className="text-button"
              disabled={report.stale}
              onClick={() => onLocateRelation(relation)}
            >
              在知识地图中定位这条联系 <ArrowUpRight size={13} />
            </button>
            <p>{relation.explanation_zh ?? relation.explanation}</p>
            <p className="quality-note">
              限制与差异：
              {String(
                relation.limitations_zh ??
                  relation.limitations ??
                  "未提供额外说明，请核对双方条件。",
              )}
            </p>
            <div className="knowledge-relation-sources">
              <div>
                <button
                  className="text-button"
                  disabled={!report.library_paper_id}
                  onClick={() => onOpenPaper(report.library_paper_id!)}
                >
                  在知识地图中打开新增论文
                </button>
                <SourceReferences
                  label="新增论文依据"
                  refs={relation.source_refs ?? []}
                />
              </div>
              <div>
                <button
                  className="text-button"
                  disabled={!targetId}
                  onClick={() => targetId && onOpenPaper(targetId)}
                >
                  在知识地图中打开
                  {String(relation.target_title ?? target?.title ?? "已有论文")}
                </button>
                <SourceReferences
                  label="已有论文依据"
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
  }[] = [
    { key: "max_candidates", label: "每篇最多候选论文", min: 1, max: 50 },
    {
      key: "max_requests_per_run",
      label: "每次分析最多请求数",
      min: 1,
      max: 8,
    },
    {
      key: "max_input_tokens",
      label: "单次输入 Token 预算",
      min: 1024,
      max: 2000000,
    },
    {
      key: "max_output_tokens",
      label: "单次输出 Token 预算",
      min: 256,
      max: 200000,
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
          策略保存后仅对后续事件生效。浏览、搜索、布局和打开报告均不调用模型。
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
          {numeric.map(({ key, label, min, max }) => (
            <label key={key}>
              {label}
              <input
                required
                type="number"
                min={min}
                max={max}
                step={1}
                value={value[key]}
                onChange={(event) =>
                  setValue({ ...value, [key]: Number(event.target.value) })
                }
              />
            </label>
          ))}
        </div>
        {(value.auto_collect || value.auto_connect) && !value.allow_network && (
          <p className="quality-note">
            请明确授权自动发送后保存策略。自动构建和联系分析会使用同一累计请求预算。
          </p>
        )}
        <p className="muted">
          候选数是本次优先比较范围，不代表穷尽全库。超出预算会暂停，不自动扩大费用。
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
  onOpenPaper: (projectId: string, paperId: string) => void;
  onOpenTasks: () => void;
};

export function ResearchKnowledgeBase({
  connected,
  projects,
  onOpenPaper,
  onOpenTasks,
}: Props) {
  const client = useQueryClient();
  const [tab, setTab] = useState<"map" | "papers" | "reports">(() => {
    const saved = localStorage.getItem("rgs.knowledge.tab");
    return saved === "map" || saved === "papers" ? saved : "reports";
  });
  const [projectId, setProjectId] = useState("");
  const [collectionId, setCollectionId] = useState("");
  const [search, setSearch] = useState("");
  const [archived, setArchived] = useState(false);
  const [offset, setOffset] = useState(0);
  const [reportOffset, setReportOffset] = useState(0);
  const [selectedPaper, setSelectedPaper] = useState("");
  const [selectedReport, setSelectedReport] = useState("");
  const [mapFocus, setMapFocus] = useState("");
  const [mapOtherFocus, setMapOtherFocus] = useState("");
  const [mapRelation, setMapRelation] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [collectionOpen, setCollectionOpen] = useState(false);
  const [collectionName, setCollectionName] = useState("");
  const [notice, setNotice] = useState("");
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["knowledge"] });
    void client.invalidateQueries({ queryKey: ["jobs"] });
    void client.invalidateQueries({ queryKey: ["lite-usage"] });
  };
  const library = useQuery({
    queryKey: ["knowledge", "library"],
    queryFn: knowledgeApi.library,
    enabled: connected,
  });
  const papers = useQuery({
    queryKey: [
      "knowledge",
      "papers",
      projectId,
      collectionId,
      search,
      archived,
      offset,
    ],
    queryFn: () =>
      knowledgeApi.papers({
        project_id: projectId,
        collection_id: collectionId,
        search,
        include_archived: archived,
        offset,
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
    queryFn: knowledgeApi.runs,
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
  const createCollection = useMutation({
    mutationFn: () => knowledgeApi.createCollection(collectionName.trim()),
    onSuccess: (value) => {
      setCollectionId(value.id);
      setCollectionName("");
      setCollectionOpen(false);
      refresh();
    },
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
    setTab(value);
    localStorage.setItem("rgs.knowledge.tab", value);
  };
  const items = papers.data?.items ?? [];
  const mapPapers = [
    ...new Map(
      [
        ...items,
        ...(focusedPaper.data ? [focusedPaper.data] : []),
        ...(otherFocusedPaper.data ? [otherFocusedPaper.data] : []),
      ].map((paper) => [paper.id, paper]),
    ).values(),
  ];
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
          <div className="eyebrow">RESEARCH KNOWLEDGE</div>
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
            className={tab === value ? "active" : ""}
            aria-current={tab === value ? "page" : undefined}
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
      <div className="knowledge-filters">
        <label className="knowledge-search">
          <Search size={15} />
          <input
            aria-label="搜索知识库"
            value={search}
            onChange={(event) => filters(() => setSearch(event.target.value))}
            placeholder="搜索论文、研究问题与概念"
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
          className="text-button"
          onClick={() => setCollectionOpen(!collectionOpen)}
        >
          <FolderPlus size={14} />
          新建专题
        </button>
        {tab !== "reports" && (
          <label className="knowledge-check">
            <input
              type="checkbox"
              checked={archived}
              onChange={(event) =>
                filters(() => setArchived(event.target.checked))
              }
            />
            包括已归档
          </label>
        )}
      </div>
      {collectionOpen && (
        <form
          className="knowledge-inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            createCollection.mutate();
          }}
        >
          <input
            autoFocus
            aria-label="专题名称"
            placeholder="专题名称"
            maxLength={120}
            value={collectionName}
            onChange={(event) => setCollectionName(event.target.value)}
          />
          <button
            className="button secondary"
            disabled={!collectionName.trim() || createCollection.isPending}
          >
            创建专题
          </button>
          <button
            type="button"
            className="text-button"
            onClick={() => setCollectionOpen(false)}
          >
            取消
          </button>
        </form>
      )}
      {[
        library.error,
        papers.error,
        collections.error,
        reports.error,
        usage.error,
        reportScope.error,
        focusedPaper.error,
        otherFocusedPaper.error,
        runs.error,
        updateReport.error,
        createCollection.error,
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
            <div key={run.id}>
              <span>
                {run.kind === "extract" ? "论文知识建模" : "论文联系分析"} ·{" "}
                {statusLabels[run.status] ?? run.status}
                {typeof run.request_count === "number" &&
                  ` · 已发送 ${run.request_count} / 预算 ${run.max_requests ?? "未知"} 次请求`}
              </span>
              {run.error && <span className="error-text">{run.error}</span>}
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
      {tab === "map" ? (
        <KnowledgeMap
          key={`${projectId}:${collectionId}:${mapFocus}:${mapRelation}`}
          focusedPaper={mapFocus}
          focusedRelation={mapRelation}
          onOpenReport={(id) => {
            const report = allReports.find((item) => item.id === id);
            if (report) openReport(report);
            else setSelectedReport(id);
          }}
          papers={mapPapers}
          reports={allReports}
          connected={connected}
          viewKey={`${projectId || "all"}:${collectionId || "all"}`}
          onSelectPaper={setSelectedPaper}
        />
      ) : tab === "papers" ? (
        <div className="knowledge-paper-list">
          {items.map((paper) => (
            <button
              className={`knowledge-paper-row${selectedPaper === paper.id ? " selected" : ""}`}
              key={paper.id}
              onClick={() => setSelectedPaper(paper.id)}
            >
              <span className="knowledge-paper-icon">
                <Library size={18} />
              </span>
              <span className="knowledge-paper-title">
                <strong>{paper.title}</strong>
                <small>
                  {paper.current_version?.evidence_status === "grounded"
                    ? "带来源知识"
                    : "历史概览 · 尚无逐项来源"}
                  {paper.archived ? " · 已归档" : ""}
                  {paper.current_version
                    ? ` · ${date(paper.current_version.created_at)}`
                    : ""}
                </small>
              </span>
              <span className="knowledge-row-count">
                {paper.current_version?.content.graph?.nodes.filter(
                  (node) => node.type !== "PAPER",
                ).length ?? 0}{" "}
                项知识
              </span>
              <ArrowUpRight size={15} />
            </button>
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
      {!papers.isPending &&
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
      {tab !== "reports" && (papers.data?.total ?? 0) > 50 && (
        <div className="knowledge-pagination">
          <span>
            显示 {offset + 1}–{Math.min(offset + 50, papers.data?.total ?? 0)} /{" "}
            {papers.data?.total}
          </span>
          <button
            className="text-button"
            disabled={!offset}
            onClick={() => setOffset(Math.max(0, offset - 50))}
          >
            上一页
          </button>
          <button
            className="text-button"
            disabled={offset + 50 >= (papers.data?.total ?? 0)}
            onClick={() => setOffset(offset + 50)}
          >
            下一页
          </button>
        </div>
      )}
      {tab === "reports" && visibleReports.length > 50 && (
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
          connected={connected}
          onClose={() => setSelectedPaper("")}
          onOpenPaper={onOpenPaper}
          onSaved={refresh}
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
            setProjectId("");
            setCollectionId("");
            setSearch("");
            setOffset(0);
            setMapFocus(id);
            setMapOtherFocus("");
            setMapRelation("");
            selectTab("map");
          }}
          onLocateRelation={(relation) => {
            setSelectedReport("");
            setProjectId("");
            setCollectionId("");
            setSearch("");
            setOffset(0);
            setMapFocus(reportDetail.data?.library_paper_id ?? "");
            setMapOtherFocus(
              relation.target_library_paper_id ??
                items.find((paper) =>
                  paper.versions.some(
                    (version) => version.id === relation.target_version_id,
                  ),
                )?.id ??
                "",
            );
            setMapRelation(relation.id);
            selectTab("map");
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
    </section>
  );
}
