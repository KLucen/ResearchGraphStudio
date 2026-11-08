import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";
import { BookOpen, LoaderCircle, MessageSquare, Search, X } from "lucide-react";
import { api, type PaperList } from "./api";
import {
  queryApi,
  type Attribution,
  type QueryAnswerView,
  type QueryBrowsePage,
  type QueryHistoryItem,
  type QueryPassage,
  type QueryPresentation,
  type QueryReference,
  type QueryRequest,
  type QuerySave,
  type QuerySourceDisplay,
} from "./queryApi";
import { QueryDerivedGraph } from "./QueryDerivedGraph";
import {
  PaperDisplayFilter,
  QueryPagination,
  matchesPapers,
  pageItems,
  type QueryPapers,
} from "./QueryBrowseControls";
import "./QueryPanel.css";

const text = (error: unknown) =>
  error instanceof Error ? error.message : String(error);
const attribution: Record<Attribution, string> = {
  paper_author: "论文作者主张",
  citation_report: "论文转述的观点",
  user_view: "个人观点",
  model_synthesis: "AI 综合解释",
};
const personalSourceLabel = (type: string) =>
  (
    ({
      note: "个人笔记",
      annotation: "个人批注评论",
      external: "外部阅读材料（科学来源未核验）",
    }) as Record<string, string>
  )[type];
const personalSourceNotice = (type: string) =>
  type === "annotation"
    ? "此来源仅为个人评论，关联的论文位置不使评论成为论文原文证据。"
    : type === "external"
      ? "此来源为已登记的外部材料快照，科学来源仍未核验。"
      : "此来源为个人笔记，保持个人归属。";
const states: Record<string, string> = {
  prepared: "证据已准备",
  not_started: "尚未生成",
  queued: "等待执行",
  running: "正在生成与核对证据",
  succeeded: "回答完成",
  failed: "生成失败",
  cancelled: "已取消",
  interrupted: "执行中断",
  insufficient: "依据不足",
};
const reasons: Record<string, string> = {
  exact_phrase: "精确短语",
  exact_term: "术语匹配",
  fts_bm25: "全文检索",
};

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

async function allHistory(projectId: string): Promise<QueryHistoryItem[]> {
  const items = new Map<string, QueryHistoryItem>();
  const seen = new Set<string>();
  let cursor: string | null = null;
  do {
    if (cursor && seen.has(cursor))
      throw new Error("问答历史分页已变化，请刷新后重试");
    if (cursor) seen.add(cursor);
    const page = await queryApi.history(projectId, cursor);
    page.items.forEach((item) => items.set(item.query_id, item));
    cursor = page.next_cursor;
  } while (cursor);
  return [...items.values()];
}

