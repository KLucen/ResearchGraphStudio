import { useRef, useState } from "react";
import {
  useIsMutating,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Archive, Folder, FolderPlus, Pencil, Search } from "lucide-react";
import { archiveApi } from "./archiveApi";
import { KnowledgeDialog } from "./KnowledgeDialog";
import {
  knowledgeApi,
  knowledgeErrorMessage,
  type KnowledgeCollection,
  type KnowledgePaper,
  type TopicMembership,
  type TopicMembershipResult,
} from "./knowledgeApi";
import "./topicManagement.css";

const collectionKey = ["knowledge", "collections"] as const;
const topicWriteKey = ["knowledge", "topic-write"] as const;
const pageSize = 15;
const selectionLimit = 100;

function errorMessage(error: unknown) {
  return knowledgeErrorMessage(
    error instanceof Error ? error.message : String(error),
  );
}

function useCommandKey() {
  const pending = useRef<{ request: string; key: string } | null>(null);
  return {
    forRequest(request: unknown) {
      const value = JSON.stringify(request);
      if (pending.current?.request !== value)
        pending.current = { request: value, key: crypto.randomUUID() };
      return pending.current.key;
    },
    clear() {
      pending.current = null;
    },
  };
}

function membershipMessage(result: TopicMembershipResult) {
  if (!result.added && !result.removed) return "专题归属已经是所选状态。";
  return `专题已更新 · 添加 ${result.added} 条归属 · 移除 ${result.removed} 条归属`;
}

function useTopicMembership(onSaved: (result: TopicMembershipResult) => void) {
  const key = useCommandKey();
  return useMutation({
    mutationKey: topicWriteKey,
    mutationFn: ({
      destination,
      body,
    }: {
      destination: string;
      body: TopicMembership;
    }) =>
      knowledgeApi.changeCollectionMembership(
        destination,
        body,
        key.forRequest([destination, body]),
      ),
    onSuccess: (result) => {
      key.clear();
      onSaved(result);
    },
  });
}

