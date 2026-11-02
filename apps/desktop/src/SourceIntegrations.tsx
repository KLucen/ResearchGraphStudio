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
  return (
    <section aria-label="笔记来源">
      <h2>笔记来源</h2>
      <Sources projectId={projectId} connected={connected} />
    </section>
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
  return (
    <div className="source-integrations">
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
      {[roots.error, authorize.error, action.error, notes.error]
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
