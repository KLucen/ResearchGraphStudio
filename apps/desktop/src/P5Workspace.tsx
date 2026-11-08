import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, RefreshCw, X } from "lucide-react";
import { api, type PaperList } from "./api";
import {
  p5Api,
  type LintIssue,
  type LintRepairPlan,
  type LintRun,
  type P5Dependency,
  type WikiPageView,
  type WikiPassage,
  type WorkflowRequest,
  emptyPersonalSelection,
} from "./p5Api";
import { PersonalSources, LintDocuments, ExternalLibrary } from "./P5Sources";
import "./P5Workspace.css";

const message = (error: unknown) =>
  error instanceof Error ? error.message : String(error);
const PAGE_SIZE = 10;
const labels: Record<string, string> = {
  queued: "等待执行",
  running: "正在处理",
  completed: "检查完成",
  prepared: "来源已准备",
  insufficient: "来源不足",
  succeeded: "生成完成",
  failed: "执行失败",
  interrupted: "执行中断",
  partial: "部分完成",
  cancelled: "已取消",
  input_stale: "检查输入已变化",
  new: "新发现",
  persistent: "仍存在",
  resolved: "已消失",
  error: "错误",
  warning: "警告",
  info: "提示",
  evidence: "原文证据",
  support: "支撑路径",
  dependency: "内容依赖",
  file: "文件状态",
  condition: "适用条件",
  link: "文档链接",
  unverifiable: "无法核验",
  paper_author: "论文作者主张",
  citation_report: "转述其他研究",
  user_view: "个人观点",
  model_synthesis: "AI 综合整理",
  draft: "草稿",
  saved: "已保存内部版本",
  published: "已导出",
  valid: "内容有效",
  stale: "内容依赖已失效",
  not_exported: "尚未导出",
  in_sync: "文件与登记版本一致",
  modified: "文件已被外部修改",
  external_modified: "文件已被外部修改",
  missing: "文件缺失",
  conflict: "文件冲突",
  unavailable: "文件当前无法访问",
  invalid: "内容来源无效",
  unverified: "内容尚未完成核验",
  staged: "导出暂存完成",
  replaced: "文件已写入，等待确认",
  node: "知识与支撑",
  chunk: "原文片段",
  note: "个人笔记快照",
  annotation: "个人批注评论",
  external: "外部阅读材料（科学来源未核验）",
  passage: "已保存的阅读段落",
  replace: "替换所选段落",
  append: "追加有据段落",
  mark_stale: "标记段落失效",
  known: "已知",
  unknown: "未知",
  not_applicable: "不适用",
  conflicting: "存在冲突",
  lint_semantic: "语义辅助检查",
  wiki_synthesis: "主题阅读整理",
  wiki_delta: "Wiki 局部更新",
};
const label = (value: string) => labels[value] ?? value;
type RepairPlan = LintRepairPlan;
const repairStatusLabels: Record<RepairPlan["status"], string> = {
  informational: "信息缺口",
  actionable: "可按步骤处理",
  blocked: "需先解决前置条件",
};
function fallbackRepairPlan(issue: LintIssue): RepairPlan {
  if (issue.lifecycle === "resolved") {
    return {
      status: "informational",
      summary: "本次检查中问题已消失，只需按需查看历史报告，无需重复修复。",
      steps: [
        {
          id: "review-history",
          title: "按需查看历史报告",
          description: "保留原诊断与处理记录；问题未再次出现时无需执行修复。",
          action: "review_history",
          automated: false,
          requires_model: false,
        },
      ],
      safeguards: [
        "历史问题已消失不等于证明科学结论正确，也不需要重复改写知识。",
      ],
    };
  }
  if (issue.lifecycle === "input_stale") {
    return {
      status: "blocked",
      summary: "检查输入已变化；先重新扫描当前范围，再依据新报告决定处理方案。",
      steps: [
        {
          id: "rerun-current-scope",
          title: "重新扫描当前范围",
          description:
            "显式启动规则检查，重新核验当前来源和依赖；旧诊断仅保留为历史。",
          action: "rerun_lint",
          automated: false,
          requires_model: false,
        },
      ],
      safeguards: ["不依据过期输入执行修复，不自动调用模型或改写科学知识。"],
    };
  }
  if (issue.code === "SOURCE_UNCHECKED") {
    return {
      status: "informational",
      summary:
        "先确认原始文献文件当前是否可读，再重新运行规则检查；这只补充来源可用性记录，不改写已有证据。",
      steps: [
        {
          id: "check-source",
          title: "在文献页检查原始来源",
          description: "打开对应论文或附件，确认文件路径、权限和内容可读。",
          action: "manual",
          automated: false,
          requires_model: false,
        },
        {
          id: "rerun-lint",
          title: "重新运行 Lint",
          description:
            "来源检查完成后重新扫描受影响范围，让诊断读取新的来源状态。",
          action: "rerun_lint",
          automated: false,
          requires_model: false,
        },
      ],
      safeguards: [
        "没有检查记录时不能判定科学结论错误。",
        "来源不可用时保留内部证据和历史版本，不删除或伪造证据。",
      ],
    };
  }
  if (issue.code === "CONDITION_UNKNOWN") {
    return {
      status: "informational",
      summary:
        "这是实验条件的信息缺口。先回查原文；有明确证据时通过受控重建或新版本补充条件，原文没有说明时继续保留 unknown。",
      steps: [
        {
          id: "review-condition",
          title: "回查原文中的实验条件",
          description:
            "查看正文、表格和图注，确认该条件是否被明确记录以及适用的实验范围。",
          action: "manual",
          automated: false,
          requires_model: false,
        },
        {
          id: "record-condition",
          title: "有明确证据时受控重建或创建新版本",
          description:
            "确认原文明确给出条件后，通过后续受控流程重建受影响内容或创建新版本；当前诊断不直接编辑条件。原文没有说明时维持 unknown。",
          action: "rebuild_affected",
          automated: false,
          requires_model: null,
        },
        {
          id: "rerun-lint",
          title: "重新运行 Lint",
          description:
            "受控重建或新版本保存完成后，重新检查受影响知识和文档段落。",
          action: "rerun_lint",
          automated: false,
          requires_model: false,
        },
      ],
      safeguards: [
        "unknown 不等于 conflicting，也不表示已经发现科学矛盾。",
        "不能根据常识、模型猜测或相邻实验补造条件。",
      ],
    };
  }
  return {
    status: issue.severity === "error" ? "actionable" : "informational",
    summary: issue.suggestion,
    steps: [
      {
        id: "review-issue",
        title: "回查问题对象和根证据",
        description:
          "先查看原文证据、知识对象和依赖范围，再决定是否创建新版本或重新检查。",
        action: "manual",
        automated: false,
        requires_model: false,
      },
    ],
    safeguards: ["Lint 只提供诊断和处理建议，不自动改写科学知识或原始文件。"],
  };
}
function issueRepairPlan(issue: LintIssue): RepairPlan {
  const supplied = issue.repair_plan;
  if (
    supplied &&
    (supplied.status === "informational" ||
      supplied.status === "actionable" ||
      supplied.status === "blocked") &&
    typeof supplied.summary === "string" &&
    Array.isArray(supplied.steps) &&
    Array.isArray(supplied.safeguards)
  ) {
    return supplied as RepairPlan;
  }
  return fallbackRepairPlan(issue);
}
function repairModelRequirement(value: boolean | null | undefined) {
  if (value === true) return "需要模型（需单独授权）";
  if (value === false) return "此步骤不调用模型";
  return "由后续受控流程决定";
}
const active = (value: string) => ["queued", "running"].includes(value);
const lintPhaseOrder = (run: LintRun) =>
  ({ scanning: 0, rebuilding_dependencies: 1, finished: 2 })[
    run.phase ?? (active(run.status) ? "scanning" : "finished")
  ];
