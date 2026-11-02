import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";
import { type Viewport } from "@xyflow/react";
import { ForceGraph } from "./ForceGraph";
import "@xyflow/react/dist/style.css";
import type { components } from "../../../packages/contracts/generated";
import { api, request, type Job } from "./api";
import { GraphExplorer, ProposalReview } from "./GraphExplorer";
import { ReadingControls } from "./ReadingControls";
import { JobHistory } from "./JobHistory";
import { placeNodes } from "./graphLayout";

type Graph = components["schemas"]["GraphProjection"];
type Layout = components["schemas"]["LayoutView"];
type Detail = components["schemas"]["ProjectionDetail"];
type Kind = Graph["nodes"][number]["kind"];
const kinds: Record<Kind, string> = {
  Paper: "论文",
  Concept: "概念",
  Method: "方法",
  Claim: "主张",
  ResearchQuestion: "研究问题",
  Experiment: "实验",
  Condition: "条件",
  Finding: "结果",
  Metric: "指标",
  Argument: "论证",
  Limitation: "限制",
};
const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));

export function GraphWorkspace({
  projectId,
  connected,
}: {
  projectId: string;
  connected: boolean;
}) {
  const [compare, setCompare] = useState(false);
  const [sourceId, setSourceId] = useState("");
  return (
    <section className="graph-workspace">
      <div className="section-heading">
        <h2>知识图谱</h2>
        <button
          className="button secondary"
          onClick={() => setCompare(!compare)}
        >
          {compare ? "返回图谱" : "Claim Comparator / 实体对齐"}
        </button>
      </div>
      {compare ? (
        <GraphExplorer
          projectId={projectId}
          connected={connected}
          initialSourceId={sourceId}
        />
      ) : (
        <ProjectionExplorer
          key={projectId}
          projectId={projectId}
          connected={connected}
          onCompare={(id) => {
            setSourceId(id);
            setCompare(true);
          }}
        />
      )}
    </section>
  );
}