export function QueryPanel({
  projectId,
  connected,
  onGraphNode,
  onSettings,
}: {
  projectId: string;
  connected: boolean;
  onGraphNode: (id: string) => void;
  onSettings?: () => void;
}) {
  const client = useQueryClient();
  const storageKey = `researchgraph.query.active.${projectId}`;
  const [activeId, setActiveId] = useState(() => {
    try {
      return localStorage.getItem(storageKey) ?? "";
    } catch {
      return "";
    }
  });
  const [draftQuestion, setQuestion] = useState<string | null>(null);
  const [paperIds, setPaperIds] = useState<string[] | null>(null);
  const [personal, setPersonal] = useState<boolean | null>(null);
  const [allowNetwork, setAllowNetwork] = useState(false);
  const [selection, setSelection] = useState<Record<string, string[]>>({});
  const [kind, setKind] = useState<"synthesis" | "insight">("synthesis");
  const [target, setTarget] = useState("");
  const [showDerived, setShowDerived] = useState(false);
  const [savedId, setSavedId] = useState("");
  const [savedFilter, setSavedFilter] = useState<string[]>([]);
  const [savedPage, setSavedPage] = useState(1);
  const [detailPage, setDetailPage] = useState(1);
  const [detailFilter, setDetailFilter] = useState<string[]>([]);
  const [historyFilter, setHistoryFilter] = useState<string[]>([]);
  const [historyPage, setHistoryPage] = useState(1);
  const [reference, setReference] = useState<QueryReference | null>(null);
  const [annotationDraft, setAnnotationDraft] = useState<{
    id: string;
    value: string;
  } | null>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [focusRequest, setFocusRequest] = useState(0);
  const recordRef = useRef<HTMLElement | null>(null);
  const keys = useRef(new Map<string, string>());
  function operationKey(operation: string, body: unknown) {
    const signature = operation + JSON.stringify(body);
    let value = keys.current.get(signature);
    if (!value) {
      value = crypto.randomUUID();
      keys.current.set(signature, value);
    }
    return value;
  }
  useEffect(() => {
    try {
      if (activeId) localStorage.setItem(storageKey, activeId);
      else localStorage.removeItem(storageKey);
    } catch {
      /* Local history remains available through the engine. */
    }
  }, [activeId, storageKey]);
  const papers = useQuery({
    queryKey: ["query-papers", projectId],
    queryFn: () => allPapers(projectId),
    enabled: connected,
  });
  const models = useQuery({
    queryKey: ["model-settings"],
    queryFn: queryApi.models,
    enabled: connected,
  });
  const prepared = useQuery({
    queryKey: ["query-run", projectId, activeId],
    queryFn: () => queryApi.run(projectId, activeId),
    enabled: connected && !!activeId,
    retry: false,
  });
  const answer = useQuery({
    queryKey: ["query-answer", projectId, activeId],
    queryFn: () => queryApi.answer(projectId, activeId),
    enabled: connected && !!activeId,
    retry: false,
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.status ?? "")
        ? 1500
        : false,
  });
  useEffect(() => {
    if (
      activeId &&
      answer.data?.status &&
      !["not_started", "queued", "running"].includes(answer.data.status)
    ) {
      void client.invalidateQueries({ queryKey: ["query-history", projectId] });
    }
  }, [activeId, answer.data?.status, client, projectId]);
  const question =
    draftQuestion ?? prepared.data?.snapshot.request.question ?? "";
  const selectedPapers =
    paperIds ?? prepared.data?.snapshot.request.paper_ids ?? [];
  const includePersonal =
    personal ?? prepared.data?.snapshot.request.include_personal ?? false;
  const makeRequest = (purpose: "local" | "model"): QueryRequest => ({
    project_id: projectId,
    question: question.trim(),
    paper_ids: selectedPapers,
    include_personal: includePersonal,
    purpose,
    limit: 20,
  });
  const history = useQuery({
    queryKey: ["query-history", projectId],
    queryFn: () => allHistory(projectId),
    enabled: connected,
    retry: false,
  });
  const documents = useQuery({
    queryKey: ["query-documents", projectId, includePersonal],
    queryFn: () => queryApi.documents(projectId, includePersonal),
    enabled: connected,
  });
  const saved = useQuery({
    queryKey: ["query-saved", projectId, includePersonal],
    queryFn: () => queryApi.saved(projectId, includePersonal),
    enabled: connected,
  });
  const savedDetail = useQuery({
    queryKey: ["query-saved-detail", projectId, savedId, includePersonal],
    queryFn: () => queryApi.savedDetail(projectId, savedId, includePersonal),
    enabled: connected && !!savedId,
    retry: false,
  });
  const targetDocuments = useMemo(
    () => [
      ...new Map(
        (documents.data?.items ?? [])
          .filter((passage) => passage.content_state === "valid")
          .map((passage) => [passage.document_id, passage]),
      ).values(),
    ],
    [documents.data],
  );
  const preview = useMutation({
    mutationFn: async () => {
      const request = makeRequest("local");
      const result = await queryApi.browse(projectId, {
        request,
        page: 1,
        page_size: 10,
        display_paper_ids: [],
      });
      return { ...result, request };
    },
  });
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["query-answer", projectId] });
    void client.invalidateQueries({ queryKey: ["query-history", projectId] });
    void client.invalidateQueries({ queryKey: ["jobs", projectId] });
  };
  const generate = useMutation({
    mutationFn: async (continueRequested: boolean) => {
      let id = activeId;
      if (!continueRequested) {
        const body = makeRequest("model");
        const result = await queryApi.prepare(
          projectId,
          body,
          operationKey("prepare", body),
        );
        id = result.query_id;
        setActiveId(id);
        client.setQueryData(["query-run", projectId, id], result);
        if (result.status === "insufficient")
          throw new Error(
            "证据上下文不足，请查看命中与覆盖限制；没有发出模型请求",
          );
      }
      if (!id) throw new Error("请先选择一条可继续的问答");
      const result = await queryApi.generate(
        projectId,
        id,
        continueRequested,
        operationKey("generate", [id, continueRequested]),
      );
      return result;
    },
    onSuccess: refresh,
  });
  const cancel = useMutation({
    mutationFn: () => {
      if (!answer.data?.job_id) throw new Error("当前没有可取消的任务");
      return api.jobAction(answer.data.job_id, "cancel", crypto.randomUUID());
    },
    onSuccess: refresh,
  });
  const save = useMutation({
    mutationFn: async () => {
      const value = answer.data?.answer;
      if (!value || value.status !== "validated")
        throw new Error("只有证据终验通过的回答可以保存");
      const document = targetDocuments.find(
        (item) => item.document_id === target,
      );
      if (target && !document) throw new Error("目标文档已不可用，请重新选择");
      const body: QuerySave = {
        source_query_id: activeId,
        answer_version_id: value.answer_version_id,
        expected_input_hash: value.input_hash,
        selected_passage_refs: selection[value.answer_version_id] ?? [],
        kind,
        target_document_id: document?.document_id ?? null,
        base_version_id: document?.version_id ?? null,
      };
      return queryApi.save(
        projectId,
        activeId,
        body,
        operationKey("save", body),
      );
    },
    onSuccess: (result) => {
      setSavedId(result.saved_id);
      void client.invalidateQueries({ queryKey: ["query-saved", projectId] });
      void client.invalidateQueries({
        queryKey: ["query-documents", projectId],
      });
      void client.invalidateQueries({ queryKey: ["query-derived", projectId] });
    },
  });
  const updateSavedCaches = () => {
    void client.invalidateQueries({ queryKey: ["query-saved", projectId] });
    void client.invalidateQueries({ queryKey: ["query-documents", projectId] });
    void client.invalidateQueries({ queryKey: ["query-derived", projectId] });
  };
  const annotate = useMutation({
    mutationFn: () => {
      const item = savedDetail.data;
      if (!item) throw new Error("请先选择已保存的阅读知识");
      const body = {
        annotation:
          annotationDraft?.id === item.saved_id
            ? annotationDraft.value
            : (item.annotation ?? ""),
        expected_revision: item.metadata_revision ?? 0,
      };
      return queryApi.annotate(
        projectId,
        item.saved_id,
        body,
        operationKey("annotate", [item.saved_id, body]),
        includePersonal,
      );
    },
    onSuccess: (item) => {
      client.setQueryData(
        ["query-saved-detail", projectId, item.saved_id, includePersonal],
        item,
      );
      setAnnotationDraft(null);
      updateSavedCaches();
    },
  });
  const removeSaved = useMutation({
    mutationFn: () => {
      const item = savedDetail.data;
      if (!item) throw new Error("请先选择已保存的阅读知识");
      const body = { expected_revision: item.metadata_revision ?? 0 };
      return queryApi.remove(
        projectId,
        item.saved_id,
        body,
        operationKey("remove", [item.saved_id, body]),
        includePersonal,
      );
    },
    onSuccess: () => {
      setSavedId("");
      setAnnotationDraft(null);
      setConfirmRemove(false);
      updateSavedCaches();
    },
  });
  function openQuery(id: string) {
    setActiveId(id);
    setQuestion(null);
    setPaperIds(null);
    setPersonal(null);
    setAllowNetwork(false);
    setReference(null);
    preview.reset();
    generate.reset();
    save.reset();
    setFocusRequest((value) => value + 1);
    void client.invalidateQueries({ queryKey: ["query-run", projectId, id] });
    void client.invalidateQueries({
      queryKey: ["query-answer", projectId, id],
    });
  }
  function openSaved(id: string) {
    setSavedId(id);
    setDetailPage(1);
    setDetailFilter([]);
    setAnnotationDraft(null);
    setConfirmRemove(false);
    annotate.reset();
    removeSaved.reset();
  }
  useEffect(() => {
    if (!focusRequest || !activeId || prepared.isPending) return;
    recordRef.current?.scrollIntoView?.({ block: "start" });
    recordRef.current?.focus({ preventScroll: true });
  }, [activeId, focusRequest, prepared.isPending]);
  function changed() {
    setActiveId("");
    setAllowNetwork(false);
    setReference(null);
    preview.reset();
    generate.reset();
    save.reset();
  }
  const busy =
    generate.isPending ||
    ["queued", "running"].includes(answer.data?.status ?? "");
  const configured = !models.error && !!models.data?.roles.reasoning;
  const references = prepared.error
    ? []
    : (prepared.data?.snapshot.context.references ?? []);
  const browseRequest = prepared.error
    ? undefined
    : activeId
      ? prepared.data?.snapshot.request
      : preview.data?.request;
  const presentation = prepared.data?.presentation;
  const visibleSaved = saved.error
    ? []
    : (saved.data?.items ?? []).filter((item) =>
        matchesPapers(item.paper_ids, savedFilter),
      );
  const savedPagination = pageItems(visibleSaved, savedPage);
  const visibleHistory = history.error
    ? []
    : (history.data ?? []).filter((item) =>
        matchesPapers(item.paper_ids, historyFilter),
      );
  const historyPagination = pageItems(visibleHistory, historyPage);
  const visibleDetail = (savedDetail.data?.passages ?? []).filter((item) =>
    matchesPapers(item.paper_ids ?? savedDetail.data?.paper_ids, detailFilter),
  );
  const detailPagination = pageItems(visibleDetail, detailPage);
  const value =
    answer.error || prepared.error || prepared.isPending || !prepared.data
      ? undefined
      : answer.data?.answer;
  const chosen = (value && selection[value.answer_version_id]) ?? [];
  const errors = [
    papers.error,
    models.error,
    prepared.error,
    answer.error,
    preview.error,
    generate.error,
    cancel.error,
    save.error,
    annotate.error,
    removeSaved.error,
  ].filter(Boolean);
  return (
    <section className="query-workspace" aria-label="项目问答">
      <form
        className="query-composer"
        onSubmit={(event) => {
          event.preventDefault();
          if (connected && question.trim() && !busy) preview.mutate();
        }}
      >
        <div className="query-heading">
          <h2>
            <MessageSquare size={20} />
            论文问答
          </h2>
          <span className="quiet-note">默认只读 · 保存需单独操作</span>
        </div>
        <label className="field">
          研究问题
          <textarea
            rows={3}
            maxLength={12000}
            value={question}
            disabled={busy}
            placeholder="例如：这些论文的方法分别在什么条件下有效？"
            onChange={(event) => {
              setQuestion(event.target.value);
              changed();
            }}
          />
        </label>
        <details className="query-scope">
          <summary>
            论文范围 ·{" "}
            {selectedPapers.length
              ? `已选 ${selectedPapers.length} 篇`
              : "全部论文"}
          </summary>
          <button
            type="button"
            className="text-button"
            disabled={busy}
            onClick={() => {
              setPaperIds([]);
              changed();
            }}
          >
            使用全部论文
          </button>
          <div className="query-paper-options">
            {papers.data?.map((paper) => (
              <label key={paper.id}>
                <input
                  type="checkbox"
                  checked={selectedPapers.includes(paper.id)}
                  disabled={busy}
                  onChange={(event) => {
                    setPaperIds(
                      event.target.checked
                        ? [...selectedPapers, paper.id]
                        : selectedPapers.filter((id) => id !== paper.id),
                    );
                    changed();
                  }}
                />
                {paper.title}
              </label>
            ))}
            {!papers.data?.length && (
              <p className="quiet-note">
                项目尚无论文，先在文献与阅读中选择来源。
              </p>
            )}
          </div>
        </details>
        <label className="query-check">
          <input
            type="checkbox"
            checked={includePersonal}
            disabled={busy}
            onChange={(event) => {
              setPersonal(event.target.checked);
              changed();
            }}
          />
          同时检索已授权的个人资料（笔记、批注评论与外部材料）及个人综合
        </label>
        {includePersonal && (
          <p className="quiet-note">
            个人内容保持个人归属，仅使用当前用途已授权的材料，包括已保存 Wiki
            中的个人来源依赖。本地读取与模型外发分别授权；外部材料登记不代表科学来源已核验。
          </p>
        )}
        <label className="query-check">
          <input
            type="checkbox"
            checked={allowNetwork}
            disabled={busy}
            onChange={(event) => setAllowNetwork(event.target.checked)}
          />
          允许本次将问题与必要来源资料发送给全局 Reasoning 模型
        </label>
        <div className="query-actions">
          <button
            className="button secondary"
            disabled={
              !connected || !question.trim() || busy || preview.isPending
            }
          >
            <Search size={16} />
            {preview.isPending ? "检索中…" : "本地预览来源"}
          </button>
          <button
            type="button"
            className="button primary"
            disabled={
              !connected ||
              !question.trim() ||
              !configured ||
              !allowNetwork ||
              busy
            }
            onClick={() => generate.mutate(false)}
          >
            {busy ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <MessageSquare size={16} />
            )}
            生成有据回答
          </button>
        </div>
        {!configured && models.isSuccess && (
          <p className="query-warning">
            尚未选择全局 Reasoning 模型。本地检索仍可使用。
            {onSettings && (
              <button
                type="button"
                className="text-button"
                onClick={onSettings}
              >
                打开设置与诊断
              </button>
            )}
          </p>
        )}
      </form>
      {errors.map((error, index) => (
        <p className="error-banner" role="alert" key={index}>
          {text(error)}
        </p>
      ))}
      {(browseRequest || activeId) && (
        <section
          className="query-record"
          aria-label="本次问答记录"
          tabIndex={-1}
          ref={recordRef}
        >
          <header className="query-record-heading">
            <small>{activeId ? "本地问答记录" : "本地来源预览"}</small>
            <h3>
              {(activeId
                ? prepared.data?.snapshot.request.question
                : question) || "正在读取问题…"}
            </h3>
            <p className="quiet-note">
              问题、来源与回答共同保留在本地历史中；选段保存后才加入阅读知识。
            </p>
            {activeId && (prepared.isPending || answer.isPending) && (
              <p role="status">正在读取问题、来源与回答…</p>
            )}
          </header>
          {browseRequest && (
            <RetrievalPreview
              key={activeId || JSON.stringify(browseRequest)}
              projectId={projectId}
              connected={connected}
              request={{ ...browseRequest, purpose: "local" }}
              initialPage={!activeId ? preview.data : undefined}
              papers={papers.data ?? []}
              onGraphNode={onGraphNode}
            />
          )}
          {activeId && (
            <section className="query-answer" aria-label="问答结果">
              <div className="query-heading">
                <h3>
                  {prepared.isPending
                    ? "正在读取问答"
                    : (states[
                        answer.data?.status ?? prepared.data?.status ?? ""
                      ] ?? "正在读取问答")}
                </h3>
                <small>知识不会因提问自动保存</small>
              </div>
              {prepared.data?.snapshot.model?.model && (
                <p className="quiet-note">
                  本次模型：{prepared.data.snapshot.model.model}
                </p>
              )}
              {busy && (
                <p role="status">
                  <LoaderCircle className="spin" size={16} />{" "}
                  {generate.isPending
                    ? "正在准备证据与启动任务…"
                    : "模型任务处理中，完成后将执行引用与来源终验。"}
                </p>
              )}
              {answer.data?.error && (
                <p role="alert" className="query-warning">
                  {answer.data.error}
                  {answer.data.error_code && (
                    <small> · {answer.data.error_code}</small>
                  )}
                </p>
              )}
              <div className="query-actions">
                {answer.data?.can_continue && (
                  <button
                    type="button"
                    className="button secondary"
                    disabled={!connected || busy || !allowNetwork}
                    onClick={() => generate.mutate(true)}
                  >
                    继续未完成问答
                  </button>
                )}
                {["queued", "running"].includes(answer.data?.status ?? "") && (
                  <button
                    type="button"
                    className="button secondary"
                    disabled={cancel.isPending}
                    onClick={() => cancel.mutate()}
                  >
                    取消本次生成
                  </button>
                )}
              </div>
              {answer.data && <QueryUsage result={answer.data} />}
              {value?.status === "validated" ? (
                <>
                  <p className="quiet-note">
                    {value.knowledge_status === "insufficient"
                      ? "当前证据不足以完整回答"
                      : value.knowledge_status === "mixed_sources"
                        ? "包含个人资料，已与论文作者主张区分"
                        : "引用身份与证据已校验；作者主张不等于科学事实"}
                  </p>
                  <AnswerPassages
                    key={value.answer_version_id}
                    passages={value.passages}
                    references={references}
                    presentation={presentation}
                    papers={papers.data ?? []}
                    chosen={chosen}
                    onSelection={(refs) =>
                      setSelection({
                        ...selection,
                        [value.answer_version_id]: refs,
                      })
                    }
                    onReference={setReference}
                  />
                  {(value.limitations.length > 0 ||
                    !!prepared.data?.snapshot.context.coverage_gaps.length) && (
                    <aside className="query-warning" aria-label="回答限制">
                      <strong>限制与覆盖范围</strong>
                      <ul>
                        {[
                          ...new Set([
                            ...value.limitations,
                            ...(prepared.data?.snapshot.context.coverage_gaps ??
                              []),
                          ]),
                        ].map((item, index) => (
                          <li key={index}>{item}</li>
                        ))}
                      </ul>
                    </aside>
                  )}
                  {value.passages.length > 0 && (
                    <div className="query-save">
                      <h4>保存阅读知识</h4>
                      <p className="quiet-note">
                        保存所选段落及来源依赖，原论文主张保持；此操作不写入
                        Obsidian 文件。
                      </p>
                      <div className="query-actions">
                        <label>
                          类型{" "}
                          <select
                            aria-label="保存知识类型"
                            value={kind}
                            onChange={(event) =>
                              setKind(
                                event.target.value as "synthesis" | "insight",
                              )
                            }
                          >
                            <option value="synthesis">阅读综合</option>
                            <option value="insight">阅读洞见</option>
                          </select>
                        </label>
                        <label>
                          目标{" "}
                          <select
                            aria-label="保存目标文档"
                            value={target}
                            onChange={(event) => setTarget(event.target.value)}
                          >
                            <option value="">新增独立阅读知识</option>
                            {targetDocuments.map((document) => (
                              <option
                                key={document.document_id}
                                value={document.document_id}
                              >
                                追加至：{document.title}
                              </option>
                            ))}
                          </select>
                        </label>
                        <button
                          type="button"
                          className="button primary"
                          disabled={
                            !connected ||
                            !chosen.length ||
                            save.isPending ||
                            !!prepared.error ||
                            !!answer.error
                          }
                          onClick={() => save.mutate()}
                        >
                          {save.isPending
                            ? "正在保存…"
                            : `保存所选 ${chosen.length} 段`}
                        </button>
                      </div>
                      {target && (
                        <p className="query-warning">
                          仅更新你选择的内部文档，并核对其基线版本；不会覆盖旧段落或导出文件。
                        </p>
                      )}
                      {save.isSuccess && (
                        <p role="status">
                          阅读知识已保存，可在下方查看，退出重开仍可读取。
                        </p>
                      )}
                    </div>
                  )}
                </>
              ) : !prepared.isPending &&
                !!prepared.data &&
                !busy &&
                answer.data &&
                answer.data.status !== "not_started" ? (
                <p className="quiet-note">
                  本次尚无通过终验的回答；未验证文本不能保存为知识。
                </p>
              ) : null}
            </section>
          )}
        </section>
      )}
      <section className="query-library" aria-label="已保存阅读知识">
        <div className="query-heading">
          <h3>
            <BookOpen size={18} />
            已保存阅读知识
          </h3>
          <label className="query-check">
            <input
              type="checkbox"
              checked={showDerived}
              onChange={(event) => setShowDerived(event.target.checked)}
            />
            显示独立衍生图层
          </label>
        </div>
        <p className="quiet-note">
          引用关系用于回溯来源，不是论文作者的新结论；隐藏图层不影响保存内容检索。
        </p>
        {removeSaved.isSuccess && (
          <p role="status">
            保存内容已移除；原问答、论文证据与模型历史仍保留。
          </p>
        )}
        {saved.isError && <p role="alert">{text(saved.error)}</p>}
        <PaperDisplayFilter
          label="保存内容论文筛选"
          papers={papers.data ?? []}
          value={savedFilter}
          onChange={(ids) => {
            setSavedFilter(ids);
            setSavedPage(1);
          }}
        />
        <QueryPagination
          label="保存内容"
          total={visibleSaved.length}
          page={savedPagination.current}
          onChange={setSavedPage}
          disabled={saved.isPending}
        />
        {!visibleSaved.length && !saved.isPending && (
          <p className="quiet-note">尚未保存阅读知识。</p>
        )}
        <div className="query-saved-list">
          {!saved.error &&
            savedPagination.items.map((item) => (
              <button
                type="button"
                className={
                  savedId === item.saved_id
                    ? "query-saved-item selected"
                    : "query-saved-item"
                }
                key={item.saved_id}
                onClick={() => openSaved(item.saved_id)}
              >
                <strong>{item.title}</strong>
                <small>
                  {item.kind === "insight" ? "阅读洞见" : "阅读综合"} · 版本{" "}
                  {item.revision} ·{" "}
                  {item.content_state === "valid"
                    ? "来源有效"
                    : "来源需重新核对"}
                </small>
              </button>
            ))}
        </div>
        {savedDetail.error && <p role="alert">{text(savedDetail.error)}</p>}
        {savedId && savedDetail.isPending && (
          <p role="status">正在读取已保存的阅读知识…</p>
        )}
        {!savedDetail.error &&
          savedDetail.data &&
          matchesPapers(savedDetail.data.paper_ids, savedFilter) && (
            <article className="query-saved-detail">
              <h4>{savedDetail.data.title}</h4>
              <PaperDisplayFilter
                label="保存详情论文筛选"
                papers={papers.data ?? []}
                value={detailFilter}
                onChange={(ids) => {
                  setDetailFilter(ids);
                  setDetailPage(1);
                }}
              />
              <QueryPagination
                label="保存详情"
                total={visibleDetail.length}
                page={detailPagination.current}
                onChange={setDetailPage}
              />
              {detailPagination.items.map((passage) => (
                <div key={passage.id}>
                  <small>{attribution[passage.attribution]}</small>
                  <p>{passage.text}</p>
                  {passage.caveats.length > 0 && (
                    <p className="quiet-note">{passage.caveats.join("；")}</p>
                  )}
                </div>
              ))}
              <button
                type="button"
                className="text-button"
                onClick={() => openQuery(savedDetail.data.source_query_id)}
              >
                查看原问答与引用
              </button>
              <div className="query-annotation">
                <label className="field">
                  个人批注
                  <textarea
                    rows={3}
                    maxLength={12000}
                    disabled={annotate.isPending || removeSaved.isPending}
                    value={
                      annotationDraft?.id === savedDetail.data.saved_id
                        ? annotationDraft.value
                        : (savedDetail.data.annotation ?? "")
                    }
                    placeholder="记录你的理解、疑问或后续阅读方向"
                    onChange={(event) => {
                      setAnnotationDraft({
                        id: savedDetail.data.saved_id,
                        value: event.target.value,
                      });
                      annotate.reset();
                    }}
                  />
                </label>
                <p className="quiet-note">
                  批注属于个人观点，与模型回答和论文主张分别保存。
                </p>
                <div className="query-actions">
                  <button
                    type="button"
                    className="button secondary"
                    disabled={
                      !connected ||
                      annotate.isPending ||
                      removeSaved.isPending ||
                      annotationDraft?.id !== savedDetail.data.saved_id ||
                      annotationDraft.value ===
                        (savedDetail.data.annotation ?? "")
                    }
                    onClick={() => annotate.mutate()}
                  >
                    {annotate.isPending ? "保存批注中…" : "保存个人批注"}
                  </button>
                  <button
                    type="button"
                    className="text-button query-remove"
                    disabled={
                      !connected || annotate.isPending || removeSaved.isPending
                    }
                    onClick={() => setConfirmRemove(true)}
                  >
                    移除保存内容
                  </button>
                </div>
                {annotate.isSuccess && <p role="status">个人批注已保存。</p>}
                {confirmRemove && (
                  <div
                    className="query-warning"
                    role="group"
                    aria-label="确认移除保存内容"
                  >
                    <p>
                      将从已保存阅读知识、检索和衍生图层中移除这项内容。原问答、论文证据与模型历史仍保留。
                    </p>
                    <div className="query-actions">
                      <button
                        type="button"
                        className="button secondary"
                        disabled={removeSaved.isPending}
                        onClick={() => removeSaved.mutate()}
                      >
                        {removeSaved.isPending ? "移除中…" : "确认移除"}
                      </button>
                      <button
                        type="button"
                        className="text-button"
                        disabled={removeSaved.isPending}
                        onClick={() => setConfirmRemove(false)}
                      >
                        取消移除
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </article>
          )}
        {showDerived && (
          <QueryDerivedGraph
            projectId={projectId}
            connected={connected}
            includePersonal={includePersonal}
            onGraphNode={onGraphNode}
            onSaved={openSaved}
            allowedSavedIds={
              savedFilter.length
                ? visibleSaved.map((item) => item.saved_id)
                : undefined
            }
          />
        )}
      </section>
      <details className="query-history" open>
        <summary>本地问答历史 · {visibleHistory.length}</summary>
        <p className="quiet-note">
          这里记录问题与回答；完整任务记录集中在“文献与阅读”。历史不会自动成为知识。
        </p>
        {history.error && (
          <div>
            <p role="alert">{text(history.error)}</p>
            <button
              type="button"
              className="text-button"
              disabled={!connected || history.isFetching}
              onClick={() => void history.refetch()}
            >
              重新读取问答历史
            </button>
          </div>
        )}
        <PaperDisplayFilter
          label="历史论文筛选"
          papers={papers.data ?? []}
          value={historyFilter}
          onChange={(ids) => {
            setHistoryFilter(ids);
            setHistoryPage(1);
          }}
        />
        <QueryPagination
          label="问答历史"
          total={visibleHistory.length}
          page={historyPagination.current}
          onChange={setHistoryPage}
          disabled={history.isPending}
        />
        {history.isPending && <p role="status">正在读取完整问答历史…</p>}
        {historyPagination.items.map((item) => (
          <button
            type="button"
            className="query-history-item"
            key={item.query_id}
            onClick={() => openQuery(item.query_id)}
          >
            <span>{item.question}</span>
            <small>
              {states[item.status] ?? item.status} ·{" "}
              {new Date(item.created_at).toLocaleString("zh-CN")}
            </small>
          </button>
        ))}
      </details>
      {reference &&
        references.some(
          (item) => item.ref === reference.ref && item.id === reference.id,
        ) && (
          <QueryEvidence
            source={reference}
            display={presentation?.references[reference.ref]}
            references={references}
            connected={connected}
            onSource={setReference}
            onClose={() => setReference(null)}
            onGraphNode={onGraphNode}
          />
        )}
    </section>
  );
}

