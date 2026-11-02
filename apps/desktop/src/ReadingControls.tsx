import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, request, type KnowledgeNode, type Job } from "./api";

type Selection = {
  selection_revision: number;
  document_version_id?: string;
  density?: string;
  build_state: string;
  build?: {
    candidate_count: number;
    extraction_incomplete: boolean;
    completed_batches: number;
    total_batches: number;
    active: boolean;
  };
};
type Candidates = {
  items: {
    node: KnowledgeNode;
    graph_role: string;
    reason: string;
    source_valid: boolean;
  }[];
  next_cursor: string | null;
};

export function ReadingControls({
  paperId,
  connected,
  onSelect,
}: {
  paperId: string;
  connected: boolean;
  onSelect: (id: string) => void;
}) {
  const client = useQueryClient();
  const [density, setDensity] = useState("standard");
  const [allow, setAllow] = useState(false);
  const [search, setSearch] = useState("");
  const [cursor, setCursor] = useState("");
  const selection = useQuery({
    queryKey: ["reading-selection", paperId],
    queryFn: () =>
      request<Selection>("GET", `/api/v1/papers/${paperId}/graph-selection`),
    enabled: connected,
    refetchInterval: 3000,
  });
  const paper = useQuery({
    queryKey: ["paper", paperId],
    queryFn: () => api.paper(paperId),
    enabled: connected,
  });
  const candidates = useQuery({
    queryKey: [
      "reading-candidates",
      paperId,
      search,
      cursor,
      selection.data?.selection_revision,
    ],
    queryFn: () =>
      request<Candidates>(
        "GET",
        `/api/v1/papers/${paperId}/candidates?${new URLSearchParams({ search, cursor, limit: "40" })}`,
      ),
    enabled: connected,
    refetchInterval: cursor ? false : 3000,
  });
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["reading-selection", paperId] });
    void client.invalidateQueries({
      queryKey: ["reading-candidates", paperId],
    });
    void client.invalidateQueries({ queryKey: ["projection"] });
  };
  const rebuild = useMutation({
    mutationFn: () =>
      request<Job>(
        "POST",
        `/api/v1/papers/${paperId}/graph-selection/rebuild`,
        {
          document_version_id:
            selection.data?.document_version_id || paper.data?.revisions[0]?.id,
          density,
          expected_revision: selection.data?.selection_revision ?? 0,
          allow_network: allow,
        },
        crypto.randomUUID(),
      ),
    onSuccess: refresh,
  });
  const preference = useMutation({
    mutationFn: ({ id, action }: { id: string; action: string }) =>
      request<Selection>(
        "POST",
        `/api/v1/papers/${paperId}/graph-selection/preferences`,
        {
          candidate_id: id,
          action,
          expected_revision: selection.data?.selection_revision,
          reason: "用户显示偏好",
        },
        crypto.randomUUID(),
      ),
    onSuccess: refresh,
  });
  return (
    <details
      className="reading-controls"
      open={selection.data?.selection_revision === 0}
    >
      <summary>
        结论选择与全部候选 ·{" "}
        {selection.data?.build_state === "complete"
          ? "已发布"
          : "待构建或部分完成"}
      </summary>
      {selection.data?.build && (
        <p role="status" className="quiet-note">
          已保存 {selection.data.build.candidate_count} 条候选/历史知识。
          {selection.data.build.extraction_incomplete
            ? `全文抽取尚未完成（${selection.data.build.completed_batches}/${selection.data.build.total_batches || "未知"} 批）；可先查看候选，任务停止后可生成标注覆盖缺口的部分图谱。`
            : "候选保存与图谱发布是两个阶段，尚未发布时仍可在下方查看知识。"}
          {selection.data.build.active &&
            "当前任务仍在运行，请等待结束或取消后再整合。"}
        </p>
      )}
      <div className="import-controls">
        <label>
          图谱密度{" "}
          <select
            aria-label="图谱密度"
            value={density}
            onChange={(e) => setDensity(e.target.value)}
          >
            <option value="concise">精简</option>
            <option value="standard">标准</option>
            <option value="detailed">详细</option>
          </select>
        </label>
        <button
          className="button secondary"
          disabled={
            !connected ||
            rebuild.isPending ||
            selection.data?.build?.active ||
            selection.data?.build?.candidate_count === 0
          }
          onClick={() => rebuild.mutate()}
        >
          {selection.data?.selection_revision === 0 &&
          selection.data.build?.extraction_incomplete
            ? "基于已保存候选生成部分图谱"
            : "基于已有候选更新图谱"}
        </button>
        <label>
          <input
            type="checkbox"
            checked={allow}
            onChange={(e) => setAllow(e.target.checked)}
          />
          允许首次整合向已配置模型发送候选及必要证据
        </label>
      </div>
      <p className="quiet-note">
        已有有效选择切换密度不调用抽取模型；显示偏好不会改变原知识或来源状态。
      </p>
      <input
        aria-label="搜索全部候选"
        placeholder="搜索包含未选知识的全部候选"
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setCursor("");
        }}
      />
      {candidates.data?.items.map((item) => (
        <article className="inspector-fact" key={item.node.id}>
          <button
            className="text-button"
            onClick={() => onSelect(item.node.id)}
          >
            {item.node.text}
          </button>
          <small>
            {item.graph_role} · {item.reason}
          </small>
          {item.node.kind === "claim" &&
            !!selection.data?.selection_revision && (
              <div className="import-controls">
                {[
                  ["include_core", "在主图显示"],
                  ["exclude_core", "从主图隐藏"],
                  ["reset_automatic", "恢复自动选择"],
                ].map(([action, label]) => (
                  <button
                    className="text-button"
                    key={action}
                    disabled={
                      preference.isPending ||
                      (!item.source_valid && action === "include_core")
                    }
                    onClick={() =>
                      preference.mutate({ id: item.node.id, action })
                    }
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
        </article>
      ))}
      <button
        className="text-button"
        disabled={!cursor}
        onClick={() => setCursor("")}
      >
        返回第一页
      </button>
      <button
        className="text-button"
        disabled={!candidates.data?.next_cursor}
        onClick={() => setCursor(candidates.data!.next_cursor!)}
      >
        更多候选
      </button>
      {[selection.error, candidates.error, rebuild.error, preference.error]
        .filter(Boolean)
        .map((e, i) => (
          <p key={i} role="alert">
            {String(e)}
          </p>
        ))}
      {rebuild.isSuccess && (
        <p role="status">已更新或排队，可在任务历史查看进度。</p>
      )}
    </details>
  );
}