function ProjectionExplorer({
  projectId,
  connected,
  onCompare,
}: {
  projectId: string;
  connected: boolean;
  onCompare: (id: string) => void;
}) {
  const client = useQueryClient();
  const base = `/api/v1/projects/${projectId}/graph`;
  const [expanded, setExpanded] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<Kind | "">("");
  const [paper, setPaper] = useState("");
  const [focus, setFocus] = useState("");
  const [depth, setDepth] = useState(1);
  const [ai, setAi] = useState(true);
  const [cursors, setCursors] = useState([""]);
  const [selected, setSelected] = useState("");
  const [edge, setEdge] = useState<Graph["edges"][number] | null>(null);
  const [language, setLanguage] = useState("zh");
  const [reset, setReset] = useState(0);
  const [layoutEpoch, setLayoutEpoch] = useState(0);
  const [pinRequest, setPinRequest] = useState<{
    id: string;
    seq: number;
  } | null>(null);
  const draftKey = `researchgraph.layout-draft.${projectId}`;
  const [draft, setDraft] = useState<Layout | null>(() => {
    try {
      const value = JSON.parse(localStorage.getItem(draftKey) ?? "null");
      return value &&
        Array.isArray(value.positions) &&
        Number.isFinite(value.version)
        ? value
        : null;
    } catch {
      return null;
    }
  });
  const [dirty, setDirty] = useState(!!draft);
  const [conflict, setConflict] = useState(false);
  const generation = useRef(0);
  const graph = useQuery({
    queryKey: [
      "projection",
      projectId,
      query,
      kind,
      paper,
      focus,
      depth,
      ai,
      cursors.at(-1),
      expanded,
    ],
    queryFn: () =>
      request<Graph>("POST", `${base}/projection`, {
        view: "paper_backbone",
        expanded_unit_ids: expanded,
        search: query,
        kinds: kind ? [kind] : Object.keys(kinds),
        paper_id: paper,
        focus_id: focus,
        depth,
        include_ai_candidates: ai,
        include_paper_context: true,
        limit: 60,
        cursor: cursors.at(-1),
      }),
    enabled: connected,
    refetchInterval: cursors.length === 1 ? 3000 : false,
  });
  const papers = useQuery({
    queryKey: ["graph-papers", projectId],
    queryFn: () => api.papers(projectId),
    enabled: connected,
  });
  const layout = useQuery({
    queryKey: ["layout", projectId],
    queryFn: () => request<Layout>("GET", `${base}/layout`),
    enabled: connected,
    refetchOnWindowFocus: false,
  });
  const current = draft ?? layout.data;
  const positions = useMemo(
    () => (graph.data ? placeNodes(graph.data, current?.positions ?? []) : []),
    [graph.data, current?.positions],
  );
  const visible = useMemo(
    () => new Map(positions.map((p) => [p.node_id, p])),
    [positions],
  );
  const save = useMutation({
    mutationFn: async (body: Layout) => {
      const sent = generation.current;
      const value = await request<Layout>("POST", `${base}/layout`, {
        expected_version: body.version,
        positions: body.positions,
        zoom: body.zoom,
        pan_x: body.pan_x,
        pan_y: body.pan_y,
      });
      return { value, sent };
    },
    onSuccess: ({ value, sent }) => {
      client.setQueryData(["layout", projectId], value);
      setDraft((previous) =>
        previous ? { ...previous, version: value.version } : value,
      );
      if (sent === generation.current) {
        setDirty(false);
        localStorage.removeItem(draftKey);
      } else {
        const cached = JSON.parse(localStorage.getItem(draftKey) ?? "null");
        if (cached)
          localStorage.setItem(
            draftKey,
            JSON.stringify({ ...cached, version: value.version }),
          );
      }
    },
    onError: () => setConflict(true),
  });
  const mutateSave = save.mutate;
  useEffect(() => {
    if (!dirty || !draft || !connected || save.isPending || conflict) return;
    const timer = window.setTimeout(() => mutateSave(draft), 700);
    return () => window.clearTimeout(timer);
  }, [dirty, draft, connected, save.isPending, conflict, mutateSave]);
  function changeLayout(next: Layout) {
    generation.current++;
    localStorage.setItem(draftKey, JSON.stringify(next));
    setDraft(next);
    setDirty(true);
  }
  function commitPositions(next: Layout["positions"]) {
    if (!current) return;
    const merged = new Map(
      (current.positions ?? []).map((p) => [p.node_id, p]),
    );
    next?.forEach((p) => merged.set(p.node_id, p));
    changeLayout({ ...current, positions: [...merged.values()] });
  }
  function viewportChanged(v: Viewport) {
    if (
      current &&
      (Math.abs(current.pan_x - v.x) > 0.1 ||
        Math.abs(current.pan_y - v.y) > 0.1 ||
        Math.abs(current.zoom - v.zoom) > 0.001)
    )
      changeLayout({
        ...current,
        positions: [
          ...new Map(
            [...(current.positions ?? []), ...positions].map((p) => [
              p.node_id,
              p,
            ]),
          ).values(),
        ],
        pan_x: v.x,
        pan_y: v.y,
        zoom: v.zoom,
      });
  }
  function resetPage() {
    setCursors([""]);
    setSelected("");
    setEdge(null);
  }
  function rearrange() {
    setReset((value) => value + 1);
  }
  const detail = useQuery({
    queryKey: [
      "projection-detail",
      projectId,
      selected,
      graph.data?.graph_revision,
    ],
    queryFn: () => request<Detail>("GET", `${base}/nodes/${selected}`),
    enabled: connected && !!selected,
  });
  return (
    <>
      <div className="import-controls">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setQuery(search);
            resetPage();
          }}
        >
          <input
            aria-label="搜索图谱"
            placeholder="搜索知识或论文"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button className="button secondary">搜索</button>
        </form>
        <select
          aria-label="节点类型"
          value={kind}
          onChange={(e) => {
            setKind(e.target.value as Kind | "");
            setFocus("");
            resetPage();
          }}
        >
          <option value="">全部类型</option>
          {Object.entries(kinds).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <select
          aria-label="论文筛选"
          value={paper}
          onChange={(e) => {
            setPaper(e.target.value);
            setFocus("");
            resetPage();
          }}
        >
          <option value="">全部论文</option>
          {papers.data?.items.map((p) => (
            <option key={p.id} value={p.id}>
              {p.title}
            </option>
          ))}
        </select>
        <select
          aria-label="图谱语言"
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
        >
          <option value="zh">中文优先</option>
          <option value="en">English</option>
          <option value="both">中英对照</option>
        </select>
        <label>
          <input
            type="checkbox"
            checked={ai}
            onChange={(e) => {
              setAi(e.target.checked);
              resetPage();
            }}
          />{" "}
          AI 候选关系
        </label>
        {focus && (
          <>
            <label>
              邻域深度{" "}
              <select
                value={depth}
                onChange={(e) => setDepth(Number(e.target.value))}
              >
                {[1, 2, 3].map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
            </label>
            <button
              className="text-button"
              onClick={() => {
                setFocus("");
                resetPage();
              }}
            >
              返回项目全图
            </button>
          </>
        )}
      </div>
      {paper && (
        <ReadingControls
          paperId={paper}
          connected={connected}
          onSelect={setSelected}
        />
      )}
      {!!graph.data?.coverage_gaps?.length && (
        <details>
          <summary>构建范围与限制</summary>
          {graph.data.coverage_gaps.map((g, i) => (
            <p key={i}>{g}</p>
          ))}
        </details>
      )}
      <button
        className="text-button"
        disabled={!current || !graph.data?.nodes.length}
        onClick={rearrange}
      >
        重新布局未固定节点
      </button>
      <p className="quiet-note">
        单击查看 · 拖动联动 · 双击固定/解除 · 滚轮缩放 · 实线为结论导航，虚线为
        AI 科学关系推断。版本 {graph.data?.graph_revision ?? "—"} ·{" "}
        {dirty ? "布局待保存" : "布局已同步"}
      </p>
      {[graph.error, layout.error, detail.error, save.error]
        .filter(Boolean)
        .map((e, i) => (
          <p role="alert" key={i}>
            {errorText(e)}
          </p>
        ))}
      {conflict && (
        <button
          className="button secondary"
          onClick={async () => {
            const value = await layout.refetch();
            if (value.data) {
              generation.current++;
              localStorage.removeItem(draftKey);
              setDraft(value.data);
              setDirty(false);
              setConflict(false);
              setLayoutEpoch((value) => value + 1);
              save.reset();
            }
          }}
        >
          重新加载服务器布局（放弃未保存位置）
        </button>
      )}
      <div className="projection-grid">
        <div className="projection-canvas" aria-label="交互知识图谱">
          {current && graph.data && (
            <ForceGraph
              key={layoutEpoch}
              graph={graph.data}
              layout={current}
              reset={reset}
              pinRequest={pinRequest}
              selected={selected}
              language={language}
              onPositions={commitPositions}
              onViewport={viewportChanged}
              onSelect={(id) => {
                setSelected(id);
                setEdge(null);
              }}
              onEdge={(id) => {
                setEdge(graph.data?.edges.find((e) => e.id === id) ?? null);
                setSelected("");
              }}
            />
          )}
          {graph.data?.nodes.length === 0 && (
            <p className="graph-empty">
              当前筛选下暂无知识。选择 Zotero 论文开始建图。
            </p>
          )}
        </div>
        <aside className="node-inspector" aria-label="节点详情">
          {detail.data ? (
            <>
              <div className="import-controls">
                {graph.data?.nodes.find((n) => n.id === selected)
                  ?.graph_role === "core" &&
                  (
                    graph.data.nodes.find((n) => n.id === selected)?.unit_ids ??
                    []
                  ).map((uid) => (
                    <button
                      key={uid}
                      className="button secondary"
                      onClick={() => {
                        setExpanded((old) =>
                          old.includes(uid)
                            ? old.filter((x) => x !== uid)
                            : [...old, uid],
                        );
                        setCursors([""]);
                      }}
                    >
                      {expanded.includes(uid) ? "收起支撑" : "展开支撑"}
                    </button>
                  ))}
                <button
                  className="text-button"
                  onClick={() => {
                    setPinRequest((previous) => ({
                      id: selected,
                      seq: (previous?.seq ?? 0) + 1,
                    }));
                  }}
                >
                  {visible.get(selected)?.pinned ? "解除固定" : "固定节点"}
                </button>
                <button
                  className="text-button"
                  onClick={() => {
                    setFocus(selected);
                    setCursors([""]);
                  }}
                >
                  聚焦邻域
                </button>
                {detail.data.node &&
                  ["claim", "concept", "method"].includes(
                    detail.data.node.kind,
                  ) && (
                    <button
                      className="text-button"
                      onClick={() => onCompare(selected)}
                    >
                      比较 / 对齐
                    </button>
                  )}
              </div>
              <NodeInspector
                key={selected}
                detail={detail.data}
                projectId={projectId}
                connected={connected}
                language={language}
              />
            </>
          ) : edge ? (
            <>
              <h3>{edge.label_zh}</h3>
              <p>
                {edge.epistemic_status === "navigation"
                  ? "导航连接"
                  : edge.epistemic_status === "model_inferred"
                    ? "模型推断关系"
                    : edge.epistemic_status === "source_reported"
                      ? "原文关系"
                      : edge.epistemic_status}
              </p>
              {edge.detail_ref?.includes("/relations/") ? (
                <ProposalReview
                  key={edge.id}
                  selection={{ id: edge.id, kind: "relation" }}
                  connected={connected}
                />
              ) : (
                <button
                  className="text-button"
                  onClick={() => {
                    setSelected(edge.source);
                    setEdge(null);
                  }}
                >
                  查看来源节点与证据
                </button>
              )}
            </>
          ) : (
            <p className="muted">
              选择节点查看完整知识、实验条件、原文证据与历史。
            </p>
          )}
        </aside>
      </div>
      <div className="import-controls">
        <button
          className="button secondary"
          disabled={cursors.length === 1}
          onClick={() => {
            setCursors(cursors.slice(0, -1));
            setSelected("");
          }}
        >
          上一页
        </button>
        <button
          className="button secondary"
          disabled={!graph.data?.next_cursor}
          onClick={() => {
            setCursors([...cursors, graph.data!.next_cursor!]);
            setSelected("");
          }}
        >
          下一页
        </button>
        <span>
          本页 {graph.data?.nodes.length ?? 0} 个节点
          {graph.data?.has_more ? " · 还有更多，可缩小筛选或聚焦邻域" : ""}
        </span>
      </div>
      <JobHistory projectId={projectId} connected={connected} />
    </>
  );
}

