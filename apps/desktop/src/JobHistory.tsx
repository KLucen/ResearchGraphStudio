import {
  useInfiniteQuery,
  useMutation,
  useQuery,
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
  section_guide: "章节导读",
  grounded_qa: "局部证据问答",
  search_keywords: "英文关键词辅助",
  pdf_translation: "文献翻译",
};
const stages: Record<string, string> = {
  starting: "准备任务",
  reading: "读取 PDF",
  parsing: "解析原文",
  checking: "检查文件",
  starting_service: "后台启动翻译服务",
  stopping_service: "关闭翻译服务",
  saving: "保存结果",
  indexing: "建立本地索引",
  diagnostics: "检查存储",
  generating: "生成论文概览",
  guide: "生成章节导读",
};

export function JobHistory({
  projectId,
  connected,
  projectNames,
  title = "文献任务",
}: {
  projectId?: string;
  connected: boolean;
  projectNames?: Record<string, string>;
  title?: string;
}) {
  const client = useQueryClient();
  const projectHistory = useInfiniteQuery({
    queryKey: ["jobs", projectId],
    queryFn: ({ pageParam }) => api.projectJobs(projectId!, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: connected && !!projectId,
    refetchInterval: 2000,
  });
  const globalHistory = useQuery({
    queryKey: ["jobs", "global"],
    queryFn: api.jobs,
    enabled: connected && !projectId,
    refetchInterval: 2000,
  });
  const action = useMutation({
    mutationFn: ({ id, kind }: { id: string; kind: "cancel" | "retry" }) =>
      api.jobAction(id, kind, crypto.randomUUID()),
    onSuccess: () => {
      void client.invalidateQueries({
        queryKey: projectId ? ["jobs", projectId] : ["jobs", "global"],
      });
      if (projectId) {
        void client.invalidateQueries({ queryKey: ["papers", projectId] });
        void client.invalidateQueries({ queryKey: ["lite-usage", projectId] });
      }
    },
  });
  const jobs = projectId
    ? (projectHistory.data?.pages.flatMap((page) => page.items) ?? [])
    : (globalHistory.data ?? []);
  const isPending = projectId
    ? projectHistory.isPending
    : globalHistory.isPending;
  const historyError = projectId ? projectHistory.error : globalHistory.error;
  const hasNextPage = projectId ? projectHistory.hasNextPage : false;
  const isFetchingNextPage = projectId
    ? projectHistory.isFetchingNextPage
    : false;
  return (
    <section className="job-history" aria-label={title}>
      <h4>{title}</h4>
      {isPending && connected && <p role="status">正在读取任务记录…</p>}
      {(historyError || action.error) && (
        <p role="alert" className="error-text">
          {(historyError || action.error)?.message}
        </p>
      )}
      {((projectId && projectHistory.isSuccess) ||
        (!projectId && globalHistory.isSuccess)) &&
        !jobs.length && (
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
                {!projectId && job.project_id
                  ? `${projectNames?.[job.project_id] ?? "研究项目"} · `
                  : ""}
                {new Date(job.created_at).toLocaleString("zh-CN")} · 第{" "}
                {job.attempt} 次执行
              </small>
              {job.status === "running" && job.stage && (
                <p role="status">
                  {job.kind === "section_guide" && job.stage === "generating"
                    ? "生成章节导读"
                    : job.kind === "grounded_qa" && job.stage === "generating"
                      ? "生成局部证据问答"
                      : job.kind === "search_keywords" &&
                          job.stage === "generating"
                        ? "生成英文关键词"
                        : stages[job.stage] || "正在处理"}
                </p>
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
              {job.kind === "section_guide" &&
                ["failed", "interrupted", "cancelled"].includes(job.status) && (
                  <p className="muted">
                    章节导读未自动重发。请回到章节目录，确认范围后重新生成。
                  </p>
                )}
              {job.kind === "grounded_qa" &&
                ["failed", "interrupted", "cancelled"].includes(job.status) && (
                  <p className="muted">
                    局部证据问答未自动重发。请回到问答区，确认范围后重新提问。
                  </p>
                )}
              {job.kind === "search_keywords" &&
                ["failed", "interrupted", "cancelled"].includes(job.status) && (
                  <p className="muted">
                    英文关键词未自动重发。请回到本地检索区，确认无命中后重新授权。
                  </p>
                )}
              {job.kind === "pdf_translation" &&
                ["failed", "interrupted", "cancelled"].includes(job.status) && (
                  <p className="muted">
                    翻译未自动重发。请回到文献翻译板块，重新预检并确认预算。
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
              ![
                "paper_overview",
                "section_guide",
                "grounded_qa",
                "search_keywords",
                "pdf_translation",
              ].includes(job.kind) &&
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
      {projectId && hasNextPage && (
        <button
          className="text-button"
          disabled={!connected || isFetchingNextPage}
          onClick={() => void projectHistory.fetchNextPage()}
        >
          {isFetchingNextPage ? "正在加载…" : "加载更早任务"}
        </button>
      )}
    </section>
  );
}
