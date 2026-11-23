import type { ReactNode } from "react";
import type { Job } from "./api";

const categories: Record<string, string> = {
  transport: "请求与连接",
  protocol: "响应格式",
  schema: "字段结构",
  source: "来源校验",
  budget: "预算",
  configuration: "模型配置",
  unknown: "原因未确定",
};

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function diagnosticFor(job: Job) {
  if (!["knowledge_extract", "knowledge_connect"].includes(job.kind))
    return null;
  const data = record(job.result?.knowledge_diagnostic);
  if (
    data?.version !== "knowledge-diagnostic-1" ||
    typeof data.code !== "string" ||
    !/^[A-Z][A-Z0-9_]{0,95}$/.test(data.code) ||
    typeof data.category !== "string" ||
    !Object.hasOwn(categories, data.category) ||
    typeof data.summary !== "string" ||
    typeof data.action !== "string" ||
    typeof data.request_sent !== "boolean" ||
    typeof data.raw_available !== "boolean" ||
    !Array.isArray(data.issues)
  )
    return null;
  const issues = data.issues.flatMap((value: unknown) => {
    const issue = record(value);
    if (
      typeof issue?.path !== "string" ||
      issue.path.length > 240 ||
      !/^(?:\$|(?:\$\.)?[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*|\.\d+|\[\d+\])*)$/.test(
        issue.path,
      ) ||
      typeof issue.code !== "string" ||
      !/^[a-zA-Z][a-zA-Z0-9_]{0,95}$/.test(issue.code) ||
      typeof issue.message !== "string"
    )
      return [];
    return [{ path: issue.path, code: issue.code, message: issue.message }];
  });
  const count = data.issue_count;
  const issueCount =
    typeof count === "number" &&
    Number.isSafeInteger(count) &&
    count >= issues.length
      ? count
      : issues.length;
  return {
    code: data.code,
    category: categories[data.category],
    summary: data.summary,
    action: data.action,
    requestSent: data.request_sent,
    rawAvailable: data.raw_available,
    issues,
    issueCount,
  };
}

export function KnowledgeTaskDiagnostic({
  job,
  children,
}: {
  job: Job;
  children?: ReactNode;
}) {
  if (
    !["knowledge_extract", "knowledge_connect"].includes(job.kind) ||
    !["failed", "interrupted", "cancelled"].includes(job.status)
  )
    return null;
  const diagnostic = diagnosticFor(job);
  if (!diagnostic)
    return (
      <section
        className="knowledge-task-diagnostic"
        aria-label="知识任务错误详情"
      >
        <p>
          此历史任务没有可用的细分诊断，当前不能仅凭错误码判断具体原因。系统不会自动重发。
        </p>
        {children}
        {job.error && /^[A-Z][A-Z0-9_]{0,95}$/.test(job.error) && (
          <details className="task-diagnostic-details">
            <summary>诊断详情</summary>
            <p className="muted">错误码：{job.error}</p>
          </details>
        )}
      </section>
    );
  return (
    <section
      className="knowledge-task-diagnostic"
      aria-label="知识任务错误详情"
    >
      <p>
        <strong>失败原因 · {diagnostic.category}</strong>
      </p>
      <p>{diagnostic.summary}</p>
      {diagnostic.action && <p>处理建议：{diagnostic.action}</p>}
      {children}
      <details className="task-diagnostic-details">
        <summary>诊断详情</summary>
        <p className="muted">
          错误码：{diagnostic.code} · 发送记录：
          {diagnostic.requestSent ? "已标记；费用未知" : "未标记发送"} ·
          原始响应：
          {diagnostic.rawAvailable ? "已在本机保留" : "没有可检查的响应"}
        </p>
        {diagnostic.issues.length > 0 && (
          <ul aria-label="知识任务校验问题">
            {diagnostic.issues.map((issue, index) => (
              <li key={`${issue.path}:${issue.code}:${index}`}>
                <code>{issue.path}</code>（{issue.code}）：{issue.message}
              </li>
            ))}
          </ul>
        )}
        {diagnostic.issueCount > diagnostic.issues.length && (
          <p className="muted">
            共 {diagnostic.issueCount} 项问题，当前显示{" "}
            {diagnostic.issues.length} 项安全诊断。
          </p>
        )}
      </details>
    </section>
  );
}