function NodeInspector({
  detail,
  projectId,
  connected,
  language,
}: {
  detail: Detail;
  projectId: string;
  connected: boolean;
  language: string;
}) {
  const client = useQueryClient();
  const [evidenceId, setEvidenceId] = useState(detail.evidence[0]?.id ?? "");
  const [openError, setOpenError] = useState("");
  const provider = "project";
  const [allow, setAllow] = useState(false);
  const evidence = detail.evidence.find((e) => e.id === evidenceId);
  const preview = useQuery({
    queryKey: ["preview", evidenceId],
    queryFn: () => api.preview(evidenceId),
    enabled: connected && !!evidenceId,
    retry: false,
  });
  const node = useQuery({
    queryKey: ["node", detail.id, detail.graph_revision],
    queryFn: () => api.node(detail.id),
    enabled: connected && !!detail.node,
  });
  const translate = useMutation({
    mutationFn: () =>
      request<Job>(
        "POST",
        `/api/v1/projects/${projectId}/graph/translate`,
        { node_ids: [detail.id], provider, allow_network: allow },
        crypto.randomUUID(),
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["jobs", projectId] });
    },
  });
  const zh = String(detail.display.summary_zh ?? "");
  return (
    <>
      <h3>
        {String(
          (language !== "en" && detail.display.label_zh) ||
            detail.display.label_en ||
            detail.title,
        )}
      </h3>
      <small>{detail.title}</small>
      {language !== "en" && zh && <p>{zh}</p>}
      {(language !== "zh" || !zh) && (
        <p>{String(detail.display.summary_en ?? detail.node?.text ?? "")}</p>
      )}
      <p className="quiet-note">
        {detail.node?.source_status} · {detail.node?.origin}
        {detail.display.translation_status
          ? ` · 译文 ${String(detail.display.translation_status)}`
          : ""}
      </p>
      {detail.zotero_url && (
        <button
          className="button secondary"
          onClick={() =>
            void invoke("open_zotero", { url: detail.zotero_url }).catch((e) =>
              setOpenError(errorText(e)),
            )
          }
        >
          在 Zotero 中打开
        </button>
      )}
      {openError && <p role="alert">{openError}</p>}
      {detail.node && (
        <details>
          <summary>按需补译中文显示</summary>
          <p>使用全局 Extraction 模型</p>
          <label>
            <input
              type="checkbox"
              checked={allow}
              onChange={(e) => setAllow(e.target.checked)}
            />
            同意发送此节点英文给已配置模型
          </label>
          <button
            className="button secondary"
            disabled={!connected || translate.isPending || !allow}
            onClick={() => translate.mutate()}
          >
            补译显示字段
          </button>
          {translate.error && <p role="alert">{errorText(translate.error)}</p>}
          {translate.isSuccess && <p>补译已排队，英文与科学内容保持不变。</p>}
        </details>
      )}
      {!!detail.related.length && (
        <details>
          <summary>方法、实验与条件 · {detail.related.length}</summary>
          {detail.related.map((n) => (
            <article className="inspector-fact" key={n.id}>
              <small>
                {n.kind} · {n.known_state ?? "原文候选"}
              </small>
              <p>
                {language === "en"
                  ? n.text
                  : String(
                      n.payload.statement_zh ||
                        n.payload.name_zh ||
                        n.payload.value_zh ||
                        n.text,
                    )}
              </p>
              {language === "both" && <p>{n.text}</p>}
              {n.value && (
                <p>
                  {n.value} {n.unit}
                </p>
              )}
            </article>
          ))}
        </details>
      )}
      <details open={!!evidence}>
        <summary>原文证据 · {detail.evidence.length}</summary>
        {detail.evidence.map((e, i) => (
          <button
            key={e.id}
            className="text-button"
            onClick={() => setEvidenceId(e.id)}
          >
            证据 {i + 1} · 第 {e.page_index + 1} 页
          </button>
        ))}
        {evidence && (
          <>
            <blockquote>{evidence.quote}</blockquote>
            <small>
              {evidence.id} · offset {evidence.start_offset}–
              {evidence.end_offset}
            </small>
            {preview.data && (
              <img
                className="evidence-image"
                src={preview.data.data_url}
                alt="PDF 证据位置"
              />
            )}
            {preview.error && <p role="alert">{errorText(preview.error)}</p>}
          </>
        )}
      </details>
      {node.data && (
        <details>
          <summary>模型来源与历史</summary>
          <details>
            <summary>原始模型记录</summary>
            <pre>{JSON.stringify(node.data.model_run, null, 2)}</pre>
          </details>
        </details>
      )}
    </>
  );
}
