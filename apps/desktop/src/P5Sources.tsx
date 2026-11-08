import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import {
  p5Api,
  emptyPersonalSelection,
  type PersonalSelection,
  type PersonalSource,
  type ExternalDocument,
  type ExternalPreview,
} from "./p5Api";

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);
const stateLabel = (state: string) =>
  ({
    draft: "草稿",
    invalid: "依赖无效",
    valid: "内容有效",
    saved: "已保存",
    published: "已导出",
    stale: "依赖已失效",
    unverified: "未核验",
    active: "当前有效",
    in_sync: "与登记快照一致",
    modified: "已被外部修改",
    external_modified: "已被外部修改",
    missing: "文件缺失",
    unavailable: "当前无法访问",
    anchored: "已定位",
    matched: "已定位",
    unanchored: "尚未定位",
    ambiguous: "定位有歧义",
    verified: "已核验",
  })[state] ?? "状态待核对";
function Failure({ error }: { error: unknown }) {
  return error ? (
    <p role="alert" className="error-text">
      {errorText(error)}
    </p>
  ) : null;
}
function Pages({
  page,
  total,
  change,
  name,
}: {
  page: number;
  total: number;
  change: (page: number) => void;
  name: string;
}) {
  return (
    <nav className="p5-pagination" aria-label={`${name}分页`}>
      <span>
        共 {total} 条 · 每页 10 条 · 第 {page} 页
      </span>
      <div>
        <button
          type="button"
          className="text-button"
          disabled={page <= 1}
          onClick={() => change(page - 1)}
          aria-label={`${name}上一页`}
        >
          上一页
        </button>
        <button
          type="button"
          className="text-button"
          disabled={page * 10 >= total}
          onClick={() => change(page + 1)}
          aria-label={`${name}下一页`}
        >
          下一页
        </button>
      </div>
    </nav>
  );
}
const sourceKey = (source: PersonalSource) =>
  source.type === "annotation"
    ? "annotation_ids"
    : source.type === "external"
      ? "external_version_ids"
      : "note_ids";

