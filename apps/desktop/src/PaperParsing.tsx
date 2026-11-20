import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, FileSearch, HardDrive, ScanLine, Sparkles } from "lucide-react";
import { api, defaultPostImportPlan } from "./api";
import { ImportPostProcessingPlan } from "./ImportPostProcessingPlan";
import { jobStageLabel } from "./jobProgress";
import { DocumentRequestStatus } from "./DocumentRequestStatus";

export function PaperParsing({
  paperId,
  projectId,
  connected,
  hasLocal,
  hasModel,
  source,
  onViewSource,
  onQueued,
  children,
}: {
  paperId: string;
  projectId: string;
  connected: boolean;
  hasLocal: boolean;
  hasModel: boolean;
  source: "local" | "model";
  onViewSource: (mode: "local" | "model") => void;
  onQueued: (mode: "local" | "model") => void;
  children?: ReactNode;
}) {
  const client = useQueryClient();
  const dialog = useRef<HTMLDialogElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const actionsId = useId();
  const [actionsOpen, setActionsOpen] = useState(false);
  const [actionsAbove, setActionsAbove] = useState(false);
  const [open, setOpen] = useState(false);
  const closeDialog = () => {
    dialog.current?.close?.();
    setOpen(false);
  };
  const closeActions = () => {
    setActionsOpen(false);
    trigger.current?.focus();
  };
  const toggleActions = () => {
    const bounds = trigger.current?.getBoundingClientRect();
    if (bounds)
      setActionsAbove(
        window.innerHeight - bounds.bottom < 260 && bounds.top > 260,
      );
    setActionsOpen(!actionsOpen);
  };
  const [plan, setPlan] = useState(() => ({
    ...defaultPostImportPlan(),
    parse: true,
    overview: false,
  }));
  const [jobId, setJobId] = useState<string | null>(null);
  const task = useQuery({
    queryKey: ["paper-parse-job", jobId],
    queryFn: () => api.job(jobId!),
    enabled: connected && !!jobId,
    refetchInterval: (query) =>
      !query.state.data ||
      ["queued", "running"].includes(query.state.data.status)
        ? 1000
        : false,
  });
  const parsing = useMutation({
    mutationFn: (mode: "local" | "model") =>
      api.parsePaper(
        paperId,
        mode === "model" ? { mode, post_import_plan: plan } : { mode },
      ),
    onSuccess: (job, mode) => {
      setJobId(job.id);
      closeDialog();
      onQueued(mode);
      void client.invalidateQueries({ queryKey: ["jobs"] });
      void client.invalidateQueries({
        queryKey: ["paper-import-sessions", projectId],
      });
    },
  });
  useEffect(() => {
    if (open && dialog.current && !dialog.current.open)
      dialog.current.showModal();
  }, [open]);
  useEffect(() => {
    if (!actionsOpen) return;
    const dismissOutside = (event: PointerEvent) => {
      if (!menu.current?.contains(event.target as Node)) setActionsOpen(false);
    };
    document.addEventListener("pointerdown", dismissOutside, true);
    return () =>
      document.removeEventListener("pointerdown", dismissOutside, true);
  }, [actionsOpen]);
  useEffect(() => {
    if (!task.data || ["queued", "running"].includes(task.data.status)) return;
    void client.invalidateQueries({ queryKey: ["paper", paperId] });
    void client.invalidateQueries({ queryKey: ["sections"] });
    void client.invalidateQueries({ queryKey: ["reading-document"] });
    void client.invalidateQueries({
      queryKey: ["paper-import-sessions", projectId],
    });
    void client.invalidateQueries({ queryKey: ["sidebar-papers", projectId] });
  }, [task.data, client, paperId, projectId]);
  const busy =
    parsing.isPending ||
    (!!jobId &&
      !task.isError &&
      (!task.data || ["queued", "running"].includes(task.data.status)));
  return (
    <section aria-label="论文解析管理" className="paper-parsing-controls">
      <div className="paper-parsing-action-row">
        {children}
        <div
          ref={menu}
          className={`paper-parsing-menu${actionsAbove ? " opens-above" : ""}`}
          onBlur={(event) => {
            if (
              event.relatedTarget &&
              !menu.current?.contains(event.relatedTarget)
            )
              setActionsOpen(false);
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape" && actionsOpen) {
              event.stopPropagation();
              closeActions();
            }
          }}
        >
          <button
            ref={trigger}
            type="button"
            className="paper-parsing-toggle"
            aria-label="论文解析操作"
            title="论文解析操作"
            aria-expanded={actionsOpen}
            aria-controls={actionsId}
            onClick={toggleActions}
          >
            <ScanLine size={18} aria-hidden="true" />
          </button>
          <div
            id={actionsId}
            className="paper-parsing-options"
            hidden={!actionsOpen}
          >
            <button
              type="button"
              disabled={!connected || busy}
              onClick={() => {
                closeActions();
                parsing.mutate("local");
              }}
            >
              <HardDrive size={16} aria-hidden="true" />
              <span>本地解析 / 重试</span>
            </button>
            <button
              type="button"
              aria-label="查看本地解析内容"
              aria-pressed={hasLocal && source === "local"}
              disabled={!hasLocal}
              onClick={() => {
                closeActions();
                onViewSource("local");
              }}
            >
              <FileSearch size={16} aria-hidden="true" />
              <span>
                查看本地解析内容
                {!hasLocal && <small>尚未完成本地解析</small>}
              </span>
              {hasLocal && source === "local" && (
                <Check size={15} aria-hidden="true" />
              )}
            </button>
            <button
              type="button"
              disabled={!connected || busy}
              onClick={() => {
                closeActions();
                parsing.reset();
                setPlan({
                  ...defaultPostImportPlan(),
                  parse: true,
                  overview: false,
                });
                setOpen(true);
              }}
            >
              <Sparkles size={16} aria-hidden="true" />
              <span>使用模型重新解析</span>
            </button>
            <button
              type="button"
              aria-label="查看模型解析内容"
              aria-pressed={hasModel && source === "model"}
              disabled={!hasModel}
              onClick={() => {
                closeActions();
                onViewSource("model");
              }}
            >
              <FileSearch size={16} aria-hidden="true" />
              <span>
                查看模型解析内容
                {!hasModel && <small>尚无模型解析记录</small>}
              </span>
              {hasModel && source === "model" && (
                <Check size={15} aria-hidden="true" />
              )}
            </button>
          </div>
        </div>
      </div>
      {task.data && (
        <p role={task.data.status === "failed" ? "alert" : "status"}>
          解析任务：
          {task.data.status === "succeeded"
            ? "已完成"
            : task.data.status === "failed"
              ? "失败，可重试"
              : task.data.status === "cancelled"
                ? "已取消"
                : task.data.status === "interrupted"
                  ? "已中断，可重试"
                  : jobStageLabel(task.data)}
          {task.data.error ? ` · ${task.data.error}` : ""}
        </p>
      )}
      {(parsing.error || task.error) && (
        <p role="alert">{String(parsing.error || task.error)}</p>
      )}
      {task.data && <DocumentRequestStatus job={task.data} />}
      {open && (
        <dialog
          ref={dialog}
          className="dialog import-dialog"
          aria-label="重新解析论文"
          onCancel={closeDialog}
          onClick={(event) => {
            if (event.target === event.currentTarget) closeDialog();
          }}
        >
          <div className="import-dialog-content">
            <h2>重新解析论文</h2>
            <p>
              沿用这篇论文已登记的
              PDF，不新建重复论文。原有本地材料、笔记和历史模型结果保留；新模型解析使用当前设置。
            </p>
            <ImportPostProcessingPlan value={plan} onChange={setPlan} />
            <button
              className="button primary"
              disabled={
                parsing.isPending || (plan.parse && !plan.allow_network)
              }
              onClick={() => parsing.mutate(plan.parse ? "model" : "local")}
            >
              确认{plan.parse ? "模型" : "本地"}解析
            </button>
            <button
              className="button secondary"
              onClick={closeDialog}
              disabled={parsing.isPending}
            >
              取消
            </button>
            {parsing.error && <p role="alert">{String(parsing.error)}</p>}
          </div>
        </dialog>
      )}
    </section>
  );
}
