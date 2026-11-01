import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

export function SourceIntegrations({
  projectId,
  connected,
}: {
  projectId: string;
  connected: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <details onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>只读来源接入 · Zotero / Obsidian</summary>
      {open && <Sources projectId={projectId} connected={connected} />}
    </details>
  );
}

function Sources({
  projectId,
  connected,
}: {
  projectId: string;
  connected: boolean;
}) {
  const client = useQueryClient();
  const [selected, setSelected] = useState("");
  const roots = useQuery({
    queryKey: ["note-roots", projectId],
    queryFn: () => api.noteRoots(projectId),
    enabled: connected,
  });
  const authorize = useMutation({
    mutationFn: () => api.authorizeNotes(projectId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["note-roots", projectId] });
    },
  });
  const action = useMutation({
    mutationFn: ({ id, kind }: { id: string; kind: "scan" | "revoke" }) =>
      api.noteAction(id, kind),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["note-roots", projectId] });
      void client.invalidateQueries({ queryKey: ["notes"] });
    },
  });
  const notes = useQuery({
    queryKey: ["notes", selected],
    queryFn: () => api.notes(selected),
    enabled:
      connected &&
      !!selected &&
      !!roots.data?.find((r) => r.id === selected && r.active),
    retry: false,
  });
  const zotero = useMutation({ mutationFn: api.zoteroStatus });
  const items = useMutation({ mutationFn: () => api.zoteroItems() });
  return (
    <div className="source-integrations">
      <h4>Zotero Local API</h4>
      <p>
        先在 Zotero 中启用本地 API。PDF
        导入仍通过原生选择器授权；在论文阅读区关联条目与批注。
      </p>
      <button
        className="button secondary"
        disabled={!connected || zotero.isPending}
        onClick={() => zotero.mutate()}
      >
        检查 Zotero 连接
      </button>
      <button
        className="button secondary"
        disabled={!connected || items.isPending}
        onClick={() => items.mutate()}
      >
        读取前 50 个条目
      </button>
      {zotero.data && (
        <p>
          {zotero.data.connected ? "Zotero 只读连接可用" : zotero.data.error}
        </p>
      )}
      {items.data?.map((item) => (
        <p key={item.key}>
          {item.data.title ?? item.data.itemType} · {item.key}
        </p>
      ))}
      <h4>Obsidian 私人笔记 · 只读快照</h4>
      <p>
        仅扫描你选择目录内的 Markdown。原笔记不会修改，内容不会自动发送给模型。
      </p>
      <button
        className="button secondary"
        disabled={!connected || authorize.isPending}
        onClick={() => authorize.mutate()}
      >
        选择并授权笔记目录
      </button>
      {roots.data?.map((root) => (
        <article className="text-chunk" key={root.id}>
          <p>
            {root.path} · {root.active ? "已授权" : "已撤销"}
          </p>
          {root.active && (
            <>
              <button
                className="text-button"
                disabled={!connected || action.isPending}
                onClick={() => action.mutate({ id: root.id, kind: "scan" })}
              >
                只读扫描
              </button>
              <button
                className="text-button"
                onClick={() => setSelected(root.id)}
              >
                查看快照
              </button>
              <button
                className="text-button"
                disabled={!connected || action.isPending}
                onClick={() => {
                  setSelected("");
                  action.mutate({ id: root.id, kind: "revoke" });
                }}
              >
                撤销授权
              </button>
            </>
          )}
        </article>
      ))}
      {action.data?.added !== undefined && (
        <p>
          保存 {action.data.added} 个新快照，跳过 {action.data.skipped} 个文件。
        </p>
      )}
      {[
        roots.error,
        authorize.error,
        action.error,
        notes.error,
        items.error,
        zotero.error,
      ]
        .filter(Boolean)
        .map((e, i) => (
          <p role="alert" key={i}>
            {e instanceof Error ? e.message : String(e)}
          </p>
        ))}
      {selected &&
        roots.data?.some((r) => r.id === selected && r.active) &&
        notes.data?.map((note) => (
          <details key={note.id}>
            <summary>
              {note.relative_path} · {note.sha256.slice(0, 12)}
            </summary>
            <pre>{note.text}</pre>
          </details>
        ))}
    </div>
  );
}
