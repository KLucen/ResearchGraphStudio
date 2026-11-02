import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { api, type Job } from "./api";

const statuses: Record<Job["status"], string> = {
  queued: "等待处理",
  running: "处理中",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
};
const stages: Record<NonNullable<Job["stage"]>, string> = {
  starting: "正在启动",
  reading: "读取文件",
  parsing: "解析原文",
  checking: "核对文件内容",
  saving: "保存结果",
  diagnostics: "检查数据库",
  outlining: "识别论文结构",
  extracting: "抽取候选知识",
  indexing: "建立证据索引",
  integrating: "整合结论与支撑",
  selecting: "选择核心结论",
  publishing: "发布分层图谱",
  resolving: "分析实体对齐候选",
  comparing: "比较实验条件",
  reasoning: "推理候选关系",
};
const kinds: Record<string, string> = {
  translation_repair: "显示补译",
  pdf_import: "PDF 导入",
  source_check: "来源检查",
  source_relocate: "重新定位",
  knowledge_extract: "知识抽取",
  knowledge_reason: "知识推理",
  zotero_import: "Zotero 导入",
};
const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

export function JobHistory({
  projectId,
  connected,
}: {
  projectId: string;
  connected: boolean;
}) {
  const client = useQueryClient();
  const history = useInfiniteQuery({
    queryKey: ["jobs", projectId],
    queryFn: ({ pageParam }) => api.projectJobs(projectId, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: connected,
    refetchInterval: 1500,
  });
  const action = useMutation({
    mutationFn: ({ id, kind }: { id: string; kind: "cancel" | "retry" }) =>
      api.jobAction(id, kind, crypto.randomUUID()),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["jobs", projectId] });
    },
  });
  const jobs = history.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <section className="task-history" aria-label="文献任务历史">
      <h3>任务记录 · 已加载 {jobs.length} 项</h3>
      {!connected && (
        <p className="muted">引擎未连接，以下为上次读取的任务记录。</p>
      )}
      {(history.error || action.error) && (
        <p role="alert" className="error-text">
          {errorText(history.error || action.error)}
        </p>
      )}
      {!jobs.length && (
        <p className="muted">
          {history.isPending && connected ? "正在加载任务…" : "暂无文献任务。"}
        </p>
      )}
      {jobs.length > 0 && (
        <div
          className="job-list task-history-scroll"
          role="region"
          aria-label="任务列表"
          tabIndex={0}
        >
          {jobs.map((job) => (
            <div className="job" key={job.id}>
              <div>
                <strong>
                  {kinds[job.kind] ?? job.kind} · {statuses[job.status]}
                </strong>
                <small>
                  {new Date(job.created_at).toLocaleString("zh-CN")} · 第{" "}
                  {job.attempt} 次执行
                </small>
                {job.status === "running" && job.stage && (
                  <p className="task-stage">{stages[job.stage]}…</p>
                )}
                {Boolean(job.result?.total_batches) && (
                  <p className="task-stage">
                    已保存 {String(job.result?.completed_batches ?? 0)} /{" "}
                    {String(job.result?.total_batches)} 个抽取批次
                  </p>
                )}
                {Array.isArray(job.result?.batches) && (
                  <details>
                    <summary>批次详情（含拆分恢复）</summary>
                    <div className="batch-statuses" aria-label="抽取批次状态">
                      {(
                        job.result?.batches as Array<{
                          index: number;
                          status: string;
                          error?: string;
                          error_code?: string;
                          retryable?: boolean;
                          split_reason?: string;
                        }>
                      ).map((batch) => (
                        <span
                          className={`batch-status ${batch.status}`}
                          key={batch.index}
                          title={[
                            batch.error_code,
                            batch.error,
                            batch.split_reason
                              ? `拆分原因：${batch.split_reason}`
                              : "",
                            batch.retryable ? "可重试" : "",
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        >
                          {batch.index + 1}:
                          {batch.status === "succeeded"
                            ? "完成"
                            : batch.status === "failed"
                              ? "失败"
                              : batch.status === "running"
                                ? "处理中"
                                : "待处理"}
                          {batch.split_reason === "timeout"
                            ? "（超时后缩小）"
                            : ""}
                        </span>
                      ))}
                    </div>
                  </details>
                )}
                {typeof job.result?.integrated_windows === "number" && (
                  <small>
                    整合 {String(job.result.integrated_windows)} /{" "}
                    {String(job.result.integration_windows)} 个窗口
                  </small>
                )}
                {typeof job.result?.published_units === "number" && (
                  <p className="task-stage">
                    已发布 {String(job.result.published_units)} 个结论单元 ·{" "}
                    {job.result.build_state === "complete"
                      ? "构建完成"
                      : "部分构建，仍有覆盖缺口"}
                  </p>
                )}
                {Array.isArray(job.result?.coverage_gaps) &&
                  job.result.coverage_gaps.length > 0 && (
                    <details>
                      <summary>覆盖范围与限制</summary>
                      {(job.result.coverage_gaps as string[]).map((g, i) => (
                        <p key={i}>{g}</p>
                      ))}
                    </details>
                  )}
                {typeof job.result?.model_calls === "number" && (
                  <small>
                    模型调用 {String(job.result.model_calls)} 次 · Token{" "}
                    {String(
                      (job.result.usage as Record<string, number> | undefined)
                        ?.total_tokens ?? "未提供",
                    )}
                    （含供应商返回的失败请求用量） · 费用{" "}
                    {job.result.cost == null
                      ? "供应商未提供"
                      : String(job.result.cost)}
                  </small>
                )}
                {job.error && <p className="error-text">{job.error}</p>}
              </div>
              {["queued", "running"].includes(job.status) ? (
                <button
                  className="text-button"
                  disabled={!connected || action.isPending}
                  onClick={() => action.mutate({ id: job.id, kind: "cancel" })}
                >
                  取消
                </button>
              ) : ["failed", "interrupted", "cancelled"].includes(job.status) &&
                job.attempt < 3 ? (
                <button
                  className="text-button"
                  disabled={!connected || action.isPending}
                  onClick={() => action.mutate({ id: job.id, kind: "retry" })}
                >
                  {job.kind === "knowledge_extract" ? "继续未完成批次" : "重试"}
                </button>
              ) : null}
            </div>
          ))}
        </div>
      )}
      {history.hasNextPage && (
        <button
          className="text-button"
          disabled={!connected || history.isFetching}
          onClick={() => void history.fetchNextPage()}
        >
          {history.isFetchingNextPage ? "正在加载…" : "加载更早任务"}
        </button>
      )}
    </section>
  );
}
