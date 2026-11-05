import { useEffect, useMemo, useRef, useState } from "react";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  LocateFixed,
  RotateCcw,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { invoke } from "@tauri-apps/api/core";
import { type Viewport } from "@xyflow/react";
import { ForceGraph } from "./ForceGraph";
import "@xyflow/react/dist/style.css";
import type { components } from "../../../packages/contracts/generated";
import { api, request, type Job } from "./api";
import { GraphExplorer, ProposalReview } from "./GraphExplorer";
import { ReadingControls } from "./ReadingControls";
import { GraphPanel } from "./GraphPanel";
import { GraphLegend, graphKindLabels } from "./graphAppearance";
import { placeNodes } from "./graphLayout";

type Graph = components["schemas"]["GraphProjection"];
type Layout = components["schemas"]["LayoutView"];
type Detail = components["schemas"]["ProjectionDetail"];
type Kind = Graph["nodes"][number]["kind"];
const kinds = graphKindLabels;
const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));

async function listGraphPapers(projectId: string) {
  const items = new Map<
    string,
    Awaited<ReturnType<typeof api.papers>>["items"][number]
  >();
  let cursor: number | null = 0;
  const visited = new Set<number>();
  while (cursor !== null) {
    if (visited.has(cursor))
      throw new Error("论文列表分页已变化，请刷新后重试");
    visited.add(cursor);
    const page = await api.papers(projectId, cursor);
    page.items.forEach((paper) => items.set(paper.id, paper));
    cursor = page.next_cursor;
  }
  return { items: [...items.values()], next_cursor: null };
}

export function GraphWorkspace({
  projectId,
  connected,
  initialFocus = "",
}: {
  projectId: string;
  connected: boolean;
  initialFocus?: string;
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
          initialFocus={initialFocus}
        />
      )}
    </section>
  );
}

