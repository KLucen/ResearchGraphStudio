import { useState } from "react";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api, type Job } from "./api";
import { jobKindLabel, jobStageLabel } from "./jobProgress";
import { DocumentRequestStatus } from "./DocumentRequestStatus";
import { KnowledgeTaskDiagnostic } from "./KnowledgeTaskDiagnostic";
import { knowledgeApi } from "./knowledgeApi";
import { KnowledgeLocalRecoveryDialog } from "./KnowledgeLocalRecoveryDialog";
import { archiveApi } from "./archiveApi";
import { useContextMenu } from "./ContextMenu";
import "./jobHistory.css";

const statuses: Record<Job["status"], string> = {
  queued: "等待执行",
  running: "正在处理",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
};
const localJobKinds = new Set([
  "diagnostics",
  "pdf_import",
  "zotero_import",
  "source_check",
  "source_relocate",
  "formula_recognize",
]);
function isDocumentModelJob(job: Job): boolean {
  return (
    job.kind === "llm_document_parse" ||
    !!job.result?.document_batches ||
    !!job.result?.document_request
  );
}
function boundaryCompatibilityRetryAvailable(job: Job): boolean {
  const batches = job.result?.document_batches;
  return (
    !!batches &&
    typeof batches === "object" &&
    !Array.isArray(batches) &&
    (batches as Record<string, unknown>).compatibility_retry_available === true
  );
}
function publicationRetryAvailable(job: Job): boolean {
  const batches = job.result?.document_batches;
  return (
    !!batches &&
    typeof batches === "object" &&
    !Array.isArray(batches) &&
    (batches as Record<string, unknown>).publication_retry_available === true
  );
}