function RetrievalPreview({
  projectId,
  connected,
  request,
  initialPage,
  papers,
  onGraphNode,
}: {
  projectId: string;
  connected: boolean;
  request: QueryRequest;
  initialPage?: QueryBrowsePage;
  papers: QueryPapers;
  onGraphNode: (id: string) => void;
}) {
  const [filter, setFilter] = useState<string[]>([]);
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const resultHash = useRef<string | null>(initialPage?.result_hash ?? null);
  const results = useQuery({
    queryKey: ["query-browse", projectId, request, filter, page, refresh],
    queryFn: () =>
      queryApi.browse(projectId, {
        request,
        page,
        page_size: 10,
        display_paper_ids: filter,
        expected_result_hash: resultHash.current,
      }),
    enabled: connected,
    retry: false,
    initialData:
      !filter.length && page === 1 && !refresh ? initialPage : undefined,
    staleTime: 0,
  });
  const data = results.error ? undefined : results.data;
  useEffect(() => {
    if (data) resultHash.current = data.result_hash;
  }, [data]);
  const refreshResults = () => {
    resultHash.current = null;
    setPage(1);
    setRefresh((value) => value + 1);
  };
  return (
    <details className="query-retrieval" open>
      <summary>来源预览 · 本筛选共 {data?.total ?? 0} 个命中</summary>
      <p className="quiet-note">
        展示本问题在当前来源中的全部检索命中；每页10条。回答引用仍以生成时的证据清单为准，翻页和展示筛选不改变模型输入。
      </p>
      <PaperDisplayFilter
        label="来源论文筛选"
        papers={papers}
        value={filter}
        onChange={(ids) => {
          resultHash.current = null;
          setFilter(ids);
          setPage(1);
        }}
      />
      {data && (
        <p className="quiet-note">
          本问题全部来源共 {data.independent_sources.length}{" "}
          个独立根来源，图谱补充 {data.graph_node_count}{" "}
          个相关知识及完整合法支撑；同一来源的
          Wiki/综合不重复计数。卡片标记反映当前默认图谱，不受画布分页影响。
        </p>
      )}
      <QueryPagination
        label="来源预览"
        total={data?.total ?? 0}
        page={data?.page ?? page}
        onChange={setPage}
        disabled={results.isFetching}
      />
      {results.isFetching && <p role="status">正在核验与读取检索结果…</p>}
      {results.error && (
        <div className="query-warning" role="alert">
          {text(results.error)}
          <button
            type="button"
            className="text-button"
            onClick={refreshResults}
          >
            刷新全部检索结果
          </button>
        </div>
      )}
      {data && !data.hits.length && (
        <p>本论文筛选下未找到可用依据，请调整展示范围或问题。</p>
      )}
      {data?.hits.map((hit) => {
        const display = data.presentation.hits[hit.entry_id];
        return (
          <article key={hit.entry_id}>
            {display?.title && <h4>{sourceTitle(display)}</h4>}
            <small>
              {(
                {
                  knowledge: "论文知识",
                  chunk: "原文",
                  wiki: "Wiki",
                  synthesis: "阅读综合",
                  note: "个人笔记",
                  annotation: "个人批注评论",
                  external: "外部阅读材料（科学来源未核验）",
                  paper: "论文题名",
                } as Record<string, string>
              )[hit.source_kind] ?? hit.source_kind}{" "}
              ·{" "}
              {hit.reasons
                .map((reason) => reasons[reason] ?? reason)
                .join("、")}
            </small>
            {personalSourceLabel(hit.source_kind) && (
              <p className="quiet-note">
                {personalSourceNotice(hit.source_kind)}
              </p>
            )}
            <GraphPresence display={display} />
            <SourceSummary display={display} />
            <details className="query-original" open>
              <summary>对照原文</summary>
              <blockquote>{display?.original ?? hit.text}</blockquote>
            </details>
            {hit.source_kind === "knowledge" && (
              <button
                type="button"
                className="text-button"
                onClick={() => onGraphNode(hit.object_id)}
              >
                在图谱中定位
              </button>
            )}
          </article>
        );
      })}
    </details>
  );
}