function ProjectionExplorer({
  projectId,
  connected,
  onCompare,
  initialFocus = "",
}: {
  projectId: string;
  connected: boolean;
  onCompare: (id: string) => void;
  initialFocus?: string;
}) {
  const client = useQueryClient();
  const base = `/api/v1/projects/${projectId}/graph`;
  const [expanded, setExpanded] = useState<string[]>([]);
  const [collapsed, setCollapsed] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<Kind | "">("");
  const [paper, setPaper] = useState("");
  const [optionsPaper, setOptionsPaper] = useState("");
  const [focus, setFocus] = useState(initialFocus);
  const [depth, setDepth] = useState(1);
  const [ai, setAi] = useState(true);
  const [cursors, setCursors] = useState([""]);
  const [selected, setSelected] = useState(initialFocus);
  const [edge, setEdge] = useState<Graph["edges"][number] | null>(null);
  const [language, setLanguage] = useState("zh");
  const [reset, setReset] = useState(0);
  const [fitRequest, setFitRequest] = useState(0);
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
  const viewKey = JSON.stringify([
    query,
    kind,
    paper,
    focus,
    depth,
    cursors.at(-1),
  ]);
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
      collapsed,
    ],
    queryFn: async () => ({
      ...(await request<Graph>("POST", `${base}/projection`, {
        view: "paper_backbone",
        expanded_unit_ids: expanded,
        collapsed_unit_ids: collapsed,
        search: query,
        kinds: kind ? [kind] : Object.keys(kinds),
        paper_id: paper,
        focus_id: focus,
        depth,
        include_ai_candidates: ai,
        include_paper_context: true,
        limit: 60,
        cursor: cursors.at(-1),
      })),
      viewKey,
    }),
    enabled: connected,
    placeholderData: keepPreviousData,
    refetchInterval: cursors.length === 1 ? 3000 : false,
  });
  const papers = useQuery({
    queryKey: ["graph-papers", projectId],
    queryFn: () => listGraphPapers(projectId),
    enabled: connected,
    refetchInterval: 15000,
  });
  const readingPapers = useMemo(() => {
    const values = new Map(
      (papers.data?.items ?? []).map((p) => [
        p.id,
        { id: p.id, title: p.title },
      ]),
    );
    graph.data?.paper_builds?.forEach((p) =>
      values.set(p.paper_id, { id: p.paper_id, title: p.title }),
    );
    return [...values.values()];
  }, [papers.data, graph.data]);
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
  function resetFilters() {
    setSearch("");
    setQuery("");
    setKind("");
    setPaper("");
    setFocus("");
    setDepth(1);
    resetPage();
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
      <section className="graph-query-toolbar" aria-label="图谱搜索与筛选">
        <form
          className="graph-search"
          onSubmit={(e) => {
            e.preventDefault();
            setQuery(search);
            setFocus("");
            resetPage();
          }}
        >
          <Search size={18} aria-hidden="true" />
          <input
            aria-label="搜索图谱"
            placeholder="搜索知识或论文"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button className="button">搜索</button>
          {(query || kind || paper || focus) && (
            <button
              className="text-button"
              type="button"
              onClick={resetFilters}
            >
              重置筛选
            </button>
          )}
        </form>
        <div className="graph-filters">
          <SlidersHorizontal size={16} aria-hidden="true" />
          <label>
            节点类型
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
          </label>
          <label>
            论文
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
              {readingPapers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            显示语言
            <select
              aria-label="图谱语言"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              <option value="zh">中文优先</option>
              <option value="en">English</option>
              <option value="both">中英对照</option>
            </select>
          </label>
          <label className="graph-filters__checkbox">
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
              <button className="text-button" onClick={resetFilters}>
                返回项目全图
              </button>
            </>
          )}
        </div>
        {papers.error && <p role="alert">{errorText(papers.error)}</p>}
      </section>
      <GraphPanel
        title="知识图谱展示"
        legend={<GraphLegend />}
        toolbar={
          <>
            <button
              className="text-button"
              disabled={!graph.data?.nodes.length}
              onClick={() => setFitRequest((value) => value + 1)}
            >
              <LocateFixed size={15} aria-hidden="true" />
              适应图谱
            </button>
            <button
              className="text-button"
              disabled={!current || !graph.data?.nodes.length}
              onClick={rearrange}
            >
              <RotateCcw size={15} aria-hidden="true" />
              重新布局未固定节点
            </button>
            {collapsed.length > 0 && (
              <button
                className="text-button"
                onClick={() => {
                  setCollapsed([]);
                  setExpanded([]);
                  resetPage();
                }}
              >
                展开全部支撑
              </button>
            )}
          </>
        }
      >
        {(graph.isPending || graph.isPlaceholderData) && (
          <p className="quiet-note" role="status">
            正在加载筛选结果…
          </p>
        )}
        {graph.data?.paper_builds
          ?.filter((b) => b.ranking_status === "pending")
          .map((build) => (
            <p
              className="quiet-note"
              key={`ranking:${build.paper_id}`}
              role="status"
            >
              {build.title}：核心贡献排序未完成，当前展示结论候选与已有支撑。
            </p>
          ))}
        {!!graph.data?.coverage_gaps?.length && (
          <details>
            <summary>构建范围与限制</summary>
            {graph.data.coverage_gaps.map((g, i) => (
              <p key={i}>{g}</p>
            ))}
          </details>
        )}
        <p className="quiet-note">
          单击查看 · 拖动联动 · 双击固定/解除 · 滚轮缩放 ·
          实线为结论导航，虚线为 AI 科学关系推断。版本{" "}
          {graph.data?.graph_revision ?? "—"} ·{" "}
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
                viewKey={graph.data.viewKey}
                fitRequest={fitRequest}
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
                  {["core", "provisional"].includes(
                    graph.data?.nodes.find((n) => n.id === selected)
                      ?.graph_role ?? "",
                  ) &&
                    (
                      graph.data?.nodes.find((n) => n.id === selected)
                        ?.unit_ids ?? []
                    ).map((uid) => (
                      <button
                        key={uid}
                        className="button secondary"
                        onClick={() => {
                          if (collapsed.includes(uid)) {
                            setCollapsed((old) => old.filter((x) => x !== uid));
                            setExpanded((old) => [...old, uid]);
                          } else {
                            setExpanded((old) => old.filter((x) => x !== uid));
                            setCollapsed((old) => [...old, uid]);
                          }
                          setCursors([""]);
                        }}
                      >
                        {collapsed.includes(uid) ? "展开支撑" : "收起支撑"}
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
          {cursors.length > 1 && (
            <button className="text-button" onClick={resetPage}>
              返回第一页
            </button>
          )}
          <button
            className="button secondary"
            disabled={cursors.length === 1 || graph.isPlaceholderData}
            onClick={() => {
              setCursors(cursors.slice(0, -1));
              setSelected("");
              setEdge(null);
            }}
          >
            上一页
          </button>
          <button
            className="button secondary"
            disabled={!graph.data?.next_cursor || graph.isPlaceholderData}
            onClick={() => {
              setCursors([...cursors, graph.data!.next_cursor!]);
              setSelected("");
              setEdge(null);
            }}
          >
            下一页
          </button>
          <span>
            本页 {new Set(graph.data?.nodes.map((node) => node.paper_id)).size}{" "}
            篇论文 · {graph.data?.nodes.length ?? 0} 个节点
            {graph.data?.has_more
              ? " · 还有更多节点，可翻页或筛选单篇论文"
              : ""}
          </span>
        </div>
      </GraphPanel>
      <section
        className="graph-reading-options"
        aria-label="论文候选与建图选项"
      >
        <h3>论文候选与建图选项</h3>
        {readingPapers.length === 0 && <p className="muted">项目暂无论文。</p>}
        {readingPapers.map((item) => {
          const build = graph.data?.paper_builds?.find(
            (value) => value.paper_id === item.id,
          );
          const open = optionsPaper === item.id;
          return (
            <article className="graph-reading-paper" key={item.id}>
              <div className="graph-reading-paper__heading">
                <div>
                  <h4>{item.title}</h4>
                  {build && (
                    <p className="quiet-note">
                      已保存 {build.candidate_count} 条新版候选 ·{" "}
                      {build.published_units
                        ? `${build.published_units} 个结论单元`
                        : "核心图谱尚未发布"}
                      {build.total_batches > 0 &&
                        ` · 抽取 ${build.completed_batches}/${build.total_batches} 批`}
                    </p>
                  )}
                </div>
                <button
                  className="text-button"
                  aria-expanded={open}
                  aria-controls={`reading-options-${item.id}`}
                  onClick={() => setOptionsPaper(open ? "" : item.id)}
                >
                  {open ? "收起候选与建图选项" : "查看已保存候选与建图选项"}
                </button>
              </div>
              {open && (
                <div id={`reading-options-${item.id}`}>
                  <ReadingControls
                    paperId={item.id}
                    connected={connected}
                    onSelect={(id) => {
                      setSelected(id);
                      setEdge(null);
                    }}
                  />
                </div>
              )}
            </article>
          );
        })}
      </section>
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