export function PersonalSources({
  projectId,
  connected,
  enabled,
  value,
  onChange,
  onEvidence,
}: {
  projectId: string;
  connected: boolean;
  enabled: boolean;
  value: PersonalSelection;
  onChange: (value: PersonalSelection) => void;
  onEvidence: (id: string) => void;
}) {
  const client = useQueryClient();
  const [page, setPage] = useState(1);
  const grantKeys = useRef(new Map<string, string>());
  const catalog = useQuery({
    queryKey: ["p5-personal-sources", projectId, page],
    queryFn: () => p5Api.personalSources(projectId, page),
    enabled: connected && enabled,
    retry: false,
  });
  const roots = useQuery({
    queryKey: ["p5-note-roots", projectId],
    queryFn: () => api.noteRoots(projectId),
    enabled: connected && enabled,
    retry: false,
  });
  const grant = useMutation({
    mutationFn: async ({
      source,
      permission,
    }: {
      source: PersonalSource;
      permission: "local" | "model";
    }) => {
      if (source.type === "annotation") {
        const body = {
          allow_model:
            permission === "model" ? !source.allow_model : source.allow_model,
          ...(permission === "local"
            ? { allow_local: !(source.allow_local ?? true) }
            : {}),
          expected_revision: source.authorization_revision,
        };
        const signature = JSON.stringify([source.id, body]);
        let key = grantKeys.current.get(signature);
        if (!key) {
          key = crypto.randomUUID();
          grantKeys.current.set(signature, key);
        }
        return p5Api.annotationGrant(projectId, source.id, body, key);
      }
      const root = roots.data?.find(
        (item) => item.id === source.root_id && item.active,
      );
      if (!root) throw new Error("读取授权目录后才能更改模型权限");
      return api.notePermissions(root.id, {
        allow_local: root.query_permissions?.allow_local ?? true,
        allow_model: !source.allow_model,
      });
    },
    onSuccess: (_result, { source, permission }) => {
      // Changing permission never selects a source. Revocation also clears any selected
      // source in that root so the next request cannot carry stale personal choices.
      if (
        permission === "local"
          ? (source.allow_local ?? true)
          : source.allow_model
      )
        onChange(emptyPersonalSelection());
      void client.invalidateQueries({
        queryKey: ["p5-personal-sources", projectId],
      });
      void client.invalidateQueries({ queryKey: ["p5-note-roots", projectId] });
    },
  });
  if (!enabled) return null;
  return (
    <details className="p5-disclosure" open>
      <summary>
        选择本次模型使用的个人材料 · 已选{" "}
        {value.note_ids.length +
          value.annotation_ids.length +
          value.external_version_ids.length}{" "}
        项
      </summary>
      <p className="quiet-note">
        默认不选。先独立授权，再选入本次来源；笔记与外部材料按目录授权，批注只发送个人评论。高亮原文只用于定位。
      </p>
      <Pages
        page={page}
        total={catalog.data?.total ?? 0}
        change={setPage}
        name="个人材料"
      />
      <Failure error={catalog.error || roots.error || grant.error} />
      <button
        type="button"
        className="text-button"
        onClick={() => void catalog.refetch()}
      >
        刷新个人材料
      </button>
      {catalog.isPending && <p role="status">正在读取当前已授权的个人材料…</p>}
      {catalog.data?.items.map((source) => (
        <article className="p5-passage" key={`${source.type}-${source.id}`}>
          <label className="p5-check">
            <input
              type="checkbox"
              aria-label={`模型来源 · ${source.label}`}
              checked={value[sourceKey(source)].includes(source.id)}
              disabled={
                !connected ||
                !source.allow_model ||
                source.allow_local === false ||
                source.redacted ||
                grant.isPending
              }
              onChange={(event) => {
                const key = sourceKey(source);
                onChange({
                  ...value,
                  [key]: event.target.checked
                    ? [...value[key], source.id]
                    : value[key].filter((id) => id !== source.id),
                });
              }}
            />
            {source.label} ·{" "}
            {source.type === "annotation"
              ? "仅个人评论"
              : source.type === "external"
                ? "外部阅读材料 · 未核验"
                : "个人笔记"}
          </label>
          <button
            type="button"
            className="text-button"
            disabled={
              !connected ||
              grant.isPending ||
              (source.type !== "annotation" && !roots.data)
            }
            onClick={() => grant.mutate({ source, permission: "model" })}
          >
            {source.allow_model ? "撤销模型使用授权" : "独立授权模型使用"} ·{" "}
            {source.label}
          </button>
          {source.type === "annotation" && (
            <button
              type="button"
              className="text-button"
              disabled={!connected || grant.isPending}
              onClick={() => grant.mutate({ source, permission: "local" })}
            >
              {source.allow_local === false
                ? "允许本地读取批注"
                : "撤销批注本地读取权限"}{" "}
              · {source.label}
            </button>
          )}
          {source.redacted ? (
            <p className="quiet-note">
              本地读取权限已撤销，评论正文和定位均已隐藏。
            </p>
          ) : (
            <details>
              <summary>查看材料与定位</summary>
              <p className="p5-passage-text">{source.text}</p>
              {source.highlight && (
                <blockquote>已有高亮原文：{source.highlight}</blockquote>
              )}
              {source.anchor_status && (
                <p>锚点状态：{stateLabel(source.anchor_status)}</p>
              )}
              {source.evidence_id && (
                <button
                  type="button"
                  className="text-button"
                  onClick={() => onEvidence(source.evidence_id!)}
                >
                  查看批注原文定位
                </button>
              )}
            </details>
          )}
        </article>
      ))}
      {catalog.data && !catalog.data.total && (
        <p className="quiet-note">
          没有当前可用的个人笔记、评论或外部阅读材料。请先在资料入口完成只读导入或登记。
        </p>
      )}
    </details>
  );
}

export function LintDocuments({
  projectId,
  connected,
  personal,
  value,
  onChange,
}: {
  projectId: string;
  connected: boolean;
  personal: boolean;
  value: string[];
  onChange: (ids: string[]) => void;
}) {
  const [page, setPage] = useState(1);
  const documents = useQuery({
    queryKey: ["lint-documents", projectId, personal, page],
    queryFn: () => p5Api.lintDocuments(projectId, page, personal),
    enabled: connected,
    retry: false,
  });
  return (
    <details className="p5-scope">
      <summary>
        检查文档范围 ·{" "}
        {value.length ? `已选 ${value.length} 份` : "全部可用文档"}
      </summary>
      <button
        type="button"
        className="text-button"
        onClick={() => onChange([])}
      >
        选择全部可用文档
      </button>
      <Failure error={documents.error} />
      <div className="p5-paper-options">
        {documents.data?.items.map((item) => (
          <label key={item.id}>
            <input
              type="checkbox"
              aria-label={`检查文档 · ${item.title}`}
              checked={value.includes(item.id)}
              onChange={(event) =>
                onChange(
                  event.target.checked
                    ? [...value, item.id]
                    : value.filter((id) => id !== item.id),
                )
              }
            />
            {item.title} · {stateLabel(item.status)}
          </label>
        ))}
      </div>
      <Pages
        page={page}
        total={documents.data?.total ?? 0}
        change={setPage}
        name="检查文档"
      />
    </details>
  );
}

