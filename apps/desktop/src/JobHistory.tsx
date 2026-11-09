import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { api, type Job } from "./api";

const statuses: Record<Job["status"], string> = {
  queued: "等待执行",
  running: "正在处理",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
};
const kinds: Record<string, string> = {
  pdf_import: "PDF 导入",
  zotero_import: "Zotero 导入",
  source_check: "检查来源文件",
  source_relocate: "重新定位文件",
  diagnostics: "存储诊断",
  paper_overview: "论文概览",
};
const stages: Record<string, string> = {
  starting: "准备任务",
  reading: "读取 PDF",
  parsing: "解析原文",
  checking: "检查文件",
  saving: "保存结果",
  indexing: "建立本地索引",
  diagnostics: "检查存储",
  generating: "生成论文概览",
};

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
    refetchInterval: 2000,
  });
  const action = useMutation({
    mutationFn: ({ id, kind }: { id: string; kind: "cancel" | "retry" }) =>
      api.jobAction(id, kind, crypto.randomUUID()),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["jobs", projectId] });
      void client.invalidateQueries({ queryKey: ["papers", projectId] });
      void client.invalidateQueries({ queryKey: ["lite-usage", projectId] });
    },
  });
  const jobs = history.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <section className="job-history" aria-label="文献任务">
      <h4>文献任务</h4>
      {history.isPending && connected && <p role="status">正在读取任务记录…</p>}
      {(history.error || action.error) && (
        <p role="alert" className="error-text">
          {(history.error || action.error)?.message}
        </p>
      )}
      {history.isSuccess && !jobs.length && (
        <p className="muted">尚无任务。导入论文后可在这里查看处理进度。</p>
      )}
      <div className="job-list">
        {jobs.map((job) => (
          <article className="job" id={`job-${job.id}`} key={job.id}>
            <div>
              <strong>
                {kinds[job.kind] || "本地任务"} · {statuses[job.status]}
              </strong>
              <small>
                {new Date(job.created_at).toLocaleString("zh-CN")} · 第{" "}
                {job.attempt} 次执行
              </small>
              {job.status === "running" && job.stage && (
                <p role="status">{stages[job.stage] || "正在处理"}</p>
              )}
              {typeof job.result?.title === "string" && (
                <p>{job.result.title}</p>
              )}
              {job.error && <p className="error-text">{job.error}</p>}
              {job.kind === "paper_overview" && job.status === "failed" && (
                <p className="muted">
                  概览未自动重发。请到论文概览查看原因，再决定是否重新生成。
                </p>
              )}
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
              job.kind !== "paper_overview" &&
              job.attempt < 3 ? (
              <button
                className="text-button"
                disabled={!connected || action.isPending}
                onClick={() => action.mutate({ id: job.id, kind: "retry" })}
              >
                重试本地处理
              </button>
            ) : null}
          </article>
        ))}
      </div>
      {history.hasNextPage && (
        <button
          className="text-button"
          disabled={!connected || history.isFetchingNextPage}
          onClick={() => void history.fetchNextPage()}
        >
          {history.isFetchingNextPage ? "正在加载…" : "加载更早任务"}
        </button>
      )}
    </section>
  );
}