const lintTimingStages = [
  ["prepare_seconds", "准备范围"],
  ["validate_seconds", "输入复核"],
  ["check_seconds", "逐批规则检查"],
  ["dependency_rebuild_seconds", "依赖索引重建"],
  ["finalize_seconds", "结束归档"],
  ["elapsed_seconds", "已记录总耗时"],
  ["last_advance_seconds", "最近一次推进"],
] as const;
function LintTimings({ timings }: { timings: LintRun["timings"] }) {
  const recorded = (key: string) => {
    const value = timings?.[key];
    return typeof value === "number" && Number.isFinite(value) && value >= 0
      ? value
      : null;
  };
  const calls = recorded("advance_calls");
  return (
    <details className="p5-timings">
      <summary>阶段耗时</summary>
      <dl>
        {lintTimingStages.map(([key, title]) => {
          const value = recorded(key);
          return (
            <div key={key}>
              <dt>{title}</dt>
              <dd>{value === null ? "未记录" : `${value.toFixed(3)} 秒`}</dd>
            </div>
          );
        })}
        <div>
          <dt>推进请求</dt>
          <dd>{calls === null ? "未记录" : `${calls} 次`}</dd>
        </div>
      </dl>
    </details>
  );
}
function field(value: Record<string, unknown> | null | undefined, key: string) {
  return typeof value?.[key] === "string" ? value[key] : "";
}
function load(key: string) {
  try {
    return localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}
function useRememberedId(key: string, initialValue = "") {
  const [value, setValue] = useState(() => initialValue || load(key));
  useEffect(() => {
    try {
      if (value) localStorage.setItem(key, value);
      else localStorage.removeItem(key);
    } catch {
      /* The persisted engine history remains available. */
    }
  }, [key, value]);
  return [value, setValue] as const;
}
function useOperationKey() {
  const keys = useRef(new Map<string, string>());
  return (name: string, body: unknown) => {
    const signature = name + JSON.stringify(body);
    let key = keys.current.get(signature);
    if (!key) {
      key = crypto.randomUUID();
      keys.current.set(signature, key);
    }
    return key;
  };
}
async function allPapers(projectId: string): Promise<PaperList["items"]> {
  const items = new Map<string, PaperList["items"][number]>();
  const seen = new Set<number>();
  let cursor: number | null = 0;
  while (cursor !== null) {
    if (seen.has(cursor)) throw new Error("论文分页已变化，请刷新后重试");
    seen.add(cursor);
    const page = await api.papers(projectId, cursor);
    page.items.forEach((paper) => items.set(paper.id, paper));
    cursor = page.next_cursor;
  }
  return [...items.values()];
}

function Pagination({
  name,
  page,
  total,
  onChange,
}: {
  name: string;
  page: number;
  total: number;
  onChange: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const current = Math.min(page, pages);
  return (
    <nav className="p5-pagination" aria-label={`${name}分页`}>
      <span>
        共 {total} 条 · 每页 10 条 · 第 {current} / {pages} 页
      </span>
      <div>
        <button
          type="button"
          className="text-button"
          aria-label={`${name}上一页`}
          disabled={current <= 1}
          onClick={() => onChange(current - 1)}
        >
          上一页
        </button>
        <button
          type="button"
          className="text-button"
          aria-label={`${name}下一页`}
          disabled={current >= pages}
          onClick={() => onChange(current + 1)}
        >
          下一页
        </button>
      </div>
    </nav>
  );
}
function ErrorBox({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  if (!error) return null;
  return (
    <div role="alert" className="error-banner">
      {message(error)}
      {onRetry && (
        <button type="button" className="text-button" onClick={onRetry}>
          重新读取
        </button>
      )}
    </div>
  );
}
function PaperScope({
  papers,
  value,
  onChange,
  name,
}: {
  papers: PaperList["items"];
  value: string[];
  onChange: (ids: string[]) => void;
  name: string;
}) {
  const [page, setPage] = useState(1);
  return (
    <details className="p5-scope">
      <summary>
        {name} · {value.length ? `已选 ${value.length} 篇` : "全部论文"}
      </summary>
      <button
        type="button"
        className="text-button"
        onClick={() => onChange([])}
      >
        选择全部论文
      </button>
      <div className="p5-paper-options">
        {papers.slice((page - 1) * 10, page * 10).map((paper) => (
          <label key={paper.id}>
            <input
              type="checkbox"
              aria-label={`${name} · ${paper.title}`}
              checked={value.includes(paper.id)}
              onChange={(event) =>
                onChange(
                  event.target.checked
                    ? [...value, paper.id]
                    : value.filter((id) => id !== paper.id),
                )
              }
            />
            {paper.title}
          </label>
        ))}
      </div>
      <Pagination
        name={name}
        page={page}
        total={papers.length}
        onChange={setPage}
      />
    </details>
  );
}

type Navigation = {
  onGraphNode: (id: string) => void;
  onWikiPage?: (id: string) => void;
};
export function P5Workspace({
  projectId,
  connected,
  mode,
  onGraphNode,
  onWikiPage,
  initialPageId = "",
}: Navigation & {
  projectId: string;
  connected: boolean;
  mode: "lint" | "wiki";
  initialPageId?: string;
}) {
  const [evidenceId, setEvidenceId] = useState("");
  const papers = useQuery({
    queryKey: ["p5-papers", projectId],
    queryFn: () => allPapers(projectId),
    enabled: connected,
    retry: false,
  });
  return (
    <section
      className="p5-workspace"
      aria-label={mode === "lint" ? "Lint 自动诊断" : "Wiki 阅读整理"}
    >
      {!connected && (
        <p role="status" className="quiet-note">
          等待本地引擎连接，暂不启动检查或生成。
        </p>
      )}
      <ErrorBox error={papers.error} onRetry={() => void papers.refetch()} />
      {mode === "lint" ? (
        <LintWorkspace
          projectId={projectId}
          connected={connected}
          papers={papers.data ?? []}
          onGraphNode={onGraphNode}
          onWikiPage={onWikiPage}
          onEvidence={setEvidenceId}
        />
      ) : (
        <WikiWorkspace
          projectId={projectId}
          connected={connected}
          papers={papers.data ?? []}
          onGraphNode={onGraphNode}
          onEvidence={setEvidenceId}
          initialPageId={initialPageId}
        />
      )}
      {evidenceId && (
        <EvidenceDialog
          evidenceId={evidenceId}
          connected={connected}
          onClose={() => setEvidenceId("")}
        />
      )}
    </section>
  );
}

type WorkProps = Navigation & {
  projectId: string;
  connected: boolean;
  papers: PaperList["items"];
  onEvidence: (id: string) => void;
};
function LintWorkspace({
  projectId,
  connected,
  papers,
  onEvidence,
  onGraphNode,
  onWikiPage,
}: WorkProps) {
  const client = useQueryClient();
  const [paperIds, setPaperIds] = useState<string[]>([]);
  const [personal, setPersonal] = useState(false);
  const [documentIds, setDocumentIds] = useState<string[]>([]);
  const [personalSources, setPersonalSources] = useState(
    emptyPersonalSelection,
  );
  const [runId, setRunId] = useRememberedId(`rgs.lint.active.${projectId}`);
  const [reportsPage, setReportsPage] = useState(1);
  const [issuePage, setIssuePage] = useState(1);
  const [severity, setSeverity] = useState("");
  const [category, setCategory] = useState("");
  const [lifecycle, setLifecycle] = useState("");
  const [sourcePaper, setSourcePaper] = useState("");
  const [question, setQuestion] = useState(
    "检查是否存在过度概括、来源错归属、条件混用或翻译偏移。",
  );
  const stopped = useRef(false);
  const mounted = useRef(true);
  const operationRevision = useRef(0);
  const readRevisions = useRef(new Map<string, number>());
  const snapshots = useRef(new Map<string, LintRun>());
  const [scanPhase, setScanPhase] = useState<"preparing" | "advancing" | null>(
    null,
  );
  const startKey = useRef(crypto.randomUUID());
  const rebuildKey = useRef(crypto.randomUUID());
  const operationKey = useOperationKey();
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      stopped.current = true;
      operationRevision.current += 1;
    };
  }, []);
  const reports = useQuery({
    queryKey: ["lint-reports", projectId, reportsPage],
    queryFn: () => p5Api.lintRuns(projectId, reportsPage),
    enabled: connected,
    retry: false,
  });
  const newerRun = (incoming: LintRun) => {
    const previous =
      snapshots.current.get(incoming.id) ??
      client.getQueryData<LintRun>(["lint-run", projectId, incoming.id]);
    if (
      previous &&
      (incoming.processed < previous.processed ||
        (incoming.processed === previous.processed &&
          lintPhaseOrder(incoming) < lintPhaseOrder(previous)) ||
        (!active(previous.status) && incoming.status !== previous.status) ||
        Date.parse(incoming.updated_at) < Date.parse(previous.updated_at))
    )
      return previous;
    return incoming;
  };
  const current = useQuery({
    queryKey: ["lint-run", projectId, runId],
    queryFn: async () => {
      const revision = readRevisions.current.get(runId) ?? 0;
      const incoming = await p5Api.lintRun(projectId, runId);
      const latest = snapshots.current.get(runId);
      const accepted =
        revision !== (readRevisions.current.get(runId) ?? 0) && latest
          ? latest
          : newerRun(incoming);
      snapshots.current.set(runId, accepted);
      return accepted;
    },
    enabled: connected && !!runId,
    retry: false,
    refetchInterval: (query) =>
      active(query.state.data?.status ?? "") ? 2000 : false,
  });
  const observedRunId = current.data?.id;
  const observedStatus = current.data?.status;
  useEffect(() => {
    if (observedRunId && observedStatus && !active(observedStatus))
      void client.invalidateQueries({ queryKey: ["lint-reports", projectId] });
  }, [client, projectId, observedRunId, observedStatus]);
  const filters = {
    page: issuePage,
    severity,
    category,
    lifecycle,
    paper_id: sourcePaper,
  };
  const issues = useQuery({
    queryKey: [
      "lint-issues",
      projectId,
      runId,
      filters,
      current.data?.processed,
      current.data?.status,
    ],
    queryFn: () => p5Api.lintIssues(projectId, runId, filters),
    enabled: connected && !!runId,
    retry: false,
  });
  const publishRun = async (incoming: LintRun, revision: number) => {
    if (!mounted.current || revision !== operationRevision.current) return null;
    await client.cancelQueries(
      { queryKey: ["lint-run", projectId, incoming.id], exact: true },
      { revert: false },
    );
    if (!mounted.current || revision !== operationRevision.current) return null;
    const accepted = newerRun(incoming);
    readRevisions.current.set(
      incoming.id,
      (readRevisions.current.get(incoming.id) ?? 0) + 1,
    );
    snapshots.current.set(incoming.id, accepted);
    client.setQueryData(["lint-run", projectId, incoming.id], accepted);
    return accepted;
  };
  const advance = async (first: LintRun, revision: number) => {
    let run = first;
    while (
      mounted.current &&
      !stopped.current &&
      revision === operationRevision.current &&
      active(run.status)
    ) {
      const previous = run;
      run = await p5Api.lintAdvance(
        projectId,
        run.id,
        operationKey("lint-advance", [
          run.id,
          run.processed,
          run.phase ?? "scanning",
          run.input_hash,
        ]),
      );
      if (
        !mounted.current ||
        stopped.current ||
        revision !== operationRevision.current
      )
        break;
      const accepted = await publishRun(run, revision);
      if (!accepted) break;
      run = accepted;
      if (
        active(run.status) &&
        run.processed === previous.processed &&
        lintPhaseOrder(run) <= lintPhaseOrder(previous)
      )
        throw new Error("本次扫描未推进，请重新读取报告后继续。");
    }
    void client.invalidateQueries({ queryKey: ["lint-reports", projectId] });
    return run;
  };
  const scan = useMutation({
    mutationFn: async (resume: boolean) => {
      const revision = ++operationRevision.current;
      stopped.current = false;
      setScanPhase(resume ? "advancing" : "preparing");
      try {
        const run =
          resume && current.data
            ? current.data
            : await p5Api.lintStart(
                projectId,
                {
                  paper_ids: paperIds,
                  document_ids: documentIds,
                  include_personal: personal,
                },
                operationKey("lint-start", [
                  startKey.current,
                  paperIds,
                  documentIds,
                  personal,
                ]),
              );
        startKey.current = crypto.randomUUID();
        if (
          mounted.current &&
          !stopped.current &&
          revision === operationRevision.current
        ) {
          const accepted = await publishRun(run, revision);
          if (!accepted) return run;
          setRunId(run.id);
          setIssuePage(1);
          setScanPhase("advancing");
          return await advance(accepted, revision);
        }
        return run;
      } finally {
        if (mounted.current && revision === operationRevision.current)
          setScanPhase(null);
      }
    },
  });
  const cancel = useMutation({
    mutationFn: async () => {
      const revision = ++operationRevision.current;
      stopped.current = true;
      setScanPhase(null);
      const run = await p5Api.lintCancel(
        projectId,
        runId,
        operationKey("lint-cancel", runId),
      );
      await publishRun(run, revision);
      void client.invalidateQueries({ queryKey: ["lint-reports", projectId] });
    },
  });
  const rebuild = useMutation({
    mutationFn: () => p5Api.rebuildDependencies(projectId, rebuildKey.current),
    onSuccess: () => {
      rebuildKey.current = crypto.randomUUID();
      void client.invalidateQueries({
        queryKey: ["lint-dependencies", projectId],
      });
    },
  });
  const run = current.data;
  const filterSelect = (
    title: string,
    value: string,
    values: string[],
    change: (value: string) => void,
  ) => (
    <label>
      {title}
      <select
        aria-label={title}
        value={value}
        onChange={(event) => {
          change(event.target.value);
          setIssuePage(1);
        }}
      >
        <option value="">全部</option>
        {values.map((item) => (
          <option key={item} value={item}>
            {label(item)}
          </option>
        ))}
      </select>
    </label>
  );
  return (
    <>
      <section className="p5-panel">
        <div className="p5-heading">
          <h3>规则检查</h3>
          <span className="p5-tag">不调用模型</span>
        </div>
        {scanPhase === "preparing" && (
          <div className="p5-scan-phase" role="status">
            <p>
              正在准备检查范围并核验来源；总数确定后开始逐批检查，不调用模型。
            </p>
            <progress aria-label="扫描准备进度" aria-valuetext="检查总数待定" />
            <span className="quiet-note">检查总数待定</span>
          </div>
        )}
        {scanPhase === "advancing" &&
          (!run ||
            (active(run.status) &&
              run.phase !== "rebuilding_dependencies")) && (
            <p role="status">
              正在逐批检查；进度在本批完成后更新，不调用模型。
            </p>
          )}
        <PaperScope
          papers={papers}
          value={paperIds}
          onChange={setPaperIds}
          name="检查论文范围"
        />
        <label className="p5-check">
          <input
            type="checkbox"
            checked={personal}
            onChange={(event) => {
              setPersonal(event.target.checked);
              setDocumentIds([]);
              setPersonalSources(emptyPersonalSelection());
            }}
          />
          包含已授权私人 Markdown 的只读检查
        </label>
        <LintDocuments
          projectId={projectId}
          connected={connected}
          personal={personal}
          value={documentIds}
          onChange={setDocumentIds}
        />
        <div className="p5-actions">
          <button
            type="button"
            className="button primary"
            disabled={!connected || scan.isPending}
            onClick={() => scan.mutate(false)}
          >
            {scan.isPending ? (
              <LoaderCircle size={16} className="spin" />
            ) : (
              <RefreshCw size={16} />
            )}
            开始规则扫描
          </button>
          {run && active(run.status) && !scan.isPending && (
            <button
              type="button"
              className="button secondary"
              disabled={!connected}
              onClick={() => scan.mutate(true)}
            >
              继续未完成检查
            </button>
          )}
          {run && active(run.status) && (
            <button
              type="button"
              className="button secondary"
              disabled={cancel.isPending || !connected}
              onClick={() => cancel.mutate()}
            >
              取消规则扫描
            </button>
          )}
        </div>
        <ErrorBox error={scan.error || cancel.error} />
        <div className="p5-actions">
          <button
            type="button"
            className="button secondary"
            disabled={!connected || scan.isPending || rebuild.isPending}
            onClick={() => rebuild.mutate()}
          >
            重建派生依赖索引
          </button>
          <span className="quiet-note">
            仅修复派生索引；完成后可重新扫描，不更改科学知识。
          </span>
        </div>
        <ErrorBox error={rebuild.error} />
        {rebuild.isPending && (
          <div className="p5-scan-phase" role="status">
            <p>正在重建派生依赖索引，完成后显示依赖条数。</p>
            <progress aria-label="手动依赖索引重建进度" />
          </div>
        )}
        {rebuild.data && (
          <p role="status">
            依赖索引已重建，共 {rebuild.data.edge_count} 条依赖；检测到{" "}
            {rebuild.data.change_count} 项变化。
          </p>
        )}
        {run && (
          <div className="p5-run-status" role="status">
            <div className="p5-heading">
              <strong>
                {active(run.status)
                  ? run.phase === "rebuilding_dependencies"
                    ? scanPhase === "advancing"
                      ? "正在重建依赖索引"
                      : "依赖索引待重建，可继续检查"
                    : scanPhase === "advancing"
                      ? "正在逐批检查"
                      : "检查尚未完成，可继续检查"
                  : label(run.status)}
              </strong>
              <button
                type="button"
                className="text-button"
                disabled={!connected || current.isFetching}
                onClick={() => void current.refetch()}
              >
                重新读取报告
              </button>
            </div>
            <progress
              aria-label="对象检查进度"
              max={Math.max(1, run.total)}
              value={run.processed}
            />
            <span>
              已检查 {run.processed} / {run.total} 个对象 · 规则{" "}
              {run.rule_version}
            </span>
            {active(run.status) && run.phase === "rebuilding_dependencies" && (
              <div className="p5-scan-phase">
                <p>
                  {scanPhase === "advancing"
                    ? "对象检查已完成，正在重建依赖索引；完成后才结束本轮扫描。"
                    : "对象检查已完成，依赖索引尚未重建；继续检查后完成报告。"}
                </p>
                {scanPhase === "advancing" && (
                  <progress aria-label="扫描依赖索引重建进度" />
                )}
              </div>
            )}
            {run.status === "completed" && (
              <p className="quiet-note">
                {run.counts.error === 0 && run.counts.warning === 0
                  ? `规则检查完成：未发现错误或警告，保留 ${run.counts.info} 条信息提示。`
                  : `规则检查完成：${run.counts.error} 条错误、${run.counts.warning} 条警告、${run.counts.info} 条信息提示。`}
                信息缺口不代表错误；规则结果不等于科学正确性证明。
              </p>
            )}
            <span>
              错误 {run.counts.error} · 警告 {run.counts.warning} · 提示{" "}
              {run.counts.info}
            </span>
            <p>
              与上次报告对比：新发现 {run.diff.new} · 仍存在{" "}
              {run.diff.persistent} · 已消失 {run.diff.resolved}
            </p>
            {["partial", "input_stale", "cancelled"].includes(run.status) && (
              <p className="quiet-note">
                保留已检查范围，此报告不代表当前项目已全部检查。
              </p>
            )}
            {run.errors.map((error, index) => (
              <p className="error-text" key={index}>
                {field(error, "message") ||
                  field(error, "error") ||
                  field(error, "code") ||
                  "部分规则未完成，请重新读取报告。"}
              </p>
            ))}
            <LintTimings timings={run.timings} />
          </div>
        )}
        <ErrorBox
          error={current.error}
          onRetry={() => void current.refetch()}
        />
      </section>
      <section className="p5-panel">
        <h3>诊断结果</h3>
        <div className="p5-filters">
          {filterSelect(
            "严重性",
            severity,
            ["error", "warning", "info"],
            setSeverity,
          )}
          {filterSelect(
            "问题类型",
            category,
            [
              "evidence",
              "support",
              "dependency",
              "file",
              "condition",
              "link",
              "unverifiable",
            ],
            setCategory,
          )}
          {filterSelect(
            "诊断状态",
            lifecycle,
            ["new", "persistent", "resolved", "input_stale"],
            setLifecycle,
          )}
          <label>
            来源论文
            <select
              aria-label="诊断来源论文"
              value={sourcePaper}
              onChange={(event) => {
                setSourcePaper(event.target.value);
                setIssuePage(1);
              }}
            >
              <option value="">全部论文</option>
              {papers.map((paper) => (
                <option value={paper.id} key={paper.id}>
                  {paper.title}
                </option>
              ))}
            </select>
          </label>
        </div>
        {runId ? (
          <>
            <Pagination
              name="诊断结果"
              total={issues.data?.total ?? 0}
              page={issuePage}
              onChange={setIssuePage}
            />
            {issues.isPending && <p role="status">正在读取已完成范围的诊断…</p>}
            <ErrorBox
              error={issues.error}
              onRetry={() => void issues.refetch()}
            />
            {issues.data?.items.map((issue) => (
              <IssueCard
                projectId={projectId}
                connected={connected}
                key={issue.id}
                issue={issue}
                onEvidence={onEvidence}
                onGraphNode={onGraphNode}
                onWikiPage={onWikiPage}
              />
            ))}
            {issues.data && !issues.data.items.length && (
              <p className="quiet-note">当前范围和筛选下没有诊断问题。</p>
            )}
          </>
        ) : (
          <p className="quiet-note">先执行检查，或从下方历史报告中选择。</p>
        )}
      </section>
      <section className="p5-panel">
        <h3>语义辅助检查</h3>
        <PersonalSources
          projectId={projectId}
          connected={connected}
          enabled={run?.scope.include_personal ?? false}
          value={personalSources}
          onChange={setPersonalSources}
          onEvidence={onEvidence}
        />
        <label className="field">
          检查关注点
          <textarea
            aria-label="语义检查关注点"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={3}
          />
        </label>
        <ModelWorkflow
          key={`lint-${runId}`}
          projectId={projectId}
          connected={connected}
          enabled={!!run && question.trim().length > 0}
          requestBody={{
            kind: "lint_semantic",
            lint_run_id: runId,
            personal_sources: run?.scope.include_personal
              ? personalSources
              : emptyPersonalSelection(),
            query: {
              project_id: projectId,
              question: question.trim(),
              paper_ids: run?.scope.paper_ids ?? paperIds,
              include_personal: run?.scope.include_personal ?? personal,
              purpose: "model",
              limit: 20,
            },
          }}
          actionLabel="运行语义辅助检查"
          onEvidence={onEvidence}
          onGraphNode={onGraphNode}
        />
      </section>
      <section className="p5-panel">
        <h3>检查报告历史</h3>
        <Pagination
          name="检查报告"
          total={reports.data?.total ?? 0}
          page={reportsPage}
          onChange={setReportsPage}
        />
        <ErrorBox
          error={reports.error}
          onRetry={() => void reports.refetch()}
        />
        {reports.isPending && <p role="status">正在读取检查报告…</p>}
        {reports.data?.items.map((item) => (
          <button
            type="button"
            className={`p5-list-row${item.id === runId ? " selected" : ""}`}
            disabled={scan.isPending}
            key={item.id}
            onClick={() => {
              setRunId(item.id);
              setPersonalSources(emptyPersonalSelection());
              setIssuePage(1);
            }}
          >
            <strong>{new Date(item.created_at).toLocaleString("zh-CN")}</strong>
            <span>
              {label(item.status)} · {item.processed}/{item.total} 对象 · 错误{" "}
              {item.counts.error} / 警告 {item.counts.warning}
            </span>
          </button>
        ))}
      </section>
    </>
  );
}

