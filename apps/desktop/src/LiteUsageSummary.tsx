import { useQuery } from "@tanstack/react-query";
import { api, type LiteUsage } from "./api";

export function LiteUsageSummary({
  connected,
  projectId,
  paperId,
}: {
  connected: boolean;
  projectId?: string;
  paperId?: string;
}) {
  const usage = useQuery({
    queryKey: ["lite-usage", projectId ?? "all", paperId ?? null],
    queryFn: () =>
      projectId ? api.liteUsage(projectId, paperId) : api.liteUsageGlobal(),
    enabled: connected,
    refetchInterval: 5000,
  });
  if (usage.isPending) return <p className="muted">正在读取本地用量统计…</p>;
  if (usage.isError)
    return <p className="quality-note">用量统计暂不可用，阅读流程仍可继续。</p>;
  const data: LiteUsage = usage.data;
  const callLabel = data.calls_known
    ? data.calls === 0
      ? data.cache_hits > 0
        ? "0 次新增模型调用"
        : "尚未调用模型"
      : `${data.calls} 次调用`
    : `已记录调用 ${data.calls} 次；另有 ${data.unrecorded_runs} 条历史记录未记录调用次数`;
  return (
    <section className="settings-card" aria-label="Lite 模型用量">
      <div className="settings-title">
        <h2>Lite 用量</h2>
        <span className="pill">{callLabel}</span>
      </div>
      <p className="muted">
        {projectId ? "当前项目" : "所有 Lite 项目"}
        的模型调用账本；本地解析、章节索引和缓存命中不会产生新的模型调用。
      </p>
      <dl>
        <dt>输入 Token</dt>
        <dd>{data.input_tokens.toLocaleString("zh-CN")}</dd>
        <dt>输出 Token</dt>
        <dd>{data.output_tokens.toLocaleString("zh-CN")}</dd>
        <dt>调用 / 重试</dt>
        <dd>
          {data.calls} / {data.retry_count}
        </dd>
        <dt>缓存命中</dt>
        <dd>{data.cache_hits}</dd>
        <dt>费用</dt>
        <dd>
          {data.cost_known && data.cost_estimate !== null
            ? data.cost_estimate.toLocaleString("zh-CN", {
                style: "currency",
                currency: "USD",
              })
            : "未提供定价"}
        </dd>
      </dl>
      {data.unknown_usage_calls > 0 && (
        <p className="quality-note">
          {data.unknown_usage_calls} 次请求未返回完整 Token 用量，不能按 0
          计算。
        </p>
      )}
      {data.cache_hits > 0 && (
        <p className="muted">
          缓存命中 {data.cache_hits} 次，未产生新的模型调用或 Token。
        </p>
      )}
    </section>
  );
}