function GraphPresence({ display }: { display?: QuerySourceDisplay }) {
  const presence = display?.graph_presence;
  const label = !presence
    ? "图谱状态暂未核验"
    : presence.state === "not_applicable"
      ? "独立来源 · 不适用论文节点标记"
      : presence.state === "retrieval_only"
        ? "未进入默认图谱 · 仍可检索"
        : presence.representation === "evidence"
          ? "图谱已有知识引用的原文 · 非独立节点"
          : "已在默认图谱中";
  return (
    <p className={`query-graph-presence ${presence?.state ?? "unknown"}`}>
      {label}
    </p>
  );
}

function sourcePaperIds(
  source: QueryReference,
  references: QueryReference[],
  presentation?: QueryPresentation,
): string[] {
  const display = presentation?.references[source.ref];
  const ids = new Set([
    ...(display?.paper_ids ?? []),
    ...(source.paper_id ? [source.paper_id] : []),
    ...(display?.paper_id ? [display.paper_id] : []),
  ]);
  for (const eid of source.evidence_ids ?? []) {
    const evidence = references.find(
      (item) => item.type === "evidence" && item.id === eid,
    );
    if (evidence?.paper_id) ids.add(evidence.paper_id);
  }
  return [...ids].sort();
}

function AnswerPassages({
  passages,
  references,
  presentation,
  papers,
  chosen,
  onSelection,
  onReference,
}: {
  passages: QueryPassage[];
  references: QueryReference[];
  presentation?: QueryPresentation;
  papers: QueryPapers;
  chosen: string[];
  onSelection: (refs: string[]) => void;
  onReference: (ref: QueryReference) => void;
}) {
  const [filter, setFilter] = useState<string[]>([]);
  const [page, setPage] = useState(1);
  const rows = passages
    .map((passage) => {
      const ids = [
        ...new Set(
          passage.source_refs.flatMap((ref) => {
            const source = references.find((item) => item.ref === ref);
            return source
              ? sourcePaperIds(source, references, presentation)
              : [];
          }),
        ),
      ].sort();
      return {
        passage,
        ids,
        group: ids.length > 1 ? "cross" : ids.length ? ids[0] : "other",
      };
    })
    .filter((row) => matchesPapers(row.ids, filter));
  const groupOrder = [...new Set(rows.map((row) => row.group))].sort((a, b) => {
    const rank = (id: string) =>
      id === "cross"
        ? papers.length
        : id === "other"
          ? papers.length + 1
          : papers.findIndex((paper) => paper.id === id);
    return rank(a) - rank(b);
  });
  const ordered = groupOrder.flatMap((group) =>
    rows.filter((row) => row.group === group),
  );
  const paged = pageItems(ordered, page);
  return (
    <div className="query-answer-passages">
      <PaperDisplayFilter
        label="回答论文筛选"
        papers={papers}
        value={filter}
        onChange={(ids) => {
          setFilter(ids);
          setPage(1);
        }}
      />
      <p className="quiet-note">
        已选择 {chosen.length}{" "}
        段保存（包含其他页与被筛选隐藏的选段）。跨论文综合保留完整表述，只显示一次。
      </p>
      <QueryPagination
        label="回答段落"
        total={rows.length}
        page={paged.current}
        onChange={setPage}
      />
      {!rows.length && <p className="quiet-note">本论文筛选下没有回答段落。</p>}
      {groupOrder.map((group) => {
        const groupRows = paged.items.filter((row) => row.group === group);
        if (!groupRows.length) return null;
        const title =
          group === "cross"
            ? "跨论文综合"
            : group === "other"
              ? "个人资料与未归属来源"
              : (papers.find((paper) => paper.id === group)?.title ??
                "论文依据");
        return (
          <section
            className="query-paper-answer"
            aria-label={`回答分组：${title}`}
            key={group}
          >
            <h4>{title}</h4>
            {groupRows.map(({ passage, ids }) => (
              <article className="query-passage" key={passage.local_ref}>
                {group === "cross" && (
                  <p className="quiet-note">
                    涉及论文：
                    {ids
                      .map(
                        (id) =>
                          papers.find((paper) => paper.id === id)?.title ??
                          "论文依据",
                      )
                      .join("、")}
                  </p>
                )}
                <label className="query-passage-select">
                  <input
                    type="checkbox"
                    checked={chosen.includes(passage.local_ref)}
                    onChange={(event) =>
                      onSelection(
                        event.target.checked
                          ? [...chosen, passage.local_ref]
                          : chosen.filter((id) => id !== passage.local_ref),
                      )
                    }
                  />
                  选择此段保存 · {attribution[passage.attribution]}
                </label>
                <p>{passage.text}</p>
                <CitationStack
                  passage={passage}
                  references={references}
                  presentation={presentation}
                  papers={papers}
                  onReference={onReference}
                />
                {passage.caveats.length > 0 && (
                  <ul className="query-caveats">
                    {passage.caveats.map((caveat, index) => (
                      <li key={index}>{caveat}</li>
                    ))}
                  </ul>
                )}
              </article>
            ))}
          </section>
        );
      })}
    </div>
  );
}

