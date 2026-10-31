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
};
const kinds: Record<string, string> = {
  pdf_import: "PDF 导入",
  source_check: "来源检查",
  source_relocate: "重新定位",
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
                  重试
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
