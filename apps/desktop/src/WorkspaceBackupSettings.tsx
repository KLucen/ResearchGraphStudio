import { invoke, isTauri } from "@tauri-apps/api/core";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

type BackupOperation = "export" | "restore";
type BackupResult = {
  path: string;
  managed_files: number;
  external_sources: number;
  previous_path?: string;
  restart_error?: string;
};

const restoreReceipt = "rgs.workspace-restore-receipt";

function priorRestore(): BackupResult | null {
  try {
    const value = sessionStorage.getItem(restoreReceipt);
    return value ? (JSON.parse(value) as BackupResult) : null;
  } catch {
    return null;
  }
}

export function WorkspaceBackupSettings() {
  const [restored, setRestored] = useState(priorRestore);
  const operation = useMutation({
    mutationFn: (operation: BackupOperation) => {
      if (!isTauri()) throw new Error("请在 Windows 桌面应用中执行备份或恢复");
      return invoke<BackupResult | null>("workspace_backup", { operation });
    },
    onSuccess: (result, kind) => {
      if (result && kind === "restore") {
        try {
          sessionStorage.setItem(restoreReceipt, JSON.stringify(result));
        } catch {
          // The new workspace still needs a fresh renderer and query cache.
        }
        window.location.reload();
      }
    },
  });
  const created = operation.variables === "export" ? operation.data : null;
  return (
    <section className="settings-card" aria-labelledby="workspace-backup-title">
      <div className="settings-title">
        <h2 id="workspace-backup-title">工作区备份与恢复</h2>
      </div>
      <p>
        完整备份包含数据库和应用管理的 PDF。Zotero
        与外部引用仅保留链接。请把备份存放在私密位置。
      </p>
      <p>
        恢复前会校验文件，随后切换到独立工作区。原工作区保留，自动联网关闭，API
        Key 需重新绑定。请等任务结束后操作。
      </p>
      <div className="dialog-actions">
        <button
          type="button"
          className="button secondary"
          disabled={operation.isPending}
          onClick={() => operation.mutate("export")}
        >
          创建完整备份
        </button>
        <button
          type="button"
          className="button secondary"
          disabled={operation.isPending}
          onClick={() => operation.mutate("restore")}
        >
          从备份恢复
        </button>
      </div>
      {operation.isPending && (
        <p role="status">正在处理文件，请保持应用打开。</p>
      )}
      {operation.isError && (
        <p role="alert" className="error-text">
          {operation.error instanceof Error
            ? operation.error.message
            : String(operation.error)}
        </p>
      )}
      {created && (
        <div role="status">
          <p>
            备份已校验，共 {created.managed_files} 份受管 PDF、
            {created.external_sources} 条外部来源链接。
          </p>
          <p className="mono">{created.path}</p>
          {created.restart_error && (
            <p role="alert">
              备份已保存，引擎重连失败。{created.restart_error}
            </p>
          )}
        </div>
      )}
      {restored && (
        <div role="status">
          <p>
            已切换到恢复出的工作区。原工作区保留在{" "}
            <span className="mono">{restored.previous_path}</span>。
          </p>
          <button
            type="button"
            className="button secondary"
            onClick={() => {
              setRestored(null);
              try {
                sessionStorage.removeItem(restoreReceipt);
              } catch {
                // Dismissing the notice never controls the backup operation.
              }
            }}
          >
            知道了
          </button>
        </div>
      )}
    </section>
  );
}