function IssueCard({
  projectId,
  connected,
  issue,
  onEvidence,
  onGraphNode,
  onWikiPage,
}: Navigation & {
  projectId: string;
  connected: boolean;
  issue: LintIssue;
  onEvidence: (id: string) => void;
}) {
  const evidenceId =
    field(issue.location, "evidence_id") ||
    (issue.object_type === "evidence" ? issue.object_id : "");
  const nodeId =
    field(issue.location, "node_id") ||
    (["node", "knowledge"].includes(issue.object_type) ? issue.object_id : "");
  const wikiId = field(issue.location, "page_id");
  const repairPlan = issueRepairPlan(issue);
  return (
    <article className="p5-issue">
      <div className="p5-heading">
        <strong>{issue.message}</strong>
        <span className={`p5-tag ${issue.severity}`}>
          {label(issue.severity)} · {label(issue.lifecycle)}
        </span>
      </div>
      <p className="quiet-note">
        {label(issue.category)} ·{" "}
        {issue.deterministic ? "规则诊断" : "模型建议"} · {issue.code}
      </p>
      <p>{issue.suggestion}</p>
      {typeof issue.location.page_index === "number" && (
        <small>PDF 第 {issue.location.page_index + 1} 页</small>
      )}
      <section className="p5-repair-plan" aria-label="Lint 修复或处理方案">
        <div className="p5-heading">
          <strong>修复 / 处理方案</strong>
          <span className={`p5-tag ${repairPlan.status}`}>
            {repairStatusLabels[repairPlan.status]}
          </span>
        </div>
        <p>{repairPlan.summary}</p>
        <ol className="p5-repair-steps">
          {repairPlan.steps.map((step) => (
            <li key={step.id}>
              <strong>{step.title}</strong>
              <p>{step.description}</p>
              <small>
                {step.automated ? "可由系统执行" : "需要用户确认"}
                {" · "}
                {repairModelRequirement(step.requires_model)}
              </small>
            </li>
          ))}
        </ol>
        {repairPlan.safeguards.length > 0 && (
          <p className="p5-repair-safeguards">
            <strong>保护边界：</strong>
            {repairPlan.safeguards.join(" ")}
          </p>
        )}
      </section>
      <div className="p5-actions">
        {evidenceId && (
          <button
            type="button"
            className="text-button"
            onClick={() => onEvidence(evidenceId)}
          >
            查看原文证据
          </button>
        )}
        {nodeId && (
          <button
            type="button"
            className="text-button"
            onClick={() => onGraphNode(nodeId)}
          >
            在知识图谱中定位
          </button>
        )}
        {wikiId && onWikiPage && (
          <button
            type="button"
            className="text-button"
            onClick={() => onWikiPage(wikiId)}
          >
            查看关联 Wiki
          </button>
        )}
      </div>
      <IssueDependencies
        projectId={projectId}
        connected={connected}
        issue={issue}
        onGraphNode={onGraphNode}
        onWikiPage={onWikiPage}
      />
    </article>
  );
}

