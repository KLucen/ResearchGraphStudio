import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Source } from "./api";

const fileStates = {
  available: "内容一致",
  changed: "内容已变化",
  missing: "文件丢失",
  unreadable: "无法读取",
  too_large: "超过 50 MiB 检查上限",
  unstable: "检查时文件发生变化，请重试",
};

export function SourceFiles({
  sources,
  paperId,
  selectedRevisionId,
  connected,
}: {
  sources: Source[];
  paperId: string;
  selectedRevisionId: string;
  connected: boolean;
}) {
  const client = useQueryClient();
  const action = useMutation({
    mutationFn: ({
      source,
      kind,
    }: {
      source: Source;
      kind: "check" | "relocate";
    }) =>
      kind === "check" ? api.checkSource(source) : api.relocateSource(source),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      void client.invalidateQueries({ queryKey: ["paper", paperId] });
    },
  });
  return (
    <section className="source-files" aria-label="来源文件">
      <h4>来源文件</h4>
      <p className="muted">
        检查只反映当次读取结果。重新定位需选择内容相同的
        PDF，已有修订与原文会保留。
      </p>
      {action.isError && (
        <p role="alert" className="error-text">
          {action.error instanceof Error
            ? action.error.message
            : String(action.error)}
        </p>
      )}
      {action.isSuccess && action.data && (
        <p role="status">任务已提交，进展见上方文献任务。</p>
      )}
      {sources.map((source) => (
        <article className="source-file" key={source.id}>
          <p className="source-path">
            {source.mode === "managed" ? "含托管副本" : "文件引用"} ·{" "}
            {source.path}
          </p>
          {source.revision_id !== selectedRevisionId && (
            <p className="quality-note">
              此来源当前指向其他修订；上方选中的历史原文仍保留。
            </p>
          )}
          {source.last_check ? (
            <>
              <p>
                原文件：{fileStates[source.last_check.original.state]}
                {source.last_check.managed && (
                  <>
                    {" "}
                    · 托管副本：{fileStates[source.last_check.managed.state]}
                  </>
                )}
              </p>
              <small>
                检查时间：
                {new Date(source.last_check.checked_at).toLocaleString("zh-CN")}
              </small>
            </>
          ) : (
            <p className="muted">尚未检查当前文件</p>
          )}
          <div className="source-actions">
            <button
              className="button secondary"
              disabled={!connected || action.isPending}
              onClick={() => action.mutate({ source, kind: "check" })}
            >
              检查文件
            </button>
            <button
              className="text-button"
              disabled={!connected || action.isPending}
              onClick={() => action.mutate({ source, kind: "relocate" })}
            >
              重新定位…
            </button>
          </div>
        </article>
      ))}
    </section>
  );
}
