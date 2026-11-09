import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, request, type Job } from "./api";

type Collection = {
  key: string;
  data: { name: string; parentCollection: string | false };
};
type Choice = { item_key: string; attachment_key: string };
type Paper = {
  key: string;
  title: string;
  attachments: {
    key: string;
    title: string;
    filename: string;
    available: boolean;
  }[];
};
type Page = { items: Paper[]; next_start: number | null };
type ImportState = Choice & {
  job: Job;
  collection_key: string;
  library: string;
};
const statuses: Record<string, string> = {
  queued: "排队",
  running: "处理中",
  succeeded: "成功",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
};
const stages: Record<string, string> = {
  starting: "连接 Zotero",
  reading: "读取 PDF",
  parsing: "解析原文",
  saving: "保存与索引",
  indexing: "建立索引",
};

export function ZoteroImport({
  projectId,
  connected,
}: {
  projectId: string;
  connected: boolean;
}) {
  const client = useQueryClient();
  const [library, setLibrary] = useState("users/0");
  const [collection, setCollection] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [start, setStart] = useState(0);
  const [chosen, setChosen] = useState<Record<string, Choice>>({});
  const [mode, setMode] = useState<"reference" | "managed">("reference");
  const [enabled, setEnabled] = useState(false);
  const collections = useQuery({
    queryKey: ["zotero-collections", library],
    enabled: connected && enabled,
    queryFn: async () => {
      const all: Collection[] = [];
      for (let offset = 0; offset < 10000; offset += 50) {
        const page = await request<Collection[]>(
          "GET",
          `/api/v1/integrations/zotero/collections?library=${encodeURIComponent(library)}&start=${offset}`,
        );
        all.push(...page);
        if (page.length < 50) return all;
      }
      throw new Error("分类超过读取上限，请缩小文献库范围");
    },
    retry: false,
  });
  const papers = useQuery({
    queryKey: ["zotero-collection", library, collection, query, start],
    queryFn: () =>
      request<Page>("POST", "/api/v1/integrations/zotero/browse", {
        library,
        collection_key: collection,
        search: query,
        start,
      }),
    enabled: connected && enabled && !!collection,
    retry: false,
  });
  const history = useQuery({
    queryKey: ["zotero-imports", projectId],
    queryFn: () =>
      request<ImportState[]>(
        "GET",
        `/api/v1/projects/${projectId}/zotero-imports`,
      ),
    enabled: connected,
    refetchInterval: 2000,
  });
  const submit = useMutation({
    mutationFn: () =>
      request<ImportState[]>(
        "POST",
        `/api/v1/projects/${projectId}/zotero-imports`,
        {
          library,
          collection_key: collection,
          selections: Object.values(chosen),
          mode,
        },
        crypto.randomUUID(),
      ),
    onSuccess: () => {
      setChosen({});
      void client.invalidateQueries({
        queryKey: ["zotero-imports", projectId],
      });
      void client.invalidateQueries({ queryKey: ["papers", projectId] });
      void client.invalidateQueries({ queryKey: ["jobs", projectId] });
    },
  });
  const action = useMutation({
    mutationFn: ({ id, kind }: { id: string; kind: "retry" | "cancel" }) =>
      api.jobAction(id, kind, crypto.randomUUID()),
    onSuccess: () =>
      void client.invalidateQueries({
        queryKey: ["zotero-imports", projectId],
      }),
  });
  useEffect(() => {
    if (history.data?.some((item) => item.job.status === "succeeded"))
      void client.invalidateQueries({ queryKey: ["papers", projectId] });
  }, [history.data, client, projectId]);
  const choose = (rows: Choice[], checked: boolean) =>
    setChosen((old) => {
      const next = { ...old };
      rows.forEach((row) =>
        checked
          ? (next[row.attachment_key] = row)
          : delete next[row.attachment_key],
      );
      return next;
    });
  const jobs =
    history.data?.filter(
      (item) => item.collection_key === collection && item.library === library,
    ) ?? [];
  const complete = jobs.filter(
    (item) => !["queued", "running"].includes(item.job.status),
  ).length;
  return (
    <section className="zotero-import" aria-label="Zotero 批量导入">
      <h4>Zotero 分类批量导入</h4>
      <p>
        勾选附件即授权只读导入对应 PDF。原文件保持在 Zotero；Lite
        只解析、建立章节和全文索引。
      </p>
      <label>
        文献库
        <select
          value={library}
          disabled={enabled}
          onChange={(e) => setLibrary(e.target.value)}
        >
          <option value="users/0">我的文献库</option>
        </select>
      </label>
      <button
        className="button secondary"
        disabled={!connected || collections.isFetching}
        onClick={() => {
          setEnabled(true);
          if (enabled) void collections.refetch();
        }}
      >
        连接并读取分类
      </button>
      {collections.data && (
        <label>
          Collection
          <select
            value={collection}
            onChange={(e) => {
              setCollection(e.target.value);
              setStart(0);
              setChosen({});
              setQuery("");
              setSearch("");
            }}
          >
            <option value="">选择分类</option>
            {collections.data.map((item) => (
              <option key={item.key} value={item.key}>
                {item.data.name} · {item.key}
              </option>
            ))}
          </select>
        </label>
      )}
      {collection && (
        <>
          <form
            className="import-controls"
            onSubmit={(e) => {
              e.preventDefault();
              setQuery(search);
              setStart(0);
            }}
          >
            <label>
              搜索分类论文
              <input
                maxLength={120}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            <button
              className="button secondary"
              disabled={!connected || papers.isFetching}
            >
              搜索
            </button>
          </form>
          {papers.data?.items.map((paper) => (
            <article className="text-chunk" key={paper.key}>
              <label>
                <input
                  type="checkbox"
                  aria-label={`选择论文 ${paper.title}`}
                  checked={paper.attachments.some((a) => !!chosen[a.key])}
                  disabled={!paper.attachments.some((a) => a.available)}
                  onChange={(e) =>
                    choose(
                      paper.attachments
                        .filter((a) => a.available)
                        .map((a) => ({
                          item_key: paper.key,
                          attachment_key: a.key,
                        })),
                      e.target.checked,
                    )
                  }
                />{" "}
                <strong>{paper.title}</strong>
              </label>
              {paper.attachments.map((attachment) => (
                <label className="attachment-choice" key={attachment.key}>
                  <input
                    type="checkbox"
                    aria-label={`选择附件 ${attachment.key}`}
                    checked={!!chosen[attachment.key]}
                    disabled={!attachment.available}
                    onChange={(e) =>
                      choose(
                        [
                          {
                            item_key: paper.key,
                            attachment_key: attachment.key,
                          },
                        ],
                        e.target.checked,
                      )
                    }
                  />
                  {attachment.filename || attachment.title} · {attachment.key}
                  {attachment.available
                    ? ""
                    : "（本地不可用，请先在 Zotero 下载）"}
                </label>
              ))}
            </article>
          ))}
          <div className="import-controls">
            <button
              className="button secondary"
              disabled={!start || papers.isFetching}
              onClick={() => setStart(Math.max(0, start - 10))}
            >
              上一页
            </button>
            <button
              className="button secondary"
              disabled={papers.data?.next_start == null || papers.isFetching}
              onClick={() => setStart(papers.data?.next_start ?? start)}
            >
              下一页
            </button>
            <label>
              保存方式
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as typeof mode)}
              >
                <option value="reference">引用 Zotero 原文件</option>
                <option value="managed">复制到应用附件目录</option>
              </select>
            </label>
            <button
              className="button primary"
              disabled={
                !connected ||
                submit.isPending ||
                Object.keys(chosen).length === 0 ||
                Object.keys(chosen).length > 50
              }
              onClick={() => submit.mutate()}
            >
              仅解析 · 已选 {Object.keys(chosen).length} 个附件
            </button>
            <button className="text-button" onClick={() => setChosen({})}>
              清空选择
            </button>
          </div>
          {Object.keys(chosen).length > 50 && (
            <p role="alert">单批最多 50 个附件。</p>
          )}
        </>
      )}
      {jobs.length > 0 && (
        <>
          <p>
            本分类最近任务：{complete}/{jobs.length} 已结束，
            {jobs.filter((item) => item.job.status === "succeeded").length} 成功
          </p>
          <progress
            max={jobs.length}
            value={complete}
            aria-label="批量导入进度"
          />
          {jobs.map(({ job, attachment_key }) => (
            <article className="import-job" key={job.id}>
              <span>
                {attachment_key} · {statuses[job.status]}{" "}
                {job.stage ? `· ${stages[job.stage] || job.stage}` : ""}{" "}
                {job.result?.reused ? "· 内容已存在，复用版本" : ""}
              </span>
              {job.error && <p role="alert">{job.error}</p>}
              {["failed", "interrupted", "cancelled"].includes(job.status) && (
                <button
                  className="text-button"
                  disabled={!connected || action.isPending}
                  onClick={() => action.mutate({ id: job.id, kind: "retry" })}
                >
                  重试 {attachment_key}
                </button>
              )}
              {["queued", "running"].includes(job.status) && (
                <button
                  className="text-button"
                  disabled={!connected || action.isPending}
                  onClick={() => action.mutate({ id: job.id, kind: "cancel" })}
                >
                  取消 {attachment_key}
                </button>
              )}
            </article>
          ))}
        </>
      )}
      {[
        collections.error,
        papers.error,
        submit.error,
        history.error,
        action.error,
      ]
        .filter(Boolean)
        .map((error, index) => (
          <p role="alert" key={index}>
            {error instanceof Error ? error.message : "读取失败"}
          </p>
        ))}
    </section>
  );
}