function IssueDependencies({
  projectId,
  connected,
  issue,
  onGraphNode,
  onWikiPage,
}: Navigation & { projectId: string; connected: boolean; issue: LintIssue }) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [direction, setDirection] = useState<"dependents" | "dependencies">(
    "dependents",
  );
  const edges = useQuery({
    queryKey: [
      "lint-dependencies",
      projectId,
      issue.object_type,
      issue.object_id,
      direction,
      page,
    ],
    queryFn: () =>
      p5Api.lintDependencies(
        projectId,
        issue.object_type,
        issue.object_id,
        page,
        direction,
      ),
    enabled: connected && open,
    retry: false,
  });
  return (
    <details
      className="p5-disclosure"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>查看依赖与影响范围</summary>
      <label className="field">
        依赖方向
        <select
          aria-label="诊断依赖方向"
          value={direction}
          onChange={(event) => {
            setDirection(event.target.value as typeof direction);
            setPage(1);
          }}
        >
          <option value="dependents">受此对象影响的内容</option>
          <option value="dependencies">此对象依赖的来源</option>
        </select>
      </label>
      <Pagination
        name="诊断依赖"
        page={page}
        total={edges.data?.total ?? 0}
        onChange={setPage}
      />
      <ErrorBox error={edges.error} onRetry={() => void edges.refetch()} />
      {edges.isPending && open && <p role="status">正在读取依赖…</p>}
      {edges.data?.items.map((edge) => {
        const type =
          direction === "dependents" ? edge.dependent_type : edge.source_type;
        const id =
          direction === "dependents" ? edge.dependent_id : edge.source_id;
        return (
          <div className="p5-reference" key={edge.id}>
            <p>
              {label(type)} · {label(edge.category)} · {label(edge.state)}
            </p>
            {type === "node" && (
              <button
                type="button"
                className="text-button"
                onClick={() => onGraphNode(id)}
              >
                定位关联知识
              </button>
            )}
            {type === "document" && onWikiPage && (
              <button
                type="button"
                className="text-button"
                onClick={() => onWikiPage(id)}
              >
                查看关联文档
              </button>
            )}
          </div>
        );
      })}
      {edges.data && !edges.data.items.length && (
        <p className="quiet-note">此方向暂无已登记依赖。</p>
      )}
    </details>
  );
}

