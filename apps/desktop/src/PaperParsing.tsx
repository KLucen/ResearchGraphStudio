import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HardDrive, MoreHorizontal, Sparkles } from "lucide-react";
import { api, defaultPostImportPlan } from "./api";
import { ImportPostProcessingPlan } from "./ImportPostProcessingPlan";
import {
  isActiveReadingTask,
  ReadingTaskStatus,
  useModelImportSession,
} from "./ReadingTaskStatus";
import "./paperWorkspace.css";

export function PaperParsing({
  paperId,
  projectId,
  connected,
  hasLocal,
  hasModel,
  modelSessionId,
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
  modelSessionId?: string;
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
        window.innerHeight - bounds.bottom < 116 && bounds.top > 116,
      );
    setActionsOpen(!actionsOpen);
  };
  const [plan, setPlan] = useState(() => ({
    ...defaultPostImportPlan(),
    parse: true,
    overview: false,
  }));
  const [jobId, setJobId] = useState<string | null>(null);
  const modelSession = useModelImportSession(modelSessionId, connected);
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
          className="paper-reading-source"
          role="group"
          aria-label="论文阅读来源"
        >
          {hasLocal && hasModel ? (
            <label>
              <span>查看来源</span>
              <select
                value={source}
                onChange={(event) =>
                  onViewSource(
                    event.target.value === "local" ? "local" : "model",
                  )
                }
              >
                <option value="local">本地解析</option>
                <option value="model">模型解析</option>
              </select>
            </label>
          ) : (
            <>
              <span>查看来源</span>
              <strong>
                {hasLocal ? "本地解析" : hasModel ? "模型解析" : "暂无可读解析"}
              </strong>
            </>
          )}
        </div>
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
            aria-label="更多解析操作"
            aria-expanded={actionsOpen}
            aria-controls={actionsId}
            onClick={toggleActions}
          >
            <MoreHorizontal size={16} aria-hidden="true" />
            更多操作
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
          </div>
        </div>
      </div>
      <ReadingTaskStatus
        connected={connected}
        session={modelSession.data}
        parseJob={task.data ?? parsing.data}
        submittedParse={busy ? parsing.variables : undefined}
      />
      {task.data &&
        !isActiveReadingTask(task.data.status) &&
        task.data.error &&
        parsing.variables === "local" && (
          <p role="alert">本地解析未完成：{task.data.error}</p>
        )}
      {(parsing.error || task.error) && (
        <p role="alert">{String(parsing.error || task.error)}</p>
      )}
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
