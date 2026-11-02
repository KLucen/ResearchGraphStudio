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
  saving: "保存与关联",
};
function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

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
  const [extractAfter, setExtractAfter] = useState(true);
  const provider = "project";
  const [allow, setAllow] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const collections = useQuery({
    queryKey: ["zotero-collections", library],
    enabled: connected && enabled,
    queryFn: async () => {
      const all: Collection[] = [];
      for (let offset = 0; offset < 10000; offset += 50) {
        const page = await request<Collection[]>(
          "GET",
          `/api/v1/integrations/zotero/collections?library=${library}&start=${offset}`,
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
  const successIds = history.data
    ?.filter((x) => x.job.status === "succeeded")
    .map((x) => x.job.id)
    .join(",");
  useEffect(() => {
    if (successIds)
      void client.invalidateQueries({ queryKey: ["papers", projectId] });
  }, [successIds, client, projectId]);
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
          extract_after_parse: extractAfter,
          provider,
          allow_network: allow,
        },
        crypto.randomUUID(),
      ),
    onSuccess: () => {
      setChosen({});
      void client.invalidateQueries({
        queryKey: ["zotero-imports", projectId],
      });
      void client.invalidateQueries({ queryKey: ["jobs", projectId] });
    },
  });
  const retry = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "retry" | "cancel" }) =>
      api.jobAction(id, action, crypto.randomUUID()),
    onSuccess: () => {
      void client.invalidateQueries({
        queryKey: ["zotero-imports", projectId],
      });
    },
  });
  const extract = useMutation({
    mutationFn: (revisionId: string) =>
      request<Job>(
        "POST",
        "/api/v1/knowledge/extract",
        {
          document_version_id: revisionId,
          provider,
          allow_network: allow,
          pipeline: "paper-reading-v1",
        },
        crypto.randomUUID(),
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["jobs", projectId] });
    },
  });
  function choose(rows: Choice[], checked: boolean) {
    setChosen((previous) => {
      const next = { ...previous };
      for (const row of rows) {
        if (checked) next[row.attachment_key] = row;
        else delete next[row.attachment_key];
      }
      return next;
    });
  }
  const rows =
    papers.data?.items.flatMap((p) =>
      p.attachments
        .filter((a) => a.available)
        .map((a) => ({ item_key: p.key, attachment_key: a.key })),
    ) ?? [];
  const jobs =
    history.data?.filter(
      (j) => j.collection_key === collection && j.library === library,
    ) ?? [];
  const complete = jobs.filter((j) =>
    ["succeeded", "failed", "cancelled", "interrupted"].includes(j.job.status),
  ).length;
  return (
    <section className="zotero-import" aria-label="Zotero 批量导入">
      <h4>Zotero 分类批量导入</h4>
      <p>
        勾选附件即授权只读导入对应 PDF 与批注。原文件保持在
        Zotero；同一条目的不同 PDF 保留为文献版本。
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
            {collections.data.map((c) => (
              <option key={c.key} value={c.key}>
                {c.data.name} · {c.key}
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
          <label>
            <input
              type="checkbox"
              aria-label="全选本页可用附件"
              checked={
                !!rows.length && rows.every((r) => !!chosen[r.attachment_key])
              }
              disabled={!rows.length}
              onChange={(e) => choose(rows, e.target.checked)}
            />
            全选本页可用附件
          </label>
          {papers.isFetching && <p role="status">读取论文及本地附件状态…</p>}
          {papers.data?.items.map((p) => (
            <article className="text-chunk" key={p.key}>
              <label>
                <input
                  type="checkbox"
                  aria-label={`选择论文 ${p.title}`}
                  checked={p.attachments.some((a) => !!chosen[a.key])}
                  disabled={!p.attachments.some((a) => a.available)}
                  onChange={(e) =>
                    choose(
                      p.attachments
                        .filter((a) => a.available)
                        .map((a) => ({
                          item_key: p.key,
                          attachment_key: a.key,
                        })),
                      e.target.checked,
                    )
                  }
                />{" "}
                <strong>{p.title}</strong>
              </label>
              {!p.attachments.length && <p>没有 PDF 附件</p>}
              {p.attachments.map((a) => (
                <label className="attachment-choice" key={a.key}>
                  <input
                    type="checkbox"
                    aria-label={`选择附件 ${a.key}`}
                    checked={!!chosen[a.key]}
                    disabled={!a.available}
                    onChange={(e) =>
                      choose(
                        [{ item_key: p.key, attachment_key: a.key }],
                        e.target.checked,
                      )
                    }
                  />
                  {a.filename || a.title} · {a.key}{" "}
                  {a.available ? "" : "（本地不可用，请先在 Zotero 下载）"}
                </label>
              ))}
            </article>
          ))}
          {papers.data?.items.length === 0 && <p>没有匹配的论文。</p>}
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
              <input
                type="checkbox"
                checked={extractAfter}
                onChange={(e) => setExtractAfter(e.target.checked)}
              />
              解析后直接建图
            </label>
            <span>全局 Extraction 模型</span>
            <label>
              <input
                type="checkbox"
                checked={allow}
                onChange={(e) => setAllow(e.target.checked)}
              />
              同意向已配置模型发送所选论文原文片段
            </label>
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
                (extractAfter && !allow) ||
                Object.keys(chosen).length === 0 ||
                Object.keys(chosen).length > 50
              }
              onClick={() => submit.mutate()}
            >
              {extractAfter ? "开始建图" : "仅解析"} · 已选{" "}
              {Object.keys(chosen).length} 个附件
            </button>
            <button className="text-button" onClick={() => setChosen({})}>
              清空选择
            </button>
          </div>
          {Object.keys(chosen).length > 50 && (
            <p role="alert">单批最多 50 个附件。</p>
          )}
          {!!jobs.length && (
            <>
              <p>
                本分类最近任务：{complete}/{jobs.length} 已结束，
                {jobs.filter((j) => j.job.status === "succeeded").length} 成功
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
                    {job.stage ? `· ${stages[job.stage] ?? job.stage}` : ""}{" "}
                    {job.result?.reused ? "· 内容已存在，复用版本" : ""}
                  </span>
                  {typeof job.result?.extraction_job_id === "string" && (
                    <small>统一抽取已排队，批次进度及重试见任务记录。</small>
                  )}
                  {job.error && <p role="alert">{job.error}</p>}
                  {job.status === "succeeded" &&
                    !job.result?.extraction_job_id &&
                    typeof job.result?.revision_id === "string" && (
                      <button
                        className="text-button"
                        disabled={!connected || extract.isPending || !allow}
                        onClick={() =>
                          extract.mutate(String(job.result?.revision_id))
                        }
                      >
                        解析并抽取知识
                      </button>
                    )}
                  {["failed", "interrupted", "cancelled"].includes(
                    job.status,
                  ) && (
                    <button
                      className="text-button"
                      disabled={!connected || retry.isPending}
                      onClick={() =>
                        retry.mutate({ id: job.id, action: "retry" })
                      }
                    >
                      重试 {attachment_key}
                    </button>
                  )}
                  {["queued", "running"].includes(job.status) && (
                    <button
                      className="text-button"
                      disabled={!connected || retry.isPending}
                      onClick={() =>
                        retry.mutate({ id: job.id, action: "cancel" })
                      }
                    >
                      取消 {attachment_key}
                    </button>
                  )}
                </article>
              ))}
              {extract.error && <p role="alert">{errorText(extract.error)}</p>}
              <p className="muted">
                此处显示项目最近 100 个 Zotero 任务，更早记录见任务历史。
              </p>
            </>
          )}
        </>
      )}
      {[
        collections.error,
        papers.error,
        submit.error,
        history.error,
        retry.error,
      ]
        .filter(Boolean)
        .map((e, i) => (
          <p role="alert" key={i}>
            {e instanceof Error ? e.message : "读取失败"}
          </p>
        ))}
    </section>
  );
}