function WikiWorkspace({
  projectId,
  connected,
  papers,
  onEvidence,
  onGraphNode,
  initialPageId,
}: WorkProps & { initialPageId: string }) {
  const client = useQueryClient();
  const operationKey = useOperationKey();
  const [topic, setTopic] = useState("");
  const [scope, setScope] = useState("论文阅读");
  const [paperIds, setPaperIds] = useState<string[]>([]);
  const [personal, setPersonal] = useState(false);
  const [personalSources, setPersonalSources] = useState(
    emptyPersonalSelection,
  );
  const [pageId, setPageId] = useRememberedId(
    `rgs.wiki.active.${projectId}`,
    initialPageId,
  );
  const [pageNumber, setPageNumber] = useState(1);
  const [versionId, setVersionId] = useState("");
  const [versionPage, setVersionPage] = useState(1);
  const [publicationPage, setPublicationPage] = useState(1);
  const [rootId, setRootId] = useState("");
  const [affected, setAffected] = useState<string[]>([]);
  const [updateQuestion, setUpdateQuestion] = useState(
    "仅更新所选段落，保留未受影响段落；无法确认的内容标出限制。",
  );
  const [publication, setPublication] = useState<Awaited<
    ReturnType<typeof p5Api.wikiPublish>
  > | null>(null);
  const pages = useQuery({
    queryKey: ["wiki-pages", projectId, pageNumber, personal],
    queryFn: () => p5Api.wikiPages(projectId, pageNumber, personal),
    enabled: connected,
    retry: false,
  });
  const page = useQuery({
    queryKey: ["wiki-page", projectId, pageId, versionId, personal],
    queryFn: () => p5Api.wikiPage(projectId, pageId, versionId, personal),
    enabled: connected && !!pageId,
    retry: false,
  });
  const roots = useQuery({
    queryKey: ["wiki-roots", projectId],
    queryFn: () => p5Api.wikiRoots(projectId),
    enabled: connected,
    retry: false,
  });
  const publications = useQuery({
    queryKey: ["wiki-publications", projectId, pageId, publicationPage],
    queryFn: () => p5Api.wikiPublications(projectId, pageId, publicationPage),
    enabled: connected && !!pageId,
    retry: false,
  });
  const value = page.error ? undefined : page.data;
  const currentSummary = pages.data?.items.find(
    (item) => item.page_id === pageId,
  );
  const selectedRoot = roots.data?.items.find(
    (item) => item.root_id === rootId && item.active,
  );
  const choosePage = (id: string) => {
    setPageId(id);
    setVersionId("");
    setVersionPage(1);
    setAffected([]);
    setPublication(null);
    setPublicationPage(1);
  };
  const materialized = (result: WikiPageView) => {
    choosePage(result.page_id);
    void client.invalidateQueries({
      queryKey: ["wiki-page", projectId, result.page_id],
    });
    void client.invalidateQueries({ queryKey: ["wiki-pages", projectId] });
  };
  const save = useMutation({
    mutationFn: () => {
      if (!value) throw new Error("请先读取整理草稿");
      if (!value.head_version_id)
        throw new Error("页面基线尚未读取，请刷新后保存");
      const body = {
        version_id: value.version_id,
        expected_head_version_id: value.head_version_id,
        expected_content_hash: value.content_hash,
      };
      return p5Api.wikiSave(
        projectId,
        value.page_id,
        body,
        operationKey("wiki-save", [value.page_id, body]),
      );
    },
    onSuccess: (result) => {
      void client.invalidateQueries({
        queryKey: ["wiki-page", projectId, result.page_id],
      });
      void client.invalidateQueries({ queryKey: ["wiki-pages", projectId] });
      void client.invalidateQueries({
        queryKey: ["wiki-publications", projectId],
      });
    },
  });
  const authorize = useMutation({
    mutationFn: () => p5Api.authorizeOutput(projectId),
    onSuccess: (root) => {
      if (root) setRootId(root.root_id);
      void client.invalidateQueries({ queryKey: ["wiki-roots", projectId] });
    },
  });
  const revoke = useMutation({
    mutationFn: () =>
      p5Api.revokeOutput(
        projectId,
        rootId,
        operationKey("wiki-revoke", rootId),
      ),
    onSuccess: () => {
      setRootId("");
      void client.invalidateQueries({ queryKey: ["wiki-roots", projectId] });
    },
  });
  const publish = useMutation({
    mutationFn: () => {
      if (!value || !selectedRoot)
        throw new Error("请选择已授权目录和已保存版本");
      const body = {
        root_id: selectedRoot.root_id,
        version_id: value.version_id,
        expected_content_hash: value.content_hash,
        expected_target_hash:
          field(value.file, "root_id") === selectedRoot.root_id
            ? field(value.file, "sha256") || null
            : null,
      };
      return p5Api.wikiPublish(
        projectId,
        value.page_id,
        body,
        operationKey("wiki-publish", [value.page_id, body]),
      );
    },
    onSuccess: (result) => {
      setPublication(result);
      void client.invalidateQueries({
        queryKey: ["wiki-publications", projectId],
      });
      void client.invalidateQueries({
        queryKey: ["wiki-page", projectId, pageId],
      });
      void client.invalidateQueries({ queryKey: ["wiki-pages", projectId] });
    },
  });
  const recover = useMutation({
    mutationFn: () => {
      if (!publication) throw new Error("没有待恢复的导出操作");
      return p5Api.wikiRecover(
        projectId,
        publication.operation_id,
        operationKey("wiki-recover", publication.operation_id),
      );
    },
    onSuccess: (result) => {
      setPublication(result);
      void client.invalidateQueries({
        queryKey: ["wiki-page", projectId, pageId],
      });
      void client.invalidateQueries({
        queryKey: ["wiki-publications", projectId],
      });
    },
  });
  const inspect = useMutation({
    mutationFn: (id: string) =>
      p5Api.inspectWikiFile(
        projectId,
        id,
        operationKey("wiki-inspect", [id, field(value?.file, "current_hash")]),
      ),
  });
  const fileState =
    field(value?.file, "state") || currentSummary?.file_state || "not_exported";
  const fileBlocked =
    ["modified", "external_modified", "unavailable", "conflict"].includes(
      fileState,
    ) &&
    (!rootId || field(value?.file, "root_id") === rootId);
  const historical = !!versionId;
  const stale =
    value?.sections.some((section) => section.stale) ||
    (!!value &&
      field(value, "content_state") !== "" &&
      field(value, "content_state") !== "valid");
  const pageItems = pages.data?.items ?? [];
  const versions = value?.versions ?? [];
  const diff =
    typeof value?.diff === "string"
      ? value.diff
      : field(value?.diff, "unified") || field(value?.diff, "markdown") || "";
  return (
    <>
      <section className="p5-panel">
        <h3>生成阅读整理</h3>
        <div className="p5-form-grid">
          <label className="field">
            整理类型
            <select
              aria-label="整理类型"
              value={scope}
              onChange={(event) => setScope(event.target.value)}
            >
              <option>论文阅读</option>
              <option>方法梳理</option>
              <option>跨论文比较</option>
            </select>
          </label>
          <label className="field">
            主题或问题
            <input
              aria-label="Wiki 主题或问题"
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              placeholder="例如：这些方法的适用条件与局限是什么？"
            />
          </label>
        </div>
        <PaperScope
          papers={papers}
          value={paperIds}
          onChange={setPaperIds}
          name="整理论文范围"
        />
        <label className="p5-check">
          <input
            type="checkbox"
            checked={personal}
            onChange={(event) => {
              setPersonal(event.target.checked);
              setPersonalSources(emptyPersonalSelection());
            }}
          />
          包含已独立授权的个人笔记、批注评论与外部资料
        </label>
        <PersonalSources
          projectId={projectId}
          connected={connected}
          enabled={personal}
          value={personalSources}
          onChange={setPersonalSources}
          onEvidence={onEvidence}
        />
        <ModelWorkflow
          projectId={projectId}
          connected={connected}
          enabled={topic.trim().length > 0}
          requestBody={{
            kind: "wiki_synthesis",
            personal_sources: personalSources,
            query: {
              project_id: projectId,
              question: `${scope}：${topic.trim()}`,
              paper_ids: paperIds,
              include_personal: personal,
              purpose: "model",
              limit: 20,
            },
          }}
          actionLabel="生成有据整理"
          onMaterialize={materialized}
          onEvidence={onEvidence}
          onGraphNode={onGraphNode}
        />
      </section>
      <section className="p5-panel">
        <h3>受管 Wiki 页面</h3>
        <Pagination
          name="Wiki 页面"
          page={pageNumber}
          total={pages.data?.total ?? 0}
          onChange={setPageNumber}
        />
        <ErrorBox error={pages.error} onRetry={() => void pages.refetch()} />
        {pages.isPending && <p role="status">正在读取 Wiki 页面…</p>}
        {pageItems.map((item) => (
          <button
            type="button"
            key={item.page_id}
            className={`p5-list-row${item.page_id === pageId ? " selected" : ""}`}
            onClick={() => choosePage(item.page_id)}
          >
            <strong>{item.title}</strong>
            <span>
              {label(item.file_state)}
              {item.head_version_id !== item.saved_version_id
                ? " · 有未保存草稿"
                : ""}
            </span>
          </button>
        ))}
        {pages.data && !pageItems.length && (
          <p className="quiet-note">
            暂无受管页面。上方生成结果后，可明确建立内部整理草稿。
          </p>
        )}
      </section>
      {pageId && (
        <section className="p5-panel">
          <div className="p5-heading">
            <h3>{value?.title ?? "整理内容"}</h3>
            <button
              type="button"
              className="text-button"
              onClick={() => void page.refetch()}
            >
              重新核验来源与文件状态
            </button>
          </div>
          {page.isPending && <p role="status">正在读取段落、引用与版本…</p>}
          <ErrorBox error={page.error} onRetry={() => void page.refetch()} />
          {value && (
            <>
              <p className="quiet-note">
                版本 {value.revision} · {label(value.state)} ·{" "}
                {label(fileState)}
                {historical ? " · 当前查看历史版本，只读" : ""}
              </p>
              {stale && (
                <p role="status" className="p5-warning">
                  部分段落依赖已失效，保留历史内容；更新并重新核验前不能直接导出陈旧内容。
                </p>
              )}
              <PassageCards
                name="Wiki 段落"
                passages={value.sections}
                onEvidence={onEvidence}
                onGraphNode={onGraphNode}
                selected={affected}
                onSelect={setAffected}
              />
              <details className="p5-disclosure">
                <summary>Markdown 预览</summary>
                <pre className="p5-markdown">{value.markdown}</pre>
              </details>
              <details className="p5-disclosure">
                <summary>与当前基线的差异</summary>
                <pre className="p5-diff">
                  {diff || "当前版本没有可展示的文本差异。"}
                </pre>
              </details>
              <div className="p5-actions">
                <button
                  type="button"
                  className="button primary"
                  disabled={
                    !connected ||
                    historical ||
                    value.state !== "draft" ||
                    stale ||
                    save.isPending
                  }
                  onClick={() => save.mutate()}
                >
                  保存内部版本
                </button>
                <span className="quiet-note">
                  保存内部版本不会写入 Markdown 文件。
                </span>
              </div>
              <ErrorBox error={save.error} />
              {save.isSuccess && <p role="status">内部版本已保存。</p>}
              <details className="p5-disclosure">
                <summary>版本历史</summary>
                <Pagination
                  name="Wiki 版本历史"
                  page={versionPage}
                  total={versions.length}
                  onChange={setVersionPage}
                />
                <button
                  type="button"
                  className="text-button"
                  onClick={() => setVersionId("")}
                >
                  返回当前草稿或版本
                </button>
                {versions
                  .slice((versionPage - 1) * 10, versionPage * 10)
                  .map((version) => (
                    <button
                      key={version.version_id}
                      type="button"
                      className="p5-list-row"
                      onClick={() => {
                        setVersionId(version.version_id);
                        setAffected([]);
                      }}
                    >
                      <strong>版本 {version.revision}</strong>
                      <span>{label(version.state)}</span>
                    </button>
                  ))}
              </details>
            </>
          )}
        </section>
      )}
      {value && (
        <section className="p5-panel">
          <h3>更新受影响段落</h3>
          <p className="quiet-note">
            在上方勾选需要更新的段落。生成建议不会直接切换内部版本或覆盖文件。
          </p>
          <label className="field">
            更新关注点
            <textarea
              aria-label="Wiki 更新关注点"
              value={updateQuestion}
              onChange={(event) => setUpdateQuestion(event.target.value)}
              rows={3}
            />
          </label>
          <ModelWorkflow
            key={`delta-${value.page_id}-${value.version_id}`}
            projectId={projectId}
            connected={connected}
            enabled={
              !historical && affected.length > 0 && !!updateQuestion.trim()
            }
            requestBody={{
              kind: "wiki_delta",
              page_id: value.page_id,
              base_version_id: value.version_id,
              affected_section_ids: affected,
              personal_sources: personalSources,
              query: {
                project_id: projectId,
                question: updateQuestion.trim(),
                paper_ids: paperIds,
                include_personal: personal,
                purpose: "model",
                limit: 20,
              },
            }}
            actionLabel="生成局部更新建议"
            onMaterialize={materialized}
            onEvidence={onEvidence}
            onGraphNode={onGraphNode}
          />
        </section>
      )}
      <ExternalLibrary projectId={projectId} connected={connected} />
      <section className="p5-panel">
        <h3>授权目录与 Markdown 导出</h3>
        <div className="p5-actions">
          <button
            type="button"
            className="button secondary"
            disabled={!connected || authorize.isPending}
            onClick={() => authorize.mutate()}
          >
            选择并授权独立导出目录
          </button>
          <span className="quiet-note">
            仅写入受管页面；原始私人笔记不被覆盖。
          </span>
        </div>
        <ErrorBox error={roots.error} onRetry={() => void roots.refetch()} />
        <ErrorBox error={authorize.error || revoke.error} />
        <label className="field">
          导出目录
          <select
            aria-label="Wiki 导出目录"
            value={rootId}
            onChange={(event) => {
              setRootId(event.target.value);
              setPublication(null);
            }}
          >
            <option value="">请选择已授权目录</option>
            {roots.data?.items
              .filter((root) => root.active)
              .map((root) => (
                <option value={root.root_id} key={root.root_id}>
                  {root.path}
                </option>
              ))}
          </select>
        </label>
        <div className="p5-actions">
          <button
            type="button"
            className="button primary"
            disabled={
              !connected ||
              !selectedRoot ||
              !value ||
              historical ||
              value.state === "draft" ||
              stale ||
              fileBlocked ||
              publish.isPending
            }
            onClick={() => publish.mutate()}
          >
            {currentSummary?.published_version_id
              ? "更新导出 Markdown"
              : "导出 Markdown"}
          </button>
          <button
            type="button"
            className="text-button"
            disabled={!selectedRoot || revoke.isPending}
            onClick={() => revoke.mutate()}
          >
            撤销所选目录写入授权
          </button>
        </div>
        {fileBlocked && (
          <p className="p5-warning" role="status">
            当前导出文件已被外部修改或无法安全核验。请保留原文件，选择新的授权目录，或先恢复文件访问再重新核验。
          </p>
        )}
        {fileState === "modified" && value && (
          <div className="p5-actions">
            <button
              type="button"
              className="button secondary"
              disabled={!connected || inspect.isPending}
              onClick={() => inspect.mutate(value.page_id)}
            >
              只读查看外部修改与差异
            </button>
            <span className="quiet-note">
              外部文本单独标记为用户修改，不继承原版本的证据归属。
            </span>
          </div>
        )}
        <ErrorBox error={inspect.error} />
        {inspect.data && inspect.variables === pageId && (
          <details className="p5-disclosure">
            <summary>外部修改快照与差异 · 未验证来源</summary>
            <pre className="p5-markdown">{inspect.data.text}</pre>
            <pre className="p5-diff">{inspect.data.diff || "无文本差异"}</pre>
          </details>
        )}
        <ErrorBox error={publish.error || recover.error} />
        {publication && (
          <div role="status" className="p5-run-status">
            <strong>导出状态：{label(publication.state)}</strong>
            {publication.error && (
              <p className="error-text">{publication.error}</p>
            )}
            {!["completed", "succeeded", "confirmed", "published"].includes(
              publication.state,
            ) && (
              <button
                type="button"
                className="button secondary"
                disabled={!connected || recover.isPending}
                onClick={() => recover.mutate()}
              >
                核对并恢复这次导出
              </button>
            )}
          </div>
        )}
        {pageId && (
          <details className="p5-disclosure">
            <summary>导出操作记录与中断恢复</summary>
            <Pagination
              name="导出操作"
              page={publicationPage}
              total={publications.data?.total ?? 0}
              onChange={setPublicationPage}
            />
            <ErrorBox
              error={publications.error}
              onRetry={() => void publications.refetch()}
            />
            {publications.data?.items.map((item, index) => (
              <button
                type="button"
                className="p5-list-row"
                key={item.operation_id}
                onClick={() => setPublication(item)}
              >
                <strong>
                  导出操作 {(publicationPage - 1) * 10 + index + 1} ·{" "}
                  {label(item.state)}
                </strong>
                <span>
                  {item.error || "查看状态，或明确核对并恢复中断的导出"}
                </span>
              </button>
            ))}
          </details>
        )}
      </section>
    </>
  );
}

