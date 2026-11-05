import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type NoteRoot } from "./api";

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
              <NotePermissions
                key={`${root.id}:${JSON.stringify(root.query_permissions)}`}
                root={root}
                connected={connected}
                onSaved={() => {
                  void client.invalidateQueries({
                    queryKey: ["note-roots", projectId],
                  });
                  for (const scope of [
                    "query-run",
                    "query-answer",
                    "query-documents",
                    "query-saved",
                    "query-saved-detail",
                    "query-derived",
                  ])
                    void client.invalidateQueries({
                      queryKey: [scope, projectId],
                    });
                }}
              />
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

function NotePermissions({
  root,
  connected,
  onSaved,
}: {
  root: NoteRoot;
  connected: boolean;
  onSaved: () => void;
}) {
  const [local, setLocal] = useState(
    root.query_permissions?.allow_local ?? false,
  );
  const [model, setModel] = useState(
    root.query_permissions?.allow_model ?? false,
  );
  const save = useMutation({
    mutationFn: () =>
      api.notePermissions(root.id, { allow_local: local, allow_model: model }),
    onSuccess: onSaved,
  });
  return (
    <fieldset
      className="note-query-permissions"
      disabled={!connected || save.isPending || !root.query_permissions}
    >
      <legend>问答用途</legend>
      <label>
        <input
          type="checkbox"
          checked={local}
          onChange={(event) => setLocal(event.target.checked)}
        />
        允许本地问答检索
      </label>
      <label>
        <input
          type="checkbox"
          checked={model}
          onChange={(event) => setModel(event.target.checked)}
        />
        允许将必要笔记片段发送给问答模型
      </label>
      <p className="quiet-note">
        模型外发默认关闭。问答中还需单独勾选个人资料及本次模型传输；撤销目录后不会自动恢复外发授权。
      </p>
      <button
        type="button"
        className="button secondary"
        onClick={() => save.mutate()}
      >
        保存用途授权
      </button>
      {!root.query_permissions && (
        <p className="quiet-note">正在等待引擎提供当前用途授权，暂不修改。</p>
      )}
      {save.error && (
        <p role="alert">
          {save.error instanceof Error ? save.error.message : "授权保存失败"}
        </p>
      )}
      {save.isSuccess && <p role="status">问答用途授权已保存。</p>}
    </fieldset>
  );
}