function CitationStack({
  passage,
  references,
  presentation,
  papers,
  onReference,
}: {
  passage: QueryPassage;
  references: QueryReference[];
  presentation?: QueryPresentation;
  papers: QueryPapers;
  onReference: (ref: QueryReference) => void;
}) {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [page, setPage] = useState(1);
  const paged = pageItems(passage.source_refs, page);
  const expandAll = () => {
    setOpen(true);
    setExpanded(
      Object.fromEntries(passage.source_refs.map((id) => [id, true])),
    );
  };
  return (
    <div className="query-citations">
      <div className="query-citation-actions">
        <button type="button" className="text-button" onClick={expandAll}>
          展开所有引用
        </button>
        <button
          type="button"
          className="text-button"
          onClick={() => {
            setOpen(false);
            setExpanded({});
          }}
        >
          收起所有引用
        </button>
      </div>
      <details className="query-citation-list" open={open}>
        <summary
          onClick={(event) => {
            event.preventDefault();
            setOpen((value) => !value);
          }}
        >
          引用 · {passage.source_refs.length} 条
        </summary>
        <QueryPagination
          label={`段落${passage.local_ref}引用`}
          total={passage.source_refs.length}
          page={paged.current}
          onChange={setPage}
        />
        {paged.items.map((id) => {
          const source = references.find((item) => item.ref === id);
          const index = passage.source_refs.indexOf(id) + 1;
          const display = presentation?.references[id];
          const title = source
            ? display
              ? sourceTitle(display)
              : (papers.find((paper) => paper.id === source.paper_id)?.title ??
                source.title ??
                "来源材料")
            : "来源当前不可用";
          return (
            <details
              className="query-citation-entry"
              key={id}
              open={!!expanded[id]}
            >
              <summary
                onClick={(event) => {
                  event.preventDefault();
                  setExpanded((before) => ({ ...before, [id]: !before[id] }));
                }}
              >
                引用 {index} · {title}
              </summary>
              {source ? (
                <QueryCitation
                  source={source}
                  display={display}
                  paperTitle={
                    papers.find((paper) => paper.id === source.paper_id)?.title
                  }
                  index={index}
                  answerSummary={passage.text}
                  onOpen={() => onReference(source)}
                />
              ) : (
                <p className="query-warning">
                  引用来源当前不可用，请重新核对来源授权。
                </p>
              )}
            </details>
          );
        })}
      </details>
    </div>
  );
}

