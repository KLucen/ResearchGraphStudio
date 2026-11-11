import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type OverviewLayout, type OverviewView } from "./api";
import { ForceGraph } from "./ForceGraph";
import { GraphLegend } from "./graphAppearance";
import type { GraphData } from "./graphTypes";

const errorText = (value: unknown) =>
  value instanceof Error ? value.message : String(value);

type PaperOverviewProps = {
  paperId: string;
  revisionId: string;
  projectId: string;
  connected: boolean;
};

export function PaperOverview(props: PaperOverviewProps) {
  return (
    <PaperOverviewSession
      key={`${props.paperId}:${props.revisionId}`}
      {...props}
    />
  );
}

function PaperOverviewSession({
  paperId,
  revisionId,
  projectId,
  connected,
}: PaperOverviewProps) {
  const client = useQueryClient();
  const [allowNetwork, setAllowNetwork] = useState(false);
  const [selectedNode, setSelectedNode] = useState("");
  const [selectedEdge, setSelectedEdge] = useState("");
  const [layout, setLayout] = useState<OverviewLayout | null>(null);
  const [reset, setReset] = useState(0);
  const pendingLayout = useRef<OverviewLayout | null>(null);
  const layoutTimer = useRef<number | null>(null);
  const layoutWrites = useRef<Promise<unknown>>(Promise.resolve());
  const previousStatus = useRef<string | undefined>(undefined);
  const overview = useQuery({
    queryKey: ["overview", paperId, revisionId],
    queryFn: () => api.overview(paperId, revisionId),
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
      api.generateOverview(
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
      client.setQueryData(["overview", paperId, revisionId], value);
    },
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ["lite-usage", projectId] });
      void client.invalidateQueries({ queryKey: ["jobs", projectId] });
    },
  });
  const data = overview.data;
  const completed =
    data?.status === "COMPLETED" && !!data.paper_card && !!data.graph;
  const resultId = data?.id ?? "";
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
    queryKey: ["overview-layout", paperId, resultId],
    queryFn: () => api.overviewLayout(paperId, resultId),
    enabled: connected && !!resultId && completed,
  });
  const { mutate: persistLayout, error: layoutError } = useMutation({
    mutationFn: (value: OverviewLayout) => {
      const write = layoutWrites.current.then(() =>
        api.saveOverviewLayout(paperId, value),
      );
      layoutWrites.current = write.catch(() => undefined);
      return write;
    },
    onSuccess: (value) =>
      client.setQueryData(
        ["overview-layout", paperId, value.overview_result_id],
        value,
      ),
  });
  const resetLayout = useMutation({
    mutationFn: (overviewResultId: string) => {
      if (layoutTimer.current !== null)
        window.clearTimeout(layoutTimer.current);
      pendingLayout.current = null;
      const write = layoutWrites.current.then(() =>
        api.resetOverviewLayout(paperId, overviewResultId),
      );
      layoutWrites.current = write.catch(() => undefined);
      return write;
    },
    onSuccess: (value) => {
      client.setQueryData(
        ["overview-layout", paperId, value.overview_result_id],
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
    [data],
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
      {data?.status === "PENDING" && (
        <p role="status">正在生成概览…本地章节和全文索引仍可继续使用。</p>
      )}
      {data?.status === "FAILED" && (
        <div role="alert" className="quality-note">
          <strong>概览生成失败</strong>
          <p>{data.error || data.error_code || "模型响应未通过校验"}</p>
        </div>
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
          <Card
            card={data.paper_card}
            cacheHit={data.cache_hit}
            usage={data.usage}
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
        </>
      )}
    </section>
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