function ModelWorkflow({
  projectId,
  connected,
  enabled,
  requestBody,
  actionLabel,
  onMaterialize,
  onEvidence,
  onGraphNode,
}: {
  projectId: string;
  connected: boolean;
  enabled: boolean;
  requestBody: WorkflowRequest;
  actionLabel: string;
  onMaterialize?: (page: WikiPageView) => void;
  onEvidence: (id: string) => void;
  onGraphNode: (id: string) => void;
}) {
  const client = useQueryClient();
  const operationKey = useOperationKey();
  const storageKey = `rgs.workflow.${projectId}.${requestBody.kind}.${requestBody.lint_run_id ?? requestBody.base_version_id ?? ""}`;
  const [id, setId] = useRememberedId(storageKey);
  const requestSignature = JSON.stringify(requestBody);
  const [consent, setConsent] = useState({
    signature: requestSignature,
    allowed: false,
  });
  if (consent.signature !== requestSignature)
    setConsent({ signature: requestSignature, allowed: false });
  const allowNetwork =
    consent.signature === requestSignature && consent.allowed;
  const [historyPage, setHistoryPage] = useState(1);
  const [suggestionPage, setSuggestionPage] = useState(1);
  const [operationPage, setOperationPage] = useState(1);
  const [runPage, setRunPage] = useState(1);
  const history = useQuery({
    queryKey: ["p5-workflows", projectId],
    queryFn: () => p5Api.workflows(projectId),
    enabled: connected,
    retry: false,
  });
  const current = useQuery({
    queryKey: ["p5-workflow", projectId, id],
    queryFn: () => p5Api.workflow(projectId, id),
    enabled: connected && !!id,
    retry: false,
    refetchInterval: (query) =>
      active(query.state.data?.status ?? "") ? 1500 : false,
  });
  const value = current.error ? undefined : current.data;
  const workflowStatus = value?.status;
  const workflowId = value?.id;
  useEffect(() => {
    if (workflowId && workflowStatus && !active(workflowStatus))
      void client.invalidateQueries({ queryKey: ["p5-workflows", projectId] });
  }, [workflowStatus, workflowId, client, projectId]);
  const generate = useMutation({
    mutationFn: async () => {
      if (!allowNetwork) throw new Error("请先确认本次模型传输");
      const prepared = await p5Api.prepare(
        projectId,
        requestBody,
        operationKey("workflow-prepare", requestBody),
      );
      setId(prepared.id);
      setSuggestionPage(1);
      client.setQueryData(["p5-workflow", projectId, prepared.id], prepared);
      if (prepared.status !== "prepared") return;
      const job = await p5Api.generate(
        projectId,
        prepared.id,
        false,
        operationKey("workflow-generate", prepared.id),
      );
      client.setQueryData(["p5-workflow", projectId, prepared.id], {
        ...prepared,
        status: job.status,
        job_id: job.id,
      });
      void client.invalidateQueries({
        queryKey: ["p5-workflow", projectId, prepared.id],
      });
      void client.invalidateQueries({ queryKey: ["p5-workflows", projectId] });
    },
  });
  const continuation = useMutation({
    mutationFn: async () => {
      if (!value || !allowNetwork)
        throw new Error("请确认本次模型传输后再继续");
      await p5Api.generate(
        projectId,
        value.id,
        value.status !== "prepared",
        operationKey("workflow-continue", [
          value.id,
          value.model_runs.length,
          value.status,
        ]),
      );
      void client.invalidateQueries({
        queryKey: ["p5-workflow", projectId, id],
      });
    },
  });
  const cancel = useMutation({
    mutationFn: async () => {
      if (!value?.job_id) throw new Error("当前没有可取消的模型任务");
      await api.jobAction(
        value.job_id,
        "cancel",
        operationKey("workflow-cancel", value.job_id),
      );
      void client.invalidateQueries({
        queryKey: ["p5-workflow", projectId, id],
      });
    },
  });
  const materialize = useMutation({
    mutationFn: () =>
      p5Api.materialize(
        projectId,
        id,
        operationKey("workflow-materialize", id),
      ),
    onSuccess: onMaterialize,
  });
  const busy =
    generate.isPending ||
    continuation.isPending ||
    (!!value && active(value.status));
  const records =
    history.data?.items.filter((item) => item.kind === requestBody.kind) ?? [];
  const suggestions = value?.result?.suggestions ?? [];
  const operations = value?.result?.patch?.operations ?? [];
  const runs = value?.model_runs ?? [];
  return (
    <div className="p5-model-workflow">
      <label className="p5-check">
        <input
          type="checkbox"
          aria-label={`允许本次${label(requestBody.kind)}发送必要来源给模型`}
          checked={allowNetwork}
          onChange={(event) =>
            setConsent({
              signature: requestSignature,
              allowed: event.target.checked,
            })
          }
        />
        允许本次将问题和必要来源发送给全局 Reasoning 模型
      </label>
      <div className="p5-actions">
        <button
          type="button"
          className="button primary"
          disabled={!connected || !enabled || !allowNetwork || busy}
          onClick={() => generate.mutate()}
        >
          {busy ? <LoaderCircle className="spin" size={16} /> : null}
          {actionLabel}
        </button>
        {value &&
          (value.can_continue || value.status === "prepared") &&
          !active(value.status) && (
            <button
              type="button"
              className="button secondary"
              disabled={!connected || !allowNetwork || continuation.isPending}
              onClick={() => continuation.mutate()}
            >
              {value.status === "prepared"
                ? "启动已准备任务"
                : "明确继续未完成生成"}
            </button>
          )}
        {value?.job_id && active(value.status) && (
          <button
            type="button"
            className="button secondary"
            disabled={!connected || cancel.isPending}
            onClick={() => cancel.mutate()}
          >
            取消模型任务
          </button>
        )}
      </div>
      <ErrorBox
        error={
          generate.error ||
          continuation.error ||
          cancel.error ||
          materialize.error
        }
      />
      {id && (
        <div className="p5-workflow-result">
          <div className="p5-heading">
            <strong>{value ? label(value.status) : "正在读取任务状态"}</strong>
            <button
              type="button"
              className="text-button"
              onClick={() => void current.refetch()}
            >
              重新读取任务
            </button>
          </div>
          <ErrorBox
            error={current.error}
            onRetry={() => void current.refetch()}
          />
          {value && (
            <>
              {value.question && (
                <p className="p5-question">{value.question}</p>
              )}
              {active(value.status) && (
                <p role="status">
                  正在等待模型返回并核验来源；切换页面不会重新发送请求。
                </p>
              )}
              {value.error && (
                <p role="alert" className="error-text">
                  {value.error}
                  {value.error_code ? `（${value.error_code}）` : ""}
                </p>
              )}
              {value.status === "insufficient" && (
                <p className="quiet-note">
                  当前来源不足，没有发送模型请求。请调整主题或选择有据论文。
                </p>
              )}
              {value.result?.draft && (
                <>
                  <h4>{value.result.draft.title}</h4>
                  <PassageCards
                    name="生成草稿段落"
                    passages={value.result.draft.passages}
                    onEvidence={onEvidence}
                    onGraphNode={onGraphNode}
                  />
                </>
              )}
              {!!suggestions.length && (
                <>
                  <p className="p5-warning">
                    下列内容为模型建议，不会自动改写知识或执行建议操作。
                  </p>
                  <Pagination
                    name="语义建议"
                    page={suggestionPage}
                    total={suggestions.length}
                    onChange={setSuggestionPage}
                  />
                  {suggestions
                    .slice((suggestionPage - 1) * 10, suggestionPage * 10)
                    .map((item, index) => (
                      <article
                        className="p5-issue"
                        key={`${item.code}-${index}`}
                      >
                        <strong>{item.rationale}</strong>
                        <p className="quiet-note">
                          {label(item.severity)} · {item.code}
                        </p>
                        <p>{item.suggested_action}</p>
                        <p>不确定性：{item.uncertainty}</p>
                        <DependencyList
                          dependencies={item.evidence_dependencies ?? []}
                          onEvidence={onEvidence}
                          onGraphNode={onGraphNode}
                        />
                        {!item.evidence_dependencies && (
                          <p className="quiet-note">
                            此历史建议未包含可定位的来源类型，请在原诊断中核对依据。
                          </p>
                        )}
                      </article>
                    ))}
                </>
              )}
              {!!operations.length && (
                <>
                  <h4>局部更新提案</h4>
                  <Pagination
                    name="更新提案"
                    page={operationPage}
                    total={operations.length}
                    onChange={setOperationPage}
                  />
                  {operations
                    .slice((operationPage - 1) * 10, operationPage * 10)
                    .map((operation, index) => (
                      <article className="p5-passage" key={index}>
                        <strong>
                          {label(
                            field(operation, "op") ||
                              field(operation, "type") ||
                              "段落更新",
                          )}
                        </strong>
                        <p>
                          {field(operation, "text") ||
                            field(operation, "reason") ||
                            field(operation, "heading") ||
                            "变更范围已绑定当前段落，建立更新预览后查看完整差异。"}
                        </p>
                      </article>
                    ))}
                </>
              )}
              {!!value.result?.coverage_gaps?.length && (
                <details className="p5-disclosure">
                  <summary>来源覆盖与保留限制</summary>
                  {value.result.coverage_gaps.map((gap, index) => (
                    <p key={index}>{gap}</p>
                  ))}
                </details>
              )}
              {!!value.result?.limitations?.length && (
                <details className="p5-disclosure">
                  <summary>语义检查限制</summary>
                  {value.result.limitations.map((limitation, index) => (
                    <p key={index}>{limitation}</p>
                  ))}
                </details>
              )}
              {onMaterialize &&
                value.status === "succeeded" &&
                (value.result?.draft || value.result?.patch) && (
                  <div className="p5-actions">
                    <button
                      type="button"
                      className="button secondary"
                      disabled={materialize.isPending || !connected}
                      onClick={() => materialize.mutate()}
                    >
                      {value.result.patch
                        ? "建立局部更新预览"
                        : "创建内部整理草稿"}
                    </button>
                    <span className="quiet-note">
                      建立草稿后仍需明确保存内部版本；不会写文件。
                    </span>
                  </div>
                )}
              <details className="p5-disclosure">
                <summary>模型调用记录 · {runs.length} 次</summary>
                <Pagination
                  name="模型调用"
                  page={runPage}
                  total={runs.length}
                  onChange={setRunPage}
                />
                {runs
                  .slice((runPage - 1) * 10, runPage * 10)
                  .map((run, index) => (
                    <article key={run.id}>
                      <strong>
                        第 {(runPage - 1) * 10 + index + 1} 次 ·{" "}
                        {label(run.status)}
                      </strong>
                      <p>
                        Token {run.usage.total_tokens ?? "供应商未提供"} ·{" "}
                        {run.duration_seconds === null
                          ? "耗时未提供"
                          : `${run.duration_seconds.toFixed(1)} 秒`}{" "}
                        ·{" "}
                        {run.cost_known
                          ? "费用见供应商记录"
                          : "供应商未提供金额"}
                      </p>
                      {run.error && <p className="error-text">{run.error}</p>}
                    </article>
                  ))}
              </details>
            </>
          )}
        </div>
      )}
      <details className="p5-disclosure">
        <summary>{label(requestBody.kind)}历史</summary>
        <Pagination
          name={`${label(requestBody.kind)}历史`}
          page={historyPage}
          total={records.length}
          onChange={setHistoryPage}
        />
        <ErrorBox
          error={history.error}
          onRetry={() => void history.refetch()}
        />
        {records.slice((historyPage - 1) * 10, historyPage * 10).map((item) => (
          <button
            type="button"
            className="p5-list-row"
            key={item.id}
            onClick={() => {
              setId(item.id);
              setConsent({ signature: requestSignature, allowed: false });
            }}
          >
            <strong>{item.question || label(item.kind)}</strong>
            <span>
              {label(item.status)}
              {item.created_at
                ? ` · ${new Date(item.created_at).toLocaleString("zh-CN")}`
                : ""}
            </span>
          </button>
        ))}
      </details>
    </div>
  );
}