function sourceTitle(display: QuerySourceDisplay, fallback?: string) {
  return [
    display.title || fallback,
    typeof display.page_index === "number"
      ? `第 ${display.page_index + 1} 页`
      : null,
    display.section_path?.join(" / "),
  ]
    .filter(Boolean)
    .join(" · ");
}

function SourceSummary({
  display,
  answerSummary,
}: {
  display?: QuerySourceDisplay;
  answerSummary?: string;
}) {
  const warnings = display?.layout_warnings?.map((warning) => (
    <p className="query-warning" key={warning}>
      {warning}
    </p>
  ));
  if (display?.summary_zh) {
    return (
      <>
        {warnings}
        <div className="query-source-summary">
          <strong>中文关键总结</strong>
          <p>{display.summary_zh}</p>
          <small>来自已保存的辅助中文知识，原文仍为权威依据</small>
        </div>
      </>
    );
  }
  if (answerSummary && /[\u3400-\u9fff]/.test(answerSummary)) {
    return (
      <>
        {warnings}
        <div className="query-source-summary">
          <strong>本次回答中文要点</strong>
          <p>{answerSummary}</p>
          <small>AI 综合本段引用的解释，不是原文逐句翻译。</small>
        </div>
      </>
    );
  }
  return (
    <>
      {warnings}
      <p className="quiet-note">
        暂无已保存的中文总结；可核对下方原文。本地预览不会额外调用模型。
      </p>
    </>
  );
}

