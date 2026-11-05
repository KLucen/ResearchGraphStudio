import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Background,
  Controls,
  Position,
  ReactFlow,
  type Node,
} from "@xyflow/react";
import { queryApi } from "./queryApi";
import "@xyflow/react/dist/style.css";

export function QueryDerivedGraph({
  projectId,
  connected,
  includePersonal,
  onGraphNode,
  onSaved,
  allowedSavedIds,
}: {
  projectId: string;
  connected: boolean;
  includePersonal: boolean;
  onGraphNode: (id: string) => void;
  onSaved: (id: string) => void;
  allowedSavedIds?: string[];
}) {
  const [sourceId, setSourceId] = useState("");
  const graph = useQuery({
    queryKey: ["query-derived", projectId, includePersonal],
    queryFn: () => queryApi.derived(projectId, includePersonal),
    enabled: connected,
  });
  const original = graph.error ? undefined : graph.data;
  const allowed = allowedSavedIds ? new Set(allowedSavedIds) : undefined;
  const edges = original?.edges.filter(
    (edge) => !allowed || allowed.has(edge.source),
  );
  const related = new Set(edges?.flatMap((edge) => [edge.source, edge.target]));
  const data = original && {
    nodes: original.nodes.filter(
      (node) =>
        !allowed ||
        (node.saved_id ? allowed.has(node.saved_id) : related.has(node.id)),
    ),
    edges: edges ?? [],
  };
  const selectedSource = data?.nodes.find((node) => node.id === sourceId);
  const relatedSaved = data?.nodes.find(
    (node) =>
      node.saved_id &&
      data.edges.some(
        (edge) =>
          (edge.source === node.id && edge.target === sourceId) ||
          (edge.target === node.id && edge.source === sourceId),
      ),
  );
  const nodes: Node[] = (data?.nodes ?? []).map((node, index) => ({
    id: node.id,
    sourcePosition: Position.Left,
    targetPosition: Position.Right,
    position: {
      x: node.saved_id ? 380 : 30,
      y: index * 110,
    },
    data: {
      label: (
        <span title={node.label}>
          {node.label.length > 100
            ? node.label.slice(0, 100) + "…"
            : node.label}
        </span>
      ),
    },
    style: {
      background: node.saved_id ? "#eee9f4" : "#e5eee7",
      borderColor: node.saved_id ? "#827093" : "#637d69",
      color: "#27372e",
      borderRadius: 10,
      fontSize: 12,
      width: 230,
    },
  }));
  return (
    <section className="query-derived" aria-label="阅读综合衍生图层">
      <h4>来源与已保存阅读知识</h4>
      <p className="quiet-note">
        绿色：来源知识 ·
        紫色：阅读综合。连线表示引用依赖，不是新的科学支持关系。
      </p>
      {graph.error && (
        <p role="alert">
          {graph.error instanceof Error
            ? graph.error.message
            : "无法读取衍生图层"}
        </p>
      )}
      {data?.nodes.length ? (
        <div className="query-derived-canvas">
          <ReactFlow
            nodes={nodes}
            edges={data.edges.map((edge) => ({
              ...edge,
              label: "引用来源",
              style: {
                stroke: "#89958b",
                strokeOpacity: 0.6,
                strokeWidth: 1.2,
              },
              labelStyle: { fill: "#6c776f", fontSize: 10 },
            }))}
            fitView
            minZoom={0.2}
            maxZoom={2}
            onNodeClick={(_, node) => {
              const item = data.nodes.find((value) => value.id === node.id);
              if (item?.saved_id) onSaved(item.saved_id);
              else if (item?.source_id) {
                const kind = item.kind.toLowerCase();
                if (
                  [
                    "paper",
                    "claim",
                    "method",
                    "finding",
                    "condition",
                    "experiment",
                    "metric",
                    "concept",
                    "research_question",
                    "researchquestion",
                    "argument",
                    "limitation",
                  ].includes(kind)
                ) {
                  setSourceId("");
                  onGraphNode(item.source_id);
                } else setSourceId(item.id);
              }
            }}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#c4cdc3" gap={22} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
      ) : graph.isSuccess ? (
        <p className="quiet-note">尚无可显示的来源引用。</p>
      ) : (
        <p className="quiet-note">正在读取引用…</p>
      )}
      {selectedSource && (
        <aside className="query-warning" aria-label="衍生引用来源">
          <strong>
            {selectedSource.kind === "note" ? "个人笔记来源" : "原文证据来源"}
          </strong>
          <p>{selectedSource.label}</p>
          <p className="quiet-note">
            此项是来源片段。可从关联阅读知识进入原问答核对完整引用及定位信息。
          </p>
          {relatedSaved?.saved_id && (
            <button
              type="button"
              className="text-button"
              onClick={() => onSaved(relatedSaved.saved_id!)}
            >
              查看关联阅读知识
            </button>
          )}
        </aside>
      )}
    </section>
  );
}