export function ExternalLibrary({
  projectId,
  connected,
}: {
  projectId: string;
  connected: boolean;
}) {
  const client = useQueryClient();
  const [enabled, setEnabled] = useState(false);
  const [rootId, setRootId] = useState("");
  const [path, setPath] = useState("");
  const [title, setTitle] = useState("");
  const [attribution, setAttribution] = useState<
    "user_view" | "external_source"
  >("user_view");
  const [preview, setPreview] = useState<ExternalPreview | null>(null);
  const [target, setTarget] = useState<ExternalDocument | null>(null);
  const [versionId, setVersionId] = useState("");
  const [page, setPage] = useState(1);
  const keys = useRef(new Map<string, string>());
  const roots = useQuery({
    queryKey: ["p5-note-roots", projectId],
    queryFn: () => api.noteRoots(projectId),
    enabled: connected && enabled,
    retry: false,
  });
  const selectedReadRoot = roots.data?.find(
    (root) => root.id === rootId && root.active,
  );
  const localAllowed =
    !!selectedReadRoot &&
    (selectedReadRoot.query_permissions?.allow_local ?? true);
  const notes = useQuery({
    queryKey: ["p5-external-files", rootId],
    queryFn: () => api.notes(rootId),
    enabled: connected && enabled && localAllowed,
    retry: false,
  });
  const documents = useQuery({
    queryKey: ["p5-external-documents", projectId],
    queryFn: () => p5Api.externalDocuments(projectId),
    enabled: connected && enabled,
    retry: false,
  });
  const detail = useQuery({
    queryKey: [
      "p5-external-document",
      projectId,
      target?.document_id,
      versionId,
    ],
    queryFn: () =>
      p5Api.externalDocument(projectId, target!.document_id, versionId),
    enabled: connected && enabled && !!target,
    retry: false,
  });
  const authorize = useMutation({
    mutationFn: () => api.authorizeNotes(projectId),
    onSuccess: (root) => {
      if (root) {
        setRootId(root.id);
        setPath("");
        setPreview(null);
      }
      void client.invalidateQueries({ queryKey: ["p5-note-roots", projectId] });
    },
  });
  const scan = useMutation({
    mutationFn: () => api.noteAction(rootId, "scan"),
    onSuccess: () => {
      void notes.refetch();
      void client.invalidateQueries({
        queryKey: ["p5-personal-sources", projectId],
      });
    },
  });
  const localGrant = useMutation({
    mutationFn: () => {
      const root = roots.data?.find(
        (item) => item.id === rootId && item.active,
      );
      if (!root) throw new Error("请先读取已授权目录");
      return api.notePermissions(root.id, {
        allow_local: !(root.query_permissions?.allow_local ?? true),
        allow_model: root.query_permissions?.allow_model ?? false,
      });
    },
    onSuccess: () => {
      setPreview(null);
      setTarget(null);
      void client.invalidateQueries({ queryKey: ["p5-note-roots", projectId] });
      void client.invalidateQueries({
        queryKey: ["p5-external-documents", projectId],
      });
      void client.invalidateQueries({
        queryKey: ["p5-personal-sources", projectId],
      });
      void client.invalidateQueries({
        queryKey: ["lint-documents", projectId],
      });
    },
  });
  const inspect = useMutation({
    mutationFn: () =>
      p5Api.externalPreview(projectId, {
        root_id: rootId,
        relative_path: path,
      }),
    onSuccess: (result) => {
      setPreview(result);
      if (!title) setTitle(path);
    },
  });
  const register = useMutation({
    mutationFn: () => {
      if (
        !preview ||
        preview.root_id !== rootId ||
        preview.relative_path !== path
      )
        throw new Error("请先读取当前文件快照");
      const body = {
        root_id: rootId,
        relative_path: path,
        expected_sha256: preview.sha256,
        title: title.trim(),
        attribution,
        ...(target
          ? {
              document_id: target.document_id,
              base_version_id: target.current_version_id,
            }
          : {}),
      };
      const signature = JSON.stringify(body);
      let key = keys.current.get(signature);
      if (!key) {
        key = crypto.randomUUID();
        keys.current.set(signature, key);
      }
      return p5Api.externalRegister(projectId, body, key);
    },
    onSuccess: (result) => {
      setTarget(result);
      setVersionId("");
      setPreview(null);
      void client.invalidateQueries({
        queryKey: ["p5-external-documents", projectId],
      });
      void client.invalidateQueries({
        queryKey: ["p5-external-document", projectId],
      });
      void client.invalidateQueries({
        queryKey: ["p5-personal-sources", projectId],
      });
      void client.invalidateQueries({
        queryKey: ["lint-documents", projectId],
      });
    },
  });
  const items = documents.data?.items ?? [];
  return (
    <section className="p5-panel">
      <h3>外部 Markdown 阅读材料</h3>
      <label className="p5-check">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(event) => {
            setEnabled(event.target.checked);
            setPreview(null);
            setTarget(null);
          }}
        />
        查看并登记已授权的外部 Markdown
      </label>
      {enabled && (
        <>
          <p className="quiet-note">
            登记只读快照，内容保持未核验。原文件不会改写，登记不会继承科学证据或自动授权模型使用。
          </p>
          <button
            type="button"
            className="button secondary"
            disabled={!connected || authorize.isPending}
            onClick={() => authorize.mutate()}
          >
            选择并授权 Markdown 读取目录
          </button>
          <div className="p5-form-grid">
            <label>
              读取目录
              <select
                aria-label="外部材料读取目录"
                value={rootId}
                onChange={(event) => {
                  setRootId(event.target.value);
                  setPath("");
                  setPreview(null);
                  setTarget(null);
                }}
              >
                <option value="">请选择</option>
                {roots.data
                  ?.filter((root) => root.active)
                  .map((root) => (
                    <option key={root.id} value={root.id}>
                      {root.path}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Markdown 文件
              <select
                aria-label="外部 Markdown 文件"
                disabled={!localAllowed}
                value={path}
                onChange={(event) => {
                  setPath(event.target.value);
                  setPreview(null);
                  setTarget(null);
                }}
              >
                <option value="">请选择已扫描文件</option>
                {(localAllowed ? notes.data : [])?.map((note) => (
                  <option key={note.id} value={note.relative_path}>
                    {note.relative_path}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="p5-actions">
            <button
              type="button"
              className="text-button"
              disabled={!rootId || !connected || localGrant.isPending}
              onClick={() => localGrant.mutate()}
            >
              {(roots.data?.find((item) => item.id === rootId)
                ?.query_permissions?.allow_local ?? true)
                ? "撤销此目录本地读取权限"
                : "允许本地读取此目录材料"}
            </button>
            <button
              type="button"
              className="text-button"
              disabled={!localAllowed || !connected || scan.isPending}
              onClick={() => scan.mutate()}
            >
              只读扫描目录
            </button>
            <button
              type="button"
              className="button secondary"
              disabled={
                !localAllowed || !path || !connected || inspect.isPending
              }
              onClick={() => inspect.mutate()}
            >
              只读预览外部 Markdown
            </button>
          </div>
          {preview && (
            <article className="p5-passage">
              <strong>当前文件快照 · 未核验</strong>
              <pre className="p5-passage-text">{preview.text}</pre>
              <label>
                登记标题
                <input
                  aria-label="外部材料标题"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </label>
              <label>
                内容归属
                <select
                  aria-label="外部材料归属"
                  value={attribution}
                  onChange={(event) =>
                    setAttribution(event.target.value as typeof attribution)
                  }
                >
                  <option value="user_view">个人观点</option>
                  <option value="external_source">外部来源材料</option>
                </select>
              </label>
              <button
                type="button"
                className="button secondary"
                disabled={!title.trim() || register.isPending || !connected}
                onClick={() => register.mutate()}
              >
                {target ? "登记外部材料新版本" : "登记外部阅读材料"}
              </button>
            </article>
          )}
          <Failure
            error={
              roots.error ||
              notes.error ||
              documents.error ||
              detail.error ||
              authorize.error ||
              localGrant.error ||
              scan.error ||
              inspect.error ||
              register.error
            }
          />
          {register.isSuccess && (
            <p role="status">外部材料快照已登记，科学来源仍未核验。</p>
          )}
          <Pages
            page={page}
            total={items.length}
            change={setPage}
            name="外部材料"
          />
          {items.slice((page - 1) * 10, page * 10).map((item) => (
            <button
              type="button"
              className="p5-list-row"
              key={item.document_id}
              onClick={() => {
                setTarget(item);
                setRootId(item.root_id);
                setPath(item.relative_path);
                setTitle(item.title);
                setAttribution(item.attribution);
                setPreview(null);
                setVersionId("");
              }}
            >
              <strong>{item.title}</strong>
              <span>未核验 · 版本 {item.revision}</span>
            </button>
          ))}
          {target && detail.data && !detail.error && (
            <article className="p5-passage">
              <h4>{detail.data.title} · 未核验</h4>
              <label>
                历史版本
                <select
                  aria-label="外部材料历史版本"
                  value={versionId}
                  onChange={(event) => setVersionId(event.target.value)}
                >
                  <option value="">当前版本</option>
                  {detail.data.versions.map((version) => (
                    <option key={version.version_id} value={version.version_id}>
                      版本 {version.revision}
                    </option>
                  ))}
                </select>
              </label>
              <p className="p5-passage-text">{detail.data.text}</p>
              <p className="quiet-note">
                {detail.data.relative_path} · 文件状态：
                {stateLabel(detail.data.file_state)}
              </p>
              <p className="quiet-note">
                再次只读预览当前文件后，可明确登记新版本；旧快照保留。
              </p>
            </article>
          )}
        </>
      )}
    </section>
  );
}
