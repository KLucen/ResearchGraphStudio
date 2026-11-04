import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";
import { api, type Job, type JobList } from "./api";

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
  selecting: "排序核心贡献",
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
const statusLabel = (job: Job) =>
  job.status === "succeeded" && job.result?.ranking_status === "pending"
    ? "核心排序待完成"
    : statuses[job.status];

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
    onMutate: () => client.cancelQueries({ queryKey: ["jobs", projectId] }),
    onSuccess: async (updated) => {
      await client.cancelQueries({
        queryKey: ["job", updated.id],
        exact: true,
      });
      client.setQueryData(["job", updated.id], updated);
      client.setQueryData<InfiniteData<JobList>>(
        ["jobs", projectId],
        (current) => {
          if (!current) return current;
          return {
            ...current,
            pages: current.pages.map((page) => ({
              ...page,
              items: page.items.map((job) =>
                job.id === updated.id ? updated : job,
              ),
            })),
          };
        },
      );
      void client.invalidateQueries({ queryKey: ["jobs", projectId] });
    },
  });
  const loadedJobs = history.data?.pages.flatMap((page) => page.items) ?? [];
  const returnedJob = action.data;
  const offpage =
    returnedJob?.project_id === projectId &&
    !loadedJobs.some((job) => job.id === returnedJob.id);
  const continuation = useQuery({
    queryKey: ["job", returnedJob?.id],
    queryFn: () => api.job(returnedJob!.id),
    initialData: returnedJob,
    enabled:
      connected &&
      offpage &&
      ["queued", "running"].includes(returnedJob?.status ?? ""),
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.status ?? "")
        ? 1500
        : false,
  });
  const actionResult =
    loadedJobs.find((job) => job.id === returnedJob?.id) ??
    continuation.data ??
    returnedJob;
  // A deterministic continuation can be older than the loaded pages. Keep the
  // returned result visible without changing the server's pagination cursors.
  const jobs =
    offpage && actionResult ? [actionResult, ...loadedJobs] : loadedJobs;
  const continued = new Map(
    jobs.flatMap((job) =>
      typeof job.result?.resumed_from === "string"
        ? [[job.result.resumed_from, job] as const]
        : [],
    ),
  );
  return (
    <section className="task-history" aria-label="文献任务历史">
      <h3>任务记录 · 已加载 {jobs.length} 项</h3>
      {!connected && (
        <p className="muted">引擎未连接，以下为上次读取的任务记录。</p>
      )}
      {(history.error || action.error) && (
        <p role="alert" className="error-text">
          {errorText(action.error || history.error)}
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
            <div
              className="job"
              key={job.id}
              id={`job-${job.id}`}
              tabIndex={-1}
            >
              <div>
                <strong>
                  {kinds[job.kind] ?? job.kind} · {statusLabel(job)}
                </strong>
                <small>
                  {new Date(job.created_at).toLocaleString("zh-CN")} · 第{" "}
                  {job.attempt} 次执行
                </small>
                {continued.has(job.id) && (
                  <p className="muted">
                    历史任务，已创建续接任务（
                    {statusLabel(continued.get(job.id)!)}
                    ）；以下为当时的执行记录。
                  </p>
                )}
                {job.result?.schema_upgrade === true && (
                  <p className="task-stage">
                    已切换新版抽取；复用符合新版 Schema 的已保存批次。
                  </p>
                )}
                {job.status === "running" && job.stage && (
                  <p className="task-stage">{stages[job.stage]}…</p>
                )}
                {job.status === "running" && (
                  <ModelActivity value={job.result?.model_activity} />
                )}
                <RankingProgress
                  result={job.result}
                  running={job.status === "running"}
                />
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
                            ? "已保存"
                            : batch.status === "failed"
                              ? "失败"
                              : batch.status === "running"
                                ? "处理中"
                                : "待处理"}
                          {batch.split_reason === "timeout"
                            ? "（超时拆分后）"
                            : ""}
                        </span>
                      ))}
                    </div>
                  </details>
                )}
                {typeof job.result?.integrated_windows === "number" && (
                  <small>
                    整合 {String(job.result.integrated_windows)} /{" "}
                    {typeof job.result.integration_windows === "number"
                      ? String(job.result.integration_windows)
                      : "未知"}{" "}
                    个窗口
                  </small>
                )}
                {typeof job.result?.selected_windows === "number" && (
                  <small>
                    核心排序 {String(job.result.selected_windows)} /{" "}
                    {typeof job.result.selection_windows === "number"
                      ? String(job.result.selection_windows)
                      : "未知"}{" "}
                    个窗口
                  </small>
                )}
                {typeof job.result?.published_units === "number" && (
                  <p className="task-stage">
                    {job.result.ranking_status === "pending" ? (
                      <>
                        已保存 {String(job.result.published_units)}{" "}
                        个结论候选单元
                      </>
                    ) : (
                      <>
                        已发布 {String(job.result.published_units)} 个结论单元 ·{" "}
                        {job.result.build_state === "complete"
                          ? "构建完成"
                          : "部分构建，仍有覆盖缺口"}
                      </>
                    )}
                  </p>
                )}
                {job.result?.ranking_status === "pending" && (
                  <p className="task-stage">
                    结论候选与已有支撑；核心贡献排序未完成
                  </p>
                )}
                {job.result?.previous_graph_retained === true && (
                  <p className="muted">上次已发布的图谱保持可用。</p>
                )}
                <StageFailure value={job.result?.stage_failure} />
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
                    {job.result.model_calls_status === "known_attempts_only" &&
                    typeof job.result.model_calls_unrecorded_runs ===
                      "number" ? (
                      <>
                        已记录模型调用 {String(job.result.model_calls)} 次；另{" "}
                        {String(job.result.model_calls_unrecorded_runs)}
                        条历史运行调用次数未知
                      </>
                    ) : (
                      <>模型调用 {String(job.result.model_calls)} 次</>
                    )}{" "}
                    · Token{" "}
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
                {typeof job.result?.resumed_from === "string" && (
                  <small>续接已有批次，模型调用与用量仅统计本续接任务。</small>
                )}
                {action.isSuccess &&
                  actionResult &&
                  action.variables.id === job.id && (
                    <p className="task-stage" role="status">
                      {action.variables.kind === "retry" &&
                      actionResult.id !== job.id &&
                      actionResult.status === "succeeded" &&
                      actionResult.result?.ranking_status !== "pending"
                        ? "此前的续接任务已完成，无需重复抽取。"
                        : `${action.variables.kind === "retry" ? "续接任务" : "任务操作"}已响应 · ${statusLabel(actionResult)}`}
                      {action.variables.kind === "retry" &&
                      ["failed", "interrupted", "cancelled"].includes(
                        actionResult.status,
                      )
                        ? "；请查看续接任务的错误信息。"
                        : ""}
                    </p>
                  )}
                {offpage &&
                  job.id === returnedJob?.id &&
                  continuation.error && (
                    <p className="error-text" role="alert">
                      续接任务状态暂未刷新，保留上次结果：
                      {errorText(continuation.error)}
                    </p>
                  )}
              </div>
              {continued.has(job.id) ? (
                <a
                  className="text-button"
                  href={`#job-${continued.get(job.id)!.id}`}
                >
                  查看续接结果
                </a>
              ) : ["queued", "running"].includes(job.status) ? (
                <button
                  className="text-button"
                  disabled={!connected || action.isPending}
                  onClick={() => action.mutate({ id: job.id, kind: "cancel" })}
                >
                  {action.isPending && action.variables.id === job.id
                    ? "正在取消…"
                    : "取消"}
                </button>
              ) : ["failed", "interrupted", "cancelled"].includes(job.status) &&
                (job.attempt < 3 || job.resume_adapter_available) ? (
                <button
                  className="text-button"
                  disabled={!connected || action.isPending}
                  onClick={() => action.mutate({ id: job.id, kind: "retry" })}
                >
                  {action.isPending && action.variables.id === job.id
                    ? "正在提交续接…"
                    : job.kind === "knowledge_extract"
                      ? "继续未完成批次"
                      : "重试"}
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

function StageFailure({ value }: { value: unknown }) {
  if (!value || typeof value !== "object") return null;
  const failure = value as Record<string, unknown>;
  const category =
    typeof failure.category === "string" ? failure.category : "unknown";
  const categories: Record<string, string> = {
    protocol: "模型响应格式错误",
    schema: "知识字段不符合规范",
    validation: "结果校验失败",
    context: "来源或任务快照不一致",
    evidence: "证据引用未通过校验",
    timeout: "模型请求超时",
    network: "模型网络连接失败",
    rate_limit: "模型请求受限",
    server: "模型服务暂时不可用",
    client: "模型服务拒绝请求",
    output_limit: "模型输出被截断",
    context_limit: "模型上下文不足",
    incomplete_stream: "模型响应中途断开",
    structured_output_unsupported: "结构化输出模式不受支持",
    structured_output_refused: "模型拒绝生成结构化结果",
  };
  const stage =
    typeof failure.stage === "string"
      ? (stages[failure.stage as NonNullable<Job["stage"]>] ?? "自动建图")
      : "自动建图";
  const defaults: Record<string, string> = {
    context: "检查来源变动并刷新任务；已保存知识保留。",
    evidence: "查看模型运行中的证据校验原因，再继续未完成阶段。",
    client: "在设置与诊断检查端点、模型和额度，再继续未完成阶段。",
    structured_output_unsupported:
      "在设置与诊断检查模型与结构化输出能力后创建新任务；已保存知识保留。",
    structured_output_refused:
      "查看模型运行记录并检查服务限制；已保存知识保留，不会自动重发。",
  };
  const next =
    failure.code === "RANKING_PROTOCOL_EXHAUSTED"
      ? "本次构建的自动格式修复已达上限；已保存候选和旧图保留，继续不会重复请求。"
      : typeof failure.next_action === "string" && failure.next_action
        ? failure.next_action
        : (defaults[category] ??
          "继续未完成阶段；已保存知识和成功检查点保留。");
  return (
    <div className="task-stage" aria-label="任务阶段诊断">
      <p>
        {stage}失败 · {categories[category] ?? "未完成本阶段"}
        {typeof failure.code === "string" && failure.code
          ? `（${failure.code}）`
          : ""}
      </p>
      <p>下一步：{next}</p>
    </div>
  );
}

function RankingProgress({
  result,
  running,
}: {
  result: Job["result"];
  running: boolean;
}) {
  if (result?.ranking_protocol !== "reading-ranking-keyed-1") return null;
  const completed = result.ranking_completed_claims;
  const total = result.ranking_total_claims;
  const request = result.ranking_request;
  const limit = result.ranking_request_limit;
  if (
    typeof completed !== "number" ||
    typeof total !== "number" ||
    !Number.isSafeInteger(completed) ||
    !Number.isSafeInteger(total) ||
    completed < 0 ||
    total < 1 ||
    completed > total
  )
    return null;
  const validRequest =
    typeof request === "number" &&
    typeof limit === "number" &&
    Number.isSafeInteger(request) &&
    Number.isSafeInteger(limit) &&
    request >= 1 &&
    request <= limit;
  return (
    <div className="task-stage" aria-label="贡献评估进度">
      <p>
        贡献评估输出已校验 {completed} / {total} 个结论
      </p>
      {running && result.ranking_repairing === true && validRequest && (
        <p>
          正在自动修复未完成的输出字段 · 第 {request} / {limit}{" "}
          次请求（含首次请求）
        </p>
      )}
    </div>
  );
}

function ModelActivity({ value }: { value: unknown }) {
  if (!value || typeof value !== "object") return null;
  const activity = value as Record<string, number>;
  const phase =
    activity.content_characters > 0
      ? `正在接收结构化结果（${activity.content_characters} 字符）`
      : activity.reasoning_characters > 0
        ? "模型正在思考"
        : "等待模型响应";
  return (
    <p className="task-stage">
      {phase} · 已等待 {activity.elapsed_seconds ?? 0} 秒
    </p>
  );
}