function TopicEditor({
  collection,
  onSaved,
  onCancel,
}: {
  collection?: KnowledgeCollection;
  onSaved: (collection: KnowledgeCollection) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(collection?.name ?? "");
  const [description, setDescription] = useState(collection?.description ?? "");
  const key = useCommandKey();
  const save = useMutation({
    mutationKey: topicWriteKey,
    mutationFn: () => {
      const body = { name: name.trim(), description: description.trim() };
      const idempotencyKey = key.forRequest(body);
      return collection
        ? knowledgeApi.updateCollection(collection.id, body, idempotencyKey)
        : knowledgeApi.createCollection(
            body.name,
            body.description,
            idempotencyKey,
          );
    },
    onSuccess: onSaved,
  });
  return (
    <form
      className="topic-editor"
      onSubmit={(event) => {
        event.preventDefault();
        if (name.trim() && !save.isPending) save.mutate();
      }}
    >
      <h3>{collection ? "编辑专题" : "新建专题"}</h3>
      <label>
        专题名称
        <input
          autoFocus
          required
          maxLength={120}
          value={name}
          disabled={save.isPending}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <label>
        专题说明（可选）
        <textarea
          maxLength={2000}
          value={description}
          disabled={save.isPending}
          onChange={(event) => setDescription(event.target.value)}
        />
      </label>
      {save.error && (
        <p role="alert" className="error-text">
          {errorMessage(save.error)}
        </p>
      )}
      <div className="topic-actions">
        <button
          type="submit"
          className="button primary"
          disabled={!name.trim() || save.isPending}
        >
          {save.isPending ? "正在保存…" : collection ? "保存专题" : "创建专题"}
        </button>
        <button
          type="button"
          className="button secondary"
          disabled={save.isPending}
          onClick={onCancel}
        >
          取消
        </button>
      </div>
    </form>
  );
}

type PickerMode = "members" | "add" | "move";

function TopicPaperPicker({
  collection,
  mode,
  sourceId,
  onChanged,
}: {
  collection: KnowledgeCollection;
  mode: PickerMode;
  sourceId: string;
  onChanged: () => void;
}) {
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [selection, setSelection] = useState<string[]>([]);
  const [notice, setNotice] = useState("");
  const scope =
    mode === "members" ? collection.id : mode === "move" ? sourceId : "";
  const papers = useQuery({
    queryKey: [
      "knowledge",
      "papers",
      "topic-management",
      scope,
      search,
      offset,
    ],
    queryFn: () =>
      knowledgeApi.papers({
        collection_id: scope,
        search,
        offset,
        limit: pageSize,
      }),
  });
  const change = useTopicMembership((result) => {
    setSelection([]);
    setOffset(0);
    setNotice(membershipMessage(result));
    onChanged();
  });
  const total = papers.data?.total ?? 0;
  const actionLabel =
    mode === "members"
      ? "移出所选论文"
      : mode === "add"
        ? "添加所选论文"
        : "移动所选论文";
  function submit() {
    const body: TopicMembership =
      mode === "move"
        ? {
            action: "move",
            paper_ids: selection,
            source_collection_ids: [sourceId],
          }
        : { action: mode === "add" ? "add" : "remove", paper_ids: selection };
    setNotice("");
    change.mutate({ destination: collection.id, body });
  }

  return (
    <div className="topic-paper-picker">
      <label className="topic-paper-search">
        <span className="sr-only">搜索可归类论文</span>
        <Search size={14} aria-hidden="true" />
        <input
          type="search"
          value={search}
          maxLength={300}
          placeholder="搜索论文、研究问题与概念"
          onChange={(event) => {
            setSearch(event.target.value);
            setOffset(0);
          }}
        />
      </label>
      {papers.isPending && <p role="status">正在读取论文知识…</p>}
      {papers.isError && (
        <div role="alert" className="topic-status error-text">
          {errorMessage(papers.error)}
          <button
            type="button"
            className="text-button"
            onClick={() => void papers.refetch()}
          >
            重试
          </button>
        </div>
      )}
      {papers.isSuccess && !papers.data.items.length && (
        <p className="topic-status muted">
          {search.trim()
            ? "没有匹配的论文知识。"
            : scope
              ? "本专题暂无论文知识。"
              : "知识库暂无论文知识。"}
        </p>
      )}
      {!!papers.data?.items.length && (
        <ul className="topic-paper-choices" aria-label="可归类论文">
          {papers.data.items.map((paper) => {
            const checked = selection.includes(paper.id);
            const existing = paper.collection_ids.includes(collection.id);
            return (
              <li key={paper.id}>
                <label>
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={
                      change.isPending ||
                      (mode === "add" && existing) ||
                      (!checked && selection.length >= selectionLimit)
                    }
                    onChange={(event) => {
                      const include = event.target.checked;
                      setSelection((current) =>
                        include
                          ? [...current, paper.id]
                          : current.filter((id) => id !== paper.id),
                      );
                    }}
                  />
                  <span>{paper.title}</span>
                  {mode !== "members" && existing && <small>已在本专题</small>}
                </label>
              </li>
            );
          })}
        </ul>
      )}
      {(total > pageSize || offset > 0) && (
        <div className="topic-page" aria-label="专题论文分页">
          <button
            type="button"
            className="text-button"
            disabled={!offset || change.isPending}
            onClick={() => setOffset(Math.max(0, offset - pageSize))}
          >
            上一页
          </button>
          <span>
            {papers.isPending
              ? "正在读取…"
              : `共 ${total} 篇 · 第 ${Math.floor(offset / pageSize) + 1} 页`}
          </span>
          <button
            type="button"
            className="text-button"
            disabled={offset + pageSize >= total || change.isPending}
            onClick={() => setOffset(offset + pageSize)}
          >
            下一页
          </button>
        </div>
      )}
      <div className="topic-actions">
        <span className="muted" aria-live="polite">
          已选 {selection.length} 篇
          {selection.length === selectionLimit ? " · 已达本次上限" : ""}
        </span>
        {selection.length > 0 && (
          <button
            type="button"
            className="text-button"
            disabled={change.isPending}
            onClick={() => setSelection([])}
          >
            清空选择
          </button>
        )}
        <button
          type="button"
          className="button primary"
          disabled={!selection.length || change.isPending}
          onClick={submit}
        >
          {change.isPending ? "正在更新…" : actionLabel}
        </button>
      </div>
      {change.error && (
        <p role="alert" className="error-text">
          {errorMessage(change.error)}
        </p>
      )}
      {notice && (
        <p role="status" className="topic-status">
          {notice}
        </p>
      )}
    </div>
  );
}

function TopicPapers({
  collection,
  others,
  onChanged,
}: {
  collection: KnowledgeCollection;
  others: KnowledgeCollection[];
  onChanged: () => void;
}) {
  const [mode, setMode] = useState<PickerMode>("members");
  const [sourceId, setSourceId] = useState("");
  const busy = useIsMutating({ mutationKey: topicWriteKey }) > 0;
  return (
    <section aria-label="管理专题论文">
      <h4>专题论文</h4>
      <div className="topic-mode" role="group" aria-label="专题论文操作">
        {(
          [
            ["members", "本专题论文"],
            ["add", "添加已有论文"],
            ["move", "从其他专题移入"],
          ] as const
        ).map(([value, label]) => (
          <button
            type="button"
            className="button secondary"
            aria-pressed={mode === value}
            disabled={busy || (value === "move" && !others.length)}
            key={value}
            onClick={() => setMode(value)}
          >
            {label}
          </button>
        ))}
      </div>
      {mode === "move" && (
        <label>
          来源专题
          <select
            value={sourceId}
            disabled={busy}
            onChange={(event) => setSourceId(event.target.value)}
          >
            <option value="">请选择来源专题</option>
            {others.map((topic) => (
              <option key={topic.id} value={topic.id}>
                {topic.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <p className="topic-status muted">
        {mode === "members"
          ? "移出仅取消本专题的归属。"
          : mode === "move"
            ? "所选论文将从指定来源移到当前专题，其他归属仍保留。"
            : "添加可让同一篇论文同时归入多个专题。"}
      </p>
      {(mode !== "move" || sourceId) && (
        <TopicPaperPicker
          key={`${mode}:${sourceId}`}
          collection={collection}
          mode={mode}
          sourceId={sourceId}
          onChanged={onChanged}
        />
      )}
    </section>
  );
}

export function TopicManagement({
  connected,
  selectedId,
  create,
  onClose,
  onBrowse,
  onChanged,
  onArchived,
}: {
  connected: boolean;
  selectedId: string;
  create: boolean;
  onClose: () => void;
  onBrowse: (id: string) => void;
  onChanged: () => void;
  onArchived: (id: string, name: string) => void;
}) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: collectionKey,
    queryFn: knowledgeApi.collections,
    enabled: connected,
  });
  const topics = query.data?.items ?? [];
  const [activeId, setActiveId] = useState(selectedId);
  const [editor, setEditor] = useState<"create" | "edit" | null>(
    create ? "create" : null,
  );
  const [archiveId, setArchiveId] = useState("");
  const [notice, setNotice] = useState("");
  const active = topics.find((topic) => topic.id === activeId) ?? topics[0];
  const busy = useIsMutating({ mutationKey: topicWriteKey }) > 0;
  const archive = useMutation({
    mutationKey: topicWriteKey,
    mutationFn: (topic: KnowledgeCollection) =>
      archiveApi.stage("knowledge_collection", topic.id),
    onSuccess: (_, topic) => {
      queryClient.setQueryData<{ items: KnowledgeCollection[] }>(
        collectionKey,
        (current) => ({
          items: (current?.items ?? []).filter((item) => item.id !== topic.id),
        }),
      );
      setActiveId("");
      setArchiveId("");
      setNotice(`专题「${topic.name}」已移至归档管理。`);
      onArchived(topic.id, topic.name);
    },
  });
  function saveTopic(topic: KnowledgeCollection) {
    queryClient.setQueryData<{ items: KnowledgeCollection[] }>(
      collectionKey,
      (current) => ({
        items: [
          ...(current?.items ?? []).filter((item) => item.id !== topic.id),
          topic,
        ],
      }),
    );
    setActiveId(topic.id);
    setEditor(null);
    setNotice(`专题「${topic.name}」已保存。`);
    onChanged();
  }
  return (
    <KnowledgeDialog title="专题管理" onClose={onClose} busy={busy}>
      <div className="topic-management">
        <aside className="topic-list" aria-label="已有专题">
          <button
            type="button"
            className="button secondary"
            disabled={busy || !connected}
            onClick={() => {
              setEditor("create");
              setArchiveId("");
            }}
          >
            <FolderPlus size={15} />
            新建专题
          </button>
          {query.isPending && connected && <p role="status">正在读取专题…</p>}
          {query.isError && (
            <div role="alert" className="error-text">
              {errorMessage(query.error)}
              <button
                type="button"
                className="text-button"
                onClick={() => void query.refetch()}
              >
                重试
              </button>
            </div>
          )}
          <ul>
            {topics.map((topic) => (
              <li key={topic.id}>
                <button
                  type="button"
                  aria-pressed={!editor && active?.id === topic.id}
                  className="topic-list-item"
                  disabled={busy}
                  onClick={() => {
                    setActiveId(topic.id);
                    setEditor(null);
                    setArchiveId("");
                    setNotice("");
                    archive.reset();
                  }}
                >
                  <Folder size={15} />
                  <span>{topic.name}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>
        <div className="topic-content">
          {editor && connected ? (
            <TopicEditor
              key={editor === "edit" ? active?.id : "new"}
              collection={editor === "edit" ? active : undefined}
              onSaved={saveTopic}
              onCancel={() => setEditor(null)}
            />
          ) : active ? (
            <>
              <div className="topic-heading">
                <h3>{active.name}</h3>
                {active.description && <p>{active.description}</p>}
              </div>
              <div className="topic-actions">
                <button
                  type="button"
                  className="button secondary"
                  disabled={busy}
                  onClick={() => onBrowse(active.id)}
                >
                  浏览专题
                </button>
                <button
                  type="button"
                  className="text-button"
                  disabled={busy || !connected}
                  onClick={() => {
                    setEditor("edit");
                    setArchiveId("");
                  }}
                >
                  <Pencil size={14} />
                  编辑专题
                </button>
                <button
                  type="button"
                  className="text-button"
                  disabled={busy || !connected}
                  onClick={() => setArchiveId(active.id)}
                >
                  <Archive size={14} />
                  归档专题
                </button>
              </div>
              {archiveId === active.id && (
                <div className="topic-archive-confirm">
                  <p>
                    归档「{active.name}
                    」后，可在归档管理恢复。论文知识和已建立的联系会保留。
                  </p>
                  <div className="topic-actions">
                    <button
                      type="button"
                      className="button secondary"
                      disabled={busy}
                      onClick={() => archive.mutate(active)}
                    >
                      确认归档专题
                    </button>
                    <button
                      type="button"
                      className="text-button"
                      disabled={busy}
                      onClick={() => {
                        setArchiveId("");
                        archive.reset();
                      }}
                    >
                      取消归档
                    </button>
                  </div>
                  {archive.error && (
                    <p role="alert" className="error-text">
                      {errorMessage(archive.error)}
                    </p>
                  )}
                </div>
              )}
              {connected && (
                <TopicPapers
                  key={active.id}
                  collection={active}
                  others={topics.filter((topic) => topic.id !== active.id)}
                  onChanged={onChanged}
                />
              )}
            </>
          ) : query.isSuccess ? (
            <p className="topic-status muted">
              还没有专题。可新建专题，再将已有论文归入其中。
            </p>
          ) : null}
          {notice && (
            <p role="status" className="topic-status">
              {notice}
            </p>
          )}
        </div>
      </div>
    </KnowledgeDialog>
  );
}

export function PaperTopicAssignment({
  paper,
  topics,
  selectedId,
  onClose,
  onCreate,
  onSaved,
}: {
  paper: KnowledgePaper;
  topics: KnowledgeCollection[];
  selectedId: string;
  onClose: () => void;
  onCreate: () => void;
  onSaved: (notice: string) => void;
}) {
  const [action, setAction] = useState<TopicMembership["action"]>("add");
  const [targetId, setTargetId] = useState(selectedId);
  const [sourceId, setSourceId] = useState(
    paper.collection_ids.includes(selectedId) ? selectedId : "",
  );
  const members = topics.filter((topic) =>
    paper.collection_ids.includes(topic.id),
  );
  const possibleTargets = topics.filter((topic) =>
    action === "add"
      ? !paper.collection_ids.includes(topic.id)
      : action === "remove"
        ? paper.collection_ids.includes(topic.id)
        : topic.id !== sourceId,
  );
  const destination = possibleTargets.some((topic) => topic.id === targetId)
    ? targetId
    : "";
  const change = useTopicMembership((result) =>
    onSaved(membershipMessage(result)),
  );
  return (
    <KnowledgeDialog
      title="管理论文专题"
      onClose={onClose}
      busy={change.isPending}
    >
      <div className="topic-paper-assignment">
        <h3>{paper.title}</h3>
        <p className="muted">
          当前专题 ·{" "}
          {members.map((topic) => topic.name).join("、") || "未归入专题"}
        </p>
        {!topics.length ? (
          <button type="button" className="button secondary" onClick={onCreate}>
            新建专题
          </button>
        ) : (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (
                !destination ||
                (action === "move" && !sourceId) ||
                change.isPending
              )
                return;
              const body: TopicMembership =
                action === "move"
                  ? {
                      action,
                      paper_ids: [paper.id],
                      source_collection_ids: [sourceId],
                    }
                  : { action, paper_ids: [paper.id] };
              change.mutate({ destination, body });
            }}
          >
            <label>
              归类操作
              <select
                value={action}
                disabled={change.isPending}
                onChange={(event) =>
                  setAction(event.target.value as TopicMembership["action"])
                }
              >
                <option value="add">添加到专题</option>
                <option
                  value="move"
                  disabled={!members.length || topics.length < 2}
                >
                  移动到其他专题
                </option>
                <option value="remove" disabled={!members.length}>
                  移出专题
                </option>
              </select>
            </label>
            {action === "move" && (
              <label>
                来源专题
                <select
                  value={sourceId}
                  disabled={change.isPending}
                  onChange={(event) => setSourceId(event.target.value)}
                >
                  <option value="">请选择来源专题</option>
                  {members.map((topic) => (
                    <option key={topic.id} value={topic.id}>
                      {topic.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label>
              {action === "remove" ? "要移出的专题" : "目标专题"}
              <select
                value={destination}
                disabled={change.isPending}
                onChange={(event) => setTargetId(event.target.value)}
              >
                <option value="">请选择专题</option>
                {possibleTargets.map((topic) => (
                  <option key={topic.id} value={topic.id}>
                    {topic.name}
                  </option>
                ))}
              </select>
            </label>
            {!possibleTargets.length && action === "add" && (
              <p className="muted">此论文已经归入所有现有专题。</p>
            )}
            {action === "move" && (
              <p className="muted">
                只移除指定来源的归属，其他专题和已建立的联系会保留。
              </p>
            )}
            {change.error && (
              <p role="alert" className="error-text">
                {errorMessage(change.error)}
              </p>
            )}
            <div className="topic-actions">
              <button
                type="submit"
                className="button primary"
                disabled={
                  !destination ||
                  (action === "move" && !sourceId) ||
                  change.isPending
                }
              >
                {change.isPending ? "正在更新…" : "应用归类"}
              </button>
            </div>
          </form>
        )}
      </div>
    </KnowledgeDialog>
  );
}