function QueryCitation({
  source,
  display,
  paperTitle,
  index,
  answerSummary,
  onOpen,
}: {
  source: QueryReference;
  display?: QuerySourceDisplay;
  paperTitle?: string;
  index: number;
  answerSummary: string;
  onOpen: () => void;
}) {
  const personalLabel = personalSourceLabel(source.type);
  const sourceLabel = personalLabel ?? "论文依据";
  const originalTitle = display
    ? sourceTitle(display, source.title || paperTitle || sourceLabel)
    : [
        paperTitle || source.title || sourceLabel,
        typeof source.page_index === "number"
          ? `第 ${source.page_index + 1} 页`
          : null,
        source.section_path?.join(" / "),
      ]
        .filter(Boolean)
        .join(" · ");
  const title =
    personalLabel && originalTitle !== personalLabel
      ? `${personalLabel} · ${originalTitle}`
      : originalTitle;
  const original = display?.original ?? source.quote ?? source.text;
  return (
    <article className="query-source-card" aria-label={`引用 ${index}`}>
      <h4>
        引用 {index} · {title}
      </h4>
      {personalLabel && (
        <p className="quiet-note">{personalSourceNotice(source.type)}</p>
      )}
      <SourceSummary display={display} answerSummary={answerSummary} />
      {original && (
        <div className="query-original">
          <strong>{personalLabel ? "来源材料内容" : "对照原文"}</strong>
          <blockquote>{original}</blockquote>
        </div>
      )}
      <button type="button" className="query-citation" onClick={onOpen}>
        {personalLabel ? "查看来源材料" : "查看完整证据"} · {title}
      </button>
    </article>
  );
}