function taskControl(
  job: Job,
): { kind: "cancel" | "retry"; label: string } | null {
  if (["queued", "running"].includes(job.status)) {
    return job.kind === "pdf_translation"
      ? null
      : { kind: "cancel", label: "取消" };
  }
  if (
    !["failed", "interrupted", "cancelled"].includes(job.status) ||
    [
      "paper_overview",
      "llm_document_postprocess",
      "section_guide",
      "section_close_reading",
      "paper_reading_notes",
      "understanding_check",
      "grounded_qa",
      "search_keywords",
      "pdf_translation",
      "knowledge_extract",
      "knowledge_connect",
    ].includes(job.kind)
  )
    return null;
  if (publicationRetryAvailable(job))
    return { kind: "retry", label: "仅重新发布章节（不重发批次）" };
  if (boundaryCompatibilityRetryAvailable(job))
    return { kind: "retry", label: "确认继续边界复核（可能收费）" };
  if (job.attempt >= 3) return null;
  return {
    kind: "retry",
    label: isDocumentModelJob(job)
      ? "确认继续未完成解析（可能收费）"
      : "重试本地处理",
  };
}
function databaseFailureLabel(job: Job): string | null {
  const value = job.result?.failure_diagnostics;
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const diagnostics = value as Record<string, unknown>;
  const dialect = diagnostics.database_dialect;
  const category = diagnostics.constraint_category;
  const labels: Record<string, string> = {
    check: "检查约束",
    foreign_key: "外键约束",
    not_null: "非空约束",
    primary_key: "主键约束",
    unique: "唯一约束",
    constraint: "完整性约束",
  };
  if (
    typeof dialect !== "string" ||
    !["sqlite", "postgresql", "mysql", "mssql"].includes(dialect) ||
    typeof category !== "string" ||
    !Object.hasOwn(labels, category)
  ) {
    return null;
  }
  const name = diagnostics.sqlite_errorname;
  const code = diagnostics.sqlite_errorcode;
  const detail =
    typeof name === "string" && /^SQLITE_CONSTRAINT(?:_[A-Z]+)?$/.test(name)
      ? ` · ${name}${typeof code === "number" && Number.isInteger(code) ? ` (${code})` : ""}`
      : "";
  return `${dialect.toUpperCase()} · ${labels[category]}${detail}`;
}
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
  const [recoveryRunId, setRecoveryRunId] = useState("");
  const [recoveryNotice, setRecoveryNotice] = useState("");
  const { contextMenuProps, contextMenu } = useContextMenu();
  const archiveTask = useMutation({
    mutationFn: (id: string) => archiveApi.stage("job", id),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["jobs"] }),
        client.invalidateQueries({ queryKey: ["health"] }),
        client.invalidateQueries({ queryKey: ["archive"] }),
        client.invalidateQueries({ queryKey: ["knowledge", "runs"] }),
      ]);
    },
  });
  const history = useInfiniteQuery({
    queryKey: ["jobs", projectId ?? "history"],
    queryFn: ({ pageParam }) =>
      projectId
        ? api.projectJobs(projectId, pageParam)
        : api.jobsPage(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: connected,
    refetchInterval: 2000,
  });
  const action = useMutation({
    mutationFn: ({ id, kind }: { id: string; kind: "cancel" | "retry" }) =>
      api.jobAction(id, kind, crypto.randomUUID()),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      void client.invalidateQueries({ queryKey: ["health"] });
      if (projectId) {
        void client.invalidateQueries({ queryKey: ["papers", projectId] });
        void client.invalidateQueries({
          queryKey: ["sidebar-papers", projectId],
        });
        void client.invalidateQueries({ queryKey: ["lite-usage", projectId] });
      }
    },
  });
  const jobs = history.data?.pages.flatMap((page) => page.items) ?? [];
  const failedKnowledgeJobs = jobs
    .filter(
      (job) => job.kind === "knowledge_extract" && job.status === "failed",
    )
    .map((job) => job.id)
    .sort();
  const knowledgeRuns = useQuery({
    queryKey: ["knowledge", "task-runs", failedKnowledgeJobs],
    queryFn: async () => {
      const pages = await Promise.all(
        Array.from(
          { length: Math.ceil(failedKnowledgeJobs.length / 25) },
          (_, page) =>
            knowledgeApi.runs(
              25,
              0,
              failedKnowledgeJobs.slice(page * 25, (page + 1) * 25),
            ),
        ),
      );
      return pages.flatMap((page) => page.items);
    },
    enabled: connected && failedKnowledgeJobs.length > 0,
    staleTime: 30000,
  });
  const knowledgeRunsByJob = new Map(
    (knowledgeRuns.data ?? []).flatMap((run) =>
      run.job_id ? [[run.job_id, run] as const] : [],
    ),
  );
  const historyError = history.error;
  return (
    <section className="job-history" aria-label={title}>
      <h4>{title}</h4>
      {history.isPending && connected && <p role="status">正在读取任务记录…</p>}
      {(historyError || action.error || archiveTask.error) && (
        <p role="alert" className="error-text">
          {(historyError || action.error || archiveTask.error)?.message}
        </p>
      )}
      {historyError && (
        <button
          type="button"
          className="text-button"
          onClick={() => void history.refetch()}
        >
          重新读取任务记录
        </button>
      )}
      {knowledgeRuns.error && (
        <p role="alert" className="error-text">
          无法读取知识恢复信息。{" "}
          <button
            type="button"
            className="text-button"
            onClick={() => void knowledgeRuns.refetch()}
          >
            重新读取
          </button>
        </p>
      )}
      {archiveTask.isSuccess && <p role="status">任务已移至归档管理。</p>}
      {recoveryNotice && <p role="status">{recoveryNotice}</p>}
      {history.isSuccess && !jobs.length && (
        <p className="muted">尚无任务。导入论文后可在这里查看处理进度。</p>
      )}
      <div className="job-list">
        {jobs.map((job) => {
          const knowledgeRun = knowledgeRunsByJob.get(job.id);
          const recovery = knowledgeRun?.local_recovery;
          const control = taskControl(job);
          const knowledgeTask = [
            "knowledge_extract",
            "knowledge_connect",
          ].includes(job.kind);
          const databaseFailure = databaseFailureLabel(job);
          const errorCode =
            job.error && /^[A-Z][A-Z0-9_]{0,95}$/.test(job.error)
              ? job.error
              : null;
          const canArchive = !["queued", "running"].includes(job.status);
          const busy = !connected || action.isPending || archiveTask.isPending;
          const archiveJob = () => archiveTask.mutate(job.id);
          const menuActions = [
            ...(control
              ? [
                  {
                    label: control.label,
                    action: () =>
                      action.mutate({ id: job.id, kind: control.kind }),
                    disabled: busy,
                  },
                ]
              : []),
            ...(canArchive
              ? [{ label: "归档任务", action: archiveJob, disabled: busy }]
              : []),
          ];
          return (
            <article
              className="job"
              data-status={job.status}
              id={`job-${job.id}`}
              key={job.id}
              tabIndex={menuActions.length ? 0 : undefined}
              {...contextMenuProps(`${jobKindLabel(job)}操作`, menuActions)}
            >
              <div>
                <strong className="job-heading">
                  {jobKindLabel(job)} · {statuses[job.status]}
                </strong>
                <small>
                  {!projectId && job.project_id
                    ? `${projectNames?.[job.project_id] ?? "研究项目"} · `
                    : ""}
                  <time dateTime={job.created_at}>
                    {new Date(job.created_at).toLocaleString("zh-CN")}
                  </time>{" "}
                  · 第 {job.attempt} 次执行
                </small>
                {job.kind !== "pdf_translation" &&
                  job.status === "running" &&
                  job.stage && <p role="status">{jobStageLabel(job)}</p>}
                {job.status === "running" &&
                  control?.kind === "cancel" &&
                  !localJobKinds.has(job.kind) && (
                    <p className="muted">
                      取消会结束本机等待。已经发送到模型的请求仍可能计费。
                    </p>
                  )}
                {typeof job.result?.title === "string" && (
                  <p>{job.result.title}</p>
                )}
                {!knowledgeTask && job.error && !errorCode && (
                  <p className="error-text">{job.error}</p>
                )}
                <KnowledgeTaskDiagnostic job={job}>
                  {job.kind === "knowledge_extract" &&
                    knowledgeRun &&
                    recovery?.available && (
                      <div className="job-recovery">
                        <button
                          type="button"
                          className="button secondary compact"
                          disabled={!connected}
                          onClick={() => setRecoveryRunId(knowledgeRun.id)}
                        >
                          预览本机恢复
                        </button>
                        <span>
                          保留 {recovery.kept_nodes} 个知识节点和{" "}
                          {recovery.kept_edges} 条关系 · 0 次模型请求
                        </span>
                      </div>
                    )}
                </KnowledgeTaskDiagnostic>
                {job.kind === "knowledge_extract" &&
                  recovery?.published_version_id && (
                    <p className="knowledge-partial-badge">
                      已本机恢复为部分知识
                    </p>
                  )}
                {knowledgeTask &&
                  !job.result?.knowledge_diagnostic &&
                  ["failed", "interrupted", "cancelled"].includes(
                    job.status,
                  ) && (
                    <p className="muted">
                      {job.error === "KNOWLEDGE_INPUT_BUDGET_EXCEEDED"
                        ? "完整输入超过知识库单次预算，本次检查未发送模型请求。请在研究内容知识库的自动分析设置中调高输入预算或选择无上限，保存后显式继续失败任务。"
                        : "错误详情在本条任务记录中显示。需要继续时，请到研究内容知识库显式继续任务；新的模型请求可能收费，系统不会自动重发。"}
                    </p>
                  )}
                {isDocumentModelJob(job) &&
                  ["failed", "interrupted", "cancelled"].includes(
                    job.status,
                  ) && (
                    <p className="muted">
                      {!publicationRetryAvailable(job)
                        ? "分批任务只继续未成功批次，保留已成功检查点。若请求已发送但结果不确定，点击继续即确认再次请求，可能再次收费；系统不会自动重发。修改配置后请到论文页使用“使用模型重新解析”。"
                        : "所有正文和边界检查点已校验，本次只重新发布章节；模型批次不会重发。"}
                    </p>
                  )}
                <DocumentRequestStatus job={job} foldDetails>
                  {(databaseFailure || (errorCode && !knowledgeTask)) && (
                    <>
                      {errorCode && !knowledgeTask && (
                        <p className="muted">错误码：{errorCode}</p>
                      )}
                      {databaseFailure && (
                        <p className="muted">
                          安全数据库诊断：{databaseFailure}
                        </p>
                      )}
                    </>
                  )}
                </DocumentRequestStatus>
                {job.reading_task === "paper_card_set" &&
                  job.status === "failed" && (
                    <p className="muted">
                      请到这篇论文的概览查看可用的本机恢复或重新生成操作。
                    </p>
                  )}
                {job.kind === "llm_document_postprocess" &&
                  (job.reading_task === "paper_reading" ||
                    job.reading_task === "translation") &&
                  ["failed", "interrupted", "cancelled"].includes(
                    job.status,
                  ) && (
                    <p className="muted">
                      请到这篇论文的精读页选择恢复或重新生成。
                    </p>
                  )}
                {job.kind === "paper_overview" &&
                  job.reading_task !== "paper_card_set" &&
                  job.status === "failed" && (
                    <p className="muted">
                      概览未自动重发。请到论文概览查看原因，再决定是否重新生成。
                    </p>
                  )}
                {job.kind === "section_guide" &&
                  ["failed", "interrupted", "cancelled"].includes(
                    job.status,
                  ) && (
                    <p className="muted">
                      章节导读未自动重发。请回到章节目录，确认范围后重新生成。
                    </p>
                  )}
                {job.kind === "paper_reading_notes" &&
                  ["failed", "interrupted", "cancelled"].includes(
                    job.status,
                  ) && (
                    <p className="muted">
                      全文精读未自动重发。请回到全文精读查看已保留的结果和原因，再决定是否重新生成。
                    </p>
                  )}
                {job.kind === "grounded_qa" &&
                  ["failed", "interrupted", "cancelled"].includes(
                    job.status,
                  ) && (
                    <p className="muted">
                      局部证据问答未自动重发。请回到问答区，确认范围后重新提问。
                    </p>
                  )}
                {job.kind === "search_keywords" &&
                  ["failed", "interrupted", "cancelled"].includes(
                    job.status,
                  ) && (
                    <p className="muted">
                      英文关键词未自动重发。请回到本地检索区，确认无命中后重新授权。
                    </p>
                  )}
                {job.kind === "pdf_translation" && (
                  <p className="muted">
                    文献翻译功能已移除，此记录仅保留为历史，不会重新执行。
                  </p>
                )}
                {["section_close_reading", "understanding_check"].includes(
                  job.kind,
                ) &&
                  ["failed", "interrupted", "cancelled"].includes(
                    job.status,
                  ) && (
                    <p className="muted">
                      {job.kind === "section_close_reading"
                        ? "双栏精读未自动重发。请回到章节精读，查看已保留段落并显式重试缺失范围。"
                        : "理解检查未自动重发。请回到章节精读，确认原文范围后重新提交复述。"}
                    </p>
                  )}
              </div>
              {(control || canArchive) && (
                <div className="job-actions">
                  {control && (
                    <button
                      type="button"
                      className="text-button"
                      disabled={busy}
                      onClick={() =>
                        action.mutate({ id: job.id, kind: control.kind })
                      }
                    >
                      {control.label}
                    </button>
                  )}
                  {canArchive && (
                    <button
                      type="button"
                      className="text-button"
                      disabled={busy}
                      onClick={archiveJob}
                    >
                      归档任务
                    </button>
                  )}
                </div>
              )}
              {publicationRetryAvailable(job) && (
                <p className="muted">
                  本次不重发已校验批次；原计划选中的概览或精读任务仍会继续，可能产生模型请求。
                </p>
              )}
            </article>
          );
        })}
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
      {recoveryRunId && (
        <KnowledgeLocalRecoveryDialog
          runId={recoveryRunId}
          connected={connected}
          onClose={() => setRecoveryRunId("")}
          onRecovered={setRecoveryNotice}
        />
      )}
      {contextMenu}
    </section>
  );
}
