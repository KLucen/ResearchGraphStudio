import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { getGraphAppearance } from "./graphAppearance";
import { knowledgeApi, knowledgeErrorMessage } from "./knowledgeApi";
import "./researchKnowledgeBase.css";

export function KnowledgeLocalRecoveryDialog({
  runId,
  connected,
  onClose,
  onRecovered,
}: {
  runId: string;
  connected: boolean;
  onClose: () => void;
  onRecovered: (message: string) => void;
}) {
  const client = useQueryClient();
  const dialog = useRef<HTMLDialogElement>(null);
  const preview = useQuery({
    queryKey: ["knowledge", "local-recovery", runId],
    queryFn: () => knowledgeApi.localRecovery(runId),
    enabled: connected && !!runId,
    staleTime: 0,
  });
  const recover = useMutation({
    mutationFn: (fingerprint: string) =>
      knowledgeApi.recoverLocal(runId, fingerprint),
    onSuccess: (result) => {
      void client.invalidateQueries({ queryKey: ["knowledge", "task-runs"] });
      void client.invalidateQueries({ queryKey: ["knowledge", "runs"] });
      void client.invalidateQueries({ queryKey: ["knowledge", "papers"] });
      void client.invalidateQueries({ queryKey: ["jobs"] });
      const recovered = result.local_recovery;
      const retained = `保留 ${recovered.kept_nodes} 个知识节点和 ${recovered.kept_edges} 条关系`;
      const excludedEdges = recovered.excluded_edges.length;
      onRecovered(
        recovered.version === "knowledge-local-recovery-2"
          ? `已保存为部分知识。${retained}，隔离 ${recovered.excluded_nodes?.length ?? 0} 个知识节点和 ${excludedEdges} 条关系。模型请求为 0 次。`
          : `已保存为部分知识：${retained}，隔离 ${excludedEdges} 条关系；未调用模型。`,
      );
      onClose();
    },
  });
  useEffect(() => {
    if (dialog.current && !dialog.current.open) dialog.current.showModal();
  }, []);

  const recovery = preview.data;
  const excludedNodes = recovery?.excluded_nodes ?? [];
  return (
    <dialog
      ref={dialog}
      className="dialog knowledge-dialog"
      aria-label="本机恢复预览"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="dialog-header">
        <h2>本机恢复预览</h2>
        <button className="icon-button" aria-label="关闭" onClick={onClose}>
          <X size={20} />
        </button>
      </div>
      <div className="knowledge-recovery-dialog">
        <p className="muted">
          {recovery?.version === "knowledge-local-recovery-2"
            ? "在本机核验引文。确认后，仅保存通过校验的节点和关系为部分知识，原始响应仍保存在任务中。模型请求为 0 次。"
            : "仅在本机隔离关系类型或方向不符合规则的边，不修改原始响应，不发送模型请求。确认后将发布为部分知识。"}
        </p>
        {preview.isPending || preview.isFetching ? (
          <p role="status">正在重新校验本机响应与来源…</p>
        ) : preview.error ? (
          <p role="alert" className="error-text">
            {knowledgeErrorMessage(
              preview.error instanceof Error
                ? preview.error.message
                : String(preview.error),
            )}
          </p>
        ) : recovery?.available ? (
          <>
            <div
              className="knowledge-recovery-stats"
              aria-label="本机恢复内容计数"
            >
              <span>
                原知识节点<strong>{recovery.original_nodes}</strong>
              </span>
              <span>
                保留节点<strong>{recovery.kept_nodes}</strong>
              </span>
              <span>
                原关系<strong>{recovery.original_edges}</strong>
              </span>
              <span>
                保留关系<strong>{recovery.kept_edges}</strong>
              </span>
              <span>
                隔离关系<strong>{recovery.excluded_edges.length}</strong>
              </span>
            </div>
            {excludedNodes.length > 0 && (
              <>
                <h3>将隔离的知识节点（{excludedNodes.length}）</h3>
                <ol className="knowledge-recovery-edges">
                  {excludedNodes.map((node) => (
                    <li key={`${node.index}:${node.path}`}>
                      <strong>
                        节点 {node.index + 1} ·{" "}
                        {getGraphAppearance(node.node_type).label}
                      </strong>
                      <span>{node.reason}</span>
                    </li>
                  ))}
                </ol>
              </>
            )}
            {recovery.excluded_edges.length > 0 && (
              <>
                <h3>将隔离的关系</h3>
                <ol className="knowledge-recovery-edges">
                  {recovery.excluded_edges.map((edge) => (
                    <li key={`${edge.index}:${edge.path}`}>
                      <strong>
                        {edge.relation_type ?? "关系"} ·{" "}
                        {edge.source_type ?? "未知"} →{" "}
                        {edge.target_type ?? "未知"}
                      </strong>
                      <span>{edge.reason}</span>
                    </li>
                  ))}
                </ol>
              </>
            )}
            <p className="quality-note knowledge-partial-note">
              保留的节点和关系仍须由你结合论文判断。恢复后版本会持续标记为“部分知识”。
            </p>
            {recover.error && (
              <p role="alert" className="error-text">
                {knowledgeErrorMessage(
                  recover.error instanceof Error
                    ? recover.error.message
                    : String(recover.error),
                )}
              </p>
            )}
            <button
              className="button primary"
              disabled={
                !connected ||
                recover.isPending ||
                preview.isFetching ||
                !recovery.preview_fingerprint
              }
              onClick={() => {
                if (recovery.preview_fingerprint)
                  recover.mutate(recovery.preview_fingerprint);
              }}
            >
              {recover.isPending ? "正在保存本机恢复…" : "确认保存为部分知识"}
            </button>
          </>
        ) : (
          <div>
            <p role="alert" className="error-text">
              {recovery?.blocking_diagnostic?.summary ??
                "当前响应不满足本机恢复条件。"}
            </p>
            {recovery?.blocking_diagnostic?.action && (
              <p className="muted">{recovery.blocking_diagnostic.action}</p>
            )}
          </div>
        )}
      </div>
    </dialog>
  );
}
