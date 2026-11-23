import { useEffect, useId, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Ellipsis, RotateCcw, Trash2 } from "lucide-react";
import { useContextMenu } from "./ContextMenu";
import {
  archiveApi,
  archiveKinds,
  type ArchiveItem,
  type ArchiveKind,
} from "./archiveApi";
import "./archiveWorkspace.css";

const pageSize = 20;
const purgeDetails: Record<ArchiveKind, string> = {
  paper:
    "将清除项目论文、本地生成内容和无引用的受管 PDF。历史用量、Zotero 和外部原件保留。清除前的数据库快照仍含原记录。如需恢复受管 PDF，请先从设置创建完整备份。",
  knowledge_paper:
    "将清除该条目的知识版本和依赖它的跨论文联系及汇报。清除前的数据库快照仍含原记录。",
  knowledge_collection: "将清除专题及其成员关系，专题中的论文保留。",
  model_connection: "将清除提供商的本机凭据和归档配置。",
  model_profile: "将清除该模型配置，已保存的结果和历史计量保留。",
  job: "将永久移除此条任务记录。已发布结果和相关用量计量保留。",
  paper_legacy_content:
    "将清除这篇论文的旧本地解析和缓存。论文、原件与个人记录保留。",
};

export function ArchiveWorkspace({
  connected,
  projectNames,
}: {
  connected: boolean;
  projectNames?: Record<string, string>;
}) {
  const client = useQueryClient();
  const [kind, setKind] = useState<ArchiveKind | "">("");
  const [offset, setOffset] = useState(0);
  const [notice, setNotice] = useState("");
  const [purgeRequest, setPurgeRequest] = useState<{
    item: ArchiveItem;
    trigger: HTMLElement | null;
  } | null>(null);
  const purgeTarget = purgeRequest?.item;
  const dialog = useRef<HTMLDialogElement>(null);
  const cancelPurge = useRef<HTMLButtonElement>(null);
  const dialogId = useId();
  const { contextMenuProps, contextMenu, openContextMenu } = useContextMenu();
  const archive = useQuery({
    queryKey: ["archive", kind, offset],
    queryFn: () => archiveApi.list(kind, offset, pageSize),
    enabled: connected,
  });
  const change = useMutation({
    mutationFn: async ({
      item,
      action,
    }: {
      item: ArchiveItem;
      action: "restore" | "purge";
    }) => archiveApi[action](item.id),
    onSuccess: (result, { item, action }) => {
      const retained =
        "retained_managed_files" in result
          ? (result.retained_managed_files ?? 0)
          : 0;
      const pendingFiles =
        "pending_managed_files" in result
          ? (result.pending_managed_files ?? 0)
          : 0;
      const needsCleanup = "status" in result && result.status === "purging";
      setNotice(
        action === "restore"
          ? `已恢复「${item.title}」。`
          : needsCleanup
            ? `「${item.title}」还有 ${pendingFiles} 个本机文件待清理。可点击继续清除。`
            : retained
              ? `已清除「${item.title}」的归档内容。保留 ${retained} 个仍有引用或由外部管理的文件。`
              : `已彻底清除「${item.title}」。`,
      );
      if (!needsCleanup && offset && archive.data?.items.length === 1)
        setOffset(Math.max(0, offset - pageSize));
      void client.invalidateQueries();
    },
    onError: () => void client.invalidateQueries({ queryKey: ["archive"] }),
  });
  useEffect(() => {
    if (!purgeTarget || !dialog.current || dialog.current.open) return;
    dialog.current.showModal();
    cancelPurge.current?.focus();
  }, [purgeTarget]);
  function projectName(item: ArchiveItem) {
    if (!item.project_id) return "无所属项目";
    return projectNames?.[item.project_id] ?? "原项目不可用";
  }
  function restore(item: ArchiveItem) {
    if (!connected || change.isPending || item.status !== "archived") return;
    setNotice("");
    change.mutate({ item, action: "restore" });
  }
  function requestPurge(item: ArchiveItem) {
    if (!connected || change.isPending || purgeTarget) return;
    const trigger = document.activeElement;
    setPurgeRequest({
      item,
      trigger: trigger instanceof HTMLElement ? trigger : null,
    });
  }
  function dismissPurge() {
    dialog.current?.close();
    setPurgeRequest(null);
    const trigger = purgeRequest?.trigger;
    if (trigger?.isConnected) trigger.focus({ preventScroll: true });
  }
  function confirmPurge() {
    if (!connected || change.isPending || !purgeTarget || !dialog.current?.open)
      return;
    const item = purgeTarget;
    dismissPurge();
    setNotice("");
    change.mutate({ item, action: "purge" });
  }
  const error = archive.error ?? change.error;
  return (
    <section
      className="archive-workspace"
      aria-labelledby="archive-workspace-title"
    >
      <header>
        <h1 id="archive-workspace-title">归档管理</h1>
        <p>在这里恢复归档内容，或确认彻底清除。</p>
      </header>
      <div className="archive-toolbar">
        <label>
          内容类型
          <select
            value={kind}
            disabled={change.isPending}
            onChange={(event) => {
              setKind(event.target.value as ArchiveKind | "");
              setOffset(0);
              setNotice("");
              change.reset();
            }}
          >
            <option value="">全部内容</option>
            {Object.entries(archiveKinds).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {archive.data && (
          <span className="muted">{archive.data.total} 条归档</span>
        )}
      </div>
      {!connected && <p role="status">正在等待本地引擎连接…</p>}
      {connected && archive.isPending && <p role="status">正在读取归档…</p>}
      {error && (
        <p className="error-text" role="alert">
          {error.message}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {archive.isSuccess && !archive.data.items.length && (
        <div className="archive-empty">
          <Archive size={24} aria-hidden="true" />
          <p>此范围暂无归档内容。</p>
        </div>
      )}
      {archive.data?.items.length ? (
        <ul className="archive-list">
          {archive.data.items.map((item) => {
            const purging = item.status === "purging";
            const busy = !connected || change.isPending;
            const purgeAction = {
              label: purging ? "继续清除" : "彻底清除",
              action: () => requestPurge(item),
              disabled: busy,
              danger: true,
            };
            const menuLabel = `管理${item.title}`;
            return (
              <li
                className="archive-row"
                key={item.id}
                tabIndex={0}
                {...contextMenuProps(menuLabel, [
                  {
                    label: "恢复",
                    action: () => restore(item),
                    disabled: busy || purging,
                  },
                  purgeAction,
                ])}
              >
                <div>
                  <strong>{item.title}</strong>
                  <small>
                    <span>{archiveKinds[item.kind]}</span>
                    <span>{projectName(item)}</span>
                    <time dateTime={item.archived_at}>
                      {new Date(item.archived_at).toLocaleString("zh-CN")}
                    </time>
                  </small>
                </div>
                <div className="archive-row-actions">
                  <button
                    type="button"
                    className="button secondary compact"
                    disabled={busy || purging}
                    onClick={() => restore(item)}
                  >
                    <RotateCcw size={14} aria-hidden="true" /> 恢复
                  </button>
                  {purging ? (
                    <button
                      type="button"
                      className="button secondary compact"
                      disabled={busy}
                      onClick={purgeAction.action}
                    >
                      <Trash2 size={14} aria-hidden="true" /> 继续清除
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="button secondary compact"
                      disabled={busy}
                      aria-haspopup="menu"
                      onClick={(event) =>
                        openContextMenu(event, menuLabel, [purgeAction])
                      }
                    >
                      <Ellipsis size={14} aria-hidden="true" /> 更多操作
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
      {(offset > 0 || (archive.data?.total ?? 0) > pageSize) && (
        <div className="archive-toolbar archive-pager" aria-label="归档分页">
          <button
            type="button"
            className="button secondary compact"
            disabled={!offset || change.isPending}
            onClick={() => setOffset(offset - pageSize)}
          >
            上一页
          </button>
          <span>第 {Math.floor(offset / pageSize) + 1} 页</span>
          <button
            type="button"
            className="button secondary compact"
            disabled={
              change.isPending ||
              offset + pageSize >= (archive.data?.total ?? 0)
            }
            onClick={() => setOffset(offset + pageSize)}
          >
            下一页
          </button>
        </div>
      )}
      <dialog
        ref={dialog}
        className="dialog archive-purge-dialog"
        aria-labelledby={`${dialogId}-title`}
        aria-describedby={`${dialogId}-impact`}
        onCancel={(event) => {
          event.preventDefault();
          dismissPurge();
        }}
      >
        {purgeTarget && (
          <>
            <h2 id={`${dialogId}-title`}>
              {purgeTarget.status === "purging"
                ? "继续清除归档"
                : "彻底清除归档"}
            </h2>
            <dl className="archive-purge-target">
              <dt>内容</dt>
              <dd>{purgeTarget.title}</dd>
              <dt>类型</dt>
              <dd>{archiveKinds[purgeTarget.kind]}</dd>
              <dt>所属项目</dt>
              <dd>{projectName(purgeTarget)}</dd>
            </dl>
            <p id={`${dialogId}-impact`}>
              {purgeDetails[purgeTarget.kind]} 此操作无法撤销。
            </p>
            <div className="dialog-actions">
              <button
                ref={cancelPurge}
                type="button"
                className="button secondary"
                onClick={dismissPurge}
              >
                取消
              </button>
              <button
                type="button"
                className="button danger"
                disabled={!connected || change.isPending}
                onClick={confirmPurge}
              >
                {purgeTarget.status === "purging" ? "继续清除" : "彻底清除"}
              </button>
            </div>
          </>
        )}
      </dialog>
      {contextMenu}
    </section>
  );
}
