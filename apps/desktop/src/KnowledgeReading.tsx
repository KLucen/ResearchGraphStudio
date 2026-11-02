import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type KnowledgeNode } from "./api";

const names: Record<string, string> = {
  research_question: "研究问题",
  claim: "主张",
  method: "方法",
  finding: "结果",
  condition: "条件",
  concept: "概念",
  experiment: "实验",
  metric: "指标",
  argument: "论证",
  limitation: "限制",
};
const origins: Record<string, string> = {
  author_claim: "作者主张",
  authors_experimental_result: "本文实验结果",
  authors_hypothesis: "作者假设",
  cited_claim: "转述他人",
  background: "背景知识",
  unknown: "归属待确认",
};
const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));
function displayText(node: KnowledgeNode): string {
  const payload = node.payload as Record<string, unknown>;
  const source = (payload.statement || payload.summary) as
    { zh?: string } | undefined;
  return String(
    source?.zh ||
      payload.statement_zh ||
      payload.canonical_name_zh ||
      payload.name_zh ||
      payload.label_zh ||
      payload.dimension_zh ||
      payload.value_zh ||
      node.text,
  );
}

export function KnowledgeReading({
  versionId,
  connected,
}: {
  versionId: string;
  connected: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <section className="knowledge-area">
      <button
        className="button secondary"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        论文结构与知识 {open ? "收起" : "展开"}
      </button>
      {open && (
        <Reading key={versionId} versionId={versionId} connected={connected} />
      )}
    </section>
  );
}