function QueryUsage({ result }: { result: QueryAnswerView }) {
  const reported = result.model_runs.some(
    (run) => typeof run.usage.total_tokens === "number",
  );
  const missing = result.model_runs.some(
    (run) => typeof run.usage.total_tokens !== "number",
  );
  const totals = result.model_runs.reduce(
    (sum, run) => ({
      prompt: sum.prompt + (run.usage.prompt_tokens ?? 0),
      completion: sum.completion + (run.usage.completion_tokens ?? 0),
      total: sum.total + (run.usage.total_tokens ?? 0),
    }),
    { prompt: 0, completion: 0, total: 0 },
  );
  return (
    <details className="query-usage">
      <summary>
        本次模型请求 {result.request_count}/{result.request_limit} · Token{" "}
        {reported
          ? `${totals.total.toLocaleString()}${missing ? "（部分已返回）" : ""}`
          : result.request_count
            ? "未返回"
            : "0"}{" "}
        · 费用未知
      </summary>
      <p>
        已返回用量：输入 {totals.prompt.toLocaleString()} · 输出{" "}
        {totals.completion.toLocaleString()}
        。供应商未提供金额或未返回用量的请求不能按零费用计算。
      </p>
      {result.model_runs.map((run) => (
        <p key={run.id}>
          请求 {run.sequence} · {states[run.status] ?? run.status}
          {run.duration_seconds !== null
            ? ` · ${run.duration_seconds.toFixed(1)} 秒`
            : ""}
          {run.error ? ` · ${run.error}` : ""}
        </p>
      ))}
    </details>
  );
}

function QueryEvidence({
  source,
  display,
  references,
  connected,
  onSource,
  onClose,
  onGraphNode,
}: {
  source: QueryReference;
  display?: QuerySourceDisplay;
  references: QueryReference[];
  connected: boolean;
  onSource: (source: QueryReference) => void;
  onClose: () => void;
  onGraphNode: (id: string) => void;
}) {
  const personalLabel = personalSourceLabel(source.type);
  const [openError, setOpenError] = useState("");
  const paper = useQuery({
    queryKey: ["paper", source.paper_id],
    queryFn: () => api.paper(source.paper_id!),
    enabled: connected && !!source.paper_id,
  });
  const preview = useQuery({
    queryKey: ["preview", source.id],
    queryFn: () => api.preview(source.id),
    enabled: connected && source.type === "evidence",
    retry: false,
  });
  const link = paper.data?.zotero_links?.find((item) =>
    /^[A-Z0-9]{8}$/.test(item.item_key ?? ""),
  );
  const library = link?.library_id.startsWith("users/")
    ? "library"
    : link?.library_id;
  const zoteroUrl =
    link && /^(library|groups\/[0-9]+)$/.test(library ?? "")
      ? `zotero://select/${library}/items/${link.item_key}`
      : null;
  return (
    <dialog
      className="dialog query-evidence"
      aria-label={personalLabel ? "回答来源材料" : "回答证据"}
      ref={(node) => {
        if (node && !node.open) node.showModal();
      }}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="query-heading">
        <h3>{personalLabel ?? "原文证据"}</h3>
        <button
          type="button"
          className="icon-button"
          aria-label={personalLabel ? "关闭来源材料" : "关闭证据"}
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>
      <p>
        {display?.title ??
          paper.data?.paper.title ??
          source.title ??
          personalLabel ??
          "已保存的来源片段"}
      </p>
      {personalLabel && (
        <p className="quiet-note">{personalSourceNotice(source.type)}</p>
      )}
      {typeof source.page_index === "number" && (
        <small>
          {source.type === "annotation" ? "评论关联位置：" : ""}PDF 第{" "}
          {source.page_index + 1} 页
          {typeof source.start === "number" && typeof source.end === "number"
            ? ` · 字符 [${source.start}, ${source.end})`
            : ""}
        </small>
      )}
      {source.section_path?.length ? (
        <small>{source.section_path.join(" / ")}</small>
      ) : null}
      <SourceSummary display={display} />
      <blockquote>
        {display?.original ??
          source.quote ??
          source.text ??
          "此引用提供来源身份，请展开其原文证据。"}
      </blockquote>
      {source.type === "node" && (
        <div className="query-citations">
          {references
            .filter(
              (item) =>
                item.type === "evidence" &&
                source.evidence_ids?.includes(item.id),
            )
            .map((item) => (
              <button
                type="button"
                className="query-citation"
                key={item.ref}
                onClick={() => onSource(item)}
              >
                查看原文证据
              </button>
            ))}
        </div>
      )}
      {source.current_file_status === "not_checked" && (
        <p className="quiet-note">
          使用已保存的不可变证据；本次尚未核验磁盘上的 PDF。
        </p>
      )}
      {source.file_state && (
        <p className="quiet-note">
          内部内容状态：{source.content_state} · 文件状态：{source.file_state}
        </p>
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
          当前无法打开 PDF 预览，保留片段仍可核对。{text(preview.error)}
        </p>
      )}
      {paper.error && <p role="alert">{text(paper.error)}</p>}
      <div className="query-actions">
        {zoteroUrl && (
          <button
            type="button"
            className="button secondary"
            onClick={() => {
              void invoke("open_zotero", { url: zoteroUrl }).catch((error) =>
                setOpenError(text(error)),
              );
            }}
          >
            在 Zotero 中打开
          </button>
        )}
        {source.type === "node" && (
          <button
            type="button"
            className="button secondary"
            onClick={() => {
              onClose();
              onGraphNode(source.id);
            }}
          >
            在图谱中定位
          </button>
        )}
      </div>
      {openError && <p role="alert">{openError}</p>}
    </dialog>
  );
}