function PassageCards({
  name,
  passages,
  onEvidence,
  onGraphNode,
  selected,
  onSelect,
}: {
  name: string;
  passages: (WikiPassage & { section_id?: string; stale?: boolean })[];
  onEvidence: (id: string) => void;
  onGraphNode: (id: string) => void;
  selected?: string[];
  onSelect?: (ids: string[]) => void;
}) {
  const [page, setPage] = useState(1);
  const current = Math.min(page, Math.max(1, Math.ceil(passages.length / 10)));
  return (
    <div>
      <Pagination
        name={name}
        page={current}
        total={passages.length}
        onChange={setPage}
      />
      {passages
        .slice((current - 1) * 10, current * 10)
        .map((passage, index) => (
          <article className="p5-passage" key={passage.section_id ?? index}>
            <div className="p5-heading">
              <h4>
                {passage.heading || `段落 ${(current - 1) * 10 + index + 1}`}
              </h4>
              <span className="p5-tag">
                {label(passage.attribution)}
                {passage.stale ? " · 依赖已失效" : ""}
              </span>
            </div>
            {passage.section_id && onSelect && (
              <label className="p5-check">
                <input
                  type="checkbox"
                  aria-label={`更新段落 · ${passage.heading}`}
                  checked={selected?.includes(passage.section_id) ?? false}
                  onChange={(event) =>
                    onSelect(
                      event.target.checked
                        ? [...(selected ?? []), passage.section_id!]
                        : (selected ?? []).filter(
                            (id) => id !== passage.section_id,
                          ),
                    )
                  }
                />
                选入局部更新范围
              </label>
            )}
            <p className="p5-passage-text">{passage.text}</p>
            {passage.conditions?.length > 0 && (
              <div className="p5-table-scroll">
                <table>
                  <caption>适用条件</caption>
                  <thead>
                    <tr>
                      <th>条件</th>
                      <th>状态</th>
                      <th>值</th>
                    </tr>
                  </thead>
                  <tbody>
                    {passage.conditions.map((condition, conditionIndex) => (
                      <tr key={conditionIndex}>
                        <td>{condition.dimension}</td>
                        <td>{label(condition.state)}</td>
                        <td>
                          {condition.value ?? "未提供"}
                          {condition.unit ? ` ${condition.unit}` : ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {passage.caveats?.map((caveat, caveatIndex) => (
              <p key={caveatIndex} className="quiet-note">
                限制：{caveat}
              </p>
            ))}
            <DependencyList
              dependencies={passage.dependencies ?? []}
              onEvidence={onEvidence}
              onGraphNode={onGraphNode}
            />
          </article>
        ))}
    </div>
  );
}
function DependencyList({
  dependencies,
  onEvidence,
  onGraphNode,
}: {
  dependencies: P5Dependency[];
  onEvidence: (id: string) => void;
  onGraphNode: (id: string) => void;
}) {
  const [page, setPage] = useState(1);
  return (
    <details className="p5-disclosure">
      <summary>原文引用与依赖 · {dependencies.length} 条</summary>
      <Pagination
        name="段落引用"
        page={page}
        total={dependencies.length}
        onChange={setPage}
      />
      {dependencies
        .slice((page - 1) * 10, page * 10)
        .map((dependency, index) => (
          <details
            className="p5-reference"
            key={`${dependency.type}-${dependency.id}-${index}`}
          >
            <summary>
              来源 {(page - 1) * 10 + index + 1} · {label(dependency.type)}
            </summary>
            {dependency.quote && <blockquote>{dependency.quote}</blockquote>}
            {dependency.type === "chunk" &&
              dependency.start !== undefined &&
              dependency.end !== undefined && (
                <small>
                  原文字符区间 [{dependency.start}, {dependency.end})
                </small>
              )}
            {dependency.type === "evidence" && (
              <button
                type="button"
                className="text-button"
                onClick={() => onEvidence(dependency.id)}
              >
                查看定位原文
              </button>
            )}
            {dependency.type === "node" && (
              <button
                type="button"
                className="text-button"
                onClick={() => onGraphNode(dependency.id)}
              >
                在图谱中查看知识与支撑
              </button>
            )}
            {["note", "passage", "annotation", "external"].includes(
              dependency.type,
            ) && (
              <p className="quiet-note">
                此来源使用已登记的不可变快照，读取仍受当前授权与依赖状态限制。
              </p>
            )}
          </details>
        ))}
    </details>
  );
}
function EvidenceDialog({
  evidenceId,
  connected,
  onClose,
}: {
  evidenceId: string;
  connected: boolean;
  onClose: () => void;
}) {
  const detail = useQuery({
    queryKey: ["p5-evidence", evidenceId],
    queryFn: () => p5Api.evidence(evidenceId),
    enabled: connected,
    retry: false,
  });
  const preview = useQuery({
    queryKey: ["p5-evidence-preview", evidenceId],
    queryFn: () => api.preview(evidenceId),
    enabled: connected && detail.isSuccess,
    retry: false,
  });
  return (
    <dialog
      className="dialog p5-evidence"
      aria-label="P5 原文证据"
      ref={(node) => {
        if (node && !node.open) node.showModal();
      }}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="p5-heading">
        <h3>原文证据</h3>
        <button
          type="button"
          className="icon-button"
          aria-label="关闭 P5 原文证据"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>
      {detail.isPending && <p role="status">正在核验原文位置…</p>}
      <ErrorBox error={detail.error} onRetry={() => void detail.refetch()} />
      {detail.data && (
        <>
          <p>
            PDF 第 {detail.data.page_index + 1} 页 · 字符 [
            {detail.data.start_offset}, {detail.data.end_offset})
          </p>
          <blockquote>{detail.data.quote}</blockquote>
        </>
      )}
      {preview.data && (
        <img
          className="evidence-image"
          src={preview.data.data_url}
          alt="证据所在 PDF 区域"
        />
      )}
      {preview.error && (
        <p className="quiet-note">
          当前 PDF 预览不可用，已保存原文片段仍可核对。{message(preview.error)}
        </p>
      )}
    </dialog>
  );
}