function Reading({
  versionId,
  connected,
}: {
  versionId: string;
  connected: boolean;
}) {
  const client = useQueryClient();
  const provider = "project";
  const [allow, setAllow] = useState(false);
  const pipeline = "paper-reading-v1";
  const [selected, setSelected] = useState("");
  const selection = useRef("");
  const [evidenceId, setEvidenceId] = useState("");
  const [sectionId, setSectionId] = useState("");
  const [kind, setKind] = useState("");
  const structure = useQuery({
    queryKey: ["structure", versionId],
    queryFn: () => api.structure(versionId),
    enabled: connected,
    refetchInterval: 3000,
  });
  const knowledge = useQuery({
    queryKey: ["knowledge", versionId],
    queryFn: () => api.knowledge(versionId),
    enabled: connected,
    refetchInterval: 2000,
  });
  const runs = useQuery({
    queryKey: ["runs", versionId],
    queryFn: () => api.runs(versionId),
    enabled: connected,
    refetchInterval: 2000,
  });
  const detail = useQuery({
    queryKey: ["node", selected],
    queryFn: () => api.node(selected),
    enabled: connected && !!selected,
  });
  const preview = useQuery({
    queryKey: ["preview", evidenceId],
    queryFn: () => api.preview(evidenceId),
    enabled: connected && !!evidenceId,
    retry: false,
  });
  const extract = useMutation({
    mutationFn: () => api.extract(versionId, provider, allow, pipeline),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
  const evidence = structure.data?.evidence.find((e) => e.id === evidenceId);
  const cards =
    knowledge.data?.items.filter((n) => !kind || n.kind === kind) ?? [];
  async function choose(node: KnowledgeNode) {
    selection.current = node.id;
    setSelected(node.id);
    setEvidenceId("");
    setSectionId("");
    if (!connected) return;
    try {
      const result = await client.fetchQuery({
        queryKey: ["node", node.id],
        queryFn: () => api.node(node.id),
      });
      if (selection.current !== node.id) return;
      setEvidenceId(result.evidence[0]?.id ?? "");
      setSectionId(result.evidence[0]?.section_id ?? "");
    } catch {
      // The detail query renders the error; no stale evidence is shown.
    }
  }
  return (
    <div>
      <h3>Paper & Reading</h3>
      <p className="quiet-note">
        当前展示新版 Schema 的候选与图谱。历史知识保留，不参与新版建图。
      </p>
      <div className="import-controls">
        <span>使用全局 Extraction 模型</span>
        <button
          className="button primary"
          disabled={!connected || extract.isPending || !allow}
          onClick={() => extract.mutate()}
        >
          生成论文知识图谱
        </button>
      </div>
      <label className="quality-note">
        <input
          type="checkbox"
          checked={allow}
          onChange={(e) => setAllow(e.target.checked)}
        />{" "}
        同意向已配置模型发送当前论文解析片段及证据 ID。私人笔记不参与此次抽取。
      </label>
      {extract.isSuccess && (
        <p role="status">
          抽取任务已排队，可在上方任务记录查看阶段、取消或重试。
        </p>
      )}
      {[structure.error, knowledge.error, detail.error, extract.error]
        .filter(Boolean)
        .map((e, i) => (
          <p role="alert" className="error-text" key={i}>
            {errorText(e)}
          </p>
        ))}
      <div className="reading-grid">
        <details className="reading-sections">
          <summary>章节与证据索引（按需查看）</summary>
          <nav aria-label="论文章节">
            <h4>章节与证据</h4>
            {structure.data?.sections.map((section) => (
              <button
                className={
                  sectionId === section.id
                    ? "paper-item selected"
                    : "paper-item"
                }
                key={section.id}
                onClick={() => {
                  selection.current = "";
                  setSectionId(section.id);
                  setEvidenceId(
                    structure.data?.evidence.find(
                      (e) => e.section_id === section.id,
                    )?.id ?? "",
                  );
                }}
              >
                {section.title}
                <small>
                  {section.role === "other" ? "结构待确认" : section.role}
                </small>
              </button>
            ))}
            {!structure.data?.sections.length && (
              <p>没有文本结构，扫描件需要另行处理。</p>
            )}
          </nav>
        </details>
        <div className="evidence-reading" aria-label="证据原文">
          <h4>原文回查</h4>
          {evidence ? (
            <>
              <p>
                PDF 第 {evidence.page_index + 1} 页 · 字符 [
                {evidence.start_offset}, {evidence.end_offset})
              </p>
              <pre className="evidence-quote">
                <mark>{evidence.quote}</mark>
              </pre>
              {preview.isFetching && <p>正在加载 PDF 原页面…</p>}
              {preview.error && (
                <p className="quality-note">{errorText(preview.error)}</p>
              )}
              {preview.data && (
                <>
                  <p className="muted">黄色为解析文本块范围，非逐字高亮。</p>
                  <img
                    className="pdf-preview"
                    src={preview.data.data_url}
                    alt={`PDF 第 ${preview.data.page_index + 1} 页原文块高亮`}
                  />
                </>
              )}
            </>
          ) : (
            <p className="muted">
              选择章节或卡片中的证据，核对原页面与解析文本。
            </p>
          )}
          {structure.data?.evidence
            .filter((e) => e.section_id === sectionId)
            .map((e, i) => (
              <button
                className="text-button"
                key={e.id}
                onClick={() => setEvidenceId(e.id)}
              >
                原文片段 {i + 1}
              </button>
            ))}
        </div>
        <div className="knowledge-cards">
          <h4>知识卡片 · {knowledge.data?.items.length ?? 0}</h4>
          <label>
            类型{" "}
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">全部</option>
              {Object.entries(names).map(([v, n]) => (
                <option value={v} key={v}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          {cards.map((node) => (
            <button
              className={
                selected === node.id
                  ? "knowledge-card selected"
                  : "knowledge-card"
              }
              onClick={() => void choose(node)}
              key={node.id}
            >
              <span>{names[node.kind]} · 候选知识</span>
              <strong>{displayText(node)}</strong>
              {displayText(node) !== node.text && (
                <small>英文原文：{node.text}</small>
              )}
              <small>
                {node.source_status === "source_verified"
                  ? "来源已验证"
                  : "来源未验证"}{" "}
                · {origins[node.origin] ?? node.origin}
              </small>
              {node.kind === "condition" && (
                <small>
                  {node.known_state} · {node.value ?? "未知/不适用"} {node.unit}
                </small>
              )}
            </button>
          ))}
          {!cards.length && (
            <p className="muted">
              尚无此类知识。抽取完成后，候选内容会显示在这里。
            </p>
          )}
        </div>
      </div>
      {detail.data && (
        <details>
          <summary>原始模型与修改历史</summary>
          <pre>
            {JSON.stringify(
              {
                model_run: detail.data.model_run,
                reviews: detail.data.reviews,
              },
              null,
              2,
            )}
          </pre>
        </details>
      )}
      <details>
        <summary>模型调用与原始结果 · {runs.data?.length ?? 0} 次</summary>
        {runs.data?.map((run) => (
          <article className="text-chunk" key={run.id}>
            <strong>
              {run.prompt_name} · {run.provider}/{run.model} · {run.status}
            </strong>
            <p className="mono small">
              运行 {run.id}
              <br />
              Prompt {run.prompt_hash}
              <br />
              输入 {run.input_hash}
            </p>
            {run.error && <p className="error-text">{run.error}</p>}
            {Boolean(run.parameters.normalization) && (
              <p className="quiet-note">
                已移除模型多出的空占位字段；未重新调用模型，原始响应完整保留。
              </p>
            )}
            {Boolean(run.parameters.reading_normalization) && (
              <p className="quiet-note">
                已合并编号和内容完全相同的重复候选；原始响应和去重记录完整保留。
              </p>
            )}
            {run.prompt_name === "P02_local_link_repair" && (
              <p className="quiet-note">
                局部引用修复：仅修复缺失的关系端点，原始抽取结果保留在来源运行中。
              </p>
            )}
            <details>
              <summary>调用参数与修复来源</summary>
              <pre>{JSON.stringify(run.parameters, null, 2)}</pre>
            </details>
            <details>
              <summary>原始输出</summary>
              <pre>{run.raw_output ?? "未返回输出"}</pre>
            </details>
          </article>
        ))}
      </details>
      <ZoteroAnnotations
        versionId={versionId}
        connected={connected}
        onEvidence={setEvidenceId}
      />
    </div>
  );
}

function ZoteroAnnotations({
  versionId,
  connected,
  onEvidence,
}: {
  versionId: string;
  connected: boolean;
  onEvidence: (id: string) => void;
}) {
  const [item, setItem] = useState("");
  const [attachment, setAttachment] = useState("");
  const client = useQueryClient();
  const notes = useQuery({
    queryKey: ["annotations", versionId],
    queryFn: () => api.annotations(versionId),
    enabled: connected,
  });
  const importing = useMutation({
    mutationFn: () => api.importAnnotations(versionId, item, attachment),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["annotations", versionId] });
    },
  });
  return (
    <details>
      <summary>Zotero 批注 · {notes.data?.length ?? 0}</summary>
      <p>
        先通过 PDF 选择器导入 Zotero 的对应附件。仅从本地 API
        读取条目与批注，不修改 Zotero 数据。
      </p>
      <label>
        源条目 Key{" "}
        <input
          value={item}
          onChange={(e) => setItem(e.target.value.toUpperCase())}
          maxLength={8}
        />
      </label>
      <label>
        附件 Key{" "}
        <input
          value={attachment}
          onChange={(e) => setAttachment(e.target.value.toUpperCase())}
          maxLength={8}
        />
      </label>
      <button
        className="button secondary"
        disabled={
          !connected ||
          item.length !== 8 ||
          attachment.length !== 8 ||
          importing.isPending
        }
        onClick={() => importing.mutate()}
      >
        读取并关联批注
      </button>
      {importing.error && <p role="alert">{errorText(importing.error)}</p>}
      {importing.data && (
        <p>
          新增 {importing.data.added} 条，未解析锚点 {importing.data.unresolved}{" "}
          条。
        </p>
      )}
      {notes.data?.map((n) => (
        <article className="text-chunk" key={n.id}>
          <blockquote>{n.text}</blockquote>
          <p>用户评论：{n.comment}</p>
          <small>
            {n.source_item_key}/{n.annotation_key} ·{" "}
            {n.anchor_status === "unresolved" ? "锚点未解析" : "匹配原文块"}
          </small>
          {n.evidence_id && (
            <button
              className="text-button"
              onClick={() => onEvidence(n.evidence_id!)}
            >
              查看关联原文
            </button>
          )}
        </article>
      ))}
    </details>
  );
}
