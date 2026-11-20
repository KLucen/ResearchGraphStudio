import { useEffect, useState } from "react";
import type { Job } from "./api";

function count(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : null;
}

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function integer(value: unknown): number | null {
  const number = count(value);
  return number !== null && Number.isSafeInteger(number) ? number : null;
}

const batchPhases: Record<string, string> = {
  preparing: "准备批次",
  planned: "批次已规划",
  queued: "等待批次执行",
  extracting: "解析当前批次",
  parsing: "解析当前批次",
  rendering: "准备批次页面",
  connecting: "连接解析服务",
  uploading: "发送当前批次",
  waiting: "等待当前批次响应",
  receiving: "接收当前批次结果",
  validating: "校验当前批次",
  repairing: "修复当前批次格式",
  format_repaired: "本批格式已修复，等待继续未完成任务",
  boundary: "复核相邻批次",
  reviewing_boundary: "复核相邻批次",
  merging: "合并已校验批次",
  completed: "批次处理完成",
  succeeded: "批次处理完成",
  failed: "批次处理失败",
  interrupted: "批次处理已中断",
  cancelled: "批次处理已取消",
  paused: "批次处理已暂停",
  publication_failed: "章节发布失败",
};

function validationLocations(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 8).flatMap((item: unknown) => {
    const error = record(item);
    if (typeof error?.path !== "string" || typeof error.code !== "string")
      return [];
    const { path, code } = error;
    if (
      path.length > 160 ||
      !/^(?:\$|(?:\$\.)?[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*|\.\d+|\[\d+\])*)$/.test(
        path,
      ) ||
      !/^[a-zA-Z][a-zA-Z0-9_]{0,63}$/.test(code)
    )
      return [];
    return [`${path}（${code}）`];
  });
}

export function DocumentRequestStatus({ job }: { job: Job }) {
  const [clock, setClock] = useState(() => Date.now());
  const data = record(job.result?.document_request);
  const batches = record(job.result?.document_batches);
  const started =
    typeof data?.started_at === "string" ? Date.parse(data.started_at) : NaN;
  const running = job.status === "running";
  useEffect(() => {
    if (!running || !Number.isFinite(started)) return;
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running, started]);
  const elapsed =
    running && Number.isFinite(started)
      ? Math.max(0, (clock - started) / 1000)
      : count(data?.elapsed_seconds);
  const rendered = count(data?.rendered_pages);
  const pages = count(data?.page_count);
  const wait = count(data?.read_timeout_seconds);
  const total = count(data?.total_timeout_seconds);
  const responseStatus = integer(data?.http_status);
  const httpStatus =
    responseStatus !== null && responseStatus >= 100 && responseStatus <= 599
      ? responseStatus
      : null;
  const parts: string[] = [];
  if (elapsed !== null)
    parts.push(`${running ? "已运行" : "请求用时"} ${Math.floor(elapsed)} 秒`);
  if (rendered !== null && pages !== null && pages > 0)
    parts.push(`页面准备 ${rendered} / ${pages} 页`);
  if (wait !== null) parts.push(`单请求响应等待上限 ${wait} 秒`);
  if (total !== null) parts.push(`单请求总时限 ${total} 秒`);
  const batchParts: string[] = [];
  const batchTotal = integer(batches?.total);
  const completed = integer(batches?.completed);
  const current = integer(batches?.current);
  const firstPage = integer(batches?.page_start);
  const lastPage = integer(batches?.page_end);
  const sent = integer(batches?.requests_sent);
  const budget = integer(batches?.request_budget);
  const repairs = integer(batches?.repairs_used);
  const boundaries = integer(batches?.boundaries_completed);
  const boundaryTotal = integer(batches?.boundaries_total);
  const reviewingBoundary = batches?.current_kind === "boundary";
  const publishing = batches?.current_kind === "publication";
  const phase =
    typeof batches?.phase === "string" &&
    Object.hasOwn(batchPhases, batches.phase)
      ? batchPhases[batches.phase]
      : undefined;
  if (publishing) {
    if (job.status === "failed") batchParts.push("章节发布失败");
    else if (job.status === "queued") batchParts.push("等待重新发布章节");
    else if (job.status === "running") batchParts.push("正在重新发布章节");
    else batchParts.push("章节发布未完成");
  } else if (reviewingBoundary) {
    if (
      current !== null &&
      current > 0 &&
      boundaryTotal !== null &&
      current <= boundaryTotal
    )
      batchParts.push(`第 ${current} / ${boundaryTotal} 个边界`);
    else if (boundaryTotal !== null)
      batchParts.push(`共 ${boundaryTotal} 个边界`);
    if (batchTotal !== null && batchTotal > 0 && completed === batchTotal)
      batchParts.push("正文批次已完成");
    if (job.status === "failed") batchParts.push("边界复核失败");
  } else if (
    current !== null &&
    current > 0 &&
    batchTotal !== null &&
    current <= batchTotal
  )
    batchParts.push(`第 ${current} / ${batchTotal} 批`);
  else if (batchTotal !== null) batchParts.push(`共 ${batchTotal} 批`);
  if (
    !publishing &&
    firstPage !== null &&
    firstPage > 0 &&
    lastPage !== null &&
    lastPage >= firstPage
  )
    batchParts.push(`原始第 ${firstPage}–${lastPage} 页`);
  if (completed !== null && batchTotal !== null && completed <= batchTotal)
    batchParts.push(`已校验 ${completed} / ${batchTotal} 批`);
  if (sent !== null)
    batchParts.push(
      budget !== null
        ? `已发送 ${sent} / ${budget} 次请求`
        : `已发送 ${sent} 次请求`,
    );
  else if (budget !== null) batchParts.push(`请求预算 ${budget} 次`);
  if (repairs !== null) batchParts.push(`格式修复已用 ${repairs} 次`);
  if (
    boundaries !== null &&
    boundaryTotal !== null &&
    boundaries <= boundaryTotal
  )
    batchParts.push(`边界复核 ${boundaries} / ${boundaryTotal}`);
  if (httpStatus !== null) batchParts.push(`HTTP 状态 ${httpStatus}`);
  if (phase && !(publishing && phase === batchPhases.publication_failed))
    batchParts.push(phase);
  const errors = validationLocations(batches?.validation_errors);
  if (!parts.length && !batchParts.length && !errors.length) return null;
  return (
    <>
      {!!parts.length && (
        <p className="muted" aria-label="文档请求状态">
          {parts.join(" · ")}
        </p>
      )}
      {!!batchParts.length && (
        <p className="muted" aria-label="文档批次状态">
          {batchParts.join(" · ")}
        </p>
      )}
      {!!errors.length && (
        <p className="muted" aria-label="文档校验位置">
          校验位置：{errors.join("；")}
        </p>
      )}
      {httpStatus === 400 && (
        <p className="muted" aria-label="文档请求拒绝提示">
          服务拒绝请求，重复继续通常不能解决，请检查请求参数或安装修复版
        </p>
      )}
    </>
  );
}
